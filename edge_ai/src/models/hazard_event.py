"""
HazardEvent — a detected safety hazard with metadata.
Stub: defined now for importability, fully used from Step 2 onward.
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple
from .severity import Severity


@dataclass(slots=True)
class HazardEvent:
    """A safety hazard detected in a frame."""
    event_type: str                                 # e.g. "fall", "no_helmet", "proximity"
    severity: Severity
    camera_id: str
    timestamp: float
    frame_number: int
    track_id: Optional[int] = field(default=None)
    bbox: Optional[Tuple[int, int, int, int]] = field(default=None)
    description: str = ""
    metadata: dict = field(default_factory=dict)
