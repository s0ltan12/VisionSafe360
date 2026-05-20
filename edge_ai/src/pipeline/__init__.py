"""Pipeline sub-package for orchestration, context, and frame processing."""

from .context import PipelineContext, FrameResult
from .frame_processor import FrameProcessor
from .orchestrator import run_pipeline
from .multi_camera import run_multi_camera_pipeline

__all__ = [
    "PipelineContext",
    "FrameResult",
    "FrameProcessor",
    "run_pipeline",
    "run_multi_camera_pipeline",
]

