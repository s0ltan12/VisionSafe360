"""Simple in-memory source-based rate limiting."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque


class RateLimitService:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._events: dict[str, deque[float]] = defaultdict(deque)
		self._limit_per_window = max(1, int(os.getenv("INCIDENT_RATE_LIMIT_PER_WINDOW", "60")))
		self._window_seconds = max(1, int(os.getenv("INCIDENT_RATE_LIMIT_WINDOW_SECONDS", "60")))

	def _prune(self, source_id: str, now: float) -> None:
		values = self._events[source_id]
		cutoff = now - float(self._window_seconds)
		while values and values[0] < cutoff:
			values.popleft()
		if not values:
			del self._events[source_id]

	def check_and_consume(self, source_id: str) -> tuple[bool, int]:
		now = time.time()
		source = source_id or "unknown"
		with self._lock:
			self._prune(source, now)
			values = self._events[source]
			if len(values) >= self._limit_per_window:
				retry_after = max(1, int(self._window_seconds - (now - values[0])))
				return False, retry_after
			values.append(now)
			return True, 0

	def snapshot(self) -> dict[str, int]:
		return {
			"limit_per_window": self._limit_per_window,
			"window_seconds": self._window_seconds,
		}


rate_limit_service = RateLimitService()
