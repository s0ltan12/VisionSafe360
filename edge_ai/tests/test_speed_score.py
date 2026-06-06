import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.collision_prediction import RelativeMotionClass
from src.analysis.dynamic_zone_engine import ZoneType
from src.analysis.risk_engine import RiskEngine


def test_speed_score_cap_at_25():
    engine = RiskEngine()

    score = engine._speed_score(
        forklift_speed_mps=100.0,
        worker_speed_mps=0.0,
        distance_m=1.0,
    )

    assert score == 25.0


def test_speed_score_distance_multiplier():
    engine = RiskEngine()

    near = engine._speed_score(1.0, 0.0, distance_m=1.0)
    far = engine._speed_score(1.0, 0.0, distance_m=5.0)

    assert near > far


def test_stationary_minimum_monitor():
    result = RiskEngine().evaluate(
        distance_m=4.0,
        danger_radius_m=1.0,
        warning_radius_m=2.0,
        forklift_speed_mps=0.0,
        worker_speed_mps=0.0,
        ttc_seconds=None,
        closest_approach_distance_m=4.0,
        relative_motion_class=RelativeMotionClass.STATIONARY,
        zone_type=ZoneType.CLEAR,
        persistence_sec=0.0,
        detection_confidence=0.9,
        tracking_confidence=0.9,
        calibration_confidence=1.0,
        predicted_collision=False,
        driver_suppressed=False,
    )

    assert result.risk_score >= result.components["proximity_floor_minimum_monitor"]
    assert result.risk_score >= RiskEngine().config.monitor_threshold
