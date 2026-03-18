"""
Unit tests for HazardAnalyzer — fall detection only.

Tests:
  1. Fall candidate → confirmed after timeout
  2. Fall candidate → recovered (aspect ratio normalizes)
  3. Stale track purged after timeout
  4. Fall disabled → no events
  5. Backward-compat kwargs accepted
"""
import sys
from pathlib import Path

import pytest

# Ensure src is importable
_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.hazard_analyzer import HazardAnalyzer
from src.models.detection import Detection
from src.models.severity import Severity


# ─── Helpers ────────────────────────────────────────────────────────

def _person(x1, y1, x2, y2, track_id=1, conf=0.9):
    return Detection(
        class_id=0, class_name="person", confidence=conf,
        bbox=(x1, y1, x2, y2), track_id=track_id,
    )


# ════════════════════════════════════════════════════════════════════
#  Fall Detection Tests
# ════════════════════════════════════════════════════════════════════

class TestFallDetection:
    def test_fall_candidate_to_confirmed(self):
        """Person transitions from upright to lying → fall_confirmed after timeout."""
        ha = HazardAnalyzer(fall_enabled=True)

        t0 = 1000.0

        # Phase 1: Person standing upright (narrow bbox) — build history
        for i in range(5):
            person = _person(100, 100, 150, 400, track_id=20)  # w=50, h=300, ar=0.17
            ha.analyze([person], camera_id="cam_01", frame_number=i, timestamp=t0 + i * 0.066)

        # Phase 2: Person falls (wide bbox) — trigger candidate
        for i in range(5, 10):
            person = _person(80, 300, 280, 380, track_id=20)  # w=200, h=80, ar=2.5
            ha.analyze([person], camera_id="cam_01", frame_number=i, timestamp=t0 + i * 0.066)

        # Verify state is "candidate"
        assert ha._fall_states[20].state == "candidate"

        # Phase 3: Stay immobile past candidate timeout (2s)
        events = []
        for i in range(10, 60):
            person = _person(80, 300, 280, 380, track_id=20)
            result = ha.analyze(
                [person], camera_id="cam_01",
                frame_number=i, timestamp=t0 + 0.7 + (i - 10) * 0.066,
            )
            events.extend(result)

        # Should have confirmed fall
        fall_events = [e for e in events if e.event_type == "fall_confirmed"]
        assert len(fall_events) >= 1
        assert fall_events[0].severity == Severity.CRITICAL

    def test_fall_recovery_resets(self):
        """Person falls but recovers (stands up) → no fall_confirmed event."""
        ha = HazardAnalyzer(fall_enabled=True)

        t0 = 2000.0

        # Build upright history
        for i in range(5):
            person = _person(100, 100, 150, 400, track_id=30)
            ha.analyze([person], camera_id="cam_01", frame_number=i, timestamp=t0 + i * 0.066)

        # Trigger fall candidate
        for i in range(5, 10):
            person = _person(80, 300, 280, 380, track_id=30)
            ha.analyze([person], camera_id="cam_01", frame_number=i, timestamp=t0 + i * 0.066)

        assert ha._fall_states[30].state == "candidate"

        # Recovery — stand back up (narrow bbox)
        person = _person(100, 100, 150, 400, track_id=30)  # ar=0.17 < 0.8
        events = ha.analyze(
            [person], camera_id="cam_01",
            frame_number=10, timestamp=t0 + 10 * 0.066,
        )
        assert ha._fall_states[30].state == "normal"
        assert len([e for e in events if e.event_type == "fall_confirmed"]) == 0

    def test_stale_track_purged(self):
        """Tracks absent for > FALL_TRACK_PURGE_SEC are removed."""
        ha = HazardAnalyzer(fall_enabled=True)

        t0 = 3000.0
        person = _person(100, 100, 150, 400, track_id=40)
        ha.analyze([person], camera_id="cam_01", frame_number=0, timestamp=t0)

        assert 40 in ha._fall_states

        # Time jump past purge threshold (5s)
        ha.analyze([], camera_id="cam_01", frame_number=1, timestamp=t0 + 10.0)
        assert 40 not in ha._fall_states

    def test_no_event_when_disabled(self):
        """With fall_enabled=False, no events are generated."""
        ha = HazardAnalyzer(fall_enabled=False)

        t0 = 4000.0
        for i in range(5):
            person = _person(100, 100, 150, 400, track_id=50)
            ha.analyze([person], camera_id="cam_01", frame_number=i, timestamp=t0 + i * 0.066)
        for i in range(5, 10):
            person = _person(80, 300, 280, 380, track_id=50)
            events = ha.analyze(
                [person], camera_id="cam_01",
                frame_number=i, timestamp=t0 + i * 0.066,
            )
            assert len(events) == 0

    def test_backward_compat_kwargs(self):
        """Old callers passing ppe_this_frame/proximity_this_frame don't crash."""
        ha = HazardAnalyzer(fall_enabled=True)
        events = ha.analyze(
            [], camera_id="cam_01", frame_number=0, timestamp=0.0,
            ppe_this_frame=True, proximity_this_frame=True,
        )
        assert events == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
