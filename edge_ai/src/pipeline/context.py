"""Pipeline context dataclasses — hold run-time services and mutable state.

Extracted from main.py — no logic changes.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2

from ..config.inference.inference_engine import InferenceEngine
from ..streaming.stream_handler import StreamHandler
from ..streaming.frame_publisher import FramePublisher
from ..analysis.hazard_analyzer import HazardAnalyzer
from ..analysis.posture_analyzer import PostureAnalyzer
from ..analysis.proximity_analyzer import ProximityAnalyzer
from ..analysis.ppe_analyzer import PPEAnalyzer
from ..analysis.event_aggregator import EventAggregator
from ..analysis.calibration import CalibrationManager
from ..analysis.track_quality import TrackQualityMonitor
from ..alerts.alert_manager import AlertManager
from ..alerts.siren_controller import SirenController
from ..integration.backend_client import BackendClient
from ..utils.logger import MetricsLogger
from ..ui.renderer import SafetyOverlayRenderer
from ..smoothing.detection_smoother import DetectionSmoother, ForkliftHoldSmoother


@dataclass
class PipelineContext:
    """Holds run-time services and mutable pipeline state."""

    stream: StreamHandler
    engine: InferenceEngine
    metrics: MetricsLogger
    event_aggregator: EventAggregator
    calibration_mgr: CalibrationManager
    track_monitor: TrackQualityMonitor
    det_smoother: DetectionSmoother
    forklift_smoother: ForkliftHoldSmoother

    hazard_analyzer: Optional[HazardAnalyzer]
    posture_analyzer: Optional[PostureAnalyzer]
    proximity_analyzer: Optional[ProximityAnalyzer]
    ppe_analyzer: Optional[PPEAnalyzer]
    ppe_enabled: bool
    person_tracker_source: str

    backend_client: BackendClient
    camera_name: str
    worker_id: Optional[str]
    worker_gpu_id: Optional[str]
    alert_manager: AlertManager
    siren_controller: SirenController

    renderer: SafetyOverlayRenderer
    is_calibrated: bool

    fall_every_n: int
    ergo_every_n: int
    proximity_every_n: int
    ppe_every_n: int

    show: bool
    headless: bool
    win_name: str
    writer: Optional[cv2.VideoWriter]
    out_path: Optional[Path]
    frame_publisher: Optional[FramePublisher]

    frame_counter: int
    frames_processed: int
    fps_t0: float
    inference_fps: float
    last_offline_flush: float
    offline_flush_in_progress: bool
    offline_flush_thread: Optional[threading.Thread]

    cumulative_forklift_dets: int
    sample_forklift_lines: list[str]
    sample_hazard_lines: list[str]
    ppe_capable: bool
    last_ppe_detections: list[Any]

    shutdown: bool = False


@dataclass
class FrameResult:
    """Frame processor result."""

    annotated: Any
