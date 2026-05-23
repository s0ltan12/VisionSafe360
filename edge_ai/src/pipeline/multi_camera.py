"""Multi-camera parallel pipeline with shared GPU models.

Reuses PipelineContext + FrameProcessor to eliminate duplicated
inference/analysis/rendering logic. Each camera gets its own
PipelineContext but all share ONE InferenceEngine (one GPU).
"""
from __future__ import annotations

import logging
import signal
import time
from typing import Optional

import cv2

from ..config.settings import (
    BACKEND_CAMERA_NAME,
    BACKEND_EVENTS_ENABLED,
    BACKEND_WORKER_GPU_ID,
    BACKEND_WORKER_ID,
    OFFLINE_FLUSH_INTERVAL_SEC,
    OFFLINE_FLUSH_MAX_PER_CYCLE,
    OFFLINE_SHUTDOWN_FLUSH_LIMIT,
    OUTPUT_DIR,
    PROXIMITY_HOLD_FRAMES,
    TARGET_INFER_FPS,
    TRACK_ID_GRACE_FRAMES,
)
from ..config.profile import ProfileConfig
from ..config.inference.inference_engine import InferenceEngine
from ..streaming.stream_handler import StreamHandler
from ..analysis.hazard_analyzer import HazardAnalyzer
from ..analysis.posture_analyzer import PostureAnalyzer
from ..analysis.proximity_analyzer import ProximityAnalyzer
from ..analysis.ppe_analyzer import PPEAnalyzer
from ..analysis.event_aggregator import EventAggregator
from ..analysis.calibration import CalibrationManager
from ..analysis.track_quality import TrackQualityMonitor
from ..alerts.alert_manager import AlertManager
from ..alerts.fcm_service import FCMService
from ..alerts.siren_controller import SirenController
from ..integration.backend_client import BackendClient
from ..utils.logger import MetricsLogger
from ..ui.renderer import SafetyOverlayRenderer
from ..config.ui_settings import load_ui_settings_from_profile
from ..smoothing.detection_smoother import DetectionSmoother, ForkliftHoldSmoother
from .context import PipelineContext
from .frame_processor import FrameProcessor

logger = logging.getLogger("PipelineOrchestrator")


def _build_multi_camera_context(
    source: str | int,
    cam_id: str,
    show: bool,
    profile: ProfileConfig,
    calibration_mgr: CalibrationManager,
    engine: InferenceEngine,
    backend_client: BackendClient,
    alert_manager: AlertManager,
    siren_controller: SirenController,
    ppe_enabled: bool,
    ppe_capable: bool,
    proximity_enabled: bool,
) -> PipelineContext:
    """Build a PipelineContext for one camera, sharing GPU and backend resources."""
    stream = StreamHandler(source=source, camera_id=cam_id)
    metrics = MetricsLogger()

    det_smoother = DetectionSmoother(grace_frames=TRACK_ID_GRACE_FRAMES)
    forklift_smoother = ForkliftHoldSmoother(hold_frames=PROXIMITY_HOLD_FRAMES)

    is_calibrated = calibration_mgr.is_calibrated(cam_id)
    ui_settings = load_ui_settings_from_profile(profile.ui_config)
    renderer = SafetyOverlayRenderer(cfg=ui_settings)

    hazard_analyzer = None
    if profile.is_enabled("hazard_analyzer"):
        hazard_analyzer = HazardAnalyzer(
            fall_enabled=profile.is_sub_enabled("hazard_analyzer", "fall")
        )

    posture_analyzer = PostureAnalyzer() if profile.is_enabled("posture_analyzer") else None
    proximity_analyzer = ProximityAnalyzer() if proximity_enabled else None
    ppe_analyzer = PPEAnalyzer() if ppe_enabled else None

    person_tracker_source = profile.person_tracker_source
    if person_tracker_source == "ppe" and not ppe_enabled:
        logger.warning(
            "person_tracker_source=ppe but ppe_analyzer is disabled; falling back to pose"
        )
        person_tracker_source = "pose"

    fall_every_n = profile.get_sub_schedule("hazard_analyzer", "fall")
    ergo_every_n = profile.get_schedule("posture_analyzer")
    proximity_every_n = profile.get_schedule("proximity_analyzer")
    ppe_every_n = profile.get_schedule("ppe_analyzer")

    win_name = f"VisionSafe360 - {cam_id}"
    out_path = OUTPUT_DIR / f"{cam_id}_output.mp4" if not show else None

    return PipelineContext(
        stream=stream,
        engine=engine,                   # shared
        metrics=metrics,
        event_aggregator=EventAggregator(),
        calibration_mgr=calibration_mgr, # shared
        track_monitor=TrackQualityMonitor(),
        det_smoother=det_smoother,
        forklift_smoother=forklift_smoother,
        hazard_analyzer=hazard_analyzer,
        posture_analyzer=posture_analyzer,
        proximity_analyzer=proximity_analyzer,
        ppe_analyzer=ppe_analyzer,
        ppe_enabled=ppe_enabled,
        person_tracker_source=person_tracker_source,
        backend_client=backend_client,   # shared
        camera_name=BACKEND_CAMERA_NAME or "",
        worker_id=BACKEND_WORKER_ID or None,
        worker_gpu_id=BACKEND_WORKER_GPU_ID or None,
        alert_manager=alert_manager,     # shared
        siren_controller=siren_controller,  # shared
        renderer=renderer,
        is_calibrated=is_calibrated,
        fall_every_n=fall_every_n,
        ergo_every_n=ergo_every_n,
        proximity_every_n=proximity_every_n,
        ppe_every_n=ppe_every_n,
        show=show,
        headless=False,                  # multi-camera doesn't use headless
        win_name=win_name,
        writer=None,
        out_path=out_path,
        frame_publisher=None,            # multi-camera doesn't use Redis pub
        frame_counter=0,
        frames_processed=0,
        fps_t0=time.monotonic(),
        inference_fps=0.0,
        last_offline_flush=time.monotonic(),
        offline_flush_in_progress=False,
        offline_flush_thread=None,
        cumulative_forklift_dets=0,
        sample_forklift_lines=[],
        sample_hazard_lines=[],
        ppe_capable=ppe_capable,
        last_ppe_detections=[],
    )


def run_multi_camera_pipeline(
    sources: list[str | int],
    show: bool,
    profile: ProfileConfig
) -> None:
    """
    Multi-camera parallel pipeline with SHARED models.

    All cameras share ONE InferenceEngine = ONE set of GPU models.
    This minimizes VRAM usage while processing multiple streams.
    Each camera gets a full PipelineContext and reuses FrameProcessor.
    """
    logger.info("═══ Starting Multi-Camera Pipeline ═══")
    logger.info("Cameras: %d", len(sources))

    # ── Shared resources (loaded once) ──────────────────────────────
    engine = InferenceEngine()
    engine.load_pose()

    proximity_enabled = profile.is_enabled("proximity_analyzer")
    if proximity_enabled:
        prox_weights = profile.get_weights("proximity_analyzer")
        if not engine.load_proximity(prox_weights):
            logger.warning("Proximity model not loaded")
            proximity_enabled = False

    ppe_enabled = profile.is_enabled("ppe_analyzer")
    ppe_capable = False
    if ppe_enabled:
        ppe_weights = profile.get_weights("ppe_analyzer")
        if engine.load_ppe(ppe_weights):
            ppe_capable = True
        else:
            logger.warning("PPE model not loaded")
            ppe_enabled = False

    calibration_mgr = CalibrationManager()
    backend_client = BackendClient()
    fcm_service = FCMService()
    siren_controller = SirenController()
    alert_manager = AlertManager(
        backend_client=backend_client,
        fcm_service=fcm_service,
        siren_controller=siren_controller,
    )

    # ── Per-camera contexts (reusing PipelineContext) ────────────────
    cam_contexts: list[PipelineContext] = []
    cam_processors: list[FrameProcessor] = []
    for idx, source in enumerate(sources):
        cam_id = f"cam_{idx + 1:02d}"
        ctx = _build_multi_camera_context(
            source=source,
            cam_id=cam_id,
            show=show,
            profile=profile,
            calibration_mgr=calibration_mgr,
            engine=engine,
            backend_client=backend_client,
            alert_manager=alert_manager,
            siren_controller=siren_controller,
            ppe_enabled=ppe_enabled,
            ppe_capable=ppe_capable,
            proximity_enabled=proximity_enabled,
        )
        cam_contexts.append(ctx)
        cam_processors.append(FrameProcessor(ctx))
        logger.info("  Camera %s: %s", cam_id, source)

    # ── Start all camera streams ────────────────────────────────────
    for ctx in cam_contexts:
        ctx.stream.start()
        if show:
            cv2.namedWindow(ctx.win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    infer_interval = 1.0 / TARGET_INFER_FPS
    global_shutdown = False

    def _handle_signal(signum, _frame):
        nonlocal global_shutdown
        logger.info("Signal %d received — shutting down all cameras", signum)
        global_shutdown = True
        for ctx in cam_contexts:
            ctx.shutdown = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Wait briefly for streams to start capturing
    time.sleep(0.5)

    logger.info("═══ Pipeline running (press 'q' to quit) ═══")

    try:
        while not global_shutdown:
            loop_start = time.monotonic()
            any_frame_processed = False

            # ── Process each camera using shared FrameProcessor ─────
            for ctx, processor in zip(cam_contexts, cam_processors):
                if ctx.shutdown:
                    continue

                bundle = ctx.stream.get_frame()
                if bundle is None:
                    continue

                any_frame_processed = True

                # Log progress every 30 frames
                if ctx.frame_counter > 0 and ctx.frame_counter % 30 == 0:
                    logger.info("  %s: %d frames processed", ctx.stream.camera_id, ctx.frame_counter)

                # Reuse FrameProcessor — handles inference, analysis,
                # rendering, alerting, metrics, and offline flush.
                result = processor.process(bundle)

                # ── Display / Write ─────────────────────────────────
                if show:
                    cv2.imshow(ctx.win_name, result.annotated)
                else:
                    if ctx.writer is None and ctx.out_path is not None:
                        h, w = result.annotated.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        ctx.writer = cv2.VideoWriter(str(ctx.out_path), fourcc, TARGET_INFER_FPS, (w, h))
                    if ctx.writer is not None:
                        ctx.writer.write(result.annotated)

            # ── Check if all streams finished ───────────────────────
            all_streams_done = all(not ctx.stream.is_running for ctx in cam_contexts)
            if all_streams_done and not any_frame_processed:
                # Give one more chance to read remaining buffered frames
                time.sleep(0.1)
                still_have_frames = any(ctx.stream.get_frame() is not None for ctx in cam_contexts)
                if not still_have_frames:
                    logger.info("All camera streams finished")
                    global_shutdown = True

            # ── Key handling ────────────────────────────────────────
            if show:
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    logger.info("User pressed quit key")
                    global_shutdown = True

            # ── Frame rate control ──────────────────────────────────
            if not any_frame_processed:
                time.sleep(0.001)
            else:
                elapsed = time.monotonic() - loop_start
                sleep_time = infer_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
    finally:
        # ── Cleanup ─────────────────────────────────────────────────
        try:
            alert_manager.shutdown(timeout_sec=2.0)
        except Exception:
            pass
        for ctx in cam_contexts:
            ctx.stream.stop()
            if ctx.writer is not None:
                ctx.writer.release()

        if show:
            cv2.destroyAllWindows()

        try:
            siren_controller.stop()
        except Exception:
            pass
        try:
            backend_client.flush_offline_queue(limit=OFFLINE_SHUTDOWN_FLUSH_LIMIT)
        except Exception:
            pass

        logger.info("═══ Multi-Camera Pipeline Finished ═══")
        for ctx in cam_contexts:
            drop_pct = (
                ctx.stream.dropped_count / ctx.stream.total_frames_read * 100
                if ctx.stream.total_frames_read > 0 else 0.0
            )
            logger.info(
                "  %s: processed=%d  read=%d  dropped=%d (%.1f%%)  reconnects=%d",
                ctx.stream.camera_id,
                ctx.frames_processed,
                ctx.stream.total_frames_read,
                ctx.stream.dropped_count,
                drop_pct,
                ctx.stream.reconnect_count,
            )
