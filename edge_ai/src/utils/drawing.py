"""
Drawing utilities — annotate frames with bounding boxes, track IDs, labels, and hazard events.
"""
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity

# Colour palette (BGR) — deterministic per class_id
_PALETTE = [
    (0, 255, 0),     # green
    (255, 178, 50),   # orange-blue
    (0, 255, 255),    # yellow
    (255, 0, 0),      # blue
    (0, 0, 255),      # red
    (255, 0, 255),    # magenta
    (128, 255, 0),    # lime
    (255, 255, 0),    # cyan
    (0, 128, 255),    # deep orange
    (128, 0, 255),    # purple
]

# Hazard severity → colour (BGR)
_SEVERITY_COLOURS = {
    Severity.LOW:      (0, 255, 0),      # green
    Severity.MEDIUM:   (0, 255, 255),    # yellow
    Severity.HIGH:     (0, 128, 255),    # orange
    Severity.CRITICAL: (0, 0, 255),      # red
}


def _colour_for(class_id: int) -> Tuple[int, int, int]:
    return _PALETTE[class_id % len(_PALETTE)]


def draw_detections(
    frame: np.ndarray,
    detections: List[Detection],
    thickness: int = 2,
    font_scale: float = 0.55,
    display_id_map: Optional[Dict[int, int]] = None,
) -> np.ndarray:
    """Draw bounding boxes, class names, confidence, and track IDs on *frame* (in-place).

    If *display_id_map* is provided, show stable display IDs instead of raw
    ByteTrack IDs (which can jump after ID switches).
    Returns the same frame for convenience.
    """
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        colour = _colour_for(det.class_id)

        # Box
        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, thickness)

        # Label text:  "person D3  0.87"  (D = display ID) or "person #3  0.87"
        parts = [det.class_name]
        if det.track_id is not None:
            if display_id_map and det.track_id in display_id_map:
                parts.append(f"D{display_id_map[det.track_id]}")
            else:
                parts.append(f"#{det.track_id}")
        parts.append(f"{det.confidence:.2f}")
        label = "  ".join(parts)

        # Background rectangle for readability
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - baseline - 4), (x1 + tw + 4, y1), colour, -1)
        cv2.putText(
            frame, label, (x1 + 2, y1 - baseline - 2),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1, cv2.LINE_AA,
        )

    return frame


def draw_hazard_events(
    frame: np.ndarray,
    events: List[HazardEvent],
    thickness: int = 2,
    font_scale: float = 0.5,
) -> np.ndarray:
    """Draw hazard event indicators on *frame* (in-place).

    - Fall: red overlay on person bbox
    - Proximity: orange line between person and vehicle (via metadata)
    - PPE: yellow icon/text on person bbox
    - Posture: purple text overlay
    """
    h, w = frame.shape[:2]
    banner_y = h - 10  # bottom-up for alert banners

    for event in events:
        colour = _SEVERITY_COLOURS.get(event.severity, (255, 255, 255))

        # Draw bbox highlight if available
        if event.bbox:
            x1, y1, x2, y2 = event.bbox

            if "fall" in event.event_type:
                # Red semi-transparent overlay
                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)

            elif "proximity" in event.event_type:
                # Orange dashed border
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 128, 255), 2)

            elif "no_helmet" in event.event_type or "no_vest" in event.event_type:
                # Yellow highlight
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)

            elif "posture" in event.event_type:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 2)

            # Label above bbox
            label = f"{event.event_type} [{event.severity.name}]"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1 - 2), colour, -1)
            cv2.putText(
                frame, label, (x1 + 2, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1, cv2.LINE_AA,
            )

        # Bottom alert banner
        banner_text = f"[!] {event.event_type.upper()} — {event.severity.name}"
        cv2.putText(
            frame, banner_text, (10, banner_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA,
        )
        banner_y -= 20

    return frame


def draw_hud(
    frame: np.ndarray,
    fps: float,
    latency_ms: float,
    n_det: int,
    n_tracked: int,
    vram_mb: int,
    n_hazards: int = 0,
    pose_ms: float = 0.0,
    calibrated: bool = True,
) -> np.ndarray:
    """Draw a small heads-up-display in the top-left corner.

    """
    lines = [
        f"FPS: {fps:.1f}",
        f"Latency: {latency_ms:.1f} ms",
        f"Det: {n_det}  Tracked: {n_tracked}",
        f"VRAM: {vram_mb} MB",
    ]
    if n_hazards > 0:
        lines.append(f"Hazards: {n_hazards}")
    if pose_ms > 0:
        lines.append(f"Pose: {pose_ms:.1f} ms")

    y = 24
    for line in lines:
        cv2.putText(
            frame, line, (10, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1, cv2.LINE_AA,
        )
        y += 22

    return frame
