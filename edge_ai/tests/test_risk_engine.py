import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.collision_prediction import RelativeMotionClass
from src.analysis.dynamic_zone_engine import ZoneType
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.analysis.risk_engine import RiskEngine, RiskLevel
from src.models.detection import Detection


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_low_risk_scores_monitor():
    engine = RiskEngine()

    result = engine.evaluate(
        distance_m=5.0,
        danger_radius_m=1.0,
        warning_radius_m=2.0,
        forklift_speed_mps=0.0,
        worker_speed_mps=0.0,
        ttc_seconds=None,
        closest_approach_distance_m=5.0,
        relative_motion_class=RelativeMotionClass.STATIONARY,
        zone_type=ZoneType.CLEAR,
        persistence_sec=0.0,
        detection_confidence=1.0,
        tracking_confidence=1.0,
        calibration_confidence=1.0,
        predicted_collision=False,
        driver_suppressed=False,
    )

    assert result.risk_level == RiskLevel.MONITOR
    assert result.risk_score < 45.0


def test_medium_risk_scores_warning():
    engine = RiskEngine()

    result = engine.evaluate(
        distance_m=1.8,
        danger_radius_m=1.0,
        warning_radius_m=2.0,
        forklift_speed_mps=0.2,
        worker_speed_mps=0.0,
        ttc_seconds=5.0,
        closest_approach_distance_m=1.0,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        zone_type=ZoneType.FRONT_DANGER,
        persistence_sec=1.0,
        detection_confidence=0.9,
        tracking_confidence=0.9,
        calibration_confidence=1.0,
        predicted_collision=False,
        driver_suppressed=False,
    )

    assert result.risk_level == RiskLevel.DANGER
    assert 65.0 <= result.risk_score < 85.0


def test_high_risk_scores_danger():
    engine = RiskEngine()

    result = engine.evaluate(
        distance_m=0.8,
        danger_radius_m=1.2,
        warning_radius_m=2.5,
        forklift_speed_mps=1.0,
        worker_speed_mps=0.0,
        ttc_seconds=2.0,
        closest_approach_distance_m=0.7,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        zone_type=ZoneType.FORK_LOAD,
        persistence_sec=1.0,
        detection_confidence=0.9,
        tracking_confidence=1.0,
        calibration_confidence=1.0,
        predicted_collision=False,
        driver_suppressed=False,
    )

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0


def test_critical_collision_course_scores_critical():
    engine = RiskEngine()

    result = engine.evaluate(
        distance_m=0.4,
        danger_radius_m=1.2,
        warning_radius_m=2.5,
        forklift_speed_mps=2.0,
        worker_speed_mps=0.5,
        ttc_seconds=1.0,
        closest_approach_distance_m=0.1,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        zone_type=ZoneType.FOOTPRINT,
        persistence_sec=2.0,
        detection_confidence=1.0,
        tracking_confidence=1.0,
        calibration_confidence=1.0,
        predicted_collision=True,
        driver_suppressed=False,
    )

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0


def test_driver_suppression_hard_gates_risk():
    engine = RiskEngine()

    result = engine.evaluate(
        distance_m=0.2,
        danger_radius_m=2.0,
        warning_radius_m=4.0,
        forklift_speed_mps=2.0,
        worker_speed_mps=1.0,
        ttc_seconds=0.5,
        closest_approach_distance_m=0.0,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        zone_type=ZoneType.FOOTPRINT,
        persistence_sec=5.0,
        detection_confidence=1.0,
        tracking_confidence=1.0,
        calibration_confidence=1.0,
        predicted_collision=True,
        driver_suppressed=True,
    )

    assert result.risk_score == 0.0
    assert result.risk_level == RiskLevel.MONITOR
    assert result.driver_gated is True


def _risk(
    *,
    distance_m: float,
    zone_type: ZoneType = ZoneType.CLEAR,
    forklift_speed_mps: float = 0.0,
    ttc_seconds: float | None = None,
    closest_approach_distance_m: float = 5.0,
    relative_motion_class: RelativeMotionClass = RelativeMotionClass.STATIONARY,
    predicted_collision: bool = False,
    calibration_confidence: float = 1.0,
    driver_suppressed: bool = False,
):
    return RiskEngine().evaluate(
        distance_m=distance_m,
        danger_radius_m=1.0,
        warning_radius_m=2.0,
        forklift_speed_mps=forklift_speed_mps,
        worker_speed_mps=0.0,
        ttc_seconds=ttc_seconds,
        closest_approach_distance_m=closest_approach_distance_m,
        relative_motion_class=relative_motion_class,
        zone_type=zone_type,
        persistence_sec=2.0,
        detection_confidence=0.9,
        tracking_confidence=1.0,
        calibration_confidence=calibration_confidence,
        predicted_collision=predicted_collision,
        driver_suppressed=driver_suppressed,
    )


def test_two_meter_stationary_forklift_floors_to_danger():
    result = _risk(distance_m=2.0)

    assert result.risk_level in {RiskLevel.DANGER, RiskLevel.CRITICAL}
    assert result.risk_score >= 65.0


def test_one_meter_stationary_hazard_zone_floors_to_critical():
    result = _risk(distance_m=0.99, zone_type=ZoneType.FRONT_DANGER)

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0


def test_half_meter_stationary_footprint_floors_to_critical():
    result = _risk(distance_m=0.49, zone_type=ZoneType.FOOTPRINT)

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0


def test_predicted_collision_ttc_two_seconds_floors_to_critical():
    result = _risk(
        distance_m=3.0,
        zone_type=ZoneType.FRONT_DANGER,
        forklift_speed_mps=1.5,
        ttc_seconds=2.0,
        closest_approach_distance_m=0.0,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        predicted_collision=True,
    )

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0


def test_predicted_collision_cpa_overlap_close_distance_floors_to_critical_without_ttc():
    result = _risk(
        distance_m=1.5,
        zone_type=ZoneType.FRONT_DANGER,
        ttc_seconds=None,
        closest_approach_distance_m=0.4,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        predicted_collision=True,
    )

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0


def test_driver_gate_still_prevents_close_zone_floors():
    result = _risk(
        distance_m=0.2,
        zone_type=ZoneType.FOOTPRINT,
        ttc_seconds=0.5,
        closest_approach_distance_m=0.0,
        relative_motion_class=RelativeMotionClass.APPROACHING,
        predicted_collision=True,
        driver_suppressed=True,
    )

    assert result.risk_score == 0.0
    assert result.risk_level == RiskLevel.MONITOR
    assert result.driver_gated is True


def test_uncalibrated_close_distance_requires_strong_zone_evidence():
    clear = _risk(
        distance_m=0.8,
        zone_type=ZoneType.CLEAR,
        calibration_confidence=0.0,
    )
    footprint = _risk(
        distance_m=0.8,
        zone_type=ZoneType.FOOTPRINT,
        calibration_confidence=0.0,
    )

    assert clear.risk_level == RiskLevel.DANGER
    assert clear.risk_score >= 65.0
    assert clear.components["safety_floor_low_cal_close_distance"] >= 0.0
    assert footprint.risk_level == RiskLevel.CRITICAL


def test_uncalibrated_immediate_distance_floors_to_critical():
    result = _risk(
        distance_m=0.4,
        zone_type=ZoneType.CLEAR,
        calibration_confidence=0.0,
    )

    assert result.risk_level == RiskLevel.CRITICAL
    assert result.risk_score >= 85.0
    assert result.components["safety_floor_low_cal_immediate_distance"] >= 0.0


def test_stationary_side_crush_zone_floors_to_danger():
    result = _risk(distance_m=1.8, zone_type=ZoneType.SIDE_CRUSH)

    assert result.risk_level in {RiskLevel.DANGER, RiskLevel.CRITICAL}
    assert result.risk_score >= 65.0


def test_proximity_event_includes_risk_metadata():
    analyzer = ProximityAnalyzer()
    forklift = _det("forklift", (100, 100, 200, 160))
    worker = _det("person", (200, 95, 240, 135), track_id=7)

    events = analyzer.analyze(
        [worker, forklift],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert len(events) == 1
    assert "risk_score" in events[0].metadata
    assert events[0].metadata["risk_level"] in {"monitor", "warning", "danger", "critical"}
    assert "risk_components" in events[0].metadata
