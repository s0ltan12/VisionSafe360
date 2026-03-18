"""
VisionSafe 360 — Offline Evaluation Harness

Runs N reference video clips through the pipeline, captures telemetry, and
produces a structured report.  Designed as a CI-like gate before deployment.

Usage:
    python -m eval.run --profile full_suite --clips eval/clips/*.mp4
    python -m eval.run --profile ppe_only --clips eval/clips/ppe_test.mp4

Outputs (in eval/results/<timestamp>/):
    report.json          — aggregated metrics per clip and overall
    <cam_id>_annotated.mp4 — annotated video with hazard overlays
    <cam_id>_telemetry.jsonl — per-frame JSON lines
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

# ── Path bootstrapping ──────────────────────────────────────────────
_EVAL_DIR = Path(__file__).resolve().parent           # eval/
_EDGE_AI_DIR = _EVAL_DIR.parent                        # edge_ai/
if str(_EDGE_AI_DIR / "src") not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR / "src"))
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

# Suppress YOLO verbosity
os.environ.setdefault("YOLO_VERBOSE", "false")
# Force X11 on Wayland
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import cv2
import numpy as np

from src.config.settings import TARGET_INFER_FPS, OUTPUT_DIR
from src.config.profile import load_profile, ProfileConfig
from src.config.inference.inference_engine import InferenceEngine
from src.streaming.stream_handler import StreamHandler
from src.analysis.hazard_analyzer import HazardAnalyzer
from src.analysis.posture_analyzer import PostureAnalyzer
from src.analysis.event_aggregator import EventAggregator
from src.analysis.calibration import CalibrationManager
from src.analysis.track_quality import TrackQualityMonitor
from src.analysis.capability_check import check_model_capabilities
from src.utils.logger import MetricsLogger, setup_logging
from src.utils.drawing import draw_detections, draw_hud, draw_hazard_events

logger = logging.getLogger("EvalHarness")


# ════════════════════════════════════════════════════════════════════
#  Single-clip evaluation
# ════════════════════════════════════════════════════════════════════

def evaluate_clip(
    clip_path: str,
    profile: ProfileConfig,
    engine: InferenceEngine,
    result_dir: Path,
    cam_id: str = "eval_cam",
    save_video: bool = True,
) -> Dict[str, Any]:
    """Run one clip through the full pipeline and return a metrics dict."""

    clip_name = Path(clip_path).stem
    logger.info("━━━ Evaluating clip: %s ━━━", clip_name)

    # ── Telemetry sink (captures JSON lines in memory) ──────────────
    telemetry_buf = StringIO()
    metrics = MetricsLogger(stream=telemetry_buf)

    # ── Components ──────────────────────────────────────────────────
    event_aggregator = EventAggregator()
    calibration_mgr = CalibrationManager()
    track_monitor = TrackQualityMonitor()

    is_calibrated = calibration_mgr.is_calibrated(cam_id)

    # ── Pose ────────────────────────────────────────────────────────
    pose_enabled = profile.is_enabled("pose")

    # ── Analyzers ───────────────────────────────────────────────────
    hazard_analyzer = None
    if profile.is_enabled("hazard_analyzer"):
        hazard_analyzer = HazardAnalyzer(
            ppe_enabled=profile.is_sub_enabled("hazard_analyzer", "ppe"),
            proximity_enabled=profile.is_sub_enabled("hazard_analyzer", "proximity"),
            fall_enabled=profile.is_sub_enabled("hazard_analyzer", "fall"),
            calibration_mgr=calibration_mgr,
        )

    posture_analyzer = None
    if profile.is_enabled("posture_analyzer") and pose_enabled:
        posture_analyzer = PostureAnalyzer()

    # ── Read clip via OpenCV (no deque — process every frame) ───────
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        logger.error("Cannot open clip: %s", clip_path)
        return {"clip": clip_name, "error": "cannot_open"}

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info("Source FPS=%.1f  total_frames=%d", source_fps, total_source_frames)

    # ── Scheduling ──────────────────────────────────────────────────
    pose_every_n = profile.get_schedule("pose") if pose_enabled else 9999
    ppe_every_n = profile.get_sub_schedule("hazard_analyzer", "ppe")
    prox_every_n = profile.get_sub_schedule("hazard_analyzer", "proximity")
    fall_every_n = profile.get_sub_schedule("hazard_analyzer", "fall")
    ergo_every_n = profile.get_schedule("posture_analyzer")

    # ── Writer ──────────────────────────────────────────────────────
    writer = None
    out_path = result_dir / f"{clip_name}_annotated.mp4"

    # ── Counters ────────────────────────────────────────────────────
    frames_processed = 0
    frame_counter = 0
    total_events = 0
    event_type_counts: Dict[str, int] = {}
    latencies: List[float] = []
    fps_t0 = time.monotonic()
    inference_fps = 0.0

    from src.models.detection import Detection

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_counter += 1

        # ── Bundle-like object for inference engine ─────────────────
        class FakeBundle:
            pass
        bundle = FakeBundle()
        bundle.frame = frame
        bundle.frame_number = frame_counter
        bundle.camera_id = cam_id
        bundle.timestamp = time.time()

        loop_start = time.monotonic()

        # ── Detector + ByteTrack ────────────────────────────────────
        try:
            detections, det_latency = engine.run_tracker(bundle)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                logger.critical("CUDA OOM: %s", exc)
                break
            raise

        latencies.append(det_latency)
        n_tracked = sum(1 for d in detections if d.track_id is not None)

        # ── Track Quality ───────────────────────────────────────────
        track_metrics = track_monitor.update(detections, time.time())
        display_id_map = track_monitor.remap_detections_display_ids(detections)

        # ── Pose ────────────────────────────────────────────────────
        pose_results = None
        pose_latency = 0.0
        if pose_enabled and frame_counter % pose_every_n == 0:
            try:
                pose_results, pose_latency = engine.run_pose(bundle)
            except RuntimeError:
                pass

        # ── Hazard analysis ─────────────────────────────────────────
        hazard_events = []
        ts_now = time.time()
        if hazard_analyzer is not None:
            hazard_events = hazard_analyzer.analyze(
                detections,
                camera_id=cam_id,
                frame_number=frame_counter,
                timestamp=ts_now,
                ppe_this_frame=(frame_counter % ppe_every_n == 0),
                proximity_this_frame=(frame_counter % prox_every_n == 0),
                fall_this_frame=(frame_counter % fall_every_n == 0),
            )

        # ── Posture analysis ────────────────────────────────────────
        if (posture_analyzer is not None
                and pose_results is not None
                and frame_counter % ergo_every_n == 0):
            hazard_events.extend(posture_analyzer.analyze(
                pose_results,
                camera_id=cam_id,
                frame_number=frame_counter,
                timestamp=ts_now,
            ))

        # ── Event aggregation ───────────────────────────────────────
        emitted = event_aggregator.process(hazard_events, ts_now)
        total_events += len(emitted)
        for ev in emitted:
            event_type_counts[ev.event_type] = event_type_counts.get(ev.event_type, 0) + 1

        frames_processed += 1

        # Rolling FPS
        if frames_processed % 30 == 0:
            elapsed = time.monotonic() - fps_t0
            inference_fps = 30.0 / elapsed if elapsed > 0 else 0.0
            fps_t0 = time.monotonic()

        # ── Telemetry ──────────────────────────────────────────────
        metrics.log_frame(
            cam_id=cam_id,
            frame_no=frame_counter,
            input_fps=source_fps,
            inference_fps=inference_fps,
            inference_ms=det_latency,
            n_detections=len(detections),
            n_tracked=n_tracked,
            dropped_frames=0,
            vram_mb=engine.vram_used_mb(),
            n_hazard_events=len(emitted),
            hazard_types=[e.event_type for e in emitted] if emitted else [],
            pose_ms=round(pose_latency, 1),
            track_coverage=track_metrics.get("track_coverage", 0.0),
            calibrated=is_calibrated,
        )

        # ── Annotated frame ────────────────────────────────────────
        if save_video:
            annotated = frame.copy()
            draw_detections(annotated, detections, display_id_map=display_id_map)
            if emitted:
                draw_hazard_events(annotated, emitted)
            draw_hud(
                annotated,
                fps=inference_fps,
                latency_ms=det_latency,
                n_det=len(detections),
                n_tracked=n_tracked,
                vram_mb=engine.vram_used_mb(),
                n_hazards=len(emitted),
                pose_ms=pose_latency,
                calibrated=is_calibrated,
            )
            if writer is None:
                h, w = annotated.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(out_path), fourcc, source_fps, (w, h))
            writer.write(annotated)

    cap.release()
    if writer is not None:
        writer.release()

    # ── Compute metrics ─────────────────────────────────────────────
    duration_sec = frames_processed / source_fps if source_fps > 0 else 0
    latencies_np = np.array(latencies) if latencies else np.array([0.0])

    report = {
        "clip": clip_name,
        "source_fps": round(source_fps, 1),
        "total_source_frames": total_source_frames,
        "frames_processed": frames_processed,
        "duration_sec": round(duration_sec, 1),
        "calibrated": is_calibrated,
        "event_rate_per_min": round((total_events / duration_sec * 60) if duration_sec > 0 else 0, 2),
        "total_events": total_events,
        "event_type_counts": event_type_counts,
        "false_alarm_proxy_events_per_min": round(
            (total_events / duration_sec * 60) if duration_sec > 0 else 0, 2,
        ),
        "avg_latency_ms": round(float(latencies_np.mean()), 1),
        "p50_latency_ms": round(float(np.percentile(latencies_np, 50)), 1),
        "p95_latency_ms": round(float(np.percentile(latencies_np, 95)), 1),
        "p99_latency_ms": round(float(np.percentile(latencies_np, 99)), 1),
        "max_latency_ms": round(float(latencies_np.max()), 1),
        "track_stability": track_metrics.get("track_coverage", 0.0),
        "id_switches_per_min": track_metrics.get("id_switches_per_min", 0.0),
        "annotated_video": str(out_path) if save_video else None,
    }

    # ── Save per-clip telemetry ─────────────────────────────────────
    telemetry_path = result_dir / f"{clip_name}_telemetry.jsonl"
    telemetry_path.write_text(telemetry_buf.getvalue())
    report["telemetry_file"] = str(telemetry_path)

    logger.info("Clip %s — events=%d  avg_lat=%.1fms  p95=%.1fms  event_rate=%.1f/min",
                clip_name, total_events, report["avg_latency_ms"],
                report["p95_latency_ms"], report["event_rate_per_min"])
    return report


# ════════════════════════════════════════════════════════════════════
#  Main evaluation runner
# ════════════════════════════════════════════════════════════════════

def run_evaluation(clip_paths: List[str], profile_name: str, save_video: bool = True) -> Dict[str, Any]:
    """Run all clips and produce an aggregate report."""

    setup_logging("INFO")
    profile = load_profile(profile_name)

    # ── Results directory ───────────────────────────────────────────
    ts_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = _EVAL_DIR / "results" / ts_label
    result_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Results directory: %s", result_dir)

    # ── Shared engine (one GPU allocation) ──────────────────────────
    engine = InferenceEngine()
    engine.load_detector()

    cap_report = check_model_capabilities(
        engine.class_names,
        ppe_enabled=profile.is_sub_enabled("hazard_analyzer", "ppe"),
        proximity_enabled=profile.is_sub_enabled("hazard_analyzer", "proximity"),
        fall_enabled=profile.is_sub_enabled("hazard_analyzer", "fall"),
    )
    cap_report.log_report()

    pose_enabled = profile.is_enabled("pose")
    if pose_enabled:
        try:
            engine.load_pose()
        except Exception as exc:
            logger.warning("Pose model load failed: %s", exc)

    # ── Evaluate each clip ──────────────────────────────────────────
    clip_reports: List[Dict[str, Any]] = []
    for clip_path in clip_paths:
        report = evaluate_clip(
            clip_path=clip_path,
            profile=profile,
            engine=engine,
            result_dir=result_dir,
            save_video=save_video,
        )
        clip_reports.append(report)

    # ── Aggregate report ────────────────────────────────────────────
    total_frames = sum(r.get("frames_processed", 0) for r in clip_reports)
    total_events = sum(r.get("total_events", 0) for r in clip_reports)
    total_duration = sum(r.get("duration_sec", 0) for r in clip_reports)
    all_latencies_avg = [r["avg_latency_ms"] for r in clip_reports if "avg_latency_ms" in r]
    all_latencies_p95 = [r["p95_latency_ms"] for r in clip_reports if "p95_latency_ms" in r]

    aggregate = {
        "eval_timestamp": ts_label,
        "profile": profile_name,
        "n_clips": len(clip_reports),
        "total_frames": total_frames,
        "total_duration_sec": round(total_duration, 1),
        "total_events": total_events,
        "overall_event_rate_per_min": round(
            (total_events / total_duration * 60) if total_duration > 0 else 0, 2,
        ),
        "mean_avg_latency_ms": round(np.mean(all_latencies_avg), 1) if all_latencies_avg else 0.0,
        "mean_p95_latency_ms": round(np.mean(all_latencies_p95), 1) if all_latencies_p95 else 0.0,
        "capability_report": {
            "ppe_ready": cap_report.ppe_ready if hasattr(cap_report, "ppe_ready") else "unknown",
            "vehicle_mode": cap_report.vehicle_mode if hasattr(cap_report, "vehicle_mode") else "unknown",
        },
        "clips": clip_reports,
    }

    # ── Write report ────────────────────────────────────────────────
    report_path = result_dir / "report.json"
    report_path.write_text(json.dumps(aggregate, indent=2, default=str))
    logger.info("━━━ Evaluation complete ━━━")
    logger.info("Report: %s", report_path)
    logger.info("Clips: %d  Frames: %d  Events: %d  Avg event rate: %.1f/min",
                len(clip_reports), total_frames, total_events,
                aggregate["overall_event_rate_per_min"])

    return aggregate


# ════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="VisionSafe360 Evaluation Harness")
    p.add_argument(
        "--clips", nargs="+", required=True,
        help="Paths or glob patterns to video clips (e.g. eval/clips/*.mp4)",
    )
    p.add_argument(
        "--profile", default="full_suite",
        help="Profile name (default: full_suite)",
    )
    p.add_argument(
        "--no-video", action="store_true",
        help="Skip writing annotated output videos (faster)",
    )
    args = p.parse_args()

    # Expand globs
    all_clips: List[str] = []
    for pattern in args.clips:
        expanded = glob.glob(pattern)
        if expanded:
            all_clips.extend(expanded)
        elif Path(pattern).exists():
            all_clips.append(pattern)
        else:
            logger.warning("No files matched: %s", pattern)
    all_clips = sorted(set(all_clips))

    if not all_clips:
        logger.error("No clips found. Provide paths via --clips")
        sys.exit(1)

    logger.info("Evaluating %d clip(s)", len(all_clips))
    run_evaluation(all_clips, profile_name=args.profile, save_video=not args.no_video)


if __name__ == "__main__":
    main()
