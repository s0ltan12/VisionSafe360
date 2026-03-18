"""
VisionSafe360 — HUD Layer (top-left telemetry overlay).

Displays a small semi-transparent panel containing inference KPIs:

    FPS:  14.8
    Latency:  21.3 ms
    Det: 4   Tracked: 3
    VRAM: 812 MB
    Hazards: 2             ← coloured orange/red when elevated
    Pose: 6.2 ms
    Track cov: 94%
    CALIBRATED: METERS MODE   ← green (small)
    -- or --
    UNCALIBRATED: PX MODE     ← red (large, bold)
"""
from __future__ import annotations

import cv2
import numpy as np

from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings


class HUDLayer:
    """Renders the top-left heads-up display."""

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
        *,
        fps: float = 0.0,
        latency_ms: float = 0.0,
        n_det: int = 0,
        n_tracked: int = 0,
        vram_mb: int = 0,
        n_hazards: int = 0,
        pose_ms: float = 0.0,
        track_coverage: float = 0.0,
        calibrated: bool = True,
    ) -> None:
        """Draw the HUD onto *frame* in-place."""
        t = self.theme
        cfg = self.cfg
        sm = t.font_sm * cfg.overlay_scale
        md = t.font_md * cfg.overlay_scale

        # Build ordered list of (text, colour) lines
        lines = [
            (f"FPS:  {fps:.1f}", t.safe if fps >= 12.0 else t.warning),
            (f"Latency:  {latency_ms:.1f} ms", t.fg_primary),
            (f"Det: {n_det}   Tracked: {n_tracked}", t.fg_primary),
        ]
        if vram_mb > 0:
            lines.append((f"VRAM: {vram_mb} MB", t.fg_primary))
        if n_hazards > 0:
            lines.append((
                f"Hazards: {n_hazards}",
                t.critical if n_hazards >= 3 else t.high,
            ))
        if pose_ms > 0.0:
            lines.append((f"Pose: {pose_ms:.1f} ms", t.fg_secondary))
        if track_coverage > 0.0:
            pct = round(track_coverage)
            lines.append((
                f"Track cov: {pct}%",
                t.safe if pct >= 80 else t.warning,
            ))

        # Calibration line (may need larger scale)
        if calibrated:
            calib_text = "CALIBRATED: METERS MODE"
            calib_c = t.safe
            calib_scale = sm * 0.85
            calib_thick = t.thick_thin
        else:
            calib_text = "UNCALIBRATED: PX MODE"
            calib_c = t.critical
            calib_scale = md * 1.05
            calib_thick = t.thick_std

        # ── Measure background rect ───────────────────────────────────
        (_, char_h), _ = cv2.getTextSize("A", t.font, sm, 1)
        row_h = char_h + 8
        all_texts = [txt for txt, _ in lines] + [calib_text]
        max_tw = max(
            cv2.getTextSize(txt, t.font, sm, 1)[0][0]
            for txt in all_texts
        )
        bg_w = max_tw + 16
        bg_h = len(lines) * row_h + row_h + 8   # extra row for calibration

        # ── Draw background ───────────────────────────────────────────
        overlay = self._overlay_buf(frame)
        cv2.rectangle(overlay, (0, 0), (bg_w, bg_h), t.bg_hud, -1)
        cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)

        # ── Draw telemetry lines ──────────────────────────────────────
        y = row_h - 4
        for text, colour in lines:
            cv2.putText(
                frame, text, (8, y),
                t.font, sm, colour, t.thick_thin, cv2.LINE_AA,
            )
            y += row_h

        # ── Calibration status ────────────────────────────────────────
        cv2.putText(
            frame, calib_text, (8, y + 2),
            t.font, calib_scale, calib_c, calib_thick, cv2.LINE_AA,
        )
