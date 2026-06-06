import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.collision_prediction import CollisionPredictionEngine, RelativeMotionClass
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.models.detection import Detection


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_head_on_motion_has_ttc_and_approaching_class():
    engine = CollisionPredictionEngine()

    result = engine.evaluate(
        forklift_position_m=(0.0, 0.0),
        worker_position_m=(5.0, 0.0),
        forklift_velocity_mps=(1.0, 0.0),
        worker_velocity_mps=(-1.0, 0.0),
        calibration_confidence=1.0,
    )

    assert result.relative_motion_class == RelativeMotionClass.APPROACHING
    assert result.ttc_seconds == 2.5
    assert result.predicted_collision is True


def test_crossing_paths_are_classified_crossing():
    engine = CollisionPredictionEngine()

    result = engine.evaluate(
        forklift_position_m=(0.0, 0.0),
        worker_position_m=(3.0, -3.0),
        forklift_velocity_mps=(1.0, 0.0),
        worker_velocity_mps=(0.0, 1.0),
        calibration_confidence=1.0,
    )

    assert result.relative_motion_class == RelativeMotionClass.CROSSING
    assert result.closest_approach_distance_m == 0.0


def test_parallel_motion_is_not_stationary():
    engine = CollisionPredictionEngine()

    result = engine.evaluate(
        forklift_position_m=(0.0, 0.0),
        worker_position_m=(0.0, 2.0),
        forklift_velocity_mps=(1.0, 0.0),
        worker_velocity_mps=(1.0, 0.0),
        calibration_confidence=1.0,
    )

    assert result.relative_motion_class == RelativeMotionClass.PARALLEL
    assert result.ttc_seconds is None


def test_forklift_moving_away_is_departing():
    engine = CollisionPredictionEngine()

    result = engine.evaluate(
        forklift_position_m=(0.0, 0.0),
        worker_position_m=(5.0, 0.0),
        forklift_velocity_mps=(-1.0, 0.0),
        worker_velocity_mps=(0.0, 0.0),
        calibration_confidence=1.0,
    )

    assert result.relative_motion_class == RelativeMotionClass.DEPARTING
    assert result.closing_speed_mps < 0.0
    assert result.ttc_seconds is None


def test_proximity_event_includes_collision_prediction_metadata():
    analyzer = ProximityAnalyzer()
    worker = _det("person", (250, 100, 290, 150), track_id=7)

    analyzer.analyze(
        [worker, _det("forklift", (100, 100, 200, 160))],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )
    events = analyzer.analyze(
        [worker, _det("forklift", (120, 100, 220, 160))],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=2,
        timestamp=100.1,
    )

    assert len(events) == 1
    assert events[0].metadata["relative_motion_class"] == "APPROACHING"
    assert events[0].metadata["ttc_seconds"] is not None
    assert "closest_approach_distance_m" in events[0].metadata
