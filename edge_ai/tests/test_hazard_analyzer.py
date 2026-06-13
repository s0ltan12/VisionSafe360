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
from types import SimpleNamespace

import numpy as np
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


class _ArrayWrap:
    def __init__(self, value):
        self._value = np.array(value)

    def cpu(self):
        return self

    def numpy(self):
        return self._value


def _pose_results(bbox, left_hip_y, right_hip_y, hip_conf=0.95, extra_conf=0.6):
    kps = np.zeros((1, 17, 2), dtype=float)
    conf = np.full((1, 17), extra_conf, dtype=float)
    kps[0, 11] = [bbox[0] + 20, left_hip_y]
    kps[0, 12] = [bbox[2] - 20, right_hip_y]
    conf[0, 11] = hip_conf
    conf[0, 12] = hip_conf
    return SimpleNamespace(
        keypoints=SimpleNamespace(xy=_ArrayWrap(kps), conf=_ArrayWrap(conf)),
        boxes=SimpleNamespace(xyxy=_ArrayWrap([bbox])),
    )


def _build_upright_history(ha, track_id, t0=1000.0, n=5):
    for i in range(n):
        ha.analyze(
            [_person(100, 100, 150, 400, track_id=track_id)],
            camera_id="cam_01",
            frame_number=i,
            timestamp=t0 + i * 0.066,
        )


def _enter_and_confirm_fall(ha, track_id, t0, start_frame=10):
    ha.analyze(
        [_person(80, 300, 280, 380, track_id=track_id)],
        "cam_01",
        start_frame,
        t0,
    )
    confirmed = []
    for i in range(1, 50):
        confirmed.extend(ha.analyze(
            [_person(80, 300, 280, 380, track_id=track_id)],
            "cam_01",
            start_frame + i,
            t0 + i * 0.066,
        ))
        if any(e.event_type == "fall_confirmed" for e in confirmed):
            break
    return confirmed


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

    def test_aspect_ratio_trigger_emits_candidate_once(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=60)

        first = ha.analyze(
            [_person(80, 300, 280, 380, track_id=60)],
            camera_id="cam_01",
            frame_number=10,
            timestamp=1001.0,
        )
        second = ha.analyze(
            [_person(80, 300, 280, 380, track_id=60)],
            camera_id="cam_01",
            frame_number=11,
            timestamp=1001.1,
        )

        candidates = [e for e in first + second if e.event_type == "fall_candidate"]
        assert len(candidates) == 1
        assert "aspect_ratio" in candidates[0].metadata["trigger_reason"]
        assert candidates[0].metadata["pose_available"] is False
        assert candidates[0].metadata["suppress_event"] is True
        assert candidates[0].metadata["operational_alert"] is False
        assert candidates[0].metadata["internal_lifecycle_event"] is True

    def test_hip_ratio_trigger_with_metadata(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=61, t0=1100.0)
        bbox = (100, 100, 180, 300)  # ar=0.4, hip trigger only

        events = ha.analyze(
            [_person(*bbox, track_id=61)],
            camera_id="cam_01",
            frame_number=20,
            timestamp=1101.0,
            pose_results=_pose_results(bbox, left_hip_y=285, right_hip_y=285),
        )

        candidate = [e for e in events if e.event_type == "fall_candidate"][0]
        assert candidate.metadata["trigger_reason"] == "hip_ratio"
        assert candidate.metadata["pose_available"] is True
        assert candidate.metadata["valid_keypoint_count"] == 17
        assert candidate.metadata["hip_ratio"] == 0.075

    def test_velocity_trigger(self):
        ha = HazardAnalyzer(fall_enabled=True)
        t0 = 1200.0
        boxes = [
            (100, 100, 200, 220),
            (100, 125, 200, 245),
        ]
        events = []
        for i, bbox in enumerate(boxes):
            events.extend(ha.analyze(
                [_person(*bbox, track_id=62)],
                camera_id="cam_01",
                frame_number=i,
                timestamp=t0 + i * 0.066,
            ))

        candidate = [e for e in events if e.event_type == "fall_candidate"][0]
        assert candidate.metadata["trigger_reason"] == "velocity"
        assert candidate.metadata["velocity"] > 15.0

    def test_confirmed_event_includes_confidence_and_debug_metadata(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=63, t0=1300.0)
        events = _enter_and_confirm_fall(ha, track_id=63, t0=1301.0)

        confirmed = [e for e in events if e.event_type == "fall_confirmed"][0]
        metadata = confirmed.metadata
        assert 0.0 <= metadata["confidence"] <= 1.0
        assert "aspect_ratio" in metadata["trigger_reason"]
        assert metadata["candidate_duration"] >= 2.5
        assert metadata["track_age"] > 0
        assert metadata["centroid_history_length"] >= 2
        assert metadata["immobile"] is True

    def test_confirmed_cooldown_enforced_for_same_track(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=64, t0=1400.0)
        first = _enter_and_confirm_fall(ha, track_id=64, t0=1401.0)
        second = ha.analyze([_person(80, 300, 280, 380, track_id=64)], "cam_01", 61, 1404.0)

        assert len([e for e in first if e.event_type == "fall_confirmed"]) == 1
        assert [e for e in second if e.event_type == "fall_confirmed"] == []

    def test_first_confirmed_event_not_suppressed_at_low_timestamp(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=640, t0=0.0)

        events = _enter_and_confirm_fall(ha, track_id=640, t0=0.5)

        assert len([e for e in events if e.event_type == "fall_confirmed"]) == 1

    def test_candidate_recovery_emits_fall_recovered(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=65, t0=1500.0)
        ha.analyze([_person(80, 300, 280, 380, track_id=65)], "cam_01", 10, 1501.0)

        events = ha.analyze(
            [_person(100, 100, 150, 400, track_id=65)],
            camera_id="cam_01",
            frame_number=11,
            timestamp=1501.1,
        )

        recovered = [e for e in events if e.event_type == "fall_recovered"][0]
        assert recovered.metadata["recovered_from_state"] == "candidate"
        assert recovered.metadata["suppress_event"] is True
        assert ha._fall_states[65].state == "normal"

    def test_confirmed_recovery_emits_fall_recovered(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=66, t0=1600.0)
        _enter_and_confirm_fall(ha, track_id=66, t0=1601.0)

        events = ha.analyze(
            [_person(100, 100, 150, 400, track_id=66)],
            camera_id="cam_01",
            frame_number=61,
            timestamp=1603.7,
        )

        recovered = [e for e in events if e.event_type == "fall_recovered"][0]
        assert recovered.metadata["recovered_from_state"] == "confirmed"
        assert recovered.metadata["suppress_event"] is True
        assert ha._fall_states[66].state == "normal"

    def test_track_continuity_transfers_candidate_after_short_fragmentation(self):
        ha = HazardAnalyzer(fall_enabled=True)
        _build_upright_history(ha, track_id=67, t0=1700.0)
        ha.analyze([_person(80, 300, 280, 380, track_id=67)], "cam_01", 10, 1701.0)

        events = ha.analyze(
            [_person(82, 302, 282, 382, track_id=99)],
            camera_id="cam_01",
            frame_number=11,
            timestamp=1701.2,
        )

        assert 67 not in ha._fall_states
        assert ha._fall_states[99].state == "candidate"
        assert [e for e in events if e.event_type == "fall_candidate"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
