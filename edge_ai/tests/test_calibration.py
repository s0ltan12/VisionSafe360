"""
Unit tests for CalibrationManager — pixel-to-metre conversion and fallback.

Tests:
  1. No calibration file → uncalibrated mode
  2. Pixel-mode euclidean fallback works
  3. Homography calibration computes correct transform
  4. is_calibrated returns correct status
"""
import sys
import json
import tempfile
from pathlib import Path

import pytest
import numpy as np

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.calibration import CalibrationManager, CameraCalibration


# ════════════════════════════════════════════════════════════════════
#  Uncalibrated Fallback
# ════════════════════════════════════════════════════════════════════

class TestUncalibratedFallback:
    def test_no_calibration_dir_returns_uncalibrated(self):
        """Without calibration files, is_calibrated should return False."""
        mgr = CalibrationManager(calibration_dir=Path("/nonexistent"))
        assert mgr.is_calibrated("cam_01") is False

    def test_pixel_distance_fallback(self):
        """compute_distance in pixel mode returns euclidean distance."""
        mgr = CalibrationManager(calibration_dir=Path("/nonexistent"))
        pt_a = (0, 0)
        pt_b = (3, 4)
        dist = mgr.compute_distance("cam_01", pt_a, pt_b)
        assert abs(dist - 5.0) < 0.01


# ════════════════════════════════════════════════════════════════════
#  Calibrated Mode
# ════════════════════════════════════════════════════════════════════

class TestCalibratedMode:
    def _make_calibration_dir(self, tmp_path, cam_id="cam_01"):
        """Create a calibration JSON with a simple identity-like homography."""
        # Simple scaling: 10 px = 1 m  (so homography scales by 0.1)
        cal_data = {
            "camera_id": cam_id,
            "image_points": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "world_points": [[0, 0], [10, 0], [10, 10], [0, 10]],
            "unit": "metres",
        }
        cal_dir = tmp_path / "calibration"
        cal_dir.mkdir()
        cal_file = cal_dir / f"{cam_id}.json"
        cal_file.write_text(json.dumps(cal_data))
        return cal_dir

    def test_is_calibrated_with_file(self, tmp_path):
        """Should be calibrated when proper JSON file exists."""
        cal_dir = self._make_calibration_dir(tmp_path)
        mgr = CalibrationManager(calibration_dir=cal_dir)
        assert mgr.is_calibrated("cam_01") is True

    def test_calibrated_distance(self, tmp_path):
        """Distance between known points should be in metres."""
        cal_dir = self._make_calibration_dir(tmp_path)
        mgr = CalibrationManager(calibration_dir=cal_dir)

        # 100px apart in image → 10m apart in world (identity-scale homography)
        pt_a = (0, 50)
        pt_b = (100, 50)
        dist = mgr.compute_distance("cam_01", pt_a, pt_b)
        # Should be approximately 10.0 metres
        assert 8.0 < dist < 12.0, f"Expected ~10m, got {dist:.1f}m"

    def test_thresholds_calibrated(self, tmp_path):
        """get_thresholds returns zeroed thresholds (proximity removed)."""
        cal_dir = self._make_calibration_dir(tmp_path)
        mgr = CalibrationManager(calibration_dir=cal_dir)
        thresholds = mgr.get_thresholds("cam_01")

        assert thresholds["critical"] == 0.0

    def test_thresholds_uncalibrated(self):
        """get_thresholds returns zeroed thresholds when uncalibrated."""
        mgr = CalibrationManager(calibration_dir=Path("/nonexistent"))
        thresholds = mgr.get_thresholds("cam_01")

        assert thresholds["critical"] == 0.0


# ════════════════════════════════════════════════════════════════════
#  CameraCalibration Direct
# ════════════════════════════════════════════════════════════════════

class TestCameraCalibration:
    def test_homography_transform(self):
        """Direct CameraCalibration with known homography."""
        # Identity homography scaled by 0.1 (10px = 1m)
        H = np.array([[0.1, 0.0, 0.0],
                       [0.0, 0.1, 0.0],
                       [0.0, 0.0, 1.0]], dtype=np.float64)
        cal = CameraCalibration(camera_id="test", homography=H, unit="metres")

        dist = cal.pixel_to_world_distance((0, 0), (100, 0))
        assert abs(dist - 10.0) < 0.01
