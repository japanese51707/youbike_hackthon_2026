"""
分位數區間的 conformal 校準（prediction.conformal）— ADR-125
=============================================================
規則引擎吃的是區間下界（P10 防空）與上界（P90 防滿），所以區間品質直接決定調度品質。
第三批全量評估顯示：邊際覆蓋率 80.8~81.2%（名目 80%，合格），
但「觀測 Δ≠0」的列只有 67.9%(30分)~75.3%(120分)——**站點真的在動的時候區間太窄**。

做法：conformalized quantile regression（CQR）
  conformity score  E = max(q_lo(x) − y, y − q_hi(x))
  偏移              Q = E 在校準集上的 ⌈(n+1)(1−α)⌉/n 分位數
  校準後區間        [q_lo − Q, q_hi + Q]
在可交換性下有有限樣本覆蓋率保證，且不需重訓模型。

★校準集必須與訓練集不重疊（ADR-125 第 2 點）：用模型訓練過的資料算 E 會低估偏移，
  把區間校得更窄，正好與要解決的問題相反。
★分組校準（Mondrian）解決條件覆蓋率：依「預測量級 |P50 − 現況|」分桶各自算偏移。
  分組變數必須在推論時算得出來，所以不能用「Δ 是否為 0」這種需要標籤的條件。

對外暴露：
    fit(...) -> dict          # 由校準集算出各視野各分組的偏移
    bucket_index(...)         # 推論時決定落在哪一桶
    offset_for(...)           # 取該桶偏移（樣本不足退回全域）
    load(model_dir, fingerprint) / save(model_dir, payload)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np

SCHEMA_VERSION = 1
FILENAME = "conformal.json"


def conformity(y_true, lower, upper) -> np.ndarray:
    """E = max(下界 − 實際, 實際 − 上界)；負值代表實際落在區間內（區間有餘裕）。"""
    y_true = np.asarray(y_true, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    return np.maximum(lower - y_true, y_true - upper)


def _quantile_offset(scores: np.ndarray, alpha: float) -> float:
    """CQR 的有限樣本分位數：⌈(n+1)(1−α)⌉/n；不足一個樣本或全為負則回 0（不縮窄）。"""
    scores = np.asarray(scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    n = scores.size
    if n == 0:
        return 0.0
    level = min(1.0, math.ceil((n + 1) * (1 - alpha)) / n)
    return float(max(0.0, np.quantile(scores, level, method="higher")))


def magnitude(predicted, available) -> np.ndarray:
    """分組變數：|P50 − 現況| ＝ 預測的淨變化量級（推論時算得出來，不需標籤）。"""
    return np.abs(np.asarray(predicted, dtype=float) - np.asarray(available, dtype=float))


def bucket_edges(values, buckets: int) -> list[float]:
    """以校準集的分位數當分桶邊界；退化（邊界重複）時自動減少桶數。"""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or buckets <= 1:
        return []
    qs = np.linspace(0, 1, buckets + 1)[1:-1]
    edges = sorted(set(round(float(v), 6) for v in np.quantile(values, qs)))
    return edges


def bucket_index(value: float, edges) -> int:
    """value 落在第幾桶（0-based）。edges 為空時一律第 0 桶。"""
    if not edges or not math.isfinite(value):
        return 0
    return int(np.searchsorted(np.asarray(edges, dtype=float), float(value), side="right"))


def fit_horizon(y_true, lower, upper, predicted, available, *,
                alpha: float = 0.2, buckets: int = 4, min_samples: int = 500) -> dict:
    """算單一視野的分組偏移。回傳可直接序列化的 dict。"""
    scores = conformity(y_true, lower, upper)
    sizes = magnitude(predicted, available)
    edges = bucket_edges(sizes, buckets)
    index = np.array([bucket_index(v, edges) for v in sizes])
    n_buckets = len(edges) + 1
    offsets, counts = [], []
    for b in range(n_buckets):
        group = scores[index == b]
        offsets.append(round(_quantile_offset(group, alpha), 4))
        counts.append(int(group.size))
    return {
        "edges": edges,
        "offsets": offsets,
        "counts": counts,
        "global_offset": round(_quantile_offset(scores, alpha), 4),
        "global_count": int(scores.size),
        "min_samples": int(min_samples),
    }


def offset_for(entry: dict, value: float) -> float:
    """取該量級對應的偏移；該桶樣本數不足門檻時退回全域偏移（ADR-125 第 3 點）。"""
    if not entry:
        return 0.0
    edges = entry.get("edges") or []
    offsets = entry.get("offsets") or []
    counts = entry.get("counts") or []
    b = bucket_index(value, edges)
    if b < len(offsets) and b < len(counts) and counts[b] >= entry.get("min_samples", 0):
        return float(offsets[b])
    return float(entry.get("global_offset", 0.0))


def save(model_dir, payload: dict) -> Path:
    path = Path(model_dir) / FILENAME
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                  separators=(",", ":")), encoding="utf-8")
    pending.replace(path)
    return path


def load(model_dir, fingerprint: Optional[str] = None) -> Optional[dict]:
    """讀校準檔。缺檔、格式不符或與模型不成套 → 回 None（視為未校準，不拋錯）。

    ADR-121 成套原則：不得把別的模型的偏移套在這個模型上。
    """
    path = Path(model_dir) / FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if payload.get("schema_version") != SCHEMA_VERSION or not payload.get("horizons"):
        return None
    if fingerprint is not None and payload.get("model_fingerprint") != fingerprint:
        return None
    return payload
