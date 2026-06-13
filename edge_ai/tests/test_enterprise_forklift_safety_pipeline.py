import math
import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.event_aggregator import EventAggregator
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.models.detection import Detection
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity


class _ScaledCalibration:
    def __init__(self, scale_m_per_px=0.02, confidence=0.95):
        self.scale = scale_m_per_px
        self.confidence = confidence

    def is_calibrated(self, camera_id: str) -> bool:
        return True

    def get(self, camera_id: str):
        return self

    def pixel_to_ground(self, px: float, py: float):
        return px * self.scale, py * self.scale

    def compute_distance(self, camera_id: str, p1_px, p2_px) -> float:
        p1 = self.pixel_to_ground(*p1_px)
        p2 = self.pixel_to_ground(*p2_px)
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def calibration_confidence(self, camera_id: str) -> float:
        return self.confidence


def _det(class_name: str, bbox, track_id=None, confidence=0.9):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=confidence,
        bbox=bbox,
        track_id=track_id,
    )


def _event(event_type: str, timestamp: float) -> HazardEvent:
    return HazardEvent(
        event_type=event_type,
        severity=Severity.MEDIUM,
        camera_id="cam_01",
        timestamp=timestamp,
        frame_number=1,
        track_id=7,
        bbox=(10, 10, 80, 140),
        description=event_type,
        metadata={},
    )


def test_operator_suppression_blocks_own_forklift_hazard():
    analyzer = ProximityAnalyzer()
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    operator = _det("person", (165, 115, 235, 245), track_id=1)

    events = analyzer.analyze(
        [operator, forklift],
        tracked_pose_people=[operator],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert events == []


def test_motion_aware_pipeline_emits_critical_collision_course_metadata():
    analyzer = ProximityAnalyzer(calibration_mgr=_ScaledCalibration())
    worker = _det("person", (250, 100, 290, 150), track_id=7)

    first = analyzer.analyze(
        [worker, _det("forklift", (100, 100, 200, 160))],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )
    second = analyzer.analyze(
        [worker, _det("forklift", (140, 100, 240, 160))],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=2,
        timestamp=100.2,
    )

    assert [
        event for event in first
        if not event.metadata.get("render_only")
    ] == []
    proximity_events = [
        event for event in second
        if event.event_type == "forklift_proximity"
    ]
    overspeed_events = [
        event for event in second
        if event.event_type == "forklift_overspeed"
    ]
    assert len(proximity_events) >= 1
    assert overspeed_events == []
    event = proximity_events[0]
    assert event.severity == Severity.CRITICAL
    assert event.metadata["proximity_alert_stage"] == "critical"
    assert event.metadata["distance_source"] == "ground_plane"
    assert event.metadata["forklift_speed_mps"] > 0.0
    assert event.metadata["relative_motion_class"] == "APPROACHING"
    assert event.metadata["ttc_seconds"] is not None
    assert event.metadata["predicted_collision"] is True
    assert event.metadata["dynamic_zone_type"] in {"fork_load", "front_danger"}
    assert event.metadata["risk_score"] >= 85.0


def test_far_stationary_pair_does_not_generate_monitor_noise():
    analyzer = ProximityAnalyzer(calibration_mgr=_ScaledCalibration())
    forklift = _det("forklift", (100, 100, 200, 160))
    worker = _det("person", (520, 100, 560, 150), track_id=7)

    events = analyzer.analyze(
        [worker, forklift],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert events == []


def test_new_risk_event_types_remain_compatible_with_event_aggregator():
    aggregator = EventAggregator()
    t0 = 100.0
    event_type = "forklift_proximity_critical"

    assert aggregator.process([_event(event_type, t0)], t0) == []
    emitted = aggregator.process([_event(event_type, t0 + 1.0)], t0 + 1.0)

    assert len(emitted) == 1
    assert emitted[0].event_type == event_type
