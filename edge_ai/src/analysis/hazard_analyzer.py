"""
VisionSafe 360 — HazardAnalyzer

CPU-only rule engine: fall detection from pose-tracked person detections.
"""
from __future__ import annotations

import logging
import math
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
    FALL_SEATED_GUARD_AR_SPREAD,
    FALL_SEATED_GUARD_DY,
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
    last_event_time: float = float("-inf")
    last_seen: float = 0.0
    last_hip_ratio: Optional[float] = None
    has_pose_data: bool = False
    track_first_seen: float = 0.0
    candidate_event_emitted: bool = False
    recovered_event_emitted: bool = False
    trigger_reason: str = ""
    last_velocity: Optional[float] = None
    last_valid_keypoint_count: int = 0
    last_bbox: Optional[Tuple[int, int, int, int]] = None


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _positive(value: float, fallback: float) -> float:
    return value if value > 0 else fallback


def _non_negative(value: float, fallback: float) -> float:
    return value if value >= 0 else fallback


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
        self._cfg = self._validated_config()

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

    @staticmethod
    def _validated_config() -> dict:
        """Return fall thresholds with defensive bounds for runtime safety."""
        return {
            "aspect_ratio_threshold": _positive(FALL_ASPECT_RATIO_THRESHOLD, 0.90),
            "hip_ratio_threshold": _clamp(FALL_HIP_RATIO_THRESHOLD, 0.0, 1.0),
            "hip_recovery_threshold": _clamp(FALL_HIP_RECOVERY_THRESHOLD, 0.0, 1.0),
            "velocity_threshold": _positive(FALL_VELOCITY_THRESHOLD, 15.0),
            "candidate_timeout": _positive(FALL_CANDIDATE_TIMEOUT, 2.5),
            "immobility_threshold": _non_negative(FALL_IMMOBILITY_THRESHOLD, 5.0),
            # Retained for backwards-compatible tuning; currently observability-only.
            "area_jitter_threshold": _non_negative(FALL_AREA_JITTER_THRESHOLD, 0.15),
            "seated_guard_dy": _non_negative(FALL_SEATED_GUARD_DY, 6.0),
            "seated_guard_ar_spread": _non_negative(FALL_SEATED_GUARD_AR_SPREAD, 0.10),
            "cooldown_sec": _non_negative(FALL_COOLDOWN_SEC, 50.0),
            "track_purge_sec": _positive(FALL_TRACK_PURGE_SEC, 5.0),
        }

    @staticmethod
    def _valid_keypoint_count(kp_conf) -> int:
        if kp_conf is None:
            return 0
        try:
            return int(sum(1 for value in kp_conf if float(value) >= _KP_CONF_MIN))
        except TypeError:
            return 0

    def _candidate_metadata(
        self,
        *,
        st: PersonFallState,
        timestamp: float,
        aspect_ratio: float,
        hip_ratio: Optional[float],
        velocity: Optional[float],
        movement: Optional[float] = None,
        immobile: Optional[bool] = None,
    ) -> dict:
        elapsed = max(0.0, timestamp - st.candidate_since) if st.candidate_since else 0.0
        metadata = {
            "aspect_ratio": round(aspect_ratio, 2),
            "duration_seconds": round(elapsed, 1),
            "candidate_duration": round(elapsed, 3),
            "pose_available": st.has_pose_data,
            "valid_keypoint_count": st.last_valid_keypoint_count,
            "track_age": round(max(0.0, timestamp - st.track_first_seen), 3) if st.track_first_seen else 0.0,
            "centroid_history_length": len(st.centroid_history),
            "trigger_reason": st.trigger_reason or "unknown",
            "area_jitter_threshold": self._cfg["area_jitter_threshold"],
        }
        if hip_ratio is not None:
            metadata["hip_ratio"] = round(float(hip_ratio), 3)
        if velocity is not None:
            metadata["velocity"] = round(float(velocity), 3)
        if movement is not None:
            metadata["movement_px"] = round(float(movement), 3)
        if immobile is not None:
            metadata["immobile"] = bool(immobile)
        metadata["confidence"] = self._confidence_score(
            aspect_ratio=aspect_ratio,
            hip_ratio=hip_ratio,
            velocity=velocity,
            candidate_duration=elapsed,
            pose_available=st.has_pose_data,
            immobile=bool(immobile),
        )
        return metadata

    def _confidence_score(
        self,
        *,
        aspect_ratio: float,
        hip_ratio: Optional[float],
        velocity: Optional[float],
        candidate_duration: float,
        pose_available: bool,
        immobile: bool,
    ) -> float:
        ar_signal = _clamp(
            (aspect_ratio - self._cfg["aspect_ratio_threshold"]) / max(self._cfg["aspect_ratio_threshold"], 0.1),
            0.0,
            1.0,
        )
        hip_signal = 0.0
        if hip_ratio is not None:
            hip_signal = _clamp(
                (self._cfg["hip_ratio_threshold"] - hip_ratio) / max(self._cfg["hip_ratio_threshold"], 0.05),
                0.0,
                1.0,
            )
        velocity_signal = 0.0
        if velocity is not None:
            velocity_signal = _clamp(
                velocity / max(self._cfg["velocity_threshold"] * 2.0, 1.0),
                0.0,
                1.0,
            )
        duration_signal = _clamp(
            candidate_duration / max(self._cfg["candidate_timeout"], 0.1),
            0.0,
            1.0,
        )
        pose_signal = 1.0 if pose_available else 0.45
        immobility_signal = 1.0 if immobile else 0.35
        score = (
            0.25 * ar_signal
            + 0.20 * hip_signal
            + 0.15 * velocity_signal
            + 0.20 * duration_signal
            + 0.10 * pose_signal
            + 0.10 * immobility_signal
        )
        return round(_clamp(score, 0.0, 1.0), 3)

    def _state_transfer_candidate(
        self,
        tid: int,
        person: Detection,
        timestamp: float,
    ) -> Optional[PersonFallState]:
        """Transfer recent fall state across short high-overlap track fragmentation."""
        best_tid = None
        best_iou = 0.70
        for old_tid, old_state in self._fall_states.items():
            if old_tid == tid or old_state.last_bbox is None:
                continue
            if timestamp - old_state.last_seen > min(1.0, self._cfg["track_purge_sec"]):
                continue
            if old_state.state not in {"candidate", "confirmed"}:
                continue
            iou = _bbox_iou(person.bbox, old_state.last_bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = old_tid
        if best_tid is None:
            return None
        st = self._fall_states.pop(best_tid)
        logger.info(
            "fall state transferred old_track=%s new_track=%s iou=%.2f state=%s",
            best_tid,
            tid,
            best_iou,
            st.state,
        )
        return st

    def _make_event(
        self,
        *,
        event_type: str,
        severity: Severity,
        camera_id: str,
        timestamp: float,
        frame_number: int,
        track_id: int,
        bbox: Tuple[int, int, int, int],
        description: str,
        metadata: dict,
    ) -> HazardEvent:
        return HazardEvent(
            event_type=event_type,
            severity=severity,
            camera_id=camera_id,
            timestamp=timestamp,
            frame_number=frame_number,
            track_id=track_id,
            bbox=bbox,
            description=description,
            metadata=metadata,
        )

    @staticmethod
    def _mark_internal_lifecycle(metadata: dict) -> dict:
        """Keep lifecycle events visible inside edge logs but out of alert routing."""
        return {
            **metadata,
            "suppress_event": True,
            "operational_alert": False,
            "internal_lifecycle_event": True,
        }

    @staticmethod
    def _log_lifecycle_event(event: HazardEvent) -> None:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        logger.info(
            "fall lifecycle event event_type=%s camera_id=%s track_id=%s confidence=%s trigger_reason=%s",
            event.event_type,
            event.camera_id,
            event.track_id,
            metadata.get("confidence"),
            metadata.get("trigger_reason"),
        )

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
                self._fall_states[tid] = self._state_transfer_candidate(tid, person, timestamp) or PersonFallState()
            st = self._fall_states[tid]
            if st.track_first_seen <= 0:
                st.track_first_seen = timestamp
            st.last_seen = timestamp
            st.centroid_history.append(centroid)
            st.aspect_ratio_history.append(aspect_ratio)
            st.area_history.append(area)
            st.last_bbox = person.bbox
            prev_hip_ratio = st.last_hip_ratio

            # ── Compute hip_ratio from pose keypoints ───────────────
            hip_ratio = None
            valid_keypoint_count = 0
            if pose_entries:
                kps, kp_conf = self._find_matching_keypoints(person.bbox, pose_entries)
                valid_keypoint_count = self._valid_keypoint_count(kp_conf)
                st.last_valid_keypoint_count = valid_keypoint_count
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
                trigger_reasons: list[str] = []

                recent_ratios = list(st.aspect_ratio_history)[-5:]
                ar_spread = (max(recent_ratios) - min(recent_ratios)) if len(recent_ratios) >= 2 else 1.0
                recent_centroids = list(st.centroid_history)[-5:]
                dy_recent = (
                    recent_centroids[-1][1] - recent_centroids[0][1]
                    if len(recent_centroids) >= 2
                    else FALL_SEATED_GUARD_DY + 1.0
                )
                seated_like_low_posture = (
                    aspect_ratio > self._cfg["aspect_ratio_threshold"]
                    and abs(dy_recent) <= self._cfg["seated_guard_dy"]
                    and ar_spread <= self._cfg["seated_guard_ar_spread"]
                )

                # Condition 1: aspect ratio (lowered from 1.0 to 0.85 per fd/ model)
                if (len(st.aspect_ratio_history) >= 3
                        and aspect_ratio > self._cfg["aspect_ratio_threshold"]):
                    prev_ratios = list(st.aspect_ratio_history)[:-1]
                    was_upright = any(r < 0.8 for r in prev_ratios[-3:])
                    if was_upright:
                        triggered = True
                        trigger_reasons.append("aspect_ratio")

                # Condition 2: hip_ratio from pose (NEW from fd/ project)
                if hip_ratio is not None and hip_ratio < self._cfg["hip_ratio_threshold"]:
                    prev_ratios = list(st.aspect_ratio_history)[:-1]
                    was_upright = any(r < 0.8 for r in prev_ratios[-3:]) if len(prev_ratios) >= 2 else False
                    hip_drop_is_sudden = (
                        prev_hip_ratio is not None
                        and (prev_hip_ratio - hip_ratio) >= 0.08
                    )
                    if (was_upright or hip_drop_is_sudden) and not seated_like_low_posture:
                        triggered = True
                        trigger_reasons.append("hip_ratio")

                # Condition 3: rapid downward velocity (kept as secondary)
                velocity = None
                if len(st.centroid_history) >= 2:
                    dy = st.centroid_history[-1][1] - st.centroid_history[0][1]
                    dt = len(st.centroid_history) - 1
                    velocity = dy / dt if dt > 0 else 0.0
                    st.last_velocity = velocity
                    if velocity > self._cfg["velocity_threshold"] and aspect_ratio > 0.8:
                        triggered = True
                        trigger_reasons.append("velocity")

                if triggered:
                    st.state = "candidate"
                    st.candidate_since = timestamp
                    st.candidate_event_emitted = True
                    st.recovered_event_emitted = False
                    st.trigger_reason = "+".join(trigger_reasons) if trigger_reasons else "unknown"
                    metadata = self._candidate_metadata(
                        st=st,
                        timestamp=timestamp,
                        aspect_ratio=aspect_ratio,
                        hip_ratio=hip_ratio,
                        velocity=st.last_velocity,
                    )
                    event = self._make_event(
                        event_type="fall_candidate",
                        severity=Severity.HIGH,
                        camera_id=camera_id,
                        timestamp=timestamp,
                        frame_number=frame_number,
                        track_id=tid,
                        bbox=person.bbox,
                        description=f"Fall candidate track={tid}",
                        metadata=self._mark_internal_lifecycle(metadata),
                    )
                    self._log_lifecycle_event(event)
                    events.append(event)

            elif st.state == "candidate":
                # Recovery check
                recovered = False
                if hip_ratio is not None:
                    # Pose-based recovery (from fd/ project)
                    if hip_ratio > self._cfg["hip_recovery_threshold"]:
                        recovered = True
                else:
                    # Bbox fallback recovery
                    if aspect_ratio < 0.8:
                        recovered = True

                if recovered:
                    if not st.recovered_event_emitted:
                        metadata = self._candidate_metadata(
                            st=st,
                            timestamp=timestamp,
                            aspect_ratio=aspect_ratio,
                            hip_ratio=hip_ratio,
                            velocity=st.last_velocity,
                        )
                        metadata["recovered_from_state"] = "candidate"
                        event = self._make_event(
                            event_type="fall_recovered",
                            severity=Severity.LOW,
                            camera_id=camera_id,
                            timestamp=timestamp,
                            frame_number=frame_number,
                            track_id=tid,
                            bbox=person.bbox,
                            description=f"Fall recovered track={tid}",
                            metadata=self._mark_internal_lifecycle(metadata),
                        )
                        self._log_lifecycle_event(event)
                        events.append(event)
                        st.recovered_event_emitted = True
                    st.state = "normal"
                    st.candidate_event_emitted = False
                    continue

                # Confirmation: time-based (matching fd/ model's approach)
                elapsed = timestamp - st.candidate_since
                if elapsed >= self._cfg["candidate_timeout"]:
                    # When no pose data, add immobility check as extra safety
                    confirmed = True
                    movement = None
                    immobile = None
                    if not st.has_pose_data and len(st.centroid_history) >= 2:
                        c0 = st.centroid_history[0]
                        c1 = st.centroid_history[-1]
                        movement = _euclidean(c0, c1)
                        immobile = movement <= self._cfg["immobility_threshold"]
                        if not immobile:
                            confirmed = False

                    if confirmed:
                        st.state = "confirmed"
                        if timestamp - st.last_event_time >= self._cfg["cooldown_sec"]:
                            st.last_event_time = timestamp
                            metadata = self._candidate_metadata(
                                st=st,
                                timestamp=timestamp,
                                aspect_ratio=aspect_ratio,
                                hip_ratio=hip_ratio,
                                velocity=st.last_velocity,
                                movement=movement,
                                immobile=immobile,
                            )
                            events.append(self._make_event(
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
                if hip_ratio is not None and hip_ratio > self._cfg["hip_recovery_threshold"]:
                    recovered = True
                elif aspect_ratio < 0.8:
                    recovered = True
                if recovered:
                    if not st.recovered_event_emitted:
                        metadata = self._candidate_metadata(
                            st=st,
                            timestamp=timestamp,
                            aspect_ratio=aspect_ratio,
                            hip_ratio=hip_ratio,
                            velocity=st.last_velocity,
                        )
                        metadata["recovered_from_state"] = "confirmed"
                        event = self._make_event(
                            event_type="fall_recovered",
                            severity=Severity.LOW,
                            camera_id=camera_id,
                            timestamp=timestamp,
                            frame_number=frame_number,
                            track_id=tid,
                            bbox=person.bbox,
                            description=f"Fall recovered track={tid}",
                            metadata=self._mark_internal_lifecycle(metadata),
                        )
                        self._log_lifecycle_event(event)
                        events.append(event)
                        st.recovered_event_emitted = True
                    st.state = "normal"
                    st.candidate_event_emitted = False

        return events

    # ── Housekeeping ────────────────────────────────────────────────

    def _purge_stale_tracks(self, now: float) -> None:
        """Remove fall states for track_ids absent for > FALL_TRACK_PURGE_SEC."""
        stale = [
            tid for tid, st in self._fall_states.items()
            if now - st.last_seen > self._cfg["track_purge_sec"]
        ]
        for tid in stale:
            del self._fall_states[tid]
