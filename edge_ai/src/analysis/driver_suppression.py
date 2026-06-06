"""Geometric forklift driver/operator suppression.

This module intentionally avoids ML retraining.  It uses only current person
and forklift detections plus track IDs when available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..config.settings import (
    DRIVER_SUPPRESSION_ASSIGN_SEC,
    DRIVER_SUPPRESSION_CABIN_OVERLAP_RATIO,
    DRIVER_SUPPRESSION_CANDIDATE_SEC,
    DRIVER_SUPPRESSION_EXIT_SEC,
    DRIVER_SUPPRESSION_OCCLUSION_TIMEOUT_SEC,
    DRIVER_SUPPRESSION_STRONG_OVERLAP_RATIO,
)
from ..models.detection import Detection

BBox = Tuple[int, int, int, int]


@dataclass(slots=True)
class DriverSuppressionConfig:
    strong_overlap_ratio: float = DRIVER_SUPPRESSION_STRONG_OVERLAP_RATIO
    cabin_overlap_ratio: float = DRIVER_SUPPRESSION_CABIN_OVERLAP_RATIO
    candidate_sec: float = DRIVER_SUPPRESSION_CANDIDATE_SEC
    assign_sec: float = DRIVER_SUPPRESSION_ASSIGN_SEC
    occlusion_timeout_sec: float = DRIVER_SUPPRESSION_OCCLUSION_TIMEOUT_SEC
    exit_sec: float = DRIVER_SUPPRESSION_EXIT_SEC


@dataclass(slots=True)
class DriverSuppressionResult:
    driver_suppressed: bool
    driver_candidate: bool
    driver_assigned: bool
    reason: str
    person_track_id: Optional[int]
    forklift_track_id: Optional[int]
    overlap_ratio: float
    cabin_overlap_ratio: float

    def metadata(self) -> dict:
        return {
            "driver_suppressed": self.driver_suppressed,
            "driver_candidate": self.driver_candidate,
            "driver_assigned": self.driver_assigned,
            "driver_suppression_reason": self.reason,
            "driver_overlap_ratio": round(self.overlap_ratio, 3),
            "driver_cabin_overlap_ratio": round(self.cabin_overlap_ratio, 3),
        }


@dataclass(slots=True)
class _DriverState:
    first_seen: float
    last_seen: float
    assigned: bool = False
    exit_since: Optional[float] = None


class DriverSuppression:
    """Stateful non-ML driver suppression for forklift proximity events."""

    def __init__(self, config: DriverSuppressionConfig | None = None) -> None:
        self.config = config or DriverSuppressionConfig()
        self._states: Dict[tuple, _DriverState] = {}

    def evaluate(
        self,
        person: Detection,
        forklift: Detection,
        timestamp: float,
    ) -> DriverSuppressionResult:
        self._purge(timestamp)

        overlap = _overlap_ratio(person.bbox, forklift.bbox)
        cabin = _cabin_roi(forklift.bbox)
        cabin_overlap = _overlap_ratio(person.bbox, cabin)
        center_inside = _contains_point(forklift.bbox, _center(person.bbox))
        bottom_inside = _contains_point(forklift.bbox, _bottom_center(person.bbox))
        cabin_center_inside = _contains_point(cabin, _center(person.bbox))

        strong_overlap = (
            overlap >= self.config.strong_overlap_ratio
            and (center_inside or bottom_inside)
        )
        cabin_signal = (
            cabin_center_inside
            or cabin_overlap >= self.config.cabin_overlap_ratio
        )
        inside_signal = strong_overlap or cabin_signal

        key = self._state_key(person, forklift)
        state = self._states.get(key)
        if state is None and inside_signal:
            state = _DriverState(first_seen=timestamp, last_seen=timestamp)
            self._states[key] = state

        if state is not None:
            if inside_signal:
                state.last_seen = timestamp
                state.exit_since = None
                if timestamp - state.first_seen >= self.config.assign_sec:
                    state.assigned = True
            else:
                if state.assigned:
                    if state.exit_since is None:
                        state.exit_since = timestamp
                    elif timestamp - state.exit_since >= self.config.exit_sec:
                        state.assigned = False
                        self._states.pop(key, None)
                        state = None

        candidate = bool(
            state is not None
            and timestamp - state.first_seen >= self.config.candidate_sec
        )
        assigned = bool(state is not None and state.assigned)

        suppressed = False
        reason = ""
        if strong_overlap:
            suppressed = True
            reason = "strong_overlap"
        elif cabin_signal:
            suppressed = True
            reason = "cabin_roi"
        elif assigned:
            suppressed = True
            reason = "assigned_driver"
        elif candidate:
            reason = "driver_candidate"

        return DriverSuppressionResult(
            driver_suppressed=suppressed,
            driver_candidate=candidate,
            driver_assigned=assigned,
            reason=reason,
            person_track_id=person.track_id,
            forklift_track_id=forklift.track_id,
            overlap_ratio=overlap,
            cabin_overlap_ratio=cabin_overlap,
        )

    def _purge(self, timestamp: float) -> None:
        stale = [
            key for key, state in self._states.items()
            if timestamp - state.last_seen > self.config.occlusion_timeout_sec
        ]
        for key in stale:
            self._states.pop(key, None)

    @staticmethod
    def _state_key(person: Detection, forklift: Detection) -> tuple:
        person_key = person.track_id
        if person_key is None:
            person_key = ("person_bbox", _quantized_center(person.bbox))
        forklift_key = forklift.track_id
        if forklift_key is None:
            forklift_key = ("forklift_bbox", _quantized_center(forklift.bbox))
        return forklift_key, person_key


def _center(bbox: BBox) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _bottom_center(bbox: BBox) -> tuple[float, float]:
    x1, _y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, float(y2))


def _contains_point(bbox: BBox, pt: tuple[float, float]) -> bool:
    x, y = pt
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _overlap_ratio(subject: BBox, container: BBox) -> float:
    ix1 = max(subject[0], container[0])
    iy1 = max(subject[1], container[1])
    ix2 = min(subject[2], container[2])
    iy2 = min(subject[3], container[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area = max(1, (subject[2] - subject[0]) * (subject[3] - subject[1]))
    return inter / area


def _cabin_roi(forklift_bbox: BBox) -> BBox:
    x1, y1, x2, y2 = forklift_bbox
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    return (
        int(round(x1 + 0.18 * w)),
        int(round(y1 + 0.05 * h)),
        int(round(x1 + 0.82 * w)),
        int(round(y1 + 0.78 * h)),
    )


def _quantized_center(bbox: BBox) -> tuple[int, int]:
    cx, cy = _center(bbox)
    return int(round(cx / 25.0) * 25), int(round(cy / 25.0) * 25)
