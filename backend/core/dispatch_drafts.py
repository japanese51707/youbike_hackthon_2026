"""ADR-302：有界、短期的後端草稿；已確認收據另存 SQLite。"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
from hashlib import sha256
import json
from threading import RLock
import time
from uuid import uuid4

from config_loader import get_config
from core.dispatch_errors import DispatchConflict

_drafts = {}
_lock = RLock()


def _json_numbers(value):
    # 瀏覽器 JSON.stringify 會把 5.0 寫成 5；數值相同不算草稿竄改。
    if type(value) is float and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def fingerprint(draft):
    return sha256(json.dumps(_json_numbers(draft), sort_keys=True, ensure_ascii=False,
                             allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def remember_draft(fn):
    @wraps(fn)
    def wrapped(*args, created_by=None, **kwargs):
        draft = fn(*args, **kwargs)
        if draft.get("error"):
            return draft
        draft["data_mode"] = get_config().get("data_source", {}).get("mode", "mock")
        cfg = get_config()["dispatch_drafts"]
        ttl = cfg["ttl_seconds"]
        draft.update(draft_id=f"DRAFT-{uuid4().hex}", version=1, created_by=created_by,
                     expires_at=(datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat())
        with _lock:
            _purge()
            if len(_drafts) >= cfg["max_entries"]:
                _drafts.pop(next(iter(_drafts)))
            _drafts[draft["draft_id"]] = (time.monotonic() + ttl, deepcopy(draft))
        return deepcopy(draft)
    return wrapped


def _purge():
    expired = [key for key, (deadline, _) in _drafts.items() if deadline <= time.monotonic()]
    for key in expired:
        del _drafts[key]


def get(draft_id, version):
    with _lock:
        _purge()
        entry = _drafts.get(draft_id)
        if entry is None or entry[1]["version"] != version:
            raise DispatchConflict("草稿不存在、已過期或版本不符，請重新預覽")
        return deepcopy(entry[1])


def active_draft_station_ids() -> set[str]:
    """目前仍有效（未過期）草稿所佔用的站 ID 集合。

    ADR-320：自動配單以系統為主，但要避開「人正在手動預覽/草稿」的站
    （手動組單改為緊急人工介入專用）。這些站的 ID 由此提供給自動配單過濾。
    只計入人工建立的草稿（created_by 非系統自動配單身分），避免自動配單自己剛建的
    草稿把站擋掉自己。
    """
    from config_loader import get_config
    auto_id = str(get_config().get("auto_dispatch", {}).get("operator_id", "OP-002"))
    ids: set[str] = set()
    with _lock:
        _purge()
        for _deadline, draft in _drafts.values():
            if str(draft.get("created_by")) == auto_id:
                continue  # 自動配單自己的草稿不算「人工佔用」
            for stop in draft.get("stations", []) or []:
                sid = stop.get("station_id")
                if sid is not None:
                    ids.add(str(sid))
    return ids


def reset_drafts():
    with _lock:
        _drafts.clear()
