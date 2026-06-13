"""
Unit tests for EventAggregator — persistence, dedup, cooldown.

Tests:
  1. Transient event (below persistence) → NOT emitted
  2. Persistent event → emitted after persistence window
  3. Duplicate events in same window → deduplicated
  4. Severity escalation within aggregation window
  5. Cooldown prevents re-emission after window
  6. Different composite keys emitted independently
  7. Fall events emit immediately (zero persistence)
"""
import sys
import time
from pathlib import Path

import pytest

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.event_aggregator import EventAggregator
from src.analysis.escalation_engine import EscalationEngine
from src.analysis.severity_engine import SeverityEngine
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity
from src.config import settings


# ─── Helpers ────────────────────────────────────────────────────────

def _event(
    event_type="no_helmet",
    severity=Severity.HIGH,
    camera_id="cam_01",
    track_id=1,
    frame_number=10,
    timestamp=100.0,
    **meta_kw,
):
    return HazardEvent(
        event_type=event_type,
        severity=severity,
        camera_id=camera_id,
        timestamp=timestamp,
        frame_number=frame_number,
        track_id=track_id,
        bbox=(10, 10, 100, 200),
        description=f"test {event_type}",
        metadata=meta_kw if meta_kw else {},
    )


# ════════════════════════════════════════════════════════════════════
#  Persistence Tests
# ════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_fall_emits_immediately(self):
        """Fall events have 0 persistence — should emit on first frame."""
        agg = EventAggregator()
        t0 = 100.0
        emitted = agg.process(
            [_event(event_type="fall_confirmed", severity=Severity.CRITICAL, timestamp=t0)],
            t0,
        )
        assert len(emitted) == 1
        assert emitted[0].event_type == "fall_confirmed"

    def test_internal_fall_lifecycle_events_are_suppressed(self):
        """Candidate/recovered lifecycle events stay out of operational routing."""
        agg = EventAggregator()
        t0 = 100.0
        emitted = agg.process(
            [
                _event(
                    event_type="fall_candidate",
                    severity=Severity.HIGH,
                    timestamp=t0,
                    suppress_event=True,
                    internal_lifecycle_event=True,
                    operational_alert=False,
                ),
                _event(
                    event_type="fall_recovered",
                    severity=Severity.LOW,
                    timestamp=t0,
                    suppress_event=True,
                    internal_lifecycle_event=True,
                    operational_alert=False,
                ),
            ],
            t0,
        )
        assert emitted == []

    def test_fall_confirmed_remains_operational_with_lifecycle_metadata(self):
        """Confirmed falls still emit even when metadata contains lifecycle fields."""
        agg = EventAggregator()
        t0 = 100.0
        emitted = agg.process(
            [
                _event(
                    event_type="fall_confirmed",
                    severity=Severity.CRITICAL,
                    timestamp=t0,
                    internal_lifecycle_event=False,
                    operational_alert=True,
                )
            ],
            t0,
        )
        assert len(emitted) == 1
        assert emitted[0].event_type == "fall_confirmed"

    def test_posture_emits_immediately(self):
        """Posture events have 0 persistence — should emit on first frame."""
        agg = EventAggregator()
        t0 = 100.0
        emitted = agg.process(
            [_event(event_type="posture_risk", severity=Severity.MEDIUM, timestamp=t0)],
            t0,
        )
        assert len(emitted) == 1
        assert emitted[0].event_type == "posture_risk"

    def test_ppe_missing_requires_three_seconds(self):
        """PPE missing alerts require continuous detection before emission."""
        agg = EventAggregator()
        t0 = 100.0
        event_type = "ppe_missing_helmet"

        assert agg.process([_event(event_type=event_type, timestamp=t0)], t0) == []
        assert agg.process([_event(event_type=event_type, timestamp=t0 + 2.9)], t0 + 2.9) == []

        emitted = agg.process([_event(event_type=event_type, timestamp=t0 + 3.0)], t0 + 3.0)
        assert len(emitted) == 1
        assert emitted[0].event_type == event_type

    def test_proximity_requires_configured_persistence(self):
        """Forklift proximity requires continuous detection before emission."""
        agg = EventAggregator()
        t0 = 100.0
        event_type = "forklift_proximity_danger"

        assert agg.process([_event(event_type=event_type, timestamp=t0)], t0) == []
        emitted = agg.process([_event(event_type=event_type, timestamp=t0 + 1.0)], t0 + 1.0)
        assert len(emitted) == 1
        assert emitted[0].metadata["active_duration_sec"] == 1.0


# ════════════════════════════════════════════════════════════════════
#  Deduplication / Cooldown Tests
# ════════════════════════════════════════════════════════════════════

class TestDeduplication:
    def test_duplicate_suppressed_in_window(self):
        """After emission, same key in same window should NOT re-emit."""
        agg = EventAggregator()
        t0 = 100.0

        # Emit the event (fall = 0 persistence)
        emitted_1 = agg.process(
            [_event(event_type="fall_confirmed", severity=Severity.CRITICAL, timestamp=t0)],
            t0,
        )
        assert len(emitted_1) == 1

        # Same event 1s later (within aggregation window)
        t1 = t0 + 1.0
        emitted_2 = agg.process(
            [_event(event_type="fall_confirmed", severity=Severity.CRITICAL, timestamp=t1)],
            t1,
        )
        # Should be suppressed (already emitted in this window)
        assert len(emitted_2) == 0

    def test_severity_escalation(self):
        """If severity increases within window, emit an update."""
        agg = EventAggregator()
        t0 = 100.0

        # Initial emission (fall = immediate)
        emitted_1 = agg.process(
            [_event(event_type="proximity_warning", severity=Severity.MEDIUM, timestamp=t0)],
            t0,
        )
        # proximity has 0.5s persistence — won't emit yet
        # Use fall to test escalation more easily
        emitted_1 = agg.process(
            [_event(event_type="fall_confirmed", severity=Severity.HIGH, timestamp=t0)],
            t0,
        )
        assert len(emitted_1) == 1
        assert emitted_1[0].severity == Severity.HIGH

        # Escalate to CRITICAL in same window
        t1 = t0 + 0.5
        emitted_2 = agg.process(
            [_event(event_type="fall_confirmed", severity=Severity.CRITICAL, timestamp=t1)],
            t1,
        )
        assert len(emitted_2) == 1
        assert emitted_2[0].severity == Severity.CRITICAL

    def test_different_keys_independent(self):
        """Events with different composite keys emit independently."""
        agg = EventAggregator()
        t0 = 100.0

        events = [
            _event(event_type="fall_confirmed", track_id=1, timestamp=t0),
            _event(event_type="fall_confirmed", track_id=2, timestamp=t0),
        ]
        emitted = agg.process(events, t0)
        # Both should emit (different track_ids → different keys)
        assert len(emitted) == 2


# ════════════════════════════════════════════════════════════════════
#  Cooldown Key Tests
# ════════════════════════════════════════════════════════════════════

class TestCooldownKeys:
    def test_different_track_ids_independent(self):
        """Different track_ids should create independent cooldown keys."""
        agg = EventAggregator()
        t0 = 100.0

        ev1 = _event(event_type="fall_confirmed", track_id=1,
                      severity=Severity.CRITICAL, timestamp=t0)
        ev2 = _event(event_type="fall_confirmed", track_id=2,
                      severity=Severity.CRITICAL, timestamp=t0)

        emitted = agg.process([ev1, ev2], t0)
        # Two different track_ids → two distinct keys → both emit
        assert len(emitted) == 2

    def test_proximity_key_includes_forklift_track_id_when_available(self):
        """Same worker near different forklifts should not share one alert stream."""
        agg = EventAggregator()
        t0 = 100.0
        event_type = "forklift_proximity_danger"

        first = _event(
            event_type=event_type,
            track_id=7,
            timestamp=t0,
            forklift_track_id=101,
        )
        second = _event(
            event_type=event_type,
            track_id=7,
            timestamp=t0,
            forklift_track_id=202,
        )

        assert agg.process([first, second], t0) == []
        emitted = agg.process(
            [
                _event(event_type=event_type, track_id=7, timestamp=t0 + 1.0, forklift_track_id=101),
                _event(event_type=event_type, track_id=7, timestamp=t0 + 1.0, forklift_track_id=202),
            ],
            t0 + 1.0,
        )

        assert len(emitted) == 2
        assert {event.metadata["forklift_track_id"] for event in emitted} == {101, 202}

    def test_proximity_stage_changes_share_one_operational_case_key(self):
        agg = EventAggregator()
        t0 = 100.0

        monitor = _event(
            event_type="forklift_proximity",
            severity=Severity.LOW,
            track_id=7,
            timestamp=t0,
            forklift_track_id=101,
            worker_track_id=7,
            case_type="forklift_proximity",
            operational_case_key=["cam_01", 101, 7],
            proximity_alert_stage="monitor",
            risk_level="monitor",
            risk_score=30.0,
        )
        assert agg.process([monitor], t0) == []
        emitted = agg.process([
            _event(
                event_type="forklift_proximity",
                severity=Severity.LOW,
                track_id=7,
                timestamp=t0 + 1.0,
                forklift_track_id=101,
                worker_track_id=7,
                case_type="forklift_proximity",
                operational_case_key=["cam_01", 101, 7],
                proximity_alert_stage="monitor",
                risk_level="monitor",
                risk_score=30.0,
            )
        ], t0 + 1.0)
        assert len(emitted) == 1
        case_id = emitted[0].metadata["operational_case_id"]
        assert emitted[0].event_type == "forklift_proximity"
        assert emitted[0].metadata["event_lifecycle"] == "created"

        escalated = agg.process([
            _event(
                event_type="forklift_proximity",
                severity=Severity.CRITICAL,
                track_id=7,
                timestamp=t0 + 2.0,
                forklift_track_id=101,
                worker_track_id=7,
                case_type="forklift_proximity",
                operational_case_key=["cam_01", 101, 7],
                proximity_alert_stage="critical",
                risk_level="critical",
                risk_score=90.0,
            )
        ], t0 + 2.0)
        assert len(escalated) == 1
        assert escalated[0].metadata["operational_case_id"] == case_id
        assert escalated[0].metadata["event_lifecycle"] == "escalated"
        assert agg.active_count == 1

    def test_proximity_resolution_and_reopen_use_same_case_within_grace(self):
        agg = EventAggregator()
        t0 = 200.0

        def prox(ts: float):
            return _event(
                event_type="forklift_proximity",
                severity=Severity.LOW,
                track_id=7,
                timestamp=ts,
                forklift_track_id=101,
                worker_track_id=7,
                case_type="forklift_proximity",
                operational_case_key=["cam_01", 101, 7],
                proximity_alert_stage="monitor",
                risk_level="monitor",
                risk_score=30.0,
            )

        assert agg.process([prox(t0)], t0) == []
        created = agg.process([prox(t0 + 1.0)], t0 + 1.0)
        case_id = created[0].metadata["operational_case_id"]

        assert agg.process([], t0 + 6.0) == []
        resolved = agg.process([], t0 + 7.1)
        assert len(resolved) == 1
        assert resolved[0].metadata["event_lifecycle"] == "resolved"
        assert resolved[0].metadata["operational_case_id"] == case_id
        assert agg.active_count == 0

        reopened = agg.process([prox(t0 + 10.0)], t0 + 10.0)
        assert len(reopened) == 1
        assert reopened[0].metadata["event_lifecycle"] == "reopened"
        assert reopened[0].metadata["operational_case_id"] == case_id

    def test_default_hazard_cooldown_is_fifty_seconds(self):
        """Non-fall hazards are suppressed for the configured 50 second cooldown."""
        agg = EventAggregator()
        t0 = 100.0
        event_type = "forklift_proximity_danger"

        assert agg.process([_event(event_type=event_type, timestamp=t0)], t0) == []
        assert len(agg.process([_event(event_type=event_type, timestamp=t0 + 1.0)], t0 + 1.0)) == 1
        assert agg.process([_event(event_type=event_type, timestamp=t0 + 49.0)], t0 + 49.0) == []
        assert agg.process([], t0 + 55.0) == []
        assert agg.process([_event(event_type=event_type, timestamp=t0 + 56.0)], t0 + 56.0) == []
        assert len(agg.process([_event(event_type=event_type, timestamp=t0 + 57.0)], t0 + 57.0)) == 1

    def test_composite_clears_source_pending_and_emits_only_composite(self):
        """Accepted composite events remove source hazard state from the aggregator."""
        agg = EventAggregator()
        t0 = 100.0
        ppe_key = ("cam_01", "ppe_missing_helmet", 7)
        forklift_key = (
            "cam_01",
            "forklift_proximity_danger",
            "forklift",
            101,
            "worker",
            7,
        )

        assert agg.process([
            _event(event_type="ppe_missing_helmet", track_id=7, timestamp=t0),
        ], t0) == []
        assert agg.pending_count == 1

        composite = _event(
            event_type="COMPOSITE_PPE_FORKLIFT_RISK",
            severity=Severity.CRITICAL,
            track_id=7,
            timestamp=t0 + 0.2,
            composite=True,
            correlation_id="cam_01:worker:7:forklift:101:COMPOSITE_PPE_FORKLIFT_RISK",
            source_events=[
                {"aggregation_key": ppe_key},
                {"aggregation_key": forklift_key},
            ],
            component_hazards=[
                {"label": "Missing Helmet", "event_type": "ppe_missing_helmet"},
                {"label": "Forklift Proximity Danger", "event_type": "forklift_proximity_danger"},
            ],
            forklift_track_id=101,
        )

        emitted = agg.process([composite], t0 + 0.2)

        assert len(emitted) == 1
        assert emitted[0].event_type == "COMPOSITE_PPE_FORKLIFT_RISK"
        assert agg.pending_count == 0
        assert agg.process([
            _event(event_type="ppe_missing_helmet", track_id=7, timestamp=t0 + 3.2),
        ], t0 + 3.2) == []

    def test_composite_clears_active_source_state(self):
        """Accepted composite events clear source active/cooldown state as well as pending state."""
        agg = EventAggregator()
        t0 = 100.0
        forklift_key = (
            "cam_01",
            "forklift_proximity_danger",
            "forklift",
            101,
            "worker",
            7,
        )

        assert agg.process([
            _event(
                event_type="forklift_proximity_danger",
                track_id=7,
                timestamp=t0,
                forklift_track_id=101,
            ),
        ], t0) == []
        emitted_source = agg.process([
            _event(
                event_type="forklift_proximity_danger",
                track_id=7,
                timestamp=t0 + 1.0,
                forklift_track_id=101,
            ),
        ], t0 + 1.0)
        assert len(emitted_source) == 1
        assert agg.active_count == 1

        composite = _event(
            event_type="COMPOSITE_PPE_FORKLIFT_RISK",
            severity=Severity.CRITICAL,
            track_id=7,
            timestamp=t0 + 1.2,
            composite=True,
            correlation_id="cam_01:worker:7:forklift:101:COMPOSITE_PPE_FORKLIFT_RISK",
            source_events=[
                {"aggregation_key": forklift_key},
            ],
            component_hazards=[
                {"label": "Forklift Proximity Danger", "event_type": "forklift_proximity_danger"},
            ],
            forklift_track_id=101,
        )

        emitted = agg.process([composite], t0 + 1.2)

        assert len(emitted) == 1
        assert emitted[0].event_type == "COMPOSITE_PPE_FORKLIFT_RISK"
        assert agg.active_count == 1
        assert all("COMPOSITE_" in key[1] for key in agg._active)
        assert agg.process([
            _event(
                event_type="forklift_proximity_danger",
                track_id=7,
                timestamp=t0 + 2.0,
                forklift_track_id=101,
            ),
        ], t0 + 2.0) == []


class TestScoringAndEscalation:
    def test_severity_engine_raises_for_high_risk_zone_duration_and_count(self):
        engine = SeverityEngine()
        event = _event(event_type="ppe_missing_helmet", severity=Severity.LOW, zone_risk="HIGH")

        severity = engine.compute(
            event,
            {"risk_level": "HIGH"},
            active_duration_sec=180.0,
            concurrent_events=3,
        )

        assert severity >= Severity.MEDIUM

    def test_escalation_engine_emits_threshold_once(self):
        engine = EscalationEngine()
        key = ("cam_01", "ppe_missing_helmet", 1)

        assert engine.check(key, 0.0, Severity.LOW, 59.0) is None
        assert engine.check(key, 0.0, Severity.LOW, 60.0) == Severity.MEDIUM
        assert engine.check(key, 0.0, Severity.LOW, 61.0) is None
        assert engine.check(key, 0.0, Severity.MEDIUM, 180.0) == Severity.HIGH
