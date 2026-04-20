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
from functools import lru_cache
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - Pillow should be available, but keep fallback safe.
    Image = None
    ImageDraw = None
    ImageFont = None

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


def _ease_out_cubic(x: float) -> float:
    """Smooth and restrained settle used for card entrance."""
    t = max(0.0, min(1.0, x))
    return 1.0 - pow(1.0 - t, 3.0)


def _truncate_text_to_width(
    text: str,
    max_w: int,
    font: int,
    scale: float,
    thickness: int,
) -> str:
    """Trim text to fit width, appending ellipsis when needed."""
    if cv2.getTextSize(text, font, scale, thickness)[0][0] <= max_w:
        return text

    clipped = text
    while clipped and cv2.getTextSize(clipped + "...", font, scale, thickness)[0][0] > max_w:
        clipped = clipped[:-1]
    return (clipped + "...") if clipped else "..."


@lru_cache(maxsize=1)
def _font_paths() -> tuple[str, str]:
    """Return high-quality system font paths with a safe fallback."""
    regular_candidates = (
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    bold_candidates = (
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    )

    def pick(paths: tuple[str, ...]) -> str:
        for path in paths:
            try:
                with open(path, "rb"):
                    return path
            except OSError:
                continue
        return ""

    return pick(regular_candidates), pick(bold_candidates)


@lru_cache(maxsize=16)
def _load_pil_font(path: str, size: int):
    if ImageFont is None or not path:
        return None
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return None


def _pil_text_width(text: str, font: object) -> int:
    if ImageDraw is None or font is None:
        return 0
    dummy = Image.new("RGB", (1, 1), (0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0])


def _truncate_text_to_width_pil(text: str, max_w: int, font: object) -> str:
    if _pil_text_width(text, font) <= max_w:
        return text

    clipped = text
    while clipped and _pil_text_width(clipped + "...", font) > max_w:
        clipped = clipped[:-1]
    return (clipped + "...") if clipped else "..."


def _draw_text_pil(
    overlay_bgr: np.ndarray,
    text: str,
    x: int,
    y: int,
    font: object,
    color_bgr: tuple[int, int, int],
) -> np.ndarray:
    if Image is None or ImageDraw is None or font is None:
        return overlay_bgr

    rgb = cv2.cvtColor(overlay_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil_img)
    draw.text((int(x), int(y)), text, font=font, fill=(int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0])))
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _prettify_event_type(event_type: str) -> str:
    """Convert machine event type into a short user-facing title."""
    mapping = {
        "fall_confirmed": "Fall Confirmed",
        "fall": "Fall Detected",
        "proximity_high": "Unsafe Proximity",
        "proximity": "Unsafe Proximity",
        "no_helmet": "Helmet Missing",
        "no_vest": "Safety Vest Missing",
    }
    key = (event_type or "").strip().lower()
    if key in mapping:
        return mapping[key]
    return (key.replace("_", " ").strip().title() or "Safety Alert")


def _notification_copy(
    ev: HazardEvent,
    include_worker_id: bool,
    display_id_map: Optional[Dict[int, int]],
) -> tuple[str, str]:
    """Build concise title/body copy that follows Apple notification guidance."""
    title = _prettify_event_type(ev.event_type)

    if include_worker_id and ev.track_id is not None:
        disp_id = (display_id_map or {}).get(ev.track_id, ev.track_id)
        subject = f"Worker D{disp_id}"
    else:
        subject = "A worker"

    location = (
        str(ev.metadata.get("location", "")).strip()
        or str(ev.metadata.get("zone_name", "")).strip()
        or f"Camera {ev.camera_id}"
    )
    body = f"{location}"
    if include_worker_id and ev.track_id is not None:
        body = f"{body} - {subject}"
    return title, body


def _hazard_kind(event_type: str) -> str:
    key = (event_type or "").strip().lower()
    if "fall" in key:
        return "fall"
    if "vest" in key:
        return "vest"
    if "helmet" in key:
        return "helmet"
    if "proximity" in key or "forklift" in key:
        return "proximity"
    return "alert"


def _hazard_accent(ev: HazardEvent, t: IndustrialTheme) -> tuple[int, int, int]:
    kind = _hazard_kind(ev.event_type)
    if kind == "fall":
        return t.critical
    if kind in ("vest", "helmet"):
        return t.high
    if kind == "proximity":
        return t.warning
    if ev.severity == Severity.CRITICAL:
        return t.critical
    if ev.severity == Severity.HIGH:
        return t.high
    return t.warning


def _draw_hazard_icon(
    img: np.ndarray,
    center: tuple[int, int],
    r: int,
    accent: tuple[int, int, int],
    kind: str,
) -> None:
    """Draw a compact glyph per hazard type inside an outlined circle."""
    cx, cy = center
    cv2.circle(img, center, r, accent, 2, cv2.LINE_AA)

    if kind == "fall":
        # tilted stick figure (falling worker)
        cv2.circle(img, (cx - r // 6, cy - r // 3), max(1, r // 6), accent, -1, cv2.LINE_AA)
        cv2.line(img, (cx - r // 8, cy - r // 5), (cx + r // 3, cy + r // 6), accent, 2, cv2.LINE_AA)
        cv2.line(img, (cx + r // 10, cy), (cx + r // 2, cy - r // 5), accent, 2, cv2.LINE_AA)
        cv2.line(img, (cx + r // 3, cy + r // 6), (cx + r // 2, cy + r // 2), accent, 2, cv2.LINE_AA)
        cv2.line(img, (cx + r // 6, cy + r // 5), (cx - r // 10, cy + r // 2), accent, 2, cv2.LINE_AA)
        return

    if kind == "vest":
        pts = np.array([
            [cx - r // 2, cy - r // 4],
            [cx - r // 4, cy - r // 2],
            [cx + r // 4, cy - r // 2],
            [cx + r // 2, cy - r // 4],
            [cx + r // 3, cy + r // 2],
            [cx - r // 3, cy + r // 2],
        ], dtype=np.int32)
        cv2.polylines(img, [pts], True, accent, 2, cv2.LINE_AA)
        cv2.line(img, (cx, cy - r // 2), (cx, cy + r // 2), accent, 2, cv2.LINE_AA)
        return

    if kind == "helmet":
        cv2.ellipse(img, (cx, cy), (r // 2, r // 3), 0, 180, 360, accent, 2, cv2.LINE_AA)
        cv2.line(img, (cx - r // 2, cy), (cx + r // 2, cy), accent, 2, cv2.LINE_AA)
        return

    if kind == "proximity":
        cv2.circle(img, (cx - r // 3, cy), max(1, r // 8), accent, -1, cv2.LINE_AA)
        cv2.circle(img, (cx + r // 3, cy), max(1, r // 8), accent, -1, cv2.LINE_AA)
        cv2.line(img, (cx - r // 8, cy), (cx + r // 8, cy), accent, 2, cv2.LINE_AA)
        return

    # default alert glyph
    cv2.line(img, (cx, cy - r // 3), (cx, cy + r // 4), accent, 2, cv2.LINE_AA)
    cv2.circle(img, (cx, cy + r // 2), max(1, r // 10), accent, -1, cv2.LINE_AA)


def _alpha_blit(dst: np.ndarray, src_rgba: np.ndarray, x: int, y: int) -> None:
    """Alpha blend RGBA icon onto BGR destination."""
    h, w = src_rgba.shape[:2]
    if h <= 0 or w <= 0:
        return

    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(dst.shape[1], x + w)
    y1 = min(dst.shape[0], y + h)
    if x0 >= x1 or y0 >= y1:
        return

    sx0 = x0 - x
    sy0 = y0 - y
    sx1 = sx0 + (x1 - x0)
    sy1 = sy0 + (y1 - y0)

    src = src_rgba[sy0:sy1, sx0:sx1]
    alpha = (src[:, :, 3:4].astype(np.float32) / 255.0)
    if np.max(alpha) <= 0:
        return
    dst_roi = dst[y0:y1, x0:x1].astype(np.float32)
    src_rgb = src[:, :, :3].astype(np.float32)
    out = (src_rgb * alpha) + (dst_roi * (1.0 - alpha))
    dst[y0:y1, x0:x1] = out.astype(np.uint8)


def _render_hazard_icon_supersampled(
    kind: str,
    accent: tuple[int, int, int],
    icon_size: int,
) -> np.ndarray:
    """Render high-quality icon (RGBA) using supersampling then downscale."""
    ss = 4
    size = max(20, int(icon_size))
    hs = size * ss
    icon = np.zeros((hs, hs, 4), dtype=np.uint8)

    c = hs // 2
    r = int(0.43 * hs)
    stroke = max(2, hs // 22)
    color = (int(accent[0]), int(accent[1]), int(accent[2]), 255)

    cv2.circle(icon, (c, c), r, color, stroke, cv2.LINE_AA)

    if kind == "fall":
        cv2.circle(icon, (c - hs // 13, c - hs // 5), max(2, hs // 16), color, -1, cv2.LINE_AA)
        cv2.line(icon, (c - hs // 11, c - hs // 8), (c + hs // 8, c + hs // 14), color, stroke, cv2.LINE_AA)
        cv2.line(icon, (c + hs // 32, c - hs // 24), (c + hs // 5, c - hs // 7), color, stroke, cv2.LINE_AA)
        cv2.line(icon, (c + hs // 8, c + hs // 14), (c + hs // 4, c + hs // 4), color, stroke, cv2.LINE_AA)
        cv2.line(icon, (c + hs // 18, c + hs // 8), (c - hs // 18, c + hs // 4), color, stroke, cv2.LINE_AA)
    elif kind == "vest":
        pts = np.array([
            [c - hs // 4, c - hs // 8],
            [c - hs // 7, c - hs // 4],
            [c + hs // 7, c - hs // 4],
            [c + hs // 4, c - hs // 8],
            [c + hs // 6, c + hs // 4],
            [c - hs // 6, c + hs // 4],
        ], dtype=np.int32)
        cv2.polylines(icon, [pts], True, color, stroke, cv2.LINE_AA)
        cv2.line(icon, (c, c - hs // 4), (c, c + hs // 4), color, stroke, cv2.LINE_AA)
    elif kind == "helmet":
        cv2.ellipse(icon, (c, c), (hs // 5, hs // 7), 0, 180, 360, color, stroke, cv2.LINE_AA)
        cv2.line(icon, (c - hs // 5, c), (c + hs // 5, c), color, stroke, cv2.LINE_AA)
    elif kind == "proximity":
        cv2.circle(icon, (c - hs // 7, c), max(2, hs // 14), color, -1, cv2.LINE_AA)
        cv2.circle(icon, (c + hs // 7, c), max(2, hs // 14), color, -1, cv2.LINE_AA)
        cv2.line(icon, (c - hs // 18, c), (c + hs // 18, c), color, stroke, cv2.LINE_AA)
    else:
        cv2.line(icon, (c, c - hs // 6), (c, c + hs // 9), color, stroke, cv2.LINE_AA)
        cv2.circle(icon, (c, c + hs // 5), max(2, hs // 20), color, -1, cv2.LINE_AA)

    return cv2.resize(icon, (size, size), interpolation=cv2.INTER_AREA)


def _draw_rounded_rect(
    img: np.ndarray,
    p1: tuple[int, int],
    p2: tuple[int, int],
    color: tuple[int, int, int],
    radius: int,
) -> None:
    """Draw a filled rounded rectangle in-place."""
    x1, y1 = p1
    x2, y2 = p2
    r = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), color, -1)
    cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), color, -1)
    cv2.circle(img, (x1 + r, y1 + r), r, color, -1)
    cv2.circle(img, (x2 - r, y1 + r), r, color, -1)
    cv2.circle(img, (x1 + r, y2 - r), r, color, -1)
    cv2.circle(img, (x2 - r, y2 - r), r, color, -1)


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
        self._last_event_ts: Dict[tuple[str, str, int, str], float] = {}

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
                dedup_key = (
                    ev.camera_id,
                    (ev.event_type or "").strip().lower(),
                    int(ev.track_id) if ev.track_id is not None else -1,
                    ev.severity.name,
                )
                prev_ts = self._last_event_ts.get(dedup_key, -1e9)
                if (now - prev_ts) < self.cfg.banner_repeat_cooldown_sec:
                    continue
                self._last_event_ts[dedup_key] = now
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

        banner_h = int(72 * cfg.overlay_scale)
        banner_w = int(max(320, min(640, fw * 0.62)))
        x0 = (fw - banner_w) // 2
        radius = max(14, int(cfg.banner_corner_radius * 1.35))
        meta_scale = t.font_md * 0.95 * cfg.overlay_scale
        title_scale = t.font_xl * 0.74 * cfg.overlay_scale
        y_offset = cfg.banner_top_margin
        line_h = max(1, int(2 * cfg.overlay_scale))

        regular_font_path, bold_font_path = _font_paths()
        meta_font = _load_pil_font(regular_font_path, max(11, int(12 * cfg.overlay_scale)))
        title_font = _load_pil_font(bold_font_path or regular_font_path, max(14, int(16 * cfg.overlay_scale)))
        body_font = _load_pil_font(regular_font_path, max(11, int(12 * cfg.overlay_scale)))
        time_font = _load_pil_font(regular_font_path, max(11, int(12 * cfg.overlay_scale)))

        for ts, ev, alpha in active:
            age = now - ts
            enter_p = _ease_out_cubic(min(1.0, age / max(0.05, cfg.banner_enter_sec)))
            slide_px = int((1.0 - enter_p) * 16)
            y = y_offset - slide_px
            overlay = frame.copy()

            title_text, body_text = _notification_copy(
                ev,
                include_worker_id=cfg.banner_include_worker_id,
                display_id_map=display_id_map,
            )
            meta_text = "VisionSafe"
            accent = _hazard_accent(ev, t)
            kind = _hazard_kind(ev.event_type)

            # Light card style matching the reference image while keeping
            # project palette for hazard color accents.
            card_outer = (232, 232, 232)
            card_inner = (246, 246, 246)
            card_stroke = (220, 220, 220)
            highlight = (255, 255, 255)
            meta_c = (110, 110, 110)
            title_c = (22, 22, 22)
            body_c = (70, 70, 70)
            time_c = (50, 50, 50)

            # Soft shadow to create floating notification depth.
            sx = cfg.banner_shadow_px
            _draw_rounded_rect(
                overlay,
                (x0 + sx, y + sx),
                (x0 + banner_w + sx, y + banner_h + sx),
                (12, 12, 12),
                radius,
            )

            # Outer shell + inner light body similar to the provided mock.
            _draw_rounded_rect(
                overlay,
                (x0, y),
                (x0 + banner_w, y + banner_h),
                card_outer,
                radius,
            )
            inset = 3
            _draw_rounded_rect(
                overlay,
                (x0 + inset, y + inset),
                (x0 + banner_w - inset, y + banner_h - inset),
                card_inner,
                max(2, radius - 2),
            )
            cv2.rectangle(
                overlay,
                (x0 + inset, y + inset),
                (x0 + banner_w - inset, y + banner_h - inset),
                card_stroke,
                1,
            )

            # Top highlight for polished card look.
            cv2.line(
                overlay,
                (x0 + radius, y + 2),
                (x0 + banner_w - radius, y + 2),
                highlight,
                line_h,
                cv2.LINE_AA,
            )

            # Left outlined hazard icon (custom per hazard).
            icon_r = int(18 * cfg.overlay_scale)
            icon_x = x0 + int(30 * cfg.overlay_scale)
            icon_y = y + (banner_h // 2)
            icon_img = _render_hazard_icon_supersampled(kind, accent, icon_size=icon_r * 2)
            _alpha_blit(overlay, icon_img, icon_x - icon_r, icon_y - icon_r)

            # Time text on the right.
            time_text = time.strftime("%I:%M %p", time.localtime(ts)).lstrip("0").lower()
            if time_font is not None:
                time_text = _truncate_text_to_width_pil(time_text, max(80, int(banner_w * 0.22)), time_font)
                time_w = _pil_text_width(time_text, time_font)
                time_x = x0 + banner_w - int(18 * cfg.overlay_scale) - time_w
                time_y = y + int(12 * cfg.overlay_scale)
                overlay = _draw_text_pil(overlay, time_text, time_x, time_y, time_font, time_c)
            else:
                (time_w, time_h), _ = cv2.getTextSize(time_text, t.font, meta_scale, t.thick_thin)
                time_x = x0 + banner_w - int(18 * cfg.overlay_scale) - time_w
                time_y = y + int(24 * cfg.overlay_scale)
                cv2.putText(
                    overlay, time_text, (time_x, time_y),
                    t.font, meta_scale, time_c, t.thick_thin, cv2.LINE_AA,
                )

            text_x = icon_x + icon_r + int(14 * cfg.overlay_scale)
            text_right = time_x - int(12 * cfg.overlay_scale)
            text_max_w = max(60, text_right - text_x)
            body_scale = t.font_md * 0.72 * cfg.overlay_scale
            if meta_font is not None and title_font is not None and body_font is not None:
                meta_text = _truncate_text_to_width_pil(meta_text, text_max_w, meta_font)
                title_text = _truncate_text_to_width_pil(title_text, text_max_w, title_font)
                body_text = _truncate_text_to_width_pil(body_text, text_max_w, body_font)
            else:
                meta_text = _truncate_text_to_width(meta_text, text_max_w, t.font, meta_scale, t.thick_thin)
                title_text = _truncate_text_to_width(title_text, text_max_w, t.font, title_scale, t.thick_std)
                body_text = _truncate_text_to_width(body_text, text_max_w, t.font, body_scale, t.thick_thin)

            meta_y = y + int(12 * cfg.overlay_scale)
            title_y = y + int(29 * cfg.overlay_scale)
            body_y = y + int(47 * cfg.overlay_scale)

            if meta_font is not None and title_font is not None and body_font is not None:
                overlay = _draw_text_pil(overlay, meta_text, text_x, meta_y, meta_font, meta_c)
                overlay = _draw_text_pil(overlay, title_text, text_x, title_y, title_font, title_c)
                overlay = _draw_text_pil(overlay, body_text, text_x, body_y, body_font, body_c)
            else:
                cv2.putText(
                    overlay, meta_text, (text_x, meta_y),
                    t.font, meta_scale, meta_c, t.thick_thin, cv2.LINE_AA,
                )
                cv2.putText(
                    overlay, title_text, (text_x, title_y),
                    t.font, title_scale, title_c, t.thick_std, cv2.LINE_AA,
                )
                cv2.putText(
                    overlay, body_text, (text_x, body_y),
                    t.font, body_scale, body_c, t.thick_thin, cv2.LINE_AA,
                )

            # Composite per-banner using animation/fade alpha.
            eff_alpha = max(0.0, min(1.0, (0.42 + 0.58 * enter_p) * alpha))
            cv2.addWeighted(overlay, eff_alpha, frame, 1.0 - eff_alpha, 0, frame)

            y_offset += banner_h + cfg.banner_stack_gap
