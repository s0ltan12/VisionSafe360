"""
scoring.py
----------
Full RULA and REBA scoring algorithms based on:
  - RULA: McAtamney & Corlett (1993), Applied Ergonomics 24(2), pp. 91-99
  - REBA: Hignett & McAtamney (2000), Applied Ergonomics 31(2), pp. 201-205

Each function takes body angles (in degrees) and returns an integer score.
None angles are handled gracefully — they default to a neutral (score=1) value
so the pipeline never crashes on partial detections.
"""

# ══════════════════════════════════════════════════════════════════════════════
# RULA
# ══════════════════════════════════════════════════════════════════════════════

def rula_upper_arm(angle):
    """
    Upper arm flexion / extension.
    0-20°  -> 1   20-45° -> 2   45-90° -> 3   >90° -> 4
    +1 if shoulder is raised (detected externally)
    +1 if upper arm is abducted
    -1 if arm is supported / gravity-assisted
    """
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
    """
    Elbow flexion.
    60-100° -> 1   otherwise -> 2
    +1 if arm crosses midline or works out to side
    """
    if angle is None:
        return 1
    if 60 <= angle <= 100:
        return 1
    else:
        return 2


def rula_wrist(angle):
    """
    Wrist flexion / extension.
    0°     -> 1 (neutral)
    0-15°  -> 2
    >15°   -> 3
    +1 if wrist is bent from midline
    """
    if angle is None:
        return 1
    if angle == 0:
        return 1
    elif angle <= 15:
        return 2
    else:
        return 3


def rula_wrist_twist():
    """
    Wrist twist (pronation / supination).
    Cannot be measured from COCO 17 keypoints.
    Defaults to mid-range = 1 (conservative neutral assumption).
    """
    return 1


def rula_neck(angle):
    """
    Neck flexion.
    0-10°  -> 1   10-20° -> 2   >20° -> 3
    +1 if neck is extended (tilted back)
    +1 if neck is side-bending or rotated
    """
    if angle is None:
        return 1
    if angle <= 10:
        return 1
    elif angle <= 20:
        return 2
    else:
        return 3


def rula_trunk(angle):
    """
    Trunk flexion.
    0-10°  -> 1   10-20° -> 2   20-60° -> 3   >60° -> 4
    +1 if trunk is twisted
    +1 if trunk is side-bending
    """
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
    """
    Leg and foot support.
    1 = legs and feet are well supported and balanced.
    2 = not supported or uneven.
    Default: assume supported (most common industrial scenario).
    """
    return 1 if supported else 2


# RULA Table A: upper limb posture (upper arm x lower arm x wrist x wrist twist)
# Source: McAtamney & Corlett (1993), Table 1
_RULA_TABLE_A = {
    # (upper_arm, lower_arm, wrist_score): [twist1, twist2]
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

# RULA Table B: postural score for neck, trunk and leg
# Source: McAtamney & Corlett (1993), Table 2
_RULA_TABLE_B = {
    # (neck, trunk, legs): score
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

# RULA Table C: final score from Group A and Group B
# Source: McAtamney & Corlett (1993), Table 3
_RULA_TABLE_C = [
    #  B: 1  2  3  4  5  6  7
       [1, 2, 3, 3, 4, 5, 5],  # A=1
       [2, 2, 3, 4, 4, 5, 5],  # A=2
       [3, 3, 3, 4, 4, 5, 6],  # A=3
       [3, 3, 3, 4, 5, 6, 6],  # A=4
       [4, 4, 4, 5, 6, 7, 7],  # A=5
       [4, 4, 5, 6, 6, 7, 7],  # A=6
       [5, 5, 6, 6, 7, 7, 7],  # A=7
]


def compute_rula(angles,
                 muscle_use=False,
                 load_kg=0.0,
                 static_posture=False):
    """
    Computes the full RULA score.

    Parameters
    ----------
    angles       : dict from angles.compute_angles()
    muscle_use   : True if posture is held > 1 min or repeated > 4x/min
    load_kg      : weight being handled in kg
    static_posture: True if posture is static (same as muscle_use in many cases)

    Returns
    -------
    dict with:
        score_a      : Group A score (upper limbs)
        score_b      : Group B score (neck / trunk / legs)
        final_score  : RULA score 1-7
        risk_level   : string description
        breakdown    : per-component scores
    """
    # --- individual component scores ---
    s_upper_arm  = rula_upper_arm(angles.get("upper_arm"))
    s_lower_arm  = rula_lower_arm(angles.get("lower_arm"))
    s_wrist      = rula_wrist(angles.get("wrist"))
    s_wrist_twist= rula_wrist_twist()
    s_neck       = rula_neck(angles.get("neck"))
    s_trunk      = rula_trunk(angles.get("trunk"))
    s_legs       = rula_legs()

    # --- muscle use adjustment (+1 if static or repetitive) ---
    muscle_adj = 1 if (muscle_use or static_posture) else 0

    # --- load / force score ---
    if load_kg < 2:
        load_score = 0
    elif load_kg <= 10:
        load_score = 1
    else:
        load_score = 2

    # --- Group A: look up in Table A ---
    key_a = (
        min(s_upper_arm, 4),
        min(s_lower_arm, 3),
        min(s_wrist, 3)
    )
    table_a_vals = _RULA_TABLE_A.get(key_a, [4, 4])
    score_a_raw  = table_a_vals[s_wrist_twist - 1]
    score_a      = min(score_a_raw + muscle_adj + load_score, 8)

    # --- Group B: look up in Table B ---
    trunk_capped = min(s_trunk, 6)
    key_b        = (min(s_neck, 4), trunk_capped, min(s_legs, 2))
    score_b_raw  = _RULA_TABLE_B.get(key_b, 5)
    score_b      = min(score_b_raw + muscle_adj + load_score, 8)

    # --- Table C: final score ---
    idx_a = min(score_a, 7) - 1
    idx_b = min(score_b, 7) - 1
    final = _RULA_TABLE_C[idx_a][idx_b]

    return {
        "score_a":     score_a,
        "score_b":     score_b,
        "final_score": final,
        "risk_level":  _rula_risk_label(final),
        "breakdown": {
            "upper_arm":   s_upper_arm,
            "lower_arm":   s_lower_arm,
            "wrist":       s_wrist,
            "neck":        s_neck,
            "trunk":       s_trunk,
            "legs":        s_legs,
            "muscle_adj":  muscle_adj,
            "load_score":  load_score,
        }
    }


def _rula_risk_label(score):
    if score <= 2:
        return "Acceptable"
    elif score <= 4:
        return "Low Risk — Review Soon"
    elif score <= 6:
        return "Medium Risk — Investigate"
    else:
        return "HIGH RISK — Change Immediately"


# ══════════════════════════════════════════════════════════════════════════════
# REBA
# ══════════════════════════════════════════════════════════════════════════════

def reba_neck(angle):
    if angle is None: return 1
    return 1 if angle <= 20 else 2


def reba_trunk(angle):
    if angle is None: return 1
    if angle <= 5:   return 1
    elif angle <= 20: return 2
    elif angle <= 60: return 3
    else:             return 4


def reba_legs(knee_angle=None, walking=False):
    """
    1 = bilateral weight bearing / walking / sitting
    2 = unilateral, unstable or large flexion
    +1 if knee flexion 30-60°
    +2 if knee flexion > 60°
    """
    base = 1 if not walking else 1
    if knee_angle is None:
        return base
    if 30 <= knee_angle <= 60:
        return base + 1
    elif knee_angle > 60:
        return base + 2
    return base


def reba_upper_arm(angle):
    if angle is None: return 1
    if angle <= 20:  return 1
    elif angle <= 45: return 2
    elif angle <= 90: return 3
    else:             return 4


def reba_lower_arm(angle):
    if angle is None: return 1
    return 1 if 60 <= angle <= 100 else 2


def reba_wrist(angle):
    if angle is None: return 1
    return 1 if angle <= 15 else 2


# REBA Table A: neck x trunk x legs
_REBA_TABLE_A = {
    (1,1,1):1,(1,1,2):2,(1,1,3):3,(1,1,4):4,
    (1,2,1):1,(1,2,2):2,(1,2,3):3,(1,2,4):4,
    (1,3,1):3,(1,3,2):3,(1,3,3):5,(1,3,4):6,
    (1,4,1):4,(1,4,2):5,(1,4,3):6,(1,4,4):7,
    (2,1,1):1,(2,1,2):3,(2,1,3):4,(2,1,4):5,
    (2,2,1):2,(2,2,2):4,(2,2,3):5,(2,2,4):6,
    (2,3,1):3,(2,3,2):5,(2,3,3):6,(2,3,4):7,
    (2,4,1):5,(2,4,2):6,(2,4,3):7,(2,4,4):8,
    (3,1,1):3,(3,1,2):4,(3,1,3):5,(3,1,4):6,
    (3,2,1):3,(3,2,2):5,(3,2,3):6,(3,2,4):7,
    (3,3,1):5,(3,3,2):6,(3,3,3):7,(3,3,4):8,
    (3,4,1):6,(3,4,2):7,(3,4,3):8,(3,4,4):9,
}

# REBA Table B: upper arm x lower arm x wrist
_REBA_TABLE_B = {
    (1,1,1):1,(1,1,2):2,(1,2,1):1,(1,2,2):3,
    (2,1,1):1,(2,1,2):2,(2,2,1):2,(2,2,2):3,
    (3,1,1):2,(3,1,2):3,(3,2,1):3,(3,2,2):4,
    (4,1,1):3,(4,1,2):4,(4,2,1):4,(4,2,2):5,
}

# REBA Table C: score A x score B -> final score
_REBA_TABLE_C = [
    # B:  1   2   3   4   5   6   7   8   9  10  11  12
         [1,  1,  1,  2,  3,  3,  4,  5,  6,  7,  7,  7],  # A=1
         [1,  2,  2,  3,  4,  4,  5,  6,  6,  7,  7,  8],  # A=2
         [2,  3,  3,  3,  4,  5,  6,  7,  7,  8,  8,  8],  # A=3
         [3,  4,  4,  4,  5,  6,  7,  8,  8,  9,  9,  9],  # A=4
         [4,  4,  4,  5,  6,  7,  8,  8,  9, 10, 10, 10],  # A=5
         [6,  6,  6,  7,  8,  8,  9,  9, 10, 10, 10, 10],  # A=6
         [7,  7,  7,  8,  9,  9,  9, 10, 10, 11, 11, 11],  # A=7
         [8,  8,  8,  9, 10, 10, 10, 10, 10, 11, 11, 11],  # A=8
         [9,  9,  9, 10, 10, 10, 11, 11, 11, 12, 12, 12],  # A=9
         [10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12], # A=10
         [11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12], # A=11
         [12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12], # A=12
]


def compute_reba(angles,
                 load_kg=0.0,
                 coupling="good",
                 activity_static=False,
                 activity_repeated=False,
                 activity_rapid=False):
    """
    Computes the full REBA score.

    Parameters
    ----------
    angles           : dict from angles.compute_angles()
    load_kg          : weight being handled in kg
    coupling         : "good" | "fair" | "poor"
    activity_static  : True if posture held > 1 min
    activity_repeated: True if action repeated > 4x/min
    activity_rapid   : True if rapid large range of motion changes

    Returns
    -------
    dict with final_score (1-15), risk_level, breakdown
    """
    # --- Group A: neck, trunk, legs ---
    s_neck  = reba_neck(angles.get("neck"))
    s_trunk = reba_trunk(angles.get("trunk"))
    s_legs  = reba_legs(angles.get("knee"))

    key_a   = (min(s_neck,3), min(s_trunk,4), min(s_legs,4))
    score_a_raw = _REBA_TABLE_A.get(key_a, 7)

    # load score
    if load_kg < 5:      load_score = 0
    elif load_kg <= 10:  load_score = 1
    else:                load_score = 2

    score_a = min(score_a_raw + load_score, 12)

    # --- Group B: upper arm, lower arm, wrist ---
    s_upper = reba_upper_arm(angles.get("upper_arm"))
    s_lower = reba_lower_arm(angles.get("lower_arm"))
    s_wrist = reba_wrist(angles.get("wrist"))

    key_b   = (min(s_upper,4), min(s_lower,2), min(s_wrist,2))
    score_b_raw = _REBA_TABLE_B.get(key_b, 4)

    # coupling score
    coupling_score = {"good": 0, "fair": 1, "poor": 2}.get(coupling, 1)
    score_b = min(score_b_raw + coupling_score, 12)

    # --- Activity score ---
    activity_score = sum([activity_static, activity_repeated, activity_rapid])

    # --- Table C ---
    idx_a  = min(score_a, 12) - 1
    idx_b  = min(score_b, 12) - 1
    score_c = _REBA_TABLE_C[idx_a][idx_b]
    final   = min(score_c + activity_score, 15)

    return {
        "score_a":     score_a,
        "score_b":     score_b,
        "final_score": final,
        "risk_level":  _reba_risk_label(final),
        "breakdown": {
            "neck":           s_neck,
            "trunk":          s_trunk,
            "legs":           s_legs,
            "upper_arm":      s_upper,
            "lower_arm":      s_lower,
            "wrist":          s_wrist,
            "load_score":     load_score,
            "coupling_score": coupling_score,
            "activity_score": activity_score,
        }
    }


def _reba_risk_label(score):
    if score == 1:
        return "Negligible"
    elif score <= 3:
        return "Low Risk"
    elif score <= 7:
        return "Medium Risk — Investigate"
    elif score <= 10:
        return "High Risk — Investigate Soon"
    else:
        return "VERY HIGH RISK — Implement Change"
