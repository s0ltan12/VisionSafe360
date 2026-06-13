"""Dynamic forklift proximity safety bubble policy."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..config.settings import (
    PROXIMITY_DANGER_BASE_M,
    PROXIMITY_DANGER_MAX_M,
    PROXIMITY_DANGER_MIN_M,
    PROXIMITY_DANGER_SPEED_GAIN,
    PROXIMITY_LOW_CONFIDENCE_RADIUS_SCALE,
    PROXIMITY_WARNING_BASE_M,
    PROXIMITY_WARNING_MAX_M,
    PROXIMITY_WARNING_MIN_M,
    PROXIMITY_WARNING_SPEED_GAIN,
)


class ProximityLevel(str, Enum):
    CLEAR = "clear"
    WARNING = "warning"
    DANGER = "danger"


@dataclass(slots=True)
class ProximityPolicyResult:
    level: ProximityLevel
    distance_m: float
    danger_radius_m: float
    warning_radius_m: float
    speed_mps: float
    confidence_scale: float

    def metadata(self) -> dict:
        return {
            "proximity_policy": "dynamic_safety_bubble",
            "proximity_level": self.level.value,
            "danger_radius_m": round(self.danger_radius_m, 3),
            "warning_radius_m": round(self.warning_radius_m, 3),
            "proximity_speed_mps": round(self.speed_mps, 3),
            "proximity_confidence_scale": round(self.confidence_scale, 3),
        }


@dataclass(slots=True)
class DynamicProximityPolicyConfig:
    danger_base_m: float = PROXIMITY_DANGER_BASE_M
    danger_speed_gain: float = PROXIMITY_DANGER_SPEED_GAIN
    danger_min_m: float = PROXIMITY_DANGER_MIN_M
    danger_max_m: float = PROXIMITY_DANGER_MAX_M
    warning_base_m: float = PROXIMITY_WARNING_BASE_M
    warning_speed_gain: float = PROXIMITY_WARNING_SPEED_GAIN
    warning_min_m: float = PROXIMITY_WARNING_MIN_M
    warning_max_m: float = PROXIMITY_WARNING_MAX_M
    low_confidence_radius_scale: float = PROXIMITY_LOW_CONFIDENCE_RADIUS_SCALE


class DynamicProximityPolicy:
    """Evaluate worker distance against a speed- and confidence-aware bubble."""

    def __init__(self, config: DynamicProximityPolicyConfig | None = None) -> None:
        self.config = config or DynamicProximityPolicyConfig()

    def evaluate(
        self,
        *,
        distance_m: float,
        speed_mps: float,
        calibration_confidence: float,
    ) -> ProximityPolicyResult:
        confidence_scale = 1.0 + (1.0 - _clamp(calibration_confidence, 0.0, 1.0)) * self.config.low_confidence_radius_scale
        danger_radius = _clamp(
            self.config.danger_base_m + self.config.danger_speed_gain * max(0.0, speed_mps),
            self.config.danger_min_m,
            self.config.danger_max_m,
        ) * confidence_scale
        warning_radius = _clamp(
            self.config.warning_base_m + self.config.warning_speed_gain * max(0.0, speed_mps),
            self.config.warning_min_m,
            self.config.warning_max_m,
        ) * confidence_scale
        warning_radius = max(warning_radius, danger_radius)

        if distance_m <= danger_radius:
            level = ProximityLevel.DANGER
        elif distance_m <= warning_radius:
            level = ProximityLevel.WARNING
        else:
            level = ProximityLevel.CLEAR

        return ProximityPolicyResult(
            level=level,
            distance_m=distance_m,
            danger_radius_m=danger_radius,
            warning_radius_m=warning_radius,
            speed_mps=max(0.0, speed_mps),
            confidence_scale=confidence_scale,
        )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
