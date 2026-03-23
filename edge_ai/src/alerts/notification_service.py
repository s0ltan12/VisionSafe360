"""Shared alert-delivery data structures.

This module provides small, typed primitives used by the alerting layer to
record per-channel delivery outcomes and aggregate frame-level metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DeliveryChannel(str, Enum):
	"""Destination channel used to deliver a hazard event."""

	BACKEND = "backend"
	FCM = "fcm"
	SIREN = "siren"


class DeliveryStatus(str, Enum):
	"""Result status for a single channel delivery attempt."""

	SUCCESS = "success"
	FAILED = "failed"
	SKIPPED = "skipped"


@dataclass(slots=True)
class DeliveryResult:
	"""Outcome for one event-channel delivery operation.

	Attributes:
		channel: Target delivery channel.
		status: Result status.
		event_type: Hazard event type.
		severity: Severity name as uppercase string.
		camera_id: Logical camera identifier.
		error: Optional error string for failed outcomes.
	"""

	channel: DeliveryChannel
	status: DeliveryStatus
	event_type: str
	severity: str
	camera_id: str
	error: Optional[str] = None


@dataclass(slots=True)
class FrameDeliveryMetrics:
	"""Delivery counters for a single processed frame.

	Sync vs async:
	- Sync mode (``async_delivery_enabled=False``): deliveries are performed
	  inline. ``n_backend_ok`` / ``n_backend_failed`` and ``n_fcm_ok`` /
	  ``n_fcm_failed`` represent completed delivery outcomes for this frame.
	- Async mode (``async_delivery_enabled=True``): deliveries are enqueued.
	  Queue results are exposed via ``n_*_queued_ok`` / ``n_*_queue_failed``.
	  Worker-completed deliveries are reported as:
	  - Per-frame deltas: ``n_backend_completed_this_frame`` and
	    ``n_fcm_completed_this_frame``.
	  - Cumulative totals since AlertManager startup:
	    ``n_backend_delivered_ok`` / ``n_backend_delivered_failed`` and
	    ``n_fcm_delivered_ok`` / ``n_fcm_delivered_failed``.
	"""

	n_events_emitted: int = 0
	n_backend_ok: int = 0
	n_backend_failed: int = 0
	n_fcm_ok: int = 0
	n_fcm_failed: int = 0
	n_backend_queued_ok: int = 0
	n_backend_queue_failed: int = 0
	n_fcm_queued_ok: int = 0
	n_fcm_queue_failed: int = 0
	n_backend_completed_this_frame: int = 0
	n_fcm_completed_this_frame: int = 0
	n_backend_delivered_ok: int = 0
	n_backend_delivered_failed: int = 0
	n_fcm_delivered_ok: int = 0
	n_fcm_delivered_failed: int = 0
	n_siren_triggers: int = 0
	offline_queue_size: int = 0
	results: list[DeliveryResult] = field(default_factory=list)

	def add(self, result: DeliveryResult) -> None:
		"""Add one delivery result and update counters.

		Args:
			result: DeliveryResult to include in this frame aggregate.

		Returns:
			None.

		Failure Behavior:
			Never raises; unknown channels are ignored for counters.
		"""

		self.results.append(result)
		if result.channel == DeliveryChannel.BACKEND:
			if result.status == DeliveryStatus.SUCCESS:
				self.n_backend_ok += 1
				self.n_backend_completed_this_frame += 1
				self.n_backend_delivered_ok += 1
			elif result.status == DeliveryStatus.FAILED:
				self.n_backend_failed += 1
				self.n_backend_completed_this_frame += 1
				self.n_backend_delivered_failed += 1
		elif result.channel == DeliveryChannel.FCM:
			if result.status == DeliveryStatus.SUCCESS:
				self.n_fcm_ok += 1
				self.n_fcm_completed_this_frame += 1
				self.n_fcm_delivered_ok += 1
			elif result.status == DeliveryStatus.FAILED:
				self.n_fcm_failed += 1
				self.n_fcm_completed_this_frame += 1
				self.n_fcm_delivered_failed += 1
		elif result.channel == DeliveryChannel.SIREN and result.status == DeliveryStatus.SUCCESS:
			self.n_siren_triggers += 1

	def add_queue_result(self, channel: DeliveryChannel, status: DeliveryStatus) -> None:
		"""Record non-blocking enqueue outcome for async delivery channels."""

		if channel == DeliveryChannel.BACKEND:
			if status == DeliveryStatus.SUCCESS:
				self.n_backend_queued_ok += 1
			elif status == DeliveryStatus.FAILED:
				self.n_backend_queue_failed += 1
		elif channel == DeliveryChannel.FCM:
			if status == DeliveryStatus.SUCCESS:
				self.n_fcm_queued_ok += 1
			elif status == DeliveryStatus.FAILED:
				self.n_fcm_queue_failed += 1

	def apply_async_delivery_delta(
		self,
		*,
		backend_delta_ok: int,
		backend_delta_failed: int,
		backend_total_ok: int,
		backend_total_failed: int,
		fcm_delta_ok: int,
		fcm_delta_failed: int,
		fcm_total_ok: int,
		fcm_total_failed: int,
	) -> None:
		"""Apply worker delivery delta + cumulative totals for async mode."""

		self.n_backend_completed_this_frame = max(0, backend_delta_ok) + max(
			0, backend_delta_failed
		)
		self.n_fcm_completed_this_frame = max(0, fcm_delta_ok) + max(0, fcm_delta_failed)

		self.n_backend_delivered_ok = backend_total_ok
		self.n_backend_delivered_failed = backend_total_failed
		self.n_fcm_delivered_ok = fcm_total_ok
		self.n_fcm_delivered_failed = fcm_total_failed

	def to_dict(self) -> dict:
		"""Serialize counters to plain dict for metrics logging.

		Args:
			None.

		Returns:
			Dictionary containing frame-level delivery counters.

		Failure Behavior:
			Never raises.
		"""

		return {
			"n_events_emitted": self.n_events_emitted,
			"n_backend_ok": self.n_backend_ok,
			"n_backend_failed": self.n_backend_failed,
			"n_fcm_ok": self.n_fcm_ok,
			"n_fcm_failed": self.n_fcm_failed,
			"n_backend_completed_this_frame": self.n_backend_completed_this_frame,
			"n_fcm_completed_this_frame": self.n_fcm_completed_this_frame,
			"n_backend_queued_ok": self.n_backend_queued_ok,
			"n_backend_queue_failed": self.n_backend_queue_failed,
			"n_fcm_queued_ok": self.n_fcm_queued_ok,
			"n_fcm_queue_failed": self.n_fcm_queue_failed,
			"n_backend_delivered_ok": self.n_backend_delivered_ok,
			"n_backend_delivered_failed": self.n_backend_delivered_failed,
			"n_fcm_delivered_ok": self.n_fcm_delivered_ok,
			"n_fcm_delivered_failed": self.n_fcm_delivered_failed,
			"n_siren_triggers": self.n_siren_triggers,
			"offline_queue_size": self.offline_queue_size,
		}
