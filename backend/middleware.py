"""
中介層（middleware）— rate limit
==================================
入向 DoS 防護：限制每個來源 IP 每分鐘的請求數（config.security.rate_limit_per_min）。

實作：記憶體滑動視窗計數（每 IP 一個時間戳佇列，清掉 60 秒前的）。
輕量、無外部依賴，適合黑客松/單機。正式大流量應改 Redis / 反向代理層限流。

超過上限回 429（Too Many Requests），不外洩內部細節。
健康檢查等路徑可在 config.security.rate_limit_exempt_paths 豁免。
"""

from __future__ import annotations
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_WINDOW_SEC = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_min: int, exempt_paths: list[str] | None = None):
        super().__init__(app)
        self._limit = int(limit_per_min)
        self._exempt = set(exempt_paths or [])
        # {client_ip: deque[timestamp]}
        self._hits: dict[str, deque] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        # 若之後放在反向代理後，應改讀 X-Forwarded-For 的第一段（且信任代理）
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._exempt or self._limit <= 0:
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()
        q = self._hits[ip]

        # 清掉視窗外的舊時間戳
        cutoff = now - _WINDOW_SEC
        while q and q[0] < cutoff:
            q.popleft()

        if len(q) >= self._limit:
            retry_after = int(_WINDOW_SEC - (now - q[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited",
                         "message": "請求過於頻繁，請稍後再試"},
                headers={"Retry-After": str(retry_after)},
            )

        q.append(now)
        return await call_next(request)
