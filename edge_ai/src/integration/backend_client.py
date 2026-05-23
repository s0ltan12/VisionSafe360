"""Backend integration client with offline queue support.

The client is intentionally defensive: request failures never propagate to the
caller and failed payloads are persisted in SQLite for later resend.
"""
from __future__ import annotations

import json
import logging
from enum import Enum
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from ..config import settings
from ..models.hazard_event import HazardEvent

logger = logging.getLogger(__name__)


class DeliveryResult(Enum):
    """Backend delivery outcome."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class BackendClientConfig:
    """Runtime configuration for BackendClient."""

    enabled: bool = settings.BACKEND_EVENTS_ENABLED
    base_url: str = settings.BACKEND_URL
    incidents_path: str = settings.BACKEND_INCIDENTS_PATH
    auth_token: str = settings.BACKEND_AUTH_TOKEN
    source_id: str = settings.BACKEND_SOURCE_ID
    camera_name: str = settings.BACKEND_CAMERA_NAME
    worker_id: str = settings.BACKEND_WORKER_ID
    worker_gpu_id: str = settings.BACKEND_WORKER_GPU_ID
    timeout_sec: float = settings.BACKEND_TIMEOUT
    max_retry: int = settings.BACKEND_MAX_RETRY
    retry_backoff: tuple[float, ...] = tuple(settings.BACKEND_RETRY_BACKOFF)
    offline_db: Path = settings.OFFLINE_QUEUE_DB
    offline_queue_max_rows: int = settings.OFFLINE_QUEUE_MAX_ROWS


class BackendClient:
    """Submit hazard incidents to backend and buffer failures locally.

    Network and backend outages are expected; the client stores failed payloads
    in SQLite and exposes ``flush_offline_queue`` for periodic resend.
    """

    def __init__(
        self,
        config: Optional[BackendClientConfig] = None,
        *,
        session: Optional[requests.Session] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or BackendClientConfig()
        self._session = session or requests.Session()
        self._sleep = sleep_fn
        self._incidents_url = self._join_url(self.config.base_url, self.config.incidents_path)

        self._db_ready = False
        self._init_db()

    @staticmethod
    def _join_url(base: str, path: str) -> str:
        base_clean = base.rstrip("/")
        path_clean = path if path.startswith("/") else f"/{path}"
        return f"{base_clean}{path_clean}"

    def _init_db(self) -> None:
        try:
            self.config.offline_db.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.config.offline_db) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS offline_incidents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        payload_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_offline_created_at "
                    "ON offline_incidents(created_at)"
                )
            self._db_ready = True
        except Exception as exc:
            self._db_ready = False
            logger.exception("BackendClient DB init failed: %s", exc)

    def submit_incident(self, event: HazardEvent) -> DeliveryResult:
        """Submit one hazard event to backend with retry + offline fallback.

        Args:
            event: HazardEvent to send.

        Returns:
            Backend delivery outcome.

        Failure Behavior:
            Any exception is handled internally. Failed sends are queued when
            local DB is available.
        """

        payload = self._event_to_payload(event)
        if not self.config.enabled:
            logger.info(
                "backend delivery skipped (disabled) event_type=%s severity=%s camera_id=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
            )
            return DeliveryResult.SKIPPED

        ok, error = self._post_with_retry(payload)
        if ok:
            logger.info("incident delivered", extra={"event": "incident_delivered", "source_id": self.config.source_id or "unknown"})
            return DeliveryResult.OK

        self._enqueue_offline(payload, error or "unknown_error")
        logger.warning(
            "incident delivery failed, queued offline",
            extra={"event": "incident_delivery_failed", "source_id": self.config.source_id or "unknown", "error": error or "unknown_error"},
        )
        return DeliveryResult.FAILED

    def submit_incident_fast(self, event: HazardEvent) -> DeliveryResult:
        """Submit one hazard event with single-attempt fast-fail behavior.

        This method is intended for asynchronous/background delivery paths where
        latency must stay bounded. It preserves offline buffering guarantees while
        skipping retry/backoff loops.
        """

        payload = self._event_to_payload(event)
        if not self.config.enabled:
            logger.info(
                "backend delivery skipped (disabled) event_type=%s severity=%s camera_id=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
            )
            return DeliveryResult.SKIPPED

        ok, error = self._post_once(payload)
        if ok:
            logger.info("incident delivered", extra={"event": "incident_delivered", "source_id": self.config.source_id or "unknown"})
            return DeliveryResult.OK

        self._enqueue_offline(payload, error or "unknown_error")
        logger.warning(
            "incident delivery failed, queued offline",
            extra={"event": "incident_delivery_failed", "source_id": self.config.source_id or "unknown", "error": error or "unknown_error"},
        )
        return DeliveryResult.FAILED

    def submit_ergonomic_sample_fast(self, event: HazardEvent) -> DeliveryResult:
        """Submit one ergonomic score sample without forcing an incident/alert."""

        payload = self._event_to_payload(event)
        payload["event_type"] = "ergonomic_sample"
        payload["description"] = event.description
        payload["timestamp"] = event.timestamp
        payload["frame_number"] = event.frame_number
        payload["track_id"] = event.track_id
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata["record_only"] = True
        payload["metadata"] = metadata

        if not self.config.enabled:
            return DeliveryResult.SKIPPED

        ok, error = self._post_once(payload)
        if ok:
            return DeliveryResult.OK

        self._enqueue_offline(payload, error or "unknown_error")
        return DeliveryResult.FAILED

    def submit_batch(self, events: list[HazardEvent]) -> tuple[int, int]:
        """Submit multiple incidents sequentially.

        Args:
            events: List of HazardEvent instances.

        Returns:
            Tuple ``(ok_count, failed_count)``.

        Failure Behavior:
            Never raises; each item is handled independently.
        """

        ok_count = 0
        failed_count = 0
        for event in events:
            result = self.submit_incident(event)
            if result == DeliveryResult.OK:
                ok_count += 1
            elif result == DeliveryResult.FAILED:
                failed_count += 1
        return ok_count, failed_count

    def flush_offline_queue(self, limit: int = 100) -> dict:
        """Attempt to resend queued incidents.

        Args:
            limit: Maximum number of rows to process in this flush cycle.

        Returns:
            Dict with flush counters: flushed, failed, remaining.

        Failure Behavior:
            Never raises. Returns best-effort counters when DB is unavailable.
        """

        if not self._db_ready or not self.config.enabled:
            return {"flushed": 0, "failed": 0, "remaining": self.offline_queue_size()}

        flushed = 0
        failed = 0
        rows: list[tuple[int, str, int]] = []
        try:
            with sqlite3.connect(self.config.offline_db) as conn:
                rows = conn.execute(
                    "SELECT id, payload_json, retry_count "
                    "FROM offline_incidents ORDER BY created_at ASC LIMIT ?",
                    (limit,),
                ).fetchall()
        except Exception as exc:
            logger.exception("offline flush read failed: %s", exc)
            return {"flushed": 0, "failed": 0, "remaining": self.offline_queue_size()}

        for row_id, payload_json, retry_count in rows:
            try:
                payload = json.loads(payload_json)
            except Exception as exc:
                failed += 1
                self._mark_retry_error(row_id, retry_count + 1, f"invalid_json: {exc}")
                continue

            # Flush runs on the main pipeline thread; keep it fast-fail to avoid
            # freezing live video when backend is down.
            ok, error = self._post_once(payload)
            if ok:
                self._delete_offline_row(row_id)
                flushed += 1
            else:
                failed += 1
                self._mark_retry_error(row_id, retry_count + 1, error or "unknown_error")

        return {
            "flushed": flushed,
            "failed": failed,
            "remaining": self.offline_queue_size(),
        }

    def _post_once(self, payload: dict) -> tuple[bool, Optional[str]]:
        """POST payload once with no retry/backoff.

        This path is used by periodic queue flush to guarantee low latency
        impact on the real-time loop.
        """

        headers = {"Content-Type": "application/json"}
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        if self.config.source_id:
            headers["X-Source-Id"] = self.config.source_id

        try:
            response = self._session.post(
                self._incidents_url,
                json=payload,
                timeout=self.config.timeout_sec,
                headers=headers,
            )
            if 200 <= response.status_code < 300:
                return True, None
            return False, f"http_{response.status_code}: {response.text[:200]}"
        except requests.RequestException as exc:
            return False, f"request_error: {exc}"
        except Exception as exc:
            return False, f"unexpected_error: {exc}"

    def offline_queue_size(self) -> int:
        """Return current number of queued offline incidents.

        Args:
            None.

        Returns:
            Queue row count.

        Failure Behavior:
            Returns 0 when DB is unavailable or read fails.
        """

        if not self._db_ready:
            return 0
        try:
            with sqlite3.connect(self.config.offline_db) as conn:
                row = conn.execute("SELECT COUNT(*) FROM offline_incidents").fetchone()
            return int(row[0] if row else 0)
        except Exception:
            return 0

    def _post_with_retry(self, payload: dict) -> tuple[bool, Optional[str]]:
        # POST payload with bounded retries.

        attempts = max(1, self.config.max_retry + 1)
        headers = {"Content-Type": "application/json"}
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        if self.config.source_id:
            headers["X-Source-Id"] = self.config.source_id

        last_error: Optional[str] = None
        for attempt in range(attempts):
            try:
                response = self._session.post(
                    self._incidents_url,
                    json=payload,
                    timeout=self.config.timeout_sec,
                    headers=headers,
                )
                if 200 <= response.status_code < 300:
                    return True, None

                last_error = f"http_{response.status_code}: {response.text[:200]}"
            except requests.RequestException as exc:
                last_error = f"request_error: {exc}"
            except Exception as exc:
                last_error = f"unexpected_error: {exc}"

            if attempt < attempts - 1:
                backoff = self._resolve_backoff(attempt)
                self._sleep(backoff)

        return False, last_error

    def _resolve_backoff(self, attempt: int) -> float:
        if attempt < len(self.config.retry_backoff):
            return float(self.config.retry_backoff[attempt])
        return float(self.config.retry_backoff[-1] if self.config.retry_backoff else 0.0)

    def _enqueue_offline(self, payload: dict, error: str) -> None:
        # Persist failed payload to local offline queue.

        if not self._db_ready:
            logger.error("offline queue unavailable, dropping payload")
            return

        try:
            with sqlite3.connect(self.config.offline_db) as conn:
                self._trim_queue_if_needed(conn)
                conn.execute(
                    "INSERT INTO offline_incidents(payload_json, created_at, retry_count, last_error) "
                    "VALUES(?, ?, 0, ?)",
                    (json.dumps(payload, ensure_ascii=False), time.time(), error),
                )
        except Exception as exc:
            logger.exception("failed to enqueue offline payload: %s", exc)

    def _trim_queue_if_needed(self, conn: sqlite3.Connection) -> None:
        # Keep queue bounded by deleting oldest rows before insert.

        max_rows = max(1, int(self.config.offline_queue_max_rows))
        row = conn.execute("SELECT COUNT(*) FROM offline_incidents").fetchone()
        current = int(row[0] if row else 0)
        if current < max_rows:
            return

        # Prevent unbounded disk growth by dropping the oldest rows first.
        to_delete = current - max_rows + 1
        conn.execute(
            "DELETE FROM offline_incidents WHERE id IN "
            "(SELECT id FROM offline_incidents ORDER BY created_at ASC LIMIT ?)",
            (to_delete,),
        )

    def _delete_offline_row(self, row_id: int) -> None:
        if not self._db_ready:
            return
        try:
            with sqlite3.connect(self.config.offline_db) as conn:
                conn.execute("DELETE FROM offline_incidents WHERE id = ?", (row_id,))
        except Exception as exc:
            logger.exception("failed deleting offline row id=%s: %s", row_id, exc)

    def _mark_retry_error(self, row_id: int, retry_count: int, error: str) -> None:
        if not self._db_ready:
            return
        try:
            with sqlite3.connect(self.config.offline_db) as conn:
                conn.execute(
                    "UPDATE offline_incidents SET retry_count = ?, last_error = ? WHERE id = ?",
                    (retry_count, error[:500], row_id),
                )
        except Exception as exc:
            logger.exception("failed updating offline row id=%s: %s", row_id, exc)

    @staticmethod
    def _event_to_payload(event: HazardEvent) -> dict:
        # Convert HazardEvent to backend IncidentCreate schema.
        severity_map = {
            "CRITICAL": "High",
            "HIGH": "High",
            "MEDIUM": "Medium",
            "LOW": "Low",
        }
        severity = severity_map.get(str(event.severity.name).upper(), "Medium")
        classification = str(event.event_type or "Hazard").replace("_", " ").title()

        zone = "Unknown Zone"
        if isinstance(event.metadata, dict):
            zone = (
                event.metadata.get("zone")
                or event.metadata.get("location")
                or event.metadata.get("camera_zone")
                or zone
            )

        track_part = f"T{event.track_id}" if event.track_id is not None else "TNA"
        incident_id = f"INC-{int(event.timestamp)}-{event.frame_number}-{track_part}"
        camera_name = getattr(event, "camera_name", None) or settings.BACKEND_CAMERA_NAME or None
        worker_id = getattr(event, "worker_id", None) or settings.BACKEND_WORKER_ID or None
        worker_gpu_id = getattr(event, "worker_gpu_id", None) or settings.BACKEND_WORKER_GPU_ID or None

        payload = {
            "id": incident_id,
            "zone": str(zone),
            "classification": classification,
            "severity": severity,
            "camera_id": event.camera_id,
            "camera_name": camera_name,
            "worker_id": worker_id,
            "worker_gpu_id": worker_gpu_id,
            "track_id": event.track_id,
            "root_cause": event.description or "Auto-detected by edge_ai pipeline",
            "corrective_action": "Investigate and acknowledge incident",
            "created_at": time.strftime("%Y-%m-%d", time.localtime(event.timestamp)),
        }
        if isinstance(event.metadata, dict):
            payload["metadata"] = BackendClient._to_json_safe(event.metadata)
        return BackendClient._to_json_safe(payload)

    @staticmethod
    def _to_json_safe(value: Any) -> Any:
        """Recursively normalize values into JSON-serializable primitives.

        Handles numpy scalar/array-like values through ``item``/``tolist`` when
        present, without introducing a hard numpy dependency here.
        """

        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, dict):
            return {
                str(k): BackendClient._to_json_safe(v)
                for k, v in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [BackendClient._to_json_safe(v) for v in value]

        # numpy scalar-like (e.g., np.float32, np.int64)
        if hasattr(value, "item"):
            try:
                return BackendClient._to_json_safe(value.item())
            except Exception:
                pass

        # numpy array-like
        if hasattr(value, "tolist"):
            try:
                return BackendClient._to_json_safe(value.tolist())
            except Exception:
                pass

        # Last-resort safe representation to avoid delivery crashes.
        return str(value)
