"""Alert routing manager for post-analysis hazard events."""
from __future__ import annotations

import logging
import time
import base64
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Optional

import cv2

from ..config import settings
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity
from ..integration.backend_client import BackendClient, DeliveryResult as BackendDeliveryResult
from .fcm_service import FCMService
from .notification_service import (
    DeliveryChannel,
    DeliveryResult,
    DeliveryStatus,
    FrameDeliveryMetrics,
)
from .siren_controller import SirenController

logger = logging.getLogger(__name__)

_SNAPSHOT_MAX_WIDTH = 960
_SNAPSHOT_JPEG_QUALITY = 72


@dataclass(slots=True)
class AlertManagerConfig:
    """Runtime config for alert routing decisions."""

    alerts_enabled: bool = settings.ALERTS_ENABLED
    medium_fcm_enabled: bool = settings.ALERT_MEDIUM_ENABLE_FCM
    async_delivery_enabled: bool = settings.ALERT_ASYNC_DELIVERY_ENABLED
    async_queue_maxsize: int = settings.ALERT_ASYNC_QUEUE_MAXSIZE
    async_poll_timeout_sec: float = settings.ALERT_ASYNC_POLL_TIMEOUT_SEC


@dataclass(slots=True)
class _DeliveryTask:
    """Internal queued delivery unit for async channels."""

    channel: DeliveryChannel
    event: HazardEvent


class AlertManager:
    """Route hazard events to backend, FCM, and siren channels.

    The manager isolates channel failures to prevent one integration from
    impacting others.
    """

    def __init__(
        self,
        *,
        backend_client: BackendClient,
        fcm_service: Optional[FCMService] = None,
        siren_controller: Optional[SirenController] = None,
        config: Optional[AlertManagerConfig] = None,
    ) -> None:
        """Initialize alert manager dependencies.

        Args:
            backend_client: Mandatory backend delivery client.
            fcm_service: Optional push notification service.
            siren_controller: Optional local siren controller.
            config: Optional routing configuration override.

        Returns:
            None.

        Failure Behavior:
            Never raises for missing optional services; routing gracefully
            skips unavailable channels.
        """

        self.backend_client = backend_client
        self.fcm_service = fcm_service
        self.siren_controller = siren_controller
        self.config = config or AlertManagerConfig()
        self._stop_event = Event()
        self._queue: Optional[Queue[_DeliveryTask]] = None
        self._worker: Optional[Thread] = None
        self._delivery_counter_lock = Lock()
        self._delivery_counters: dict[DeliveryChannel, dict[DeliveryStatus, int]] = {
            DeliveryChannel.BACKEND: {DeliveryStatus.SUCCESS: 0, DeliveryStatus.FAILED: 0},
            DeliveryChannel.FCM: {DeliveryStatus.SUCCESS: 0, DeliveryStatus.FAILED: 0},
        }
        self._reported_delivery_counters: dict[DeliveryChannel, dict[DeliveryStatus, int]] = {
            DeliveryChannel.BACKEND: {DeliveryStatus.SUCCESS: 0, DeliveryStatus.FAILED: 0},
            DeliveryChannel.FCM: {DeliveryStatus.SUCCESS: 0, DeliveryStatus.FAILED: 0},
        }
        self._last_failure_log_at: dict[DeliveryChannel, float] = {
            DeliveryChannel.BACKEND: 0.0,
            DeliveryChannel.FCM: 0.0,
        }

        if self.config.async_delivery_enabled:
            self._queue = Queue(maxsize=max(1, self.config.async_queue_maxsize))
            self._worker = Thread(
                target=self._delivery_worker,
                name="AlertDeliveryWorker",
                daemon=True,
            )
            self._worker.start()

    def shutdown(self, timeout_sec: float = 2.0) -> None:
        """Stop async worker gracefully.

        Args:
            timeout_sec: Maximum wait time for worker termination.

        Returns:
            None.

        Failure Behavior:
            Never raises; failures are logged and ignored.
        """

        self._stop_event.set()
        if self._worker is None:
            return
        try:
            self._worker.join(timeout=max(0.0, timeout_sec))
        except Exception as exc:
            logger.exception("alert worker shutdown failed: %s", exc)

    def process_events(self, events: list[HazardEvent], frame=None) -> dict:
        """Process emitted events and route each one independently.

        Args:
            events: List of emitted HazardEvent objects for the current frame.
            frame: Optional annotated frame captured at the hazard moment.

        Returns:
            Dictionary with per-frame delivery counters.

        Failure Behavior:
            Never raises. Any per-channel delivery failure is logged and
            represented as a failed counter.
        """

        metrics = FrameDeliveryMetrics(n_events_emitted=len(events))
        self._attach_evidence_snapshot(events, frame)

        if self.siren_controller is not None:
            self.siren_controller.tick()

        if not self.config.alerts_enabled:
            metrics.offline_queue_size = self.backend_client.offline_queue_size()
            return metrics.to_dict()

        for event in events:
            if not self._is_valid_event(event):
                logger.warning("invalid hazard event skipped: %r", event)
                continue

            if self.config.async_delivery_enabled:
                self._enqueue_fcm(event, metrics)
                self._enqueue_backend(event, metrics)
            else:
                self._route_fcm(event, metrics)
                self._route_backend(event, metrics)
            self._route_siren(event, metrics)

        if self.config.async_delivery_enabled:
            self._apply_async_delivery_delta(metrics)
        metrics.offline_queue_size = self.backend_client.offline_queue_size()
        return metrics.to_dict()

    def _attach_evidence_snapshot(self, events: list[HazardEvent], frame) -> None:
        """Attach one encoded evidence frame to every alert event in this frame."""

        if not events or frame is None:
            return

        encoded = self._encode_snapshot_data_url(frame)
        if encoded is None:
            return

        data_url, width, height = encoded
        for event in events:
            if not isinstance(event.metadata, dict):
                event.metadata = {}
            if event.metadata.get("record_only"):
                continue
            event.metadata.setdefault("snapshot_data_url", data_url)
            event.metadata.setdefault("snapshot_width", width)
            event.metadata.setdefault("snapshot_height", height)
            event.metadata.setdefault("evidence_kind", "annotated_frame")
            event.metadata.setdefault("evidence_captured_at", event.timestamp)

    def _encode_snapshot_data_url(self, frame) -> Optional[tuple[str, int, int]]:
        """Encode a compact JPEG data URL suitable for backend alert evidence."""

        try:
            height, width = frame.shape[:2]
            output = frame
            if width > _SNAPSHOT_MAX_WIDTH:
                scale = _SNAPSHOT_MAX_WIDTH / float(width)
                output = cv2.resize(
                    frame,
                    (_SNAPSHOT_MAX_WIDTH, max(1, int(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )
                height, width = output.shape[:2]

            ok, buffer = cv2.imencode(
                ".jpg",
                output,
                [int(cv2.IMWRITE_JPEG_QUALITY), _SNAPSHOT_JPEG_QUALITY],
            )
            if not ok:
                logger.warning("alert evidence snapshot encode failed")
                return None
            payload = base64.b64encode(buffer).decode("ascii")
            return f"data:image/jpeg;base64,{payload}", width, height
        except Exception as exc:
            logger.warning("alert evidence snapshot unavailable: %s", exc)
            return None

    def _is_valid_event(self, event: HazardEvent) -> bool:
        # Validate minimal event shape.

        return bool(event.event_type and event.camera_id and event.severity)

    def _route_backend(self, event: HazardEvent, metrics: FrameDeliveryMetrics) -> None:
        # Route event to backend channel.

        try:
            result = self.backend_client.submit_incident(event)
            if result == BackendDeliveryResult.OK:
                status = DeliveryStatus.SUCCESS
                error = None
            elif result == BackendDeliveryResult.FAILED:
                status = DeliveryStatus.FAILED
                error = "backend_submit_failed"
            else:
                status = DeliveryStatus.SKIPPED
                error = "backend_delivery_skipped"

            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.BACKEND,
                    status=status,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error=error,
                )
            )
            if result == BackendDeliveryResult.FAILED:
                logger.warning(
                    "backend delivery failed event_type=%s severity=%s camera_id=%s",
                    event.event_type,
                    event.severity.name,
                    event.camera_id,
                )
        except Exception as exc:
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.BACKEND,
                    status=DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error=str(exc),
                )
            )
            logger.exception(
                "backend delivery exception event_type=%s severity=%s camera_id=%s error=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
                exc,
            )

    def _enqueue_backend(self, event: HazardEvent, metrics: FrameDeliveryMetrics) -> None:
        """Queue backend delivery without blocking frame loop."""

        if self._queue is None:
            self._route_backend(event, metrics)
            return
        try:
            self._queue.put_nowait(_DeliveryTask(channel=DeliveryChannel.BACKEND, event=event))
            metrics.add_queue_result(DeliveryChannel.BACKEND, DeliveryStatus.SUCCESS)
        except Full:
            metrics.add_queue_result(DeliveryChannel.BACKEND, DeliveryStatus.FAILED)
            logger.warning(
                "backend queue full event_type=%s severity=%s camera_id=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
            )

    def _route_fcm(self, event: HazardEvent, metrics: FrameDeliveryMetrics) -> None:
        # Route event to push notifications when policy requires it.

        if not self._should_send_fcm(event.severity):
            return

        # If FCM is enabled but has no recipients configured, skip routing.
        if not self._fcm_has_recipients():
            return

        if self.fcm_service is None:
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.FCM,
                    status=DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error="fcm_service_unavailable",
                )
            )
            return

        try:
            ok = self.fcm_service.send_event(event)
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.FCM,
                    status=DeliveryStatus.SUCCESS if ok else DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error=None if ok else "fcm_send_failed",
                )
            )
            if not ok:
                logger.warning(
                    "fcm delivery failed event_type=%s severity=%s camera_id=%s",
                    event.event_type,
                    event.severity.name,
                    event.camera_id,
                )
        except Exception as exc:
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.FCM,
                    status=DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error=str(exc),
                )
            )
            logger.exception(
                "fcm delivery exception event_type=%s severity=%s camera_id=%s error=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
                exc,
            )

    def _enqueue_fcm(self, event: HazardEvent, metrics: FrameDeliveryMetrics) -> None:
        """Queue FCM delivery when routing policy requires it."""

        if not self._should_send_fcm(event.severity):
            return

        # If FCM is enabled but has no recipients configured, skip routing.
        if not self._fcm_has_recipients():
            return

        if self._queue is None:
            self._route_fcm(event, metrics)
            return

        if self.fcm_service is None:
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.FCM,
                    status=DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error="fcm_service_unavailable",
                )
            )
            return

        try:
            self._queue.put_nowait(_DeliveryTask(channel=DeliveryChannel.FCM, event=event))
            metrics.add_queue_result(DeliveryChannel.FCM, DeliveryStatus.SUCCESS)
        except Full:
            metrics.add_queue_result(DeliveryChannel.FCM, DeliveryStatus.FAILED)
            logger.warning(
                "fcm queue full event_type=%s severity=%s camera_id=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
            )

    def _delivery_worker(self) -> None:
        """Background consumer for backend and FCM deliveries."""

        if self._queue is None:
            return

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                task = self._queue.get(timeout=max(0.01, self.config.async_poll_timeout_sec))
            except Empty:
                continue

            try:
                self._deliver_task(task)
            except Exception as exc:
                logger.exception("alert worker task failed: %s", exc)
            finally:
                self._queue.task_done()

    def _deliver_task(self, task: _DeliveryTask) -> None:
        """Execute one queued delivery task."""

        event = task.event
        if task.channel == DeliveryChannel.BACKEND:
            if hasattr(self.backend_client, "submit_incident_fast"):
                result = self.backend_client.submit_incident_fast(event)
            else:
                result = self.backend_client.submit_incident(event)
            if result == BackendDeliveryResult.SKIPPED:
                return
            self._record_async_delivery_result(
                DeliveryChannel.BACKEND, result == BackendDeliveryResult.OK
            )
            if result == BackendDeliveryResult.FAILED and self._should_log_failure(task.channel):
                logger.warning(
                    "backend delivery failed event_type=%s severity=%s camera_id=%s",
                    event.event_type,
                    event.severity.name,
                    event.camera_id,
                )
            return

        if task.channel == DeliveryChannel.FCM:
            if not self._fcm_has_recipients():
                return
            if self.fcm_service is None:
                self._record_async_delivery_result(DeliveryChannel.FCM, False)
                return
            ok = self.fcm_service.send_event(event)
            self._record_async_delivery_result(DeliveryChannel.FCM, ok)
            if not ok and self._should_log_failure(task.channel):
                logger.warning(
                    "fcm delivery failed event_type=%s severity=%s camera_id=%s",
                    event.event_type,
                    event.severity.name,
                    event.camera_id,
                )

    def _should_log_failure(self, channel: DeliveryChannel, interval_sec: float = 5.0) -> bool:
        """Return True when enough time elapsed since last channel failure log."""

        now = time.monotonic()
        last = self._last_failure_log_at.get(channel, 0.0)
        if now - last < interval_sec:
            return False
        self._last_failure_log_at[channel] = now
        return True

    def _route_siren(self, event: HazardEvent, metrics: FrameDeliveryMetrics) -> None:
        # Route CRITICAL events to local siren.

        if event.severity != Severity.CRITICAL:
            return

        if self.siren_controller is None:
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.SIREN,
                    status=DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error="siren_service_unavailable",
                )
            )
            return

        try:
            ok = self.siren_controller.trigger(event)
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.SIREN,
                    status=DeliveryStatus.SUCCESS if ok else DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error=None if ok else "siren_trigger_failed",
                )
            )
        except Exception as exc:
            metrics.add(
                DeliveryResult(
                    channel=DeliveryChannel.SIREN,
                    status=DeliveryStatus.FAILED,
                    event_type=event.event_type,
                    severity=event.severity.name,
                    camera_id=event.camera_id,
                    error=str(exc),
                )
            )
            logger.exception(
                "siren trigger exception event_type=%s severity=%s camera_id=%s error=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
                exc,
            )

    def _should_send_fcm(self, severity: Severity) -> bool:
        # Return True when routing policy requires push delivery.

        if severity == Severity.MEDIUM:
            return self.config.medium_fcm_enabled
        return severity in {Severity.HIGH, Severity.CRITICAL}

    def _fcm_has_recipients(self) -> bool:
        """Return True when FCM is actually routable to at least one token.

        For test stubs that do not expose a config object, assume routable.
        """

        if self.fcm_service is None:
            return False

        cfg = getattr(self.fcm_service, "config", None)
        if cfg is None:
            return True

        enabled = getattr(cfg, "enabled", True)
        if not enabled:
            return False

        tokens = getattr(cfg, "device_tokens", None)
        if tokens is None:
            return True

        return len(tokens) > 0

    def _record_async_delivery_result(self, channel: DeliveryChannel, ok: bool) -> None:
        """Thread-safe aggregate of worker-completed delivery outcomes."""

        status = DeliveryStatus.SUCCESS if ok else DeliveryStatus.FAILED
        with self._delivery_counter_lock:
            self._delivery_counters[channel][status] += 1

    def _apply_async_delivery_delta(self, metrics: FrameDeliveryMetrics) -> None:
        """Apply completed async delivery delta since previous process_events call."""

        with self._delivery_counter_lock:
            current = {
                DeliveryChannel.BACKEND: {
                    DeliveryStatus.SUCCESS: self._delivery_counters[DeliveryChannel.BACKEND][DeliveryStatus.SUCCESS],
                    DeliveryStatus.FAILED: self._delivery_counters[DeliveryChannel.BACKEND][DeliveryStatus.FAILED],
                },
                DeliveryChannel.FCM: {
                    DeliveryStatus.SUCCESS: self._delivery_counters[DeliveryChannel.FCM][DeliveryStatus.SUCCESS],
                    DeliveryStatus.FAILED: self._delivery_counters[DeliveryChannel.FCM][DeliveryStatus.FAILED],
                },
            }

            delta_backend_ok = (
                current[DeliveryChannel.BACKEND][DeliveryStatus.SUCCESS]
                - self._reported_delivery_counters[DeliveryChannel.BACKEND][DeliveryStatus.SUCCESS]
            )
            delta_backend_failed = (
                current[DeliveryChannel.BACKEND][DeliveryStatus.FAILED]
                - self._reported_delivery_counters[DeliveryChannel.BACKEND][DeliveryStatus.FAILED]
            )
            delta_fcm_ok = (
                current[DeliveryChannel.FCM][DeliveryStatus.SUCCESS]
                - self._reported_delivery_counters[DeliveryChannel.FCM][DeliveryStatus.SUCCESS]
            )
            delta_fcm_failed = (
                current[DeliveryChannel.FCM][DeliveryStatus.FAILED]
                - self._reported_delivery_counters[DeliveryChannel.FCM][DeliveryStatus.FAILED]
            )

            self._reported_delivery_counters = current

        metrics.apply_async_delivery_delta(
            backend_delta_ok=max(0, delta_backend_ok),
            backend_delta_failed=max(0, delta_backend_failed),
            backend_total_ok=current[DeliveryChannel.BACKEND][DeliveryStatus.SUCCESS],
            backend_total_failed=current[DeliveryChannel.BACKEND][DeliveryStatus.FAILED],
            fcm_delta_ok=max(0, delta_fcm_ok),
            fcm_delta_failed=max(0, delta_fcm_failed),
            fcm_total_ok=current[DeliveryChannel.FCM][DeliveryStatus.SUCCESS],
            fcm_total_failed=current[DeliveryChannel.FCM][DeliveryStatus.FAILED],
        )

    def get_async_delivery_counters(self) -> dict:
        """Return absolute worker-completed delivery counters since startup."""

        with self._delivery_counter_lock:
            return {
                "backend_ok": self._delivery_counters[DeliveryChannel.BACKEND][DeliveryStatus.SUCCESS],
                "backend_failed": self._delivery_counters[DeliveryChannel.BACKEND][DeliveryStatus.FAILED],
                "fcm_ok": self._delivery_counters[DeliveryChannel.FCM][DeliveryStatus.SUCCESS],
                "fcm_failed": self._delivery_counters[DeliveryChannel.FCM][DeliveryStatus.FAILED],
            }
