import logging
import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.driver_suppression import (
    DriverSuppression,
    DriverSuppressionConfig,
    DriverSuppressionResult,
)
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.models.detection import Detection


def _det(class_name: str, bbox, track_id=None, conf=0.9):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=conf,
        bbox=bbox,
        track_id=track_id,
    )


def _analyze(persons, forklifts, tracked=None, ts=100.0):
    analyzer = ProximityAnalyzer(danger_px=220.0, warning_px=320.0)
    return analyzer.analyze(
        detections=[*persons, *forklifts],
        tracked_pose_people=tracked or persons,
        camera_id="cam_01",
        frame_number=1,
        timestamp=ts,
    )


def test_operator_inside_forklift_is_suppressed_with_audit_trail(caplog):
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    operator = _det("person", (165, 115, 235, 245), track_id=1)

    with caplog.at_level(logging.WARNING, logger="src.analysis.proximity_analyzer"):
        events = _analyze([operator], [forklift])

    assert events == []
    assert "DRIVER_SUPPRESSION_AUDIT" in caplog.text
    assert "shadow_score=" in caplog.text


def test_operator_entering_forklift_becomes_assigned_driver():
    cfg = DriverSuppressionConfig(candidate_sec=0.5, assign_sec=1.0)
    suppression = DriverSuppression(cfg)
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    operator = _det("person", (120, 105, 185, 235), track_id=1)

    first = suppression.evaluate(operator, forklift, 100.0)
    second = suppression.evaluate(operator, forklift, 101.1)

    assert first.driver_suppressed is True
    assert first.driver_candidate is False
    assert second.driver_candidate is True
    assert second.driver_assigned is True


def test_driver_exiting_revokes_assignment_after_exit_grace():
    cfg = DriverSuppressionConfig(candidate_sec=0.1, assign_sec=0.2, exit_sec=0.5)
    suppression = DriverSuppression(cfg)
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    inside = _det("person", (165, 115, 235, 245), track_id=1)
    outside = _det("person", (325, 120, 385, 245), track_id=1)

    suppression.evaluate(inside, forklift, 100.0)
    assigned = suppression.evaluate(inside, forklift, 100.3)
    grace = suppression.evaluate(outside, forklift, 100.4)
    revoked = suppression.evaluate(outside, forklift, 101.0)

    assert assigned.driver_assigned is True
    assert grace.driver_suppressed is True
    assert revoked.driver_suppressed is False
    assert revoked.driver_assigned is False


def test_partial_occlusion_does_not_immediately_remove_driver_state():
    cfg = DriverSuppressionConfig(candidate_sec=0.1, assign_sec=0.2, occlusion_timeout_sec=2.0)
    suppression = DriverSuppression(cfg)
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    operator = _det("person", (165, 115, 235, 245), track_id=1)

    suppression.evaluate(operator, forklift, 100.0)
    assigned = suppression.evaluate(operator, forklift, 100.3)
    reappeared = suppression.evaluate(operator, forklift, 101.5)

    assert assigned.driver_assigned is True
    assert reappeared.driver_suppressed is True
    assert reappeared.driver_assigned is True


def test_multiple_workers_nearby_only_driver_is_suppressed():
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    operator = _det("person", (165, 115, 235, 245), track_id=1)
    nearby_worker = _det("person", (300, 180, 360, 320), track_id=2)

    events = _analyze([operator, nearby_worker], [forklift])

    assert len(events) == 1
    assert events[0].track_id == 2
    assert events[0].metadata["driver_suppressed"] is False


def test_false_positive_driver_suppression_can_be_overridden_for_critical_shadow_risk(caplog):
    analyzer = ProximityAnalyzer(danger_px=220.0, warning_px=320.0)
    forklift = _det("forklift", (100, 100, 320, 260), track_id=10)
    worker = _det("person", (260, 180, 320, 260), track_id=7)

    def false_suppression(_person, _forklift, _timestamp):
        return DriverSuppressionResult(
            driver_suppressed=True,
            driver_candidate=False,
            driver_assigned=False,
            reason="cabin_roi",
            person_track_id=worker.track_id,
            forklift_track_id=forklift.track_id,
            overlap_ratio=0.0,
            cabin_overlap_ratio=0.0,
        )

    analyzer._driver_suppression.evaluate = false_suppression

    with caplog.at_level(logging.WARNING, logger="src.analysis.proximity_analyzer"):
        events = analyzer.analyze(
            detections=[worker, forklift],
            tracked_pose_people=[worker],
            camera_id="cam_01",
            frame_number=1,
            timestamp=100.0,
        )

    assert len(events) == 1
    assert events[0].metadata["driver_suppressed"] is True
    assert events[0].metadata["driver_suppression_overridden"] is True
    assert events[0].metadata["risk_score"] >= 85.0
    assert "DRIVER_SUPPRESSION_AUDIT" in caplog.text
    assert "SUPPRESSION_OVERRIDE" in caplog.text
