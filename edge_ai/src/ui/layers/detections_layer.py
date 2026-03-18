"""
VisionSafe360 — Detections Layer.

Renders dashed bounding boxes and identification label bars for every
tracked detection.  Uses per-class colours from the active theme.

Label format:  "person  D3  0.87"  (display ID when available)
"""
from __future__ import annotations

from typing import Dict, List, Optional

import cv2
import numpy as np

from ...models.detection import Detection
from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings

# ── Primitive helpers ────────────────────────────────────────────────

def _draw_dashed_line(
    frame: np.ndarray,
    p1: tuple[int, int],
    p2: tuple[int, int],
    colour: tuple[int, int, int],
    thickness: int,
    dash_on: int,
    dash_off: int,
) -> None:
    """Draw a dashed segment from *p1* to *p2* (in-place)."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = int(np.hypot(dx, dy))
    if length == 0:
        return
    step = dash_on + dash_off
    for s in range(0, length, step):
        e = min(s + dash_on, length)
        ax = x1 + dx * s // length
        ay = y1 + dy * s // length
        bx = x1 + dx * e // length
        by = y1 + dy * e // length
        cv2.line(frame, (ax, ay), (bx, by), colour, thickness, cv2.LINE_AA)


def draw_dashed_rect(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    colour: tuple[int, int, int],
    thickness: int = 2,
    dash_on: int = 10,
    dash_off: int = 6,
) -> None:
    """Draw a dashed-border rectangle (in-place, all four sides)."""
    _draw_dashed_line(frame, (x1, y1), (x2, y1), colour, thickness, dash_on, dash_off)
    _draw_dashed_line(frame, (x2, y1), (x2, y2), colour, thickness, dash_on, dash_off)
    _draw_dashed_line(frame, (x2, y2), (x1, y2), colour, thickness, dash_on, dash_off)
    _draw_dashed_line(frame, (x1, y2), (x1, y1), colour, thickness, dash_on, dash_off)


def _put_label_bar(
    frame: np.ndarray,
    x1: int,
    y1: int,
    text: str,
    bg_colour: tuple[int, int, int],
    text_colour: tuple[int, int, int],
    font: int,
    scale: float,
    thickness: int,
) -> None:
    """Draw a label bar above *(x1, y1)* with vs-darkCard bg and vs-text foreground."""
    fh, fw = frame.shape[:2]
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    bar_h = th + baseline + 6
    bx1 = max(0, x1)
    by1 = max(0, y1 - bar_h)
    bx2 = min(fw - 1, x1 + tw + 10)
    by2 = min(fh - 1, y1)
    cv2.rectangle(frame, (bx1, by1), (bx2, by2), bg_colour, -1)
    ty = by1 + th + 2
    cv2.putText(
        frame, text, (bx1 + 4, ty),
        font, scale, text_colour, thickness, cv2.LINE_AA,
    )


# ── Layer class ──────────────────────────────────────────────────────

class DetectionsLayer:
    """Renders tracked detections as dashed bboxes with ID label bars."""

    def __init__(
        self,
        theme: IndustrialTheme = DARK,
        cfg: UISettings | None = None,
    ) -> None:
        self.theme = theme
        self.cfg = cfg or UISettings()

    def draw(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        display_id_map: Optional[Dict[int, int]] = None,
        hazard_events: Optional[list] = None,
    ) -> None:
        """Draw all detections onto *frame* in-place."""
        if not detections:
            return

        t = self.theme
        cfg = self.cfg
        scale = t.font_md * cfg.overlay_scale
        fh, fw = frame.shape[:2]

        # Build lookup: track_id → highest severity for person bbox colouring
        _worker_sev: Dict[int, int] = {}
        if hazard_events:
            for ev in hazard_events:
                tid = getattr(ev, "track_id", None)
                if tid is not None:
                    prev = _worker_sev.get(tid, 0)
                    sev_val = int(getattr(ev, "severity", 0))
                    if sev_val > prev:
                        _worker_sev[tid] = sev_val

        for det in detections:
            x1, y1, x2, y2 = det.bbox
            # Clamp to frame boundaries
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(fw - 1, x2), min(fh - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            # Choose colour by class; persons escalate by hazard severity
            if det.class_name == "person":
                colour = t.person_bbox               # vs-safe default
                sev = _worker_sev.get(det.track_id, 0) if det.track_id is not None else 0
                if sev >= 4:       colour = t.critical
                elif sev >= 3:     colour = t.high
                elif sev >= 2:     colour = t.warning
            else:
                colour = t.generic_bbox

            # Dashed bounding box
            draw_dashed_rect(
                frame, x1, y1, x2, y2,
                colour, t.thick_std, t.dash_on, t.dash_off,
            )

            # Build label: "person  D3  0.87"
            display_id: Optional[int] = None
            if det.track_id is not None:
                if not cfg.show_raw_track_ids and display_id_map:
                    display_id = display_id_map.get(det.track_id)
                else:
                    display_id = det.track_id

            parts = [det.class_name]
            if display_id is not None:
                parts.append(f"D{display_id}")
            if cfg.show_confidence:
                parts.append(f"{det.confidence:.2f}")
            label = "  ".join(parts)

            _put_label_bar(frame, x1, y1, label, t.bg_panel, t.fg_primary,
                           t.font, scale, t.thick_thin)
