"""ADR-336 分析：哪些熱門站在尖峰時段有「固定」全空／全滿風險（逐星期判定）。

要找的不是「曾經空過」的站——那太多了。要找的是**值得每天提前佈車的站**：
同一個星期幾、同一個尖峰，空／滿是**反覆發生**的。只有反覆發生，
每天提前兩小時派車去備著才划算。

三道關卡：
  1. 熱門：該尖峰的日均振幅（當日最高可借 − 最低可借）>= 全市 P75
  2. 反覆：該星期幾 × 該尖峰出事日數比例 >= RECUR_RATIO（預設 0.5）
  3. 樣本：該星期幾至少 MIN_DAYS 天

備車量用「該時段淨流出的中位數」，不用平均——極端日會把平均拉高，
備過頭等於把車鎖死在一個站，那些車本來可以去別的地方。

★記憶體：先切尖峰時段（2.25M → 約 0.5M 列）再排序彙總，站名轉 categorical。
  一次載入六個月（13.5M 列）會 OOM。
"""

import glob
import json

import numpy as np
import pandas as pd

PEAKS = {"morning": (7, 9), "evening": (17, 19)}
WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]

RECUR_RATIO = 0.5
MIN_DAYS = 8
MIN_RESERVE = 3
MAX_RESERVE = 15
COLS = ["日期", "行政區", "場站名稱", "總車柱數", "可借車數", "可還位數"]
KEY = ["station", "date", "peak"]


def month_summary(path: str) -> pd.DataFrame:
    """壓成（站×日期×尖峰）的小彙總，約 10 萬列/月。"""
    df = pd.read_parquet(path, columns=COLS)
    ts = pd.to_datetime(df["日期"], errors="coerce")
    hour = ts.dt.hour

    keep = pd.Series(False, index=df.index)
    peak_name = pd.Series("", index=df.index, dtype=object)
    for name, (lo, hi) in PEAKS.items():
        sel = (hour >= lo) & (hour <= hi)
        keep |= sel
        peak_name = peak_name.where(~sel, name)
    keep &= ts.notna()
    if not keep.any():
        return pd.DataFrame()

    small = pd.DataFrame({
        "station": df.loc[keep, "場站名稱"].astype("category"),
        "district": df.loc[keep, "行政區"].astype("category"),
        "peak": peak_name[keep].astype("category"),
        "date": ts[keep].dt.normalize(),
        "weekday": ts[keep].dt.weekday.astype("int8"),
        "ts": ts[keep],
        "avail": pd.to_numeric(df.loc[keep, "可借車數"], errors="coerce").astype("float32"),
        "docks": pd.to_numeric(df.loc[keep, "總車柱數"], errors="coerce").astype("float32"),
        "free": pd.to_numeric(df.loc[keep, "可還位數"], errors="coerce").astype("float32"),
    })
    del df, ts, hour, keep, peak_name
    small = small.dropna(subset=["avail", "docks"])
    small = small[small["docks"] > 0]
    if small.empty:
        return pd.DataFrame()

    # 依時間排序後，同組的 first/last 就是該時段的頭尾觀測（不靠原始列序）
    small = small.sort_values("ts", kind="mergesort")
    out = small.groupby(KEY, observed=True, sort=False).agg(
        district=("district", "first"),
        weekday=("weekday", "first"),
        docks=("docks", "max"),
        max_avail=("avail", "max"),
        min_avail=("avail", "min"),
        min_free=("free", "min"),
        avail_first=("avail", "first"),
        avail_last=("avail", "last"),
    ).reset_index()
    del small

    out["amplitude"] = out["max_avail"] - out["min_avail"]   # 順序無關的「有多忙」
    out["empty"] = out["min_avail"] <= 0
    out["full"] = out["min_free"].fillna(1) <= 0
    out["net_out"] = out["avail_first"] - out["avail_last"]
    out["station"] = out["station"].astype(str)
    out["district"] = out["district"].astype(str)
    out["peak"] = out["peak"].astype(str)
    return out.drop(columns=["max_avail", "min_free", "avail_first", "avail_last"])


def analyse() -> dict:
    files = sorted(glob.glob("output/youbike_parquet/year_month=*/data.parquet"))
    parts = []
    for path in files:
        part = month_summary(path)
        if not part.empty:
            parts.append(part)
        print(f"  已處理 {path.split('=')[-1][:7]}　累計彙總 "
              f"{sum(len(p) for p in parts):,} 列", flush=True)
    daily = pd.concat(parts, ignore_index=True)
    del parts
    print(f"彙總完成：{len(daily):,} 列　站數 {daily['station'].nunique():,}　"
          f"期間 {daily['date'].min().date()} ~ {daily['date'].max().date()}", flush=True)

    results = []
    meta_peaks = {}
    for peak in PEAKS:
        pf = daily[daily["peak"] == peak]
        busy = pf.groupby("station")["amplitude"].mean()
        hot_cut = float(busy.quantile(0.75))
        hot = set(busy[busy >= hot_cut].index)
        meta_peaks[peak] = {"hours": list(PEAKS[peak]), "hot_cut_amplitude": round(hot_cut, 2),
                            "hot_stations": len(hot)}
        print(f"[{peak}] 熱門門檻 日均振幅 >= {hot_cut:.1f} 台　熱門站 {len(hot)}", flush=True)
        pf = pf[pf["station"].isin(hot)]

        for kind in ("empty", "full"):
            stat = (pf.groupby(["station", "district", "weekday"], observed=True)
                      .agg(days=("date", "nunique"), hit=(kind, "sum"),
                           docks=("docks", "max"), net_median=("net_out", "median"))
                      .reset_index())
            stat = stat[stat["days"] >= MIN_DAYS]
            stat["ratio"] = stat["hit"] / stat["days"]
            for _, row in stat[stat["ratio"] >= RECUR_RATIO].iterrows():
                net = row["net_median"]
                net = 0.0 if (net is None or np.isnan(net)) else abs(float(net))
                results.append({
                    "station_name": row["station"],
                    "district": row["district"],
                    "weekday": int(row["weekday"]),
                    "weekday_label": WEEKDAY_NAMES[int(row["weekday"])],
                    "peak": peak,
                    "kind": kind,
                    "days_observed": int(row["days"]),
                    "days_hit": int(row["hit"]),
                    "recurrence": round(float(row["ratio"]), 3),
                    "total_docks": int(row["docks"]),
                    "suggested_reserve": int(min(MAX_RESERVE, max(MIN_RESERVE, round(net)))),
                })
    return {
        "generated_from": "output/youbike_parquet",
        "recurrence_threshold": RECUR_RATIO,
        "min_days": MIN_DAYS,
        "peaks": meta_peaks,
        "rows": sorted(results, key=lambda r: (-r["recurrence"], -r["days_hit"])),
    }


if __name__ == "__main__":
    data = analyse()
    rows = data["rows"]
    print(f"\n符合『固定風險』的 站×星期×尖峰 組合：{len(rows)}")
    print(f"  全空風險 {sum(1 for r in rows if r['kind'] == 'empty')}　"
          f"全滿風險 {sum(1 for r in rows if r['kind'] == 'full')}")
    print(f"  涉及站點 {len({r['station_name'] for r in rows})}")
    print("\n前 20 筆（依反覆率）：")
    for r in rows[:20]:
        print(f"  {r['district']:>4} {r['station_name'][:20]:20} 週{r['weekday_label']} "
              f"{r['peak']:7} {r['kind']:5} 反覆 {r['recurrence']:>5.0%} "
              f"({r['days_hit']:>2}/{r['days_observed']:>2}天) 柱{r['total_docks']:>3} "
              f"建議備 {r['suggested_reserve']:>2} 台")
    with open("docs/analysis/standby_reserve_plan.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n已寫出 docs/analysis/standby_reserve_plan.json")
