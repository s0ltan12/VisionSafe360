"""PPE compliance analyzer.

Converts PPE detector outputs such as ``helmet_off`` and ``vest_off`` into
HazardEvent objects. EventAggregator handles the 3 second persistence and
50 second cooldown policy.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Tuple

from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity


_NEGATIVE_PPE: dict[str, tuple[str, str, Severity]] = {
    "helmet_off": ("helmet", "ppe_missing_helmet", Severity.HIGH),
    "vest_off": ("safety_vest", "ppe_missing_vest", Severity.HIGH),
    "gloves_off": ("gloves", "ppe_missing_gloves", Severity.MEDIUM),
    "bare_foot": ("safety_shoes", "ppe_missing_shoes", Severity.HIGH),
}


def _center(bbox: Tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


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


def _contains_point(bbox: Tuple[int, int, int, int], point: tuple[float, float]) -> bool:
    x, y = point
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


class PPEAnalyzer:
    """Create PPE missing hazard candidates from detector outputs."""

    def analyze(
        self,
        *,
        ppe_detections: Iterable[Detection],
        tracked_people: Iterable[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        people = [d for d in tracked_people if d.class_name == "person"]
        if not people:
            return []

        events: List[HazardEvent] = []
        for ppe in ppe_detections:
            spec = _NEGATIVE_PPE.get(ppe.class_name)
            if spec is None:
                continue

            person = self._match_person(ppe, people)
            if person is None:
                continue

            item, event_type, severity = spec
            raw_track_id = person.track_id
            track_id = raw_track_id if raw_track_id is not None else 1
            has_stable_track = raw_track_id is not None and int(raw_track_id) > 0
            events.append(HazardEvent(
                event_type=event_type,
                severity=severity,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=track_id,
                bbox=person.bbox,
                description=f"PPE missing: {item.replace('_', ' ')} track={track_id}",
                metadata={
                    "ppe_item": item,
                    "ppe_detection": ppe.class_name,
                    "ppe_detection_bbox": ppe.bbox,
                    "confidence": round(float(ppe.confidence), 4),
                    "person_bbox": person.bbox,
                    "worker_track_id": raw_track_id,
                    "worker_track_id_valid": has_stable_track,
                    "worker_track_id_fallback": not has_stable_track,
                    "worker_track_id_source": "bytetrack" if has_stable_track else "fallback",
                    "composite_eligible": has_stable_track,
                },
            ))

        return events

    @staticmethod
    def _match_person(ppe: Detection, people: list[Detection]) -> Optional[Detection]:
        ppe_center = _center(ppe.bbox)
        best_person: Optional[Detection] = None
        best_score = -1.0

        for person in people:
            iou_score = _iou(ppe.bbox, person.bbox)
            contained = _contains_point(person.bbox, ppe_center)
            px, py = _center(person.bbox)
            cx, cy = ppe_center
            distance = math.hypot(px - cx, py - cy)
            person_w = max(1, person.bbox[2] - person.bbox[0])
            person_h = max(1, person.bbox[3] - person.bbox[1])
            normalized_distance = distance / max(person_w, person_h)

            score = iou_score
            if contained:
                score += 0.5
            score -= min(normalized_distance, 2.0) * 0.05

            if score > best_score:
                best_score = score
                best_person = person

        if best_person is None:
            return None
        if best_score < 0.02:
            return None
        return best_person
