"""Ground-plane distance estimation for forklift proximity."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from ..config.settings import DISTANCE_FALLBACK_METERS_PER_PIXEL

BBox = Tuple[int, int, int, int]


class _CalibrationLike(Protocol):
    def is_calibrated(self, camera_id: str) -> bool:
        ...

    def compute_distance(
        self,
        camera_id: str,
        p1_px: tuple[float, float],
        p2_px: tuple[float, float],
    ) -> float:
        ...


@dataclass(slots=True)
class DistanceResult:
    distance_px: float
    distance_m: float
    calibration_confidence: float
    distance_source: str
    worker_bottom_center: tuple[float, float]
    forklift_bottom_center: tuple[float, float]
    worker_ground_point: Optional[tuple[float, float]] = None
    forklift_ground_point: Optional[tuple[float, float]] = None

    def metadata(self) -> dict:
        data = {
            "distance_px": round(self.distance_px, 3),
            "distance_m": round(self.distance_m, 3),
            "calibration_confidence": round(self.calibration_confidence, 3),
            "distance_source": self.distance_source,
            "worker_bottom_center": (
                round(self.worker_bottom_center[0], 3),
                round(self.worker_bottom_center[1], 3),
            ),
            "forklift_bottom_center": (
                round(self.forklift_bottom_center[0], 3),
                round(self.forklift_bottom_center[1], 3),
            ),
        }
        if self.worker_ground_point is not None:
            data["worker_ground_point_m"] = (
                round(self.worker_ground_point[0], 3),
                round(self.worker_ground_point[1], 3),
            )
        if self.forklift_ground_point is not None:
            data["forklift_ground_point_m"] = (
                round(self.forklift_ground_point[0], 3),
                round(self.forklift_ground_point[1], 3),
            )
        return data


class DistanceEngine:
    """Compute worker-to-forklift distance from bottom-center points."""

    def __init__(
        self,
        calibration_mgr: Optional[_CalibrationLike] = None,
        *,
        fallback_meters_per_pixel: float = DISTANCE_FALLBACK_METERS_PER_PIXEL,
    ) -> None:
        self.calibration_mgr = calibration_mgr
        self.fallback_meters_per_pixel = max(0.0, float(fallback_meters_per_pixel))

    def compute(
        self,
        *,
        camera_id: str,
        worker_bbox: BBox,
        forklift_bbox: BBox,
        detection_confidence: float | None = None,
    ) -> DistanceResult:
        worker_point = bottom_center(worker_bbox)
        forklift_point = bottom_center(forklift_bbox)
        distance_px = _distance(worker_point, forklift_point)

        if self.calibration_mgr is not None and self.calibration_mgr.is_calibrated(camera_id):
            worker_ground, forklift_ground = self._ground_points(
                camera_id,
                worker_point,
                forklift_point,
            )
            distance_m = float(
                self.calibration_mgr.compute_distance(camera_id, worker_point, forklift_point)
            )
            confidence = self._calibration_confidence(camera_id)
            return DistanceResult(
                distance_px=distance_px,
                distance_m=distance_m,
                calibration_confidence=confidence,
                distance_source="ground_plane",
                worker_bottom_center=worker_point,
                forklift_bottom_center=forklift_point,
                worker_ground_point=worker_ground,
                forklift_ground_point=forklift_ground,
            )

        distance_m = distance_px * self.fallback_meters_per_pixel
        return DistanceResult(
            distance_px=distance_px,
            distance_m=distance_m,
            calibration_confidence=0.0,
            distance_source="pixel_fallback",
            worker_bottom_center=worker_point,
            forklift_bottom_center=forklift_point,
        )

    def _calibration_confidence(self, camera_id: str) -> float:
        fn = getattr(self.calibration_mgr, "calibration_confidence", None)
        if callable(fn):
            try:
                return max(0.0, min(1.0, float(fn(camera_id))))
            except (TypeError, ValueError):
                return 1.0
        return 1.0

    def _ground_points(
        self,
        camera_id: str,
        worker_point: tuple[float, float],
        forklift_point: tuple[float, float],
    ) -> tuple[Optional[tuple[float, float]], Optional[tuple[float, float]]]:
        get_calibration = getattr(self.calibration_mgr, "get", None)
        if not callable(get_calibration):
            return None, None
        calibration = get_calibration(camera_id)
        if calibration is None:
            return None, None
        pixel_to_ground = getattr(calibration, "pixel_to_ground", None)
        if not callable(pixel_to_ground):
            return None, None
        try:
            return (
                pixel_to_ground(*worker_point),
                pixel_to_ground(*forklift_point),
            )
        except (TypeError, ValueError, ZeroDivisionError):
            return None, None


def bottom_center(bbox: BBox) -> tuple[float, float]:
    x1, _y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, float(y2))


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
