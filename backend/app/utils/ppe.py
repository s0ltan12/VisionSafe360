"""PPE requirement vocabulary shared by backend validation and serializers."""
from __future__ import annotations

from collections.abc import Iterable

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

_ALIASES: dict[str, str] = {
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
_ALIASES.update({item: item for item in SUPPORTED_PPE_ITEMS})


def normalize_ppe_item(value: object) -> str | None:
    """Normalize one PPE item name to the API canonical value."""
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    return _ALIASES.get(key)


def normalize_required_ppe(values: object) -> list[str]:
    """Validate, normalize, and preserve PPE requirement order."""
    if values in (None, ""):
        return []
    if isinstance(values, str):
        raw_values: Iterable[object] = [values]
    elif isinstance(values, Iterable):
        raw_values = values
    else:
        raise ValueError("required_ppe must be a list of PPE item names")

    normalized: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for raw in raw_values:
        item = normalize_ppe_item(raw)
        if item is None:
            invalid.append(str(raw))
            continue
        if item in seen:
            duplicates.append(PPE_ITEM_LABELS[item])
            continue
        seen.add(item)
        normalized.append(item)

    if invalid:
        raise ValueError(
            "unsupported PPE types: "
            + ", ".join(invalid)
            + f". Supported PPE types: {', '.join(SUPPORTED_PPE_ITEMS)}"
        )
    if duplicates:
        raise ValueError("duplicate PPE requirements: " + ", ".join(duplicates))
    return normalized
