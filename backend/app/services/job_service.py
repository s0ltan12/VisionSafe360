"""In-memory worker job control for dashboard MVP."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


class JobService:
	"""Manage one edge worker process for MVP control APIs."""

	def __init__(self) -> None:
		self._logger = logging.getLogger("visionsafe.jobs")
		self._lock = threading.Lock()
		self._process: subprocess.Popen | None = None
		self._process_log_handle = None
		self._running = False
		self._started_at: float | None = None
		self._source_name: str | None = None
		self._camera_id: str | None = None
		self._last_error: str | None = None
		self._last_exit_code: int | None = None

		self._repo_root = Path(__file__).resolve().parents[3]
		self._edge_dir = self._repo_root / "edge_ai"
		self._videos_dir = self._edge_dir / "vids_test"

	def _refresh_state(self) -> None:
		if not self._process:
			return
		exit_code = self._process.poll()
		if exit_code is None:
			return
		self._running = False
		self._last_exit_code = exit_code
		self._process = None
		if self._process_log_handle:
			self._process_log_handle.close()
			self._process_log_handle = None
		self._logger.info(
			"worker exited",
			extra={"event": "worker_exit", "status_code": exit_code, "source_name": self._source_name, "camera_id": self._camera_id},
		)

	def status(self) -> dict[str, Any]:
		with self._lock:
			self._refresh_state()
			return {
				"running": self._running,
				"pid": self._process.pid if self._process else None,
				"source_name": self._source_name,
				"camera_id": self._camera_id,
				"started_at": self._started_at,
				"last_error": self._last_error,
				"last_exit_code": self._last_exit_code,
			}

	def start(self, source_name: str, camera_id: str, auth_token: str | None = None) -> dict[str, Any]:
		with self._lock:
			self._refresh_state()
			if self._running:
				raise RuntimeError("Worker is already running")

			source_path = (self._videos_dir / source_name).resolve()
			if not source_path.exists() or source_path.parent != self._videos_dir.resolve():
				raise FileNotFoundError(f"Unknown source file: {source_name}")

			env = os.environ.copy()
			env["VISIONSAFE_BACKEND_EVENTS_ENABLED"] = "true"
			env["VISIONSAFE_BACKEND_URL"] = "http://127.0.0.1:8000"
			env["VISIONSAFE_BACKEND_INCIDENTS_PATH"] = "/api/incidents"
			env["VISIONSAFE_BACKEND_SOURCE_ID"] = camera_id
			env["VISIONSAFE_LOOP_FILE_SOURCE"] = "false"
			if auth_token:
				env["VISIONSAFE_BACKEND_AUTH_TOKEN"] = auth_token

			logs_dir = self._repo_root / "backend" / "logs"
			logs_dir.mkdir(parents=True, exist_ok=True)
			worker_log_path = logs_dir / "edge_worker.log"
			self._process_log_handle = open(worker_log_path, "a", encoding="utf-8")

			cmd = [
				sys.executable,
				"-m",
				"examples.live_monitoring_worker",
				"--source",
				str(source_path),
				"--camera-id",
				camera_id,
			]

			self._process = subprocess.Popen(
				cmd,
				cwd=str(self._edge_dir),
				env=env,
				stdout=self._process_log_handle,
				stderr=subprocess.STDOUT,
			)

			self._running = True
			self._started_at = time.time()
			self._source_name = source_name
			self._camera_id = camera_id
			self._last_error = None
			self._last_exit_code = None
			self._logger.info(
				"worker started",
				extra={"event": "worker_start", "source_name": source_name, "camera_id": camera_id, "pid": self._process.pid},
			)
			return self.status()

	def stop(self) -> dict[str, Any]:
		with self._lock:
			self._refresh_state()
			if not self._running or not self._process:
				return self.status()

			proc = self._process
			try:
				proc.terminate()
				proc.wait(timeout=6)
			except subprocess.TimeoutExpired:
				proc.kill()
				proc.wait(timeout=3)
			except Exception as exc:
				self._last_error = str(exc)

			self._last_exit_code = proc.poll()
			self._process = None
			if self._process_log_handle:
				self._process_log_handle.close()
				self._process_log_handle = None
			self._running = False
			self._started_at = None
			self._source_name = None
			self._camera_id = None
			self._logger.info("worker stopped", extra={"event": "worker_stop", "status_code": self._last_exit_code})
			return self.status()


job_service = JobService()