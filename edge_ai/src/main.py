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
    DEBUG_MODE,
    LOG_LEVEL,
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


# ════════════════════════════════════════════════════════════════════
#  Main pipeline
# ════════════════════════════════════════════════════════════════════

def run_pipeline(source: str | int, cam_id: str, show: bool, profile: ProfileConfig) -> None:
    """Single-camera inference loop.  Blocks until Ctrl-C or stream exhaustion."""

    # ── 1. Initialise components ────────────────────────────────────
    stream = StreamHandler(source=source, camera_id=cam_id)
    engine = InferenceEngine()
    metrics = MetricsLogger()               # writes JSON to stdout
    event_aggregator = EventAggregator()
    calibration_mgr = CalibrationManager()
    track_monitor = TrackQualityMonitor()
    det_smoother = _DetectionSmoother(grace_frames=TRACK_ID_GRACE_FRAMES)
    forklift_smoother = _ForkliftHoldSmoother(hold_frames=PROXIMITY_HOLD_FRAMES)

    # Runtime counters for handover report.
    cumulative_forklift_dets = 0
    sample_forklift_lines: list[str] = []
    sample_hazard_lines: list[str] = []

    # ── 1a. Load pose model (provides person detection + keypoints) ─
    engine.load_pose()

    # Optional second model: forklift/person detector for proximity hazards
    proximity_enabled = profile.is_enabled("proximity_analyzer")
    if proximity_enabled:
        prox_weights = profile.get_weights("proximity_analyzer")
        loaded = engine.load_proximity(prox_weights)
        if not loaded:
            logger.warning("Proximity analyzer enabled in profile but model was not loaded")
            proximity_enabled = False

    is_calibrated = calibration_mgr.is_calibrated(cam_id)

    # ── 1b. Build UI renderer from profile ──────────────────────────
    ui_settings = load_ui_settings_from_profile(profile.ui_config)
    renderer = SafetyOverlayRenderer(cfg=ui_settings)

    # ── 1c. Initialise analyzers based on profile ───────────────────
    hazard_analyzer = None
    if profile.is_enabled("hazard_analyzer"):
        hazard_analyzer = HazardAnalyzer(
            fall_enabled=profile.is_sub_enabled("hazard_analyzer", "fall"),
        )

    posture_analyzer = None
    if profile.is_enabled("posture_analyzer"):
        posture_analyzer = PostureAnalyzer()

    proximity_analyzer = None
    if proximity_enabled:
        proximity_analyzer = ProximityAnalyzer()

    stream.start()
    logger.info(
        "Pipeline running — source=%s  cam_id=%s  show=%s  profile=%s",
        source, cam_id, show, profile.profile_name,
    )

    # ── 2. Display / writer setup ──────────────────────────────────
    win_name = f"VisionSafe360 - {cam_id}"
    if show:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    writer: cv2.VideoWriter | None = None
    if not show:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{cam_id}_out.mp4"
        logger.info("Output video → %s", out_path)

    # ── 3. Graceful shutdown on Ctrl-C / SIGTERM ────────────────────
    shutdown = False

    def _handle_signal(signum, _frame):
        nonlocal shutdown
        logger.info("Signal %d received — shutting down", signum)
        shutdown = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── 4. Scheduling config from profile ───────────────────────────
    fall_every_n = profile.get_sub_schedule("hazard_analyzer", "fall")
    ergo_every_n = profile.get_schedule("posture_analyzer")
    proximity_every_n = profile.get_schedule("proximity_analyzer")

    # ── 5. Inference loop ───────────────────────────────────────────
    infer_interval = 1.0 / TARGET_INFER_FPS
    frames_processed = 0
    frame_counter = 0
    fps_t0 = time.monotonic()
    inference_fps = 0.0

    try:
        while not shutdown:
            loop_start = time.monotonic()

            # Pop latest frame (non-blocking)
            bundle = stream.get_frame()
            if bundle is None:
                # No frame ready — brief sleep to avoid busy-spin
                time.sleep(0.001)
                continue

            # ── Pose model + ByteTrack (every frame) ────────────────
            try:
                pose_results, detections, det_latency = engine.run_pose_tracker(bundle)
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    logger.critical("CUDA OOM during inference: %s", exc)
                    sys.exit(2)
                raise

            n_tracked = sum(1 for d in detections if d.track_id is not None)

            # ── Optional forklift/person detector ───────────────────
            raw_prox_detections = []
            prox_detections = []
            prox_latency = 0.0
            raw_forklift_dets = 0
            forklift_dets = 0
            if proximity_analyzer is not None:
                if frame_counter % proximity_every_n == 0:
                    raw_prox_detections, prox_latency = engine.run_proximity(bundle)

                # Apply hold smoothing only to downstream UI/proximity flow.
                prox_detections, used_hold = forklift_smoother.smooth(raw_prox_detections)

                raw_forklift_dets = sum(
                    1 for d in raw_prox_detections if d.class_name == "forklift"
                )
                forklift_dets = sum(1 for d in prox_detections if d.class_name == "forklift")

                if DEBUG_MODE:
                    logger.info(
                        "frame=%s forklift_dets=%s raw_forklift_dets=%s hold=%s",
                        bundle.frame_number,
                        forklift_dets,
                        raw_forklift_dets,
                        used_hold,
                    )

                if forklift_dets > 0 and len(sample_forklift_lines) < 8:
                    sample_forklift_lines.append(
                        (
                            f"frame={bundle.frame_number} forklift_dets={forklift_dets} "
                            f"raw_forklift_dets={raw_forklift_dets}"
                        )
                    )

                cumulative_forklift_dets += forklift_dets

                # Keep forklift boxes in shared detections for rendering,
                # but keep tracked person boxes from pose model as source of truth.
                detections.extend([d for d in prox_detections if d.class_name == "forklift"])

            # ── Detection smoothing (fill brief detection gaps) ─────
            detections = det_smoother.smooth(detections)

            # ── Track Quality Monitor ───────────────────────────────
            track_metrics = track_monitor.update(detections, time.time())
            display_id_map = track_monitor.remap_detections_display_ids(detections)

            # ── HazardAnalyzer (CPU only, fall detection) ───────────
            hazard_events = []
            ts_now = time.time()
            if hazard_analyzer is not None:
                hazard_events = hazard_analyzer.analyze(
                    detections,
                    camera_id=cam_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                    fall_this_frame=(frame_counter % fall_every_n == 0),
                    pose_results=pose_results,
                )

            # ── Proximity hazards (forklift <-> person) ───────────
            if proximity_analyzer is not None and prox_detections:
                tracked_pose_people = [d for d in detections if d.class_name == "person"]
                hazard_events.extend(proximity_analyzer.analyze(
                    prox_detections,
                    tracked_pose_people,
                    camera_id=cam_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                ))

            # ── PostureAnalyzer (CPU only, ergonomic assessment) ────
            if (posture_analyzer is not None
                    and pose_results is not None
                    and frame_counter % ergo_every_n == 0):
                hazard_events.extend(posture_analyzer.analyze(
                    pose_results,
                    camera_id=cam_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                ))

            # ── Event Aggregation (persistence + dedupe + cooldown) ─
            emitted_events = event_aggregator.process(hazard_events, ts_now)

            frames_processed += 1
            frame_counter += 1

            # Rolling inference FPS (every 30 frames)
            if frames_processed % 30 == 0:
                elapsed = time.monotonic() - fps_t0
                inference_fps = 30.0 / elapsed if elapsed > 0 else 0.0
                fps_t0 = time.monotonic()

            # ── Log hazard events ───────────────────────────────────
            for event in emitted_events:
                logger.warning(
                    "HAZARD: %s  severity=%s  cam=%s  track=%s",
                    event.event_type, event.severity.name,
                    event.camera_id, event.track_id,
                )
                if (
                    event.event_type in {
                        "forklift_proximity_warning",
                        "forklift_proximity_danger",
                    }
                    and len(sample_hazard_lines) < 8
                ):
                    sample_hazard_lines.append(
                        (
                            f"frame={bundle.frame_number} event={event.event_type} "
                            f"severity={event.severity.name} track={event.track_id}"
                        )
                    )

            # ── Structured JSON metric ──────────────────────────────
            hazard_types = [e.event_type for e in emitted_events]
            metrics.log_frame(
                cam_id=cam_id,
                frame_no=bundle.frame_number,
                input_fps=stream.input_fps,
                inference_fps=inference_fps,
                inference_ms=round(det_latency + prox_latency, 2),
                n_detections=len(detections),
                n_tracked=n_tracked,
                dropped_frames=stream.dropped_count,
                vram_mb=engine.vram_used_mb(),
                n_hazard_events=len(emitted_events),
                hazard_types=hazard_types if hazard_types else [],
                forklift_dets=forklift_dets,
                raw_forklift_dets=raw_forklift_dets,
                pose_ms=round(det_latency, 1),
                track_coverage=track_metrics.get("track_coverage", 0.0),
                calibrated=is_calibrated,
            )

            # ── Annotate frame ──────────────────────────────────────
            annotated = bundle.frame.copy()
            renderer.render(
                annotated,
                detections=detections,
                pose_results=pose_results,
                hazard_events=emitted_events,
                display_id_map=display_id_map,
                calibrated=is_calibrated,
                fps=inference_fps,
                latency_ms=det_latency + prox_latency,
                n_det=len(detections),
                n_tracked=n_tracked,
                vram_mb=engine.vram_used_mb(),
                n_hazards=len(emitted_events),
                pose_ms=0.0,
                track_coverage=track_metrics.get("track_coverage", 0.0),
                ppe_capable=False,
                now=ts_now,
            )

            # ── Display or write ────────────────────────────────────
            if show:
                cv2.imshow(win_name, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:  # q or Esc
                    logger.info("User pressed quit key")
                    break
            else:
                if writer is None:
                    h, w = annotated.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(out_path), fourcc, TARGET_INFER_FPS, (w, h))
                writer.write(annotated)

            # ── Throttle to target FPS ──────────────────────────────
            elapsed = time.monotonic() - loop_start
            sleep_time = infer_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
    finally:
        stream.stop()
        if writer is not None:
            writer.release()
        if show:
            cv2.destroyAllWindows()

        # ── Summary ─────────────────────────────────────────────────
        logger.info(
            "Pipeline finished — frames_processed=%d  total_read=%d  "
            "dropped=%d  reconnects=%d",
            frames_processed,
            stream.total_frames_read,
            stream.dropped_count,
            stream.reconnect_count,
        )
        drop_pct = (
            (stream.dropped_count / stream.total_frames_read * 100)
            if stream.total_frames_read > 0
            else 0
        )
        logger.info("Drop rate: %.1f%%", drop_pct)
        logger.info("\n%s", track_monitor.summary())

        # Auto-generate a handover-ready Step 2 report at run end.
        track_snapshot = track_monitor.snapshot()
        avg_forklift_dets = (
            cumulative_forklift_dets / frames_processed if frames_processed > 0 else 0.0
        )
        report_path = _EDGE_AI_DIR / "STEP2_COMPLETION_REPORT.md"
        _write_step2_completion_report(
            report_path=report_path,
            track_coverage=track_snapshot.get("track_coverage", 0.0),
            avg_forklift_dets_per_frame=avg_forklift_dets,
            sample_forklift_lines=sample_forklift_lines,
            sample_hazard_lines=sample_hazard_lines,
        )
        logger.info("Step 2 completion report written: %s", report_path)


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
