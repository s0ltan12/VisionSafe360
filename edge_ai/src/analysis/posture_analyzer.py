"""
VisionSafe 360 — PostureAnalyzer

CPU-only ergonomic risk scoring from COCO-17 pose keypoints.
Full RULA/REBA scoring with temporal EMA smoothing.
Integrated from the Ergonomic Risk Assessment standalone project.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from ..config.settings import (
    ERGONOMIC_SCORE_WINDOW,
    POSTURE_COOLDOWN_SEC,
    POSTURE_EMA_ALPHA,
    POSTURE_KEYPOINT_CONF_MIN,
    POSTURE_SUSTAINED_THRESHOLD,
)
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity
from .angles import compute_angles
from .scoring import compute_rula, compute_reba

logger = logging.getLogger(__name__)


# ─── COCO-17 keypoint indices ───────────────────────────────────────

KP_NOSE = 0
KP_LEFT_EYE = 1
KP_RIGHT_EYE = 2
KP_LEFT_EAR = 3
KP_RIGHT_EAR = 4
KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_ELBOW = 7
KP_RIGHT_ELBOW = 8
KP_LEFT_WRIST = 9
KP_RIGHT_WRIST = 10
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12
KP_LEFT_KNEE = 13
KP_RIGHT_KNEE = 14
KP_LEFT_ANKLE = 15
KP_RIGHT_ANKLE = 16

# ─── Alert thresholds (from Ergonomic RA tracker) ───────────────────

RULA_ALERT_THRESHOLD = 5
REBA_ALERT_THRESHOLD = 7
GRACE_SEC = 2.0  # seconds of good posture before resetting duration


# ─── Per-person posture tracking ────────────────────────────────────

@dataclass
class PersonPostureState:
    """Tracks temporal keypoint smoothing and sustained score history."""
    smoothed_kps: Optional[np.ndarray] = None   # (17, 2)
    score_history: deque = field(default_factory=lambda: deque(maxlen=ERGONOMIC_SCORE_WINDOW))
    last_event_time: float = 0.0
    last_seen: float = 0.0
    high_score_start: float = 0.0               # when sustained poor posture started
    # Duration tracking (from Ergonomic RA)
    bad_posture_start: Optional[float] = None
    good_posture_start: Optional[float] = None
    rula_score: Optional[int] = None
    reba_score: Optional[int] = None


# ─── Angle computation (kept for test backward compatibility) ───────

def _angle_between(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Angle at point b formed by rays ba and bc (degrees)."""
    ba = a - b
    bc = c - b
    cos_val = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cos_val, -1.0, 1.0))))


class PostureAnalyzer:
    """Ergonomic risk scoring from pose keypoints.  CPU-only.

    Uses full RULA (1-7) and REBA (1-15) scoring from the
    Ergonomic Risk Assessment project's lookup tables.
    """

    def __init__(self, cooldown_sec: Optional[float] = None) -> None:
        self._states: Dict[int, PersonPostureState] = {}
        self._cooldown_sec = max(0.0, float(cooldown_sec)) if cooldown_sec is not None else POSTURE_COOLDOWN_SEC
        self.last_samples: List[HazardEvent] = []
        logger.info("PostureAnalyzer initialized (full RULA/REBA)")

    @staticmethod
    def _score_side(kp: np.ndarray, kp_conf: np.ndarray, side: str) -> dict:
        angles = compute_angles(
            kp,
            kp_conf,
            side=side,
            confidence_threshold=POSTURE_KEYPOINT_CONF_MIN,
        )
        rula_result = compute_rula(angles)
        reba_result = compute_reba(angles)
        return {
            "side": side,
            "angles": angles,
            "rula_result": rula_result,
            "reba_result": reba_result,
            "rula_score": rula_result["final_score"],
            "reba_score": reba_result["final_score"],
        }

    @staticmethod
    def _score_rank(side_score: dict) -> tuple[int, int]:
        rula_score = int(side_score["rula_score"])
        reba_score = int(side_score["reba_score"])
        return (
            int(rula_score >= 7 or reba_score >= 11),
            int(rula_score >= RULA_ALERT_THRESHOLD or reba_score >= REBA_ALERT_THRESHOLD),
            reba_score,
            rula_score,
        )

    @staticmethod
    def _event_metadata(
        *,
        score: dict,
        valid_mask: np.ndarray,
        kp_conf: np.ndarray,
        sustained: Optional[float] = None,
        score_history: Optional[deque] = None,
    ) -> dict:
        metadata = {
            "rula_score": score["rula_score"],
            "reba_score": score["reba_score"],
            "rula_risk": score["rula_result"]["risk_level"],
            "reba_risk": score["reba_result"]["risk_level"],
            "analysis_side": score["side"],
            "angles": {
                key: round(float(value), 2) if value is not None else None
                for key, value in score["angles"].items()
            },
            "rula_breakdown": score["rula_result"]["breakdown"],
            "reba_breakdown": score["reba_result"]["breakdown"],
            "valid_keypoints": int(np.count_nonzero(valid_mask)),
            "keypoint_conf_min": float(POSTURE_KEYPOINT_CONF_MIN),
            "keypoint_conf_mean": round(float(np.mean(kp_conf)), 3),
        }
        if sustained is not None:
            metadata["sustained_seconds"] = round(sustained, 1)
        if score_history:
            values = [float(v) for v in score_history]
            metadata["score_window_size"] = len(values)
            metadata["rula_score_avg"] = round(sum(values) / len(values), 2)
            metadata["rula_score_max"] = int(max(values))
        return metadata

    def analyze(
        self,
        pose_results: Any,
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        """Compute ergonomic risk for each detected person.

        Args:
            pose_results: Ultralytics Results object with .keypoints attribute.
        """
        events: List[HazardEvent] = []
        self.last_samples = []

        if pose_results is None:
            self._purge_stale(timestamp)
            return events

        # Extract keypoints — shape: (N, 17, 3) where last dim = (x, y, conf)
        kps_data = getattr(pose_results, "keypoints", None)
        if kps_data is None:
            self._purge_stale(timestamp)
            return events

        xy = kps_data.xy          # (N, 17, 2)  on CPU
        conf = kps_data.conf      # (N, 17)

        if xy is None or conf is None:
            self._purge_stale(timestamp)
            return events

        # Convert to numpy
        if hasattr(xy, "cpu"):
            xy_np = xy.cpu().numpy()
            conf_np = conf.cpu().numpy()
        else:
            xy_np = np.array(xy)
            conf_np = np.array(conf)

        if xy_np.ndim != 3 or xy_np.shape[1] < 17 or xy_np.shape[2] < 2:
            self._purge_stale(timestamp)
            return events
        if conf_np.ndim != 2 or conf_np.shape[1] < 17:
            self._purge_stale(timestamp)
            return events

        n_persons = xy_np.shape[0]

        # Get track IDs if available (from boxes)
        boxes = getattr(pose_results, "boxes", None)
        track_ids: List[Optional[int]] = []
        if boxes is not None and boxes.id is not None:
            ids = boxes.id.cpu().numpy() if hasattr(boxes.id, "cpu") else np.array(boxes.id)
            track_ids = [int(i) for i in ids]
        else:
            track_ids = list(range(n_persons))  # fallback to index

        for i in range(n_persons):
            if i >= len(track_ids):
                break
            tid = track_ids[i]
            if tid is None:
                continue

            kp_xy = xy_np[i]       # (17, 2)
            kp_conf = conf_np[i]   # (17,)

            # Apply confidence filter
            valid_mask = kp_conf >= POSTURE_KEYPOINT_CONF_MIN

            # Need minimum keypoints for angle computation
            required = [KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER,
                        KP_LEFT_HIP, KP_RIGHT_HIP]
            if not all(valid_mask[k] for k in required):
                continue

            # Temporal EMA smoothing
            if tid not in self._states:
                self._states[tid] = PersonPostureState(smoothed_kps=kp_xy.copy())
            st = self._states[tid]
            st.last_seen = timestamp

            if st.smoothed_kps is not None:
                alpha = POSTURE_EMA_ALPHA
                # Only smooth valid keypoints
                for k in range(17):
                    if valid_mask[k]:
                        st.smoothed_kps[k] = alpha * kp_xy[k] + (1 - alpha) * st.smoothed_kps[k]
            else:
                st.smoothed_kps = kp_xy.copy()

            kp = st.smoothed_kps  # use smoothed

            # Score both visible sides and use the higher-risk side for alerts.
            side_scores = [
                self._score_side(kp, kp_conf, "left"),
                self._score_side(kp, kp_conf, "right"),
            ]
            score = max(side_scores, key=self._score_rank)
            rula_result = score["rula_result"]
            reba_result = score["reba_result"]
            rula_score = score["rula_score"]
            reba_score = score["reba_score"]
            st.rula_score = rula_score
            st.reba_score = reba_score
            st.score_history.append(rula_score)

            is_risky = (rula_score >= RULA_ALERT_THRESHOLD
                        or reba_score >= REBA_ALERT_THRESHOLD)
            sample_severity = (
                Severity.HIGH
                if rula_score >= 7 or reba_score >= 11
                else Severity.MEDIUM
                if is_risky
                else Severity.LOW
            )
            sample_metadata = self._event_metadata(
                score=score,
                valid_mask=valid_mask,
                kp_conf=kp_conf,
                score_history=st.score_history,
            )
            sample_metadata["record_only"] = True
            self.last_samples.append(HazardEvent(
                event_type="ergonomic_sample",
                severity=sample_severity,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=tid,
                description=f"Ergonomic score sample RULA={rula_score} REBA={reba_score} track={tid}",
                metadata=sample_metadata,
            ))

            # ── Event emission ──────────────────────────────────────
            # Immediate critical (RULA 7, or REBA's very-high-risk band).
            if rula_score >= 7 or reba_score >= 11:
                if timestamp - st.last_event_time >= self._cooldown_sec:
                    st.last_event_time = timestamp
                    st.bad_posture_start = None
                    st.good_posture_start = None
                    events.append(HazardEvent(
                        event_type="dangerous_posture",
                        severity=Severity.CRITICAL,
                        camera_id=camera_id,
                        timestamp=timestamp,
                        frame_number=frame_number,
                        track_id=tid,
                        description=(
                            f"Dangerous posture RULA={rula_score} "
                            f"REBA={reba_score} track={tid}"
                        ),
                        metadata=self._event_metadata(
                            score=score,
                            valid_mask=valid_mask,
                            kp_conf=kp_conf,
                            score_history=st.score_history,
                        ),
                    ))
                continue

            # Duration tracking for sustained poor posture
            if is_risky:
                st.good_posture_start = None
                if st.bad_posture_start is None:
                    st.bad_posture_start = timestamp
                    st.high_score_start = timestamp
                sustained = timestamp - st.bad_posture_start

                if sustained >= POSTURE_SUSTAINED_THRESHOLD:
                    if timestamp - st.last_event_time >= self._cooldown_sec:
                        st.last_event_time = timestamp
                        events.append(HazardEvent(
                            event_type="poor_posture",
                            severity=Severity.HIGH,
                            camera_id=camera_id,
                            timestamp=timestamp,
                            frame_number=frame_number,
                            track_id=tid,
                            description=(
                                f"Sustained poor posture RULA={rula_score} "
                                f"REBA={reba_score} track={tid}"
                            ),
                            metadata=self._event_metadata(
                                score=score,
                                valid_mask=valid_mask,
                                kp_conf=kp_conf,
                                sustained=sustained,
                                score_history=st.score_history,
                            ),
                        ))
                        st.bad_posture_start = None
                        st.high_score_start = 0.0
            else:
                # Recovery grace period
                if st.good_posture_start is None:
                    st.good_posture_start = timestamp
                if timestamp - st.good_posture_start >= GRACE_SEC:
                    st.bad_posture_start = None
                    st.high_score_start = 0.0

        # Purge stale
        self._purge_stale(timestamp)
        return events

    def _purge_stale(self, now: float, timeout: float = 10.0) -> None:
        stale = [tid for tid, st in self._states.items()
                 if now - st.last_seen > timeout]
        for tid in stale:
            del self._states[tid]
