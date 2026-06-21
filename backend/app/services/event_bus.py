"""Redis-backed realtime event bus for horizontally scaled websocket delivery."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any
import logging

from redis import Redis
from redis.exceptions import RedisError

INCIDENT_CHANNEL = "visionsafe:events:incidents"
NOTIFICATION_CHANNEL = "visionsafe:events:notifications"
ERGONOMICS_CHANNEL = "visionsafe:events:ergonomics"
ANALYTICS_CHANNEL = "visionsafe:events:analytics"
INCIDENT_STREAM = "visionsafe:streams:incidents"
NOTIFICATION_STREAM = "visionsafe:streams:notifications"
ERGONOMICS_STREAM = "visionsafe:streams:ergonomics"
ANALYTICS_STREAM = "visionsafe:streams:analytics"
MAX_STREAM_LEN = int(os.getenv("VISIONSAFE_EVENT_STREAM_MAXLEN", "10000"))
logger = logging.getLogger("visionsafe.event_bus")


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _events_db() -> int:
    if os.getenv("REDIS_EVENTS_DB") is not None:
        return int(os.getenv("REDIS_EVENTS_DB", "2"))
    return int(os.getenv("REDIS_DB", "2"))


@lru_cache(maxsize=1)
def get_event_redis() -> Redis:
    prefix = "REDIS_EVENTS"
    return Redis(
        host=os.getenv(f"{prefix}_HOST", os.getenv("REDIS_HOST", "localhost")),
        port=int(os.getenv(f"{prefix}_PORT", os.getenv("REDIS_PORT", "6379"))),
        password=os.getenv(f"{prefix}_PASSWORD", os.getenv("REDIS_PASSWORD", "")) or None,
        db=_events_db(),
        ssl=_to_bool(os.getenv(f"{prefix}_SSL", os.getenv("REDIS_SSL")), default=False),
        socket_timeout=float(os.getenv("REDIS_EVENTS_SOCKET_TIMEOUT", "5")),
        socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "5")),
        decode_responses=True,
    )


def publish_event(channel: str, stream: str, payload: dict[str, Any]) -> None:
    """Persist event to a Redis Stream and fan out via Pub/Sub."""

    message = json.dumps(payload, default=str, separators=(",", ":"))
    redis = get_event_redis()
    try:
        if channel == INCIDENT_CHANNEL and isinstance(payload.get("incident"), dict):
            incident = payload["incident"]
            logger.debug(
                "publish incident event incident_id=%s camera_id=%s camera_name=%s worker_id=%s worker_gpu_id=%s stream=%s channel=%s",
                incident.get("id"),
                incident.get("camera_id"),
                incident.get("camera_name"),
                incident.get("worker_id"),
                incident.get("worker_gpu_id"),
                stream,
                channel,
            )
        redis.xadd(stream, {"payload": message}, maxlen=MAX_STREAM_LEN, approximate=True)
        redis.publish(channel, message)
    except RedisError:
        raise


def publish_incident(payload: dict[str, Any]) -> None:
    publish_event(INCIDENT_CHANNEL, INCIDENT_STREAM, payload)


def publish_notification(payload: dict[str, Any]) -> None:
    publish_event(NOTIFICATION_CHANNEL, NOTIFICATION_STREAM, payload)


def publish_ergonomics(payload: dict[str, Any]) -> None:
    publish_event(ERGONOMICS_CHANNEL, ERGONOMICS_STREAM, payload)


def publish_analytics(payload: dict[str, Any]) -> None:
    publish_event(ANALYTICS_CHANNEL, ANALYTICS_STREAM, payload)
