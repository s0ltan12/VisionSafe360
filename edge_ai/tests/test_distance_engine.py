import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.distance_engine import DistanceEngine
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.models.detection import Detection


class _FakeCalibration:
    def __init__(self, calibrated=True, confidence=1.0, distance=2.5):
        self._calibrated = calibrated
        self._confidence = confidence
        self._distance = distance

    def is_calibrated(self, camera_id: str) -> bool:
        return self._calibrated

    def compute_distance(self, camera_id: str, p1_px, p2_px) -> float:
        return self._distance

    def calibration_confidence(self, camera_id: str) -> float:
        return self._confidence


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_calibrated_camera_uses_ground_plane_distance():
    engine = DistanceEngine(_FakeCalibration(calibrated=True, confidence=1.0, distance=3.2))

    result = engine.compute(
        camera_id="cam_01",
        worker_bbox=(100, 100, 140, 220),
        forklift_bbox=(200, 100, 320, 260),
    )

    assert result.distance_m == 3.2
    assert result.calibration_confidence == 1.0
    assert result.distance_source == "ground_plane"


def test_uncalibrated_camera_uses_pixel_fallback():
    engine = DistanceEngine(_FakeCalibration(calibrated=False), fallback_meters_per_pixel=0.02)

    result = engine.compute(
        camera_id="cam_01",
        worker_bbox=(100, 100, 140, 220),
        forklift_bbox=(200, 100, 320, 260),
    )

    assert result.distance_px > 0.0
    assert result.distance_m == result.distance_px * 0.02
    assert result.calibration_confidence == 0.0
    assert result.distance_source == "pixel_fallback"


def test_partial_calibration_confidence_is_preserved():
    engine = DistanceEngine(_FakeCalibration(calibrated=True, confidence=0.45, distance=2.0))

    result = engine.compute(
        camera_id="cam_01",
        worker_bbox=(100, 100, 140, 220),
        forklift_bbox=(200, 100, 320, 260),
    )

    assert result.distance_m == 2.0
    assert result.calibration_confidence == 0.45


def test_proximity_event_includes_distance_metadata():
    analyzer = ProximityAnalyzer(
        danger_px=260.0,
        warning_px=320.0,
        calibration_mgr=_FakeCalibration(calibrated=True, confidence=0.9, distance=1.8),
    )
    forklift = _det("forklift", (100, 100, 240, 220))
    worker = _det("person", (260, 130, 320, 250), track_id=7)

    events = analyzer.analyze(
        [worker, forklift],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert len(events) == 1
    assert events[0].metadata["distance_m"] == 1.8
    assert events[0].metadata["calibration_confidence"] == 0.9
    assert events[0].metadata["distance_source"] == "ground_plane"
