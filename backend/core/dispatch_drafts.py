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


def reset_drafts():
    with _lock:
        _drafts.clear()
