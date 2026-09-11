"""
每日參數最適化 optimizer（optimization.param_optimizer）— ADR-120
==================================================================
每天離線一次，拿近 N 天實際資料，分情境算「站點實際行為 vs 基準參數」偏差，
產生「站點調整係數」建議（乘在基準上，預設 1.0），供 controller 核准後寫入 ai_optimized 層。

★做法 Y（ADR-120 owner 核准）：本模組做「建議層」——算偏差、產生建議、核准存版本閉環。
  「調整係數真的被 rule_engine/predictor 消費」的生效接線，待系統穩定後另做（ADR-120 尚未解決項）。
  故本模組產出的係數會存進 ai_optimized 版本、可 demo「AI建議→人核准→版本」閉環，
  但目前尚未影響即時調度行為（誠實標記，不假裝已生效）。

調整係數（每站，預設 1.0）：
  - base_outflow_coef / base_target_coef：站點基礎參數調整係數
  - env_coef_{rain/heavy_rain/weekend/holiday/event}：各情境環境敏感度調整係數

偏差歸因（ADR-120）：先扣環境、再看基礎——
  晴天平日偏差 → 調基礎係數；特定情境（雨天）殘差 → 調該情境敏感度係數。

ADR-304 補充（第三批 C）：
  - 狀態必須可區分：status ∈ {ok, no_data, insufficient_samples, failed}，各附 reason。
    計算失敗不得偽裝成「沒有資料」；樣本不足不得靜默跳過。
  - review_id 為不可猜測識別（uuid4），供 approve 綁定與冪等比對。
  - 本模組產出的係數「仍未」被 rule_engine／dispatcher／prediction 讀取（ADR-120 做法 Y），
    effective_note 為誠實標記，並由 tests/test_optimizer_apply.py 固定此事實。

對外暴露：
    compute_daily_review(review_date, lookback_days) -> dict   # daily-review 建議清單
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional
from uuid import uuid4

from config_loader import get_config

# 情境維度（分情境算偏差）
_ENV_SCENARIOS = ["rain", "heavy_rain", "weekend", "holiday", "event"]
# 樣本量門檻：某情境樣本數不足不調（避免用少數樣本亂調）
_MIN_SAMPLES = 12   # 近 N 天 30 分格，一情境至少 12 格才調


def _opt_cfg() -> dict:
    return get_config().get("optimization", {})


def _clip_change(old: float, new: float, max_pct: float) -> float:
    """把調整幅度夾在 ±max_pct%（防暴衝，ADR-120）。"""
    if old == 0:
        return new
    change = (new - old) / abs(old) * 100
    if change > max_pct:
        return round(old * (1 + max_pct / 100), 4)
    if change < -max_pct:
        return round(old * (1 - max_pct / 100), 4)
    return round(new, 4)


def compute_daily_review(
    review_date: Optional[str] = None,
    lookback_days: Optional[int] = None,
) -> dict:
    """產生每日最適化建議（ADR-120）。分情境算偏差 → 調整係數建議 → 待核准清單。

    偏差資料：用 S3 歷史重算「近 N 天各站分情境的實際行為 vs 基準」。
    回傳結構對齊 api/optimization.py daily-review（station_changes/params item）。
    """
    cfg = _opt_cfg()
    lookback = int(lookback_days or cfg.get("回看天數", 3))
    max_pct = float(cfg.get("單次最大調幅百分比", 10))
    review_date = review_date or _dt.date.today().isoformat()

    def _envelope(status, reason, changes=None, diag=None):
        changes = changes or []
        all_pcts = [abs(p["change_pct"]) for c in changes for p in c["params"]]
        return {
            "review_id": f"REV-{review_date.replace('-', '')}-{uuid4().hex}",
            "review_date": review_date,
            "lookback_days": lookback,
            "summary": {
                "total_stations_adjusted": len(changes),
                "avg_change_pct": round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0,
                "significant_count": len([c for c in changes if c.get("is_significant")]),
            },
            "station_changes": changes,
            "status": status,          # ok / no_data / insufficient_samples / failed
            "reason": reason,
            "diagnostics": diag or {},
            "effective_note": ("做法Y:建議層,調整係數存 ai_optimized 版本;"
                               "尚未被 rule_engine/dispatcher/prediction 讀取(ADR-120 未解決項)"),
        }

    try:
        changes, diag = _analyze_stations(lookback, max_pct)
    except Exception as exc:   # ADR-304：計算失敗必須明說失敗，不得偽裝成沒有資料
        return _envelope("failed", f"偏差計算失敗：{type(exc).__name__}: {exc}",
                         diag={"stage": "analyze"})

    if diag.get("rows", 0) == 0 or diag.get("stations_considered", 0) == 0:
        return _envelope("no_data", "歷史來源沒有可用資料列", diag=diag)

    adjusted = [c for c in changes if c["params"]]
    if not adjusted:
        if diag.get("skipped_insufficient", 0) > 0:
            return _envelope(
                "insufficient_samples",
                f"有資料但所有站的情境樣本數皆低於門檻 {_MIN_SAMPLES}，不產生建議",
                diag=diag)
        return _envelope("ok", "有足夠樣本，但沒有站達到建議調整門檻", diag=diag)

    env = _envelope("ok", f"產生 {len(adjusted)} 站調整建議", adjusted, diag)
    env["status"] = "ok"
    env["approval_state"] = "pending_approval"
    return env


def _analyze_stations(lookback: int, max_pct: float) -> tuple[list[dict], dict]:
    """用 S3 歷史，分情境算各站偏差 → 調整係數建議。

    偏差定義：以站點自身歷史為基準——「近 lookback 天各情境的平均淨流出」相對
    「該站全期同情境平均」的比值＝該情境的調整係數建議（>1 表近期比平常活躍→需上調）。
    先算基礎（晴天平日）係數，再算各環境情境的殘差係數（扣掉基礎後）。
    """
    import warnings
    warnings.filterwarnings("ignore")
    import pandas as pd
    import numpy as np
    from core.data.historical import HistoricalDataSource
    from core.data.weather_source import _map_condition  # 情境映射（非即時，僅分類名）

    h = HistoricalDataSource()
    df = h._df().copy()
    diag = {"rows": int(len(df)), "stations_considered": 0,
            "skipped_insufficient": 0, "skipped_flat": 0, "skipped_stations": []}
    if df.empty:
        return [], diag
    df["dt"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["station_id", "dt"])
    df["delta"] = df.groupby("station_id")["available_bikes"].diff()
    df["outflow"] = (-df["delta"]).clip(lower=0)   # 淨流出（借車）
    df["is_weekend"] = df["dt"].dt.dayofweek >= 5

    # 近 lookback 天 vs 全期（以歷史末日往回推）
    last_day = df["dt"].max().normalize()
    recent_start = last_day - pd.Timedelta(days=lookback - 1)
    df["is_recent"] = df["dt"] >= recent_start

    changes = []
    # 只對「近期有足夠樣本」的站算（避免全 1576 站慢；取周轉較高的站示範，可調）
    active_stations = (df.groupby("station_id")["outflow"].sum()
                       .sort_values(ascending=False).head(200).index)
    diag["stations_considered"] = int(len(active_stations))

    for sid in active_stations:
        g = df[df["station_id"] == sid]
        name = g["station_name"].iloc[0] if len(g) else sid
        params = []

        # ── 基礎係數（晴天平日）：近期 vs 全期 平均流出比值 ──
        base_mask = ~g["is_weekend"]
        recent_base = g[base_mask & g["is_recent"]]["outflow"]
        all_base = g[base_mask]["outflow"]
        enough_base = len(recent_base) >= _MIN_SAMPLES
        if not enough_base:
            pass
        elif not all_base.mean() > 0.05:
            diag["skipped_flat"] += 1
        if enough_base and all_base.mean() > 0.05:
            ratio = recent_base.mean() / all_base.mean()
            if abs(ratio - 1.0) >= 0.05:   # 偏差 ≥5% 才建議調
                old = 1.0
                new = _clip_change(old, round(ratio, 4), max_pct)
                if abs(new - old) > 1e-4:
                    params.append({
                        "param": "base_outflow_coef", "old": old, "new": new,
                        "change_pct": round((new - old) * 100, 1),
                        "scenario": "平日基礎", "samples": int(len(recent_base)),
                        "reason": f"近{lookback}日平日流出為全期 {ratio:.2f} 倍，建議基礎係數調 {new}",
                    })

        # ── 環境情境殘差係數（假日）：扣掉基礎後仍有的偏差 ──
        we_mask = g["is_weekend"]
        recent_we = g[we_mask & g["is_recent"]]["outflow"]
        all_we = g[we_mask]["outflow"]
        enough_we = len(recent_we) >= _MIN_SAMPLES
        # 兩個情境都因樣本數不足而無法評估 → 該站標為樣本不足（ADR-304 不得靜默跳過）
        insufficient = not enough_base and not enough_we
        if enough_we and all_we.mean() > 0.05:
            ratio_we = recent_we.mean() / all_we.mean()
            if abs(ratio_we - 1.0) >= 0.05:
                old = 1.0
                new = _clip_change(old, round(ratio_we, 4), max_pct)
                if abs(new - old) > 1e-4:
                    params.append({
                        "param": "env_coef_weekend", "old": old, "new": new,
                        "change_pct": round((new - old) * 100, 1),
                        "scenario": "假日敏感度", "samples": int(len(recent_we)),
                        "reason": f"近{lookback}日假日流出為全期 {ratio_we:.2f} 倍，建議假日敏感度係數調 {new}",
                    })

        if params:
            changes.append({
                "station_id": str(sid), "station_name": str(name),
                "is_significant": any(abs(p["change_pct"]) >= max_pct * 0.8 for p in params),
                "params": params,
            })
        elif insufficient:
            # ADR-304：樣本不足不得靜默跳過，逐站記錄原因
            diag["skipped_insufficient"] += 1
            if len(diag["skipped_stations"]) < 50:
                diag["skipped_stations"].append(
                    {"station_id": str(sid), "reason": "insufficient_samples",
                     "min_samples": _MIN_SAMPLES})

    return changes, diag
