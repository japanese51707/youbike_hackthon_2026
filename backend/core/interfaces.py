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
from typing import Protocol


@dataclass
class PredictionInterval:
    """單一視野的預測區間（B 的 predict 輸出）。

    point/lower/upper 皆為「該視野目標時點的預測可借車數（存量）」。
    多視野時回傳多個 PredictionInterval（見 MultiHorizonPrediction）。
    """
    predicted_available: float   # 點估計（僅供顯示，規則引擎不吃）
    lower_bound: float           # 下界（悲觀：車最少）→ 防空站用
    upper_bound: float           # 上界（悲觀：車最多）→ 防滿站用
    horizon_minutes: int         # 前瞻分鐘數（分鐘數，不綁資料格數，ADR-107）
    source: str = "mock"         # 來源標記（mock / lightgbm / historical_fallback）


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

        point = max(0.0, min(total, available + drift))
        # 區間寬度：容量越大越寬（±10% 容量，至少 ±1）
        half = max(1.0, total * 0.10)
        lower = max(0.0, point - half)
        upper = min(total, point + half)
        return PredictionInterval(
            predicted_available=round(point, 1),
            lower_bound=round(lower, 1),
            upper_bound=round(upper, 1),
            horizon_minutes=horizon_minutes,
            source="mock",
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


# 預設用 mock（A6 整合時改這裡指向 B 的實作）
def get_predictor() -> Predictor:
    return MockPredictor()


def get_urgency_calculator() -> UrgencyCalculator:
    return MockUrgencyCalculator()
