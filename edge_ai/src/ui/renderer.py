"""
VisionSafe360 — SafetyOverlayRenderer (Layer Orchestrator).

Drives all rendering layers in the correct drawing order, measures the
total UI cost per frame, and applies adaptive degradation when the budget
is exceeded.

Drawing order (back → front):
    1. Zones            — static/dynamic safety zone polygons
    2. Detections       — dashed bboxes + ID label bars
    3. Pose             — COCO-17 skeleton
    4. Hazards          — severity-coded bbox fills + labels
    5. Worker Panels    — floating Intenseye-style info cards
    6. HUD              — top-left telemetry strip
    7. Banners          — full-width critical alert strip

Usage::

    renderer = SafetyOverlayRenderer(cfg=ui_settings)

    # Inside the inference loop:
    annotated = bundle.frame.copy()
    renderer.render(
        annotated,
        detections=detections,
        pose_results=pose_results,
        hazard_events=emitted_events,
        display_id_map=display_id_map,
        calibrated=is_calibrated,
        fps=inference_fps,
        latency_ms=det_latency,
        n_det=len(detections),
        n_tracked=n_tracked,
        vram_mb=engine.vram_used_mb(),
        n_hazards=len(emitted_events),
        pose_ms=pose_latency,
        track_coverage=track_metrics.get("track_coverage", 0.0),
        ppe_capable=cap_report.ppe_ready,
        now=ts_now,
    )
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np

from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..config.ui_settings import UISettings
from .theme import IndustrialTheme, DARK
from .layers.detections_layer import DetectionsLayer
from .layers.pose_layer import PoseLayer
from .layers.zones_layer import ZonesLayer
from .layers.hazards_layer import HazardsLayer
from .layers.worker_panel_layer import WorkerPanelLayer
from .layers.hud_layer import HUDLayer
from .layers.banners_layer import BannersLayer


class SafetyOverlayRenderer:
    """
    Stateful overlay renderer that orchestrates all UI layers.

    The renderer maintains a ``degraded`` flag.  When the most recent frame's
    render cost exceeded ``cfg.perf_budget_ms``, degraded=True is forwarded
    to the pose and panel layers so they can reduce visual fidelity:

    * Pose layer:   limb thickness drops to 1 px.
    * Panel layer:  skipped entirely.
    """

    def __init__(
        self,
        cfg: UISettings | None = None,
        theme: IndustrialTheme = DARK,
    ) -> None:
        self.cfg = cfg or UISettings()
        self.theme = theme

        # Instantiate layers (share the same cfg & theme reference)
        self._zones     = ZonesLayer(theme, self.cfg)
        self._detect    = DetectionsLayer(theme, self.cfg)
        self._pose      = PoseLayer(theme, self.cfg)
        self._hazards   = HazardsLayer(theme, self.cfg)
        self._panels    = WorkerPanelLayer(theme, self.cfg)
        self._hud       = HUDLayer(theme, self.cfg)
        self._banners   = BannersLayer(theme, self.cfg)

        self._degraded: bool = False
        self.last_render_ms: float = 0.0
        # Hysteresis counters to avoid panel flicker when render cost
        # oscillates around perf_budget_ms.
        self._over_budget_frames: int = 0
        self._under_budget_frames: int = 0

    # ── Public API ───────────────────────────────────────────────────

    def render(
        self,
        frame: np.ndarray,
        *,
        detections: List[Detection],
        pose_results: Any = None,
        hazard_events: List[HazardEvent],
        display_id_map: Dict[int, int],
        calibrated: bool,
        fps: float = 0.0,
        latency_ms: float = 0.0,
        n_det: int = 0,
        n_tracked: int = 0,
        vram_mb: int = 0,
        n_hazards: int = 0,
        pose_ms: float = 0.0,
        track_coverage: float = 0.0,
        zones: Optional[List[dict]] = None,
        ppe_capable: bool = False,
        now: Optional[float] = None,
    ) -> np.ndarray:
        """
        Render all enabled overlay layers onto *frame* in-place.

        *frame* must be a mutable copy of the raw camera frame; the caller
        is responsible for the ``frame.copy()`` before passing it here.
        Returns the same ndarray for convenience (no reallocation).
        """
        t0 = time.perf_counter()
        cfg = self.cfg
        ts = now if now is not None else time.time()

        # 1 ── Zones (background spatial context)
        if cfg.enable_zones and zones:
            self._zones.draw(frame, zones, hazard_events)

        # 2 ── Detections (dashed bboxes + ID labels)
        if cfg.enable_detections:
            self._detect.draw(frame, detections, display_id_map, hazard_events)

        # 3 ── Pose skeleton
        if cfg.enable_pose and pose_results is not None:
            self._pose.draw(frame, pose_results, degraded=self._degraded)

        # 4 ── Hazard severity overlays (draw runs every frame so the box can
        #      linger for hazard_hold_sec after the event clears)
        if cfg.enable_hazards:
            self._hazards.draw(frame, hazard_events or [], calibrated, display_id_map, now=ts)

        # 5 ── Worker info panels
        if cfg.enable_worker_panels:
            self._panels.draw(
                frame, detections, hazard_events,
                display_id_map, ppe_capable, self._degraded,
            )

        # 6 ── HUD
        if cfg.enable_hud:
            self._hud.draw(
                frame,
                fps=fps,
                latency_ms=latency_ms,
                n_det=n_det,
                n_tracked=n_tracked,
                vram_mb=vram_mb,
                n_hazards=n_hazards,
                pose_ms=pose_ms,
                track_coverage=track_coverage,
                calibrated=calibrated,
            )

        # 7 ── Banners (must update before draw each frame)
        if cfg.enable_banners:
            self._banners.update(hazard_events, ts)
            self._banners.draw(frame, display_id_map)

        # ── Performance feedback ─────────────────────────────────────
        self.last_render_ms = (time.perf_counter() - t0) * 1000.0
        if cfg.auto_degrade:
            over = self.last_render_ms > cfg.perf_budget_ms
            # Recovery needs to be meaningfully below the budget to avoid
            # rapid toggling.
            under = self.last_render_ms < (cfg.perf_budget_ms * 0.8)
            if over:
                self._over_budget_frames += 1
                self._under_budget_frames = 0
            elif under:
                self._under_budget_frames += 1
                self._over_budget_frames = 0
            else:
                # In the deadband: don't advance counters.
                pass

            # Tune these two constants for stability rather than aggressiveness.
            degrade_after = 3
            recover_after = 3
            if not self._degraded and self._over_budget_frames >= degrade_after:
                self._degraded = True
                self._under_budget_frames = 0
            elif self._degraded and self._under_budget_frames >= recover_after:
                self._degraded = False
                self._over_budget_frames = 0

        return frame

    @property
    def degraded(self) -> bool:
        """True when the previous frame exceeded the render budget."""
        return self._degraded
