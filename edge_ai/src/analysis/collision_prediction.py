"""Relative motion, CPA, and TTC prediction for forklift-worker pairs."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ..config.settings import (
    COLLISION_ACTOR_RADIUS_M,
    COLLISION_CROSSING_DISTANCE_M,
    COLLISION_MIN_CLOSING_SPEED_MPS,
    COLLISION_PARALLEL_COSINE,
    COLLISION_PREDICTION_HORIZON_SEC,
    COLLISION_STATIONARY_REL_SPEED_MPS,
)

Vector = tuple[float, float]


class RelativeMotionClass(str, Enum):
    APPROACHING = "APPROACHING"
    DEPARTING = "DEPARTING"
    CROSSING = "CROSSING"
    PARALLEL = "PARALLEL"
    STATIONARY = "STATIONARY"


@dataclass(slots=True)
class CollisionPredictionConfig:
    horizon_sec: float = COLLISION_PREDICTION_HORIZON_SEC
    min_closing_speed_mps: float = COLLISION_MIN_CLOSING_SPEED_MPS
    stationary_relative_speed_mps: float = COLLISION_STATIONARY_REL_SPEED_MPS
    crossing_distance_m: float = COLLISION_CROSSING_DISTANCE_M
    parallel_cosine: float = COLLISION_PARALLEL_COSINE
    actor_radius_m: float = COLLISION_ACTOR_RADIUS_M


@dataclass(slots=True)
class CollisionPrediction:
    ttc_seconds: float | None
    time_to_closest_approach: float
    closest_approach_distance_m: float
    relative_motion_class: RelativeMotionClass
    relative_speed_mps: float
    closing_speed_mps: float
    predicted_collision: bool
    confidence: float
    horizon_sec: float

    def metadata(self) -> dict:
        return {
            "ttc_seconds": None if self.ttc_seconds is None else round(self.ttc_seconds, 3),
            "time_to_closest_approach": round(self.time_to_closest_approach, 3),
            "closest_approach_distance_m": round(self.closest_approach_distance_m, 3),
            "relative_motion_class": self.relative_motion_class.value,
            "relative_speed_mps": round(self.relative_speed_mps, 3),
            "closing_speed_mps": round(self.closing_speed_mps, 3),
            "predicted_collision": self.predicted_collision,
            "collision_prediction_confidence": round(self.confidence, 3),
            "collision_prediction_horizon_sec": round(self.horizon_sec, 3),
        }


class CollisionPredictionEngine:
    """Evaluate relative motion and future closest approach."""

    def __init__(self, config: CollisionPredictionConfig | None = None) -> None:
        self.config = config or CollisionPredictionConfig()

    def evaluate(
        self,
        *,
        forklift_position_m: Vector,
        worker_position_m: Vector,
        forklift_velocity_mps: Vector,
        worker_velocity_mps: Vector,
        calibration_confidence: float,
    ) -> CollisionPrediction:
        relative_position = _sub(worker_position_m, forklift_position_m)
        relative_velocity = _sub(worker_velocity_mps, forklift_velocity_mps)
        distance_m = _norm(relative_position)
        relative_speed = _norm(relative_velocity)
        forklift_speed = _norm(forklift_velocity_mps)
        worker_speed = _norm(worker_velocity_mps)

        closing_speed = 0.0
        if distance_m > 1e-9:
            closing_speed = -_dot(relative_position, relative_velocity) / distance_m

        time_to_closest = 0.0
        if relative_speed > 1e-9:
            raw_tcpa = -_dot(relative_position, relative_velocity) / (relative_speed ** 2)
            time_to_closest = _clamp(raw_tcpa, 0.0, max(0.0, self.config.horizon_sec))
        closest_point = _add(relative_position, _scale(relative_velocity, time_to_closest))
        closest_distance = _norm(closest_point)
        if closest_distance < 1e-9:
            closest_distance = 0.0

        ttc = None
        if closing_speed > self.config.min_closing_speed_mps:
            ttc = distance_m / closing_speed

        motion_class = self._classify(
            closing_speed=closing_speed,
            relative_speed=relative_speed,
            forklift_velocity=forklift_velocity_mps,
            worker_velocity=worker_velocity_mps,
            forklift_speed=forklift_speed,
            worker_speed=worker_speed,
            time_to_closest=time_to_closest,
            closest_distance=closest_distance,
        )
        predicted_collision = (
            ttc is not None
            and 0.0 <= time_to_closest <= self.config.horizon_sec
            and closest_distance <= self.config.actor_radius_m
        )

        return CollisionPrediction(
            ttc_seconds=ttc,
            time_to_closest_approach=time_to_closest,
            closest_approach_distance_m=closest_distance,
            relative_motion_class=motion_class,
            relative_speed_mps=relative_speed,
            closing_speed_mps=closing_speed,
            predicted_collision=predicted_collision,
            confidence=self._confidence(calibration_confidence, relative_speed),
            horizon_sec=self.config.horizon_sec,
        )

    def _classify(
        self,
        *,
        closing_speed: float,
        relative_speed: float,
        forklift_velocity: Vector,
        worker_velocity: Vector,
        forklift_speed: float,
        worker_speed: float,
        time_to_closest: float,
        closest_distance: float,
    ) -> RelativeMotionClass:
        velocity_cosine = _cosine(forklift_velocity, worker_velocity)
        actor_moving = forklift_speed >= self.config.stationary_relative_speed_mps or worker_speed >= self.config.stationary_relative_speed_mps

        if relative_speed < self.config.stationary_relative_speed_mps:
            if actor_moving and velocity_cosine >= self.config.parallel_cosine:
                return RelativeMotionClass.PARALLEL
            return RelativeMotionClass.STATIONARY

        if closing_speed > self.config.min_closing_speed_mps:
            if (
                forklift_speed >= self.config.stationary_relative_speed_mps
                and worker_speed >= self.config.stationary_relative_speed_mps
                and abs(velocity_cosine) < self.config.parallel_cosine
                and 0.0 < time_to_closest <= self.config.horizon_sec
                and closest_distance <= self.config.crossing_distance_m
            ):
                return RelativeMotionClass.CROSSING
            return RelativeMotionClass.APPROACHING

        if closing_speed < -self.config.min_closing_speed_mps:
            return RelativeMotionClass.DEPARTING

        if (
            0.0 < time_to_closest <= self.config.horizon_sec
            and closest_distance <= self.config.crossing_distance_m
        ):
            return RelativeMotionClass.CROSSING
        return RelativeMotionClass.PARALLEL

    def _confidence(self, calibration_confidence: float, relative_speed: float) -> float:
        calibration = _clamp(calibration_confidence, 0.0, 1.0)
        motion_confidence = min(1.0, relative_speed / max(self.config.min_closing_speed_mps * 4.0, 1e-9))
        return calibration * (0.5 + 0.5 * motion_confidence)


def _add(a: Vector, b: Vector) -> Vector:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Vector, b: Vector) -> Vector:
    return (a[0] - b[0], a[1] - b[1])


def _scale(v: Vector, scalar: float) -> Vector:
    return (v[0] * scalar, v[1] * scalar)


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _norm(v: Vector) -> float:
    return math.hypot(v[0], v[1])


def _cosine(a: Vector, b: Vector) -> float:
    denom = _norm(a) * _norm(b)
    if denom <= 1e-9:
        return 0.0
    return _clamp(_dot(a, b) / denom, -1.0, 1.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
