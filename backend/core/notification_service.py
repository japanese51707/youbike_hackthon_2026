"""ADR-335：把「案件持續緊急多久」換算成該送給誰的分級提醒。

分級（config escalation.階段，預設 [30, 45, 60]）：
  L1 ≥30 分  提醒承辦司機處理，後台確認進度
  L2 ≥45 分  催辦承辦司機，後台核實進度／電話聯絡
  L3 ≥60 分  紅色置頂，管理端安排支援；之後每 escalation.持續提醒間隔_分鐘 再提醒一次

界線刻意用精確秒數比較，不能用畫面上四捨五入的分鐘——29.6 分顯示成 30 分
就提早升級，會讓稽核時間對不起來。

合併（owner 核准時要求）：同一行政區同階段超過 escalation.合併門檻_件數 時，
送一則區級摘要而不是逐站送。早尖峰同時上百站緊急是常態，逐站送等於把後台洗版，
那是另一種形式的阻塞。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Optional

DEFAULT_STAGES = (30, 45, 60)


def _cfg(config: Optional[dict] = None) -> dict:
    if config is None:
        from config_loader import get_config
        config = get_config()
    return (config or {}).get("escalation", {}) or {}


def settings(config: Optional[dict] = None) -> dict:
    cfg = _cfg(config)
    stages = cfg.get("階段") or list(DEFAULT_STAGES)
    return {
        "stages": list(stages),
        "repeat_minutes": int(cfg.get("持續提醒間隔_分鐘", 15) or 15),
        "digest_threshold": int(cfg.get("合併門檻_件數", 3) or 3),
        "mute_minutes": int(cfg.get("靜音分鐘", 10) or 10),
    }


def stage_for(waited_minutes: float, stages: list) -> int:
    """精確秒數換算到第幾階段（0 = 尚未到第一階段）。"""
    reached = 0
    for index, minutes in enumerate(stages, start=1):
        if waited_minutes + 1e-9 >= minutes:
            reached = index
    return reached


def reminder_index_for(waited_minutes: float, stages: list, stage: int,
                       repeat_minutes: int) -> int:
    """最高階段之後的第幾次重覆提醒。未達最高階段一律 0。"""
    if stage < len(stages) or repeat_minutes <= 0:
        return 0
    overdue = waited_minutes - stages[-1]
    if overdue < repeat_minutes:
        return 0
    return int(overdue // repeat_minutes)


def _nid(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return "NOTI-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def assignment_version(case: dict) -> str:
    """承辦版本：轉派後要讓新承辦收到自己的提醒，但不重算緊急時間。"""
    rows = case.get("assignments") or []
    if not rows:
        return "none"
    return "|".join(sorted(f"{r.get('task_id')}:{r.get('operator_id')}" for r in rows))


def recipients_for(case: dict, controllers: list) -> list:
    """誰該收到這個案件的提醒。

    - 有有效承辦：承辦司機（＋隨車）＋ 全體管理端。
    - 無承辦：只通知管理端。不能把所有司機都當收件者——那是另一種轟炸。
    - 承辦衝突（多張未結案任務涵蓋同站）：只通知管理端去查，不任選一人扛。
    """
    out = []
    status = case.get("responsibility_status")
    if status in ("assigned", "in_progress"):
        for row in case.get("assignments") or []:
            for key, role in (("operator_id", "driver"), ("escort_id", "driver")):
                who = row.get(key)
                if who:
                    out.append({"recipient_id": who, "recipient_role": role,
                                "task_id": row.get("task_id")})
    for controller in controllers or []:
        out.append({"recipient_id": controller, "recipient_role": "controller",
                    "task_id": None})
    seen = set()
    unique = []
    for row in out:
        key = (row["recipient_id"], row["recipient_role"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _body(case: dict, stage: int, stages: list, reminder_index: int) -> str:
    name = case.get("station_name") or case.get("station_id")
    waited = int(case.get("waited_minutes") or 0)
    tail = f"（第 {reminder_index + 1} 次持續提醒）" if reminder_index else ""
    label = {1: "請儘速處理", 2: "請核實進度，必要時電話聯絡",
             3: "請管理端安排支援"}.get(stage, "請確認")
    return f"{name} 已持續緊急 {waited} 分鐘，{label}{tail}"


def build_notifications(cases: list, controllers: list,
                        now: Optional[_dt.datetime] = None,
                        config: Optional[dict] = None) -> list:
    """算出這一輪應該存在的提醒（不寫 DB，純函式，方便測試）。

    回傳 list of dict，欄位對齊 notifications_repo.ensure 的參數。
    """
    conf = settings(config)
    stages = conf["stages"]
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    stamp = moment.isoformat()

    # 先算每一件的階段，再決定要不要合併
    staged = []
    for case in cases or []:
        if case.get("closed_at"):
            continue
        waited = float(case.get("waited_minutes") or 0)
        stage = stage_for(waited, stages)
        if stage < 1:
            continue
        staged.append((case, stage,
                       reminder_index_for(waited, stages, stage, conf["repeat_minutes"])))

    # 合併：同區同階段超過門檻 → 一則區級摘要取代逐站
    grouped: dict = {}
    for case, stage, reminder in staged:
        grouped.setdefault((case.get("district") or "未分區", stage), []).append(
            (case, reminder))

    out = []
    for (district, stage), rows in grouped.items():
        if len(rows) > conf["digest_threshold"]:
            digest_key = f"{district}:{stage}"
            reminder = max(r for _, r in rows)
            body = f"{district} 有 {len(rows)} 站持續緊急超過 {stages[stage - 1]} 分鐘"
            # 合併後仍要送到「所有相關收件人」：各案承辦 + 管理端
            recipients = []
            for case, _ in rows:
                recipients.extend(recipients_for(case, controllers))
            seen = set()
            for row in recipients:
                key = (row["recipient_id"], row["recipient_role"])
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "notification_id": _nid(digest_key, row["recipient_id"], reminder),
                    "case_id": rows[0][0]["case_id"],   # 代表案件，詳情頁展開全部
                    "stage": stage,
                    "recipient_id": row["recipient_id"],
                    "recipient_role": row["recipient_role"],
                    "task_id": row.get("task_id"),
                    "assignment_version": digest_key,
                    "reminder_index": reminder,
                    "created_at": stamp,
                    "digest_key": digest_key,
                    "body": body,
                })
            continue
        for case, reminder in rows:
            version = assignment_version(case)
            for row in recipients_for(case, controllers):
                out.append({
                    "notification_id": _nid(case["case_id"], stage, row["recipient_id"],
                                            version, reminder),
                    "case_id": case["case_id"],
                    "stage": stage,
                    "recipient_id": row["recipient_id"],
                    "recipient_role": row["recipient_role"],
                    "task_id": row.get("task_id"),
                    "assignment_version": version,
                    "reminder_index": reminder,
                    "created_at": stamp,
                    "digest_key": None,
                    "body": _body(case, stage, stages, reminder),
                })
    return out


def sync_notifications(cases: list, controllers: list,
                       now: Optional[_dt.datetime] = None,
                       config: Optional[dict] = None) -> list:
    """算出並冪等寫入這一輪的提醒。回傳實際存在的通知列。"""
    from db import notifications_repo

    rows = build_notifications(cases, controllers, now=now, config=config)
    saved = []
    for row in rows:
        stored = notifications_repo.ensure(row)
        if stored:
            saved.append(stored)
    return saved
