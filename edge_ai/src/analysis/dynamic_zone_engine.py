"""Dynamic forklift safety zone generation and membership checks."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from ..config.settings import (
    FORKLIFT_ZONE_FORK_BASE_RATIO,
    FORKLIFT_ZONE_FORK_SPEED_GAIN,
    FORKLIFT_ZONE_FRONT_BASE_RATIO,
    FORKLIFT_ZONE_FRONT_SPEED_GAIN,
    FORKLIFT_ZONE_HEADING_UNCERTAINTY_WIDTH_GAIN,
    FORKLIFT_ZONE_REAR_BASE_RATIO,
    FORKLIFT_ZONE_REAR_SPEED_GAIN,
    FORKLIFT_ZONE_SIDE_BASE_RATIO,
    FORKLIFT_ZONE_SIDE_SPEED_GAIN,
    FORKLIFT_ZONE_STATIONARY_DIRECTIONAL_SCALE,
    MOTION_STATIONARY_SPEED_MPS,
)

BBox = Tuple[int, int, int, int]
Point = tuple[float, float]
Polygon = tuple[Point, ...]


class ZoneType(str, Enum):
    CLEAR = "clear"
    FOOTPRINT = "footprint"
    FORK_LOAD = "fork_load"
    FRONT_DANGER = "front_danger"
    REAR_DANGER = "rear_danger"
    SIDE_CRUSH = "side_crush"


@dataclass(slots=True)
class DynamicZoneConfig:
    front_base_ratio: float = FORKLIFT_ZONE_FRONT_BASE_RATIO
    front_speed_gain: float = FORKLIFT_ZONE_FRONT_SPEED_GAIN
    rear_base_ratio: float = FORKLIFT_ZONE_REAR_BASE_RATIO
    rear_speed_gain: float = FORKLIFT_ZONE_REAR_SPEED_GAIN
    fork_base_ratio: float = FORKLIFT_ZONE_FORK_BASE_RATIO
    fork_speed_gain: float = FORKLIFT_ZONE_FORK_SPEED_GAIN
    side_base_ratio: float = FORKLIFT_ZONE_SIDE_BASE_RATIO
    side_speed_gain: float = FORKLIFT_ZONE_SIDE_SPEED_GAIN
    heading_uncertainty_width_gain: float = FORKLIFT_ZONE_HEADING_UNCERTAINTY_WIDTH_GAIN
    stationary_directional_scale: float = FORKLIFT_ZONE_STATIONARY_DIRECTIONAL_SCALE
    stationary_speed_mps: float = MOTION_STATIONARY_SPEED_MPS


@dataclass(slots=True)
class DynamicZoneResult:
    zone_type: ZoneType
    active_zones: tuple[ZoneType, ...]
    worker_point: Point
    heading_px: Point
    heading_confidence: float
    directional_scale: float
    width_scale: float
    front_length_px: float
    rear_length_px: float
    side_margin_px: float
    polygons: dict[str, Polygon | tuple[Polygon, Polygon]]

    def metadata(self) -> dict:
        return {
            "dynamic_zone_type": self.zone_type.value,
            "dynamic_zone_active": [zone.value for zone in self.active_zones],
            "zone_heading_px": (
                round(self.heading_px[0], 4),
                round(self.heading_px[1], 4),
            ),
            "zone_heading_confidence": round(self.heading_confidence, 3),
            "zone_directional_scale": round(self.directional_scale, 3),
            "zone_width_scale": round(self.width_scale, 3),
            "zone_front_length_px": round(self.front_length_px, 3),
            "zone_rear_length_px": round(self.rear_length_px, 3),
            "zone_side_margin_px": round(self.side_margin_px, 3),
            "zone_polygons_px": _round_polygons(self.polygons),
        }


class DynamicZoneEngine:
    """Generate forklift-relative zones and classify worker membership."""

    def __init__(self, config: DynamicZoneConfig | None = None) -> None:
        self.config = config or DynamicZoneConfig()

    def evaluate(
        self,
        *,
        forklift_bbox: BBox,
        worker_point: Point,
        heading_px: Point,
        heading_confidence: float,
        speed_mps: float,
    ) -> DynamicZoneResult:
        x1, y1, x2, y2 = forklift_bbox
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        bbox_width = max(1.0, float(x2 - x1))
        bbox_height = max(1.0, float(y2 - y1))

        heading, resolved_confidence = _resolve_heading(heading_px, heading_confidence)
        side = (-heading[1], heading[0])
        half_length = max(1.0, abs(heading[0]) * bbox_width / 2.0 + abs(heading[1]) * bbox_height / 2.0)
        half_width = max(1.0, abs(side[0]) * bbox_width / 2.0 + abs(side[1]) * bbox_height / 2.0)
        vehicle_length = half_length * 2.0
        vehicle_width = half_width * 2.0

        speed = max(0.0, float(speed_mps))
        directional_scale = (
            _clamp(self.config.stationary_directional_scale, 0.0, 1.0)
            if speed < self.config.stationary_speed_mps
            else 1.0
        )
        width_scale = 1.0 + (1.0 - resolved_confidence) * max(0.0, self.config.heading_uncertainty_width_gain)

        front_length = vehicle_length * (
            self.config.front_base_ratio + self.config.front_speed_gain * speed
        ) * directional_scale
        rear_length = vehicle_length * (
            self.config.rear_base_ratio + self.config.rear_speed_gain * speed
        ) * directional_scale
        fork_length = vehicle_length * (
            self.config.fork_base_ratio + self.config.fork_speed_gain * speed
        ) * directional_scale
        side_margin = vehicle_width * (
            self.config.side_base_ratio + self.config.side_speed_gain * speed
        ) * width_scale

        front_edge = _add(center, _scale(heading, half_length))
        rear_edge = _add(center, _scale(heading, -half_length))
        front_end = _add(front_edge, _scale(heading, front_length))
        fork_end = _add(front_edge, _scale(heading, fork_length))
        rear_end = _add(rear_edge, _scale(heading, -rear_length))

        footprint = (
            (float(x1), float(y1)),
            (float(x2), float(y1)),
            (float(x2), float(y2)),
            (float(x1), float(y2)),
        )
        front_zone = _oriented_rect(front_edge, front_end, half_width * 1.20 * width_scale)
        fork_zone = _oriented_rect(front_edge, fork_end, half_width * 0.65 * width_scale)
        rear_zone = _oriented_rect(rear_edge, rear_end, half_width * 1.15 * width_scale)
        left_zone, right_zone = _side_zones(
            center=center,
            heading=heading,
            side=side,
            half_length=half_length,
            half_width=half_width,
            margin=side_margin,
        )

        polygons: dict[str, Polygon | tuple[Polygon, Polygon]] = {
            ZoneType.FOOTPRINT.value: footprint,
            ZoneType.FORK_LOAD.value: fork_zone,
            ZoneType.FRONT_DANGER.value: front_zone,
            ZoneType.REAR_DANGER.value: rear_zone,
            ZoneType.SIDE_CRUSH.value: (left_zone, right_zone),
        }
        active = self._active_zones(worker_point, polygons)
        zone_type = self._highest_priority(active)

        return DynamicZoneResult(
            zone_type=zone_type,
            active_zones=tuple(active),
            worker_point=worker_point,
            heading_px=heading,
            heading_confidence=resolved_confidence,
            directional_scale=directional_scale,
            width_scale=width_scale,
            front_length_px=front_length,
            rear_length_px=rear_length,
            side_margin_px=side_margin,
            polygons=polygons,
        )

    def _active_zones(
        self,
        worker_point: Point,
        polygons: dict[str, Polygon | tuple[Polygon, Polygon]],
    ) -> list[ZoneType]:
        active: list[ZoneType] = []
        for zone in (
            ZoneType.FOOTPRINT,
            ZoneType.FORK_LOAD,
            ZoneType.FRONT_DANGER,
            ZoneType.REAR_DANGER,
            ZoneType.SIDE_CRUSH,
        ):
            polygon = polygons[zone.value]
            if _contains(worker_point, polygon):
                active.append(zone)
        return active

    @staticmethod
    def _highest_priority(active: list[ZoneType]) -> ZoneType:
        for zone in (
            ZoneType.FOOTPRINT,
            ZoneType.FORK_LOAD,
            ZoneType.FRONT_DANGER,
            ZoneType.REAR_DANGER,
            ZoneType.SIDE_CRUSH,
        ):
            if zone in active:
                return zone
        return ZoneType.CLEAR


def _side_zones(
    *,
    center: Point,
    heading: Point,
    side: Point,
    half_length: float,
    half_width: float,
    margin: float,
) -> tuple[Polygon, Polygon]:
    rear_center = _add(center, _scale(heading, -half_length))
    front_center = _add(center, _scale(heading, half_length))
    left_inner_rear = _add(rear_center, _scale(side, half_width))
    left_inner_front = _add(front_center, _scale(side, half_width))
    left_outer_front = _add(left_inner_front, _scale(side, margin))
    left_outer_rear = _add(left_inner_rear, _scale(side, margin))

    right_inner_rear = _add(rear_center, _scale(side, -half_width))
    right_inner_front = _add(front_center, _scale(side, -half_width))
    right_outer_front = _add(right_inner_front, _scale(side, -margin))
    right_outer_rear = _add(right_inner_rear, _scale(side, -margin))

    return (
        (left_inner_rear, left_inner_front, left_outer_front, left_outer_rear),
        (right_inner_rear, right_inner_front, right_outer_front, right_outer_rear),
    )


def _oriented_rect(start: Point, end: Point, half_width: float) -> Polygon:
    direction = _unit((end[0] - start[0], end[1] - start[1]))
    side = (-direction[1], direction[0])
    return (
        _add(start, _scale(side, half_width)),
        _add(end, _scale(side, half_width)),
        _add(end, _scale(side, -half_width)),
        _add(start, _scale(side, -half_width)),
    )


def _resolve_heading(heading: Point, confidence: float) -> tuple[Point, float]:
    norm = math.hypot(heading[0], heading[1])
    if norm <= 1e-9:
        return (1.0, 0.0), 0.0
    return (heading[0] / norm, heading[1] / norm), _clamp(confidence, 0.0, 1.0)


def _contains(point: Point, polygon_or_polygons: Polygon | tuple[Polygon, Polygon]) -> bool:
    if not polygon_or_polygons:
        return False
    first = polygon_or_polygons[0]
    if isinstance(first, tuple) and len(first) == 2 and isinstance(first[0], (int, float)):
        return _point_in_polygon(point, polygon_or_polygons)  # type: ignore[arg-type]
    return any(_point_in_polygon(point, polygon) for polygon in polygon_or_polygons)  # type: ignore[arg-type]


def _point_in_polygon(point: Point, polygon: Polygon) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if _point_on_segment(point, (xi, yi), (xj, yj)):
            return True
        intersects = (yi > y) != (yj > y)
        if intersects:
            x_intersection = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x <= x_intersection:
                inside = not inside
        j = i
    return inside


def _point_on_segment(point: Point, a: Point, b: Point, *, eps: float = 1e-6) -> bool:
    cross = (point[1] - a[1]) * (b[0] - a[0]) - (point[0] - a[0]) * (b[1] - a[1])
    if abs(cross) > eps:
        return False
    dot = (point[0] - a[0]) * (b[0] - a[0]) + (point[1] - a[1]) * (b[1] - a[1])
    if dot < -eps:
        return False
    length_sq = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
    return dot <= length_sq + eps


def _round_polygons(polygons: dict[str, Polygon | tuple[Polygon, Polygon]]) -> dict:
    rounded: dict[str, list] = {}
    for key, polygon_or_polygons in polygons.items():
        first = polygon_or_polygons[0]
        if isinstance(first, tuple) and len(first) == 2 and isinstance(first[0], (int, float)):
            rounded[key] = [_round_point(point) for point in polygon_or_polygons]  # type: ignore[arg-type]
        else:
            rounded[key] = [
                [_round_point(point) for point in polygon]
                for polygon in polygon_or_polygons  # type: ignore[union-attr]
            ]
    return rounded


def _round_point(point: Point) -> tuple[float, float]:
    return (round(point[0], 3), round(point[1], 3))


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _scale(v: Point, scalar: float) -> Point:
    return (v[0] * scalar, v[1] * scalar)


def _unit(v: Point) -> Point:
    norm = math.hypot(v[0], v[1])
    if norm <= 1e-9:
        return (1.0, 0.0)
    return (v[0] / norm, v[1] / norm)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
