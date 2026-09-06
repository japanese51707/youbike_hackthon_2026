"""
B 模組介面契約 + Mock 實作（讓 A 的規則引擎能獨立開發）
=========================================================
規則引擎需要 B 的兩個能力：
  1. predict(station, horizon)     → 預測區間（含下界/上界）
  2. calc_urgency(station, ...)    → 緊急度分數 0~100

這裡定義介面 + 提供 mock 版（用簡單啟發式產生合理值），
讓 A2 不必等 B 完成就能開發與測試。A6 整合時換成 B 的真實實作即可。

呼應 steering §2 介面契約先行、§5 AI 只估計規則引擎決策。
核心：predict 一定回「區間」（下界+上界），不只點估計——
規則引擎防空看下界、防滿看上界（雙向保守觸發）。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class PredictionInterval:
    """單一視野的預測區間（B 的 predict 輸出）。

    到達存量 = 現況可借 + 模型預測淨Δ，組裝在 predictor 層（ADR-111）。

    ★兩套值（ADR-111，避免假數據蓋掉截斷訊號）：
    - lower/upper/predicted_available：**夾過 [0, 總柱]** 的物理可能值，供前端顯示。
    - raw_lower/raw_upper/raw_predicted：**照實、可為負或超過總柱**，供規則引擎判斷截斷
      （raw_lower<0 即穿透空站底、缺口=|raw_lower|；raw_upper>總柱 即穿透滿站頂）。
      raw 預設沿用夾過值（向後相容：B 未提供 raw 時退回夾過值，不影響現有呼叫）。
    """
    predicted_available: float   # 點估計（夾過，僅供顯示，規則引擎不吃）
    lower_bound: float           # 下界（夾過 [0,總柱]，悲觀：車最少）→ 顯示用
    upper_bound: float           # 上界（夾過 [0,總柱]，悲觀：車最多）→ 顯示用
    horizon_minutes: int         # 前瞻分鐘數（分鐘數，不綁資料格數，ADR-107）
    source: str = "mock"         # 來源標記（mock / lightgbm / historical_fallback）
    # ADR-111 raw（照實不夾，截斷判斷用）；None 時退回夾過值（向後相容）
    raw_lower_bound: Optional[float] = None
    raw_upper_bound: Optional[float] = None
    raw_predicted: Optional[float] = None

    def __post_init__(self):
        # raw 未提供時退回夾過值（向後相容：舊 predictor 不會壞，只是失去穿透偵測能力）
        if self.raw_lower_bound is None:
            self.raw_lower_bound = self.lower_bound
        if self.raw_upper_bound is None:
            self.raw_upper_bound = self.upper_bound
        if self.raw_predicted is None:
            self.raw_predicted = self.predicted_available


@dataclass
class MultiHorizonPrediction:
    """多視野預測（ADR-107）：一站含多個 horizon 的區間。

    規則引擎依調度員到達時間，用 for_horizon() 挑最接近的視野。
    """
    station_id: str
    intervals: list  # list[PredictionInterval]，各不同 horizon_minutes

    def for_horizon(self, target_minutes: int) -> "PredictionInterval":
        """挑最接近 target_minutes 的視野（規則引擎依到達時間選）。"""
        if not self.intervals:
            raise ValueError("無任何 horizon 預測")
        return min(self.intervals, key=lambda iv: abs(iv.horizon_minutes - target_minutes))


class Predictor(Protocol):
    """B 的預測模型介面。A 只依賴這個 Protocol。"""

    def predict(self, station: dict, horizon_minutes: int) -> PredictionInterval:
        ...


class UrgencyCalculator(Protocol):
    """B 的緊急度計算介面。"""

    def calc_urgency(self, station: dict, prediction: PredictionInterval, action: str) -> float:
        """回傳緊急度 0~100（越高越急）。"""
        ...


# ────────────────────────────────────────────────────────────
# Mock 實作（A2 開發/測試用；A6 換成 B 的真實模型）
# ────────────────────────────────────────────────────────────

class MockPredictor:
    """用「當前存量 + 借用率」做簡單啟發式，產出合理的預測區間。

    非真實預測，只為讓規則引擎有區間可吃。區間寬度隨容量放大，
    模擬「越大的站不確定性越高」。
    """

    def predict(self, station: dict, horizon_minutes: int = 30) -> PredictionInterval:
        available = float(station.get("available_bikes", 0))
        total = float(station.get("total_docks", 1)) or 1.0
        usage = float(station.get("usage_rate", 0))

        # 啟發式淨流出：借用率低（缺車）的站傾向續降；借用率高的站傾向續升
        # drift 為預測期間的存量變化量（負=續減，正=續增）
        if usage < 30:
            drift = -min(available, total * 0.15)      # 缺車站續流出
        elif usage > 70:
            drift = min(total - available, total * 0.15)  # 滿站站續流入
        else:
            drift = 0.0

        # raw：照實的到達存量（可為負/超過總柱，ADR-111 截斷判斷用，不夾）
        raw_point = available + drift
        half = max(1.0, total * 0.10)   # 區間寬度：容量越大越寬（±10%，至少 ±1）
        raw_lower = raw_point - half
        raw_upper = raw_point + half
        # 夾過值：物理可能值 [0, 總柱]，前端顯示用
        point = max(0.0, min(total, raw_point))
        lower = max(0.0, min(total, raw_lower))
        upper = max(0.0, min(total, raw_upper))
        return PredictionInterval(
            predicted_available=round(point, 1),
            lower_bound=round(lower, 1),
            upper_bound=round(upper, 1),
            horizon_minutes=horizon_minutes,
            source="mock",
            raw_lower_bound=round(raw_lower, 1),
            raw_upper_bound=round(raw_upper, 1),
            raw_predicted=round(raw_point, 1),
        )


class MockUrgencyCalculator:
    """簡易緊急度：離安全緩衝越遠、站越小 → 越急。回 0~100。"""

    def calc_urgency(self, station: dict, prediction: PredictionInterval, action: str) -> float:
        total = float(station.get("total_docks", 1)) or 1.0
        if action == "補車":
            # 下界越低越急
            deficit = max(0.0, 3.0 - prediction.lower_bound)
            base = min(1.0, deficit / 3.0)
        else:  # 取車
            returnable = total - prediction.upper_bound
            deficit = max(0.0, 3.0 - returnable)
            base = min(1.0, deficit / 3.0)
        small = 1.0 - min(1.0, total / 60.0)   # 小站加權
        score = 100.0 * (0.7 * base + 0.3 * small)
        return round(score, 1)


class RealUrgencyCalculator:
    """ADR-112 緊急度分數：分層打底 + 五因素排序，回 0~100。

    分層打底（保證截斷層一定 > 警示層）：
      censored（穿透邊界）70~100 / warning（快空滿未穿透）30~69。
    五因素（落在層級區間內排序）：穿透時機/嚴重層級(打底)/時段人流/當下空滿/穿透幅度。
    ★人流用站×hour 訓練期平均周轉量（station_hour_turnover.json，防洩漏）。
    ★confidence_tier 不進分數（守 ADR-104）。
    """
    _TURNOVER = None  # 類層級快取（站×hour 周轉表）

    def __init__(self):
        if RealUrgencyCalculator._TURNOVER is None:
            RealUrgencyCalculator._TURNOVER = self._load_turnover()

    @staticmethod
    def _load_turnover() -> dict:
        import json
        from pathlib import Path
        p = Path(__file__).parent.parent / "features" / "station_hour_turnover.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"by_station_hour": {}, "station_avg": {}, "global_p90": 2.5}

    def _flow_score(self, station: dict) -> float:
        """時段人流分 0~1：該站×該 hour 訓練期平均周轉量，用全市 P90 正規化。"""
        t = self._TURNOVER
        sk = station.get("station_key") or station.get("station_id", "")
        hour = int(station.get("hour", 12))  # 當前小時；未提供預設中午
        by = t.get("by_station_hour", {}).get(str(sk), {})
        val = by.get(str(hour))
        if val is None:  # 退回該站整體平均
            val = t.get("station_avg", {}).get(str(sk), 0.0)
        p90 = t.get("global_p90", 2.5) or 2.5
        return min(1.0, float(val) / p90)   # 用 P90 正規化，超過封頂 1.0

    def calc_urgency(self, station: dict, prediction: PredictionInterval, action: str) -> float:
        total = float(station.get("total_docks", 1)) or 1.0
        available = float(station.get("available_bikes", 0) or 0)
        raw_lo = prediction.raw_lower_bound if prediction else None
        raw_hi = prediction.raw_upper_bound if prediction else None

        # 判斷層級（與 rule_engine 一致）：raw 穿透邊界=censored
        breached = (raw_lo is not None and raw_lo < 0) or (raw_hi is not None and raw_hi > total)

        # 時機分（越早穿透/觸發越急）：用 horizon 分鐘，30→1.0 遞減到 120→0.25
        hm = float(prediction.horizon_minutes) if prediction else 60.0
        timing = max(0.0, min(1.0, (150.0 - hm) / 120.0))  # 30→1.0, 120→0.25
        # 人流分
        flow = self._flow_score(station)
        # 當下已空滿加成
        at_limit = 1.0 if (available <= 0 or available >= total) else 0.0

        if breached:
            # 穿透幅度分：缺口深淺 / 總柱，封頂 1.0
            if raw_lo is not None and raw_lo < 0:
                depth = min(1.0, abs(raw_lo) / max(1.0, total * 0.3))
            else:
                depth = min(1.0, (raw_hi - total) / max(1.0, total * 0.3))
            rank = 0.35 * timing + 0.20 * flow + 0.25 * at_limit + 0.20 * depth
            score = 70.0 + 30.0 * rank   # censored 打底 70
        else:
            # warning 層（去幅度後正規化權重）
            rank = 0.4375 * timing + 0.25 * flow + 0.3125 * at_limit
            score = 30.0 + 39.0 * rank   # warning 打底 30
        return round(score, 1)


# 預設用 mock（A6 整合時改這裡指向 B 的實作）
def get_predictor() -> Predictor:
    return MockPredictor()


def get_urgency_calculator() -> UrgencyCalculator:
    return RealUrgencyCalculator()
