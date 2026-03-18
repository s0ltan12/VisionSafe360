"""
tracker.py
----------
Tracks how long each worker has been holding a risky posture.

Key insight: a 70-degree trunk bend for 0.5 seconds is NOT a hazard.
The same posture held for 10+ seconds IS a hazard.

This module maintains per-worker duration counters and only triggers
alerts when both score AND duration thresholds are exceeded.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional


# ── alert configuration ────────────────────────────────────────────────────────
RULA_ALERT_THRESHOLD    = 5      # RULA score that triggers monitoring
REBA_ALERT_THRESHOLD    = 7      # REBA score that triggers monitoring
SUSTAINED_DURATION_SEC  = 3.0    # seconds a bad posture must be held to alert
RESET_GRACE_SEC         = 2.0    # seconds of good posture before counter resets


@dataclass
class WorkerState:
    worker_id:        int
    rula_score:       Optional[int]   = None
    reba_score:       Optional[int]   = None
    rula_risk:        str             = "Unknown"
    reba_risk:        str             = "Unknown"

    # duration tracking
    bad_posture_start: Optional[float] = None   # timestamp when bad posture began
    good_posture_start: Optional[float] = None  # timestamp when recovery began
    sustained_duration: float          = 0.0    # total seconds in bad posture
    alert_active:       bool           = False

    # smoothed angles (for display)
    angles: Dict = field(default_factory=dict)


class PostureTracker:
    """
    One instance per camera / scene.
    Tracks multiple workers simultaneously by their YOLO detection index.
    """

    def __init__(self,
                 rula_threshold=RULA_ALERT_THRESHOLD,
                 reba_threshold=REBA_ALERT_THRESHOLD,
                 duration_sec=SUSTAINED_DURATION_SEC,
                 grace_sec=RESET_GRACE_SEC):
        self.rula_threshold = rula_threshold
        self.reba_threshold = reba_threshold
        self.duration_sec   = duration_sec
        self.grace_sec      = grace_sec
        self.workers: Dict[int, WorkerState] = {}

    # ── main update ────────────────────────────────────────────────────────────
    def update(self, worker_id: int, rula_result: dict, reba_result: dict,
               smoothed_angles: dict) -> WorkerState:
        """
        Called every frame for each detected worker.

        Returns the updated WorkerState including alert status.
        """
        now = time.monotonic()

        if worker_id not in self.workers:
            self.workers[worker_id] = WorkerState(worker_id=worker_id)

        state = self.workers[worker_id]
        state.rula_score = rula_result["final_score"]
        state.reba_score = reba_result["final_score"]
        state.rula_risk  = rula_result["risk_level"]
        state.reba_risk  = reba_result["risk_level"]
        state.angles     = smoothed_angles

        is_risky = (state.rula_score >= self.rula_threshold or
                    state.reba_score >= self.reba_threshold)

        if is_risky:
            # start or continue bad posture timer
            state.good_posture_start = None
            if state.bad_posture_start is None:
                state.bad_posture_start = now
            state.sustained_duration = now - state.bad_posture_start

            if state.sustained_duration >= self.duration_sec:
                state.alert_active = True
        else:
            # start recovery timer
            if state.good_posture_start is None:
                state.good_posture_start = now

            if now - state.good_posture_start >= self.grace_sec:
                # worker has recovered — reset everything
                state.bad_posture_start  = None
                state.sustained_duration = 0.0
                state.alert_active       = False

        return state

    def remove_worker(self, worker_id: int):
        """Call when a worker leaves the frame."""
        self.workers.pop(worker_id, None)

    def get_active_alerts(self):
        """Returns list of WorkerState objects currently in alert."""
        return [s for s in self.workers.values() if s.alert_active]

    def summary(self):
        """Quick text summary for logging."""
        lines = []
        for wid, s in self.workers.items():
            lines.append(
                f"  Worker {wid}: RULA={s.rula_score} ({s.rula_risk}) | "
                f"REBA={s.reba_score} ({s.reba_risk}) | "
                f"Duration={s.sustained_duration:.1f}s | Alert={s.alert_active}"
            )
        return "\n".join(lines) if lines else "  No workers tracked."
