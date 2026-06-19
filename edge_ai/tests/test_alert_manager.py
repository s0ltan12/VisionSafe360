"""Unit tests for AlertManager routing behavior."""
import sys
import time
from pathlib import Path
from queue import PriorityQueue
from threading import Event

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
	sys.path.insert(0, str(_EDGE_AI_DIR))

import pytest

from src.alerts.alert_manager import AlertManager, AlertManagerConfig
from src.integration.backend_client import DeliveryResult as BackendDeliveryResult
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity
from src.alerts.notification_service import DeliveryChannel


class _BackendStub:
	def __init__(self, ok: bool = True, gate: Event | None = None) -> None:
		self.ok = ok
		self.calls = 0
		self.gate = gate

	def submit_incident(self, event: HazardEvent) -> BackendDeliveryResult:
		del event
		self.calls += 1
		if self.gate is not None:
			self.gate.wait(timeout=1.0)
		return BackendDeliveryResult.OK if self.ok else BackendDeliveryResult.FAILED

	def offline_queue_size(self) -> int:
		return 0


class _FCMStub:
	def __init__(self, ok: bool = True) -> None:
		self.ok = ok
		self.calls = 0

	def send_event(self, event: HazardEvent) -> bool:
		del event
		self.calls += 1
		return self.ok


class _SirenStub:
	def __init__(self, ok: bool = True) -> None:
		self.ok = ok
		self.calls = 0

	def tick(self) -> None:
		return None

	def trigger(self, event: HazardEvent) -> bool:
		del event
		self.calls += 1
		return self.ok


def _event(severity: Severity) -> HazardEvent:
	return HazardEvent(
		event_type="test_event",
		severity=severity,
		camera_id="cam_01",
		timestamp=100.0,
		frame_number=1,
		track_id=1,
		description="test",
		metadata={},
	)


def _zone_event() -> HazardEvent:
	return HazardEvent(
		event_type="zone_person_in_danger",
		severity=Severity.CRITICAL,
		camera_id="cam_01",
		timestamp=100.0,
		frame_number=1,
		track_id=1,
		description="Worker in danger zone",
		metadata={
			"safety_zone": True,
			"safety_zone_id": "CSZ-1",
			"stable_object_key": "person:1",
		},
	)


def _suppressed_fall_lifecycle_event() -> HazardEvent:
	return HazardEvent(
		event_type="fall_candidate",
		severity=Severity.HIGH,
		camera_id="cam_01",
		timestamp=100.0,
		frame_number=1,
		track_id=1,
		description="candidate",
		metadata={
			"suppress_event": True,
			"internal_lifecycle_event": True,
			"operational_alert": False,
		},
	)


def _wait_until(predicate, timeout_sec: float = 1.0, interval_sec: float = 0.01) -> bool:
	deadline = time.monotonic() + timeout_sec
	while time.monotonic() < deadline:
		if predicate():
			return True
		time.sleep(interval_sec)
	return predicate()


def test_low_routes_to_backend_only() -> None:
	backend = _BackendStub(ok=True)
	fcm = _FCMStub(ok=True)
	siren = _SirenStub(ok=True)

	manager = AlertManager(
		backend_client=backend,
		fcm_service=fcm,
		siren_controller=siren,
		config=AlertManagerConfig(
			alerts_enabled=True,
			medium_fcm_enabled=True,
			async_delivery_enabled=False,
		),
	)

	metrics = manager.process_events([_event(Severity.LOW)])
	assert backend.calls == 1
	assert fcm.calls == 0
	assert siren.calls == 0
	assert metrics["n_backend_ok"] == 1
	assert metrics["n_fcm_ok"] == 0
	assert metrics["n_siren_triggers"] == 0


def test_suppressed_fall_lifecycle_event_routes_to_no_channels() -> None:
	backend = _BackendStub(ok=True)
	fcm = _FCMStub(ok=True)
	siren = _SirenStub(ok=True)

	manager = AlertManager(
		backend_client=backend,
		fcm_service=fcm,
		siren_controller=siren,
		config=AlertManagerConfig(
			alerts_enabled=True,
			medium_fcm_enabled=True,
			async_delivery_enabled=False,
		),
	)

	metrics = manager.process_events([_suppressed_fall_lifecycle_event()])

	assert backend.calls == 0
	assert fcm.calls == 0
	assert siren.calls == 0
	assert metrics["n_backend_ok"] == 0
	assert metrics["n_fcm_ok"] == 0
	assert metrics["n_siren_triggers"] == 0


def test_critical_routes_to_all_channels() -> None:
	backend = _BackendStub(ok=True)
	fcm = _FCMStub(ok=True)
	siren = _SirenStub(ok=True)

	manager = AlertManager(
		backend_client=backend,
		fcm_service=fcm,
		siren_controller=siren,
		config=AlertManagerConfig(async_delivery_enabled=False),
	)

	metrics = manager.process_events([_event(Severity.CRITICAL)])
	assert backend.calls == 1
	assert fcm.calls == 1
	assert siren.calls == 1
	assert metrics["n_backend_ok"] == 1
	assert metrics["n_fcm_ok"] == 1
	assert metrics["n_siren_triggers"] == 1


def test_fcm_failure_does_not_block_backend() -> None:
	backend = _BackendStub(ok=True)
	fcm = _FCMStub(ok=False)
	siren = _SirenStub(ok=True)

	manager = AlertManager(
		backend_client=backend,
		fcm_service=fcm,
		siren_controller=siren,
		config=AlertManagerConfig(async_delivery_enabled=False),
	)

	metrics = manager.process_events([_event(Severity.HIGH)])
	assert backend.calls == 1
	assert fcm.calls == 1
	assert metrics["n_backend_ok"] == 1
	assert metrics["n_fcm_failed"] == 1


def test_async_enqueue_and_worker_delivery_success() -> None:
	backend_gate = Event()
	backend = _BackendStub(ok=True, gate=backend_gate)
	fcm = _FCMStub(ok=True)
	siren = _SirenStub(ok=True)
	manager = AlertManager(
		backend_client=backend,
		fcm_service=fcm,
		siren_controller=siren,
		config=AlertManagerConfig(
			alerts_enabled=True,
			medium_fcm_enabled=True,
			async_delivery_enabled=True,
			async_queue_maxsize=8,
			async_poll_timeout_sec=0.01,
		),
	)
	try:
		initial = manager.process_events([_event(Severity.HIGH)])
		assert initial["n_backend_queued_ok"] == 1
		assert initial["n_fcm_queued_ok"] == 1
		assert initial["n_backend_ok"] == 0
		assert initial["n_fcm_ok"] == 0
		assert initial["n_backend_completed_this_frame"] == 0
		assert initial["n_fcm_completed_this_frame"] == 0
		assert initial["n_backend_delivered_ok"] == 0
		assert initial["n_fcm_delivered_ok"] == 0

		backend_gate.set()
		assert _wait_until(lambda: backend.calls >= 1 and fcm.calls >= 1)

		delivered = manager.process_events([])
		assert delivered["n_backend_ok"] == 0
		assert delivered["n_fcm_ok"] == 0
		assert delivered["n_backend_completed_this_frame"] == 1
		assert delivered["n_fcm_completed_this_frame"] == 1
		assert delivered["n_backend_delivered_ok"] == 1
		assert delivered["n_fcm_delivered_ok"] == 1

		total = manager.get_async_delivery_counters()
		assert total["backend_ok"] == 1
		assert total["backend_failed"] == 0
		assert total["fcm_ok"] == 1
		assert total["fcm_failed"] == 0
	finally:
		manager.shutdown(timeout_sec=1.0)
		assert manager._worker is None or not manager._worker.is_alive()


def test_async_worker_delivery_failure_metrics() -> None:
	backend_gate = Event()
	backend = _BackendStub(ok=False, gate=backend_gate)
	fcm = _FCMStub(ok=False)
	manager = AlertManager(
		backend_client=backend,
		fcm_service=fcm,
		siren_controller=_SirenStub(ok=True),
		config=AlertManagerConfig(
			async_delivery_enabled=True,
			async_queue_maxsize=8,
			async_poll_timeout_sec=0.01,
		),
	)
	try:
		initial = manager.process_events([_event(Severity.HIGH)])
		assert initial["n_backend_queued_ok"] == 1
		assert initial["n_fcm_queued_ok"] == 1
		assert initial["n_backend_failed"] == 0
		assert initial["n_fcm_failed"] == 0

		backend_gate.set()
		assert _wait_until(lambda: backend.calls >= 1 and fcm.calls >= 1)

		delivered = manager.process_events([])
		assert delivered["n_backend_failed"] == 0
		assert delivered["n_fcm_failed"] == 0
		assert delivered["n_backend_completed_this_frame"] == 1
		assert delivered["n_fcm_completed_this_frame"] == 1
		assert delivered["n_backend_delivered_failed"] == 1
		assert delivered["n_fcm_delivered_failed"] == 1
	finally:
		manager.shutdown(timeout_sec=1.0)


def test_async_queue_overflow_reports_queue_failure(monkeypatch: pytest.MonkeyPatch) -> None:
	backend_gate = Event()
	backend = _BackendStub(ok=True, gate=backend_gate)
	manager = AlertManager(
		backend_client=backend,
		fcm_service=_FCMStub(ok=True),
		siren_controller=_SirenStub(ok=True),
		config=AlertManagerConfig(
			async_delivery_enabled=True,
			async_queue_maxsize=1,
			async_poll_timeout_sec=0.01,
		),
	)
	try:
		assert manager._queue is not None
		original_put_nowait = manager._queue.put_nowait
		call_count = {"n": 0}

		def _controlled_put_nowait(item) -> None:
			call_count["n"] += 1
			if call_count["n"] >= 2:
				raise Full
			original_put_nowait(item)

		from queue import Full

		monkeypatch.setattr(manager._queue, "put_nowait", _controlled_put_nowait)
		metrics = manager.process_events([_event(Severity.LOW), _event(Severity.LOW)])
		assert metrics["n_backend_queued_ok"] == 1
		assert metrics["n_backend_queue_failed"] == 1
		assert metrics["n_backend_ok"] == 0

		backend_gate.set()
		assert _wait_until(lambda: manager.get_async_delivery_counters()["backend_ok"] >= 1)

		after = manager.process_events([])
		assert after["n_backend_ok"] == 0
		assert after["n_backend_completed_this_frame"] == 1
	finally:
		manager.shutdown(timeout_sec=1.0)


def test_async_shutdown_stops_worker_gracefully() -> None:
	backend = _BackendStub(ok=True)
	manager = AlertManager(
		backend_client=backend,
		fcm_service=_FCMStub(ok=True),
		siren_controller=_SirenStub(ok=True),
		config=AlertManagerConfig(
			async_delivery_enabled=True,
			async_queue_maxsize=8,
			async_poll_timeout_sec=0.01,
		),
	)
	manager.process_events([_event(Severity.LOW)])
	assert _wait_until(lambda: backend.calls >= 1)
	manager.shutdown(timeout_sec=1.0)
	assert manager._worker is None or not manager._worker.is_alive()


def test_priority_task_orders_critical_before_low() -> None:
	manager = AlertManager(
		backend_client=_BackendStub(ok=True),
		config=AlertManagerConfig(async_delivery_enabled=False),
	)
	low = manager._prioritized_task(DeliveryChannel.BACKEND, _event(Severity.LOW))
	critical = manager._prioritized_task(DeliveryChannel.BACKEND, _event(Severity.CRITICAL))

	assert sorted([low, critical])[0].task.event.severity == Severity.CRITICAL


def test_priority_task_preserves_fifo_within_same_severity() -> None:
	manager = AlertManager(
		backend_client=_BackendStub(ok=True),
		config=AlertManagerConfig(async_delivery_enabled=False),
	)
	first_event = _event(Severity.HIGH)
	second_event = _event(Severity.HIGH)
	second_event.frame_number = 2

	first = manager._prioritized_task(DeliveryChannel.BACKEND, first_event)
	second = manager._prioritized_task(DeliveryChannel.BACKEND, second_event)

	ordered = sorted([second, first])
	assert [item.task.event.frame_number for item in ordered] == [1, 2]


def test_full_priority_queue_evicts_low_for_critical() -> None:
	manager = AlertManager(
		backend_client=_BackendStub(ok=True),
		config=AlertManagerConfig(async_delivery_enabled=False),
	)
	manager._queue = PriorityQueue(maxsize=1)

	low = _event(Severity.LOW)
	critical = _event(Severity.CRITICAL)
	critical.frame_number = 99

	queued_low, evicted_low = manager._enqueue_delivery_task(DeliveryChannel.BACKEND, low)
	queued_critical, evicted_critical = manager._enqueue_delivery_task(DeliveryChannel.BACKEND, critical)

	assert queued_low is True
	assert evicted_low is None
	assert queued_critical is True
	assert evicted_critical is low
	assert manager._queue.get_nowait().task.event is critical


def test_full_priority_queue_does_not_evict_same_severity_fifo() -> None:
	manager = AlertManager(
		backend_client=_BackendStub(ok=True),
		config=AlertManagerConfig(async_delivery_enabled=False),
	)
	manager._queue = PriorityQueue(maxsize=1)

	first = _event(Severity.HIGH)
	second = _event(Severity.HIGH)
	second.frame_number = 2

	assert manager._enqueue_delivery_task(DeliveryChannel.BACKEND, first) == (True, None)
	assert manager._enqueue_delivery_task(DeliveryChannel.BACKEND, second) == (False, None)
	assert manager._queue.get_nowait().task.event is first


def test_clip_failure_still_routes_zone_event_to_backend() -> None:
	backend = _BackendStub(ok=True)
	manager = AlertManager(
		backend_client=backend,
		fcm_service=None,
		siren_controller=_SirenStub(ok=True),
		config=AlertManagerConfig(async_delivery_enabled=False),
	)

	event = _zone_event()
	manager._route_clip_fallback(event, reason="no_frames")

	assert backend.calls == 1
	assert event.metadata["video_clip_fallback_reason"] == "no_frames"
