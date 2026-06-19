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
    # Toast notification card on the video is disabled: the real alert
    # pipeline (backend events, push, siren, dashboard) is unaffected. The
    # on-frame hazard is conveyed by the severity-coloured box around the
    # worker (detections + hazards layers).
    enable_banners:       bool  = False

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
    # Width of the worker panels in pixels (cards close to person, readable).
    panel_width:          int  = 140
    panel_min_height:     int  = 88

    # ── Hazards layer ─────────────────────────────────────────────────
    hazard_fill_critical: bool  = True    # fill with red for CRITICAL severity
    hazard_fill_high:     bool  = True    # fill with orange for HIGH severity
    hazard_fill_medium:   bool  = False   # border-only for MEDIUM (less noisy)
    # Keep the worker hazard box/label visible for this many extra seconds
    # after the hazard last appeared, so a dashboard operator can notice it
    # even if detection briefly flickers. UI-only — does not affect the real
    # alert pipeline (backend events, push, siren).
    hazard_hold_sec:      float = 1.0

    # ── Banner layer ──────────────────────────────────────────────────
    banner_critical_sec: float = 3.0     # total banner visible duration (s)
    banner_fade_sec:     float = 0.6     # fade-out duration within that window
    banner_max:           int  = 1       # max simultaneous banners (less intrusive)
    banner_enter_sec:    float = 0.40    # entrance motion duration (s)
    banner_stack_gap:     int  = 6       # vertical spacing between notification cards
    banner_corner_radius: int  = 16      # rounded card radius
    banner_side_margin:   int  = 16      # left/right outer margin
    banner_top_margin:    int  = 12      # top outer margin
    banner_shadow_px:      int  = 6      # soft shadow offset for depth
    banner_glow_strength: float = 0.08   # subtle severity glow alpha
    banner_repeat_cooldown_sec: float = 4.0  # suppress duplicate notifications
    banner_include_worker_id: bool = True    # include worker ID in notification body

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
