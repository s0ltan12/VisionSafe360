"""Temporal smoothing for detection and tracking stability.

Extracted from main.py — preserves original algorithms unchanged.
"""


class DetectionSmoother:
    """Persist last-known bboxes for tracked persons to fill brief detection gaps.

    Handles two flickering scenarios:
    1. Person is detected but ByteTrack fails to assign a track_id on some
       frames → match untracked bbox to cached tracked bbox by IoU and
       reassign the track_id.
    2. Person disappears entirely for up to *grace_frames* → inject a
       'ghost' detection at the last known bbox.
    """

    def __init__(self, grace_frames: int = 5) -> None:
        self._grace = grace_frames
        # track_id → (Detection, frames_since_last_seen)
        self._cache: dict = {}

    @staticmethod
    def _iou(b1, b2) -> float:
        xa = max(b1[0], b2[0]); ya = max(b1[1], b2[1])
        xb = min(b1[2], b2[2]); yb = min(b1[3], b2[3])
        inter = max(0, xb - xa) * max(0, yb - ya)
        a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0.0

    def smooth(self, detections: list) -> list:
        # --- Phase 1: recover untracked detections ---
        # When a person is detected but has no track_id, try to match it
        # to a recently-tracked person by bbox IoU.
        for det in detections:
            if det.track_id is not None or det.class_name != "person":
                continue
            best_tid, best_iou = None, 0.3  # minimum IoU threshold
            for tid, (cached_det, _age) in self._cache.items():
                iou = self._iou(det.bbox, cached_det.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid
            if best_tid is not None:
                det.track_id = best_tid

        current_ids = {d.track_id for d in detections if d.track_id is not None}

        # Update cache with current detections
        for det in detections:
            if det.track_id is not None:
                self._cache[det.track_id] = (det, 0)

        # --- Phase 2: inject ghosts for fully missing tracks ---
        ghosts = []
        stale = []
        for tid, (cached_det, age) in self._cache.items():
            if tid in current_ids:
                continue
            new_age = age + 1
            if new_age <= self._grace:
                self._cache[tid] = (cached_det, new_age)
                ghosts.append(cached_det)
            else:
                stale.append(tid)

        for tid in stale:
            del self._cache[tid]

        return detections + ghosts


class ForkliftHoldSmoother:
    """Temporal hold for forklift detections to reduce flicker on skipped frames.

    Important: this smoother is applied only to proximity analyzer input and UI
    rendering flow. Raw model detections are preserved separately.
    """

    def __init__(self, hold_frames: int = 5) -> None:
        self._hold_frames = max(0, int(hold_frames))
        self._remaining = 0
        self._cached_forklifts: list = []

    def smooth(self, raw_proximity_detections: list) -> tuple[list, bool]:
        persons = [d for d in raw_proximity_detections if d.class_name == "person"]
        forklifts = [d for d in raw_proximity_detections if d.class_name == "forklift"]

        used_hold = False
        if forklifts:
            self._cached_forklifts = forklifts
            self._remaining = self._hold_frames
        elif self._remaining > 0 and self._cached_forklifts:
            forklifts = self._cached_forklifts
            self._remaining -= 1
            used_hold = True
        else:
            self._cached_forklifts = []
            self._remaining = 0

        return persons + forklifts, used_hold
