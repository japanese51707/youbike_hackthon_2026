"""
行政區人力分派分析（調度員 driver + 駐點員 stationed）
=====================================================
讀 S3 歷史 Parquet（1–6 月官方資料），依各行政區的「調度工作量」與
「高周轉尖峰站」算出人力分派建議，輸出 JSON 供後端 seed 預設分派。

分派邏輯（可解釋的啟發式，非黑箱）：
  A. 調度員（driver，跨站巡迴補/取車）：
     各區工作量指標 = 標準化(空站頻率) + 標準化(滿站頻率) + 標準化(周轉量)
     再依工作量占比，用「最大餘數法」把 N 名調度員整數分配到各區（每區至少 1）。
     直覺：空站/滿站越頻繁、車流周轉越大的區，越需要調度人力。

  B. 駐點員（stationed，守熱門站現場調節）：
     各區「尖峰高周轉站」數（日均周轉量 ≥ 全市 P75 的站）越多，配越多駐點員；
     每區駐點員數 = 依高周轉站占比用最大餘數法分配（可為 0，非每區都需駐點）。
     另附各區「駐點候選站」（該區周轉量前幾名），供 seed 指定 stationed_at。

輸出：docs/analysis/workforce_allocation.json
用法：python analysis_workforce_allocation.py
      （需 AWS 憑證可讀 s3://youbike-hackathon-2026-use1/youbike_data/）
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import boto3
import pandas as pd
import pyarrow.parquet as pq

# ── 資料來源（對齊 config.yaml / historical.py）──
BUCKET = os.environ.get("YOUBIKE_S3_BUCKET", "youbike-hackathon-2026-use1")
PREFIX = os.environ.get("YOUBIKE_S3_PREFIX", "youbike_data")
MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]  # 1–6 月官方資料

# ── 人力總數（對齊 operators_repo seed）──
N_DRIVERS = 350
N_STATIONED = 30

OUT_PATH = Path("docs/analysis/workforce_allocation.json")

_COL_MAP = {
    "日期": "timestamp",
    "行政區": "district",
    "場站名稱": "station_name",
    "總車柱數": "total_docks",
    "可借車數": "available_bikes",
    "可還位數": "available_docks",
    "經度": "lng",
    "緯度": "lat",
    "借用率": "usage_rate",
    "是否空站": "is_empty",
    "是否滿站": "is_full",
}


def load_months(months: list[str]) -> pd.DataFrame:
    """讀多個月份分區的 Parquet，合併成一個 DataFrame。缺月不致命。"""
    s3 = boto3.client("s3")
    frames = []
    for m in months:
        key = f"{PREFIX}/year_month={m}/data.parquet"
        try:
            obj = s3.get_object(Bucket=BUCKET, Key=key)
            df = pq.read_table(io.BytesIO(obj["Body"].read())).to_pandas()
            df = df.rename(columns=_COL_MAP)
            df["year_month"] = m
            frames.append(df)
            print(f"  ✓ {m}：{len(df):,} 筆")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {m}：讀取失敗（{e}）— 略過")
    if not frames:
        raise SystemExit("沒有任何月份資料可用，請確認 AWS 憑證與 bucket。")
    return pd.concat(frames, ignore_index=True)


def _fallback_flags(df: pd.DataFrame) -> pd.DataFrame:
    """若原始資料無 is_empty/is_full 欄，用可借/可還推算。"""
    if "is_empty" not in df.columns:
        df["is_empty"] = (df["available_bikes"] == 0).astype(int)
    if "is_full" not in df.columns:
        df["is_full"] = (df["available_docks"] == 0).astype(int)
    return df


def station_turnover(df: pd.DataFrame) -> pd.DataFrame:
    """算每站日均周轉量（相鄰時段 |Δ可借車數| 總和 / 天數）。"""
    df = df.sort_values(["station_name", "timestamp"])
    df["_delta"] = df.groupby("station_name")["available_bikes"].diff().abs()
    grp = df.groupby("station_name")
    turnover = grp["_delta"].sum()
    n_slots = grp["available_bikes"].count()
    days = (n_slots / 48.0).clip(lower=1)  # 每天 48 格（30 分一格）
    daily_turnover = (turnover / days).round(1)
    district = grp["district"].first()
    return pd.DataFrame({
        "district": district,
        "avg_daily_turnover": daily_turnover,
    }).reset_index()


def largest_remainder(weights: dict[str, float], total: int,
                      min_each: int = 0) -> dict[str, int]:
    """最大餘數法：依權重占比把 total 個整數名額分到各鍵，總和剛好=total。

    min_each>0：先保底每鍵 min_each，再把剩餘按占比分。
    """
    keys = list(weights)
    wsum = sum(weights.values()) or 1.0
    reserved = min_each * len(keys)
    pool = max(0, total - reserved)
    raw = {k: weights[k] / wsum * pool for k in keys}
    base = {k: int(raw[k]) for k in keys}
    used = sum(base.values())
    remainder = pool - used
    # 餘數大者優先 +1
    for k in sorted(keys, key=lambda x: raw[x] - int(raw[x]), reverse=True)[:remainder]:
        base[k] += 1
    return {k: base[k] + min_each for k in keys}


def normalize(series: pd.Series) -> pd.Series:
    """min-max 標準化到 0~1；全同值時回 0。"""
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        return series * 0
    return (series - lo) / (hi - lo)


def main() -> None:
    print("=" * 60)
    print("行政區人力分派分析（調度員 + 駐點員）")
    print(f"S3：s3://{BUCKET}/{PREFIX}/ ｜月份：{MONTHS[0]}~{MONTHS[-1]}")
    print("=" * 60)

    print("\n[1/4] 讀 S3 歷史資料 …")
    df = load_months(MONTHS)
    df = _fallback_flags(df)
    print(f"  合計 {len(df):,} 筆，{df['station_name'].nunique()} 站，"
          f"{df['district'].nunique()} 區")

    print("\n[2/4] 算各區調度工作量指標（周轉量主導 + 空/滿站絕對次數）…")
    # ★用「絕對次數/總量」而非「頻率比例」：偏遠山區站少車不動，空站率/滿站率
    #   雖各約 50%，但實際幾乎沒車流、不需調度人力。頻率比例會誤把它們衝到滿分，
    #   所以改用「周轉量（車流負荷）」為主導，空/滿站以絕對次數（每 30 分一格算一次）
    #   計入，低活動區自然被壓低——這才貼近「哪裡真的需要人去調度」。
    dist_grp = df.groupby("district")
    empty_events = dist_grp["is_empty"].sum()   # 空站事件總次數（區內所有站累計）
    full_events = dist_grp["is_full"].sum()     # 滿站事件總次數
    empty_freq = dist_grp["is_empty"].mean()    # 仍保留頻率供輸出參考
    full_freq = dist_grp["is_full"].mean()

    # 周轉量：先算每站日均周轉，再彙總到區（區內站周轉量總和 = 該區總車流負荷）
    st_turn = station_turnover(df)
    dist_turnover = st_turn.groupby("district")["avg_daily_turnover"].sum()

    metrics = pd.DataFrame({
        "empty_freq": empty_freq,
        "full_freq": full_freq,
        "empty_events": empty_events,
        "full_events": full_events,
        "turnover_sum": dist_turnover,
    }).fillna(0.0)

    # 工作量分數 = 周轉量(權重2，主導) + 空站絕對次數 + 滿站絕對次數（皆標準化）
    metrics["workload_score"] = (
        2.0 * normalize(metrics["turnover_sum"])
        + normalize(metrics["empty_events"])
        + normalize(metrics["full_events"])
    ).round(4)
    metrics = metrics.sort_values("workload_score", ascending=False)

    print("  各區工作量（前 10）：")
    for d, row in metrics.head(10).iterrows():
        print(f"    {d:<8} 周轉{row['turnover_sum']:8.0f} "
              f"空站{row['empty_events']:8.0f}次 "
              f"滿站{row['full_events']:8.0f}次 → 分數 {row['workload_score']:.3f}")

    print("\n[3/4] 依工作量分配調度員（最大餘數法，每區至少 1）…")
    driver_weights = metrics["workload_score"].to_dict()
    driver_alloc = largest_remainder(driver_weights, N_DRIVERS, min_each=1)

    # 駐點員：依各區「高周轉站數」分配（全市 P75 為門檻）
    print("\n[4/4] 依高周轉尖峰站分配駐點員 …")
    p75 = st_turn["avg_daily_turnover"].quantile(0.75)
    hot = st_turn[st_turn["avg_daily_turnover"] >= p75]
    hot_by_district = hot.groupby("district").size().to_dict()
    stationed_alloc = largest_remainder(
        {d: float(hot_by_district.get(d, 0)) for d in metrics.index},
        N_STATIONED, min_each=0)

    # 各區駐點候選站（周轉量前 N 名，N = 該區駐點員配額）
    stationed_candidates: dict[str, list[str]] = {}
    for d in metrics.index:
        quota = stationed_alloc.get(d, 0)
        if quota <= 0:
            continue
        top = (st_turn[st_turn["district"] == d]
               .nlargest(quota, "avg_daily_turnover")["station_name"].tolist())
        stationed_candidates[d] = top

    # ── 彙整輸出 ──
    result = {
        "meta": {
            "source": f"s3://{BUCKET}/{PREFIX}/",
            "months": MONTHS,
            "n_records": int(len(df)),
            "n_stations": int(df["station_name"].nunique()),
            "n_districts": int(df["district"].nunique()),
            "n_drivers": N_DRIVERS,
            "n_stationed": N_STATIONED,
            "method": "工作量=周轉量(權重2,主導)+空站絕對次數+滿站絕對次數(皆標準化) → "
                      "最大餘數法整數分配(調度員每區至少1)；駐點員依高周轉站(≥全市P75)數分配，"
                      "候選站取各區周轉量前列。改用周轉量主導+絕對次數,避免偏遠山區空/滿站率高但無車流被誤配人力",
            "turnover_p75": round(float(p75), 1),
        },
        "districts": [],
        "driver_allocation": driver_alloc,
        "stationed_allocation": {k: v for k, v in stationed_alloc.items() if v > 0},
        "stationed_candidates": stationed_candidates,
    }
    for d, row in metrics.iterrows():
        result["districts"].append({
            "district": d,
            "empty_freq_pct": round(float(row["empty_freq"]) * 100, 2),
            "full_freq_pct": round(float(row["full_freq"]) * 100, 2),
            "empty_events": int(row["empty_events"]),
            "full_events": int(row["full_events"]),
            "turnover_sum": round(float(row["turnover_sum"]), 1),
            "workload_score": round(float(row["workload_score"]), 4),
            "drivers": driver_alloc.get(d, 0),
            "stationed": stationed_alloc.get(d, 0),
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("分派結果（依工作量排序）")
    print("=" * 60)
    print(f"{'行政區':<8}{'調度員':>6}{'駐點員':>6}   工作量分數")
    for d in metrics.index:
        print(f"{d:<8}{driver_alloc.get(d,0):>6}{stationed_alloc.get(d,0):>6}"
              f"   {metrics.loc[d,'workload_score']:.3f}")
    print(f"\n調度員合計 {sum(driver_alloc.values())} / {N_DRIVERS}，"
          f"駐點員合計 {sum(stationed_alloc.values())} / {N_STATIONED}")
    print(f"\n💾 已輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
