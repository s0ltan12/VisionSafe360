"""Redis-backed job control service using RQ."""

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any

from rq import Retry
from rq.job import Job

from .queue_service import clear_job_state, get_job_queue, get_job_state, set_job_state
from .worker_tasks import run_edge_worker_job


class JobService:
    """Queue-backed worker job control while preserving existing API shape."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("visionsafe.jobs")
        self._lock = threading.Lock()
        self._repo_root = Path(__file__).resolve().parents[3]
        self._edge_dir = self._repo_root / "edge_ai"
        self._videos_dir = self._edge_dir / "vids_test"

    def status(self) -> dict[str, Any]:
        state = get_job_state()
        return {
            "running": bool(state.get("running") or state.get("queued")),
            "pid": state.get("pid"),
            "source_name": state.get("source_name"),
            "camera_id": state.get("camera_id"),
            "started_at": state.get("started_at"),
            "last_error": state.get("last_error"),
            "last_exit_code": state.get("last_exit_code"),
        }

    def start(self, source_name: str, camera_id: str, auth_token: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = get_job_state()
            if state.get("running") or state.get("queued"):
                raise RuntimeError("Worker is already running")

            source_path = (self._videos_dir / source_name).resolve()
            if not source_path.exists() or source_path.parent != self._videos_dir.resolve():
                raise FileNotFoundError(f"Unknown source file: {source_name}")

            queue = get_job_queue()
            retry_max = int(os.getenv("JOB_RETRY_MAX", "3"))
            retry_schedule = [10, 30, 60]

            job = queue.enqueue(
                run_edge_worker_job,
                kwargs={
                    "source_name": source_name,
                    "camera_id": camera_id,
                    "auth_token": auth_token,
                },
                retry=Retry(max=retry_max, interval=retry_schedule),
                job_timeout=-1,
                failure_ttl=7 * 24 * 3600,
                result_ttl=24 * 3600,
                description=f"Edge worker for {camera_id} ({source_name})",
            )

            set_job_state(
                running=False,
                queued=True,
                stop_requested=False,
                current_job_id=job.id,
                source_name=source_name,
                camera_id=camera_id,
                started_at=None,
                pid=None,
                last_error=None,
                last_exit_code=None,
            )
            self._logger.info(
                "worker queued",
                extra={
                    "event": "worker_queued",
                    "source_name": source_name,
                    "camera_id": camera_id,
                    "job_id": job.id,
                },
            )
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            state = get_job_state()
            if not state.get("running") and not state.get("queued"):
                return self.status()

            job_id = state.get("current_job_id")
            pid = state.get("pid")

            set_job_state(stop_requested=True)

            if job_id:
                try:
                    job = Job.fetch(job_id, connection=get_job_queue().connection)
                    if job.get_status(refresh=True) in {"queued", "scheduled", "deferred"}:
                        job.cancel()
                        self._logger.info(
                            "queued worker cancelled",
                            extra={"event": "worker_cancelled", "job_id": job_id},
                        )
                except Exception:
                    self._logger.exception("failed to cancel queued job")

            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except Exception:
                    self._logger.exception("failed to terminate worker process", extra={"pid": pid})

            clear_job_state()
            self._logger.info("worker stop requested", extra={"event": "worker_stop_requested", "job_id": job_id})
            return self.status()


job_service = JobService()
