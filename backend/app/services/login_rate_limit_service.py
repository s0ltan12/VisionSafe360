"""Redis-backed login rate limiter with in-process fallback.

Limits login attempts per IP address using a sliding-window algorithm
implemented in a Lua script for atomic Redis operations.
"""
from __future__ import annotations

import threading
import time

from redis.exceptions import RedisError

from .redis_client import get_redis_client
from ..config.settings import settings


_LUA_CHECK_AND_CONSUME = """
local key       = KEYS[1]
local now_ms    = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit     = tonumber(ARGV[3])
local member    = ARGV[4]

local cutoff = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)

if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest[2] ~= nil then
        retry_after = math.ceil((window_ms - (now_ms - tonumber(oldest[2]))) / 1000)
        if retry_after < 1 then retry_after = 1 end
    end
    return {0, retry_after}
end

redis.call('ZADD', key, now_ms, member)
redis.call('EXPIRE', key, math.ceil(window_ms / 1000) + 1)
return {1, 0}
"""


class LoginRateLimitService:
    """Sliding-window rate limiter for login endpoints (per IP)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._max_attempts = settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS
        self._window_sec = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
        self._window_ms = self._window_sec * 1000
        # In-process fallback: ip -> [timestamps]
        self._fallback: dict[str, list[float]] = {}

    @staticmethod
    def _key(ip: str) -> str:
        return f"visionsafe:rate_limit:login:{ip or 'unknown'}"

    def _fallback_check(self, ip: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            times = self._fallback.setdefault(ip, [])
            cutoff = now - self._window_sec
            times[:] = [t for t in times if t >= cutoff]
            if len(times) >= self._max_attempts:
                retry_after = max(1, int(self._window_sec - (now - times[0])))
                return False, retry_after
            times.append(now)
            return True, 0

    def check_and_consume(self, ip: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds).

        If allowed is False the caller MUST return HTTP 429.
        """
        now_ms = int(time.time() * 1000)
        member = f"{now_ms}:{time.perf_counter_ns()}"
        try:
            result = get_redis_client().eval(
                _LUA_CHECK_AND_CONSUME,
                1,
                self._key(ip),
                now_ms,
                self._window_ms,
                self._max_attempts,
                member,
            )
            allowed = bool(int(result[0]))
            retry_after = int(result[1]) if len(result) > 1 else 0
            return allowed, retry_after
        except RedisError:
            return self._fallback_check(ip)

    def reset(self, ip: str) -> None:
        """Clear rate limit state for an IP (e.g., after successful login)."""
        try:
            get_redis_client().delete(self._key(ip))
        except RedisError:
            with self._lock:
                self._fallback.pop(ip, None)


login_rate_limit_service = LoginRateLimitService()
