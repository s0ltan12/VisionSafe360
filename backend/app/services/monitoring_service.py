"""Redis-backed runtime metrics with graceful in-process fallback."""

from __future__ import annotations

import threading
import time

from redis.exceptions import RedisError

from .redis_client import get_redis_client


class MonitoringService:
	def __init__(self) -> None:
		self._lock = threading.Lock()

		# Fallback state when Redis is unavailable.
		self._fb_ws_active = 0
		self._fb_ws_total = 0
		self._fb_incident_times: list[float] = []
		self._fb_rate_limited_times: list[float] = []
		self._fb_incident_by_source: dict[str, list[float]] = {}
		self._fb_rate_limited_by_source: dict[str, list[float]] = {}

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

	def _fallback_prune(self, now: float) -> None:
		cutoff = now - 300.0
		self._fb_incident_times = [ts for ts in self._fb_incident_times if ts >= cutoff]
		self._fb_rate_limited_times = [ts for ts in self._fb_rate_limited_times if ts >= cutoff]

		for mapping in (self._fb_incident_by_source, self._fb_rate_limited_by_source):
			for source in list(mapping.keys()):
				mapping[source] = [ts for ts in mapping[source] if ts >= cutoff]
				if not mapping[source]:
					del mapping[source]

	def ws_connected(self) -> int:
		try:
			redis = get_redis_client()
			pipe = redis.pipeline(transaction=True)
			pipe.incr(self._ws_active_key())
			pipe.incr(self._ws_total_key())
			active, _total = pipe.execute()
			return int(active)
		except RedisError:
			with self._lock:
				self._fb_ws_active += 1
				self._fb_ws_total += 1
				return self._fb_ws_active

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
			with self._lock:
				self._fb_ws_active = max(0, self._fb_ws_active - 1)
				return self._fb_ws_active

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
			now = time.time()
			with self._lock:
				self._fb_incident_times.append(now)
				self._fb_incident_by_source.setdefault(source, []).append(now)
				self._fallback_prune(now)

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
			now = time.time()
			with self._lock:
				self._fb_rate_limited_times.append(now)
				self._fb_rate_limited_by_source.setdefault(source, []).append(now)
				self._fallback_prune(now)

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

	def _fallback_snapshot(self) -> dict:
		now = time.time()
		with self._lock:
			self._fallback_prune(now)
			cutoff = now - 60.0

			incidents_last_60 = sum(1 for ts in self._fb_incident_times if ts >= cutoff)
			rate_limited_last_60 = sum(1 for ts in self._fb_rate_limited_times if ts >= cutoff)

			incidents_per_source = {
				source: sum(1 for ts in values if ts >= cutoff)
				for source, values in self._fb_incident_by_source.items()
			}
			rate_limited_per_source = {
				source: sum(1 for ts in values if ts >= cutoff)
				for source, values in self._fb_rate_limited_by_source.items()
			}

			incidents_per_source = {k: v for k, v in incidents_per_source.items() if v > 0}
			rate_limited_per_source = {k: v for k, v in rate_limited_per_source.items() if v > 0}

			return {
				"ws_active_connections": self._fb_ws_active,
				"ws_total_connections": self._fb_ws_total,
				"incidents_last_60s": incidents_last_60,
				"incidents_last_300s": len(self._fb_incident_times),
				"incidents_per_source_last_60s": incidents_per_source,
				"rate_limited_last_60s": rate_limited_last_60,
				"rate_limited_per_source_last_60s": rate_limited_per_source,
			}

	def snapshot(self) -> dict:
		try:
			return self._redis_snapshot()
		except RedisError:
			return self._fallback_snapshot()


monitoring_service = MonitoringService()
