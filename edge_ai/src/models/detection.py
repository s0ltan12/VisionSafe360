"""
Detection — a single bounding box detection with optional track ID.
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple

# ─── Unified Class Map (matches Model A training schema) ────────────
UNIFIED_CLASS_MAP = {
    0: "person",
    1: "helmet_on",
    2: "helmet_off",
    3: "vest_on",
    4: "vest_off",
    5: "forklift",
    6: "loader",
    7: "truck",
    8: "vehicle_other",
}

# COCO person class id (used when running pretrained COCO weights)
COCO_CLASS_MAP = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus",
    7: "truck", 14: "bird", 15: "cat", 16: "dog",
    # …full COCO map not needed; we resolve at runtime from model.names
}


@dataclass(slots=True)
class Detection:
    """Single detection from Model A."""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]           # (x1, y1, x2, y2) absolute pixels
    track_id: Optional[int] = field(default=None)
