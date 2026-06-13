"""
VisionSafe360 — Hazards Layer.

Consumes already-aggregated HazardEvents (post-EventAggregator) and
renders severity-coded overlays on top of each affected detection bbox.

Does NOT recompute any hazard logic — pure read-only UI consumer.

Rendering per severity:
    CRITICAL → thick red border + semi-transparent red fill
    HIGH     → thick orange border + optional fill
    MEDIUM   → yellow border  (fill off by default; toggle in UISettings)
    LOW      → teal label only (no box overlay)

Hazard label format (below bbox):
    "[!] FALL CONFIRMED"
    "[!] POSTURE HIGH  6"
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ...models.hazard_event import HazardEvent
from ...models.severity import Severity
from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings


# Draw order: highest severity last so it renders on top
_SEVERITY_DRAW_ORDER: Dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def _sev_colour(sev: Severity, t: IndustrialTheme) -> Tuple[int, int, int]:
    return {
        Severity.CRITICAL: t.critical,
        Severity.HIGH:     t.high,
        Severity.MEDIUM:   t.warning,
        Severity.LOW:      t.low_info,
    }.get(sev, t.fg_secondary)


def build_hazard_label(event: HazardEvent, calibrated: bool) -> str:
    """Return a human-readable ASCII hazard label string."""
    et  = event.event_type
    sev = event.severity.name
    meta = event.metadata or {}

    if "fall" in et:
        return "[!] FALL CONFIRMED"

    if "posture" in et or "ergo" in et:
        score = meta.get("ergo_score")
        if score is not None:
            return f"[!] POSTURE {sev}  {score:.0f}"
        return f"[!] POSTURE {sev}"

    if et == "forklift_proximity" or et.startswith("forklift_proximity_"):
        stage = str(meta.get("proximity_alert_stage") or et.rsplit("_", 1)[-1]).replace("_", " ").upper()
        risk_score = meta.get("risk_score")
        dist_m = meta.get("distance_m")
        if risk_score is not None and dist_m is not None:
            return f"[!] FORKLIFT {stage}  {risk_score:.0f}  {dist_m:.1f}m"
        if dist_m is not None:
            return f"[!] FORKLIFT {stage}  {dist_m:.1f}m"
        dist_px = meta.get("distance_px")
        if dist_px is not None:
            return f"[!] FORKLIFT {stage}  {dist_px:.0f}px"
        return f"[!] FORKLIFT {stage}"

    if et == "forklift_overspeed":
        speed = meta.get("forklift_speed_mps") or meta.get("speed_mps")
        limit = meta.get("limit_mps")
        if speed is not None and limit is not None:
            return f"[!] OVERSPEED {sev}  {float(speed):.1f}>{float(limit):.1f}m/s"
        if speed is not None:
            return f"[!] OVERSPEED {sev}  {float(speed):.1f}m/s"
        return f"[!] OVERSPEED {sev}"

    # Generic fallback — truncate to keep label width manageable
    short = et.replace("_", " ").upper()[:20]
    return f"[!] {short}"


class HazardsLayer:
    """Severity-coded overlay for aggregated HazardEvents."""

    def __init__(
        self,
        theme: IndustrialTheme = DARK,
        cfg: UISettings | None = None,
    ) -> None:
        self.theme = theme
        self.cfg = cfg or UISettings()
        self._buf: np.ndarray | None = None

    def _overlay_buf(self, frame: np.ndarray) -> np.ndarray:
        """Return a pre-allocated buffer matching *frame* (avoids per-frame alloc)."""
        if self._buf is None or self._buf.shape != frame.shape:
            self._buf = np.empty_like(frame)
        np.copyto(self._buf, frame)
        return self._buf

    def draw(
        self,
        frame: np.ndarray,
        events: List[HazardEvent],
        calibrated: bool = False,
        display_id_map: Optional[Dict[int, int]] = None,
    ) -> None:
        """Render severity overlays and labels onto *frame* in-place."""
        if not events:
            return

        t = self.theme
        cfg = self.cfg
        fh, fw = frame.shape[:2]

        # Sort so higher severities are drawn last (on top)
        sorted_ev = sorted(events, key=lambda e: _SEVERITY_DRAW_ORDER.get(e.severity, 0))

        # ── fill pass (all fills → one addWeighted) ──────────────────
        overlay = self._overlay_buf(frame)
        has_fill = False

        for ev in sorted_ev:
            if _is_render_only_telemetry(ev):
                continue
            if not ev.bbox:
                continue
            x1, y1, x2, y2 = ev.bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(fw - 1, x2), min(fh - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            if (
                (ev.severity == Severity.CRITICAL and cfg.hazard_fill_critical)
                or (ev.severity == Severity.HIGH and cfg.hazard_fill_high)
                or (ev.severity == Severity.MEDIUM and cfg.hazard_fill_medium)
            ):
                c = _sev_colour(ev.severity, t)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), c, -1)
                has_fill = True

        if has_fill:
            cv2.addWeighted(overlay, t.alpha_hazard_fill, frame, 1.0 - t.alpha_hazard_fill, 0, frame)

        self._draw_proximity_distance_lines(frame, sorted_ev)

        # ── border + label pass ──────────────────────────────────────
        label_scale = t.font_md * cfg.overlay_scale

        # Group labels by track_id so multiple events on the same worker stack
        # neatly below their bbox.
        from collections import defaultdict
        track_labels: dict[Optional[int], list[tuple]] = defaultdict(list)

        for ev in sorted_ev:
            if _is_render_only_telemetry(ev):
                continue
            if not ev.bbox:
                continue
            x1, y1, x2, y2 = ev.bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(fw - 1, x2), min(fh - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            c = _sev_colour(ev.severity, t)
            thick = t.thick_bold if ev.severity == Severity.CRITICAL else t.thick_std
            cv2.rectangle(frame, (x1, y1), (x2, y2), c, thick)

            track_labels[ev.track_id].append((x1, y1, x2, y2, c, ev))

        # ── draw stacked labels per track ────────────────────────────
        for track_id, ev_list in track_labels.items():
            # Use the bbox of the most severe event for label anchor
            ev_list_sorted = sorted(ev_list, key=lambda t: _SEVERITY_DRAW_ORDER.get(t[5].severity, 0), reverse=True)
            x1, y1, x2, y2, _, _ = ev_list_sorted[0]

            (_, th), baseline = cv2.getTextSize("A", t.font, label_scale, t.thick_thin)
            row_h = th + baseline + 6
            # First label position: just below the bbox
            ly = y2 + row_h
            if ly + row_h > fh:
                # Fallback: above bbox
                ly = max(row_h, y1 - row_h * len(ev_list_sorted))

            for _, _, _, _, c, ev in ev_list_sorted[:3]:   # max 3 labels per worker
                label = build_hazard_label(ev, calibrated)
                (tw, th2), bl = cv2.getTextSize(label, t.font, label_scale, t.thick_thin)
                lx = max(0, x1)
                lx2 = min(fw - 1, lx + tw + 8)
                ly_top = max(0, ly - th2 - bl - 2)
                cv2.rectangle(frame, (lx, ly_top), (lx2, ly + 2), t.bg_panel, -1)
                cv2.putText(
                    frame, label, (lx + 4, ly - bl),
                    t.font, label_scale, c, t.thick_thin, cv2.LINE_AA,
                )
                ly += row_h + 2

    def _draw_proximity_distance_lines(
        self,
        frame: np.ndarray,
        events: List[HazardEvent],
    ) -> None:
        t = self.theme
        fh, fw = frame.shape[:2]
        for ev in events:
            meta = ev.metadata or {}
            if (
                ev.event_type not in {"forklift_proximity", "forklift_distance_telemetry"}
                and meta.get("case_type") not in {"forklift_proximity", "forklift_distance_telemetry"}
            ):
                continue
            worker_pt = _point_from_meta(meta.get("worker_bottom_center"))
            forklift_pt = _point_from_meta(meta.get("forklift_bottom_center"))
            distance_m = meta.get("distance_m")
            if worker_pt is None or forklift_pt is None or distance_m is None:
                continue

            wx, wy = _clamp_point(worker_pt, fw, fh)
            fx, fy = _clamp_point(forklift_pt, fw, fh)
            colour = _sev_colour(ev.severity, t)
            cv2.line(frame, (wx, wy), (fx, fy), colour, 2, cv2.LINE_AA)
            cv2.circle(frame, (wx, wy), 4, colour, -1, cv2.LINE_AA)
            cv2.circle(frame, (fx, fy), 4, colour, -1, cv2.LINE_AA)

            label = f"{float(distance_m):.1f}m"
            mx, my = (wx + fx) // 2, (wy + fy) // 2
            (tw, th), bl = cv2.getTextSize(label, t.font, t.font_md, t.thick_thin)
            pad = 4
            x1 = max(0, min(fw - tw - 2 * pad - 1, mx - tw // 2 - pad))
            y1 = max(th + bl + pad, my - 8)
            cv2.rectangle(
                frame,
                (x1, y1 - th - bl - pad),
                (x1 + tw + 2 * pad, y1 + pad),
                t.bg_panel,
                -1,
            )
            cv2.putText(
                frame,
                label,
                (x1 + pad, y1 - bl),
                t.font,
                t.font_md,
                colour,
                t.thick_thin,
                cv2.LINE_AA,
            )


def _point_from_meta(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _is_render_only_telemetry(event: HazardEvent) -> bool:
    if not (event.metadata or {}).get("render_only"):
        return False
    return event.event_type in {"forklift_telemetry", "forklift_distance_telemetry"}


def _clamp_point(point: tuple[float, float], fw: int, fh: int) -> tuple[int, int]:
    return (
        max(0, min(fw - 1, int(round(point[0])))),
        max(0, min(fh - 1, int(round(point[1])))),
    )
