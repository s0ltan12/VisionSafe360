"""Redis-backed source-based rate limiting with graceful local fallback."""

from __future__ import annotations

import os
import threading
import time

from redis.exceptions import RedisError

from .redis_client import get_redis_client


class RateLimitService:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._limit_per_window = max(1, int(os.getenv("INCIDENT_RATE_LIMIT_PER_WINDOW", "60")))
		self._window_seconds = max(1, int(os.getenv("INCIDENT_RATE_LIMIT_WINDOW_SECONDS", "60")))
		self._window_ms = self._window_seconds * 1000

		# Graceful local fallback when Redis is unavailable.
		self._fallback_events: dict[str, list[float]] = {}

		self._lua_check_and_consume = """
		local key = KEYS[1]
		local now_ms = tonumber(ARGV[1])
		local window_ms = tonumber(ARGV[2])
		local limit = tonumber(ARGV[3])
		local member = ARGV[4]

		local cutoff = now_ms - window_ms
		redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
		local count = redis.call('ZCARD', key)

		if count >= limit then
			local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
			local retry_after = 1
			if oldest[2] ~= nil then
				retry_after = math.ceil((window_ms - (now_ms - tonumber(oldest[2]))) / 1000)
				if retry_after < 1 then
					retry_after = 1
				end
			end
			return {0, retry_after}
		end

		redis.call('ZADD', key, now_ms, member)
		redis.call('EXPIRE', key, math.ceil(window_ms / 1000) + 1)
		return {1, 0}
		"""

	@staticmethod
	def _key(source_id: str) -> str:
		source = source_id or "unknown"
		return f"visionsafe:rate_limit:incidents:{source}"

	def _fallback_check_and_consume(self, source_id: str) -> tuple[bool, int]:
		now = time.time()
		with self._lock:
			values = self._fallback_events.setdefault(source_id, [])
			cutoff = now - float(self._window_seconds)
			values[:] = [v for v in values if v >= cutoff]

			if len(values) >= self._limit_per_window:
				retry_after = max(1, int(self._window_seconds - (now - values[0])))
				return False, retry_after

			values.append(now)
			return True, 0

	def check_and_consume(self, source_id: str) -> tuple[bool, int]:
		source = source_id or "unknown"
		now_ms = int(time.time() * 1000)
		member = f"{now_ms}:{time.perf_counter_ns()}"

		try:
			result = get_redis_client().eval(
				self._lua_check_and_consume,
				1,
				self._key(source),
				now_ms,
				self._window_ms,
				self._limit_per_window,
				member,
			)
			allowed = bool(int(result[0]))
			retry_after = int(result[1]) if len(result) > 1 else 0
			return allowed, retry_after
		except RedisError:
			return self._fallback_check_and_consume(source)

	def snapshot(self) -> dict[str, int]:
		return {
			"limit_per_window": self._limit_per_window,
			"window_seconds": self._window_seconds,
		}


rate_limit_service = RateLimitService()
