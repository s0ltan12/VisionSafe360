"""Shared PPE item normalization, labeling, and person association helpers."""
from __future__ import annotations

import math
from typing import Optional, Tuple

from ..models.detection import Detection
from ..models.severity import Severity

PPE_ZONE_TYPES = {"ppe", "ppe_required"}

SUPPORTED_PPE_ITEMS = (
    "helmet",
    "vest",
    "gloves",
    "safety_glasses",
    "face_mask",
    "safety_shoes",
    "protective_suit",
    "ear_protection",
)

PPE_ITEM_LABELS: dict[str, str] = {
    "helmet": "Helmet",
    "vest": "Safety Vest",
    "gloves": "Gloves",
    "safety_glasses": "Safety Glasses",
    "face_mask": "Face Mask",
    "safety_shoes": "Safety Shoes",
    "protective_suit": "Protective Suit",
    "ear_protection": "Ear Protection",
}

PPE_ITEM_SEVERITY: dict[str, Severity] = {
    "helmet": Severity.HIGH,
    "vest": Severity.HIGH,
    "gloves": Severity.MEDIUM,
    "safety_glasses": Severity.MEDIUM,
    "face_mask": Severity.MEDIUM,
    "safety_shoes": Severity.HIGH,
    "protective_suit": Severity.HIGH,
    "ear_protection": Severity.MEDIUM,
}

PPE_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

PPE_POSITIVE_DETECTIONS: dict[str, str] = {
    "helmet_on": "helmet",
    "helmet": "helmet",
    "hard_hat": "helmet",
    "hardhat": "helmet",
    "safety_vest": "vest",
    "vest_on": "vest",
    "vest": "vest",
    "gloves_on": "gloves",
    "gloves": "gloves",
    "glove": "gloves",
    "glasses": "safety_glasses",
    "goggles": "safety_glasses",
    "eye_protection": "safety_glasses",
    "face_mask": "face_mask",
    "mask": "face_mask",
    "shoes": "safety_shoes",
    "boots": "safety_shoes",
    "safety_shoes": "safety_shoes",
    "safety_suit": "protective_suit",
    "medical_suit": "protective_suit",
    "coverall": "protective_suit",
    "coveralls": "protective_suit",
    "ear_muffs": "ear_protection",
    "earmuffs": "ear_protection",
    "hearing_protection": "ear_protection",
}

PPE_NEGATIVE_DETECTIONS: dict[str, tuple[str, str, Severity]] = {
    "helmet_off": ("helmet", "ppe_missing_helmet", Severity.HIGH),
    "vest_off": ("vest", "ppe_missing_vest", Severity.HIGH),
    "gloves_off": ("gloves", "ppe_missing_gloves", Severity.MEDIUM),
    "bare_foot": ("safety_shoes", "ppe_missing_shoes", Severity.HIGH),
}

_ALIASES: dict[str, str] = {
    **{item: item for item in SUPPORTED_PPE_ITEMS},
    "hard_hat": "helmet",
    "hardhat": "helmet",
    "safety_vest": "vest",
    "reflective_vest": "vest",
    "glove": "gloves",
    "glasses": "safety_glasses",
    "goggles": "safety_glasses",
    "eye_protection": "safety_glasses",
    "mask": "face_mask",
    "shoes": "safety_shoes",
    "boots": "safety_shoes",
    "suit": "protective_suit",
    "safety_suit": "protective_suit",
    "coverall": "protective_suit",
    "coveralls": "protective_suit",
    "ear_muffs": "ear_protection",
    "earmuffs": "ear_protection",
    "hearing_protection": "ear_protection",
}


def normalize_ppe_item(value: object) -> str | None:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    return _ALIASES.get(key)


def normalize_required_ppe(values: object) -> list[str]:
    if values in (None, ""):
        return []
    raw_values = [values] if isinstance(values, str) else list(values)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        item = normalize_ppe_item(raw)
        if item is None:
            raise ValueError(f"unsupported PPE type: {raw}")
        if item in seen:
            raise ValueError(f"duplicate PPE requirement: {item}")
        seen.add(item)
        normalized.append(item)
    return normalized


def detection_present_item(class_name: str) -> str | None:
    return PPE_POSITIVE_DETECTIONS.get(_normalize_detection_class(class_name))


def detection_negative_spec(class_name: str) -> tuple[str, str, Severity] | None:
    return PPE_NEGATIVE_DETECTIONS.get(_normalize_detection_class(class_name))


def ppe_item_label(item: str) -> str:
    return PPE_ITEM_LABELS.get(item, item.replace("_", " ").strip().title())


def ppe_items_phrase(items: list[str] | tuple[str, ...]) -> str:
    labels = [ppe_item_label(item) for item in items]
    if not labels:
        return "PPE"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def ppe_missing_title(items: list[str]) -> str:
    if not items:
        return "PPE missing"
    return "PPE missing " + ", ".join(ppe_item_label(item).lower() for item in items)


def highest_ppe_severity(items: list[str]) -> Severity:
    severities = [PPE_ITEM_SEVERITY.get(item, Severity.MEDIUM) for item in items]
    if not severities:
        return Severity.MEDIUM
    return max(severities, key=lambda severity: PPE_SEVERITY_RANK.get(severity, 0))


def match_person_for_ppe(ppe: Detection, people: list[Detection]) -> Optional[Detection]:
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

    if best_person is None or best_score < 0.02:
        return None
    return best_person


def person_detection_key(person: Detection) -> tuple[int | None, Tuple[int, int, int, int]]:
    return person.track_id, person.bbox


def _normalize_detection_class(class_name: str) -> str:
    return str(class_name or "").strip().lower().replace("-", "_").replace(" ", "_")


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
