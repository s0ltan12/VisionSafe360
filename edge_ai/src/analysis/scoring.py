"""
VisionSafe 360 — RULA and REBA Ergonomic Scoring

Full scoring algorithms based on:
  - RULA: McAtamney & Corlett (1993), Applied Ergonomics 24(2), pp. 91-99
  - REBA: Hignett & McAtamney (2000), Applied Ergonomics 31(2), pp. 201-205

Ported from the Ergonomic Risk Assessment standalone project.
"""
from __future__ import annotations


# ══════════════════════════════════════════════════════════════════
# RULA — Individual Component Scoring
# ══════════════════════════════════════════════════════════════════

def rula_upper_arm(angle):
    if angle is None:
        return 1
    if angle <= 20:
        return 1
    elif angle <= 45:
        return 2
    elif angle <= 90:
        return 3
    else:
        return 4


def rula_lower_arm(angle):
    if angle is None:
        return 1
    if 60 <= angle <= 100:
        return 1
    else:
        return 2


def rula_wrist(angle):
    if angle is None:
        return 1
    if angle == 0:
        return 1
    elif angle <= 15:
        return 2
    else:
        return 3


def rula_wrist_twist():
    """Cannot measure from COCO-17. Default neutral."""
    return 1


def rula_neck(angle):
    if angle is None:
        return 1
    if angle <= 10:
        return 1
    elif angle <= 20:
        return 2
    else:
        return 3


def rula_trunk(angle):
    if angle is None:
        return 1
    if angle <= 10:
        return 1
    elif angle <= 20:
        return 2
    elif angle <= 60:
        return 3
    else:
        return 4


def rula_legs(supported=True):
    return 1 if supported else 2


# RULA Table A: (upper_arm, lower_arm, wrist) → [twist1, twist2]
_RULA_TABLE_A = {
    (1, 1, 1): [1, 2], (1, 1, 2): [2, 2], (1, 1, 3): [2, 3],
    (1, 2, 1): [2, 2], (1, 2, 2): [2, 2], (1, 2, 3): [3, 3],
    (1, 3, 1): [2, 3], (1, 3, 2): [3, 3], (1, 3, 3): [3, 3],
    (2, 1, 1): [2, 3], (2, 1, 2): [2, 3], (2, 1, 3): [3, 3],
    (2, 2, 1): [3, 3], (2, 2, 2): [3, 3], (2, 2, 3): [3, 4],
    (2, 3, 1): [3, 4], (2, 3, 2): [3, 4], (2, 3, 3): [4, 4],
    (3, 1, 1): [3, 3], (3, 1, 2): [3, 3], (3, 1, 3): [4, 4],
    (3, 2, 1): [4, 4], (3, 2, 2): [4, 4], (3, 2, 3): [4, 4],
    (3, 3, 1): [4, 4], (3, 3, 2): [4, 4], (3, 3, 3): [5, 5],
    (4, 1, 1): [4, 4], (4, 1, 2): [4, 4], (4, 1, 3): [4, 5],
    (4, 2, 1): [4, 4], (4, 2, 2): [4, 4], (4, 2, 3): [4, 5],
    (4, 3, 1): [4, 4], (4, 3, 2): [4, 5], (4, 3, 3): [5, 5],
}

# RULA Table B: (neck, trunk, legs) → score
_RULA_TABLE_B = {
    (1, 1, 1): 1, (1, 1, 2): 2, (1, 2, 1): 2, (1, 2, 2): 3,
    (1, 3, 1): 2, (1, 3, 2): 3, (1, 4, 1): 3, (1, 4, 2): 4,
    (1, 5, 1): 4, (1, 5, 2): 4, (1, 6, 1): 4, (1, 6, 2): 5,
    (2, 1, 1): 1, (2, 1, 2): 2, (2, 2, 1): 2, (2, 2, 2): 3,
    (2, 3, 1): 3, (2, 3, 2): 3, (2, 4, 1): 3, (2, 4, 2): 4,
    (2, 5, 1): 4, (2, 5, 2): 5, (2, 6, 1): 5, (2, 6, 2): 5,
    (3, 1, 1): 3, (3, 1, 2): 3, (3, 2, 1): 3, (3, 2, 2): 4,
    (3, 3, 1): 4, (3, 3, 2): 4, (3, 4, 1): 4, (3, 4, 2): 5,
    (3, 5, 1): 5, (3, 5, 2): 6, (3, 6, 1): 6, (3, 6, 2): 6,
    (4, 1, 1): 4, (4, 1, 2): 4, (4, 2, 1): 4, (4, 2, 2): 4,
    (4, 3, 1): 4, (4, 3, 2): 5, (4, 4, 1): 5, (4, 4, 2): 5,
    (4, 5, 1): 6, (4, 5, 2): 6, (4, 6, 1): 6, (4, 6, 2): 7,
}

# RULA Table C: A × B → final (1-indexed)
_RULA_TABLE_C = [
    [1, 2, 3, 3, 4, 5, 5],  # A=1
    [2, 2, 3, 4, 4, 5, 5],  # A=2
    [3, 3, 3, 4, 4, 5, 6],  # A=3
    [3, 3, 3, 4, 5, 6, 6],  # A=4
    [4, 4, 4, 5, 6, 7, 7],  # A=5
    [4, 4, 5, 6, 6, 7, 7],  # A=6
    [5, 5, 6, 6, 7, 7, 7],  # A=7
]


def compute_rula(angles, muscle_use=False, load_kg=0.0, static_posture=False):
    """
    Full RULA score from body angles.

    Returns dict with: score_a, score_b, final_score (1-7), risk_level, breakdown.
    """
    s_upper_arm = rula_upper_arm(angles.get("upper_arm"))
    s_lower_arm = rula_lower_arm(angles.get("lower_arm"))
    s_wrist = rula_wrist(angles.get("wrist"))
    s_wrist_twist = rula_wrist_twist()
    s_neck = rula_neck(angles.get("neck"))
    s_trunk = rula_trunk(angles.get("trunk"))
    s_legs = rula_legs()

    muscle_adj = 1 if (muscle_use or static_posture) else 0
    if load_kg < 2:
        load_score = 0
    elif load_kg <= 10:
        load_score = 1
    else:
        load_score = 2

    key_a = (min(s_upper_arm, 4), min(s_lower_arm, 3), min(s_wrist, 3))
    table_a_vals = _RULA_TABLE_A.get(key_a, [4, 4])
    score_a_raw = table_a_vals[s_wrist_twist - 1]
    score_a = min(score_a_raw + muscle_adj + load_score, 8)

    trunk_capped = min(s_trunk, 6)
    key_b = (min(s_neck, 4), trunk_capped, min(s_legs, 2))
    score_b_raw = _RULA_TABLE_B.get(key_b, 5)
    score_b = min(score_b_raw + muscle_adj + load_score, 8)

    idx_a = min(score_a, 7) - 1
    idx_b = min(score_b, 7) - 1
    final = _RULA_TABLE_C[idx_a][idx_b]

    return {
        "score_a": score_a,
        "score_b": score_b,
        "final_score": final,
        "risk_level": _rula_risk_label(final),
        "breakdown": {
            "upper_arm": s_upper_arm,
            "lower_arm": s_lower_arm,
            "wrist": s_wrist,
            "neck": s_neck,
            "trunk": s_trunk,
            "legs": s_legs,
            "muscle_adj": muscle_adj,
            "load_score": load_score,
        },
    }


def _rula_risk_label(score):
    if score <= 2:
        return "Acceptable"
    elif score <= 4:
        return "Low Risk"
    elif score <= 6:
        return "Medium Risk"
    else:
        return "HIGH RISK"


# ══════════════════════════════════════════════════════════════════
# REBA — Individual Component Scoring
# ══════════════════════════════════════════════════════════════════

def reba_neck(angle):
    if angle is None:
        return 1
    return 1 if angle <= 20 else 2


def reba_trunk(angle):
    if angle is None:
        return 1
    if angle <= 5:
        return 1
    elif angle <= 20:
        return 2
    elif angle <= 60:
        return 3
    else:
        return 4


def reba_legs(knee_angle=None):
    base = 1
    if knee_angle is None:
        return base
    if 30 <= knee_angle <= 60:
        return base + 1
    elif knee_angle > 60:
        return base + 2
    return base


def reba_upper_arm(angle):
    if angle is None:
        return 1
    if angle <= 20:
        return 1
    elif angle <= 45:
        return 2
    elif angle <= 90:
        return 3
    else:
        return 4


def reba_lower_arm(angle):
    if angle is None:
        return 1
    return 1 if 60 <= angle <= 100 else 2


def reba_wrist(angle):
    if angle is None:
        return 1
    return 1 if angle <= 15 else 2


# REBA Table A: (neck, trunk, legs) → score
_REBA_TABLE_A = {
    (1, 1, 1): 1, (1, 1, 2): 2, (1, 1, 3): 3, (1, 1, 4): 4,
    (1, 2, 1): 1, (1, 2, 2): 2, (1, 2, 3): 3, (1, 2, 4): 4,
    (1, 3, 1): 3, (1, 3, 2): 3, (1, 3, 3): 5, (1, 3, 4): 6,
    (1, 4, 1): 4, (1, 4, 2): 5, (1, 4, 3): 6, (1, 4, 4): 7,
    (2, 1, 1): 1, (2, 1, 2): 3, (2, 1, 3): 4, (2, 1, 4): 5,
    (2, 2, 1): 2, (2, 2, 2): 4, (2, 2, 3): 5, (2, 2, 4): 6,
    (2, 3, 1): 3, (2, 3, 2): 5, (2, 3, 3): 6, (2, 3, 4): 7,
    (2, 4, 1): 5, (2, 4, 2): 6, (2, 4, 3): 7, (2, 4, 4): 8,
    (3, 1, 1): 3, (3, 1, 2): 4, (3, 1, 3): 5, (3, 1, 4): 6,
    (3, 2, 1): 3, (3, 2, 2): 5, (3, 2, 3): 6, (3, 2, 4): 7,
    (3, 3, 1): 5, (3, 3, 2): 6, (3, 3, 3): 7, (3, 3, 4): 8,
    (3, 4, 1): 6, (3, 4, 2): 7, (3, 4, 3): 8, (3, 4, 4): 9,
}

# REBA Table B: (upper_arm, lower_arm, wrist) → score
_REBA_TABLE_B = {
    (1, 1, 1): 1, (1, 1, 2): 2, (1, 2, 1): 1, (1, 2, 2): 3,
    (2, 1, 1): 1, (2, 1, 2): 2, (2, 2, 1): 2, (2, 2, 2): 3,
    (3, 1, 1): 2, (3, 1, 2): 3, (3, 2, 1): 3, (3, 2, 2): 4,
    (4, 1, 1): 3, (4, 1, 2): 4, (4, 2, 1): 4, (4, 2, 2): 5,
}

# REBA Table C: A × B → final
_REBA_TABLE_C = [
    [1, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 7],      # A=1
    [1, 2, 2, 3, 4, 4, 5, 6, 6, 7, 7, 8],      # A=2
    [2, 3, 3, 3, 4, 5, 6, 7, 7, 8, 8, 8],      # A=3
    [3, 4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9],      # A=4
    [4, 4, 4, 5, 6, 7, 8, 8, 9, 10, 10, 10],   # A=5
    [6, 6, 6, 7, 8, 8, 9, 9, 10, 10, 10, 10],  # A=6
    [7, 7, 7, 8, 9, 9, 9, 10, 10, 11, 11, 11], # A=7
    [8, 8, 8, 9, 10, 10, 10, 10, 10, 11, 11, 11],  # A=8
    [9, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 12], # A=9
    [10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12],  # A=10
    [11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12],  # A=11
    [12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12],  # A=12
]


def compute_reba(angles, load_kg=0.0, coupling="good"):
    """
    Full REBA score from body angles.

    Returns dict with: score_a, score_b, final_score (1-15), risk_level, breakdown.
    """
    s_neck = reba_neck(angles.get("neck"))
    s_trunk = reba_trunk(angles.get("trunk"))
    s_legs = reba_legs(angles.get("knee"))

    key_a = (min(s_neck, 3), min(s_trunk, 4), min(s_legs, 4))
    score_a_raw = _REBA_TABLE_A.get(key_a, 7)

    if load_kg < 5:
        load_score = 0
    elif load_kg <= 10:
        load_score = 1
    else:
        load_score = 2
    score_a = min(score_a_raw + load_score, 12)

    s_upper = reba_upper_arm(angles.get("upper_arm"))
    s_lower = reba_lower_arm(angles.get("lower_arm"))
    s_wrist = reba_wrist(angles.get("wrist"))

    key_b = (min(s_upper, 4), min(s_lower, 2), min(s_wrist, 2))
    score_b_raw = _REBA_TABLE_B.get(key_b, 4)

    coupling_score = {"good": 0, "fair": 1, "poor": 2}.get(coupling, 1)
    score_b = min(score_b_raw + coupling_score, 12)

    idx_a = min(score_a, 12) - 1
    idx_b = min(score_b, 12) - 1
    score_c = _REBA_TABLE_C[idx_a][idx_b]
    final = min(score_c, 15)

    return {
        "score_a": score_a,
        "score_b": score_b,
        "final_score": final,
        "risk_level": _reba_risk_label(final),
        "breakdown": {
            "neck": s_neck,
            "trunk": s_trunk,
            "legs": s_legs,
            "upper_arm": s_upper,
            "lower_arm": s_lower,
            "wrist": s_wrist,
            "load_score": load_score,
            "coupling_score": coupling_score,
        },
    }


def _reba_risk_label(score):
    if score == 1:
        return "Negligible"
    elif score <= 3:
        return "Low Risk"
    elif score <= 7:
        return "Medium Risk"
    elif score <= 10:
        return "High Risk"
    else:
        return "VERY HIGH RISK"
