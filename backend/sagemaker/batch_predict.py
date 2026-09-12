"""
SageMaker Processing Job：全站批次預測（ADR-306/307 雲端批次推論示範）
=====================================================================
在 SageMaker 受管執行個體上，用團隊訓練好的 LightGBM 模型對「一批站點」做多視野預測，
結果寫回 S3。定位：

  - 即時單站預測仍由後端服務跑（毫秒級，見 core/interfaces.py）。
  - 本 job 展示「雲端可擴展的批次推論」：一次算全部站點、按需啟動、跑完自動關，
    符合競賽「資源節制」規範。未來可延伸為「每日重訓 + 批次回填」的排程管線。

SageMaker Processing 慣例路徑（容器內）：
  /opt/ml/processing/model/   輸入：模型包（meta.json / model_*.txt / serving_features.json）
  /opt/ml/processing/input/   輸入：待預測的站點快照（stations.json）
  /opt/ml/processing/output/  輸出：預測結果（predictions.json）→ SageMaker 自動上傳回 S3

本檔在 sklearn 內建 container 執行；lightgbm 於執行時安裝（Processing 允許）。
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

MODEL_DIR = Path("/opt/ml/processing/model")
INPUT_DIR = Path("/opt/ml/processing/input")
OUTPUT_DIR = Path("/opt/ml/processing/output")


def _ensure_lightgbm():
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "lightgbm", "numpy"])


def _load_models(meta):
    import lightgbm as lgb
    models = {}
    for mins in meta["horizons"]:
        for q in meta["quantiles"]:
            path = MODEL_DIR / f"model_{mins}_{q}.txt"
            models[(mins, q)] = lgb.Booster(model_file=str(path))
    return models


def _feature_row(station, feature_cols):
    """把站點快照組成模型特徵向量（缺特徵補 NaN，LightGBM 可吃）。

    這裡用精簡特徵組法示範：即時量 + 日曆。lag/天氣等歷史特徵缺就 NaN，
    模型仍會輸出（degraded），與線上服務語意一致。批次示範重點是「能在雲端跑全站」。
    """
    import numpy as np
    from datetime import datetime

    row = {name: np.nan for name in feature_cols}
    for k in ("available_bikes", "available_docks", "total_docks"):
        if station.get(k) is not None:
            row[k] = float(station[k])
    ts = station.get("observed_at") or station.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            row["hour"] = dt.hour
            row["weekday"] = dt.weekday()
            row["month"] = dt.month
            row["time_slot"] = dt.hour * 2 + int(dt.minute >= 30)
        except (ValueError, TypeError):
            pass
    return np.asarray([[row.get(c, np.nan) for c in feature_cols]], dtype=float)


def main():
    _ensure_lightgbm()
    import numpy as np

    meta = json.loads((MODEL_DIR / "meta.json").read_text())
    feature_cols = meta["feature_cols"]
    models = _load_models(meta)

    stations = json.loads((INPUT_DIR / "stations.json").read_text())
    print(f"[batch] 載入 {len(stations)} 站，{len(models)} 個模型（{meta['horizons']} 視野 × {list(meta['quantiles'])}）")

    results = []
    for st in stations:
        total = float(st.get("total_docks") or 0)
        avail = float(st.get("available_bikes") or 0)
        feats = _feature_row(st, feature_cols)
        horizons = []
        for mins in meta["horizons"]:
            preds = {}
            for q in meta["quantiles"]:
                delta = float(models[(mins, q)].predict(feats, num_threads=1)[0])
                val = avail + delta
                preds[q] = round(max(0.0, min(total, val)) if total else max(0.0, val), 1)
            horizons.append({
                "horizon_minutes": mins,
                "predicted_available": preds.get("p50"),
                "lower_bound": preds.get("p10"),
                "upper_bound": preds.get("p90"),
            })
        results.append({
            "station_id": st.get("station_id"),
            "station_name": st.get("station_name"),
            "current_available": int(avail),
            "total_docks": int(total),
            "horizons": horizons,
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "predictions.json"
    out.write_text(json.dumps({
        "generated_by": "sagemaker-processing",
        "model_horizons": meta["horizons"],
        "quantiles": list(meta["quantiles"]),
        "station_count": len(results),
        "predictions": results,
    }, ensure_ascii=False))
    print(f"[batch] 完成，{len(results)} 站預測寫入 {out}")


if __name__ == "__main__":
    main()
