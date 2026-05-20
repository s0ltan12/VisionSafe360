"""Multi-camera parallel pipeline with shared GPU models.

Extracted from main.py — preserves original logic unchanged.
"""
from __future__ import annotations

import logging
import signal
import time
from typing import Any, Optional

import cv2

from ..config.settings import (
    ALERTS_ENABLED,
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
from ..ui.renderer import SafetyOverlayRenderer
from ..config.ui_settings import load_ui_settings_from_profile
from ..smoothing.detection_smoother import DetectionSmoother, ForkliftHoldSmoother
from .context import CameraContext

logger = logging.getLogger("PipelineOrchestrator")


def _build_camera_context(
    source: str | int,
    cam_id: str,
    show: bool,
    profile: ProfileConfig,
    calibration_mgr: CalibrationManager
) -> CameraContext:
    """Build per-camera context (no GPU resources - those are shared)."""
    stream = StreamHandler(source=source, camera_id=cam_id)

    is_calibrated = calibration_mgr.is_calibrated(cam_id)
    ui_settings = load_ui_settings_from_profile(profile.ui_config)
    renderer = SafetyOverlayRenderer(cfg=ui_settings)

    hazard_analyzer = None
    if profile.is_enabled("hazard_analyzer"):
        hazard_analyzer = HazardAnalyzer(
            fall_enabled=profile.is_sub_enabled("hazard_analyzer", "fall")
        )

    posture_analyzer = PostureAnalyzer() if profile.is_enabled("posture_analyzer") else None
    proximity_analyzer = ProximityAnalyzer() if profile.is_enabled("proximity_analyzer") else None
    ppe_analyzer = PPEAnalyzer() if profile.is_enabled("ppe_analyzer") else None

    win_name = f"VisionSafe360 - {cam_id}"
    out_path = OUTPUT_DIR / f"{cam_id}_output.mp4" if not show else None

    return CameraContext(
        cam_id=cam_id,
        stream=stream,
        event_aggregator=EventAggregator(),
        track_monitor=TrackQualityMonitor(),
        det_smoother=DetectionSmoother(grace_frames=TRACK_ID_GRACE_FRAMES),
        forklift_smoother=ForkliftHoldSmoother(hold_frames=PROXIMITY_HOLD_FRAMES),
        hazard_analyzer=hazard_analyzer,
        posture_analyzer=posture_analyzer,
        proximity_analyzer=proximity_analyzer,
        ppe_analyzer=ppe_analyzer,
        renderer=renderer,
        is_calibrated=is_calibrated,
        win_name=win_name,
        writer=None,
        out_path=out_path,
        frame_counter=0,
        frames_processed=0,
        fps_t0=time.monotonic(),
        inference_fps=0.0,
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

    # ── Per-camera contexts ─────────────────────────────────────────
    cameras: list[CameraContext] = []
    for idx, source in enumerate(sources):
        cam_id = f"cam_{idx + 1:02d}"
        cam_ctx = _build_camera_context(source, cam_id, show, profile, calibration_mgr)
        cameras.append(cam_ctx)
        logger.info("  Camera %s: %s", cam_id, source)

    # ── Start all camera streams ────────────────────────────────────
    for cam in cameras:
        cam.stream.start()
        if show:
            cv2.namedWindow(cam.win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

    # ── Scheduling ──────────────────────────────────────────────────
    fall_every_n = profile.get_sub_schedule("hazard_analyzer", "fall")
    ergo_every_n = profile.get_schedule("posture_analyzer")
    proximity_every_n = profile.get_schedule("proximity_analyzer")
    ppe_every_n = profile.get_schedule("ppe_analyzer")

    infer_interval = 1.0 / TARGET_INFER_FPS
    global_shutdown = False
    last_offline_flush = time.monotonic()

    def _handle_signal(signum, _frame):
        nonlocal global_shutdown
        logger.info("Signal %d received — shutting down all cameras", signum)
        global_shutdown = True
        for cam in cameras:
            cam.shutdown = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Wait briefly for streams to start capturing
    time.sleep(0.5)

    logger.info("═══ Pipeline running (press 'q' to quit) ═══")

    try:
        while not global_shutdown:
            loop_start = time.monotonic()
            any_frame_processed = False

            # ── Process each camera ─────────────────────────────────
            for cam in cameras:
                if cam.shutdown:
                    continue

                bundle = cam.stream.get_frame()
                if bundle is None:
                    continue

                any_frame_processed = True
                cam.frame_counter += 1

                # Log progress every 30 frames
                if cam.frame_counter % 30 == 0:
                    logger.info("  %s: %d frames processed", cam.cam_id, cam.frame_counter)

                # ── Inference (shared engine) ───────────────────────
                try:
                    pose_results, detections, det_latency = engine.run_pose_tracker(bundle)
                except RuntimeError as exc:
                    if "out of memory" in str(exc).lower():
                        logger.critical("CUDA OOM: %s", exc)
                        global_shutdown = True
                        break
                    raise

                # ── Proximity detection ─────────────────────────────
                raw_prox_detections: list = []
                prox_detections = []
                prox_latency = 0.0
                if proximity_enabled:
                    if cam.frame_counter % proximity_every_n == 0:
                        raw_prox_detections, prox_latency = engine.run_proximity(bundle)
                    prox_detections, _ = cam.forklift_smoother.smooth(raw_prox_detections)
                    detections.extend([d for d in prox_detections if d.class_name == "forklift"])

                # ── PPE detection ───────────────────────────────────
                ppe_detections = []
                ppe_latency = 0.0
                if ppe_enabled and cam.frame_counter % ppe_every_n == 0:
                    ppe_detections, ppe_latency = engine.run_ppe(bundle)
                    cam.last_ppe_detections = ppe_detections
                else:
                    ppe_detections = cam.last_ppe_detections

                detections = cam.det_smoother.smooth(detections)
                render_detections = detections + ppe_detections

                n_tracked = sum(1 for d in detections if d.track_id is not None)
                track_metrics = cam.track_monitor.update(detections, time.time())
                display_id_map = cam.track_monitor.remap_detections_display_ids(detections)

                # ── Hazard analysis ─────────────────────────────────
                hazard_events = []
                ts_now = time.time()
                if cam.hazard_analyzer is not None:
                    hazard_events.extend(cam.hazard_analyzer.analyze(
                        pose_results=pose_results,
                        detections=detections,
                        camera_id=cam.cam_id,
                        frame_number=cam.frame_counter,
                        timestamp=ts_now,
                        fall_this_frame=(cam.frame_counter % fall_every_n == 0),
                    ))

                # ── Posture analysis ────────────────────────────────
                if cam.posture_analyzer is not None and cam.frame_counter % ergo_every_n == 0:
                    hazard_events.extend(cam.posture_analyzer.analyze(
                        pose_results,
                        camera_id=cam.cam_id,
                        frame_number=cam.frame_counter,
                        timestamp=ts_now,
                    ))
                    if BACKEND_EVENTS_ENABLED:
                        for sample in getattr(cam.posture_analyzer, "last_samples", []):
                            if not getattr(sample, "camera_name", None) and BACKEND_CAMERA_NAME:
                                sample.camera_name = BACKEND_CAMERA_NAME
                            if not getattr(sample, "worker_id", None) and BACKEND_WORKER_ID:
                                sample.worker_id = BACKEND_WORKER_ID
                            if not getattr(sample, "worker_gpu_id", None) and BACKEND_WORKER_GPU_ID:
                                sample.worker_gpu_id = BACKEND_WORKER_GPU_ID
                            backend_client.submit_ergonomic_sample_fast(sample)

                # ── Proximity analysis ──────────────────────────────
                if cam.proximity_analyzer is not None and prox_detections:
                    # Merge forklift detections into main detections for analysis
                    all_detections = detections + [d for d in prox_detections if d.class_name == "forklift"]
                    hazard_events.extend(cam.proximity_analyzer.analyze(
                        detections=all_detections,
                        tracked_pose_people=detections,
                        camera_id=cam.cam_id,
                        frame_number=cam.frame_counter,
                        timestamp=ts_now,
                    ))

                # ── PPE compliance analysis ────────────────────────
                if cam.ppe_analyzer is not None and ppe_detections:
                    hazard_events.extend(cam.ppe_analyzer.analyze(
                        ppe_detections=ppe_detections,
                        tracked_people=[d for d in detections if d.class_name == "person"],
                        camera_id=cam.cam_id,
                        frame_number=cam.frame_counter,
                        timestamp=ts_now,
                    ))

                # ── Event aggregation ───────────────────────────────
                emitted_events = cam.event_aggregator.process(hazard_events, ts_now)
                for event in emitted_events:
                    if not getattr(event, "camera_name", None) and BACKEND_CAMERA_NAME:
                        event.camera_name = BACKEND_CAMERA_NAME
                    if not getattr(event, "worker_id", None) and BACKEND_WORKER_ID:
                        event.worker_id = BACKEND_WORKER_ID
                    if not getattr(event, "worker_gpu_id", None) and BACKEND_WORKER_GPU_ID:
                        event.worker_gpu_id = BACKEND_WORKER_GPU_ID

                # ── Rendering ───────────────────────────────────────
                cam.frames_processed += 1
                if cam.frames_processed % 30 == 0:
                    elapsed = time.monotonic() - cam.fps_t0
                    cam.inference_fps = 30.0 / elapsed if elapsed > 0 else 0.0
                    cam.fps_t0 = time.monotonic()

                annotated = bundle.frame.copy()
                cam.renderer.render(
                    annotated,
                    detections=render_detections,
                    pose_results=pose_results,
                    hazard_events=emitted_events,
                    display_id_map=display_id_map,
                    calibrated=cam.is_calibrated,
                    fps=cam.inference_fps,
                    latency_ms=det_latency + prox_latency + ppe_latency,
                    n_det=len(detections),
                    n_tracked=n_tracked,
                    vram_mb=engine.vram_used_mb(),
                    n_hazards=len(emitted_events),
                    pose_ms=0.0,
                    track_coverage=track_metrics.get("track_coverage", 0.0),
                    ppe_capable=ppe_capable,
                    now=ts_now,
                )

                # ── Alerting ────────────────────────────────────────
                if emitted_events and ALERTS_ENABLED:
                    alert_manager.process_events(emitted_events, frame=annotated)

                # ── Display / Write ─────────────────────────────────
                if show:
                    cv2.imshow(cam.win_name, annotated)
                else:
                    if cam.writer is None and cam.out_path is not None:
                        h, w = annotated.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        cam.writer = cv2.VideoWriter(str(cam.out_path), fourcc, TARGET_INFER_FPS, (w, h))
                    if cam.writer is not None:
                        cam.writer.write(annotated)

            # ── Periodic offline flush ──────────────────────────────
            if BACKEND_EVENTS_ENABLED and (time.monotonic() - last_offline_flush) >= OFFLINE_FLUSH_INTERVAL_SEC:
                backend_client.flush_offline_queue(limit=OFFLINE_FLUSH_MAX_PER_CYCLE)
                last_offline_flush = time.monotonic()

            # ── Check if all streams finished ───────────────────────
            all_streams_done = all(not cam.stream.is_running for cam in cameras)
            if all_streams_done and not any_frame_processed:
                # Give one more chance to read remaining buffered frames
                time.sleep(0.1)
                still_have_frames = any(cam.stream.get_frame() is not None for cam in cameras)
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
        for cam in cameras:
            cam.stream.stop()
            if cam.writer is not None:
                cam.writer.release()

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
        for cam in cameras:
            drop_pct = (
                cam.stream.dropped_count / cam.stream.total_frames_read * 100
                if cam.stream.total_frames_read > 0 else 0.0
            )
            logger.info(
                "  %s: processed=%d  read=%d  dropped=%d (%.1f%%)  reconnects=%d",
                cam.cam_id,
                cam.frames_processed,
                cam.stream.total_frames_read,
                cam.stream.dropped_count,
                drop_pct,
                cam.stream.reconnect_count,
            )
