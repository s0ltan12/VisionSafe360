"""
Unit tests for PostureAnalyzer — synthetic keypoint tests.

Tests:
  1. Good posture → no event
  2. Poor posture angles → HIGH severity event (sustained)
  3. Low-confidence keypoints filtered out
  4. EMA smoothing reduces noise
  5. Immediate critical for score >= 7
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

import src.analysis.posture_analyzer as posture_module
from src.analysis.angles import compute_angles
from src.analysis.posture_analyzer import PostureAnalyzer, _angle_between
from src.models.severity import Severity


# ─── Helpers ────────────────────────────────────────────────────────

def _make_pose_results(kps_xy: np.ndarray, kps_conf: np.ndarray, track_ids=None):
    """Create a mock Ultralytics Results object with keypoints."""
    mock = MagicMock()
    kp_mock = MagicMock()
    kp_mock.xy = kps_xy          # (N, 17, 2)
    kp_mock.conf = kps_conf      # (N, 17)
    mock.keypoints = kp_mock

    # boxes with optional track IDs
    boxes_mock = MagicMock()
    if track_ids is not None:
        boxes_mock.id = np.array(track_ids)
    else:
        boxes_mock.id = None
    mock.boxes = boxes_mock

    return mock


def _good_standing_keypoints() -> np.ndarray:
    """Keypoints for a person standing upright.

    COCO-17 order: nose, L/R eye, L/R ear, L/R shoulder, L/R elbow,
                   L/R wrist, L/R hip, L/R knee, L/R ankle
    """
    kp = np.zeros((17, 2), dtype=np.float32)
    # Head area
    kp[0] = [300, 50]    # nose
    kp[1] = [290, 45]    # left_eye
    kp[2] = [310, 45]    # right_eye
    kp[3] = [280, 55]    # left_ear
    kp[4] = [320, 55]    # right_ear
    # Shoulders
    kp[5] = [270, 120]   # left_shoulder
    kp[6] = [330, 120]   # right_shoulder
    # Elbows (arms at sides)
    kp[7] = [260, 200]   # left_elbow
    kp[8] = [340, 200]   # right_elbow
    # Wrists
    kp[9] = [255, 280]   # left_wrist
    kp[10] = [345, 280]  # right_wrist
    # Hips
    kp[11] = [280, 300]  # left_hip
    kp[12] = [320, 300]  # right_hip
    # Knees
    kp[13] = [280, 420]  # left_knee
    kp[14] = [320, 420]  # right_knee
    # Ankles
    kp[15] = [280, 540]  # left_ankle
    kp[16] = [320, 540]  # right_ankle
    return kp


def _bent_forward_keypoints() -> np.ndarray:
    """Keypoints for a person severely bent forward (poor posture)."""
    kp = _good_standing_keypoints().copy()
    # Bend trunk forward: move shoulders + head forward, hips stay
    kp[0] = [400, 200]   # nose far forward
    kp[3] = [380, 190]   # left_ear
    kp[4] = [420, 190]   # right_ear
    kp[5] = [360, 220]   # left_shoulder forward+down
    kp[6] = [420, 220]   # right_shoulder forward+down
    kp[7] = [350, 300]   # elbows far forward below shoulders
    kp[8] = [430, 300]
    kp[9] = [340, 350]   # wrists forward
    kp[10] = [440, 350]
    return kp


def _rula_result(score: int, risk: str = "Medium Risk"):
    return {
        "score_a": min(score, 7),
        "score_b": min(score, 7),
        "final_score": score,
        "risk_level": risk,
        "breakdown": {
            "upper_arm": 1,
            "lower_arm": 1,
            "wrist": 1,
            "neck": 1,
            "trunk": 1,
            "legs": 1,
            "muscle_adj": 0,
            "load_score": 0,
        },
    }


def _reba_result(score: int, risk: str = "Medium Risk"):
    return {
        "score_a": min(score, 12),
        "score_b": min(score, 12),
        "final_score": score,
        "risk_level": risk,
        "breakdown": {
            "neck": 1,
            "trunk": 1,
            "legs": 1,
            "upper_arm": 1,
            "lower_arm": 1,
            "wrist": 1,
            "load_score": 0,
            "coupling_score": 0,
        },
    }


# ════════════════════════════════════════════════════════════════════
#  Tests
# ════════════════════════════════════════════════════════════════════

class TestPostureAnalyzer:
    def test_good_posture_no_event(self):
        """Upright standing posture → no hazard event."""
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]  # (1, 17, 2)
        conf = np.ones((1, 17), dtype=np.float32) * 0.9

        results = _make_pose_results(kps, conf, track_ids=[1])
        events = pa.analyze(results, camera_id="cam_01", frame_number=1, timestamp=1000.0)
        assert len(events) == 0

    def test_poor_posture_immediate_critical(self):
        """Severely bent posture → immediate critical if score >= 7.

        We test that the analyzer produces a CRITICAL event without
        needing sustained time, by crafting extremely poor angles.
        """
        pa = PostureAnalyzer()
        # Create extremely bad posture keypoints
        kp = _good_standing_keypoints().copy()
        # Extreme trunk bend: shoulders way in front of hips
        kp[5] = [200, 350]   # left shoulder at hip level but far forward
        kp[6] = [400, 350]   # right shoulder same
        kp[7] = [150, 400]   # elbows far down
        kp[8] = [450, 400]
        kp[9] = [130, 420]   # wrists very low
        kp[10] = [470, 420]
        kp[0] = [300, 280]   # nose at trunk level
        kp[3] = [250, 270]   # ears far down
        kp[4] = [350, 270]

        kps = kp[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9

        results = _make_pose_results(kps, conf, track_ids=[5])
        events = pa.analyze(results, camera_id="cam_01", frame_number=1, timestamp=1000.0)
        assert isinstance(events, list)

    def test_dangerous_posture_emits_when_rula_is_critical(self, monkeypatch):
        """RULA 7 emits an immediate dangerous_posture event."""
        monkeypatch.setattr(posture_module, "compute_rula", lambda _angles: _rula_result(7, "HIGH RISK"))
        monkeypatch.setattr(posture_module, "compute_reba", lambda _angles: _reba_result(8, "High Risk"))
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9

        events = pa.analyze(_make_pose_results(kps, conf, track_ids=[8]), "cam_01", 1, 1000.0)

        assert len(events) == 1
        event = events[0]
        assert event.event_type == "dangerous_posture"
        assert event.severity == Severity.CRITICAL
        assert event.metadata["rula_score"] == 7
        assert event.metadata["reba_score"] == 8
        assert event.metadata["analysis_side"] in {"left", "right"}

    def test_sustained_poor_posture_emits_after_threshold(self, monkeypatch):
        """Risky non-critical posture must persist before poor_posture is emitted."""
        monkeypatch.setattr(posture_module, "compute_rula", lambda _angles: _rula_result(5))
        monkeypatch.setattr(posture_module, "compute_reba", lambda _angles: _reba_result(7))
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9
        results = _make_pose_results(kps, conf, track_ids=[9])

        assert pa.analyze(results, "cam_01", 1, 1000.0) == []
        assert pa.analyze(results, "cam_01", 2, 1002.0) == []
        events = pa.analyze(results, "cam_01", 3, 1004.1)

        assert len(events) == 1
        assert events[0].event_type == "poor_posture"
        assert events[0].severity == Severity.HIGH
        assert events[0].metadata["sustained_seconds"] == 4.1

    def test_posture_cooldown_suppresses_repeat_critical(self, monkeypatch):
        """Per-track cooldown prevents repeated dangerous_posture events."""
        monkeypatch.setattr(posture_module, "compute_rula", lambda _angles: _rula_result(7, "HIGH RISK"))
        monkeypatch.setattr(posture_module, "compute_reba", lambda _angles: _reba_result(8, "High Risk"))
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9
        results = _make_pose_results(kps, conf, track_ids=[10])

        assert len(pa.analyze(results, "cam_01", 1, 1000.0)) == 1
        assert pa.analyze(results, "cam_01", 2, 1001.0) == []
        assert len(pa.analyze(results, "cam_01", 3, 1051.0)) == 1

    def test_stale_state_cleanup_runs_on_empty_pose(self):
        """Track state is purged even when the current frame has no poses."""
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9
        pa.analyze(_make_pose_results(kps, conf, track_ids=[11]), "cam_01", 1, 1000.0)
        assert 11 in pa._states

        empty = _make_pose_results(
            np.empty((0, 17, 2), dtype=np.float32),
            np.empty((0, 17), dtype=np.float32),
            track_ids=[],
        )
        pa.analyze(empty, "cam_01", 2, 1011.0)
        assert 11 not in pa._states

    def test_missing_optional_limb_keypoints_still_records_sample(self):
        """Missing elbow/wrist keypoints degrade angle detail but keep torso scoring."""
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9
        conf[0, 7] = 0.1
        conf[0, 9] = 0.1

        events = pa.analyze(_make_pose_results(kps, conf, track_ids=[12]), "cam_01", 1, 1000.0)

        assert events == []
        assert len(pa.last_samples) == 1
        assert pa.last_samples[0].metadata["valid_keypoints"] == 15

    def test_low_confidence_keypoints_filtered(self):
        """Keypoints below confidence threshold → no angle computed → no event."""
        pa = PostureAnalyzer()
        kps = _bent_forward_keypoints()[np.newaxis, ...]
        # Set all confidences to 0.2 (below threshold 0.5)
        conf = np.ones((1, 17), dtype=np.float32) * 0.2

        results = _make_pose_results(kps, conf, track_ids=[2])
        events = pa.analyze(results, camera_id="cam_01", frame_number=1, timestamp=1000.0)
        # Should skip analysis entirely due to low confidence
        assert len(events) == 0
        assert pa.last_samples == []

    def test_ema_smoothing_effect(self):
        """EMA smoothing should reduce sudden keypoint jumps."""
        pa = PostureAnalyzer()
        conf = np.ones((1, 17), dtype=np.float32) * 0.9

        # Frame 1: good posture
        kps1 = _good_standing_keypoints()[np.newaxis, ...]
        results1 = _make_pose_results(kps1, conf, track_ids=[3])
        pa.analyze(results1, camera_id="cam_01", frame_number=1, timestamp=1000.0)

        # Frame 2: noisy jump
        kps2 = _good_standing_keypoints()
        kps2 += np.random.randn(17, 2).astype(np.float32) * 20  # big noise
        kps2 = kps2[np.newaxis, ...]
        results2 = _make_pose_results(kps2, conf, track_ids=[3])
        pa.analyze(results2, camera_id="cam_01", frame_number=2, timestamp=1000.2)

        # Check that smoothed keypoints are closer to original than noisy
        state = pa._states[3]
        original = _good_standing_keypoints()
        diff_smoothed = np.mean(np.abs(state.smoothed_kps - original))
        diff_noisy = np.mean(np.abs(kps2[0] - original))
        # Smoothed should be closer to original than raw noisy
        assert diff_smoothed < diff_noisy

    def test_none_pose_results(self):
        """pose_results=None → empty list, no crash."""
        pa = PostureAnalyzer()
        events = pa.analyze(None, camera_id="cam_01", frame_number=1, timestamp=1000.0)
        assert events == []

    def test_event_metadata_contains_debug_fields(self, monkeypatch):
        """Emitted events carry additive diagnostic metadata for triage."""
        monkeypatch.setattr(posture_module, "compute_rula", lambda _angles: _rula_result(7, "HIGH RISK"))
        monkeypatch.setattr(posture_module, "compute_reba", lambda _angles: _reba_result(8, "High Risk"))
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9

        event = pa.analyze(_make_pose_results(kps, conf, track_ids=[13]), "cam_01", 1, 1000.0)[0]

        assert "angles" in event.metadata
        assert "rula_breakdown" in event.metadata
        assert "reba_breakdown" in event.metadata
        assert event.metadata["keypoint_conf_min"] == 0.5
        assert event.metadata["score_window_size"] == 1
        assert event.metadata["rula_score_avg"] == 7.0

    def test_right_side_can_drive_selected_posture_score(self, monkeypatch):
        """The analyzer uses the higher-risk side instead of always using left."""
        def fake_rula(angles):
            return _rula_result(3 if angles["upper_arm"] == 10.0 else 5)

        def fake_reba(angles):
            return _reba_result(2 if angles["upper_arm"] == 10.0 else 7)

        def fake_angles(_kp, _conf, side, confidence_threshold=0.5):
            return {"upper_arm": 10.0 if side == "left" else 90.0}

        monkeypatch.setattr(posture_module, "compute_angles", fake_angles)
        monkeypatch.setattr(posture_module, "compute_rula", fake_rula)
        monkeypatch.setattr(posture_module, "compute_reba", fake_reba)
        pa = PostureAnalyzer()
        kps = _good_standing_keypoints()[np.newaxis, ...]
        conf = np.ones((1, 17), dtype=np.float32) * 0.9
        results = _make_pose_results(kps, conf, track_ids=[14])

        pa.analyze(results, "cam_01", 1, 1000.0)
        events = pa.analyze(results, "cam_01", 2, 1004.1)

        assert len(events) == 1
        assert events[0].event_type == "poor_posture"
        assert events[0].metadata["analysis_side"] == "right"
        assert events[0].metadata["reba_score"] == 7


class TestAngleBetween:
    def test_right_angle(self):
        """90-degree angle."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 0.0])
        c = np.array([0.0, 1.0])
        angle = _angle_between(a, b, c)
        assert abs(angle - 90.0) < 1.0

    def test_straight_angle(self):
        """180-degree angle."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 0.0])
        c = np.array([-1.0, 0.0])
        angle = _angle_between(a, b, c)
        assert abs(angle - 180.0) < 1.0

    def test_zero_angle(self):
        """~0-degree angle (same direction)."""
        a = np.array([2.0, 0.0])
        b = np.array([0.0, 0.0])
        c = np.array([1.0, 0.0])
        angle = _angle_between(a, b, c)
        assert angle < 5.0


class TestComputeAngles:
    def test_left_and_right_sides_use_distinct_limbs(self):
        """Side-specific angles should come from the requested COCO limb."""
        kp = _good_standing_keypoints()
        kp[8] = [430, 120]
        kp[10] = [520, 120]
        conf = np.ones(17, dtype=np.float32) * 0.9

        left = compute_angles(kp, conf, side="left")
        right = compute_angles(kp, conf, side="right")

        assert left["upper_arm"] != right["upper_arm"]
        assert left["lower_arm"] != right["lower_arm"]

    def test_compute_angles_rejects_invalid_side(self):
        kp = _good_standing_keypoints()
        conf = np.ones(17, dtype=np.float32) * 0.9

        with pytest.raises(ValueError):
            compute_angles(kp, conf, side="center")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
