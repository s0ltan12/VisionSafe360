"""System health aggregation for the dashboard HUD."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Camera
from .monitoring_service import monitoring_service
from .queue_service import active_jobs_for_worker, list_job_states, list_workers
from .redis_client import redis_available


class SystemHealthService:
    @staticmethod
    def get_summary(db: Session) -> dict[str, Any]:
        now = time.time()
        workers = list_workers()
        job_states = list_job_states()
        runtime = monitoring_service.snapshot()

        db_ok = True
        db_latency_ms: float | None = None
        try:
            start = time.perf_counter()
            db.execute(text("SELECT 1"))
            db_latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        except Exception:
            db_ok = False

        redis_ok = redis_available()
        disk = shutil.disk_usage(Path.cwd())
        load_average = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        cpu_count = os.cpu_count() or 1
        cpu_load_percent = round(min((load_average[0] / cpu_count) * 100.0, 100.0), 1)

        cameras = db.query(Camera).all()
        online_cameras = [camera for camera in cameras if str(camera.status).lower() == "online"]
        global_fps = round(sum(float(camera.fps or 0) for camera in online_cameras), 1)

        worker_nodes = []
        for worker in workers:
            worker_id = str(worker.get("worker_id") or "unknown")
            last_seen = float(worker.get("last_seen") or 0.0)
            active_jobs = active_jobs_for_worker(worker_id)
            capacity = int(worker.get("capacity") or 1)
            age_seconds = max(0.0, now - last_seen) if last_seen else None
            load_percent = round(min((active_jobs / max(capacity, 1)) * 100.0, 100.0), 1)
            worker_nodes.append({
                "id": worker_id,
                "name": f"Edge Worker {worker_id}",
                "status": "online" if age_seconds is not None and age_seconds <= 60 else "stale",
                "hostname": worker.get("hostname"),
                "gpu_id": worker.get("gpu_id"),
                "queue": worker.get("queue"),
                "capacity": capacity,
                "active_jobs": active_jobs,
                "load_percent": load_percent,
                "latency_ms": round(age_seconds * 1000.0, 0) if age_seconds is not None else None,
                "last_seen_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            })

        camera_nodes = []
        state_by_camera = {state.get("camera_id"): state for state in job_states if state.get("camera_id")}
        for camera in cameras:
            state = state_by_camera.get(camera.id, {})
            running = bool(state.get("running") or state.get("queued"))
            status = "online" if running or str(camera.status).lower() == "online" else "offline"
            camera_nodes.append({
                "id": camera.id,
                "name": camera.name,
                "status": status,
                "zone": camera.zone,
                "fps": round(float(camera.fps or 0), 1),
                "health": round(float(camera.health or 0), 1),
                "source_name": state.get("source_name"),
                "running": running,
                "queued": bool(state.get("queued")),
                "worker_id": state.get("assigned_worker_id"),
                "worker_gpu_id": state.get("assigned_worker_gpu_id"),
                "started_at": state.get("started_at"),
                "last_error": state.get("last_error"),
            })

        return {
            "generated_at": now,
            "summary": {
                "backend": "online",
                "database": "online" if db_ok else "offline",
                "redis": "online" if redis_ok else "offline",
                "active_workers": len([node for node in worker_nodes if node["status"] == "online"]),
                "active_jobs": len([state for state in job_states if state.get("running") or state.get("queued")]),
                "online_cameras": len(online_cameras),
                "total_cameras": len(cameras),
                "global_fps": global_fps,
                "cpu_load_percent": cpu_load_percent,
                "load_average_1m": round(float(load_average[0]), 2),
                "disk_used_bytes": disk.used,
                "disk_total_bytes": disk.total,
                "disk_used_percent": round((disk.used / disk.total) * 100.0, 1) if disk.total else 0,
                "db_latency_ms": db_latency_ms,
                "ws_active_connections": runtime.get("ws_active_connections", 0),
                "incidents_last_60s": runtime.get("incidents_last_60s", 0),
                "rate_limited_last_60s": runtime.get("rate_limited_last_60s", 0),
            },
            "workers": worker_nodes,
            "cameras": camera_nodes,
        }


system_health_service = SystemHealthService()
