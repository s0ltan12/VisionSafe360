"""
VisionSafe360 — Banner Layer.

Renders full-width alert banners at the top of the frame when HIGH or
CRITICAL hazard events occur.  Banners persist for ``banner_critical_sec``
seconds and undergo a smooth alpha fade during the final ``banner_fade_sec``
seconds of their lifetime.

Banner format:
    "CRITICAL: [!] FALL CONFIRMED — Worker D7"
    "HIGH: [!] PROXIMITY HIGH  2.1m — Worker D3"

Up to ``banner_max`` banners are shown simultaneously (most-recent first).
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ...models.hazard_event import HazardEvent
from ...models.severity import Severity
from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings
from .hazards_layer import build_hazard_label


def _banner_alpha(age: float, total_sec: float, fade_sec: float) -> float:
    """Return alpha in [0, 1] for a banner that is *age* seconds old."""
    if age >= total_sec:
        return 0.0
    if age < total_sec - fade_sec:
        return 1.0
    # Linear fade in the final fade_sec window
    return (total_sec - age) / fade_sec


class BannersLayer:
    """Full-width critical/high-severity alert banners."""

    def __init__(
        self,
        theme: IndustrialTheme = DARK,
        cfg: UISettings | None = None,
    ) -> None:
        self.theme = theme
        self.cfg = cfg or UISettings()
        # (timestamp_emitted, HazardEvent)
        self._recent: Deque[Tuple[float, HazardEvent]] = deque(maxlen=30)

    def update(
        self,
        events: List[HazardEvent],
        now: Optional[float] = None,
    ) -> None:
        """Record new HIGH/CRITICAL events.  Call once per frame before draw()."""
        if now is None:
            now = time.time()
        for ev in events:
            if ev.severity >= Severity.HIGH:
                self._recent.append((now, ev))

    def draw(
        self,
        frame: np.ndarray,
        display_id_map: Optional[Dict[int, int]] = None,
    ) -> None:
        """Render active banners onto *frame* in-place."""
        if not self._recent:
            return

        t = self.theme
        cfg = self.cfg
        now = time.time()
        fh, fw = frame.shape[:2]

        # Collect still-visible banners
        active: List[Tuple[float, HazardEvent, float]] = []
        for ts, ev in self._recent:
            age = now - ts
            alpha = _banner_alpha(age, cfg.banner_critical_sec, cfg.banner_fade_sec)
            if alpha > 0.0:
                active.append((ts, ev, alpha))

        if not active:
            return

        # Most-recent first, capped at banner_max
        active.sort(key=lambda x: x[0], reverse=True)
        active = active[:cfg.banner_max]

        banner_h = 40
        scale = t.font_lg * cfg.overlay_scale
        y_offset = 0

        # ── Single blend for all banner backgrounds ───────────────────────
        for ts, ev, alpha in active:
            bar_c = t.critical if ev.severity == Severity.CRITICAL else t.high
            eff_alpha = t.alpha_banner * alpha
            row_ov = frame.copy()
            cv2.rectangle(row_ov, (0, y_offset), (fw, y_offset + banner_h), bar_c, -1)
            cv2.addWeighted(row_ov, eff_alpha, frame, 1.0 - eff_alpha, 0, frame)
            y_offset += banner_h + 2

        # ── Draw banner text on top ────────────────────────────────────────
        y_offset = 0
        for ts, ev, alpha in active:
            worker_suffix = ""
            if ev.track_id is not None:
                disp_id = (display_id_map or {}).get(ev.track_id, ev.track_id)
                worker_suffix = f" — Worker D{disp_id}"

            hazard_str = build_hazard_label(ev, calibrated=True)
            if hazard_str.startswith("[!] "):
                hazard_str = hazard_str[4:]
            banner_text = f"{ev.severity.name}: {hazard_str}{worker_suffix}"

            (tw, th), _ = cv2.getTextSize(banner_text, t.font, scale, t.thick_std)
            tx = max(8, (fw - tw) // 2)
            ty = y_offset + (banner_h + th) // 2

            # Outline for legibility on any background colour
            cv2.putText(
                frame, banner_text, (tx, ty),
                t.font, scale, (0, 0, 0), t.thick_bold, cv2.LINE_AA,
            )
            cv2.putText(
                frame, banner_text, (tx, ty),
                t.font, scale, t.fg_primary, t.thick_std, cv2.LINE_AA,
            )

            y_offset += banner_h + 2
