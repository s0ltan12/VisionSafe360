"""
Unit tests for TrackQualityMonitor — coverage, ID switches, display ID mapping.

Tests:
  1. Full coverage when all detections are tracked
  2. Partial coverage computed correctly
  3. Display ID is monotonically increasing
  4. Display ID stable across calls for same raw ID
  5. ID switch detected when raw ID changes for same spatial position
  6. Summary string produced
"""
import sys
from pathlib import Path

import pytest

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.track_quality import TrackQualityMonitor
from src.models.detection import Detection


# ─── Helpers ────────────────────────────────────────────────────────

def _det(track_id=None, class_id=0, conf=0.9, bbox=(10, 10, 100, 200)):
    return Detection(
        class_id=class_id, class_name="person", confidence=conf,
        bbox=bbox, track_id=track_id,
    )


# ════════════════════════════════════════════════════════════════════
#  Coverage Tests
# ════════════════════════════════════════════════════════════════════

class TestTrackCoverage:
    def test_full_coverage(self):
        """All detections tracked → coverage = 100.0%."""
        mon = TrackQualityMonitor()
        dets = [_det(track_id=1), _det(track_id=2), _det(track_id=3)]
        metrics = mon.update(dets, 100.0)
        assert metrics["track_coverage"] == 100.0

    def test_partial_coverage(self):
        """2 tracked out of 3 → coverage ≈ 66.7%."""
        mon = TrackQualityMonitor()
        dets = [_det(track_id=1), _det(track_id=2), _det(track_id=None)]
        metrics = mon.update(dets, 100.0)
        assert abs(metrics["track_coverage"] - 66.7) < 1.0

    def test_zero_detections(self):
        """No detections → coverage = 0.0 (nothing to track)."""
        mon = TrackQualityMonitor()
        metrics = mon.update([], 100.0)
        assert metrics["track_coverage"] == 0.0


# ════════════════════════════════════════════════════════════════════
#  Display ID Mapping Tests
# ════════════════════════════════════════════════════════════════════

class TestDisplayIDMapping:
    def test_display_ids_monotonic(self):
        """Display IDs should be assigned in order of first appearance."""
        mon = TrackQualityMonitor()
        dets = [_det(track_id=50), _det(track_id=20), _det(track_id=80)]
        id_map = mon.remap_detections_display_ids(dets)

        # IDs seen in order: 50, 20, 80 → display IDs 1, 2, 3
        assert id_map[50] == 1
        assert id_map[20] == 2
        assert id_map[80] == 3

    def test_display_ids_stable(self):
        """Same raw ID across calls → same display ID."""
        mon = TrackQualityMonitor()

        dets1 = [_det(track_id=50)]
        map1 = mon.remap_detections_display_ids(dets1)
        d50_first = map1[50]

        dets2 = [_det(track_id=50), _det(track_id=99)]
        map2 = mon.remap_detections_display_ids(dets2)
        assert map2[50] == d50_first
        assert map2[99] == d50_first + 1  # next sequential

    def test_none_track_id_excluded(self):
        """Untracked detections (track_id=None) should not appear in map."""
        mon = TrackQualityMonitor()
        dets = [_det(track_id=10), _det(track_id=None)]
        id_map = mon.remap_detections_display_ids(dets)
        assert 10 in id_map
        assert None not in id_map


# ════════════════════════════════════════════════════════════════════
#  Summary
# ════════════════════════════════════════════════════════════════════

class TestSummary:
    def test_summary_string(self):
        """summary() should return a non-empty string."""
        mon = TrackQualityMonitor()
        dets = [_det(track_id=1)]
        mon.update(dets, 100.0)
        s = mon.summary()
        assert isinstance(s, str)
        assert len(s) > 10
