"""
VisionSafe 360 — Camera Calibration Layer

Converts pixel-space bottom-center points to real-world ground-plane metres
using a per-camera homography matrix (3×3).

If no calibration is provided, distances remain in pixels and the system
flags "UNCALIBRATED: PX MODE" on the HUD.

Calibration files:  calibration/<camera_id>.json
  {
    "camera_id": "cam_01",
    "image_points": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
    "world_points": [[X1,Y1], [X2,Y2], [X3,Y3], [X4,Y4]],
    "homography": [[h00,h01,h02],[h10,h11,h12],[h20,h21,h22]]
  }

4-point calibration: pick 4 ground-plane points visible in the camera image,
measure their real-world coordinates in metres.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from ..config.settings import (
    CALIBRATION_DIR,
)

logger = logging.getLogger(__name__)


class CameraCalibration:
    """Per-camera pixel→metre transform using homography."""

    def __init__(self, camera_id: str, homography: np.ndarray, unit: str = "metres") -> None:
        self.camera_id = camera_id
        self.unit = unit
        self.H = homography  # 3×3
        self._H_inv = np.linalg.inv(homography)

    def pixel_to_ground(self, px: float, py: float) -> Tuple[float, float]:
        """Transform pixel (x, y) to ground-plane (X_m, Y_m)."""
        pt = np.array([px, py, 1.0])
        world = self.H @ pt
        world /= world[2]  # normalize
        return float(world[0]), float(world[1])

    def ground_distance(
        self, p1: Tuple[float, float], p2: Tuple[float, float]
    ) -> float:
        """Euclidean distance in metres between two pixel points."""
        g1 = self.pixel_to_ground(*p1)
        g2 = self.pixel_to_ground(*p2)
        return float(np.sqrt((g1[0] - g2[0]) ** 2 + (g1[1] - g2[1]) ** 2))

    # Alias for backward compatibility
    pixel_to_world_distance = ground_distance


class CalibrationManager:
    """Manages per-camera calibration configs.

    Loads from calibration/ directory on startup.  Falls back to pixel mode
    for uncalibrated cameras.
    """

    def __init__(self, calibration_dir: Optional[Path] = None) -> None:
        self._calibration_dir = calibration_dir if calibration_dir is not None else CALIBRATION_DIR
        self._calibrations: Dict[str, CameraCalibration] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Scan calibration/ directory for .json files."""
        if not self._calibration_dir.exists():
            logger.info("No calibration directory found — all cameras in PX MODE")
            return

        for f in self._calibration_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                cam_id = data["camera_id"]
                if "homography" in data:
                    H = np.array(data["homography"], dtype=np.float64)
                    assert H.shape == (3, 3), f"Bad homography shape: {H.shape}"
                elif "image_points" in data and "world_points" in data:
                    img_pts = np.array(data["image_points"], dtype=np.float64)
                    wld_pts = np.array(data["world_points"], dtype=np.float64)
                    assert img_pts.shape == (4, 2) and wld_pts.shape == (4, 2)
                    import cv2
                    H, _ = cv2.findHomography(img_pts, wld_pts)
                else:
                    logger.warning("Calibration file %s missing homography or points", f)
                    continue

                self._calibrations[cam_id] = CameraCalibration(cam_id, H)
                logger.info("Loaded calibration for %s from %s", cam_id, f.name)
            except Exception as exc:
                logger.warning("Failed to load calibration from %s: %s", f, exc)

    def is_calibrated(self, camera_id: str) -> bool:
        return camera_id in self._calibrations

    def get(self, camera_id: str) -> Optional[CameraCalibration]:
        return self._calibrations.get(camera_id)

    def compute_distance(
        self,
        camera_id: str,
        p1_px: Tuple[float, float],
        p2_px: Tuple[float, float],
    ) -> float:
        """Compute distance between two bottom-center points.

        Returns distance in metres (if calibrated) or pixels (if not).
        Use ``is_calibrated(camera_id)`` to check which unit applies.
        """
        import math

        cal = self._calibrations.get(camera_id)
        if cal is not None:
            return cal.ground_distance(p1_px, p2_px)
        else:
            return math.sqrt(
                (p1_px[0] - p2_px[0]) ** 2 + (p1_px[1] - p2_px[1]) ** 2
            )

    def get_thresholds(
        self, camera_id: str
    ) -> Dict[str, float]:
        """Placeholder — proximity thresholds removed (pose-only pipeline)."""
        return {"critical": 0.0, "high": 0.0, "warning": 0.0}
