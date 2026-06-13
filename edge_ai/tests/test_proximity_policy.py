import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.analysis.proximity_policy import DynamicProximityPolicy, ProximityLevel
from src.models.detection import Detection


class _FakeCalibration:
    def __init__(self, distance):
        self.distance = distance

    def is_calibrated(self, camera_id: str) -> bool:
        return True

    def compute_distance(self, camera_id: str, p1_px, p2_px) -> float:
        return self.distance

    def calibration_confidence(self, camera_id: str) -> float:
        return 1.0


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_stationary_forklift_uses_base_warning_radius():
    policy = DynamicProximityPolicy()

    result = policy.evaluate(distance_m=1.5, speed_mps=0.0, calibration_confidence=1.0)

    assert result.level == ProximityLevel.WARNING
    assert result.danger_radius_m == 1.0
    assert result.warning_radius_m == 2.0


def test_slow_forklift_expands_warning_radius():
    policy = DynamicProximityPolicy()

    result = policy.evaluate(distance_m=2.2, speed_mps=0.2, calibration_confidence=1.0)

    assert result.level == ProximityLevel.WARNING
    assert result.warning_radius_m > 2.0


def test_fast_forklift_expands_danger_radius():
    policy = DynamicProximityPolicy()

    result = policy.evaluate(distance_m=2.4, speed_mps=2.0, calibration_confidence=1.0)

    assert result.level == ProximityLevel.DANGER
    assert result.danger_radius_m >= 2.6


def test_proximity_analyzer_uses_meter_policy_not_legacy_pixel_threshold():
    analyzer = ProximityAnalyzer(
        danger_px=999.0,
        warning_px=1000.0,
        calibration_mgr=_FakeCalibration(distance=3.0),
    )
    forklift = _det("forklift", (100, 100, 240, 220))
    worker = _det("person", (245, 110, 285, 230), track_id=7)

    events = analyzer.analyze(
        [worker, forklift],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert [
        event for event in events
        if not event.metadata.get("render_only")
    ] == []
