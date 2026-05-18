"""
VisionSafe 360 - ProximityAnalyzer

Rule-based forklift proximity hazards from detector outputs.

Inputs:
- Person detections (tracked from pose model)
- Forklift detections (from optional second detect model)

Outputs:
- HazardEvent("forklift_proximity_warning", MEDIUM)
- HazardEvent("forklift_proximity_danger", HIGH)
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from ..config.settings import PROXIMITY_DANGER_PX, PROXIMITY_WARNING_PX
from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity


def _center(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _distance_px(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class ProximityAnalyzer:
    """Compute forklift-person proximity hazards from detections."""

    def __init__(self, danger_px: float = PROXIMITY_DANGER_PX, warning_px: float = PROXIMITY_WARNING_PX) -> None:
        self._danger_px = float(danger_px)
        self._warning_px = max(float(warning_px), self._danger_px)

    @staticmethod
    def _assign_track_id(person_bbox: Tuple[int, int, int, int], tracked_people: List[Detection]) -> Optional[int]:
        """Match untracked person bbox to a tracked pose person by IoU or distance.

        Returns None when no plausible match is found; callers should treat that
        as an unattributed hazard rather than guessing a worker.
        """
        # 1. Try matching with normal IoU
        best_tid = None
        best_iou = 0.2
        for p in tracked_people:
            if p.track_id is None:
                continue
            iou = _iou(person_bbox, p.bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = p.track_id
        if best_tid is not None:
            return best_tid

        # 2. Try matching with very low IoU (generous)
        best_iou = 0.02
        for p in tracked_people:
            if p.track_id is None:
                continue
            iou = _iou(person_bbox, p.bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = p.track_id
        if best_tid is not None:
            return best_tid

        # 3. Try matching with center distance (within 250 pixels)
        min_dist = 250.0
        px, py = _center(person_bbox)
        for p in tracked_people:
            if p.track_id is None:
                continue
            tx, ty = _center(p.bbox)
            dist = math.hypot(px - tx, py - ty)
            if dist < min_dist:
                min_dist = dist
                best_tid = p.track_id
        if best_tid is not None:
            return best_tid

        # 4. If exactly one tracked person exists in the frame, assign their track ID
        valid_tracks = [p.track_id for p in tracked_people if p.track_id is not None]
        if len(valid_tracks) == 1:
            return valid_tracks[0]

        return None

    def analyze(
        self,
        detections: List[Detection],
        tracked_pose_people: List[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        forklifts = [d for d in detections if d.class_name == "forklift"]
        persons = [d for d in detections if d.class_name == "person"]

        events: List[HazardEvent] = []
        if not forklifts or not persons:
            return events

        for person in persons:
            track_id = person.track_id
            if track_id is None:
                track_id = self._assign_track_id(person.bbox, tracked_pose_people)

            nearest = min((_distance_px(person.bbox, f.bbox), f) for f in forklifts)
            dist_px, near_forklift = nearest

            if dist_px <= self._danger_px:
                event_type = "forklift_proximity_danger"
                sev = Severity.HIGH
            elif dist_px <= self._warning_px:
                event_type = "forklift_proximity_warning"
                sev = Severity.MEDIUM
            else:
                continue

            events.append(HazardEvent(
                event_type=event_type,
                severity=sev,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=track_id,
                bbox=person.bbox,
                description=f"Forklift proximity risk (dist={dist_px:.1f}px)",
                metadata={
                    "distance_px": round(dist_px, 1),
                    "forklift_bbox": near_forklift.bbox,
                },
            ))

        return events
