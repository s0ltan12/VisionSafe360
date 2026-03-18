"""
VisionSafe360 — UI Layer Configuration.

UISettings is a flat dataclass that drives every rendering toggle and
parameter.  It can be populated from the ``ui:`` block in a profile YAML
via ``load_ui_settings_from_profile()``.

All toggles default to sensible production values so that the pipeline
works correctly even when no ``ui:`` section is present in the profile.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UISettings:
    """Per-profile UI rendering configuration."""

    # ── Layer enable toggles ─────────────────────────────────────────
    enable_detections:    bool  = True
    enable_pose:          bool  = True
    enable_zones:         bool  = False   # off unless per-camera polygons provided
    enable_hazards:       bool  = True
    enable_worker_panels: bool  = True
    enable_hud:           bool  = True
    enable_banners:       bool  = True

    # ── Detections layer ─────────────────────────────────────────────
    # show_raw_track_ids=True shows un-remapped ByteTrack IDs in labels
    show_raw_track_ids:  bool  = False
    show_confidence:     bool  = True
    overlay_scale:       float = 1.0     # global font-size multiplier

    # ── Pose layer ────────────────────────────────────────────────────
    pose_kp_conf_thresh: float = 0.45    # min keypoint confidence to draw

    # ── Worker panel layer ────────────────────────────────────────────
    max_worker_panels:    int  = 8        # cap panels shown per frame
    # anchor mode: "left_of_bbox" | "top_left" | "auto_avoid_overlap"
    panel_anchor_mode:   str  = "auto_avoid_overlap"
    panel_width:          int  = 168
    panel_min_height:     int  = 88

    # ── Hazards layer ─────────────────────────────────────────────────
    hazard_fill_critical: bool  = True    # fill with red for CRITICAL severity
    hazard_fill_high:     bool  = True    # fill with orange for HIGH severity
    hazard_fill_medium:   bool  = False   # border-only for MEDIUM (less noisy)

    # ── Banner layer ──────────────────────────────────────────────────
    banner_critical_sec: float = 2.5     # total banner visible duration (s)
    banner_fade_sec:     float = 0.6     # fade-out duration within that window
    banner_max:           int  = 3       # max simultaneous banners

    # ── Adaptive performance degradation ─────────────────────────────
    perf_budget_ms:      float = 12.0    # target maximum UI cost per frame
    auto_degrade:        bool  = True    # reduce quality if over budget


def load_ui_settings_from_profile(raw_ui: dict) -> UISettings:
    """Build a UISettings from a profile's ``ui:`` YAML dict.

    Unknown keys are ignored; missing keys fall back to the dataclass
    defaults so old profiles without a ``ui:`` section continue to work.
    """
    cfg = UISettings()
    if not raw_ui:
        return cfg
    for key, val in raw_ui.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    return cfg
