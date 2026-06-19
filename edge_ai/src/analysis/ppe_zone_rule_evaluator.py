"""PPE alert gating and zone-specific requirement evaluation."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Tuple

from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from .ppe_rules import (
    detection_negative_spec,
    detection_present_item,
    highest_ppe_severity,
    match_person_for_ppe,
    normalize_required_ppe,
    person_detection_key,
    ppe_items_phrase,
)
from .safety_zone_engine import SafetyZone, SafetyZoneEngine


class PPEZoneRuleEvaluator:
    """Evaluate PPE violations only for workers inside configured PPE zones."""

    def __init__(self, safety_zone_engine: SafetyZoneEngine) -> None:
        self._safety_zone_engine = safety_zone_engine

    def evaluate(
        self,
        *,
        ppe_detections: Iterable[Detection],
        tracked_people: Iterable[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
        frame_shape: tuple[int, ...] | None = None,
    ) -> list[HazardEvent]:
        people = [d for d in tracked_people if d.class_name == "person"]
        if not people:
            return []

        ppe_list = list(ppe_detections)
        present_by_person: dict[tuple[int | None, Tuple[int, int, int, int]], set[str]] = defaultdict(set)
        negative_by_person: dict[tuple[int | None, Tuple[int, int, int, int]], set[str]] = defaultdict(set)

        for ppe in ppe_list:
            present_item = detection_present_item(ppe.class_name)
            negative_spec = detection_negative_spec(ppe.class_name)
            if present_item is None and negative_spec is None:
                continue
            person = match_person_for_ppe(ppe, people)
            if person is None:
                continue
            key = person_detection_key(person)
            if present_item is not None:
                present_by_person[key].add(present_item)
            if negative_spec is not None:
                negative_by_person[key].add(negative_spec[0])

        events: list[HazardEvent] = []
        for person in people:
            ppe_zones = self._safety_zone_engine.ppe_zones_for_person(
                person,
                camera_id=camera_id,
                frame_shape=frame_shape,
            )
            if not ppe_zones:
                continue

            required_items = _combined_required_ppe(ppe_zones)
            if not required_items:
                continue

            person_key = person_detection_key(person)
            present_items = present_by_person.get(person_key, set())
            negative_items = negative_by_person.get(person_key, set())
            if not present_items and not negative_items:
                continue
            missing_items = [
                item for item in required_items
                if item not in present_items
            ]
            if not missing_items:
                continue

            track_id = person.track_id if person.track_id is not None else 1
            raw_track_id = person.track_id
            has_stable_track = raw_track_id is not None and int(raw_track_id) > 0
            primary_zone = ppe_zones[0]
            zone_ids = [zone.id for zone in ppe_zones]
            zone_names = [zone.name for zone in ppe_zones]
            title = _alert_title(missing_items)
            detections = [
                {
                    "ppe_item": item,
                    "event_type": _source_event_type(item),
                }
                for item in missing_items
            ]
            events.append(HazardEvent(
                event_type="ppe_missing",
                severity=highest_ppe_severity(missing_items),
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=track_id,
                bbox=person.bbox,
                description=f"{title} track={track_id}",
                metadata={
                    "display_title": title,
                    "alert_title": title,
                    "ppe_zone": True,
                    "safety_zone": True,
                    "safety_zone_id": primary_zone.id,
                    "safety_zone_name": primary_zone.name,
                    "safety_zone_type": primary_zone.zone_type,
                    "safety_zone_snapshot": _zone_snapshot(primary_zone),
                    "ppe_zone_ids": zone_ids,
                    "ppe_zone_names": zone_names,
                    "zone": primary_zone.name,
                    "zone_color": primary_zone.color,
                    "zone_priority": primary_zone.priority,
                    "zone_rules": primary_zone.rules,
                    "required_ppe": required_items,
                    "detected_ppe_items": sorted(present_items),
                    "negative_ppe_items": sorted(negative_items),
                    "ppe_item": missing_items[0],
                    "ppe_items": missing_items,
                    "missing_ppe_items": missing_items,
                    "ppe_detections": detections,
                    "ppe_source_event_types": [item["event_type"] for item in detections],
                    "person_bbox": person.bbox,
                    "object_class": "person",
                    "stable_object_key": _stable_person_key(person),
                    "worker_track_id": raw_track_id,
                    "worker_track_id_valid": has_stable_track,
                    "worker_track_id_fallback": not has_stable_track,
                    "worker_track_id_source": "bytetrack" if has_stable_track else "fallback",
                    "composite_eligible": has_stable_track,
                },
            ))

        return events


def _combined_required_ppe(zones: list[SafetyZone]) -> list[str]:
    combined: list[str] = []
    seen: set[str] = set()
    for zone in zones:
        try:
            requirements = normalize_required_ppe(
                (zone.rules or {}).get("required_ppe") or (zone.rules or {}).get("requiredPpe") or []
            )
        except ValueError:
            requirements = []
        for item in requirements:
            if item in seen:
                continue
            seen.add(item)
            combined.append(item)
    return combined


def _alert_title(missing_items: list[str]) -> str:
    if len(missing_items) == 1:
        return f"Worker inside PPE Zone without {ppe_items_phrase(missing_items)}"
    return f"Worker inside PPE Zone missing {ppe_items_phrase(missing_items)}"


def _source_event_type(item: str) -> str:
    return {
        "vest": "ppe_missing_vest",
        "safety_shoes": "ppe_missing_shoes",
        "safety_glasses": "ppe_missing_safety_glasses",
        "face_mask": "ppe_missing_face_mask",
        "protective_suit": "ppe_missing_protective_suit",
        "ear_protection": "ppe_missing_ear_protection",
    }.get(item, f"ppe_missing_{item}")


def _stable_person_key(person: Detection) -> str:
    if person.track_id is not None:
        return f"person:{person.track_id}"
    x1, y1, x2, y2 = person.bbox
    return f"person:bbox:{round((x1 + x2) / 20)}:{round((y1 + y2) / 20)}"


def _zone_snapshot(zone: SafetyZone) -> dict:
    return {
        "id": zone.id,
        "name": zone.name,
        "zone_type": zone.zone_type,
        "polygon": [{"x": x, "y": y} for x, y in zone.polygon],
        "coordinate_space": "source_pixels",
        "source_width": zone.source_width,
        "source_height": zone.source_height,
        "color": zone.color,
        "enabled": True,
        "priority": zone.priority,
        "rules": dict(zone.rules or {}),
    }
