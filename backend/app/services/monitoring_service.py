"""In-memory runtime metrics for lightweight production monitoring."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class MonitoringService:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._ws_active = 0
		self._ws_total = 0
		self._incident_times: deque[float] = deque()
		self._incident_by_source: dict[str, deque[float]] = defaultdict(deque)
		self._rate_limited_times: deque[float] = deque()
		self._rate_limited_by_source: dict[str, deque[float]] = defaultdict(deque)

	def _prune(self, now: float) -> None:
		cutoff = now - 300.0
		while self._incident_times and self._incident_times[0] < cutoff:
			self._incident_times.popleft()
		while self._rate_limited_times and self._rate_limited_times[0] < cutoff:
			self._rate_limited_times.popleft()

		for mapping in (self._incident_by_source, self._rate_limited_by_source):
			empty: list[str] = []
			for source, values in mapping.items():
				while values and values[0] < cutoff:
					values.popleft()
				if not values:
					empty.append(source)
			for source in empty:
				del mapping[source]

	def ws_connected(self) -> int:
		with self._lock:
			self._ws_active += 1
			self._ws_total += 1
			return self._ws_active

	def ws_disconnected(self) -> int:
		with self._lock:
			self._ws_active = max(0, self._ws_active - 1)
			return self._ws_active

	def record_incident(self, source_id: str) -> None:
		now = time.time()
		with self._lock:
			self._incident_times.append(now)
			self._incident_by_source[source_id].append(now)
			self._prune(now)

	def record_rate_limited(self, source_id: str) -> None:
		now = time.time()
		with self._lock:
			self._rate_limited_times.append(now)
			self._rate_limited_by_source[source_id].append(now)
			self._prune(now)

	def snapshot(self) -> dict:
		now = time.time()
		with self._lock:
			self._prune(now)
			incident_cutoff = now - 60.0
			rate_limit_cutoff = now - 60.0

			incidents_last_min = sum(1 for ts in self._incident_times if ts >= incident_cutoff)
			rate_limited_last_min = sum(1 for ts in self._rate_limited_times if ts >= rate_limit_cutoff)

			per_source = {
				source: sum(1 for ts in values if ts >= incident_cutoff)
				for source, values in self._incident_by_source.items()
			}

			rate_limited_per_source = {
				source: sum(1 for ts in values if ts >= rate_limit_cutoff)
				for source, values in self._rate_limited_by_source.items()
			}

			return {
				"ws_active_connections": self._ws_active,
				"ws_total_connections": self._ws_total,
				"incidents_last_60s": incidents_last_min,
				"incidents_last_300s": len(self._incident_times),
				"incidents_per_source_last_60s": per_source,
				"rate_limited_last_60s": rate_limited_last_min,
				"rate_limited_per_source_last_60s": rate_limited_per_source,
			}


monitoring_service = MonitoringService()
