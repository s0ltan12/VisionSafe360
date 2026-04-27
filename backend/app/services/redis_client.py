"""Redis client singleton for backend runtime services."""

from __future__ import annotations

import os
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError


def _to_bool(value: str | None, default: bool = False) -> bool:
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
	"""Create a cached Redis client instance.

	Environment variables:
	- REDIS_HOST (default: localhost)
	- REDIS_PORT (default: 6379)
	- REDIS_PASSWORD (optional)
	- REDIS_DB (default: 0)
	- REDIS_SSL (default: false)
	- REDIS_SOCKET_TIMEOUT (default: 1.0)
	"""

	host = os.getenv("REDIS_HOST", "localhost")
	port = int(os.getenv("REDIS_PORT", "6379"))
	password = os.getenv("REDIS_PASSWORD") or None
	db = int(os.getenv("REDIS_DB", "0"))
	ssl = _to_bool(os.getenv("REDIS_SSL"), default=False)
	socket_timeout = float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.0"))

	return Redis(
		host=host,
		port=port,
		password=password,
		db=db,
		ssl=ssl,
		socket_timeout=socket_timeout,
		socket_connect_timeout=socket_timeout,
		decode_responses=True,
	)


def redis_available() -> bool:
	"""Best-effort availability check for graceful fallback decisions."""

	try:
		return bool(get_redis_client().ping())
	except RedisError:
		return False
