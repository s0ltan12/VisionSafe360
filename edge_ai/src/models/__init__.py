"""
Edge AI models — public exports.
"""
from .frame_bundle import FrameBundle
from .detection import Detection, UNIFIED_CLASS_MAP
from .inference_result import InferenceResult
from .severity import Severity
from .hazard_event import HazardEvent

__all__ = [
    "FrameBundle",
    "Detection",
    "UNIFIED_CLASS_MAP",
    "InferenceResult",
    "Severity",
    "HazardEvent",
]
