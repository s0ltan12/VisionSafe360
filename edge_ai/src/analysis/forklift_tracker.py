"""Lightweight forklift tracker for proximity detections.

The current proximity detector runs in predict mode, so forklift detections do
not have persistent IDs.  This tracker performs inexpensive bbox association
and short lost-track recovery while preserving externally supplied IDs when
available.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..config.settings import (
    FORKLIFT_TRACK_MATCH_IOU,
    FORKLIFT_TRACK_MAX_CENTER_DISTANCE_PX,
    FORKLIFT_TRACK_MAX_LOST_FRAMES,
)
from ..models.detection import Detection

BBox = Tuple[int, int, int, int]


@dataclass(slots=True)
class ForkliftTrack:
    track_id: int
    bbox: BBox
    bottom_center: tuple[float, float]
    confidence: float
    age: int
    lost_frames: int
    timestamp: float

    @property
    def is_active(self) -> bool:
        return self.lost_frames == 0


@dataclass(slots=True)
class ForkliftTrackerConfig:
    max_lost_frames: int = FORKLIFT_TRACK_MAX_LOST_FRAMES
    match_iou: float = FORKLIFT_TRACK_MATCH_IOU
    max_center_distance_px: float = FORKLIFT_TRACK_MAX_CENTER_DISTANCE_PX


class ForkliftTracker:
    """Assign and maintain persistent forklift track IDs."""

    def __init__(self, config: Optional[ForkliftTrackerConfig] = None) -> None:
        self.config = config or ForkliftTrackerConfig()
        self._tracks: Dict[int, ForkliftTrack] = {}
        self._next_track_id = 1

    def update(self, detections: List[Detection], timestamp: float) -> List[ForkliftTrack]:
        forklifts = [d for d in detections if d.class_name == "forklift"]
        matched_track_ids: set[int] = set()
        matched_det_ids: set[int] = set()

        for det_idx, det in enumerate(forklifts):
            if det.track_id is not None and det.track_id in self._tracks:
                self._update_track(self._tracks[det.track_id], det, timestamp)
                matched_track_ids.add(det.track_id)
                matched_det_ids.add(det_idx)

        candidates: list[tuple[float, int, int]] = []
        for det_idx, det in enumerate(forklifts):
            if det_idx in matched_det_ids:
                continue
            for tid, track in self._tracks.items():
                if tid in matched_track_ids:
                    continue
                score = self._match_score(det.bbox, track)
                if score is not None:
                    candidates.append((score, det_idx, tid))

        for _score, det_idx, tid in sorted(candidates, reverse=True):
            if det_idx in matched_det_ids or tid in matched_track_ids:
                continue
            det = forklifts[det_idx]
            det.track_id = tid
            self._update_track(self._tracks[tid], det, timestamp)
            matched_track_ids.add(tid)
            matched_det_ids.add(det_idx)

        for det_idx, det in enumerate(forklifts):
            if det_idx in matched_det_ids:
                continue
            tid = int(det.track_id) if det.track_id is not None else self._allocate_track_id()
            self._next_track_id = max(self._next_track_id, tid + 1)
            det.track_id = tid
            self._tracks[tid] = ForkliftTrack(
                track_id=tid,
                bbox=det.bbox,
                bottom_center=_bottom_center(det.bbox),
                confidence=det.confidence,
                age=1,
                lost_frames=0,
                timestamp=timestamp,
            )
            matched_track_ids.add(tid)

        for tid in list(self._tracks):
            if tid in matched_track_ids:
                continue
            track = self._tracks[tid]
            track.lost_frames += 1
            if track.lost_frames > self.config.max_lost_frames:
                self._tracks.pop(tid, None)

        return [track for track in self._tracks.values() if track.is_active]

    def get(self, track_id: int | None) -> Optional[ForkliftTrack]:
        if track_id is None:
            return None
        return self._tracks.get(track_id)

    @property
    def tracks(self) -> dict[int, ForkliftTrack]:
        return dict(self._tracks)

    def _allocate_track_id(self) -> int:
        tid = self._next_track_id
        self._next_track_id += 1
        return tid

    def _update_track(self, track: ForkliftTrack, det: Detection, timestamp: float) -> None:
        track.bbox = det.bbox
        track.bottom_center = _bottom_center(det.bbox)
        track.confidence = det.confidence
        track.age += 1
        track.lost_frames = 0
        track.timestamp = timestamp

    def _match_score(self, bbox: BBox, track: ForkliftTrack) -> Optional[float]:
        iou = _iou(bbox, track.bbox)
        distance = _distance(_center(bbox), _center(track.bbox))
        if iou < self.config.match_iou and distance > self.config.max_center_distance_px:
            return None
        distance_score = max(0.0, 1.0 - distance / max(1.0, self.config.max_center_distance_px))
        lost_penalty = min(track.lost_frames, self.config.max_lost_frames) * 0.03
        return iou * 2.0 + distance_score - lost_penalty


def _center(bbox: BBox) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _bottom_center(bbox: BBox) -> tuple[float, float]:
    x1, _y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, float(y2))


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _iou(a: BBox, b: BBox) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
