"""Redis-backed request rate limiting with an in-memory fallback for local runs.

Redis failures fail open (availability over strict limiting); the fallback
keeps development and Redis-less environments bounded per process.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable

from fastapi import Request
from redis.exceptions import RedisError

from app.auth.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.errors import ApiError

_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class _MemoryWindow:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = self._hits[key]
            while recent and now - recent[0] > self.window_seconds:
                recent.popleft()
            if len(recent) >= self.limit:
                return False
            recent.append(now)
            return True


_memory_windows: dict[tuple[str, int, int], _MemoryWindow] = {}


def _memory(scope: str, limit: int, window_seconds: int) -> _MemoryWindow:
    key = (scope, limit, window_seconds)
    if key not in _memory_windows:
        _memory_windows[key] = _MemoryWindow(limit, window_seconds)
    return _memory_windows[key]


async def _enforce(request: Request, scope: str, limit: int, window_seconds: int, identity: str) -> None:
    settings = get_settings()
    key = f"{settings.redis_key_prefix}voltstop:rate:{scope}:{identity}"
    client = getattr(request.app.state, "redis", None)
    if client is not None:
        try:
            count = await client.eval(_LUA, 1, key, window_seconds)
            allowed = int(count) <= limit
        except RedisError:
            allowed = True
    else:
        allowed = _memory(scope, limit, window_seconds).allow(key)
    if not allowed:
        raise ApiError(429, "RATE_LIMITED", "Too many requests; please slow down and retry")


def rate_limit(scope: str, limit: int, window_seconds: int) -> Callable[..., Any]:
    """IP-scoped limiter for public or provider-facing routes."""

    async def _check(request: Request) -> None:
        host = request.client.host if request.client else "unknown"
        await _enforce(request, scope, limit, window_seconds, host)

    return _check


def user_rate_limit(scope: str, limit: int, window_seconds: int) -> Callable[..., Any]:
    """User-scoped limiter; resolves against the route's own auth dependency."""

    async def _check(request: Request, user: CurrentUser) -> None:
        await _enforce(request, scope, limit, window_seconds, str(user.id))

    return _check
