"""
VisionSafe 360 — HazardAnalyzer

CPU-only rule engine: fall detection from pose-tracked person detections.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..config.settings import (
    FALL_ASPECT_RATIO_THRESHOLD,
    FALL_AREA_JITTER_THRESHOLD,
    FALL_CANDIDATE_TIMEOUT,
    FALL_COOLDOWN_SEC,
    FALL_HIP_RATIO_THRESHOLD,
    FALL_HIP_RECOVERY_THRESHOLD,
    FALL_IMMOBILITY_THRESHOLD,
    FALL_TRACK_PURGE_SEC,
    FALL_VELOCITY_THRESHOLD,
    FALL_VELOCITY_WINDOW,
)
from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity

logger = logging.getLogger(__name__)

# Hip keypoint indices (COCO-17) for pose-based fall detection
_KP_LEFT_HIP = 11
_KP_RIGHT_HIP = 12
_KP_CONF_MIN = 0.5


# ─── Fall State Machine ─────────────────────────────────────────────

@dataclass
class PersonFallState:
    """Per-track_id fall detection state."""
    centroid_history: deque = field(default_factory=lambda: deque(maxlen=FALL_VELOCITY_WINDOW))
    aspect_ratio_history: deque = field(default_factory=lambda: deque(maxlen=FALL_VELOCITY_WINDOW))
    area_history: deque = field(default_factory=lambda: deque(maxlen=FALL_VELOCITY_WINDOW))
    state: str = "normal"           # "normal" | "candidate" | "confirmed"
    candidate_since: float = 0.0
    last_event_time: float = 0.0
    last_seen: float = 0.0
    last_hip_ratio: Optional[float] = None
    has_pose_data: bool = False


# ─── Helper Functions ───────────────────────────────────────────────

def _bbox_area(bbox: Tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0, x2 - x1) * max(0, y2 - y1)


def _bbox_centroid(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _bbox_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = _bbox_area(a)
    area_b = _bbox_area(b)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _euclidean(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


# ════════════════════════════════════════════════════════════════════
#  HazardAnalyzer
# ════════════════════════════════════════════════════════════════════

class HazardAnalyzer:
    """CPU-only fall detection rule engine.  Zero GPU calls inside."""

    def __init__(
        self,
        fall_enabled: bool = True,
        **kwargs,
    ) -> None:
        self.fall_enabled = fall_enabled

        # Fall state machines per track_id
        self._fall_states: Dict[int, PersonFallState] = {}

        logger.info("HazardAnalyzer init — fall=%s", fall_enabled)

    # ── Public API ──────────────────────────────────────────────────

    def analyze(
        self,
        detections: List[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
        *,
        fall_this_frame: bool = True,
        pose_results=None,
        **kwargs,
    ) -> List[HazardEvent]:
        """Run fall detection.  Returns (possibly empty) list of events."""
        events: List[HazardEvent] = []

        persons = [d for d in detections if d.class_name == "person"]

        if self.fall_enabled and fall_this_frame:
            pose_entries = self._extract_pose_entries(pose_results)
            events.extend(self._fall_detection(
                persons, camera_id, frame_number, timestamp,
                pose_entries=pose_entries,
            ))
            self._purge_stale_tracks(timestamp)

        return events

    # ── Pose Keypoint Extraction (for fall detection) ─────────────────

    @staticmethod
    def _extract_pose_entries(pose_results) -> List:
        """Extract (bbox, keypoints, confs) tuples from pose results."""
        if pose_results is None:
            return []
        kps_data = getattr(pose_results, "keypoints", None)
        if kps_data is None:
            return []

        xy = kps_data.xy
        conf = kps_data.conf
        boxes = getattr(pose_results, "boxes", None)
        if xy is None or conf is None or boxes is None:
            return []

        import numpy as np
        xy_np = xy.cpu().numpy() if hasattr(xy, "cpu") else np.array(xy)
        conf_np = conf.cpu().numpy() if hasattr(conf, "cpu") else np.array(conf)
        boxes_np = boxes.xyxy.cpu().numpy() if hasattr(boxes.xyxy, "cpu") else np.array(boxes.xyxy)

        entries = []
        for i in range(xy_np.shape[0]):
            bbox = (int(boxes_np[i][0]), int(boxes_np[i][1]),
                    int(boxes_np[i][2]), int(boxes_np[i][3]))
            entries.append((bbox, xy_np[i], conf_np[i]))
        return entries

    @staticmethod
    def _find_matching_keypoints(
        person_bbox: Tuple[int, int, int, int],
        pose_entries: List,
    ) -> Tuple[Optional[object], Optional[object]]:
        """Find pose keypoints best matching a person's bbox by IoU."""
        best_iou = 0.3  # minimum match threshold
        best_kps = None
        best_conf = None
        for (pose_bbox, kps, conf) in pose_entries:
            iou = _bbox_iou(person_bbox, pose_bbox)
            if iou > best_iou:
                best_iou = iou
                best_kps = kps
                best_conf = conf
        return best_kps, best_conf

    # ── Fall Detection State Machine ────────────────────────────────

    def _fall_detection(
        self,
        persons: List[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
        pose_entries: Optional[List] = None,
    ) -> List[HazardEvent]:
        """Pose-aware fall detection integrated from the fd/ standalone project.

        Trigger conditions (any of):
          1. aspect_ratio > 0.85 AND was_upright recently
          2. hip_ratio < 0.2 (pose keypoints, when available)
          3. rapid downward velocity AND aspect_ratio > 0.8

        Confirmation: elapsed >= 2.0s in candidate state.
        Recovery: hip_ratio > 0.6 (pose) OR aspect_ratio < 0.8 (bbox fallback).
        """
        events: List[HazardEvent] = []
        if pose_entries is None:
            pose_entries = []

        for person in persons:
            tid = person.track_id
            if tid is None:
                continue

            x1, y1, x2, y2 = person.bbox
            w = x2 - x1
            h = y2 - y1
            if h <= 0 or w <= 0:
                continue

            aspect_ratio = w / h
            centroid = _bbox_centroid(person.bbox)
            area = _bbox_area(person.bbox)

            # Get or create state
            if tid not in self._fall_states:
                self._fall_states[tid] = PersonFallState()
            st = self._fall_states[tid]
            st.last_seen = timestamp
            st.centroid_history.append(centroid)
            st.aspect_ratio_history.append(aspect_ratio)
            st.area_history.append(area)

            # ── Compute hip_ratio from pose keypoints ───────────────
            hip_ratio = None
            if pose_entries:
                kps, kp_conf = self._find_matching_keypoints(person.bbox, pose_entries)
                if (kps is not None and kp_conf is not None
                        and kp_conf[_KP_LEFT_HIP] >= _KP_CONF_MIN
                        and kp_conf[_KP_RIGHT_HIP] >= _KP_CONF_MIN):
                    hip_y = (kps[_KP_LEFT_HIP][1] + kps[_KP_RIGHT_HIP][1]) / 2.0
                    hip_ratio = (y2 - hip_y) / h
                    st.last_hip_ratio = hip_ratio
                    st.has_pose_data = True

            # ── State machine ───────────────────────────────────────
            if st.state == "normal":
                triggered = False

                # Condition 1: aspect ratio (lowered from 1.0 to 0.85 per fd/ model)
                if (len(st.aspect_ratio_history) >= 3
                        and aspect_ratio > FALL_ASPECT_RATIO_THRESHOLD):
                    prev_ratios = list(st.aspect_ratio_history)[:-1]
                    was_upright = any(r < 0.8 for r in prev_ratios[-3:])
                    if was_upright:
                        triggered = True

                # Condition 2: hip_ratio from pose (NEW from fd/ project)
                if hip_ratio is not None and hip_ratio < FALL_HIP_RATIO_THRESHOLD:
                    prev_ratios = list(st.aspect_ratio_history)[:-1]
                    was_upright = any(r < 0.8 for r in prev_ratios[-3:]) if len(prev_ratios) >= 1 else True
                    if was_upright:
                        triggered = True

                # Condition 3: rapid downward velocity (kept as secondary)
                if len(st.centroid_history) >= 2:
                    dy = st.centroid_history[-1][1] - st.centroid_history[0][1]
                    dt = len(st.centroid_history) - 1
                    velocity = dy / dt if dt > 0 else 0.0
                    if velocity > FALL_VELOCITY_THRESHOLD and aspect_ratio > 0.8:
                        triggered = True

                if triggered:
                    st.state = "candidate"
                    st.candidate_since = timestamp

            elif st.state == "candidate":
                # Recovery check
                recovered = False
                if hip_ratio is not None:
                    # Pose-based recovery (from fd/ project)
                    if hip_ratio > FALL_HIP_RECOVERY_THRESHOLD:
                        recovered = True
                else:
                    # Bbox fallback recovery
                    if aspect_ratio < 0.8:
                        recovered = True

                if recovered:
                    st.state = "normal"
                    continue

                # Confirmation: time-based (matching fd/ model's approach)
                elapsed = timestamp - st.candidate_since
                if elapsed >= FALL_CANDIDATE_TIMEOUT:
                    # When no pose data, add immobility check as extra safety
                    confirmed = True
                    if not st.has_pose_data and len(st.centroid_history) >= 2:
                        c0 = st.centroid_history[0]
                        c1 = st.centroid_history[-1]
                        movement = _euclidean(c0, c1)
                        if movement > FALL_IMMOBILITY_THRESHOLD:
                            confirmed = False

                    if confirmed:
                        st.state = "confirmed"
                        if timestamp - st.last_event_time >= FALL_COOLDOWN_SEC:
                            st.last_event_time = timestamp
                            metadata = {
                                "aspect_ratio": round(aspect_ratio, 2),
                                "duration_seconds": round(elapsed, 1),
                            }
                            if hip_ratio is not None:
                                metadata["hip_ratio"] = round(hip_ratio, 3)
                            events.append(HazardEvent(
                                event_type="fall_confirmed",
                                severity=Severity.CRITICAL,
                                camera_id=camera_id,
                                timestamp=timestamp,
                                frame_number=frame_number,
                                track_id=tid,
                                bbox=person.bbox,
                                description=f"Fall confirmed track={tid}",
                                metadata=metadata,
                            ))

            elif st.state == "confirmed":
                # Recovery from confirmed state
                recovered = False
                if hip_ratio is not None and hip_ratio > FALL_HIP_RECOVERY_THRESHOLD:
                    recovered = True
                elif aspect_ratio < 0.8:
                    recovered = True
                if recovered:
                    st.state = "normal"

        return events

    # ── Housekeeping ────────────────────────────────────────────────

    def _purge_stale_tracks(self, now: float) -> None:
        """Remove fall states for track_ids absent for > FALL_TRACK_PURGE_SEC."""
        stale = [
            tid for tid, st in self._fall_states.items()
            if now - st.last_seen > FALL_TRACK_PURGE_SEC
        ]
        for tid in stale:
            del self._fall_states[tid]
