"""Regression tests for static safety-zone event delivery."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.models.detection import Detection
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity
from src.pipeline import frame_processor as frame_processor_module
from src.pipeline.frame_processor import FrameProcessor


class _EngineStub:
    def run_pose_tracker(self, bundle):
        del bundle
        return (
            None,
            [
                Detection(
                    class_id=0,
                    class_name="person",
                    confidence=0.95,
                    bbox=(140, 120, 180, 180),
                    track_id=7,
                )
            ],
            0.0,
        )

    def vram_used_mb(self):
        return 0


class _PPEEngineStub:
    def run_pose_tracker(self, bundle):
        del bundle
        return (
            None,
            [
                Detection(
                    class_id=0,
                    class_name="person",
                    confidence=0.95,
                    bbox=(140, 120, 180, 180),
                    track_id=7,
                )
            ],
            0.0,
        )

    def run_ppe(self, bundle):
        del bundle
        return [
            Detection(
                class_id=2,
                class_name="helmet_off",
                confidence=0.95,
                bbox=(145, 120, 175, 150),
                track_id=None,
            )
        ], 0.0

    def vram_used_mb(self):
        return 0


class _BackendClientStub:
    def fetch_safety_zones(self, camera_id):
        assert camera_id == "CAM-01"
        return {
            "zones": [
                {
                    "id": "CSZ-1",
                    "name": "Danger Zone",
                    "zone_type": "danger",
                    "polygon": [
                        {"x": 100, "y": 100},
                        {"x": 300, "y": 100},
                        {"x": 300, "y": 300},
                        {"x": 100, "y": 300},
                    ],
                    "source_width": 640,
                    "source_height": 480,
                    "enabled": True,
                    "rules": {"severity": "Critical", "cooldown_sec": 0},
                }
            ]
        }

    def offline_queue_size(self):
        return 0


class _PPEBackendClientStub:
    def __init__(self, zones):
        self._zones = zones

    def fetch_safety_zones(self, camera_id):
        assert camera_id == "CAM-01"
        return {"zones": self._zones}

    def offline_queue_size(self):
        return 0


class _HazardAnalyzerStub:
    def analyze(self, detections, *, camera_id, frame_number, timestamp, fall_this_frame, pose_results):
        del detections, fall_this_frame, pose_results
        return [
            HazardEvent(
                event_type="fall_confirmed",
                severity=Severity.CRITICAL,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=99,
                description="fall",
                metadata={},
            )
        ]


class _EventAggregatorStub:
    def __init__(self):
        self.received = []

    def process(self, events, timestamp):
        del timestamp
        self.received = list(events)
        return list(events)


class _NoopSmoother:
    def smooth(self, detections):
        return detections


class _NoopTrackMonitor:
    def update(self, detections, timestamp):
        del detections, timestamp
        return {"track_coverage": 1.0}

    def remap_detections_display_ids(self, detections):
        del detections
        return {}


class _NoopRenderer:
    def __init__(self):
        self.last_kwargs = None

    def render(self, *args, **kwargs):
        del args
        self.last_kwargs = kwargs


class _NoopMetrics:
    def log_frame(self, **kwargs):
        del kwargs


def _ctx(event_aggregator):
    renderer = _NoopRenderer()
    return SimpleNamespace(
        stream=SimpleNamespace(camera_id="CAM-01", input_fps=20, dropped_count=0),
        engine=_EngineStub(),
        metrics=_NoopMetrics(),
        event_aggregator=event_aggregator,
        calibration_mgr=None,
        track_monitor=_NoopTrackMonitor(),
        det_smoother=_NoopSmoother(),
        forklift_smoother=None,
        hazard_analyzer=_HazardAnalyzerStub(),
        posture_analyzer=None,
        proximity_analyzer=None,
        ppe_analyzer=None,
        ppe_enabled=False,
        person_tracker_source="pose",
        backend_client=_BackendClientStub(),
        camera_name="Camera 1",
        worker_id=None,
        worker_gpu_id=None,
        alert_manager=None,
        frame_ring_buffer=None,
        siren_controller=None,
        renderer=renderer,
        is_calibrated=False,
        fall_every_n=1,
        ergo_every_n=10,
        proximity_every_n=1,
        ppe_every_n=1,
        show=False,
        headless=True,
        win_name="",
        writer=None,
        out_path=None,
        frame_publisher=None,
        frame_counter=0,
        frames_processed=0,
        fps_t0=100.0,
        inference_fps=0.0,
        last_offline_flush=0.0,
        offline_flush_in_progress=False,
        offline_flush_thread=None,
        cumulative_forklift_dets=0,
        sample_forklift_lines=[],
        sample_hazard_lines=[],
        ppe_capable=False,
        last_ppe_detections=[],
    )


def _ppe_ctx(event_aggregator, zones):
    ctx = _ctx(event_aggregator)
    ctx.engine = _PPEEngineStub()
    ctx.hazard_analyzer = None
    ctx.ppe_analyzer = object()
    ctx.ppe_enabled = True
    ctx.ppe_capable = True
    ctx.backend_client = _PPEBackendClientStub(zones)
    return ctx


def test_frame_processor_preserves_zone_events_when_hazard_analyzer_runs(monkeypatch):
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_ENABLED", True)
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_REFRESH_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(frame_processor_module, "ALERTS_ENABLED", False)
    monkeypatch.setattr(frame_processor_module, "BACKEND_EVENTS_ENABLED", False)

    aggregator = _EventAggregatorStub()
    processor = FrameProcessor(_ctx(aggregator))
    bundle = SimpleNamespace(
        frame=np.zeros((480, 640, 3), dtype=np.uint8),
        frame_number=1,
    )

    processor.process(bundle)

    event_types = [event.event_type for event in aggregator.received]
    assert "zone_person_in_danger" in event_types
    assert "fall_confirmed" in event_types


def test_frame_processor_passes_safety_zones_to_renderer(monkeypatch):
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_ENABLED", True)
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_REFRESH_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(frame_processor_module, "ALERTS_ENABLED", False)
    monkeypatch.setattr(frame_processor_module, "BACKEND_EVENTS_ENABLED", False)

    aggregator = _EventAggregatorStub()
    ctx = _ctx(aggregator)
    processor = FrameProcessor(ctx)
    bundle = SimpleNamespace(
        frame=np.zeros((480, 640, 3), dtype=np.uint8),
        frame_number=1,
    )

    processor.process(bundle)

    rendered_zones = ctx.renderer.last_kwargs["zones"]
    assert rendered_zones == [
        {
            "id": "CSZ-1",
            "name": "Danger Zone",
            "type": "danger",
            "points": [(100, 100), (300, 100), (300, 300), (100, 300)],
        }
    ]


def test_frame_processor_marks_evidence_zone_overlay_when_rendered(monkeypatch):
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_ENABLED", True)
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_REFRESH_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(frame_processor_module, "ALERTS_ENABLED", False)
    monkeypatch.setattr(frame_processor_module, "BACKEND_EVENTS_ENABLED", False)

    aggregator = _EventAggregatorStub()
    ctx = _ctx(aggregator)
    ctx.renderer.cfg = SimpleNamespace(enable_zones=True)
    processor = FrameProcessor(ctx)
    bundle = SimpleNamespace(
        frame=np.zeros((480, 640, 3), dtype=np.uint8),
        frame_number=1,
    )

    processor.process(bundle)

    zone_events = [event for event in aggregator.received if event.event_type == "zone_person_in_danger"]
    assert zone_events
    assert zone_events[0].metadata["evidence_has_safety_zone_overlay"] is True


def test_frame_processor_suppresses_ppe_alerts_without_ppe_zone(monkeypatch):
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_ENABLED", True)
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_REFRESH_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(frame_processor_module, "ALERTS_ENABLED", False)
    monkeypatch.setattr(frame_processor_module, "BACKEND_EVENTS_ENABLED", False)

    aggregator = _EventAggregatorStub()
    processor = FrameProcessor(_ppe_ctx(aggregator, []))
    bundle = SimpleNamespace(frame=np.zeros((480, 640, 3), dtype=np.uint8), frame_number=1)

    processor.process(bundle)

    assert not any(event.event_type == "ppe_missing" for event in aggregator.received)


def test_frame_processor_emits_ppe_alert_inside_ppe_zone(monkeypatch):
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_ENABLED", True)
    monkeypatch.setattr(frame_processor_module, "SAFETY_ZONES_REFRESH_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(frame_processor_module, "ALERTS_ENABLED", False)
    monkeypatch.setattr(frame_processor_module, "BACKEND_EVENTS_ENABLED", False)

    zones = [
        {
            "id": "PPE-1",
            "name": "Helmet Area",
            "zone_type": "ppe_required",
            "polygon": [
                {"x": 100, "y": 100},
                {"x": 220, "y": 100},
                {"x": 220, "y": 230},
                {"x": 100, "y": 230},
            ],
            "source_width": 640,
            "source_height": 480,
            "enabled": True,
            "rules": {"required_ppe": ["helmet"], "cooldown_sec": 0},
        }
    ]
    aggregator = _EventAggregatorStub()
    processor = FrameProcessor(_ppe_ctx(aggregator, zones))
    bundle = SimpleNamespace(frame=np.zeros((480, 640, 3), dtype=np.uint8), frame_number=1)

    processor.process(bundle)

    ppe_events = [event for event in aggregator.received if event.event_type == "ppe_missing"]
    assert len(ppe_events) == 1
    assert ppe_events[0].metadata["missing_ppe_items"] == ["helmet"]
    assert ppe_events[0].metadata["safety_zone_id"] == "PPE-1"
