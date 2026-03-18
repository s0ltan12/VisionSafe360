"""
InferenceResult — output of the inference loop for one frame.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any

from .frame_bundle import FrameBundle
from .detection import Detection


@dataclass(slots=True)
class InferenceResult:
    """Complete inference output for a single frame."""
    bundle: FrameBundle
    detections: List[Detection]               # after ByteTrack (track_id populated)
    detection_latency_ms: float               # Model A wall-clock ms
    pose_results: Optional[Any] = field(default=None)  # raw Ultralytics Results or None
    pose_latency_ms: float = 0.0
