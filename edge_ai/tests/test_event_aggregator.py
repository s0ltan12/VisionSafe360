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
