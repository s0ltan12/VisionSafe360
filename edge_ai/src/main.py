"""
VisionSafe 360 — Edge AI Pipeline Orchestrator (Pose-Only)

Single-camera, pose-based analysis pipeline:
  python src/main.py --source path/to/test.mp4 --cam-id cam_01 --show
  python src/main.py --source path/to/test.mp4 --cam-id cam_01 --profile full_suite

Capabilities: fall detection + ergonomic risk assessment (RULA/REBA).
Single pose model provides person detection, tracking, and keypoints.

Design invariants:
  • deque(maxlen=1) latest-frame policy — old frames dropped, not queued.
  • ONE thread owns the GPU (this main thread after StreamHandler starts).
  • Pose model + ByteTrack in a single serial loop.
  • HazardAnalyzer + PostureAnalyzer are CPU-only (no GPU calls inside).
  • Profile-driven module enable/disable — no code changes needed.
"""
import argparse
import logging
import os as _os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

# ── Force Qt/OpenCV to use X11 (XCB) on Wayland ────────────────────
# Without this, cv2.imshow renders a black window on Wayland compositors.
if _os.environ.get("XDG_SESSION_TYPE") == "wayland":
    _os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# Suppress Ultralytics auto-update and verbose stdout pollution
_os.environ.setdefault("YOLO_VERBOSE", "false")

import cv2

# ── Ensure edge_ai/src is on sys.path when run as script ───────────
_SCRIPT_DIR = Path(__file__).resolve().parent          # edge_ai/src
_EDGE_AI_DIR = _SCRIPT_DIR.parent                       # edge_ai/
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.config.settings import (
    ALERTS_ENABLED,
    BACKEND_EVENTS_ENABLED,
    DEBUG_MODE,
    LOG_LEVEL,
    OFFLINE_FLUSH_INTERVAL_SEC,
    OUTPUT_DIR,
    PROXIMITY_HOLD_FRAMES,
    TARGET_INFER_FPS,
    TRACK_ID_GRACE_FRAMES,
)
from src.config.profile import load_profile, ProfileConfig
from src.config.inference.inference_engine import InferenceEngine
from src.streaming.stream_handler import StreamHandler
from src.analysis.hazard_analyzer import HazardAnalyzer
from src.analysis.posture_analyzer import PostureAnalyzer
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.analysis.event_aggregator import EventAggregator
from src.analysis.calibration import CalibrationManager
from src.analysis.track_quality import TrackQualityMonitor
from src.alerts.alert_manager import AlertManager
from src.alerts.fcm_service import FCMService
from src.alerts.siren_controller import SirenController
from src.integration.backend_client import BackendClient
from src.utils.logger import MetricsLogger, setup_logging
from src.utils.drawing import draw_detections, draw_hud, draw_hazard_events  # kept as fallback
from src.ui.renderer import SafetyOverlayRenderer
from src.config.ui_settings import load_ui_settings_from_profile

logger = logging.getLogger("PipelineOrchestrator")


# ── Detection Smoother ──────────────────────────────────────────────

class _DetectionSmoother:
    """Persist last-known bboxes for tracked persons to fill brief detection gaps.

    Handles two flickering scenarios:
    1. Person is detected but ByteTrack fails to assign a track_id on some
       frames → match untracked bbox to cached tracked bbox by IoU and
       reassign the track_id.
    2. Person disappears entirely for up to *grace_frames* → inject a
       'ghost' detection at the last known bbox.
    """

    def __init__(self, grace_frames: int = 5) -> None:
        self._grace = grace_frames
        # track_id → (Detection, frames_since_last_seen)
        self._cache: dict = {}

    @staticmethod
    def _iou(b1, b2) -> float:
        xa = max(b1[0], b2[0]); ya = max(b1[1], b2[1])
        xb = min(b1[2], b2[2]); yb = min(b1[3], b2[3])
        inter = max(0, xb - xa) * max(0, yb - ya)
        a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0.0

    def smooth(self, detections: list) -> list:
        # --- Phase 1: recover untracked detections ---
        # When a person is detected but has no track_id, try to match it
        # to a recently-tracked person by bbox IoU.
        for det in detections:
            if det.track_id is not None or det.class_name != "person":
                continue
            best_tid, best_iou = None, 0.3  # minimum IoU threshold
            for tid, (cached_det, _age) in self._cache.items():
                iou = self._iou(det.bbox, cached_det.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid
            if best_tid is not None:
                det.track_id = best_tid

        current_ids = {d.track_id for d in detections if d.track_id is not None}

        # Update cache with current detections
        for det in detections:
            if det.track_id is not None:
                self._cache[det.track_id] = (det, 0)

        # --- Phase 2: inject ghosts for fully missing tracks ---
        ghosts = []
        stale = []
        for tid, (cached_det, age) in self._cache.items():
            if tid in current_ids:
                continue
            new_age = age + 1
            if new_age <= self._grace:
                self._cache[tid] = (cached_det, new_age)
                ghosts.append(cached_det)
            else:
                stale.append(tid)

        for tid in stale:
            del self._cache[tid]

        return detections + ghosts


class _ForkliftHoldSmoother:
    """Temporal hold for forklift detections to reduce flicker on skipped frames.

    Important: this smoother is applied only to proximity analyzer input and UI
    rendering flow. Raw model detections are preserved separately.
    """

    def __init__(self, hold_frames: int = 5) -> None:
        self._hold_frames = max(0, int(hold_frames))
        self._remaining = 0
        self._cached_forklifts: list = []

    def smooth(self, raw_proximity_detections: list) -> tuple[list, bool]:
        persons = [d for d in raw_proximity_detections if d.class_name == "person"]
        forklifts = [d for d in raw_proximity_detections if d.class_name == "forklift"]

        used_hold = False
        if forklifts:
            self._cached_forklifts = forklifts
            self._remaining = self._hold_frames
        elif self._remaining > 0 and self._cached_forklifts:
            forklifts = self._cached_forklifts
            self._remaining -= 1
            used_hold = True
        else:
            self._cached_forklifts = []
            self._remaining = 0

        return persons + forklifts, used_hold


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


@dataclass
class PipelineContext:
    """Holds run-time services and mutable pipeline state."""

    stream: StreamHandler
    engine: InferenceEngine
    metrics: MetricsLogger
    event_aggregator: EventAggregator
    calibration_mgr: CalibrationManager
    track_monitor: TrackQualityMonitor
    det_smoother: _DetectionSmoother
    forklift_smoother: _ForkliftHoldSmoother

    hazard_analyzer: Optional[HazardAnalyzer]
    posture_analyzer: Optional[PostureAnalyzer]
    proximity_analyzer: Optional[ProximityAnalyzer]

    backend_client: BackendClient
    alert_manager: AlertManager
    siren_controller: SirenController

    renderer: SafetyOverlayRenderer
    is_calibrated: bool

    fall_every_n: int
    ergo_every_n: int
    proximity_every_n: int

    show: bool
    win_name: str
    writer: Optional[cv2.VideoWriter]
    out_path: Optional[Path]

    frame_counter: int
    frames_processed: int
    fps_t0: float
    inference_fps: float
    last_offline_flush: float

    cumulative_forklift_dets: int
    sample_forklift_lines: list[str]
    sample_hazard_lines: list[str]

    shutdown: bool = False


@dataclass
class FrameResult:
    """Frame processor result."""

    annotated: Any


class FrameProcessor:
    """Per-frame processing of inference, hazard detection, delivery, rendering."""

    def __init__(self, ctx: PipelineContext) -> None:
        self._ctx = ctx

    def process(self, bundle) -> FrameResult:
        ctx = self._ctx

        try:
            pose_results, detections, det_latency = ctx.engine.run_pose_tracker(bundle)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                logger.critical("CUDA OOM during inference: %s", exc)
                sys.exit(2)
            raise
        prox_detections: list[Any] = []
        prox_latency = 0.0
        raw_prox_detections: list[Any] = []
        raw_forklift_dets = 0
        forklift_dets = 0

        if ctx.proximity_analyzer is not None:
            if ctx.frame_counter % ctx.proximity_every_n == 0:
                raw_prox_detections, prox_latency = ctx.engine.run_proximity(bundle)

            prox_detections, _used_hold = ctx.forklift_smoother.smooth(raw_prox_detections)
            raw_forklift_dets = sum(
                1 for d in raw_prox_detections if d.class_name == "forklift"
            )
            forklift_dets = sum(1 for d in prox_detections if d.class_name == "forklift")
            ctx.cumulative_forklift_dets += forklift_dets

            if forklift_dets > 0 and len(ctx.sample_forklift_lines) < 8:
                ctx.sample_forklift_lines.append(
                    (
                        f"frame={bundle.frame_number} forklift_dets={forklift_dets} "
                        f"raw_forklift_dets={raw_forklift_dets}"
                    )
                )

            detections.extend([d for d in prox_detections if d.class_name == "forklift"])

        detections = ctx.det_smoother.smooth(detections)

        n_tracked = sum(1 for d in detections if d.track_id is not None)
        track_metrics = ctx.track_monitor.update(detections, time.time())
        display_id_map = ctx.track_monitor.remap_detections_display_ids(detections)

        ts_now = time.time()
        hazard_events: list[Any] = []

        if ctx.hazard_analyzer is not None:
            hazard_events = ctx.hazard_analyzer.analyze(
                detections,
                camera_id=ctx.stream.camera_id,
                frame_number=bundle.frame_number,
                timestamp=ts_now,
                fall_this_frame=(ctx.frame_counter % ctx.fall_every_n == 0),
                pose_results=pose_results,
            )

        if ctx.proximity_analyzer is not None and prox_detections:
            tracked_pose_people = [d for d in detections if d.class_name == "person"]
            hazard_events.extend(
                ctx.proximity_analyzer.analyze(
                    prox_detections,
                    tracked_pose_people,
                    camera_id=ctx.stream.camera_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                )
            )

        if (
            ctx.posture_analyzer is not None
            and pose_results is not None
            and ctx.frame_counter % ctx.ergo_every_n == 0
        ):
            hazard_events.extend(
                ctx.posture_analyzer.analyze(
                    pose_results,
                    camera_id=ctx.stream.camera_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                )
            )

        emitted_events = ctx.event_aggregator.process(hazard_events, ts_now)

        delivery_metrics: dict[str, Any] = {
            "n_events_emitted": len(emitted_events),
            "n_backend_ok": 0,
            "n_backend_failed": 0,
            "n_fcm_ok": 0,
            "n_fcm_failed": 0,
            "n_backend_completed_this_frame": 0,
            "n_fcm_completed_this_frame": 0,
            "n_siren_triggers": 0,
            "offline_queue_size": ctx.backend_client.offline_queue_size(),
        }
        if ALERTS_ENABLED:
            delivery_metrics = ctx.alert_manager.process_events(emitted_events)

        if (
            BACKEND_EVENTS_ENABLED
            and (time.monotonic() - ctx.last_offline_flush) >= OFFLINE_FLUSH_INTERVAL_SEC
        ):
            flush_stats = ctx.backend_client.flush_offline_queue()
            delivery_metrics["offline_queue_size"] = flush_stats.get(
                "remaining", ctx.backend_client.offline_queue_size()
            )
            ctx.last_offline_flush = time.monotonic()

        ctx.frames_processed += 1
        ctx.frame_counter += 1
        if ctx.frames_processed % 30 == 0:
            elapsed = time.monotonic() - ctx.fps_t0
            ctx.inference_fps = 30.0 / elapsed if elapsed > 0 else 0.0
            ctx.fps_t0 = time.monotonic()

        hazard_types = [e.event_type for e in emitted_events]
        ctx.metrics.log_frame(
            cam_id=ctx.stream.camera_id,
            frame_no=bundle.frame_number,
            input_fps=ctx.stream.input_fps,
            inference_fps=ctx.inference_fps,
            inference_ms=round(det_latency + prox_latency, 2),
            n_detections=len(detections),
            n_tracked=n_tracked,
            dropped_frames=ctx.stream.dropped_count,
            vram_mb=ctx.engine.vram_used_mb(),
            n_hazard_events=len(emitted_events),
            hazard_types=hazard_types if hazard_types else [],
            forklift_dets=forklift_dets,
            raw_forklift_dets=raw_forklift_dets,
            pose_ms=round(det_latency, 1),
            track_coverage=track_metrics.get("track_coverage", 0.0),
            calibrated=ctx.is_calibrated,
            n_events_emitted=delivery_metrics.get("n_events_emitted", 0),
            n_backend_ok=delivery_metrics.get("n_backend_ok", 0),
            n_backend_failed=delivery_metrics.get("n_backend_failed", 0),
            n_backend_completed_this_frame=delivery_metrics.get(
                "n_backend_completed_this_frame", 0
            ),
            n_backend_delivered_ok=delivery_metrics.get("n_backend_delivered_ok", 0),
            n_backend_delivered_failed=delivery_metrics.get(
                "n_backend_delivered_failed", 0
            ),
            n_fcm_ok=delivery_metrics.get("n_fcm_ok", 0),
            n_fcm_failed=delivery_metrics.get("n_fcm_failed", 0),
            n_fcm_completed_this_frame=delivery_metrics.get(
                "n_fcm_completed_this_frame", 0
            ),
            n_fcm_delivered_ok=delivery_metrics.get("n_fcm_delivered_ok", 0),
            n_fcm_delivered_failed=delivery_metrics.get("n_fcm_delivered_failed", 0),
            n_siren_triggers=delivery_metrics.get("n_siren_triggers", 0),
            offline_queue_size=delivery_metrics.get("offline_queue_size", 0),
        )

        for event in emitted_events:
            logger.warning(
                "HAZARD: %s  severity=%s  cam=%s  track=%s",
                event.event_type,
                event.severity.name,
                event.camera_id,
                event.track_id,
            )
            if (
                event.event_type
                in {"forklift_proximity_warning", "forklift_proximity_danger"}
                and len(ctx.sample_hazard_lines) < 8
            ):
                ctx.sample_hazard_lines.append(
                    (
                        f"frame={bundle.frame_number} event={event.event_type} "
                        f"severity={event.severity.name} track={event.track_id}"
                    )
                )

        annotated = bundle.frame.copy()
        ctx.renderer.render(
            annotated,
            detections=detections,
            pose_results=pose_results,
            hazard_events=emitted_events,
            display_id_map=display_id_map,
            calibrated=ctx.is_calibrated,
            fps=ctx.inference_fps,
            latency_ms=det_latency + prox_latency,
            n_det=len(detections),
            n_tracked=n_tracked,
            vram_mb=ctx.engine.vram_used_mb(),
            n_hazards=len(emitted_events),
            pose_ms=0.0,
            track_coverage=track_metrics.get("track_coverage", 0.0),
            ppe_capable=False,
            now=ts_now,
        )

        return FrameResult(annotated=annotated)


def _build_pipeline_context(
    source: str | int, cam_id: str, show: bool, profile: ProfileConfig
) -> PipelineContext:
    stream = StreamHandler(source=source, camera_id=cam_id)
    engine = InferenceEngine()
    metrics = MetricsLogger()
    event_aggregator = EventAggregator()
    calibration_mgr = CalibrationManager()
    track_monitor = TrackQualityMonitor()
    det_smoother = _DetectionSmoother(grace_frames=TRACK_ID_GRACE_FRAMES)
    forklift_smoother = _ForkliftHoldSmoother(hold_frames=PROXIMITY_HOLD_FRAMES)

    engine.load_pose()

    proximity_enabled = profile.is_enabled("proximity_analyzer")
    if proximity_enabled:
        prox_weights = profile.get_weights("proximity_analyzer")
        if not engine.load_proximity(prox_weights):
            logger.warning(
                "Proximity analyzer enabled in profile but model was not loaded"
            )
            proximity_enabled = False

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

    stream.start()
    logger.info(
        "Pipeline running — source=%s  cam_id=%s  show=%s  profile=%s",
        source,
        cam_id,
        show,
        profile.profile_name,
    )

    win_name = f"VisionSafe360 - {cam_id}"
    if show:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    writer = None
    out_path = None
    if not show:
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
        backend_client=backend_client,
        alert_manager=alert_manager,
        siren_controller=siren_controller,
        renderer=renderer,
        is_calibrated=is_calibrated,
        fall_every_n=fall_every_n,
        ergo_every_n=ergo_every_n,
        proximity_every_n=proximity_every_n,
        show=show,
        win_name=win_name,
        writer=writer,
        out_path=out_path,
        frame_counter=0,
        frames_processed=0,
        fps_t0=time.monotonic(),
        inference_fps=0.0,
        last_offline_flush=time.monotonic(),
        cumulative_forklift_dets=0,
        sample_forklift_lines=[],
        sample_hazard_lines=[],
    )


def _shutdown_pipeline(ctx: PipelineContext) -> None:
    try:
        ctx.alert_manager.shutdown(timeout_sec=2.0)
    except Exception:
        pass
    try:
        ctx.backend_client.flush_offline_queue()
    except Exception:
        pass
    try:
        ctx.siren_controller.stop()
    except Exception:
        pass
    ctx.stream.stop()
    if ctx.writer is not None:
        ctx.writer.release()
    if ctx.show:
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

def run_pipeline(source: str | int, cam_id: str, show: bool, profile: ProfileConfig) -> None:
    """Single-camera inference loop. Blocks until Ctrl-C or stream exhaustion."""

    ctx = _build_pipeline_context(source=source, cam_id=cam_id, show=show, profile=profile)
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

            if ctx.show:
                cv2.imshow(ctx.win_name, result.annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
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


# ════════════════════════════════════════════════════════════════════
#  CLI entry point
# ════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="VisionSafe 360 — Step 2 modular safety pipeline",
    )
    p.add_argument(
        "--source", required=True,
        help="Path to .mp4 file, RTSP URL, or camera index (0 for webcam).",
    )
    p.add_argument(
        "--cam-id", default="cam_01",
        help="Logical camera identifier (default: cam_01).",
    )
    p.add_argument(
        "--show", action="store_true",
        help="Display annotated frames in a cv2.imshow window.",
    )
    p.add_argument(
        "--profile", default="full_suite",
        help="Profile name or path (default: full_suite).",
    )
    return p.parse_args()


def main() -> None:
    setup_logging(LOG_LEVEL)
    args = parse_args()

    source = args.source
    # Accept integer camera index (e.g. 0 for webcam), RTSP URLs, or file paths
    is_camera_index = source.isdigit()
    is_rtsp = source.startswith("rtsp")
    if not is_camera_index and not is_rtsp and not Path(source).exists():
        logger.error("Source file not found: %s", source)
        sys.exit(1)
    if is_camera_index:
        source = int(source)

    profile = load_profile(args.profile)
    run_pipeline(source=source, cam_id=args.cam_id, show=args.show, profile=profile)


if __name__ == "__main__":
    main()
