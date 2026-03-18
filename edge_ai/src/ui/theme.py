"""
VisionSafe360 — Industrial Dark UI Theme.

All colours are BGR tuples (OpenCV convention — Blue, Green, Red).
Import ``DARK`` for the default singleton instance.

Mutate by creating a new IndustrialTheme with overridden fields:
    my_theme = IndustrialTheme(safe=(0, 255, 128))
"""
from __future__ import annotations

from dataclasses import dataclass

# BGR colour type alias  (B, G, R)
BGRColour = tuple[int, int, int]


@dataclass(frozen=True)
class IndustrialTheme:
    """
    Immutable theme specification for the industrial safety overlay.

    BGR colour convention (OpenCV):
      red    = (0,   0, 255)
      green  = (0, 255,   0)
      yellow = (0, 255, 255)   ← G+R channels
      orange = (0, 165, 255)
      cyan   = (255, 255, 0)   ← B+G channels
    """

    # ── Panel chrome ────────────────────────────────────────────────
    bg_panel:          BGRColour = (20,  20,  20)    # vs-darkCard   #141414
    bg_hud:            BGRColour = (10,  10,  10)    # vs-darkBg     #0A0A0A
    fg_primary:        BGRColour = (229, 229, 229)   # vs-text       #E5E5E5
    fg_secondary:      BGRColour = (175, 163, 156)   # vs-muted      #9CA3AF
    border:            BGRColour = (38,  38,  38)    # vs-darkBorder #262626
    accent:            BGRColour = (0,   106, 255)   # vs-orange     #FF6A00

    # ── Severity colours (ISO 12100-inspired) ────────────────────────
    # SAFE=green  WARNING=yellow  HIGH=orange  CRITICAL=red
    safe:              BGRColour = (129, 185,  16)   # vs-safe       #10B981
    warning:           BGRColour = (58,  138, 255)   # vs-lightOrange #FF8A3A
    high:              BGRColour = (0,   106, 255)   # vs-orange     #FF6A00
    critical:          BGRColour = (68,   68, 239)   # vs-critical   #EF4444
    low_info:          BGRColour = (175, 163, 156)   # vs-muted      #9CA3AF

    # ── Detection bbox colours ────────────────────────────────────────
    person_bbox:       BGRColour = (129, 185,  16)   # vs-safe       #10B981
    vehicle_bbox:      BGRColour = (0,   106, 255)   # vs-orange     #FF6A00
    generic_bbox:      BGRColour = (175, 163, 156)   # vs-muted      #9CA3AF

    # ── Pose skeleton ────────────────────────────────────────────────
    skeleton_joint:    BGRColour = (58,  138, 255)   # vs-lightOrange #FF8A3A
    skeleton_limb:     BGRColour = (0,   106, 255)   # vs-orange     #FF6A00

    # ── Overlay alphas (0.0 – 1.0) ───────────────────────────────────
    alpha_bbox:          float = 0.10   # semi-transparent tint under bbox
    alpha_panel:         float = 0.60   # worker card background (~0.60 per spec)
    alpha_hazard_fill:   float = 0.26   # severity-coded fill on hazard bbox
    alpha_zone_fill:     float = 0.10   # restricted-zone polygon fill
    alpha_banner:        float = 0.84   # banner strip background

    # ── Typography ───────────────────────────────────────────────────
    font:     int   = 0     # cv2.FONT_HERSHEY_SIMPLEX
    font_sm:  float = 0.40
    font_md:  float = 0.50
    font_lg:  float = 0.65
    font_xl:  float = 0.85

    # ── Thickness presets ────────────────────────────────────────────
    thick_thin: int = 1
    thick_std:  int = 2
    thick_bold: int = 3

    # ── Dashed-box pattern ───────────────────────────────────────────
    dash_on:  int = 10   # pixels drawn per dash segment
    dash_off: int = 6    # pixels gap between segments

    # ── Skeleton geometry ────────────────────────────────────────────
    kp_radius:    int = 3   # keypoint circle radius (px)
    limb_thickness: int = 2  # skeleton limb line thickness

    # ── Worker panel geometry ────────────────────────────────────────
    panel_padding: int = 6    # inner padding (px)
    panel_row_h:   int = 20   # height of each info row (px)


# Default singleton — every module should ``from .theme import DARK``
DARK: IndustrialTheme = IndustrialTheme()
