"""Redis-backed background queue utilities (RQ)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from redis import Redis
from rq import Queue

QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "edge-worker")
STATE_KEY = "visionsafe:jobs:edge_worker:state"


def _to_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_queue_connection() -> Redis:
    """Return Redis connection for queue operations."""
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    db = int(os.getenv("REDIS_DB", "0"))
    ssl = _to_bool(os.getenv("REDIS_SSL"), default=False)
    # socket_timeout must be high because RQ uses BLPOP which blocks for
    # extended periods waiting for new jobs.  A low value (e.g. 1 s) causes
    # the worker to die with "Redis connection timeout".
    socket_timeout = float(os.getenv("REDIS_SOCKET_TIMEOUT", "300"))
    connect_timeout = float(os.getenv("REDIS_CONNECT_TIMEOUT", "5"))

    # RQ stores pickled bytes payloads, so decode_responses must be disabled.
    return Redis(
        host=host,
        port=port,
        password=password,
        db=db,
        ssl=ssl,
        socket_timeout=socket_timeout,
        socket_connect_timeout=connect_timeout,
        decode_responses=False,
    )


@lru_cache(maxsize=1)
def get_job_queue() -> Queue:
    """Return shared RQ queue instance."""
    return Queue(name=QUEUE_NAME, connection=get_queue_connection(), default_timeout=-1)


def _empty_job_state() -> dict[str, Any]:
    return {
        "running": False,
        "pid": None,
        "source_name": None,
        "camera_id": None,
        "started_at": None,
        "last_error": None,
        "last_exit_code": None,
        "current_job_id": None,
        "queued": False,
        "stop_requested": False,
    }


def get_job_state() -> dict[str, Any]:
    """Read current edge worker state from Redis and normalize fields.
    
    Returns empty state dict when Redis is unavailable (graceful fallback).
    """
    from redis.exceptions import RedisError
    try:
        raw_payload = get_queue_connection().hgetall(STATE_KEY)
    except RedisError:
        return _empty_job_state()

    payload: dict[str, str] = {
        (k.decode("utf-8") if isinstance(k, bytes) else str(k)): (
            v.decode("utf-8") if isinstance(v, bytes) else str(v)
        )
        for k, v in raw_payload.items()
    }
    if not payload:
        return {
            "running": False,
            "pid": None,
            "source_name": None,
            "camera_id": None,
            "started_at": None,
            "last_error": None,
            "last_exit_code": None,
            "current_job_id": None,
            "queued": False,
            "stop_requested": False,
        }

    started_at = payload.get("started_at")
    if started_at in {None, "", "None"}:
        parsed_started_at = None
    else:
        try:
            parsed_started_at = float(started_at)
        except ValueError:
            parsed_started_at = None

    pid = payload.get("pid")
    if pid in {None, "", "None"}:
        parsed_pid = None
    else:
        try:
            parsed_pid = int(pid)
        except ValueError:
            parsed_pid = None

    last_exit_code = payload.get("last_exit_code")
    if last_exit_code in {None, "", "None"}:
        parsed_exit_code = None
    else:
        try:
            parsed_exit_code = int(last_exit_code)
        except ValueError:
            parsed_exit_code = None

    return {
        "running": _to_bool(payload.get("running"), default=False),
        "pid": parsed_pid,
        "source_name": payload.get("source_name") or None,
        "camera_id": payload.get("camera_id") or None,
        "started_at": parsed_started_at,
        "last_error": payload.get("last_error") or None,
        "last_exit_code": parsed_exit_code,
        "current_job_id": payload.get("current_job_id") or None,
        "queued": _to_bool(payload.get("queued"), default=False),
        "stop_requested": _to_bool(payload.get("stop_requested"), default=False),
    }


def set_job_state(**fields: Any) -> None:
    """Persist selected state fields to Redis (no-op if Redis unavailable)."""
    from redis.exceptions import RedisError
    if not fields:
        return
    serialized: dict[str, str] = {}
    for key, value in fields.items():
        if value is None:
            serialized[key] = ""
        elif isinstance(value, bool):
            serialized[key] = "1" if value else "0"
        else:
            serialized[key] = str(value)
    try:
        get_queue_connection().hset(STATE_KEY, mapping=serialized)
    except RedisError:
        pass


def clear_job_state() -> None:
    """Reset volatile runtime state while keeping last error/exit info untouched."""
    set_job_state(
        running=False,
        queued=False,
        stop_requested=False,
        pid=None,
        current_job_id=None,
        started_at=None,
        source_name=None,
        camera_id=None,
    )
