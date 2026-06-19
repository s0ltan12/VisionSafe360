"""PPE compliance analyzer.

Converts PPE detector outputs such as ``helmet_off`` and ``vest_off`` into
HazardEvent objects. EventAggregator handles the 3 second persistence and
50 second cooldown policy.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List, Tuple

from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity
from .ppe_rules import (
    PPE_SEVERITY_RANK,
    detection_negative_spec,
    match_person_for_ppe,
    ppe_missing_title,
)


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

        grouped: dict[tuple[int, Tuple[int, int, int, int]], list[tuple[Detection, str, str, Severity]]] = defaultdict(list)
        matched_people: dict[tuple[int, Tuple[int, int, int, int]], Detection] = {}
        for ppe in ppe_detections:
            spec = detection_negative_spec(ppe.class_name)
            if spec is None:
                continue

            person = match_person_for_ppe(ppe, people)
            if person is None:
                continue

            item, event_type, severity = spec
            track_id = person.track_id if person.track_id is not None else 1
            key = (track_id, person.bbox)
            grouped[key].append((ppe, item, event_type, severity))
            matched_people[key] = person

        events: List[HazardEvent] = []
        for key, violations in grouped.items():
            track_id, _ = key
            person = matched_people[key]
            raw_track_id = person.track_id
            has_stable_track = raw_track_id is not None and int(raw_track_id) > 0
            highest_severity = max(
                (violation[3] for violation in violations),
                key=lambda severity: PPE_SEVERITY_RANK.get(severity, 0),
            )
            missing_items = list(dict.fromkeys(item for _, item, _, _ in violations))
            source_event_types = list(dict.fromkeys(event_type for _, _, event_type, _ in violations))
            detections = [
                {
                    "ppe_item": item,
                    "ppe_detection": ppe.class_name,
                    "ppe_detection_bbox": ppe.bbox,
                    "event_type": event_type,
                    "confidence": round(float(ppe.confidence), 4),
                }
                for ppe, item, event_type, _ in violations
            ]
            title = ppe_missing_title(missing_items)
            primary_item = missing_items[0] if missing_items else "ppe"
            events.append(HazardEvent(
                event_type="ppe_missing",
                severity=highest_severity,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=track_id,
                bbox=person.bbox,
                description=f"{title} track={track_id}",
                metadata={
                    "display_title": title,
                    "alert_title": title,
                    "ppe_item": primary_item,
                    "ppe_items": missing_items,
                    "missing_ppe_items": missing_items,
                    "ppe_detection": detections[0]["ppe_detection"] if detections else None,
                    "ppe_detection_bbox": detections[0]["ppe_detection_bbox"] if detections else None,
                    "ppe_detections": detections,
                    "ppe_source_event_types": source_event_types,
                    "confidence": max((item["confidence"] for item in detections), default=None),
                    "person_bbox": person.bbox,
                    "worker_track_id": raw_track_id,
                    "worker_track_id_valid": has_stable_track,
                    "worker_track_id_fallback": not has_stable_track,
                    "worker_track_id_source": "bytetrack" if has_stable_track else "fallback",
                    "composite_eligible": has_stable_track,
                },
            ))

        return events
