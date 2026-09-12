"""戰情室顧問協調：先試 Bedrock，失敗則規則型降級。不碰派工。"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from config_loader import get_config
from models_schema.assistant import TwinAssistantRequest, TwinAssistantResponse

from .bedrock import assistant_config, converse_text
from .fallback import answer_twin_fallback
from .twin_prompt import build_messages

logger = logging.getLogger(__name__)

_WINDOW_SEC = 60
_hits: dict[str, deque] = defaultdict(deque)


class AssistantRateLimited(Exception):
    """單一操作者超過顧問呼叫上限。"""


def _touch_rate_limit(operator_id: str, limit: int) -> None:
    now = time.time()
    bucket = _hits[operator_id]
    while bucket and now - bucket[0] > _WINDOW_SEC:
        bucket.popleft()
    if limit > 0 and len(bucket) >= limit:
        raise AssistantRateLimited()
    bucket.append(now)


def reset_assistant_limits() -> None:
    _hits.clear()


def answer_twin(payload: TwinAssistantRequest, operator_id: str) -> TwinAssistantResponse:
    cfg = get_config().get("assistant") or {}
    _touch_rate_limit(operator_id, int(cfg.get("rate_limit_per_min", 10)))

    settings = assistant_config()
    fallback_text = answer_twin_fallback(payload.context, payload.question)
    if not settings["enabled"]:
        return TwinAssistantResponse(text=fallback_text, source="fallback", model=None)

    system, messages = build_messages(payload.context, payload.question, payload.history)
    try:
        text = converse_text(system=system, messages=messages, settings=settings)
        return TwinAssistantResponse(text=text, source="bedrock", model=settings["model_id"])
    except Exception as exc:  # 出向失敗一律降級，不把 AWS 細節回前端
        logger.warning("bedrock_unavailable: %s: %s", type(exc).__name__, str(exc)[:180])
        return TwinAssistantResponse(text=fallback_text, source="fallback", model=None)
