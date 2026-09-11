"""
最適化調整係數的生效接線（params.coefficients）— ADR-124
==========================================================
把 optimizer 產生、maintainer 核准、存成 ai_optimized 版本的站點調整係數，
接進 ADR-115 的動態目標水位計算。

★決策邊界（ADR-004）：係數是「人核准過的確定性規則參數」，不是模型輸出。
  決策仍由規則引擎做；係數只改變「預期流量」這一個量，不改門檻、不改觸發邏輯。

★三態開關（config.optimization.係數套用模式，預設 off）：
    off    完全不讀參數，行為與接線前相同
    shadow 照常算出套用後的水位但不採用，只附影子值供比對
    on     實際採用

★護欄：生效係數一律夾在 config.optimization.係數上下限（預設 0.8~1.25）。
  ADR-120 的「單次最大調幅 ±10%」管每次調整量，本模組管累積後的絕對值，兩者並存。
  係數缺漏、非數值、非有限或非正數 → 一律視為 1.0（不影響），不讓壞資料放大調度量。

對外暴露：
    current_mode(config) -> str
    bulk_load(station_ids) -> dict[str, dict]        # 一次查完，不逐站打 DB
    resolve(entry, is_dayoff, config) -> dict | None # 算出該站生效係數與依據
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from config_loader import get_config

VALID_MODES = ("off", "shadow", "on")
# ADR-120 產生的係數欄位；基礎乘上情境，其餘欄位目前 optimizer 尚未產生
BASE_KEY = "base_outflow_coef"
WEEKEND_KEY = "env_coef_weekend"


def current_mode(config: Optional[dict] = None) -> str:
    cfg = config or get_config()
    mode = str(cfg.get("optimization", {}).get("係數套用模式", "off")).strip().lower()
    return mode if mode in VALID_MODES else "off"


def _limits(config: Optional[dict] = None) -> tuple[float, float]:
    cfg = config or get_config()
    raw = cfg.get("optimization", {}).get("係數上下限", [0.8, 1.25])
    try:
        low, high = float(raw[0]), float(raw[1])
    except (TypeError, ValueError, IndexError):
        return 0.8, 1.25
    return (low, high) if low <= high else (high, low)


def _sanitize(value) -> float:
    """壞值一律回 1.0（不影響）。不接受布林、非有限、非正數。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 1.0
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return 1.0
    return number


def bulk_load(station_ids: Iterable[str]) -> dict[str, dict]:
    """一次取回多站的生效參數版本（ADR-124：不逐站查 DB）。"""
    from db import params_repo
    return params_repo.get_active_many(station_ids)


def resolve(entry: Optional[dict], is_dayoff: bool,
            config: Optional[dict] = None) -> Optional[dict]:
    """算出該站的生效係數。沒有參數版本或係數全為 1.0 時仍回傳（讓輸出可追溯）。

    回傳 {value, version, applied, clamped}；entry 為 None 時回 None。
    """
    if not entry:
        return None
    params = entry.get("params") or {}
    base = _sanitize(params.get(BASE_KEY, 1.0))
    weekend = _sanitize(params.get(WEEKEND_KEY, 1.0)) if is_dayoff else 1.0
    raw_value = base * weekend
    low, high = _limits(config)
    value = min(high, max(low, raw_value))
    return {
        "value": round(value, 4),
        "version": entry.get("version"),
        "applied": {BASE_KEY: round(base, 4),
                    **({WEEKEND_KEY: round(weekend, 4)} if is_dayoff else {})},
        "clamped": abs(value - raw_value) > 1e-9,
    }


def is_dayoff(moment=None) -> bool:
    """今天是否為放假型態（週末或國定假日，補班日視為上班）——與 ADR-101 dayoff_mode 一致。"""
    import datetime as _dt
    moment = moment or _dt.datetime.now()
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from features.calendar_holiday import get_holiday_feature
        return bool(get_holiday_feature(moment.strftime("%Y%m%d"))["is_holiday"])
    except Exception:
        return moment.weekday() >= 5
