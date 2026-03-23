"""Unit tests for notification_service primitives."""
import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
	sys.path.insert(0, str(_EDGE_AI_DIR))

from src.alerts.notification_service import (
	DeliveryChannel,
	DeliveryResult,
	DeliveryStatus,
	FrameDeliveryMetrics,
)


def test_delivery_result_creation() -> None:
	result = DeliveryResult(
		channel=DeliveryChannel.BACKEND,
		status=DeliveryStatus.SUCCESS,
		event_type="fall_detected",
		severity="HIGH",
		camera_id="cam_01",
		error=None,
	)
	assert result.channel == DeliveryChannel.BACKEND
	assert result.status == DeliveryStatus.SUCCESS
	assert result.event_type == "fall_detected"
	assert result.severity == "HIGH"
	assert result.camera_id == "cam_01"
	assert result.error is None


def test_frame_metrics_aggregation_and_to_dict() -> None:
	metrics = FrameDeliveryMetrics(n_events_emitted=2, offline_queue_size=3)
	metrics.add(
		DeliveryResult(
			channel=DeliveryChannel.BACKEND,
			status=DeliveryStatus.SUCCESS,
			event_type="fall",
			severity="HIGH",
			camera_id="cam_01",
		)
	)
	metrics.add(
		DeliveryResult(
			channel=DeliveryChannel.FCM,
			status=DeliveryStatus.FAILED,
			event_type="fall",
			severity="HIGH",
			camera_id="cam_01",
			error="timeout",
		)
	)
	metrics.add_queue_result(DeliveryChannel.BACKEND, DeliveryStatus.SUCCESS)
	metrics.add_queue_result(DeliveryChannel.FCM, DeliveryStatus.FAILED)
	data = metrics.to_dict()
	assert data["n_events_emitted"] == 2
	assert data["n_backend_ok"] == 1
	assert data["n_backend_failed"] == 0
	assert data["n_fcm_ok"] == 0
	assert data["n_fcm_failed"] == 1
	assert data["n_backend_queued_ok"] == 1
	assert data["n_fcm_queue_failed"] == 1
	assert data["offline_queue_size"] == 3


def test_apply_async_delivery_delta_sets_per_frame_deltas_and_cumulative_totals() -> None:
	metrics = FrameDeliveryMetrics()
	metrics.apply_async_delivery_delta(
		backend_delta_ok=4,
		backend_delta_failed=2,
		backend_total_ok=8,
		backend_total_failed=3,
		fcm_delta_ok=3,
		fcm_delta_failed=1,
		fcm_total_ok=7,
		fcm_total_failed=2,
	)
	data = metrics.to_dict()
	assert data["n_backend_ok"] == 0
	assert data["n_backend_failed"] == 0
	assert data["n_fcm_ok"] == 0
	assert data["n_fcm_failed"] == 0
	assert data["n_backend_completed_this_frame"] == 6
	assert data["n_fcm_completed_this_frame"] == 4
	assert data["n_backend_delivered_ok"] == 8
	assert data["n_backend_delivered_failed"] == 3
	assert data["n_fcm_delivered_ok"] == 7
	assert data["n_fcm_delivered_failed"] == 2
