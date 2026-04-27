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

logger = logging.getLogger("visionsafe.jobs")


def run_edge_worker_job(source_name: str, camera_id: str, auth_token: str | None = None) -> dict[str, object]:
    """Execute heavy edge processing in an async queue worker."""
    job = get_current_job()
    job_id = job.id if job else None

    repo_root = Path(__file__).resolve().parents[3]
    edge_dir = repo_root / "edge_ai"
    videos_dir = edge_dir / "vids_test"

    source_path = (videos_dir / source_name).resolve()
    if not source_path.exists() or source_path.parent != videos_dir.resolve():
        raise FileNotFoundError(f"Unknown source file: {source_name}")

    env = os.environ.copy()
    env["VISIONSAFE_BACKEND_EVENTS_ENABLED"] = "true"
    env["VISIONSAFE_BACKEND_URL"] = env.get("VISIONSAFE_BACKEND_URL", "http://127.0.0.1:8000")
    env["VISIONSAFE_BACKEND_INCIDENTS_PATH"] = env.get("VISIONSAFE_BACKEND_INCIDENTS_PATH", "/api/incidents")
    env["VISIONSAFE_BACKEND_SOURCE_ID"] = camera_id
    env["VISIONSAFE_LOOP_FILE_SOURCE"] = "false"
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
        str(source_path),
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
                running=True,
                queued=False,
                stop_requested=False,
                source_name=source_name,
                camera_id=camera_id,
                started_at=time.time(),
                current_job_id=job_id,
                pid=process.pid,
                last_error=None,
                last_exit_code=None,
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

                state = get_job_state()
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
                running=False,
                queued=False,
                stop_requested=False,
                pid=None,
                current_job_id=None,
                started_at=None,
                source_name=None,
                camera_id=None,
                last_exit_code=exit_code,
            )

            if exit_code not in {0, None} and not stop_requested:
                msg = f"Edge worker failed with exit code {exit_code}"
                set_job_state(last_error=msg)
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
                "last_error": get_job_state().get("last_error"),
                "last_exit_code": exit_code,
            }

        except Exception as exc:
            set_job_state(
                running=False,
                queued=False,
                pid=None,
                started_at=None,
                source_name=None,
                camera_id=None,
                current_job_id=None,
                last_error=str(exc),
            )
            logger.exception("queued worker crashed")
            raise
