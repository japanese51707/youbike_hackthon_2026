"""
調度器（core.dispatcher）— 排序 + 緊急度 + ③覆寫 + 資源限制
=============================================================
職責：把 rule_engine 產出的「需調度清單」轉成「排序後、受資源限制的最終建議」。
不做：觸發判斷（在 rule_engine）、預測（在 predictor）、任務狀態機（在 task_manager）。

排序邏輯（對齊既有決策）：
  1. ③即時覆寫站 = 「最前綴」：被覆寫的站一律排最前面（不改它的 urgency 分數，
     只是排序時強制置頂）。這是刻意的設計——覆寫是人為緊急介入，不污染分數體系。
  2. 其餘依 priority_score（緊急度 0~100）由高到低。

資源限制（config.fleet）：
  最終清單站數 ≤ min(每時段最大調度站數, 調度車數量 × 每趟最大站數)

緊急度來自 B 的 calc_urgency（先用 mock）；priority_level 依分數分級 high/medium/low。

對外暴露：
    build_dispatch_list(stations, config, predictor, urgency_calc, override_station_ids)
        -> list[dict]   # 對齊 api_contract DispatchRecommendation（含 priority_score/level）
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config
from .rule_engine import generate_recommendations
from .interfaces import get_predictor, get_urgency_calculator


def _level(score: float, cfg: dict) -> str:
    """緊急度分數 → 分級。門檻可在 config 覆寫，預設 high≥70 / medium≥40。"""
    band = cfg.get("priority_band", {})
    high = band.get("high_min", 70)
    medium = band.get("medium_min", 40)
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def _rec_id(station_id: str) -> str:
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M")
    return f"REC-{ts}-{station_id}"


def build_dispatch_list(
    stations: list[dict],
    config: Optional[dict] = None,
    predictor=None,
    urgency_calc=None,
    override_station_ids: Optional[set[str]] = None,
) -> list[dict]:
    """產出最終排序 + 資源受限的調度建議清單。

    override_station_ids：③即時覆寫的站，排序時強制置頂（最前綴）。
    """
    cfg = config or get_config()
    pred = predictor or get_predictor()
    urg = urgency_calc or get_urgency_calculator()
    overrides = override_station_ids or set()
    horizon = cfg["fleet"]["響應時間_分鐘"]

    # 1. 規則引擎產出需調度清單
    recs = generate_recommendations(stations, cfg, pred)

    # 2. 每筆補上緊急度分數 + 分級 + recommendation_id + 覆寫旗標
    station_by_id = {s.get("station_id"): s for s in stations}
    for r in recs:
        st = station_by_id.get(r["station_id"], {})
        try:
            interval = pred.predict(st, horizon)
        except NotImplementedError:
            interval = None
        if interval is not None:
            score = urg.calc_urgency(st, interval, r["action"])
        else:
            score = 50.0   # 無預測時的中性分數（降級）
        r["priority_score"] = score
        r["priority_level"] = _level(score, cfg)
        r["recommendation_id"] = _rec_id(r["station_id"])
        r["override_active"] = r["station_id"] in overrides

    # 3. 排序：覆寫站最前綴（override_active True 先），其餘依分數降序，
    #    同分時以流量信心分級 tie-break（ADR-109 機制 C：high 流量站優先）。
    #    ★confidence_tier 只當「同分次要排序鍵」，不改觸發、不改緊急度分數本身
    #      （守 ADR-104：流量是加分項，非調度觸發依據）。
    _tier_rank = {"high": 0, "mid": 1, "low": 2}
    recs.sort(key=lambda r: (not r["override_active"], -r["priority_score"],
                             _tier_rank.get(r.get("confidence_tier", "mid"), 1)))

    # 4. 資源限制：時段上限
    fleet = cfg["fleet"]
    cap = min(int(fleet["每時段最大調度站數"]),
              int(fleet["調度車數量"]) * int(fleet["每趟最大站數"]))
    return recs[:cap]
