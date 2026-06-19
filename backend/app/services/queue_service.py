"""Redis-backed background queue, job state, and worker registry utilities."""

from __future__ import annotations

import os
import socket
import time
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue

QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "edge-worker")
STATE_PREFIX = "visionsafe:jobs:cameras"
WORKER_PREFIX = "visionsafe:workers"
WORKER_TTL_SECONDS = int(os.getenv("WORKER_HEARTBEAT_TTL_SECONDS", "45"))


def _to_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _redis_db_for(purpose: str, default: int) -> int:
    specific = os.getenv(f"REDIS_{purpose.upper()}_DB")
    if specific is not None:
        return int(specific)
    return int(os.getenv("REDIS_DB", str(default)))


def _redis_client(purpose: str, db: int, decode_responses: bool, socket_timeout: float) -> Redis:
    prefix = f"REDIS_{purpose.upper()}"
    host = os.getenv(f"{prefix}_HOST", os.getenv("REDIS_HOST", "localhost"))
    port = int(os.getenv(f"{prefix}_PORT", os.getenv("REDIS_PORT", "6379")))
    password = os.getenv(f"{prefix}_PASSWORD", os.getenv("REDIS_PASSWORD", "")) or None
    ssl = _to_bool(os.getenv(f"{prefix}_SSL", os.getenv("REDIS_SSL")), default=False)
    connect_timeout = float(os.getenv("REDIS_CONNECT_TIMEOUT", "5"))
    return Redis(
        host=host,
        port=port,
        password=password,
        db=db,
        ssl=ssl,
        socket_timeout=socket_timeout,
        socket_connect_timeout=connect_timeout,
        decode_responses=decode_responses,
    )


@lru_cache(maxsize=1)
def get_queue_connection() -> Redis:
    """Return Redis connection for RQ queue payloads.

    RQ stores pickled bytes payloads, so decode_responses must stay disabled.
    """

    socket_timeout = float(os.getenv("REDIS_QUEUE_SOCKET_TIMEOUT", os.getenv("REDIS_SOCKET_TIMEOUT", "600")))
    return _redis_client(
        purpose="queue",
        db=_redis_db_for("queue", 0),
        decode_responses=False,
        socket_timeout=socket_timeout,
    )


@lru_cache(maxsize=1)
def get_state_connection() -> Redis:
    """Return Redis connection for lightweight shared orchestration state."""

    socket_timeout = float(os.getenv("REDIS_STATE_SOCKET_TIMEOUT", os.getenv("REDIS_SOCKET_TIMEOUT", "2")))
    return _redis_client(
        purpose="state",
        db=_redis_db_for("state", 1),
        decode_responses=True,
        socket_timeout=socket_timeout,
    )


@lru_cache(maxsize=16)
def get_job_queue(name: str = QUEUE_NAME) -> Queue:
    """Return an RQ queue instance."""

    return Queue(name=name, connection=get_queue_connection(), default_timeout=-1)


def worker_queue_name(worker_id: str) -> str:
    return f"{QUEUE_NAME}:{worker_id}"


def camera_state_key(camera_id: str) -> str:
    return f"{STATE_PREFIX}:{camera_id}:state"


def _empty_job_state(camera_id: str | None = None) -> dict[str, Any]:
    return {
        "running": False,
        "pid": None,
        "source_name": None,
        "camera_id": camera_id,
        "started_at": None,
        "last_error": None,
        "last_exit_code": None,
        "current_job_id": None,
        "queued": False,
        "stop_requested": False,
        "assigned_worker_id": None,
        "assigned_worker_gpu_id": None,
        "worker_queue": None,
        "updated_at": None,
    }


def _parse_job_state(payload: dict[str, str], camera_id: str | None = None) -> dict[str, Any]:
    if not payload:
        return _empty_job_state(camera_id)

    def as_float(key: str) -> float | None:
        value = payload.get(key)
        if value in {None, "", "None"}:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def as_int(key: str) -> int | None:
        value = payload.get(key)
        if value in {None, "", "None"}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return {
        "running": _to_bool(payload.get("running"), default=False),
        "pid": as_int("pid"),
        "source_name": payload.get("source_name") or None,
        "camera_id": payload.get("camera_id") or camera_id,
        "started_at": as_float("started_at"),
        "last_error": payload.get("last_error") or None,
        "last_exit_code": as_int("last_exit_code"),
        "current_job_id": payload.get("current_job_id") or None,
        "queued": _to_bool(payload.get("queued"), default=False),
        "stop_requested": _to_bool(payload.get("stop_requested"), default=False),
        "assigned_worker_id": payload.get("assigned_worker_id") or None,
        "assigned_worker_gpu_id": payload.get("assigned_worker_gpu_id") or None,
        "worker_queue": payload.get("worker_queue") or None,
        "updated_at": as_float("updated_at"),
    }


def get_job_state(camera_id: str) -> dict[str, Any]:
    """Read a camera's worker state from Redis."""

    try:
        payload = get_state_connection().hgetall(camera_state_key(camera_id))
    except RedisError:
        return _empty_job_state(camera_id)
    return _parse_job_state(payload, camera_id)


def list_job_states() -> list[dict[str, Any]]:
    """Return all known camera job states."""

    redis = get_state_connection()
    try:
        keys = list(redis.scan_iter(f"{STATE_PREFIX}:*:state"))
        if not keys:
            return []
        pipe = redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        rows = pipe.execute()
    except RedisError:
        return []

    states: list[dict[str, Any]] = []
    for key, row in zip(keys, rows):
        camera_id = str(key).removeprefix(f"{STATE_PREFIX}:").removesuffix(":state")
        states.append(_parse_job_state(row, camera_id))
    return states


def set_job_state(camera_id: str, **fields: Any) -> None:
    """Persist selected state fields for one camera."""

    if not fields:
        return
    serialized: dict[str, str] = {"camera_id": camera_id, "updated_at": str(time.time())}
    for key, value in fields.items():
        if value is None:
            serialized[key] = ""
        elif isinstance(value, bool):
            serialized[key] = "1" if value else "0"
        else:
            serialized[key] = str(value)
    try:
        get_state_connection().hset(camera_state_key(camera_id), mapping=serialized)
    except RedisError:
        pass


def clear_job_state(camera_id: str) -> None:
    """Reset volatile runtime state for one camera."""

    set_job_state(
        camera_id,
        running=False,
        queued=False,
        stop_requested=False,
        pid=None,
        current_job_id=None,
        started_at=None,
        source_name=None,
        last_exit_code=None,
        assigned_worker_id=None,
        assigned_worker_gpu_id=None,
        worker_queue=None,
    )


def register_worker(worker_id: str, gpu_id: str | None, capacity: int) -> None:
    """Register or refresh a worker heartbeat for scheduling decisions."""

    key = f"{WORKER_PREFIX}:{worker_id}"
    try:
        redis = get_state_connection()
        redis.hset(
            key,
            mapping={
                "worker_id": worker_id,
                "hostname": socket.gethostname(),
                "gpu_id": gpu_id or "",
                "capacity": str(max(1, capacity)),
                "queue": worker_queue_name(worker_id),
                "last_seen": str(time.time()),
            },
        )
        redis.expire(key, WORKER_TTL_SECONDS)
    except RedisError:
        pass


def list_workers() -> list[dict[str, Any]]:
    """Return currently alive workers from Redis heartbeats."""

    redis = get_state_connection()
    try:
        keys = list(redis.scan_iter(f"{WORKER_PREFIX}:*"))
        if not keys:
            return []
        pipe = redis.pipeline()
        for key in keys:
            pipe.hgetall(key)
        rows = pipe.execute()
    except RedisError:
        return []

    workers: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        try:
            capacity = int(row.get("capacity") or "1")
        except ValueError:
            capacity = 1
        workers.append(
            {
                "worker_id": row.get("worker_id"),
                "hostname": row.get("hostname"),
                "gpu_id": row.get("gpu_id") or None,
                "capacity": max(1, capacity),
                "queue": row.get("queue"),
                "last_seen": float(row.get("last_seen") or 0),
            }
        )
    return workers


def active_jobs_for_worker(worker_id: str) -> int:
    return sum(
        1
        for state in list_job_states()
        if state.get("assigned_worker_id") == worker_id
        and (state.get("running") or state.get("queued"))
    )


def select_worker() -> dict[str, Any] | None:
    """Pick the least-loaded alive worker with spare declared capacity."""

    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for worker in list_workers():
        worker_id = worker.get("worker_id")
        if not worker_id:
            continue
        load = active_jobs_for_worker(worker_id)
        if load < int(worker.get("capacity") or 1):
            candidates.append((load, float(worker.get("last_seen") or 0), worker))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]
