"""
VisionSafe360 — Worker Panel Layer  (Intenseye-style info cards).

Renders a floating orange-bordered card per tracked worker showing:

    Worker ID: {display_id}
    Confidence: 87%
    ─────────────────
    Equipped PPEs:
    X Hard Hat
    X Gloves
    v Reflective Vest
    ─────────────────
    [!] FALL CONFIRMED

Position smoother (EMA) prevents frame-to-frame wobble.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ...models.detection import Detection
from ...models.hazard_event import HazardEvent
from ...models.severity import Severity
from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings

_PERSON_CLASS = "person"

# PPE items: (display_name, positive_class, negative_class)
_PPE_ITEMS = [
    ("Hard Hat",        "helmet_on",  "helmet_off"),
    ("Gloves",          None,         None),
    ("Glasses",         None,         None),
    ("Reflective Vest", "vest_on",    "vest_off"),
    ("Mask",            None,         None),
]

# BGR colours
_ORANGE    = (0, 165, 255)
_LIGHT_BG  = (245, 245, 245)
_DARK_TEXT  = (40,  40,  40)
_GREEN_MK  = (0, 180, 0)
_RED_MK    = (0, 0, 200)
_GRAY_MK   = (160, 160, 160)


# ── Position smoother ───────────────────────────────────────────────

class _PositionSmoother:
    """EMA-based panel position smoother keyed by track_id.

    Uses a low alpha for very smooth motion and locks the
    panel side (left/right of person) to prevent flip-flop.
    """

    def __init__(self, alpha: float = 0.10):
        self._a = alpha
        self._pos: Dict[int, Tuple[float, float]] = {}
        self._side: Dict[int, str] = {}          # 'L' or 'R' lock
        self._tick_no = 0
        self._seen: Dict[int, int] = {}

    # side locking ─────────────────────────────────────────────
    def get_side(self, tid: int) -> Optional[str]:
        return self._side.get(tid)

    def set_side(self, tid: int, side: str) -> None:
        if tid not in self._side:
            self._side[tid] = side

    def smooth(self, tid: int, px: int, py: int) -> Tuple[int, int]:
        self._tick_no += 1
        self._seen[tid] = self._tick_no
        if tid in self._pos:
            ox, oy = self._pos[tid]
            nx = self._a * px + (1 - self._a) * ox
            ny = self._a * py + (1 - self._a) * oy
            self._pos[tid] = (nx, ny)
            return int(round(nx)), int(round(ny))
        self._pos[tid] = (float(px), float(py))
        return px, py

    def cleanup(self, max_stale: int = 90):
        stale = [k for k, v in self._seen.items()
                 if self._tick_no - v > max_stale]
        for k in stale:
            self._pos.pop(k, None)
            self._seen.pop(k, None)
            self._side.pop(k, None)


# ── Layout helpers ───────────────────────────────────────────────────

def _rects_overlap(r1: Tuple, r2: Tuple) -> bool:
    return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])


def _place_panel(
    det: Detection, pw: int, ph: int,
    fw: int, fh: int,
    occupied: List[Tuple[int, int, int, int]],
    mode: str,
    locked_side: Optional[str] = None,
) -> Tuple[int, int, str]:
    x1, y1, x2, y2 = det.bbox
    chosen_side = locked_side or "L"

    def _clamp(px: int, py: int) -> Tuple[int, int]:
        return max(0, min(px, fw - pw)), max(0, min(py, fh - ph))

    if mode == "top_left":
        px, py = _clamp(8, 8)
    else:
        # Decide side (left vs right of bbox)
        if locked_side == "L":
            px, py = _clamp(x1 - pw - 8, y1)
        elif locked_side == "R":
            px, py = _clamp(x2 + 8, y1)
        else:
            # First time: prefer left, fallback right
            if x1 - pw - 8 >= 0:
                px, py = _clamp(x1 - pw - 8, y1)
                chosen_side = "L"
            else:
                px, py = _clamp(x2 + 8, y1)
                chosen_side = "R"

    if mode == "auto_avoid_overlap":
        for _ in range(15):
            r = (px, py, px + pw, py + ph)
            if not any(_rects_overlap(r, o) for o in occupied):
                break
            py += ph + 6
            if py + ph > fh:
                py = 0
                px = max(0, min(px + pw + 4, fw - pw))
        px, py = _clamp(px, py)

    return px, py, chosen_side


def _overlap_ratio(a_bbox, b_bbox) -> float:
    """Fraction of *a_bbox* area that overlaps *b_bbox*."""
    ix1 = max(a_bbox[0], b_bbox[0])
    iy1 = max(a_bbox[1], b_bbox[1])
    ix2 = min(a_bbox[2], b_bbox[2])
    iy2 = min(a_bbox[3], b_bbox[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area = max(1, (a_bbox[2] - a_bbox[0]) * (a_bbox[3] - a_bbox[1]))
    return inter / area


# ── Layer class ──────────────────────────────────────────────────────

class WorkerPanelLayer:
    """Renders per-worker Intenseye-style floating info cards."""

    def __init__(
        self,
        theme: IndustrialTheme = DARK,
        cfg: UISettings | None = None,
    ) -> None:
        self.theme = theme
        self.cfg = cfg or UISettings()
        self._smoother = _PositionSmoother(alpha=0.10)
        self._buf: np.ndarray | None = None

    def _blend_buf(self, frame: np.ndarray) -> np.ndarray:
        if self._buf is None or self._buf.shape != frame.shape:
            self._buf = np.empty_like(frame)
        np.copyto(self._buf, frame)
        return self._buf

    # ── PPE association ──────────────────────────────────────────────

    @staticmethod
    def _ppe_status(
        person: Detection, all_dets: List[Detection],
    ) -> Dict[str, Optional[bool]]:
        """True = equipped, False = missing, None = unknown."""
        nearby: Dict[str, float] = {}
        for d in all_dets:
            if d.class_name == _PERSON_CLASS:
                continue
            if _overlap_ratio(d.bbox, person.bbox) > 0.3:
                prev = nearby.get(d.class_name, 0.0)
                if d.confidence > prev:
                    nearby[d.class_name] = d.confidence

        out: Dict[str, Optional[bool]] = {}
        for name, pos_cls, neg_cls in _PPE_ITEMS:
            if pos_cls and pos_cls in nearby:
                out[name] = True
            elif neg_cls and neg_cls in nearby:
                out[name] = False
            else:
                out[name] = None
        return out

    # ── Main draw ────────────────────────────────────────────────────

    def draw(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        hazard_events: List[HazardEvent],
        display_id_map: Optional[Dict[int, int]] = None,
        ppe_capable: bool = False,
        degraded: bool = False,
    ) -> None:
        """Draw worker info panels onto *frame* in-place."""
        if degraded:
            return

        cfg = self.cfg
        fh, fw = frame.shape[:2]

        persons = sorted(
            [d for d in detections
             if d.class_name == _PERSON_CLASS and d.track_id is not None],
            key=lambda d: d.track_id,
        )[:cfg.max_worker_panels]

        if not persons:
            self._smoother.cleanup()
            return

        # Hazard events grouped by track
        wk_ev: Dict[int, List[HazardEvent]] = defaultdict(list)
        for ev in hazard_events:
            if ev.track_id is not None:
                wk_ev[ev.track_id].append(ev)

        scale = cfg.overlay_scale
        font = cv2.FONT_HERSHEY_SIMPLEX
        sm = 0.34 * scale
        md = 0.40 * scale
        row_h = 17
        pad = 6
        panel_w = max(cfg.panel_width, 160)

        occupied: List[Tuple[int, int, int, int]] = []
        specs = []

        for person in persons:
            tid = person.track_id
            did = (display_id_map or {}).get(tid, tid)
            conf = int(person.confidence * 100)

            ppe = self._ppe_status(person, detections) if ppe_capable else {
                n: None for n, _, _ in _PPE_ITEMS
            }

            haz = sorted(wk_ev.get(tid, []),
                         key=lambda e: e.severity, reverse=True)[:2]

            # Rows: header + confidence + sep + "Equipped PPEs:" + items
            n_rows = 2 + 1 + len(_PPE_ITEMS)
            if haz:
                n_rows += 1 + len(haz)
            panel_h = n_rows * row_h + pad * 2

            # Raw placement (with side-lock to prevent L/R flip)
            locked = self._smoother.get_side(tid)
            raw_px, raw_py, side = _place_panel(
                person, panel_w, panel_h, fw, fh, occupied,
                cfg.panel_anchor_mode, locked_side=locked,
            )
            self._smoother.set_side(tid, side)
            # Smooth position
            px, py = self._smoother.smooth(tid, raw_px, raw_py)
            px = max(0, min(px, fw - panel_w))
            py = max(0, min(py, fh - panel_h))

            occupied.append((px, py, px + panel_w, py + panel_h))
            specs.append((person, tid, did, conf, ppe, haz,
                          px, py, panel_w, panel_h))

        # ── Semi-transparent light background ──────────────────────────
        bg = self._blend_buf(frame)
        for *_, px, py, pw, ph in specs:
            cv2.rectangle(bg, (px, py), (px + pw, py + ph), _LIGHT_BG, -1)
        cv2.addWeighted(bg, 0.75, frame, 0.25, 0, frame)

        # ── Per-panel rendering ────────────────────────────────────────
        for person, tid, did, conf, ppe, haz, px, py, pw, ph in specs:
            # Orange border
            cv2.rectangle(frame, (px, py), (px + pw, py + ph), _ORANGE, 2)

            # Connector line
            bx1, by1, bx2, by2 = person.bbox
            conn_x = bx1 if (px + pw) < bx1 else bx2
            conn_y = (by1 + by2) // 2
            cv2.line(frame,
                     (px + pw // 2, py + ph // 2),
                     (max(0, min(conn_x, fw - 1)),
                      max(0, min(conn_y, fh - 1))),
                     _ORANGE, 1, cv2.LINE_AA)

            # ── Orange header bar ─────────────────────────────────
            hdr_h = row_h + 6
            cv2.rectangle(frame, (px, py), (px + pw, py + hdr_h),
                          _ORANGE, -1)

            tx = px + pad
            ty = py + hdr_h - 5
            cv2.putText(frame, f"Worker ID : {did}",
                        (tx, ty), font, md, _DARK_TEXT, 1, cv2.LINE_AA)
            ty = py + hdr_h + row_h - 2

            # Confidence
            cv2.putText(frame, f"Confidence: {conf}%",
                        (tx, ty), font, sm, _DARK_TEXT, 1, cv2.LINE_AA)
            ty += row_h

            # Separator
            sep_y = ty - 8
            cv2.line(frame, (px + pad, sep_y), (px + pw - pad, sep_y),
                     _GRAY_MK, 1)

            # PPE header
            cv2.putText(frame, "Equipped PPEs:",
                        (tx, ty), font, sm, _DARK_TEXT, 1, cv2.LINE_AA)
            ty += row_h

            # PPE items
            for name, _, _ in _PPE_ITEMS:
                status = ppe.get(name)
                if status is True:
                    mk, mc = "v", _GREEN_MK
                elif status is False:
                    mk, mc = "X", _RED_MK
                else:
                    mk, mc = "X", _RED_MK      # default: not detected
                cv2.putText(frame, mk,
                            (tx, ty), font, sm, mc, 1, cv2.LINE_AA)
                cv2.putText(frame, name,
                            (tx + 16, ty), font, sm, _DARK_TEXT, 1, cv2.LINE_AA)
                ty += row_h

            # Hazards
            if haz:
                sep_y2 = ty - 8
                cv2.line(frame, (px + pad, sep_y2), (px + pw - pad, sep_y2),
                         _GRAY_MK, 1)
                for ev in haz:
                    hc = {
                        Severity.CRITICAL: (0, 0, 220),
                        Severity.HIGH:     _ORANGE,
                        Severity.MEDIUM:   (0, 200, 200),
                    }.get(ev.severity, _GRAY_MK)
                    short = ev.event_type.replace("_", " ").upper()[:18]
                    cv2.putText(frame, f"[!] {short}",
                                (tx, ty), font, sm * 0.9, hc, 1, cv2.LINE_AA)
                    ty += row_h

        self._smoother.cleanup()
