"""Motion state estimation for tracked forklifts and workers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Hashable, Optional

from ..config.settings import (
    MOTION_CREEPING_SPEED_MPS,
    MOTION_EMA_ALPHA,
    MOTION_FALLBACK_METERS_PER_PIXEL,
    MOTION_MIN_HEADING_SPEED_MPS,
    MOTION_STATIONARY_SPEED_MPS,
)


class MotionState(str, Enum):
    STATIONARY = "STATIONARY"
    CREEPING = "CREEPING"
    MOVING = "MOVING"


@dataclass(slots=True)
class MotionSnapshot:
    track_key: Hashable
    point_px: tuple[float, float]
    point_m: Optional[tuple[float, float]]
    timestamp: float
    speed_pxps: float
    speed_mps: float
    raw_speed_pxps: float
    raw_speed_mps: float
    velocity_pxps: tuple[float, float]
    velocity_mps: tuple[float, float]
    raw_velocity_pxps: tuple[float, float]
    raw_velocity_mps: tuple[float, float]
    heading: tuple[float, float]
    heading_confidence: float
    state: MotionState
    age: int
    age_seconds: float
    speed_source: str

    def metadata(self, prefix: str) -> dict:
        return {
            f"{prefix}_speed_pxps": round(self.speed_pxps, 3),
            f"{prefix}_speed_mps": round(self.speed_mps, 3),
            f"{prefix}_raw_speed_pxps": round(self.raw_speed_pxps, 3),
            f"{prefix}_raw_speed_mps": round(self.raw_speed_mps, 3),
            f"{prefix}_velocity_pxps": (
                round(self.velocity_pxps[0], 3),
                round(self.velocity_pxps[1], 3),
            ),
            f"{prefix}_velocity_mps": (
                round(self.velocity_mps[0], 3),
                round(self.velocity_mps[1], 3),
            ),
            f"{prefix}_raw_velocity_pxps": (
                round(self.raw_velocity_pxps[0], 3),
                round(self.raw_velocity_pxps[1], 3),
            ),
            f"{prefix}_raw_velocity_mps": (
                round(self.raw_velocity_mps[0], 3),
                round(self.raw_velocity_mps[1], 3),
            ),
            f"{prefix}_heading": (
                round(self.heading[0], 4),
                round(self.heading[1], 4),
            ),
            f"{prefix}_heading_confidence": round(self.heading_confidence, 3),
            f"{prefix}_motion_state": self.state.value,
            f"{prefix}_motion_age": self.age,
            f"{prefix}_motion_age_seconds": round(self.age_seconds, 3),
            f"{prefix}_speed_source": self.speed_source,
        }


@dataclass(slots=True)
class _TrackMotionState:
    point_px: tuple[float, float]
    point_m: Optional[tuple[float, float]]
    timestamp: float
    first_timestamp: float
    velocity_pxps: tuple[float, float] = (0.0, 0.0)
    velocity_mps: tuple[float, float] = (0.0, 0.0)
    raw_velocity_pxps: tuple[float, float] = (0.0, 0.0)
    raw_velocity_mps: tuple[float, float] = (0.0, 0.0)
    heading: tuple[float, float] = (1.0, 0.0)
    heading_confidence: float = 0.0
    age: int = 1
    speed_source: str = "ground_plane"


class MotionEngine:
    """Compute speed, heading, and coarse motion state for track histories."""

    def __init__(
        self,
        *,
        stationary_speed_mps: float = MOTION_STATIONARY_SPEED_MPS,
        creeping_speed_mps: float = MOTION_CREEPING_SPEED_MPS,
        ema_alpha: float = MOTION_EMA_ALPHA,
        min_heading_speed_mps: float = MOTION_MIN_HEADING_SPEED_MPS,
        fallback_meters_per_pixel: float = MOTION_FALLBACK_METERS_PER_PIXEL,
    ) -> None:
        self.stationary_speed_mps = float(stationary_speed_mps)
        self.creeping_speed_mps = float(creeping_speed_mps)
        self.ema_alpha = max(0.0, min(1.0, float(ema_alpha)))
        self.min_heading_speed_mps = float(min_heading_speed_mps)
        self.fallback_meters_per_pixel = max(0.0, float(fallback_meters_per_pixel))
        self._states: dict[Hashable, _TrackMotionState] = {}

    def update(
        self,
        track_key: Hashable,
        point_px: tuple[float, float],
        timestamp: float,
        *,
        point_m: Optional[tuple[float, float]] = None,
    ) -> MotionSnapshot:
        prev = self._states.get(track_key)
        if prev is None:
            state = _TrackMotionState(
                point_px=point_px,
                point_m=point_m,
                timestamp=timestamp,
                first_timestamp=timestamp,
                speed_source="ground_plane" if point_m is not None else "pixel_fallback",
            )
            self._states[track_key] = state
            return self._snapshot(track_key, state)

        dt = max(0.0, timestamp - prev.timestamp)
        if dt > 0.0:
            raw_px = (
                (point_px[0] - prev.point_px[0]) / dt,
                (point_px[1] - prev.point_px[1]) / dt,
            )
            raw_m, speed_source = self._raw_velocity_m(prev, point_m, raw_px, dt)
            prev.raw_velocity_pxps = raw_px
            prev.raw_velocity_mps = raw_m
            prev.speed_source = speed_source
            prev.velocity_pxps = _ema(prev.velocity_pxps, raw_px, self.ema_alpha)
            prev.velocity_mps = _ema(prev.velocity_mps, raw_m, self.ema_alpha)

            speed_mps = _norm(prev.velocity_mps)
            if speed_mps >= self.min_heading_speed_mps:
                prev.heading = _unit(prev.velocity_mps)
                prev.heading_confidence = min(1.0, speed_mps / max(self.creeping_speed_mps, 0.001))
            else:
                prev.heading_confidence *= 0.8

        prev.point_px = point_px
        prev.point_m = point_m
        prev.timestamp = timestamp
        prev.age += 1
        return self._snapshot(track_key, prev)

    def get(self, track_key: Hashable) -> Optional[MotionSnapshot]:
        state = self._states.get(track_key)
        return self._snapshot(track_key, state) if state is not None else None

    def _raw_velocity_m(
        self,
        prev: _TrackMotionState,
        point_m: Optional[tuple[float, float]],
        raw_px: tuple[float, float],
        dt: float,
    ) -> tuple[tuple[float, float], str]:
        if prev.point_m is not None and point_m is not None:
            return (
                (
                    (point_m[0] - prev.point_m[0]) / dt,
                    (point_m[1] - prev.point_m[1]) / dt,
                ),
                "ground_plane",
            )
        return (
            (
                raw_px[0] * self.fallback_meters_per_pixel,
                raw_px[1] * self.fallback_meters_per_pixel,
            ),
            "pixel_fallback",
        )

    def _snapshot(self, track_key: Hashable, state: _TrackMotionState) -> MotionSnapshot:
        speed_pxps = _norm(state.velocity_pxps)
        speed_mps = _norm(state.velocity_mps)
        raw_speed_pxps = _norm(state.raw_velocity_pxps)
        raw_speed_mps = _norm(state.raw_velocity_mps)
        if speed_mps < self.stationary_speed_mps:
            motion = MotionState.STATIONARY
        elif speed_mps <= self.creeping_speed_mps:
            motion = MotionState.CREEPING
        else:
            motion = MotionState.MOVING
        return MotionSnapshot(
            track_key=track_key,
            point_px=state.point_px,
            point_m=state.point_m,
            timestamp=state.timestamp,
            speed_pxps=speed_pxps,
            speed_mps=speed_mps,
            raw_speed_pxps=raw_speed_pxps,
            raw_speed_mps=raw_speed_mps,
            velocity_pxps=state.velocity_pxps,
            velocity_mps=state.velocity_mps,
            raw_velocity_pxps=state.raw_velocity_pxps,
            raw_velocity_mps=state.raw_velocity_mps,
            heading=state.heading,
            heading_confidence=state.heading_confidence,
            state=motion,
            age=state.age,
            age_seconds=max(0.0, state.timestamp - state.first_timestamp),
            speed_source=state.speed_source,
        )


def _ema(old: tuple[float, float], new: tuple[float, float], alpha: float) -> tuple[float, float]:
    return (
        alpha * new[0] + (1.0 - alpha) * old[0],
        alpha * new[1] + (1.0 - alpha) * old[1],
    )


def _norm(v: tuple[float, float]) -> float:
    return math.hypot(v[0], v[1])


def _unit(v: tuple[float, float]) -> tuple[float, float]:
    n = _norm(v)
    if n <= 1e-9:
        return (1.0, 0.0)
    return (v[0] / n, v[1] / n)
