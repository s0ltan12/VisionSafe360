"""
FrameBundle — immutable snapshot of a decoded video frame.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(slots=True)
class FrameBundle:
    """A single decoded frame with provenance metadata."""
    frame: np.ndarray       # BGR HWC uint8 image
    camera_id: str          # logical camera identifier
    timestamp: float        # time.time() when captured
    frame_number: int       # monotonic counter from StreamHandler
