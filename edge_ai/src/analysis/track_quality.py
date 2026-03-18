"""
VisionSafe 360 — TrackQualityMonitor

Verifies ByteTrack tracking correctness and provides quality metrics:
  - track_coverage: % of detections that have a valid track_id
  - id_switches_per_min: estimated from abrupt ID changes
  - active_track_count: current number of active tracks
  - stable_tracks: tracks alive >= N frames

Also provides optional display-ID remapping (raw ByteTrack ID → small
sequential integer) for UI readability WITHOUT changing internal track_ids
used for cooldown/dedupe.

Note: ByteTrack IDs are NOT required to be sequential.  IDs like 1, 50, 243
are normal — they come from ByteTrack's internal counter that increments for
every new track across the entire session.  This does NOT indicate bugs.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..models.detection import Detection

logger = logging.getLogger(__name__)


class TrackQualityMonitor:
    """Monitors tracking quality and provides display-ID mapping."""

    def __init__(self, stable_frame_threshold: int = 10) -> None:
        self._stable_threshold = stable_frame_threshold

        # Per-track frame count
        self._track_frames: Dict[int, int] = defaultdict(int)
        # Per-track last-seen timestamp
        self._track_last_seen: Dict[int, float] = {}
        # Previous frame's track→centroid (for ID switch detection)
        self._prev_centroids: Dict[int, Tuple[float, float]] = {}

        # Display ID mapping: raw_id → display_id
        self._display_map: Dict[int, int] = {}
        self._next_display_id: int = 1
        # Pool of freed display IDs available for reuse
        self._free_display_ids: List[int] = []
        # Recently lost tracks: raw_id → (centroid, display_id, timestamp)
        self._lost_tracks: Dict[int, Tuple[Tuple[float, float], int, float]] = {}

        # Cumulative metrics
        self._total_detections: int = 0
        self._tracked_detections: int = 0
        self._id_switches: int = 0
        self._start_time: float = time.monotonic()

    def update(
        self,
        detections: List[Detection],
        timestamp: float,
    ) -> Dict[str, float]:
        """Process one frame's detections and return quality metrics.

        Returns dict with:
          track_coverage, id_switches_per_min, active_track_count,
          stable_track_count, total_detections
        """
        current_ids: set = set()
        current_centroids: Dict[int, Tuple[float, float]] = {}

        for det in detections:
            self._total_detections += 1
            if det.track_id is not None:
                self._tracked_detections += 1
                tid = det.track_id
                current_ids.add(tid)
                self._track_frames[tid] += 1
                self._track_last_seen[tid] = timestamp

                # Compute centroid
                x1, y1, x2, y2 = det.bbox
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                current_centroids[tid] = (cx, cy)

        # ID switch detection: if a track_id appears at a very different
        # position than last frame, it might be a switch.
        # We use a simple heuristic: check for tracks that disappeared
        # and new tracks that appeared in similar locations.
        prev_ids = set(self._prev_centroids.keys())
        disappeared = prev_ids - current_ids
        appeared = current_ids - prev_ids

        # Move disappeared tracks to lost pool (keep centroid + display ID)
        for old_id in disappeared:
            if old_id in self._prev_centroids and old_id in self._display_map:
                self._lost_tracks[old_id] = (
                    self._prev_centroids[old_id],
                    self._display_map[old_id],
                    timestamp,
                )

        # Re-ID: new tracks near recently-lost tracks inherit their display ID
        matched_new: set = set()
        if len(appeared) > 0 and len(self._lost_tracks) > 0:
            for new_id in appeared:
                if new_id not in current_centroids:
                    continue
                nc = current_centroids[new_id]
                best_old = None
                best_dist = 200.0  # max px distance for re-ID
                for lost_id, (lc, l_disp, l_ts) in self._lost_tracks.items():
                    if timestamp - l_ts > 30.0:  # too old
                        continue
                    dist = ((nc[0] - lc[0]) ** 2 + (nc[1] - lc[1]) ** 2) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_old = lost_id
                if best_old is not None:
                    # Inherit the display ID from the lost track
                    _, old_disp, _ = self._lost_tracks.pop(best_old)
                    self._display_map[new_id] = old_disp
                    matched_new.add(new_id)
                    logger.debug(
                        "Re-ID: new track %d inherits display D%d from lost track %d (dist=%.0fpx)",
                        new_id, old_disp, best_old, best_dist,
                    )

        # ID switch detection for unmatched appear/disappear pairs
        if len(disappeared) > 0 and len(appeared - matched_new) > 0:
            for new_id in (appeared - matched_new):
                if new_id not in current_centroids:
                    continue
                nc = current_centroids[new_id]
                for old_id in disappeared:
                    if old_id not in self._prev_centroids:
                        continue
                    oc = self._prev_centroids[old_id]
                    dist = ((nc[0] - oc[0]) ** 2 + (nc[1] - oc[1]) ** 2) ** 0.5
                    if dist < 100:
                        self._id_switches += 1
                        break

        self._prev_centroids = current_centroids

        # Purge stale lost tracks (> 30s)
        stale_lost = [
            tid for tid, (_, _, ts) in self._lost_tracks.items()
            if timestamp - ts > 30.0
        ]
        for tid in stale_lost:
            _, disp, _ = self._lost_tracks.pop(tid)
            self._free_display_ids.append(disp)

        # Purge stale active tracks (not seen for > 10s)
        stale = [
            tid for tid, ts in self._track_last_seen.items()
            if timestamp - ts > 10.0
        ]
        for tid in stale:
            self._track_last_seen.pop(tid, None)
            self._track_frames.pop(tid, None)
            disp = self._display_map.pop(tid, None)
            if disp is not None and tid not in self._lost_tracks:
                self._free_display_ids.append(disp)

        # Compute metrics
        elapsed_min = (time.monotonic() - self._start_time) / 60.0
        active = len(self._track_last_seen)
        stable = sum(
            1 for tid, fc in self._track_frames.items()
            if fc >= self._stable_threshold and tid in self._track_last_seen
        )

        coverage = (
            self._tracked_detections / self._total_detections * 100.0
            if self._total_detections > 0
            else 0.0
        )
        switches_per_min = (
            self._id_switches / elapsed_min if elapsed_min > 0.01 else 0.0
        )

        return {
            "track_coverage": round(coverage, 1),
            "id_switches_per_min": round(switches_per_min, 2),
            "active_track_count": active,
            "stable_track_count": stable,
            "total_detections": self._total_detections,
        }

    def get_display_id(self, raw_track_id: int) -> int:
        """Map a raw ByteTrack ID to a small sequential display ID.

        Recycles freed display IDs so numbers stay compact (1..N).
        """
        if raw_track_id not in self._display_map:
            if self._free_display_ids:
                self._free_display_ids.sort()
                self._display_map[raw_track_id] = self._free_display_ids.pop(0)
            else:
                self._display_map[raw_track_id] = self._next_display_id
                self._next_display_id += 1
        return self._display_map[raw_track_id]

    def remap_detections_display_ids(
        self, detections: List[Detection]
    ) -> Dict[int, int]:
        """Return a mapping of raw_track_id → display_id for all detections.

        Does NOT modify the Detection objects (track_id stays raw for cooldown/dedupe).
        """
        mapping: Dict[int, int] = {}
        for det in detections:
            if det.track_id is not None:
                mapping[det.track_id] = self.get_display_id(det.track_id)
        return mapping

    def summary(self) -> str:
        """Human-readable tracking quality summary."""
        elapsed = time.monotonic() - self._start_time
        coverage = (
            self._tracked_detections / self._total_detections * 100.0
            if self._total_detections > 0
            else 0.0
        )
        return (
            f"Track Quality Report:\n"
            f"  Duration: {elapsed:.0f}s\n"
            f"  Total detections: {self._total_detections}\n"
            f"  Tracked detections: {self._tracked_detections}\n"
            f"  Coverage: {coverage:.1f}%\n"
            f"  ID switches: {self._id_switches}\n"
            f"  Switches/min: {self._id_switches / max(elapsed / 60, 0.01):.2f}\n"
            f"  Active tracks: {len(self._track_last_seen)}\n"
            f"  Stable tracks (>={self._stable_threshold} frames): "
            f"{sum(1 for fc in self._track_frames.values() if fc >= self._stable_threshold)}\n"
        )

    def snapshot(self) -> Dict[str, float]:
        """Structured cumulative tracking metrics for reports."""
        elapsed = time.monotonic() - self._start_time
        coverage = (
            self._tracked_detections / self._total_detections * 100.0
            if self._total_detections > 0
            else 0.0
        )
        return {
            "duration_sec": round(elapsed, 1),
            "total_detections": float(self._total_detections),
            "tracked_detections": float(self._tracked_detections),
            "track_coverage": round(coverage, 1),
            "id_switches": float(self._id_switches),
            "active_tracks": float(len(self._track_last_seen)),
        }
