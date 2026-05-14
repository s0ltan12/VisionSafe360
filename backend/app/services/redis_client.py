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


def _db_for_purpose(purpose: str) -> int:
	specific = os.getenv(f"REDIS_{purpose.upper()}_DB")
	if specific is not None:
		return int(specific)
	return int(os.getenv("REDIS_DB", "1"))


@lru_cache(maxsize=8)
def get_redis_client(purpose: str = "state") -> Redis:
	"""Create a cached Redis client instance.

	Environment variables:
	- REDIS_HOST (default: localhost)
	- REDIS_PORT (default: 6379)
	- REDIS_PASSWORD (optional)
	- REDIS_DB (default: 0)
	- REDIS_SSL (default: false)
	- REDIS_SOCKET_TIMEOUT (default: 1.0)
	"""

	prefix = f"REDIS_{purpose.upper()}"
	host = os.getenv(f"{prefix}_HOST", os.getenv("REDIS_HOST", "localhost"))
	port = int(os.getenv(f"{prefix}_PORT", os.getenv("REDIS_PORT", "6379")))
	password = os.getenv(f"{prefix}_PASSWORD", os.getenv("REDIS_PASSWORD", "")) or None
	db = _db_for_purpose(purpose)
	ssl = _to_bool(os.getenv(f"{prefix}_SSL", os.getenv("REDIS_SSL")), default=False)
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
