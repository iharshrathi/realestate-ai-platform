"""In-memory sliding-window rate limiter.

Good enough for a single API process. When running several replicas, back it with Redis
(or terminate rate limiting at the gateway) so counters are shared.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError


class RateLimitExceeded(AppError):
    status_code = 429
    default_detail = "Too many requests. Please slow down."


class SlidingWindowLimiter:
    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit_getter: Callable[[], int]) -> Callable[[Request], None]:
    """Create a FastAPI dependency that limits ``bucket`` per client IP."""

    def dependency(request: Request) -> None:
        if not limiter.allow(f"{bucket}:{client_ip(request)}", limit_getter()):
            raise RateLimitExceeded()

    return dependency


login_rate_limit = rate_limit("login", lambda: get_settings().rate_limit_login_per_minute)
chat_rate_limit = rate_limit("chat", lambda: get_settings().rate_limit_chat_per_minute)
