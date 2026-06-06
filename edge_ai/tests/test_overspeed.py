import sys
import math
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.analysis.risk_engine import RiskEngine, ZoneFlags
from src.config.settings import EventTypes
from src.models.detection import Detection
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity
from src.pipeline.frame_processor import _safety_overlay_events


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


def test_overspeed_general_zone_warning():
    result = RiskEngine().check_overspeed(
        forklift_speed_mps=2.5,
        distance_m=10.0,
        zone_flags=ZoneFlags(),
    )

    assert result is not None
    assert result.severity == "warning"
    assert result.context == "general"


def test_overspeed_pedestrian_zone_danger():
    result = RiskEngine().check_overspeed(
        forklift_speed_mps=2.0,
        distance_m=3.0,
        zone_flags=ZoneFlags(),
    )

    assert result is not None
    assert result.severity == "danger"
    assert result.context == "pedestrian_zone"


def test_overspeed_critical():
    result = RiskEngine().check_overspeed(
        forklift_speed_mps=5.0,
        distance_m=2.0,
        zone_flags=ZoneFlags(),
    )

    assert result is not None
    assert result.severity == "critical"


def test_no_overspeed_safe_speed():
    result = RiskEngine().check_overspeed(
        forklift_speed_mps=1.0,
        distance_m=10.0,
        zone_flags=ZoneFlags(),
    )

    assert result is None


def test_overspeed_emits_safety_event():
    analyzer = ProximityAnalyzer()
    overspeed = RiskEngine().check_overspeed(
        forklift_speed_mps=5.0,
        distance_m=2.0,
        zone_flags=ZoneFlags(),
    )

    forklift = Detection(
        class_id=5,
        class_name="forklift",
        confidence=0.9,
        bbox=(100, 100, 220, 200),
        track_id=42,
    )

    event = analyzer._emit_overspeed_event(overspeed, camera_id="cam_01", forklift=forklift)

    assert event.event_type == EventTypes.FORKLIFT_OVERSPEED
    assert event.severity == Severity.CRITICAL
    assert event.metadata["speed_mps"] == 5.0
    assert event.metadata["forklift_speed_mps"] == 5.0
    assert event.metadata["forklift_track_id"] == 42
    assert event.metadata["overspeed_context"] == "pedestrian_zone"


def test_overspeed_no_worker_detected():
    result = RiskEngine().check_overspeed(
        forklift_speed_mps=5.0,
        distance_m=None,
        zone_flags=ZoneFlags(),
    )

    assert result is not None
    assert result.context == "general"
    assert result.severity == "critical"


def test_live_overlay_keeps_forklift_telemetry_without_raw_ppe_alerts():
    emitted = [
        HazardEvent(
            event_type="forklift_telemetry",
            severity=Severity.LOW,
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=42,
            metadata={"forklift_track_id": 42, "speed_mps": 1.2},
        ),
        HazardEvent(
            event_type="ppe_missing_helmet",
            severity=Severity.HIGH,
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=7,
            metadata={},
        )
    ]
    raw = [
        HazardEvent(
            event_type="forklift_proximity",
            severity=Severity.LOW,
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=7,
            metadata={
                "forklift_track_id": 42,
                "worker_track_id": 7,
                "distance_m": 3.2,
                "render_only": True,
                "suppress_event": True,
            },
        ),
        HazardEvent(
            event_type="forklift_overspeed",
            severity=Severity.HIGH,
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=42,
            metadata={"forklift_track_id": 42, "forklift_speed_mps": 3.0},
        ),
        HazardEvent(
            event_type="forklift_distance_telemetry",
            severity=Severity.LOW,
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=7,
            metadata={
                "forklift_track_id": 42,
                "worker_track_id": 7,
                "distance_m": 3.2,
                "render_only": True,
                "suppress_event": True,
            },
        ),
        HazardEvent(
            event_type="ppe_missing_helmet",
            severity=Severity.HIGH,
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=8,
            metadata={},
        ),
    ]

    overlay = _safety_overlay_events(emitted, raw)

    assert [event.event_type for event in overlay].count("ppe_missing_helmet") == 1
    assert any(event.event_type == "forklift_proximity" for event in overlay)
    assert any(event.event_type == "forklift_overspeed" for event in overlay)
    assert any(event.event_type == "forklift_telemetry" for event in overlay)
    assert any(event.event_type == "forklift_distance_telemetry" for event in overlay)


def test_distance_telemetry_event_is_render_only():
    analyzer = ProximityAnalyzer()
    events = analyzer.distance_telemetry_events(
        [
            Detection(
                class_id=0,
                class_name="person",
                confidence=0.9,
                bbox=(100, 100, 140, 220),
                track_id=7,
            ),
            Detection(
                class_id=5,
                class_name="forklift",
                confidence=0.95,
                bbox=(220, 100, 340, 230),
                track_id=42,
            ),
        ],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "forklift_distance_telemetry"
    assert event.metadata["render_only"] is True
    assert event.metadata["suppress_event"] is True
    assert event.metadata["forklift_track_id"] == 42
    assert event.metadata["worker_track_id"] == 7
    assert event.metadata["distance_m"] > 0


def test_stationary_jitter_does_not_emit_overspeed():
    for jitter_px in (0, 5, 10, 15, 20, 30):
        analyzer = ProximityAnalyzer(calibration_mgr=_ScaledCalibration())
        emitted = []
        for frame in range(80):
            offset = jitter_px if frame % 2 else 0
            forklift = _det(
                "forklift",
                (100 + offset, 100, 200 + offset, 160),
                track_id=101,
            )
            worker = _det(
                "person",
                (360, 100, 400, 150),
                track_id=7,
            )
            emitted.extend(
                analyzer.analyze(
                    [worker, forklift],
                    tracked_pose_people=[worker],
                    camera_id="cam_01",
                    frame_number=frame,
                    timestamp=frame * 0.2,
                )
            )

        assert [
            event for event in emitted
            if event.event_type == EventTypes.FORKLIFT_OVERSPEED
        ] == []


def test_single_frame_track_jump_does_not_emit_overspeed():
    analyzer = ProximityAnalyzer(calibration_mgr=_ScaledCalibration())
    emitted = []
    for frame in range(25):
        x = 450 if frame == 16 else 100
        forklift = _det("forklift", (x, 100, x + 100, 160), track_id=101)
        worker = _det("person", (360, 100, 400, 150), track_id=7)
        emitted.extend(
            analyzer.analyze(
                [worker, forklift],
                tracked_pose_people=[worker],
                camera_id="cam_01",
                frame_number=frame,
                timestamp=frame * 0.2,
            )
        )

    assert [
        event for event in emitted
        if event.event_type == EventTypes.FORKLIFT_OVERSPEED
    ] == []


def test_stable_calibrated_motion_emits_overspeed_after_confirmation():
    analyzer = ProximityAnalyzer(calibration_mgr=_ScaledCalibration())
    emitted = []
    for frame in range(35):
        x = 100 + frame * 20
        forklift = _det("forklift", (x, 100, x + 100, 160), track_id=101)
        worker = _det("person", (x + 270, 100, x + 310, 150), track_id=7)
        emitted.extend(
            analyzer.analyze(
                [worker, forklift],
                tracked_pose_people=[worker],
                camera_id="cam_01",
                frame_number=frame,
                timestamp=frame * 0.2,
            )
        )

    overspeed_events = [
        event for event in emitted
        if event.event_type == EventTypes.FORKLIFT_OVERSPEED
    ]

    assert len(overspeed_events) >= 1
    event = overspeed_events[0]
    assert event.severity == Severity.HIGH
    assert event.metadata["overspeed_severity"] == "danger"
    assert event.metadata["speed_source"] == "ground_plane"
    assert event.metadata["speed_confidence"] >= 0.6
    assert event.metadata["track_age_seconds"] >= 3.0
    assert event.metadata["raw_speed_mps"] > 0.0
    assert event.metadata["smoothed_speed_mps"] > 0.0
