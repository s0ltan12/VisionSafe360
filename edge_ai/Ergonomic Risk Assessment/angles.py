"""
angles.py
---------
Computes the 7 body angles required for RULA / REBA from YOLO11-Pose keypoints.

YOLO11-Pose keypoint index map (COCO 17):
  0  Nose          1  Left Eye       2  Right Eye
  3  Left Ear      4  Right Ear      5  Left Shoulder
  6  Right Shoulder 7 Left Elbow     8  Right Elbow
  9  Left Wrist    10 Right Wrist    11 Left Hip
  12 Right Hip     13 Left Knee      14 Right Knee
  15 Left Ankle    16 Right Ankle
"""

import numpy as np
from collections import deque

# ── constants ──────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.5   # ignore keypoints below this confidence
SMOOTHING_WINDOW     = 10    # frames for moving average (~0.3 sec at 30 FPS)

# ── keypoint indices ───────────────────────────────────────────────────────────
KP = {
    "nose":           0,
    "left_shoulder":  5,  "right_shoulder": 6,
    "left_elbow":     7,  "right_elbow":    8,
    "left_wrist":     9,  "right_wrist":   10,
    "left_hip":      11,  "right_hip":     12,
    "left_knee":     13,  "right_knee":    14,
    "left_ankle":    15,  "right_ankle":   16,
}


# ── core math ──────────────────────────────────────────────────────────────────
def angle_between(a, b, c):
    """
    Angle at point B formed by vectors BA and BC, in degrees.
    Returns None if vectors are degenerate.
    """
    ba = a - b
    bc = c - b
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return None
    cos_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def vertical_angle(a, b):
    """
    Angle between vector AB and the upward vertical (0, -1).
    Used for trunk and neck flexion relative to gravity.
    """
    vec = b - a
    vertical = np.array([0.0, -1.0])
    norm_vec = np.linalg.norm(vec)
    if norm_vec < 1e-6:
        return None
    cos_angle = np.dot(vec, vertical) / norm_vec
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def lateral_tilt(left_pt, right_pt):
    """
    Angle of tilt between two symmetric points (e.g. shoulders or hips)
    relative to horizontal. Used for trunk lateral tilt (REBA).
    """
    dx = right_pt[0] - left_pt[0]
    dy = right_pt[1] - left_pt[1]
    return float(abs(np.degrees(np.arctan2(dy, dx))))


# ── confidence check ───────────────────────────────────────────────────────────
def get_kp(keypoints, name, confs):
    """
    Returns the (x, y) numpy array for a keypoint only if confidence >= threshold.
    Returns None otherwise.
    """
    idx = KP[name]
    if confs[idx] < CONFIDENCE_THRESHOLD:
        return None
    return np.array(keypoints[idx][:2], dtype=float)


def midpoint(p1, p2):
    if p1 is None or p2 is None:
        return None
    return (p1 + p2) / 2.0


# ── main angle extraction ──────────────────────────────────────────────────────
def compute_angles(keypoints, confs, side="left"):
    """
    Extracts all 7 angles from one person's keypoints.

    Parameters
    ----------
    keypoints : list of [x, y] pairs  (17 points)
    confs     : list of float confidence values (17 values)
    side      : "left" or "right" — which arm to use for RULA upper-limb group

    Returns
    -------
    dict  {angle_name: degrees_or_None}
        None means the angle could not be computed (low confidence / occlusion).
    """
    g = lambda name: get_kp(keypoints, name, confs)

    shoulder = g(f"{side}_shoulder")
    elbow    = g(f"{side}_elbow")
    wrist    = g(f"{side}_wrist")
    hip      = g(f"{side}_hip")
    knee     = g(f"{side}_knee")
    ankle    = g(f"{side}_ankle")

    l_shoulder = g("left_shoulder")
    r_shoulder = g("right_shoulder")
    l_hip      = g("left_hip")
    r_hip      = g("right_hip")
    nose       = g("nose")

    mid_shoulder = midpoint(l_shoulder, r_shoulder)
    mid_hip      = midpoint(l_hip, r_hip)

    results = {}

    # 1. Upper arm — angle at shoulder between hip line and elbow
    if shoulder is not None and elbow is not None and hip is not None:
        results["upper_arm"] = angle_between(hip, shoulder, elbow)
    else:
        results["upper_arm"] = None

    # 2. Lower arm (elbow flexion)
    if shoulder is not None and elbow is not None and wrist is not None:
        results["lower_arm"] = angle_between(shoulder, elbow, wrist)
    else:
        results["lower_arm"] = None

    # 3. Wrist flexion — approximate from elbow-wrist alignment
    #    Full wrist deviation needs hand keypoints (not in COCO 17).
    #    We estimate via elbow -> wrist direction vs wrist vertical.
    if elbow is not None and wrist is not None:
        results["wrist"] = vertical_angle(elbow, wrist)
    else:
        results["wrist"] = None

    # 4. Neck flexion — angle from mid-shoulder up to nose vs vertical
    if mid_shoulder is not None and nose is not None:
        results["neck"] = vertical_angle(mid_shoulder, nose)
    else:
        results["neck"] = None

    # 5. Trunk flexion — angle of mid-shoulder -> mid-hip vs vertical
    if mid_shoulder is not None and mid_hip is not None:
        results["trunk"] = vertical_angle(mid_hip, mid_shoulder)
    else:
        results["trunk"] = None

    # 6. Trunk lateral tilt — tilt of shoulder line vs horizontal
    if l_shoulder is not None and r_shoulder is not None:
        results["trunk_tilt"] = lateral_tilt(l_shoulder, r_shoulder)
    else:
        results["trunk_tilt"] = None

    # 7. Knee flexion
    if hip is not None and knee is not None and ankle is not None:
        results["knee"] = angle_between(hip, knee, ankle)
    else:
        results["knee"] = None

    return results


# ── smoothing ──────────────────────────────────────────────────────────────────
class AngleSmoother:
    """
    Maintains a moving average window per angle to reduce noise.
    Only includes frames where the value is not None (confident detection).
    """
    def __init__(self, window=SMOOTHING_WINDOW):
        self.window = window
        self.buffers = {}

    def update(self, angles: dict) -> dict:
        smoothed = {}
        for key, val in angles.items():
            if key not in self.buffers:
                self.buffers[key] = deque(maxlen=self.window)
            if val is not None:
                self.buffers[key].append(val)
            buf = self.buffers[key]
            smoothed[key] = float(np.mean(buf)) if len(buf) > 0 else None
        return smoothed
