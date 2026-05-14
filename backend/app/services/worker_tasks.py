"""Background job tasks for edge worker orchestration (RQ)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from rq import get_current_job

from .queue_service import get_job_state, set_job_state


def _find_repo_root() -> Path:
    """Locate the project root by searching upward for 'edge_ai' directory.

    Works both locally (deep file path) and in Docker containers (WORKDIR=/app).
    """
    anchor = Path(__file__).resolve()
    for parent in anchor.parents:
        if (parent / "edge_ai").is_dir():
            return parent
    # Docker fallback: WORKDIR is /app and edge_ai is volume-mounted at /app/edge_ai
    docker_root = Path("/app")
    if (docker_root / "edge_ai").is_dir():
        return docker_root
    raise FileNotFoundError(
        "Cannot locate project root: 'edge_ai' directory not found in any parent"
    )

logger = logging.getLogger("visionsafe.jobs")


def _is_live_source(source: str) -> bool:
    """Return True if source is a live stream (RTSP, HTTP stream, webcam index)."""
    s = source.strip().lower()
    return s.startswith(("rtsp://", "http://", "https://", "rtmp://")) or s.isdigit()


def run_edge_worker_job(
    source_name: str,
    camera_id: str,
    auth_token: str | None = None,
    is_live_source: bool = False,
    assigned_worker_id: str | None = None,
) -> dict[str, object]:
    """Execute heavy edge processing in an async queue worker.

    source_name is now a fully-resolved value — either an absolute file path
    or a live stream URL (rtsp://, http://, webcam index). The job_service
    resolves it before enqueueing.
    """
    job = get_current_job()
    job_id = job.id if job else None

    repo_root = _find_repo_root()
    edge_dir = repo_root / "edge_ai"

    # Validate file-based sources; pass live sources through directly
    if is_live_source or _is_live_source(source_name):
        source_arg = source_name
        logger.info(
            "Starting RTSP/live stream: %s for camera %s",
            source_name, camera_id,
        )
    else:
        # source_name is an absolute path resolved by job_service
        source_path = Path(source_name)
        if not source_path.exists():
            # Fallback: try resolving relative to vids_test
            videos_dir = edge_dir / "vids_test"
            alt = (videos_dir / Path(source_name).name).resolve()
            if alt.exists():
                source_path = alt
            else:
                raise FileNotFoundError(f"Source file not found: {source_name}")
        source_arg = str(source_path)
        logger.info(
            "Starting file-based stream: %s for camera %s",
            source_arg, camera_id,
        )

    env = os.environ.copy()
    env["VISIONSAFE_BACKEND_EVENTS_ENABLED"] = "true"
    # VISIONSAFE_BACKEND_URL is set to http://backend:8000 in docker-compose.yml.
    # Fallback to localhost only for local (non-Docker) execution.
    if "VISIONSAFE_BACKEND_URL" not in env:
        env["VISIONSAFE_BACKEND_URL"] = "http://127.0.0.1:8000"
    # Use the no-auth ingest endpoint instead of /api/incidents (which requires RBAC).
    env["VISIONSAFE_BACKEND_INCIDENTS_PATH"] = "/api/ingest/incident"
    env["VISIONSAFE_BACKEND_SOURCE_ID"] = camera_id
    env["VISIONSAFE_LOOP_FILE_SOURCE"] = "true"
    # Increase flush aggressiveness so the offline queue drains quickly.
    env["VISIONSAFE_OFFLINE_FLUSH_INTERVAL_SEC"] = "2"
    env["VISIONSAFE_OFFLINE_FLUSH_MAX_PER_CYCLE"] = "10"
    env["VISIONSAFE_OFFLINE_SHUTDOWN_FLUSH_LIMIT"] = "50"
    # auth_token is passed for audit/logging but not required by the ingest endpoint.
    if auth_token:
        env["VISIONSAFE_BACKEND_AUTH_TOKEN"] = auth_token

    logs_dir = repo_root / "backend" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    worker_log_path = logs_dir / "edge_worker.log"

    cmd = [
        sys.executable,
        "-m",
        "src.main",
        "--source",
        source_arg,
        "--cam-id",
        camera_id,
        "--headless",
    ]

    process: subprocess.Popen | None = None
    exit_code: int | None = None
    stop_requested = False

    with open(worker_log_path, "a", encoding="utf-8") as log_handle:
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(edge_dir),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            set_job_state(
                camera_id,
                running=True,
                queued=False,
                stop_requested=False,
                source_name=source_name,
                started_at=time.time(),
                current_job_id=job_id,
                pid=process.pid,
                last_error=None,
                last_exit_code=None,
                assigned_worker_id=assigned_worker_id,
            )
            logger.info(
                "queued worker started",
                extra={
                    "event": "worker_start",
                    "source_name": source_name,
                    "camera_id": camera_id,
                    "pid": process.pid,
                    "job_id": job_id,
                },
            )

            while True:
                exit_code = process.poll()
                if exit_code is not None:
                    break

                state = get_job_state(camera_id)
                if state.get("stop_requested"):
                    stop_requested = True
                    process.terminate()
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                    exit_code = process.poll()
                    break
                time.sleep(1.0)

            set_job_state(
                camera_id,
                running=False,
                queued=False,
                stop_requested=False,
                pid=None,
                current_job_id=None,
                started_at=None,
                source_name=None,
                last_exit_code=exit_code,
            )

            if exit_code not in {0, None} and not stop_requested:
                msg = f"Edge worker failed with exit code {exit_code}"
                set_job_state(camera_id, last_error=msg)
                logger.error(
                    "worker failed",
                    extra={"event": "worker_fail", "status_code": exit_code, "job_id": job_id},
                )
                raise RuntimeError(msg)

            logger.info(
                "worker finished",
                extra={
                    "event": "worker_exit",
                    "status_code": exit_code,
                    "job_id": job_id,
                    "stop_requested": stop_requested,
                },
            )
            return {
                "running": False,
                "pid": None,
                "source_name": None,
                "camera_id": None,
                "started_at": None,
                "last_error": get_job_state(camera_id).get("last_error"),
                "last_exit_code": exit_code,
            }

        except Exception as exc:
            set_job_state(
                camera_id,
                running=False,
                queued=False,
                pid=None,
                started_at=None,
                source_name=None,
                current_job_id=None,
                last_error=str(exc),
            )
            logger.exception("queued worker crashed")
            raise
