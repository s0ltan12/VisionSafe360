"""Alert routing manager for post-analysis hazard events."""
from __future__ import annotations

import logging
import time
import base64
import heapq
from dataclasses import dataclass, field
from itertools import count
from queue import Empty, Full, PriorityQueue
from threading import Event, Lock, Thread
from typing import Optional

import cv2

from ..config import settings
from .frame_ring_buffer import FrameRingBuffer
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


@dataclass(order=True, slots=True)
class _PrioritizedDeliveryTask:
    """Priority queue wrapper; lower priority value is delivered first."""

    priority: int
    sequence: int
    task: _DeliveryTask = field(compare=False)


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
        ring_buffer: Optional[FrameRingBuffer] = None,
    ) -> None:
        """Initialize alert manager dependencies.

        Args:
            backend_client: Mandatory backend delivery client.
            fcm_service: Optional push notification service.
            siren_controller: Optional local siren controller.
            config: Optional routing configuration override.
            ring_buffer: Optional circular frame buffer for video evidence.

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
        self.ring_buffer = ring_buffer
        self._stop_event = Event()
        self._queue: Optional[PriorityQueue[_PrioritizedDeliveryTask]] = None
        self._worker: Optional[Thread] = None
        self._delivery_sequence = count()
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
            self._queue = PriorityQueue(maxsize=max(1, self.config.async_queue_maxsize))
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

    def process_events(
        self,
        events: list[HazardEvent],
        frame=None,
        ring_buffer: Optional[FrameRingBuffer] = None,
    ) -> dict:
        """Process emitted events and route each one independently.

        Args:
            events: List of emitted HazardEvent objects for the current frame.
            frame: Optional annotated frame captured at the hazard moment.
            ring_buffer: Optional circular frame buffer for video evidence.

        Returns:
            Dictionary with per-frame delivery counters.

        Failure Behavior:
            Never raises. Any per-channel delivery failure is logged and
            represented as a failed counter.
        """

        metrics = FrameDeliveryMetrics(n_events_emitted=len(events))

        # Determine the ring buffer to use (override with parameter if provided)
        buf = ring_buffer if ring_buffer is not None else self.ring_buffer

        if self.siren_controller is not None:
            self.siren_controller.tick()

        if not self.config.alerts_enabled:
            metrics.offline_queue_size = self.backend_client.offline_queue_size()
            return metrics.to_dict()

        for event in events:
            if not self._is_valid_event(event):
                logger.warning("invalid hazard event skipped: %r", event)
                continue
            if isinstance(event.metadata, dict) and event.metadata.get("suppress_event"):
                logger.info(
                    "suppressed event skipped by alert manager event_type=%s camera_id=%s track_id=%s",
                    event.event_type,
                    event.camera_id,
                    event.track_id,
                )
                continue

            self._attach_event_frame([event], frame)

            # Route siren immediately (low latency local response)
            self._route_siren(event, metrics)

            if buf is not None and settings.EVIDENCE_CLIP_ENABLED:
                # Spawn deferred clip assembly background thread.
                # This gathers pre-event frames, collects post-event frames, encodes
                # the 3s MP4 video evidence, and then submits the alert.
                thread = Thread(
                    target=self._assemble_and_route_clip,
                    args=(event, buf),
                    name=f"ClipAssembly-{event.event_type}-{event.frame_number}",
                    daemon=True,
                )
                thread.start()
                # Since delivery is deferred, we count this event as queued/pending.
                if self.config.async_delivery_enabled:
                    metrics.add_queue_result(DeliveryChannel.BACKEND, DeliveryStatus.SUCCESS)
                    if self._should_send_fcm(event.severity) and self._fcm_has_recipients():
                        metrics.add_queue_result(DeliveryChannel.FCM, DeliveryStatus.SUCCESS)
            else:
                # Fallback to single-frame JPEG snapshot
                self._attach_evidence_snapshot([event], frame)
                if self.config.async_delivery_enabled:
                    self._enqueue_fcm(event, metrics)
                    self._enqueue_backend(event, metrics)
                else:
                    self._route_fcm(event, metrics)
                    self._route_backend(event, metrics)

        if self.config.async_delivery_enabled:
            self._apply_async_delivery_delta(metrics)
        metrics.offline_queue_size = self.backend_client.offline_queue_size()
        return metrics.to_dict()

    def _assemble_and_route_clip(
        self,
        event: HazardEvent,
        ring_buffer: FrameRingBuffer,
    ) -> None:
        """Background thread worker to accumulate post-event frames, encode clip and deliver."""
        try:
            logger.info(
                "clip_assembly_start event_type=%s frame=%s camera=%s",
                event.event_type, event.frame_number, event.camera_id,
            )
            # 1. Start clip (captures pre-event frames)
            clip = ring_buffer.start_clip(
                event_timestamp=event.timestamp,
                pre_sec=settings.EVIDENCE_CLIP_HALF_SEC,
                post_sec=settings.EVIDENCE_CLIP_HALF_SEC,
            )

            # 2. Wait for the post-event frames to accumulate.
            # We poll clip.assembled or wait up to settings.EVIDENCE_CLIP_POST_WAIT_SEC + 2.0s buffer.
            start_wait = time.monotonic()
            wait_limit = settings.EVIDENCE_CLIP_POST_WAIT_SEC + 2.0
            while not clip.assembled and (time.monotonic() - start_wait < wait_limit):
                time.sleep(0.1)

            # 3. Retrieve all frames
            frames = ring_buffer.all_frames(clip)
            ring_buffer.cleanup_clip(clip)

            if not frames:
                logger.warning(
                    "No frames collected for clip event %s, frame_number=%d",
                    event.event_type,
                    event.frame_number,
                )
                return

            # 4. Encode the clip to base64 MP4
            from .video_clip_encoder import encode_clip
            result = encode_clip(
                frames=frames,
                fps=settings.EVIDENCE_CLIP_VIDEO_FPS,
                max_width=settings.EVIDENCE_CLIP_MAX_WIDTH,
                jpeg_quality=settings.EVIDENCE_CLIP_JPEG_QUALITY,
                target_duration_sec=settings.EVIDENCE_CLIP_DURATION_SEC,
                event_timestamp=event.timestamp,
            )

            if result is None:
                logger.warning(
                    "Failed to encode video clip for event %s, frame_number=%d",
                    event.event_type,
                    event.frame_number,
                )
                return

            # 5. Attach clip details to event metadata
            if not isinstance(event.metadata, dict):
                event.metadata = {}
            exact_frame = event.metadata.get("event_frame_data_url")
            event.metadata["snapshot_data_url"] = exact_frame or result.thumbnail_data_url
            event.metadata["clip_thumbnail_data_url"] = result.thumbnail_data_url
            event.metadata["video_evidence_data_url"] = result.video_data_url
            event.metadata.setdefault("snapshot_width", result.frame_width)
            event.metadata.setdefault("snapshot_height", result.frame_height)
            event.metadata["evidence_kind"] = "video_clip"
            event.metadata["evidence_captured_at"] = event.timestamp
            event.metadata["video_duration_sec"] = result.duration_sec
            event.metadata["event_offset_sec"] = settings.EVIDENCE_CLIP_HALF_SEC

            logger.info(
                "clip_assembly_done event_type=%s frame=%s n_frames=%d size_kb=%.1f duration_sec=%.2f",
                event.event_type, event.frame_number,
                result.n_frames,
                len(result.video_data_url) * 0.75 / 1024,
                result.duration_sec,
            )

            # 6. Route or enqueue the event
            if self.config.async_delivery_enabled:
                self._enqueue_fcm(event)
                self._enqueue_backend(event)
            else:
                self._route_fcm(event)
                self._route_backend(event)

        except Exception as exc:
            logger.exception("Failed in _assemble_and_route_clip: %s", exc)

    def _attach_event_frame(self, events: list[HazardEvent], frame) -> None:
        """Attach the exact annotated frame from the hazard moment."""

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
            event.metadata["event_frame_data_url"] = data_url
            event.metadata["event_frame_width"] = width
            event.metadata["event_frame_height"] = height
            event.metadata["event_frame_number"] = event.frame_number
            event.metadata["event_frame_timestamp"] = event.timestamp
            if event.track_id is not None:
                event.metadata.setdefault("event_track_id", event.track_id)
            event.metadata.setdefault("snapshot_data_url", data_url)
            event.metadata.setdefault("snapshot_width", width)
            event.metadata.setdefault("snapshot_height", height)
            event.metadata.setdefault("evidence_kind", "annotated_event_frame")
            event.metadata.setdefault("evidence_captured_at", event.timestamp)

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

    def _route_backend(self, event: HazardEvent, metrics: Optional[FrameDeliveryMetrics] = None) -> None:
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

            if metrics is not None:
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
            if metrics is not None:
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

    def _enqueue_backend(self, event: HazardEvent, metrics: Optional[FrameDeliveryMetrics] = None) -> None:
        """Queue backend delivery without blocking frame loop."""

        if self._queue is None:
            self._route_backend(event, metrics)
            return
        queued, evicted = self._enqueue_delivery_task(DeliveryChannel.BACKEND, event)
        if queued:
            if metrics is not None:
                metrics.add_queue_result(DeliveryChannel.BACKEND, DeliveryStatus.SUCCESS)
            if evicted is not None:
                logger.warning(
                    "backend queue evicted lower-priority event_type=%s severity=%s camera_id=%s for event_type=%s severity=%s camera_id=%s",
                    evicted.event_type,
                    evicted.severity.name,
                    evicted.camera_id,
                    event.event_type,
                    event.severity.name,
                    event.camera_id,
                )
            return
        if metrics is not None:
            metrics.add_queue_result(DeliveryChannel.BACKEND, DeliveryStatus.FAILED)
        logger.warning(
            "backend queue full event_type=%s severity=%s camera_id=%s",
            event.event_type,
            event.severity.name,
            event.camera_id,
        )

    def _route_fcm(self, event: HazardEvent, metrics: Optional[FrameDeliveryMetrics] = None) -> None:
        # Route event to push notifications when policy requires it.

        if not self._should_send_fcm(event.severity):
            return

        # If FCM is enabled but has no recipients configured, skip routing.
        if not self._fcm_has_recipients():
            return

        if self.fcm_service is None:
            if metrics is not None:
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
            if metrics is not None:
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
            if metrics is not None:
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

    def _enqueue_fcm(self, event: HazardEvent, metrics: Optional[FrameDeliveryMetrics] = None) -> None:
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
            if metrics is not None:
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

        queued, evicted = self._enqueue_delivery_task(DeliveryChannel.FCM, event)
        if queued:
            if metrics is not None:
                metrics.add_queue_result(DeliveryChannel.FCM, DeliveryStatus.SUCCESS)
            if evicted is not None:
                logger.warning(
                    "fcm queue evicted lower-priority event_type=%s severity=%s camera_id=%s for event_type=%s severity=%s camera_id=%s",
                    evicted.event_type,
                    evicted.severity.name,
                    evicted.camera_id,
                    event.event_type,
                    event.severity.name,
                    event.camera_id,
                )
            return
        if metrics is not None:
            metrics.add_queue_result(DeliveryChannel.FCM, DeliveryStatus.FAILED)
        logger.warning(
            "fcm queue full event_type=%s severity=%s camera_id=%s",
            event.event_type,
            event.severity.name,
            event.camera_id,
        )

    def _enqueue_delivery_task(
        self,
        channel: DeliveryChannel,
        event: HazardEvent,
    ) -> tuple[bool, HazardEvent | None]:
        """Queue a task, evicting lower-severity work when the queue is full."""

        if self._queue is None:
            return False, None

        candidate = self._prioritized_task(channel, event)
        try:
            self._queue.put_nowait(candidate)
            return True, None
        except Full:
            pass

        with self._queue.mutex:
            queued = self._queue.queue
            if not queued:
                return False, None
            worst_idx, worst = max(
                enumerate(queued),
                key=lambda item: (item[1].priority, item[1].sequence),
            )
            if candidate.priority >= worst.priority:
                return False, None

            evicted_event = worst.task.event
            queued[worst_idx] = candidate
            heapq.heapify(queued)
            self._queue.not_empty.notify()
            return True, evicted_event

    def _delivery_worker(self) -> None:
        """Background consumer for backend and FCM deliveries."""

        if self._queue is None:
            return

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                queued = self._queue.get(timeout=max(0.01, self.config.async_poll_timeout_sec))
            except Empty:
                continue

            try:
                self._deliver_task(queued.task)
            except Exception as exc:
                logger.exception("alert worker task failed: %s", exc)
            finally:
                self._queue.task_done()

    def _prioritized_task(
        self,
        channel: DeliveryChannel,
        event: HazardEvent,
    ) -> _PrioritizedDeliveryTask:
        return _PrioritizedDeliveryTask(
            priority=self._priority_for(event.severity),
            sequence=next(self._delivery_sequence),
            task=_DeliveryTask(channel=channel, event=event),
        )

    @staticmethod
    def _priority_for(severity: Severity) -> int:
        return {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }.get(severity, 3)

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
