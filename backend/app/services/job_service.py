"""Redis-backed job control service using RQ."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from rq import Retry
from rq.job import Job

from .queue_service import (
    QUEUE_NAME,
    clear_job_state,
    get_job_queue,
    get_job_state,
    get_state_connection,
    list_job_states,
    list_workers,
    select_worker,
    set_job_state,
)
from .worker_tasks import run_edge_worker_job, _find_repo_root

STOP_FORCE_CLEAR_SECONDS = float(os.getenv("JOB_STOP_FORCE_CLEAR_SECONDS", "15"))


def _is_live_source(source: str) -> bool:
    """Return True if source is a live stream (RTSP, HTTP stream, webcam index)."""
    s = source.strip().lower()
    return s.startswith(("rtsp://", "http://", "https://", "rtmp://")) or s.isdigit()


class JobService:
    """Queue-backed worker job control while preserving existing API shape."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("visionsafe.jobs")
        self._lock = threading.RLock()
        self._repo_root = _find_repo_root()
        self._edge_dir = self._repo_root / "edge_ai"
        self._videos_dir = self._edge_dir / "vids_test"

    def status(self, camera_id: str | None = None) -> dict[str, Any]:
        if camera_id is not None:
            state = get_job_state(camera_id)
            return {
                "running": bool(state.get("running") or state.get("queued")),
                "pid": state.get("pid"),
                "source_name": state.get("source_name"),
                "camera_id": state.get("camera_id"),
                "started_at": state.get("started_at"),
                "last_error": state.get("last_error"),
                "last_exit_code": state.get("last_exit_code"),
                "current_job_id": state.get("current_job_id"),
                "queued": state.get("queued"),
                "assigned_worker_id": state.get("assigned_worker_id"),
                "worker_queue": state.get("worker_queue"),
            }

        states = list_job_states()
        active = [state for state in states if state.get("running") or state.get("queued")]
        if not active:
            return {
                "running": False,
                "pid": None,
                "source_name": None,
                "camera_id": None,
                "started_at": None,
                "last_error": None,
                "last_exit_code": None,
                "jobs": states,
            }

        state = active[0]
        return {
            "running": True,
            "pid": state.get("pid"),
            "source_name": state.get("source_name"),
            "camera_id": state.get("camera_id"),
            "started_at": state.get("started_at"),
            "last_error": state.get("last_error"),
            "last_exit_code": state.get("last_exit_code"),
            "jobs": states,
        }

    def _resolve_source(self, source_name: str | None, camera_id: str, db=None) -> str:
        """Resolve source to a concrete file path or live stream URL.

        Priority:
          1. source_name is an RTSP/HTTP URL → use directly
          2. source_name is a filename → resolve to vids_test/
          3. source_name is None AND db provided → look up camera.stream_url
          4. source_name is None AND no db → raise FileNotFoundError
        """
        if source_name and _is_live_source(source_name):
            self._logger.info(
                "RTSP/live source detected — using directly: %s for camera %s",
                source_name, camera_id,
            )
            return source_name

        if source_name:
            # File-based source
            source_path = (self._videos_dir / source_name).resolve()
            if not source_path.exists() or source_path.parent != self._videos_dir.resolve():
                raise FileNotFoundError(f"Unknown source file: {source_name}")
            return str(source_path)

        # Auto-resolve from DB camera.stream_url
        if db is not None:
            from ..models import Camera as CameraModel
            cam = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
            if cam and cam.stream_url:
                self._logger.info(
                    "Auto-resolved source from camera.stream_url: %s for camera %s",
                    cam.stream_url, camera_id,
                )
                return cam.stream_url
            raise FileNotFoundError(
                f"Camera '{camera_id}' has no stream_url configured and no source_name provided"
            )

        raise FileNotFoundError(
            "source_name is required when not providing a DB session for auto-resolve"
        )

    def start(
        self,
        source_name: str | None,
        camera_id: str,
        auth_token: str | None = None,
        db=None,
    ) -> dict[str, Any]:
        redis_lock = get_state_connection().lock(
            f"visionsafe:locks:cameras:{camera_id}:job",
            timeout=30,
            blocking_timeout=10,
        )
        with self._lock, redis_lock:
            self._cancel_pending_jobs_for_camera(camera_id)
            state = get_job_state(camera_id)
            if state.get("running") or state.get("queued"):
                raise RuntimeError(f"Worker is already running for camera '{camera_id}'")

            resolved_source = self._resolve_source(source_name, camera_id, db)

            selected_worker = select_worker()
            assigned_worker_id = selected_worker.get("worker_id") if selected_worker else None
            queue_name = selected_worker.get("queue") if selected_worker else QUEUE_NAME
            queue = get_job_queue(str(queue_name))
            retry_max = int(os.getenv("JOB_RETRY_MAX", "3"))
            retry_schedule = [10, 30, 60]

            job = queue.enqueue(
                run_edge_worker_job,
                kwargs={
                    "source_name": resolved_source,
                    "camera_id": camera_id,
                    "auth_token": auth_token,
                    "is_live_source": _is_live_source(resolved_source),
                    "assigned_worker_id": assigned_worker_id,
                },
                retry=Retry(max=retry_max, interval=retry_schedule),
                job_timeout=-1,
                failure_ttl=7 * 24 * 3600,
                result_ttl=24 * 3600,
                description=f"Edge worker for {camera_id} ({resolved_source})",
            )

            set_job_state(
                camera_id,
                running=False,
                queued=True,
                stop_requested=False,
                current_job_id=job.id,
                source_name=resolved_source,
                started_at=None,
                pid=None,
                last_error=None,
                last_exit_code=None,
                assigned_worker_id=assigned_worker_id,
                worker_queue=queue.name,
            )
            self._logger.info(
                "worker queued",
                extra={
                    "event": "worker_queued",
                    "source_name": resolved_source,
                    "camera_id": camera_id,
                    "job_id": job.id,
                },
            )
            return self.status(camera_id)

    def stop(self, camera_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if camera_id is None:
                active = [s for s in list_job_states() if s.get("running") or s.get("queued")]
                if not active:
                    return self.status()
                results = [self.stop(str(state.get("camera_id"))) for state in active if state.get("camera_id")]
                status = self.status()
                status["stopped"] = results
                return status

            redis_lock = get_state_connection().lock(
                f"visionsafe:locks:cameras:{camera_id}:job",
                timeout=30,
                blocking_timeout=10,
            )
            with redis_lock:
                return self._stop_locked(camera_id)

    def _stop_locked(self, camera_id: str) -> dict[str, Any]:
        state = get_job_state(camera_id)
        if not state.get("running") and not state.get("queued"):
            self._cancel_pending_jobs_for_camera(camera_id)
            return self.status(camera_id)

        job_id = state.get("current_job_id")

        if state.get("stop_requested") and state.get("running"):
            updated_at = float(state.get("updated_at") or 0)
            if updated_at and time.time() - updated_at >= STOP_FORCE_CLEAR_SECONDS:
                clear_job_state(camera_id)
                self._logger.warning(
                    "Force cleared running job state after stop grace period",
                    extra={"job_id": job_id, "camera_id": camera_id},
                )
                return self.status(camera_id)
            self._logger.info(
                "worker stop already requested",
                extra={"event": "worker_stop_pending", "job_id": job_id, "camera_id": camera_id},
            )
            return self.status(camera_id)

        if state.get("stop_requested"):
            clear_job_state(camera_id)
            self._logger.warning(
                "Force cleared job state because stop was already requested",
                extra={"job_id": job_id, "camera_id": camera_id},
            )
            return self.status(camera_id)

        set_job_state(camera_id, stop_requested=True)
        self._cancel_pending_jobs_for_camera(camera_id, exclude_job_id=str(job_id) if job_id else None)

        cancelled_queued_job = False
        if job_id:
            try:
                queue_name = state.get("worker_queue") or QUEUE_NAME
                job = Job.fetch(job_id, connection=get_job_queue(str(queue_name)).connection)
                if job.get_status(refresh=True) in {"queued", "scheduled", "deferred"}:
                    job.cancel()
                    cancelled_queued_job = True
                    self._logger.info(
                        "queued worker cancelled",
                        extra={"event": "worker_cancelled", "job_id": job_id, "camera_id": camera_id},
                    )
            except Exception:
                self._logger.exception("failed to cancel queued job")

        if state.get("queued") and not state.get("running") and (cancelled_queued_job or not job_id):
            clear_job_state(camera_id)
            self._logger.info(
                "queued worker state cleared",
                extra={"event": "worker_queue_cleared", "job_id": job_id, "camera_id": camera_id},
            )
            return self.status(camera_id)

        self._logger.info(
            "worker stop requested",
            extra={"event": "worker_stop_requested", "job_id": job_id, "camera_id": camera_id},
        )
        return self.status(camera_id)

    def _cancel_pending_jobs_for_camera(self, camera_id: str, exclude_job_id: str | None = None) -> int:
        queue_names = {QUEUE_NAME}
        for worker in list_workers():
            queue_name = worker.get("queue")
            if queue_name:
                queue_names.add(str(queue_name))

        cancelled = 0
        for queue_name in queue_names:
            queue = get_job_queue(queue_name)
            try:
                job_ids = queue.get_job_ids()
            except Exception:
                self._logger.exception("failed to list queued jobs")
                continue

            for queued_job_id in job_ids:
                if exclude_job_id and queued_job_id == exclude_job_id:
                    continue
                try:
                    job = Job.fetch(queued_job_id, connection=queue.connection)
                    if job.kwargs.get("camera_id") != camera_id:
                        continue
                    status = job.get_status(refresh=True)
                    if status in {"queued", "scheduled", "deferred"}:
                        job.cancel()
                        job.delete()
                        cancelled += 1
                except Exception:
                    self._logger.exception("failed to cancel stale queued job")

        if cancelled:
            self._logger.info(
                "cancelled stale queued jobs",
                extra={"event": "stale_jobs_cancelled", "camera_id": camera_id, "count": cancelled},
            )
        return cancelled


job_service = JobService()
