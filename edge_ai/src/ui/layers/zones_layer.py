"""
VisionSafe360 — Zones Layer.

Renders static safety zones — restricted areas, walkways loaded from
per-camera config as polygon dicts.

Zone types → colours:
    restricted   → red
    walkway      → green
    (default)    → teal-cyan
"""
from __future__ import annotations

from typing import List

import cv2
import numpy as np

from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings


class ZonesLayer:
    """Renders static polygon zones."""

    def __init__(
        self,
        theme: IndustrialTheme = DARK,
        cfg: UISettings | None = None,
    ) -> None:
        self.theme = theme
        self.cfg = cfg or UISettings()
        self._buf: np.ndarray | None = None

    def _overlay_buf(self, frame: np.ndarray) -> np.ndarray:
        if self._buf is None or self._buf.shape != frame.shape:
            self._buf = np.empty_like(frame)
        np.copyto(self._buf, frame)
        return self._buf

    def draw(
        self,
        frame: np.ndarray,
        zones: List[dict],
        **kwargs,
    ) -> None:
        """Draw zones onto *frame* in-place."""
        t = self.theme

        # ── Static zone fills (batch into one addWeighted) ───────────
        overlay = self._overlay_buf(frame)
        for zone in zones:
            pts_raw = zone.get("points", [])
            if len(pts_raw) < 3:
                continue
            pts = np.array(pts_raw, dtype=np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(overlay, [pts], t.bg_panel)

        cv2.addWeighted(overlay, t.alpha_zone_fill, frame, 1.0 - t.alpha_zone_fill, 0, frame)

        # ── Zone borders and labels (drawn over the blended fill) ────
        for zone in zones:
            pts_raw = zone.get("points", [])
            if len(pts_raw) < 3:
                continue
            pts = np.array(pts_raw, dtype=np.int32).reshape(-1, 1, 2)
            zone_type = zone.get("type", "default")
            cv2.polylines(
                frame, [pts], isClosed=True,
                color=t.fg_secondary, thickness=t.thick_std, lineType=cv2.LINE_AA,
            )
            name = zone.get("name", zone_type.replace("_", " ").title())
            cx = int(np.mean([p[0] for p in pts_raw]))
            cy = int(np.mean([p[1] for p in pts_raw]))
            cv2.putText(
                frame, name,
                (max(0, cx - 30), max(14, cy)),
                t.font, t.font_sm * self.cfg.overlay_scale,
                t.fg_secondary, t.thick_thin, cv2.LINE_AA,
            )


