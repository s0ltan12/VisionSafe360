"""Per-frame inference, hazard detection, delivery, and rendering.

Extracted from main.py — preserves original algorithm unchanged.
"""
from __future__ import annotations

import logging
import sys
import time
import threading
from typing import Any

from ..config.settings import (
    ALERTS_ENABLED,
    BACKEND_EVENTS_ENABLED,
    OFFLINE_FLUSH_INTERVAL_SEC,
    OFFLINE_FLUSH_MAX_PER_CYCLE,
    SAFETY_ZONES_ENABLED,
    SAFETY_ZONES_REFRESH_INTERVAL_SEC,
)
from ..analysis.composite_hazard_engine import CompositeHazardEngine
from ..analysis.safety_zone_engine import SafetyZoneEngine
from ..analysis.zone_config_loader import ZoneConfigLoader
from .context import PipelineContext, FrameResult

logger = logging.getLogger("PipelineOrchestrator")


class FrameProcessor:
    """Per-frame processing of inference, hazard detection, delivery, rendering."""

    def __init__(self, ctx: PipelineContext) -> None:
        self._ctx = ctx
        self._composite_hazard_engine = CompositeHazardEngine()
        self._zone_config_loader = ZoneConfigLoader()
        self._safety_zone_engine = SafetyZoneEngine()
        self._last_safety_zone_refresh: dict[str, float] = {}

    def process(self, bundle) -> FrameResult:
        ctx = self._ctx

        pose_latency = 0.0
        if ctx.person_tracker_source == "ppe" and ctx.ppe_enabled:
            try:
                pose_results, pose_latency = ctx.engine.run_pose(bundle)
                detections, det_latency = ctx.engine.run_ppe_person_tracker(bundle)
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    logger.critical("CUDA OOM during inference: %s", exc)
                    sys.exit(2)
                raise
        else:
            try:
                pose_results, detections, det_latency = ctx.engine.run_pose_tracker(bundle)
                pose_latency = det_latency
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    logger.critical("CUDA OOM during inference: %s", exc)
                    sys.exit(2)
                raise
        prox_detections: list[Any] = []
        prox_latency = 0.0
        ppe_detections: list[Any] = []
        ppe_latency = 0.0
        raw_prox_detections: list[Any] = []
        raw_forklift_dets = 0
        forklift_dets = 0
        ts_now = time.time()

        if ctx.proximity_analyzer is not None:
            if ctx.frame_counter % ctx.proximity_every_n == 0:
                raw_prox_detections, prox_latency = ctx.engine.run_proximity(bundle)

            prox_detections, _used_hold = ctx.forklift_smoother.smooth(raw_prox_detections)
            raw_forklift_dets = sum(
                1 for d in raw_prox_detections if d.class_name == "forklift"
            )
            prox_detections = ctx.proximity_analyzer.prepare_detections(
                prox_detections,
                ts_now,
            )
            forklift_dets = sum(1 for d in prox_detections if d.class_name == "forklift")
            ctx.cumulative_forklift_dets += forklift_dets

            if forklift_dets > 0 and len(ctx.sample_forklift_lines) < 8:
                forklift_ids = [
                    d.track_id for d in prox_detections
                    if d.class_name == "forklift"
                ]
                ctx.sample_forklift_lines.append(
                    (
                        f"frame={bundle.frame_number} forklift_dets={forklift_dets} "
                        f"raw_forklift_dets={raw_forklift_dets} "
                        f"forklift_ids={forklift_ids}"
                    )
                )

            detections.extend([d for d in prox_detections if d.class_name == "forklift"])

        if ctx.ppe_enabled:
            if ctx.frame_counter % ctx.ppe_every_n == 0:
                ppe_detections, ppe_latency = ctx.engine.run_ppe(bundle)
                ctx.last_ppe_detections = ppe_detections
            else:
                ppe_detections = ctx.last_ppe_detections

        detections = ctx.det_smoother.smooth(detections)
        render_detections = detections + ppe_detections

        n_tracked = sum(1 for d in detections if d.track_id is not None)
        track_metrics = ctx.track_monitor.update(detections, time.time())
        display_id_map = ctx.track_monitor.remap_detections_display_ids(detections)

        hazard_events: list[Any] = []

        if SAFETY_ZONES_ENABLED:
            self._refresh_safety_zones(ctx.stream.camera_id, ts_now)
            hazard_events.extend(
                self._safety_zone_engine.analyze(
                    detections,
                    camera_id=ctx.stream.camera_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                    frame_shape=getattr(bundle.frame, "shape", None),
                )
            )

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
                    detections_are_prepared=True,
                )
            )
            hazard_events.extend(
                ctx.proximity_analyzer.forklift_telemetry_events(
                    prox_detections,
                    camera_id=ctx.stream.camera_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                )
            )
            hazard_events.extend(
                ctx.proximity_analyzer.distance_telemetry_events(
                    prox_detections,
                    camera_id=ctx.stream.camera_id,
                    frame_number=bundle.frame_number,
                    timestamp=ts_now,
                )
            )

        if ctx.ppe_analyzer is not None and ppe_detections:
            tracked_people = [d for d in detections if d.class_name == "person"]
            hazard_events.extend(
                ctx.ppe_analyzer.analyze(
                    ppe_detections=ppe_detections,
                    tracked_people=tracked_people,
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
            if BACKEND_EVENTS_ENABLED:
                for sample in getattr(ctx.posture_analyzer, "last_samples", []):
                    if not getattr(sample, "camera_name", None) and ctx.camera_name:
                        sample.camera_name = ctx.camera_name
                    if not getattr(sample, "worker_id", None) and ctx.worker_id:
                        sample.worker_id = ctx.worker_id
                    if not getattr(sample, "worker_gpu_id", None) and ctx.worker_gpu_id:
                        sample.worker_gpu_id = ctx.worker_gpu_id
                    ctx.backend_client.submit_ergonomic_sample_fast(sample)

        hazard_events = self._zone_config_loader.enrich_events(hazard_events)
        composite_events = self._composite_hazard_engine.process(hazard_events, ts_now)
        if composite_events:
            hazard_events = self._composite_hazard_engine.suppress_source_events(
                hazard_events,
                composite_events,
            )
        aggregation_input_events = hazard_events + composite_events
        emitted_events = ctx.event_aggregator.process(aggregation_input_events, ts_now)
        safety_overlay_events = _safety_overlay_events(
            emitted_events,
            aggregation_input_events,
        )
        for event in emitted_events:
            if not getattr(event, "camera_name", None) and ctx.camera_name:
                event.camera_name = ctx.camera_name
            if not getattr(event, "worker_id", None) and ctx.worker_id:
                event.worker_id = ctx.worker_id
            if not getattr(event, "worker_gpu_id", None) and ctx.worker_gpu_id:
                event.worker_gpu_id = ctx.worker_gpu_id

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

        annotated = bundle.frame.copy()
        ctx.renderer.render(
            annotated,
            detections=render_detections,
            pose_results=pose_results,
            hazard_events=safety_overlay_events,
            display_id_map=display_id_map,
            calibrated=ctx.is_calibrated,
            fps=ctx.inference_fps,
            latency_ms=det_latency + prox_latency + ppe_latency + pose_latency,
            n_det=len(detections),
            n_tracked=n_tracked,
            vram_mb=ctx.engine.vram_used_mb(),
            n_hazards=len(safety_overlay_events),
            pose_ms=0.0,
            track_coverage=track_metrics.get("track_coverage", 0.0),
            ppe_capable=ctx.ppe_capable,
            now=ts_now,
        )

        if ctx.frame_ring_buffer is not None:
            ctx.frame_ring_buffer.push(annotated, timestamp=ts_now)

        if ALERTS_ENABLED:
            delivery_metrics = ctx.alert_manager.process_events(
                emitted_events, frame=annotated, ring_buffer=ctx.frame_ring_buffer
            )

        if (
            BACKEND_EVENTS_ENABLED
            and (time.monotonic() - ctx.last_offline_flush) >= OFFLINE_FLUSH_INTERVAL_SEC
        ):
            flush_limit = max(0, int(OFFLINE_FLUSH_MAX_PER_CYCLE))
            # Important: avoid blocking the main video loop with HTTP requests.
            if flush_limit > 0:
                delivery_metrics["offline_queue_size"] = ctx.backend_client.offline_queue_size()
                if not ctx.offline_flush_in_progress:
                    ctx.offline_flush_in_progress = True

                    def _offline_flush_worker() -> None:
                        try:
                            ctx.backend_client.flush_offline_queue(limit=flush_limit)
                        except Exception:
                            logger.exception("offline flush worker failed")
                        finally:
                            ctx.offline_flush_in_progress = False

                    ctx.offline_flush_thread = threading.Thread(
                        target=_offline_flush_worker,
                        name=f"offline-flush-{ctx.stream.camera_id}",
                        daemon=True,
                    )
                    ctx.offline_flush_thread.start()
            else:
                # Explicitly disabled: report current queue size.
                delivery_metrics["offline_queue_size"] = ctx.backend_client.offline_queue_size()
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
            inference_ms=round(det_latency + prox_latency + ppe_latency + pose_latency, 2),
            n_detections=len(detections),
            n_tracked=n_tracked,
            dropped_frames=ctx.stream.dropped_count,
            vram_mb=ctx.engine.vram_used_mb(),
            n_hazard_events=len(emitted_events),
            hazard_types=hazard_types if hazard_types else [],
            forklift_dets=forklift_dets,
            raw_forklift_dets=raw_forklift_dets,
            pose_ms=round(pose_latency, 1),
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
            n_fcm_delivered_failed=delivery_metrics.get(
                "n_fcm_delivered_failed", 0
            ),
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
                event.event_type.startswith("forklift_proximity_")
                and len(ctx.sample_hazard_lines) < 8
            ):
                ctx.sample_hazard_lines.append(
                    (
                        f"frame={bundle.frame_number} event={event.event_type} "
                        f"severity={event.severity.name} track={event.track_id}"
                    )
                )

        # Publish annotated frame to Redis for dashboard streaming
        if ctx.frame_publisher is not None:
            ctx.frame_publisher.publish(annotated)

        return FrameResult(annotated=annotated)

    def _refresh_safety_zones(self, camera_id: str, timestamp: float) -> None:
        last = self._last_safety_zone_refresh.get(camera_id, 0.0)
        if timestamp - last < SAFETY_ZONES_REFRESH_INTERVAL_SEC:
            return
        self._last_safety_zone_refresh[camera_id] = timestamp
        payload = self._ctx.backend_client.fetch_safety_zones(camera_id)
        zones = payload.get("zones") if isinstance(payload, dict) else []
        self._safety_zone_engine.set_camera_zones(camera_id, zones or [])


def _safety_overlay_events(emitted_events: list[Any], raw_events: list[Any]) -> list[Any]:
    """Merge emitted alerts with live forklift-only overlay telemetry.

    The delivery path must remain governed by EventAggregator, but the video UI
    needs per-frame forklift distance and speed telemetry.  Limit raw overlay
    passthrough to forklift proximity/overspeed so PPE/fall hazards still obey
    persistence before appearing as alerts.
    """
    merged = list(emitted_events)
    existing = {_overlay_key(event) for event in merged}
    for event in raw_events:
        if not _is_live_forklift_overlay_event(event):
            continue
        key = _overlay_key(event)
        if key in existing:
            continue
        merged.append(event)
        existing.add(key)
    return merged


def _is_live_forklift_overlay_event(event: Any) -> bool:
    event_type = str(getattr(event, "event_type", "")).lower()
    return event_type in {
        "forklift_proximity",
        "forklift_overspeed",
        "forklift_telemetry",
        "forklift_distance_telemetry",
    }


def _overlay_key(event: Any) -> tuple:
    metadata = getattr(event, "metadata", None) or {}
    event_type = str(getattr(event, "event_type", "")).lower()
    if event_type == "forklift_overspeed":
        return (
            getattr(event, "camera_id", None),
            event_type,
            metadata.get("forklift_track_id", getattr(event, "track_id", None)),
        )
    if event_type == "forklift_telemetry":
        return (
            getattr(event, "camera_id", None),
            event_type,
            metadata.get("forklift_track_id", getattr(event, "track_id", None)),
        )
    if event_type == "forklift_distance_telemetry":
        return (
            getattr(event, "camera_id", None),
            event_type,
            metadata.get("forklift_track_id"),
            metadata.get("worker_track_id", getattr(event, "track_id", None)),
        )
    if event_type == "forklift_proximity":
        return (
            getattr(event, "camera_id", None),
            event_type,
            metadata.get("forklift_track_id"),
            metadata.get("worker_track_id", getattr(event, "track_id", None)),
        )
    return (
        getattr(event, "camera_id", None),
        event_type,
        getattr(event, "track_id", None),
    )
