"""Redis-backed runtime metrics."""

from __future__ import annotations

import time

from redis.exceptions import RedisError

from .redis_client import get_redis_client


class MonitoringService:
	def __init__(self) -> None:
		pass

	@staticmethod
	def _safe_source(source_id: str) -> str:
		value = (source_id or "unknown").strip()
		return value or "unknown"

	@staticmethod
	def _ws_active_key() -> str:
		return "visionsafe:monitoring:ws:active"

	@staticmethod
	def _ws_total_key() -> str:
		return "visionsafe:monitoring:ws:total"

	@staticmethod
	def _incidents_all_key() -> str:
		return "visionsafe:monitoring:incidents:all"

	@staticmethod
	def _incidents_source_key(source_id: str) -> str:
		return f"visionsafe:monitoring:incidents:source:{source_id}"

	@staticmethod
	def _rate_limited_all_key() -> str:
		return "visionsafe:monitoring:rate_limited:all"

	@staticmethod
	def _rate_limited_source_key(source_id: str) -> str:
		return f"visionsafe:monitoring:rate_limited:source:{source_id}"

	@staticmethod
	def _incidents_sources_set() -> str:
		return "visionsafe:monitoring:incidents:sources"

	@staticmethod
	def _rate_limited_sources_set() -> str:
		return "visionsafe:monitoring:rate_limited:sources"

	def _record_event(self, all_key: str, source_key: str, source_set_key: str, source_id: str) -> None:
		now = time.time()
		now_ms = int(now * 1000)
		member = f"{now_ms}:{time.perf_counter_ns()}"
		cutoff_ms = int((now - 300.0) * 1000)

		redis = get_redis_client()
		pipe = redis.pipeline(transaction=True)
		pipe.zadd(all_key, {member: now_ms})
		pipe.zremrangebyscore(all_key, 0, cutoff_ms)
		pipe.expire(all_key, 305)

		pipe.zadd(source_key, {member: now_ms})
		pipe.zremrangebyscore(source_key, 0, cutoff_ms)
		pipe.expire(source_key, 305)

		pipe.sadd(source_set_key, source_id)
		pipe.expire(source_set_key, 3600)
		pipe.execute()

	def ws_connected(self) -> int:
		try:
			redis = get_redis_client()
			pipe = redis.pipeline(transaction=True)
			pipe.incr(self._ws_active_key())
			pipe.incr(self._ws_total_key())
			active, _total = pipe.execute()
			return int(active)
		except RedisError:
			return 0

	def ws_disconnected(self) -> int:
		try:
			redis = get_redis_client()
			lua = """
			local key = KEYS[1]
			local current = tonumber(redis.call('GET', key) or '0')
			if current <= 0 then
				redis.call('SET', key, 0)
				return 0
			end
			return redis.call('DECR', key)
			"""
			value = redis.eval(lua, 1, self._ws_active_key())
			return int(value)
		except RedisError:
			return 0

	def record_incident(self, source_id: str) -> None:
		source = self._safe_source(source_id)
		try:
			self._record_event(
				self._incidents_all_key(),
				self._incidents_source_key(source),
				self._incidents_sources_set(),
				source,
			)
		except RedisError:
			return

	def record_rate_limited(self, source_id: str) -> None:
		source = self._safe_source(source_id)
		try:
			self._record_event(
				self._rate_limited_all_key(),
				self._rate_limited_source_key(source),
				self._rate_limited_sources_set(),
				source,
			)
		except RedisError:
			return

	def _redis_snapshot(self) -> dict:
		now_ms = int(time.time() * 1000)
		start_60 = now_ms - 60_000
		start_300 = now_ms - 300_000

		redis = get_redis_client()
		active = int(redis.get(self._ws_active_key()) or 0)
		total = int(redis.get(self._ws_total_key()) or 0)

		incidents_last_60 = int(redis.zcount(self._incidents_all_key(), start_60, "+inf"))
		incidents_last_300 = int(redis.zcount(self._incidents_all_key(), start_300, "+inf"))
		rate_limited_last_60 = int(redis.zcount(self._rate_limited_all_key(), start_60, "+inf"))

		incident_sources = redis.smembers(self._incidents_sources_set())
		rate_limit_sources = redis.smembers(self._rate_limited_sources_set())

		incidents_per_source = {
			source: int(redis.zcount(self._incidents_source_key(source), start_60, "+inf"))
			for source in incident_sources
		}

		rate_limited_per_source = {
			source: int(redis.zcount(self._rate_limited_source_key(source), start_60, "+inf"))
			for source in rate_limit_sources
		}

		incidents_per_source = {k: v for k, v in incidents_per_source.items() if v > 0}
		rate_limited_per_source = {k: v for k, v in rate_limited_per_source.items() if v > 0}

		return {
			"ws_active_connections": active,
			"ws_total_connections": total,
			"incidents_last_60s": incidents_last_60,
			"incidents_last_300s": incidents_last_300,
			"incidents_per_source_last_60s": incidents_per_source,
			"rate_limited_last_60s": rate_limited_last_60,
			"rate_limited_per_source_last_60s": rate_limited_per_source,
		}

	def snapshot(self) -> dict:
		try:
			return self._redis_snapshot()
		except RedisError:
			return {
				"redis_available": False,
				"ws_active_connections": 0,
				"ws_total_connections": 0,
				"incidents_last_60s": 0,
				"incidents_last_300s": 0,
				"incidents_per_source_last_60s": {},
				"rate_limited_last_60s": 0,
				"rate_limited_per_source_last_60s": {},
			}


monitoring_service = MonitoringService()
