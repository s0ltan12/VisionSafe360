import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.event_aggregator import EventAggregator
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.analysis.proximity_event_generator import (
    ProximityEventGenerator,
    ProximityEventStage,
)
from src.analysis.risk_engine import RiskLevel, RiskResult
from src.models.detection import Detection
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity


def _risk(score: float) -> RiskResult:
    return RiskResult(
        risk_score=score,
        risk_level=RiskLevel.MONITOR,
        driver_gated=False,
        components={},
    )


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
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


def test_event_generator_maps_score_bands_to_stages():
    generator = ProximityEventGenerator()
    pair = ("cam_01", 1, 7)

    cases = [
        (30.0, ProximityEventStage.MONITOR, "forklift_proximity", Severity.LOW),
        (35.0, ProximityEventStage.NEAR_MISS, "forklift_proximity", Severity.MEDIUM),
        (45.0, ProximityEventStage.WARNING, "forklift_proximity", Severity.MEDIUM),
        (65.0, ProximityEventStage.DANGER, "forklift_proximity", Severity.HIGH),
        (85.0, ProximityEventStage.CRITICAL, "forklift_proximity", Severity.CRITICAL),
    ]

    for idx, (score, stage, event_type, severity) in enumerate(cases):
        decision = generator.decide(
            pair_key=(*pair, idx),
            risk_result=_risk(score),
            timestamp=100.0 + idx,
        )
        assert decision is not None
        assert decision.stage == stage
        assert decision.event_type == event_type
        assert decision.severity == severity


def test_event_generator_does_not_emit_below_monitor_band():
    generator = ProximityEventGenerator()

    decision = generator.decide(
        pair_key=("cam_01", 1, 7),
        risk_result=_risk(29.9),
        timestamp=100.0,
    )

    assert decision is None


def test_event_generator_holds_deescalation_briefly_to_prevent_flapping():
    generator = ProximityEventGenerator()
    pair = ("cam_01", 1, 7)

    first = generator.decide(pair_key=pair, risk_result=_risk(90.0), timestamp=100.0)
    held = generator.decide(pair_key=pair, risk_result=_risk(45.0), timestamp=100.2)
    released = generator.decide(pair_key=pair, risk_result=_risk(45.0), timestamp=101.0)

    assert first.stage == ProximityEventStage.CRITICAL
    assert held.stage == ProximityEventStage.CRITICAL
    assert held.candidate_stage == ProximityEventStage.WARNING
    assert held.deescalation_held is True
    assert released.stage == ProximityEventStage.WARNING
    assert released.deescalation_held is False


def test_new_proximity_event_types_use_existing_aggregator_persistence():
    aggregator = EventAggregator()
    t0 = 100.0
    event_type = "forklift_proximity_near_miss"

    assert aggregator.process([_event(event_type, t0)], t0) == []
    emitted = aggregator.process([_event(event_type, t0 + 1.0)], t0 + 1.0)

    assert len(emitted) == 1
    assert emitted[0].event_type == event_type


def test_analyzer_emits_from_risk_stage_not_raw_policy_level():
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
    assert events[0].metadata["proximity_level"] == "danger"
    assert events[0].event_type == "forklift_proximity"
    assert events[0].metadata["proximity_alert_stage"] == "critical"
    assert events[0].metadata["proximity_stage_severity"] == "CRITICAL"
    assert events[0].metadata["case_type"] == "forklift_proximity"
    assert events[0].metadata["operational_case_key"]
