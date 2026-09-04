"""
LightGBM 訓練 + 驗證（prediction.train）— P1
=============================================
第一個誠實數字：seasonal naive baseline vs LightGBM，同一驗證集比較。

依 ADR-002/004/015：
- 時間切分（1~5月訓、6月驗），禁隨機切分
- quantile regression 出 P10/P50/P90（規則引擎吃下界/上界）
- 截斷樣本（is_censored）訓練時排除（ADR-015：Δ=0且空/滿站的假資料）
- 分區間評估（健康/接近空/已空），不只報整體平均

用法：
    python backend/prediction/train.py                 # 全量
    python backend/prediction/train.py --sample 60     # 子集(N站)快速驗證管線
"""

from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from prediction.feature_pipeline import build_training_frame
from prediction.baseline import fit_seasonal_naive, predict_seasonal_naive

BUCKET = "youbike-hackathon-2026"
TRAIN_END = "2026-05-31"   # 1~5月訓、6月驗


def load_data(sample_n: int | None = None) -> pd.DataFrame:
    """讀 S3 全部月份 Parquet（1~6月）。sample_n 只取前 N 站快速驗證管線。"""
    import boto3
    import pyarrow.parquet as pq
    s3 = boto3.client("s3")
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    dfs = []
    for m in months:
        obj = s3.get_object(Bucket=BUCKET, Key=f"youbike_data/year_month={m}/data.parquet")
        dfs.append(pq.read_table(io.BytesIO(obj["Body"].read())).to_pandas())
    df = pd.concat(dfs, ignore_index=True)
    if sample_n:
        keep = df["場站名稱"].drop_duplicates().head(sample_n)
        df = df[df["場站名稱"].isin(keep)]
    return df


def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def evaluate_by_zone(frame, y_true, y_pred_lgb, y_pred_base):
    """分區間評估（ADR-015）：健康/接近空/已空，各報 MAE。"""
    ab = frame["available_bikes"].values
    zones = {
        "已空(可借=0)": ab <= 0,
        "接近空(1-3)": (ab >= 1) & (ab <= 3),
        "健康(>3)": ab > 3,
    }
    rows = []
    for name, mask in zones.items():
        if mask.sum() == 0:
            continue
        rows.append((name, int(mask.sum()),
                     round(mae(y_true[mask], y_pred_base[mask]), 3),
                     round(mae(y_true[mask], y_pred_lgb[mask]), 3)))
    return rows


def run_weight_experiment(df):
    """ADR-019：樣本權重三方案對比（等權 / log 溫和 / 線性）。

    用固定特徵集（含天氣，天氣已定案留）+ L2 探針，對三種 sample_weight 各訓一個模型，
    報各切面 MAE：全樣本 / 已空區 / Δ≠0 / 高流量站 / 低流量站，選在關鍵區改善且不讓極端站主宰者。
    ★權重只用訓練期 turnover 算（feature_pipeline 已保證防洩漏）；turnover/權重欄不進特徵。
    """
    import lightgbm as lgb
    from prediction.feature_pipeline import HORIZON_STEPS
    frame, feat_cols = build_training_frame(df, TRAIN_END, with_weather=True)

    # 防洩漏印證：turnover 應只由訓練期算 → 驗證期(6月)站若訓練期沒資料應為 0
    va6 = frame[frame["is_train"] == 0]
    tr = frame[frame["is_train"] == 1]
    print(f"      [防洩漏印證] turnover 由訓練期 {tr['station_key'].nunique()} 站算；"
          f"驗證期 turnover=0 的列比={float((va6['station_turnover']==0).mean())*100:.1f}%"
          f"（僅新站/無訓練資料站應為 0）", flush=True)

    weight_cols = [("等權", "w_equal"), ("log溫和", "w_log"), ("線性", "w_linear")]
    # 高/低流量站分界：用驗證集的 confidence_tier（high vs low）
    print("\n[3/3] ADR-019 樣本權重三方案對比（L2 探針，含天氣）", flush=True)
    print("=" * 100, flush=True)
    print(f"{'視野':>4} {'權重方案':>8} {'全樣本':>9} {'已空區':>9} {'Δ≠0':>9} "
          f"{'高流量站':>10} {'低流量站':>10}", flush=True)
    for h, mins in HORIZON_STEPS.items():
        tgt = f"target_delta_{mins}"
        sub = frame.dropna(subset=[tgt])
        train = sub[sub["is_train"] == 1]
        valid = sub[sub["is_train"] == 0]
        train_clean = train[train["is_censored"] == 0]

        Xtr = train_clean[feat_cols].astype(float)
        ytr = train_clean[tgt].astype(float)
        Xva = valid[feat_cols].astype(float)
        yva = valid[tgt].astype(float).values
        ab = valid["available_bikes"].values
        empty_mask = ab <= 0
        nz_mask = np.abs(yva) > 0
        tier = valid["confidence_tier"].astype(str).to_numpy()
        hi_mask = tier == "high"
        lo_mask = tier == "low"

        for label, wcol in weight_cols:
            w = train_clean[wcol].astype(float).values
            m = lgb.LGBMRegressor(objective="regression",
                                  n_estimators=300, learning_rate=0.05,
                                  num_leaves=31, min_child_samples=50, verbose=-1)
            m.fit(Xtr, ytr, sample_weight=w)
            pred = m.predict(Xva)

            def zmae(mask):
                return mae(yva[mask], pred[mask]) if mask.sum() else float("nan")
            print(f"{mins:>3}分 {label:>8} {mae(yva, pred):>9.3f} {zmae(empty_mask):>9.3f} "
                  f"{zmae(nz_mask):>9.3f} {zmae(hi_mask):>10.3f} {zmae(lo_mask):>10.3f}", flush=True)
        print("-" * 100, flush=True)
    print("=" * 100, flush=True)
    print("解讀（ADR-019）：比較三方案。理想=高流量站 MAE 下降(模型更重視有訊號的站)，", flush=True)
    print("  且低流量站未被嚴重犧牲。log 溫和 vs 線性看極端站是否主宰。選最佳者定案。", flush=True)
    print("  ★注意：sample_weight 改變訓練目標，MAE 絕對值口徑一致(同驗證集)，可跨方案比。", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None, help="只取前 N 站快速驗證")
    ap.add_argument("--weather", action="store_true", help="併入天氣因子（消融對比用）")
    ap.add_argument("--mode", choices=["ablation", "weight"], default="ablation",
                    help="ablation=因子消融對比 / weight=ADR-019 樣本權重三方案對比(已定案:不採用A,見ADR-019)")
    ap.add_argument("--factor", choices=["weather", "holiday", "dayoff", "poi", "profile"], default="holiday",
                    help="ablation 模式要測的因子：weather=天氣 / holiday=非週末假日(加料) / "
                         "dayoff=is_weekend 升級 is_dayoff(修正既有特徵,非加料) / poi=POI距離(14類) / "
                         "profile=站點行為指紋(日夜比/平假比/早峰流向/峰度/空滿頻率)")
    args = ap.parse_args()

    print(f"[1/4] 讀 S3 資料{'(子集 '+str(args.sample)+' 站)' if args.sample else '(全量)'} ...", flush=True)
    df = load_data(args.sample)
    print(f"      列數 {len(df):,}｜站數 {df['場站名稱'].nunique()}", flush=True)

    from prediction.feature_pipeline import HORIZON_STEPS

    def run_group(**factor_kwargs):
        """跑一組（有/無因子），回各視野結果，供消融對比。

        factor_kwargs：傳給 build_training_frame 的因子開關（with_weather/with_holiday...）。
          不傳=基準組（純時序+站點識別）；傳 with_xxx=True=加該因子組。

        ★消融探針用 L2 迴歸（objective=regression，學均值），不是分位數。
          原因（ADR-002 消融評估方法段）：目標 Δ 有 ~78% 為 0（零膨脹重尾），
          分位數 P50 被 0 主導，任何因子都推不動中位數 → 全部消融都會顯示 +0.00%。
          L2 學均值對因子敏感，才能公平比較每個因子的邊際貢獻。
          （上線出區間仍用分位數 P10/P50/P90，見主訓練流程；探針只為量測因子效果。）
        """
        frame, feat_cols = build_training_frame(df, TRAIN_END, **factor_kwargs)
        import lightgbm as lgb
        out = []
        for h, mins in HORIZON_STEPS.items():
            tgt = f"target_delta_{mins}"
            sub = frame.dropna(subset=[tgt])
            train = sub[sub["is_train"] == 1]
            valid = sub[sub["is_train"] == 0]
            train_clean = train[train["is_censored"] == 0]   # 截斷排除 ADR-015

            yva = valid[tgt].astype(float).values
            Xtr = train_clean[feat_cols].astype(float)
            ytr = train_clean[tgt].astype(float)
            Xva = valid[feat_cols].astype(float)

            m = lgb.LGBMRegressor(objective="regression",  # L2 探針（學均值，對因子敏感）
                                  n_estimators=300, learning_rate=0.05,  # 未調參預設值
                                  num_leaves=31, min_child_samples=50, verbose=-1)
            m.fit(Xtr, ytr)
            pred = m.predict(Xva)

            full_mae = mae(yva, pred)
            # 已空區 MAE（系統存在理由的關鍵區）
            ab = valid["available_bikes"].values
            empty_mask = ab <= 0
            empty_mae = mae(yva[empty_mask], pred[empty_mask]) if empty_mask.sum() else None
            # Δ≠0 樣本 MAE（排除零膨脹稀釋，看真正有變化時的準度）
            nz_mask = np.abs(yva) > 0
            nz_mae = mae(yva[nz_mask], pred[nz_mask]) if nz_mask.sum() else None
            # ADR-018 ③：新舊站分報（老站=訓練期見過；新站=訓練期後才上線的冷啟動站）
            newmask = valid["is_new_station"].values == 1
            old_mae = mae(yva[~newmask], pred[~newmask]) if (~newmask).sum() else None
            new_mae = mae(yva[newmask], pred[newmask]) if newmask.sum() else None
            new_n = int(newmask.sum())
            new_stations = int(valid.loc[newmask, "station_key"].nunique())
            out.append((mins, full_mae, empty_mae, nz_mae,
                        old_mae, new_mae, new_n, new_stations))
        return out

    # ===== ADR-019：樣本權重三方案對比模式 =====
    if args.mode == "weight":
        run_weight_experiment(df)
        return

    # 依 --factor 決定本輪消融的因子（名稱 + build_training_frame 的開關）
    _FACTOR_MAP = {"weather": ("天氣", "with_weather"),
                   "holiday": ("非週末假日", "with_holiday"),
                   "dayoff": ("放假日升級", "dayoff_mode"),
                   "poi": ("POI距離", "with_poi"),
                   "profile": ("行為指紋", "with_profile")}
    FACTOR, factor_kw = _FACTOR_MAP[args.factor]
    print(f"[2/3] 消融對比：基準(無{FACTOR}) vs +{FACTOR} ...", flush=True)
    print(f"      探針=L2迴歸(學均值,對因子敏感);上線出區間仍用分位數", flush=True)
    print("      跑基準組...", flush=True)
    # 測 dayoff 本身時，基準組須明確關掉 dayoff（否則預設 True 會兩組相同）；
    # 測其他因子時，基準組保持預設（含已定案的 dayoff，才是正確對照基準）。
    base_kwargs = {"dayoff_mode": False} if args.factor == "dayoff" else {}
    base_group = run_group(**base_kwargs)
    print(f"      跑 +{FACTOR} 組（全站批次併入）...", flush=True)
    weather_group = run_group(**{factor_kw: True})

    print(f"[3/3] 消融結果：{FACTOR}因子的邊際影響程度", flush=True)
    print("=" * 92, flush=True)
    print(f"{'視野':>5} {'基準全':>9} {'+因子全':>9} {'全改善':>8}  "
          f"{'基準已空':>9} {'+因子已空':>10} {'已空改善':>9}  "
          f"{'基準Δ≠0':>9} {'+因子Δ≠0':>10} {'Δ≠0改善':>9}", flush=True)
    for b_row, w_row in zip(base_group, weather_group):
        mins, b_full, b_emp, b_nz = b_row[0], b_row[1], b_row[2], b_row[3]
        w_full, w_emp, w_nz = w_row[1], w_row[2], w_row[3]

        def pct(a, b):
            return (a - b) / a * 100 if a else 0.0
        print(f"{mins:>3}分 {b_full:>9.3f} {w_full:>9.3f} {pct(b_full, w_full):>+7.2f}%  "
              f"{b_emp:>9.3f} {w_emp:>10.3f} {pct(b_emp, w_emp):>+8.2f}%  "
              f"{b_nz:>9.3f} {w_nz:>10.3f} {pct(b_nz, w_nz):>+8.2f}%", flush=True)
    print("=" * 92, flush=True)
    print("解讀：改善>0 = 因子讓模型更準。三個切面——全樣本(被0稀釋)/已空區(系統存在理由)/Δ≠0(真正有變化時)", flush=True)
    _factor_note = {"天氣": "天氣型態用雨量分級(無日照無法分晴/陰)+溫度倒U舒適度",
                    "非週末假日": "is_holiday/國定假日/連假；邊際價值在 is_weekend 之外的平日型假日與補班日",
                    "放假日升級": "is_weekend→is_dayoff(週末 OR 國定假日視為放假,補班日視為上班);修正既有特徵非加料",
                    "POI距離": "14類POI到最近距離(捷運/火車/轉運/學校/百貨/傳統市場/夜市/醫院/公園×3/河濱/展演/運動中心)+區域類型;靜態全站批次",
                    "行為指紋": "日夜比/平假比/早峰淨流向/峰度/空滿頻率;訓練期算防洩漏;需求密度不進特徵(ADR-014)"}
    print(f"      本輪因子：{FACTOR}。{_factor_note.get(FACTOR, '')}", flush=True)

    # ADR-018 ③：新舊站分報（用 +因子組數字；冷啟動表現不被整體平均掩蓋）
    print("\n[附] 新舊站分報 MAE（ADR-018，+因子組）：老站=訓練期見過 / 新站=訓練期後才上線", flush=True)
    print("-" * 72, flush=True)
    print(f"{'視野':>5} {'老站MAE':>10} {'新站MAE':>10} {'新站樣本數':>12} {'新站數':>8}", flush=True)
    for w_row in weather_group:
        mins, old_mae, new_mae, new_n, new_st = w_row[0], w_row[4], w_row[5], w_row[6], w_row[7]
        new_s = f"{new_mae:.3f}" if new_mae is not None else "—(驗證集無新站)"
        print(f"{mins:>3}分 {old_mae:>10.3f} {new_s:>10} {new_n:>12,} {new_st:>8}", flush=True)
    print("-" * 72, flush=True)
    print("解讀：新站無訓練期歷史(冷啟動)。若新站 MAE 明顯高於老站 → 未來考慮 ADR-001 分層降級(另開 ADR)", flush=True)
    return

    # （舊單組輸出保留供參考，上面 return 已結束）
    print("[4/4] 結果（多視野 ADR-017）", flush=True)
    print("=" * 64, flush=True)
    print(f"{'視野':>6} {'baseline':>10} {'LightGBM':>10} {'改善':>8} {'覆蓋率':>8} {'交叉':>6}", flush=True)
    for mins, bm, lm, cov, cross, _ in results:
        imp = (bm - lm) / bm * 100 if bm else 0
        print(f"{mins:>4}分 {bm:>10.3f} {lm:>10.3f} {imp:>+7.1f}% {cov*100:>7.1f}% {cross*100:>5.1f}%", flush=True)
    print("-" * 64, flush=True)
    print("分區間 MAE（各視野的 已空/接近空/健康，baseline / LightGBM）：", flush=True)
    for mins, bm, lm, cov, cross, zones in results:
        print(f"  [{mins}分]", flush=True)
        for name, n, zbm, zlm in zones:
            print(f"    {name:12} n={n:>8,}  {zbm:>7.3f} / {zlm:>7.3f}", flush=True)
    print("=" * 64, flush=True)
    print("註：各視野直接對累積Δ訓練(分位數不可加F-05);截斷樣本排除;超參數未調", flush=True)


if __name__ == "__main__":
    main()
