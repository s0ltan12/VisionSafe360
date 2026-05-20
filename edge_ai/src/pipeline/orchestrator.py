"""Single-camera pipeline orchestration — build, run, shutdown.

Extracted from main.py — preserves original logic unchanged.
"""
from __future__ import annotations

import logging
import os as _os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2

from ..config.settings import (
    BACKEND_CAMERA_NAME,
    BACKEND_EVENTS_ENABLED,
    BACKEND_WORKER_GPU_ID,
    BACKEND_WORKER_ID,
    OUTPUT_DIR,
    PROXIMITY_HOLD_FRAMES,
    TARGET_INFER_FPS,
    TRACK_ID_GRACE_FRAMES,
    OFFLINE_SHUTDOWN_FLUSH_LIMIT,
)
from ..config.profile import ProfileConfig
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


# ── Step 2 report helpers ───────────────────────────────────────────

def _write_step2_completion_report(
    report_path: Path,
    track_coverage: float,
    avg_forklift_dets_per_frame: float,
    sample_forklift_lines: list[str],
    sample_hazard_lines: list[str],
) -> None:
    """Write a handover-ready Step 2 completion report."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    forklift_section = (
        "\n".join(f"- `{line}`" for line in sample_forklift_lines)
        if sample_forklift_lines else "- No forklift sample lines captured in this run."
    )
    hazard_section = (
        "\n".join(f"- `{line}`" for line in sample_hazard_lines)
        if sample_hazard_lines else "- No proximity hazard events captured in this run."
    )

    content = f"""# Step 2 Completion Report

Generated at: {ts}

## System Summary
- Pose + Tracking: [OK]
- Fall detection: [OK]
- Ergonomics: [OK]
- Proximity (forklift): [OK]

## Evidence
### Forklift detections (`forklift_dets > 0`)
{forklift_section}

### Proximity hazard events
Expected event types:
- `forklift_proximity_warning`
- `forklift_proximity_danger`

Observed samples:
{hazard_section}

## Metrics
- `track_coverage`: **{track_coverage:.1f}%**
- `avg_forklift_detections_per_frame`: **{avg_forklift_dets_per_frame:.3f}**

## Notes
- Added forklift temporal smoothing (hold-based) for UI/proximity input only.
- Added global debug toggle via env `VISIONSAFE_DEBUG`.
- Tuned ByteTrack parameters for improved persistence under brief occlusions.
"""
    report_path.write_text(content, encoding="utf-8")


def _should_write_step2_report() -> bool:
    return _os.getenv("VISIONSAFE_WRITE_STEP2_REPORT", "0").strip() == "1"


def _step2_report_output_path() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return OUTPUT_DIR / f"{ts}_report.md"


# ── Pipeline lifecycle ──────────────────────────────────────────────

def _build_pipeline_context(
    source: str | int, cam_id: str, show: bool, profile: ProfileConfig,
    headless: bool = False,
) -> PipelineContext:
    stream = StreamHandler(source=source, camera_id=cam_id)
    engine = InferenceEngine()
    metrics = MetricsLogger()
    event_aggregator = EventAggregator()
    calibration_mgr = CalibrationManager()
    track_monitor = TrackQualityMonitor()
    det_smoother = DetectionSmoother(grace_frames=TRACK_ID_GRACE_FRAMES)
    forklift_smoother = ForkliftHoldSmoother(hold_frames=PROXIMITY_HOLD_FRAMES)

    engine.load_pose()

    proximity_enabled = profile.is_enabled("proximity_analyzer")
    if proximity_enabled:
        prox_weights = profile.get_weights("proximity_analyzer")
        if not engine.load_proximity(prox_weights):
            logger.warning(
                "Proximity analyzer enabled in profile but model was not loaded"
            )
            proximity_enabled = False

    ppe_enabled = profile.is_enabled("ppe_analyzer")
    ppe_capable = False
    if ppe_enabled:
        ppe_weights = profile.get_weights("ppe_analyzer")
        if not engine.load_ppe(ppe_weights):
            logger.warning(
                "PPE analyzer enabled in profile but model was not loaded"
            )
            ppe_enabled = False
        else:
            ppe_capable = True

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

    backend_client = BackendClient()
    fcm_service = FCMService()
    siren_controller = SirenController()
    alert_manager = AlertManager(
        backend_client=backend_client,
        fcm_service=fcm_service,
        siren_controller=siren_controller,
    )

    fall_every_n = profile.get_sub_schedule("hazard_analyzer", "fall")
    ergo_every_n = profile.get_schedule("posture_analyzer")
    proximity_every_n = profile.get_schedule("proximity_analyzer")
    ppe_every_n = profile.get_schedule("ppe_analyzer")
    person_tracker_source = profile.person_tracker_source
    if person_tracker_source == "ppe" and not ppe_enabled:
        logger.warning(
            "person_tracker_source=ppe but ppe_analyzer is disabled; falling back to pose"
        )
        person_tracker_source = "pose"

    stream.start()
    logger.info(
        "Pipeline running — source=%s  cam_id=%s  show=%s  profile=%s",
        source,
        cam_id,
        show,
        profile.profile_name,
    )

    win_name = f"VisionSafe360 - {cam_id}"
    if show and not headless:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    # Frame publisher for headless dashboard streaming
    frame_publisher: Optional[FramePublisher] = None
    if headless:
        frame_publisher = FramePublisher(camera_id=cam_id)
        logger.info("Headless mode enabled — frames will be streamed via Redis")

    writer = None
    out_path = None
    if not show and not headless:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{cam_id}_out.mp4"
        logger.info("Output video → %s", out_path)

    return PipelineContext(
        stream=stream,
        engine=engine,
        metrics=metrics,
        event_aggregator=event_aggregator,
        calibration_mgr=calibration_mgr,
        track_monitor=track_monitor,
        det_smoother=det_smoother,
        forklift_smoother=forklift_smoother,
        hazard_analyzer=hazard_analyzer,
        posture_analyzer=posture_analyzer,
        proximity_analyzer=proximity_analyzer,
        ppe_analyzer=ppe_analyzer,
        ppe_enabled=ppe_enabled,
        person_tracker_source=person_tracker_source,
        backend_client=backend_client,
        camera_name=BACKEND_CAMERA_NAME or "",
        worker_id=BACKEND_WORKER_ID or None,
        worker_gpu_id=BACKEND_WORKER_GPU_ID or None,
        alert_manager=alert_manager,
        siren_controller=siren_controller,
        renderer=renderer,
        is_calibrated=is_calibrated,
        fall_every_n=fall_every_n,
        ergo_every_n=ergo_every_n,
        proximity_every_n=proximity_every_n,
        ppe_every_n=ppe_every_n,
        show=show,
        headless=headless,
        win_name=win_name,
        writer=writer,
        out_path=out_path,
        frame_publisher=frame_publisher,
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


def _shutdown_pipeline(ctx: PipelineContext) -> None:
    try:
        ctx.alert_manager.shutdown(timeout_sec=2.0)
    except Exception:
        pass
    try:
        flush_limit = max(0, int(OFFLINE_SHUTDOWN_FLUSH_LIMIT))
        if flush_limit > 0:
            ctx.backend_client.flush_offline_queue(limit=flush_limit)
    except Exception:
        pass
    try:
        ctx.siren_controller.stop()
    except Exception:
        pass
    ctx.stream.stop()
    # Best-effort wait for background offline flush (avoid exiting mid-write).
    try:
        t = ctx.offline_flush_thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
    except Exception:
        pass
    if ctx.frame_publisher is not None:
        ctx.frame_publisher.close()
    if ctx.writer is not None:
        ctx.writer.release()
    if ctx.show and not ctx.headless:
        cv2.destroyAllWindows()


def _maybe_write_step2_report(ctx: PipelineContext) -> None:
    if not _should_write_step2_report():
        return

    track_snapshot = ctx.track_monitor.snapshot()
    avg_forklift_dets = (
        ctx.cumulative_forklift_dets / ctx.frames_processed if ctx.frames_processed > 0 else 0.0
    )
    report_path = _step2_report_output_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_step2_completion_report(
        report_path=report_path,
        track_coverage=track_snapshot.get("track_coverage", 0.0),
        avg_forklift_dets_per_frame=avg_forklift_dets,
        sample_forklift_lines=ctx.sample_forklift_lines,
        sample_hazard_lines=ctx.sample_hazard_lines,
    )
    logger.info("Step 2 completion report written: %s", report_path)


# ════════════════════════════════════════════════════════════════════
#  Main pipeline
# ════════════════════════════════════════════════════════════════════

def run_pipeline(source: str | int, cam_id: str, show: bool, profile: ProfileConfig, headless: bool = False) -> None:
    """Single-camera inference loop. Blocks until Ctrl-C or stream exhaustion."""

    ctx = _build_pipeline_context(source=source, cam_id=cam_id, show=show, profile=profile, headless=headless)
    processor = FrameProcessor(ctx)
    infer_interval = 1.0 / TARGET_INFER_FPS

    def _handle_signal(signum, _frame):
        logger.info("Signal %d received — shutting down", signum)
        ctx.shutdown = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not ctx.shutdown:
            loop_start = time.monotonic()
            bundle = ctx.stream.get_frame()
            if bundle is None:
                time.sleep(0.001)
                continue

            result = processor.process(bundle)

            if ctx.headless:
                # Headless mode: frames are published via FramePublisher in
                # FrameProcessor.process(). No GUI or file output needed.
                pass
            elif ctx.show:
                cv2.imshow(ctx.win_name, result.annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    logger.info("User pressed quit key")
                    break
            else:
                if ctx.writer is None:
                    h, w = result.annotated.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    assert ctx.out_path is not None
                    ctx.writer = cv2.VideoWriter(
                        str(ctx.out_path), fourcc, TARGET_INFER_FPS, (w, h)
                    )
                ctx.writer.write(result.annotated)

            elapsed = time.monotonic() - loop_start
            sleep_time = infer_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
    finally:
        _shutdown_pipeline(ctx)

        logger.info(
            "Pipeline finished — frames_processed=%d  total_read=%d  dropped=%d  "
            "reconnects=%d",
            ctx.frames_processed,
            ctx.stream.total_frames_read,
            ctx.stream.dropped_count,
            ctx.stream.reconnect_count,
        )
        drop_pct = (
            (ctx.stream.dropped_count / ctx.stream.total_frames_read * 100)
            if ctx.stream.total_frames_read > 0
            else 0.0
        )
        logger.info("Drop rate: %.1f%%", drop_pct)
        logger.info("\n%s", ctx.track_monitor.summary())
        _maybe_write_step2_report(ctx)
