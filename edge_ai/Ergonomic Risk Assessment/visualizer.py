"""
visualizer.py
-------------
Draws keypoints, skeleton, angle values, RULA/REBA scores,
and risk alerts on each video frame using OpenCV.
"""

import cv2
import numpy as np
from tracker import WorkerState


# ── colour map (BGR) ───────────────────────────────────────────────────────────
COLOR = {
    "safe":    (50, 200, 50),    # green
    "low":     (50, 200, 200),   # yellow-green
    "medium":  (30, 140, 255),   # orange
    "high":    (30, 30, 230),    # red
    "skeleton":(200, 200, 200),  # light grey
    "kp":      (255, 255, 255),  # white
    "text_bg": (20, 20, 20),     # near black
    "text":    (240, 240, 240),  # off-white
}

# COCO skeleton connections
SKELETON = [
    (5, 6),   # shoulders
    (5, 7),   (7, 9),    # left arm
    (6, 8),   (8, 10),   # right arm
    (5, 11),  (6, 12),   # torso sides
    (11, 12),            # hips
    (11, 13), (13, 15),  # left leg
    (12, 14), (14, 16),  # right leg
]


def _score_color(score, max_score=7):
    ratio = (score - 1) / max(max_score - 1, 1)
    if ratio < 0.3:
        return COLOR["safe"]
    elif ratio < 0.6:
        return COLOR["low"]
    elif ratio < 0.85:
        return COLOR["medium"]
    else:
        return COLOR["high"]


def _put_text(frame, text, pos, scale=0.5, color=None, thickness=1, bg=True):
    color = color or COLOR["text"]
    font  = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    x, y = pos
    if bg:
        cv2.rectangle(frame, (x - 2, y - th - 2), (x + tw + 2, y + baseline),
                      COLOR["text_bg"], -1)
    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def draw_skeleton(frame, keypoints, confs, conf_thresh=0.5):
    """Draw skeleton lines and keypoint circles."""
    pts = []
    for i, (kp, cf) in enumerate(zip(keypoints, confs)):
        if cf >= conf_thresh:
            pts.append((int(kp[0]), int(kp[1])))
        else:
            pts.append(None)

    # connections
    for a, b in SKELETON:
        if pts[a] and pts[b]:
            cv2.line(frame, pts[a], pts[b], COLOR["skeleton"], 2, cv2.LINE_AA)

    # keypoints
    for pt in pts:
        if pt:
            cv2.circle(frame, pt, 4, COLOR["kp"], -1, cv2.LINE_AA)
            cv2.circle(frame, pt, 4, (0, 0, 0), 1, cv2.LINE_AA)


def draw_angle_labels(frame, keypoints, confs, angles, conf_thresh=0.5):
    """Draw computed angle values next to their reference joint."""
    label_map = {
        # angle_name: keypoint_index_to_place_label_near
        "upper_arm": 5,   # shoulder
        "lower_arm": 7,   # elbow
        "neck":      0,   # nose
        "trunk":     11,  # hip
        "knee":      13,  # knee
    }
    for angle_name, kp_idx in label_map.items():
        val = angles.get(angle_name)
        if val is None:
            continue
        cf = confs[kp_idx] if kp_idx < len(confs) else 0
        if cf < conf_thresh:
            continue
        x = int(keypoints[kp_idx][0]) + 8
        y = int(keypoints[kp_idx][1])
        _put_text(frame, f"{angle_name}: {val:.0f}°", (x, y), scale=0.4)


def draw_worker_panel(frame, state: WorkerState, panel_x: int, panel_y: int):
    """
    Draws a score panel for one worker in the top-left area.
    """
    rula  = state.rula_score or 0
    reba  = state.reba_score or 0
    dur   = state.sustained_duration
    alert = state.alert_active

    rula_col = _score_color(rula, 7)
    reba_col = _score_color(reba, 15)

    panel_w, panel_h = 230, 110
    overlay = frame.copy()
    cv2.rectangle(overlay, (panel_x, panel_y),
                  (panel_x + panel_w, panel_y + panel_h),
                  (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    cv2.rectangle(frame, (panel_x, panel_y),
                  (panel_x + panel_w, panel_y + panel_h),
                  rula_col if alert else (80, 80, 80), 2)

    _put_text(frame, f"Worker {state.worker_id}",
              (panel_x + 6, panel_y + 18), scale=0.5,
              color=COLOR["text"], bg=False)

    _put_text(frame, f"RULA: {rula}  ({state.rula_risk[:20]})",
              (panel_x + 6, panel_y + 40), scale=0.42,
              color=rula_col, bg=False)

    _put_text(frame, f"REBA: {reba}  ({state.reba_risk[:20]})",
              (panel_x + 6, panel_y + 60), scale=0.42,
              color=reba_col, bg=False)

    _put_text(frame, f"Duration: {dur:.1f}s",
              (panel_x + 6, panel_y + 80), scale=0.42,
              color=COLOR["text"], bg=False)

    if alert:
        _put_text(frame, "!  ALERT — BAD POSTURE",
                  (panel_x + 6, panel_y + 100), scale=0.45,
                  color=COLOR["high"], bg=False)


def draw_global_alert(frame):
    """Full-frame red border + banner when any worker is in alert."""
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), COLOR["high"], 8)
    banner_h = 40
    overlay  = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), COLOR["high"], -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    _put_text(frame, "ERGONOMIC RISK ALERT — Review Worker Posture",
              (10, 28), scale=0.7, color=WHITE, thickness=2, bg=False)


WHITE = (255, 255, 255)


def draw_fps(frame, fps):
    _put_text(frame, f"FPS: {fps:.1f}", (10, frame.shape[0] - 10),
              scale=0.45, color=COLOR["text"], bg=False)
