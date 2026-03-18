"""
VisionSafe360 — Pose / Skeleton Layer.

Draws COCO-17 keypoint skeletons produced by YOLO-pose in the theme's
yellow palette.  Only joints above the confidence threshold are rendered;
limbs connecting a low-confidence pair are silently skipped.

Expected input: Ultralytics ``Results`` object from ``engine.run_pose()``.
``results.keypoints.data`` has shape ``(N, 17, 3)``  → ``(x, y, conf)``.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..theme import IndustrialTheme, DARK
from ...config.ui_settings import UISettings


# COCO-17 skeleton connections (0-indexed joint pairs)
_SKELETON: list[tuple[int, int]] = [
    (0, 1),  (0, 2),           # nose → left/right eye
    (1, 3),  (2, 4),           # eyes → ears
    (0, 5),  (0, 6),           # nose → shoulders
    (5, 7),  (7, 9),           # left arm
    (6, 8),  (8, 10),          # right arm
    (5, 6),                    # shoulder bar
    (5, 11), (6, 12),          # torso sides
    (11, 12),                  # hip bar
    (11, 13), (13, 15),        # left leg
    (12, 14), (14, 16),        # right leg
]

_NUM_KP = 17


class PoseLayer:
    """Renders YOLO-pose COCO-17 skeletons on the frame."""

    def __init__(
        self,
        theme: IndustrialTheme = DARK,
        cfg: UISettings | None = None,
    ) -> None:
        self.theme = theme
        self.cfg = cfg or UISettings()

    def draw(
        self,
        frame: np.ndarray,
        pose_results: Any,          # Ultralytics Results object
        degraded: bool = False,
    ) -> None:
        """Draw all skeletons from *pose_results* onto *frame* in-place."""
        if pose_results is None:
            return

        kps_obj = getattr(pose_results, "keypoints", None)
        if kps_obj is None:
            return
        kps_data = getattr(kps_obj, "data", None)
        if kps_data is None or len(kps_data) == 0:
            return

        t = self.theme
        thresh = self.cfg.pose_kp_conf_thresh
        fh, fw = frame.shape[:2]

        # Reduce quality when over performance budget
        limb_thick = 1 if degraded else t.limb_thickness
        kp_radius = max(1, t.kp_radius - (1 if degraded else 0))
        joint_c = t.skeleton_joint
        limb_c = t.skeleton_limb

        # Convert tensor to numpy (handles both torch Tensor and ndarray)
        try:
            kps_np = kps_data.cpu().numpy()
        except AttributeError:
            kps_np = np.asarray(kps_data)

        for person_kps in kps_np:
            # person_kps: (17, 3) = [(x, y, conf), …]
            if person_kps.shape[0] < _NUM_KP:
                continue

            # Draw limbs first (under the joint dots)
            for i1, i2 in _SKELETON:
                x1, y1, c1 = person_kps[i1]
                x2, y2, c2 = person_kps[i2]
                if c1 < thresh or c2 < thresh:
                    continue
                ix1, iy1 = int(x1), int(y1)
                ix2, iy2 = int(x2), int(y2)
                # Skip degenerate/out-of-frame points
                if (ix1 <= 0 and ix2 <= 0) or (iy1 <= 0 and iy2 <= 0):
                    continue
                cv2.line(frame, (ix1, iy1), (ix2, iy2), limb_c, limb_thick, cv2.LINE_AA)

            # Draw joints on top
            for kp in person_kps:
                x, y, c = kp
                if c < thresh:
                    continue
                ix, iy = int(x), int(y)
                if 0 <= ix < fw and 0 <= iy < fh:
                    cv2.circle(frame, (ix, iy), kp_radius, joint_c, -1, cv2.LINE_AA)
