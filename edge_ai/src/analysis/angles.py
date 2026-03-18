"""
VisionSafe 360 — Body Angle Computation from COCO-17 Pose Keypoints

Computes the 7 body angles required for RULA / REBA scoring.
Ported from the Ergonomic Risk Assessment standalone project.

YOLO Pose keypoint index map (COCO 17):
  0  Nose          1  Left Eye       2  Right Eye
  3  Left Ear      4  Right Ear      5  Left Shoulder
  6  Right Shoulder 7 Left Elbow     8  Right Elbow
  9  Left Wrist    10 Right Wrist    11 Left Hip
  12 Right Hip     13 Left Knee      14 Right Knee
  15 Left Ankle    16 Right Ankle
"""
from __future__ import annotations

import numpy as np

# ── constants ──────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.5

# ── keypoint indices ───────────────────────────────────────────────
KP = {
    "nose": 0,
    "left_shoulder": 5, "right_shoulder": 6,
    "left_elbow": 7, "right_elbow": 8,
    "left_wrist": 9, "right_wrist": 10,
    "left_hip": 11, "right_hip": 12,
    "left_knee": 13, "right_knee": 14,
    "left_ankle": 15, "right_ankle": 16,
}


# ── core math ──────────────────────────────────────────────────────
def angle_between(a: np.ndarray, b: np.ndarray, c: np.ndarray):
    """Angle at point B formed by vectors BA and BC, in degrees."""
    ba = a - b
    bc = c - b
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return None
    cos_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def vertical_angle(a: np.ndarray, b: np.ndarray):
    """Angle between vector AB and the upward vertical (0, -1)."""
    vec = b - a
    vertical = np.array([0.0, -1.0])
    norm_vec = np.linalg.norm(vec)
    if norm_vec < 1e-6:
        return None
    cos_angle = np.dot(vec, vertical) / norm_vec
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


# ── confidence check ───────────────────────────────────────────────
def _get_kp(keypoints, name, confs):
    """Returns (x, y) for a keypoint only if confidence >= threshold."""
    idx = KP[name]
    if confs[idx] < CONFIDENCE_THRESHOLD:
        return None
    return np.array(keypoints[idx][:2], dtype=float)


def _midpoint(p1, p2):
    if p1 is None or p2 is None:
        return None
    return (p1 + p2) / 2.0


# ── main angle extraction ─────────────────────────────────────────
def compute_angles(keypoints, confs, side="left"):
    """
    Extracts 7 body angles from one person's COCO-17 keypoints.

    Parameters
    ----------
    keypoints : array-like, shape (17, 2) — [x, y] per keypoint
    confs     : array-like, shape (17,)   — confidence per keypoint
    side      : "left" or "right" — which arm for RULA upper-limb group

    Returns
    -------
    dict {angle_name: degrees_or_None}
    """
    g = lambda name: _get_kp(keypoints, name, confs)

    shoulder = g(f"{side}_shoulder")
    elbow = g(f"{side}_elbow")
    wrist = g(f"{side}_wrist")
    hip = g(f"{side}_hip")
    knee = g(f"{side}_knee")
    ankle = g(f"{side}_ankle")

    l_shoulder = g("left_shoulder")
    r_shoulder = g("right_shoulder")
    l_hip = g("left_hip")
    r_hip = g("right_hip")
    nose = g("nose")

    mid_shoulder = _midpoint(l_shoulder, r_shoulder)
    mid_hip = _midpoint(l_hip, r_hip)

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

    # 3. Wrist flexion — approximate from elbow-wrist vertical alignment
    if elbow is not None and wrist is not None:
        results["wrist"] = vertical_angle(elbow, wrist)
    else:
        results["wrist"] = None

    # 4. Neck flexion — angle from mid-shoulder up to nose vs vertical
    if mid_shoulder is not None and nose is not None:
        results["neck"] = vertical_angle(mid_shoulder, nose)
    else:
        results["neck"] = None

    # 5. Trunk flexion — angle of mid-hip → mid-shoulder vs vertical
    if mid_shoulder is not None and mid_hip is not None:
        results["trunk"] = vertical_angle(mid_hip, mid_shoulder)
    else:
        results["trunk"] = None

    # 6. Trunk lateral tilt — tilt of shoulder line vs horizontal
    if l_shoulder is not None and r_shoulder is not None:
        dx = r_shoulder[0] - l_shoulder[0]
        dy = r_shoulder[1] - l_shoulder[1]
        results["trunk_tilt"] = float(abs(np.degrees(np.arctan2(dy, dx))))
    else:
        results["trunk_tilt"] = None

    # 7. Knee flexion (0° = straight, increases with bend)
    if hip is not None and knee is not None and ankle is not None:
        joint_angle = angle_between(hip, knee, ankle)
        results["knee"] = (180.0 - joint_angle) if joint_angle is not None else None
    else:
        results["knee"] = None

    return results
