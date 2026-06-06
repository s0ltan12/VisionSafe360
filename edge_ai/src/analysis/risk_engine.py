"""Dynamic forklift proximity risk scoring."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from ..config.settings import (
    COLLISION_ACTOR_RADIUS_M,
    FORKLIFT_OVERSPEED_CRITICAL_FACTOR,
    FORKLIFT_OVERSPEED_MIN_CONFIDENCE,
    FORKLIFT_OVERSPEED_MIN_TRACK_AGE_SEC,
    FORKLIFT_OVERSPEED_PIXEL_MAX_SEVERITY,
    FORKLIFT_OVERSPEED_SPEED_DEADBAND_MPS,
    FORKLIFT_PEDESTRIAN_ZONE_LIMIT_MPS,
    FORKLIFT_SPEED_LIMIT_MPS,
    FORKLIFT_SPEED_WARNING_FACTOR,
    PROXIMITY_EVENT_MONITOR_SCORE,
    RISK_CRITICAL_SCORE,
    RISK_DANGER_SCORE,
    RISK_PERSISTENCE_FULL_SEC,
    RISK_SPEED_REFERENCE_MPS,
    RISK_TTC_CRITICAL_SEC,
    RISK_TTC_DANGER_SEC,
    RISK_TTC_WARNING_SEC,
    RISK_WARNING_SCORE,
)
from .collision_prediction import RelativeMotionClass
from .dynamic_zone_engine import ZoneType

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    MONITOR = "monitor"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


@dataclass(slots=True)
class ZoneFlags:
    active_zones: tuple[str, ...] = ()

    def any_active(self) -> bool:
        return bool(self.active_zones)


@dataclass(slots=True)
class OverspeedResult:
    speed_mps: float
    limit_mps: float
    severity: str
    context: str
    distance_to_worker_m: float | None
    speed_source: str = "ground_plane"
    speed_confidence: float = 1.0
    track_age_seconds: float = 999.0
    raw_speed_mps: float = 0.0
    smoothed_speed_mps: float = 0.0

    def metadata(self) -> dict:
        return {
            "speed_mps": round(self.speed_mps, 3),
            "limit_mps": round(self.limit_mps, 3),
            "overspeed_severity": self.severity,
            "overspeed_context": self.context,
            "distance_to_worker_m": (
                None if self.distance_to_worker_m is None else round(self.distance_to_worker_m, 3)
            ),
            "speed_source": self.speed_source,
            "speed_confidence": round(self.speed_confidence, 3),
            "track_age_seconds": round(self.track_age_seconds, 3),
            "raw_speed_mps": round(self.raw_speed_mps, 3),
            "smoothed_speed_mps": round(self.smoothed_speed_mps, 3),
        }


@dataclass(slots=True)
class RiskEngineConfig:
    monitor_threshold: float = PROXIMITY_EVENT_MONITOR_SCORE
    warning_score: float = RISK_WARNING_SCORE
    danger_score: float = RISK_DANGER_SCORE
    critical_score: float = RISK_CRITICAL_SCORE
    ttc_warning_sec: float = RISK_TTC_WARNING_SEC
    ttc_danger_sec: float = RISK_TTC_DANGER_SEC
    ttc_critical_sec: float = RISK_TTC_CRITICAL_SEC
    ttc_force_critical_sec: float = 2.0
    speed_reference_mps: float = RISK_SPEED_REFERENCE_MPS
    persistence_full_sec: float = RISK_PERSISTENCE_FULL_SEC
    actor_radius_m: float = COLLISION_ACTOR_RADIUS_M
    close_distance_danger_m: float = 2.0
    close_zone_critical_m: float = 1.0
    immediate_critical_distance_m: float = 0.5
    valid_distance_confidence: float = 0.5
    high_confidence_distance: float = 0.75
    low_cal_danger_distance_m: float = 2.0
    low_cal_critical_distance_m: float = 0.5
    forklift_speed_limit_mps: float = FORKLIFT_SPEED_LIMIT_MPS
    forklift_pedestrian_zone_limit_mps: float = FORKLIFT_PEDESTRIAN_ZONE_LIMIT_MPS
    speed_warning_factor: float = FORKLIFT_SPEED_WARNING_FACTOR
    overspeed_critical_factor: float = FORKLIFT_OVERSPEED_CRITICAL_FACTOR
    overspeed_min_track_age_sec: float = FORKLIFT_OVERSPEED_MIN_TRACK_AGE_SEC
    overspeed_speed_deadband_mps: float = FORKLIFT_OVERSPEED_SPEED_DEADBAND_MPS
    overspeed_min_confidence: float = FORKLIFT_OVERSPEED_MIN_CONFIDENCE
    overspeed_pixel_max_severity: str = FORKLIFT_OVERSPEED_PIXEL_MAX_SEVERITY


@dataclass(slots=True)
class RiskResult:
    risk_score: float
    risk_level: RiskLevel
    driver_gated: bool
    components: dict[str, float]

    def metadata(self) -> dict:
        return {
            "risk_engine": "dynamic_multifactor",
            "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level.value,
            "risk_driver_gate": self.driver_gated,
            "risk_components": {
                key: round(value, 3)
                for key, value in self.components.items()
            },
        }


class RiskEngine:
    """Fuse distance, motion, TTC, zones, persistence, and confidence."""

    def __init__(self, config: RiskEngineConfig | None = None) -> None:
        self.config = config or RiskEngineConfig()

    def evaluate(
        self,
        *,
        distance_m: float,
        danger_radius_m: float,
        warning_radius_m: float,
        forklift_speed_mps: float,
        worker_speed_mps: float,
        ttc_seconds: float | None,
        closest_approach_distance_m: float,
        relative_motion_class: RelativeMotionClass | str,
        zone_type: ZoneType | str,
        persistence_sec: float,
        detection_confidence: float,
        tracking_confidence: float,
        calibration_confidence: float,
        predicted_collision: bool,
        driver_suppressed: bool,
    ) -> RiskResult:
        if driver_suppressed:
            return RiskResult(
                risk_score=0.0,
                risk_level=RiskLevel.MONITOR,
                driver_gated=True,
                components={
                    "driver_gate": 100.0,
                    "distance": 0.0,
                    "ttc": 0.0,
                    "zone": 0.0,
                    "speed": 0.0,
                    "relative_motion": 0.0,
                    "persistence": 0.0,
                    "confidence": 0.0,
                },
            )

        components = {
            "distance": self._distance_score(distance_m, danger_radius_m, warning_radius_m),
            "ttc": self._ttc_score(ttc_seconds, closest_approach_distance_m, predicted_collision),
            "zone": self._zone_score(zone_type),
            "speed": self._speed_score(forklift_speed_mps, worker_speed_mps, distance_m),
            "relative_motion": self._relative_motion_score(relative_motion_class),
            "persistence": self._persistence_score(persistence_sec),
        }
        base_score = sum(components.values())
        components["confidence"] = self._effective_confidence_score(
            base_score,
            self._confidence_score(
                detection_confidence,
                tracking_confidence,
                calibration_confidence,
            ),
        )
        score = sum(components.values())
        if (
            distance_m is not None
            and distance_m <= 5.0
            and score < self.config.monitor_threshold
        ):
            components["proximity_floor_minimum_monitor"] = max(
                0.0,
                self.config.monitor_threshold - score,
            )
            score = self.config.monitor_threshold
            logger.debug(
                "PROXIMITY_FLOOR: both detected at %.1fm -> minimum monitor applied",
                distance_m,
            )
        score = self._apply_safety_floors(
            score=score,
            components=components,
            distance_m=distance_m,
            ttc_seconds=ttc_seconds,
            closest_approach_distance_m=closest_approach_distance_m,
            zone_type=zone_type,
            calibration_confidence=calibration_confidence,
            predicted_collision=predicted_collision,
        )
        if predicted_collision and ttc_seconds is not None:
            if ttc_seconds <= self.config.ttc_force_critical_sec:
                score = max(score, self.config.critical_score)
            elif ttc_seconds <= self.config.ttc_danger_sec:
                score = max(score, self.config.danger_score)
        score = _clamp(score, 0.0, 100.0)

        return RiskResult(
            risk_score=score,
            risk_level=self._level_for(score),
            driver_gated=False,
            components=components,
        )

    def _distance_score(self, distance_m: float, danger_radius_m: float, warning_radius_m: float) -> float:
        danger = max(0.0, danger_radius_m)
        warning = max(danger, warning_radius_m)
        distance = max(0.0, distance_m)
        if distance <= danger:
            return 35.0
        if distance <= warning:
            span = max(1e-9, warning - danger)
            return 15.0 + 20.0 * (warning - distance) / span
        return 0.0

    def _ttc_score(
        self,
        ttc_seconds: float | None,
        closest_approach_distance_m: float,
        predicted_collision: bool,
    ) -> float:
        if ttc_seconds is not None:
            if ttc_seconds <= self.config.ttc_critical_sec:
                return 25.0
            if ttc_seconds <= self.config.ttc_danger_sec:
                return 18.0
            if ttc_seconds <= self.config.ttc_warning_sec:
                return 12.0
            return 5.0
        if predicted_collision or closest_approach_distance_m <= self.config.actor_radius_m:
            return 8.0
        return 0.0

    @staticmethod
    def _zone_score(zone_type: ZoneType | str) -> float:
        zone = _zone_value(zone_type)
        return {
            ZoneType.FOOTPRINT.value: 30.0,
            ZoneType.FORK_LOAD.value: 28.0,
            ZoneType.FRONT_DANGER.value: 16.0,
            ZoneType.REAR_DANGER.value: 14.0,
            ZoneType.SIDE_CRUSH.value: 25.0,
            ZoneType.CLEAR.value: 0.0,
        }.get(zone, 0.0)

    def check_overspeed(
        self,
        forklift_speed_mps: float,
        distance_m: float | None,
        zone_flags: ZoneFlags,
        *,
        track_age_seconds: float | None = None,
        speed_confidence: float | None = None,
        speed_source: str = "ground_plane",
        raw_speed_mps: float | None = None,
    ) -> OverspeedResult | None:
        speed = max(0.0, forklift_speed_mps)
        age = 999.0 if track_age_seconds is None else max(0.0, float(track_age_seconds))
        confidence = 1.0 if speed_confidence is None else _clamp(float(speed_confidence), 0.0, 1.0)
        source = str(speed_source or "unknown")
        raw_speed = speed if raw_speed_mps is None else max(0.0, float(raw_speed_mps))

        if speed < self.config.overspeed_speed_deadband_mps:
            return None
        if age < self.config.overspeed_min_track_age_sec:
            return None
        if confidence < self.config.overspeed_min_confidence:
            return None

        zone_active = zone_flags.any_active() if zone_flags is not None else False
        if (distance_m is not None and distance_m <= 5.0) or zone_active:
            limit = self.config.forklift_pedestrian_zone_limit_mps
            context = "pedestrian_zone"
        else:
            limit = self.config.forklift_speed_limit_mps
            context = "general"

        warning_threshold = limit * self.config.speed_warning_factor
        critical_threshold = limit * self.config.overspeed_critical_factor
        if speed < warning_threshold:
            return None
        if speed >= critical_threshold:
            severity = "critical"
        elif speed >= limit:
            severity = "danger"
        else:
            severity = "warning"
        if source != "ground_plane" and severity == "critical":
            severity = self._cap_pixel_fallback_severity(severity)

        logger.warning(
            "OVERSPEED | speed=%.2fm/s | limit=%.2fm/s | severity=%s | "
            "context=%s | source=%s | confidence=%.2f | track_age=%.2fs",
            speed,
            limit,
            severity,
            context,
            source,
            confidence,
            age,
        )
        return OverspeedResult(
            speed_mps=speed,
            limit_mps=limit,
            severity=severity,
            context=context,
            distance_to_worker_m=distance_m,
            speed_source=source,
            speed_confidence=confidence,
            track_age_seconds=age,
            raw_speed_mps=raw_speed,
            smoothed_speed_mps=speed,
        )

    def _cap_pixel_fallback_severity(self, severity: str) -> str:
        cap = str(self.config.overspeed_pixel_max_severity or "danger").lower()
        rank = {"warning": 1, "danger": 2, "critical": 3}
        if rank.get(severity, 0) > rank.get(cap, 2):
            return cap if cap in rank else "danger"
        return severity

    def _speed_score(
        self,
        forklift_speed_mps: float,
        worker_speed_mps: float,
        distance_m: float = 999.0,
    ) -> float:
        base_forklift = min(
            20.0,
            max(0.0, forklift_speed_mps)
            / max(1e-9, self.config.speed_reference_mps)
            * 20.0,
        )
        distance_multiplier = max(1.0, 3.0 / max(distance_m, 0.5))
        forklift_score = min(25.0, base_forklift * distance_multiplier)

        worker_score = min(
            5.0,
            max(0.0, worker_speed_mps)
            / max(1e-9, self.config.speed_reference_mps)
            * 5.0,
        )
        return forklift_score + worker_score

    @staticmethod
    def _relative_motion_score(relative_motion_class: RelativeMotionClass | str) -> float:
        motion = _motion_value(relative_motion_class)
        return {
            RelativeMotionClass.APPROACHING.value: 10.0,
            RelativeMotionClass.CROSSING.value: 9.0,
            RelativeMotionClass.PARALLEL.value: 3.0,
            RelativeMotionClass.STATIONARY.value: 0.0,
            RelativeMotionClass.DEPARTING.value: 0.0,
        }.get(motion, 0.0)

    def _persistence_score(self, persistence_sec: float) -> float:
        return min(5.0, max(0.0, persistence_sec) / max(1e-9, self.config.persistence_full_sec) * 5.0)

    @staticmethod
    def _confidence_score(
        detection_confidence: float,
        tracking_confidence: float,
        calibration_confidence: float,
    ) -> float:
        confidence = (
            _clamp(detection_confidence, 0.0, 1.0)
            + _clamp(tracking_confidence, 0.0, 1.0)
            + _clamp(calibration_confidence, 0.0, 1.0)
        ) / 3.0
        return 5.0 * confidence

    def _effective_confidence_score(self, base_score: float, confidence_score: float) -> float:
        if base_score < self.config.warning_score:
            return 0.0
        if base_score < self.config.danger_score:
            return min(confidence_score, max(0.0, self.config.danger_score - base_score - 1e-3))
        if base_score < self.config.critical_score:
            return min(confidence_score, max(0.0, self.config.critical_score - base_score - 1e-3))
        return confidence_score

    def _apply_safety_floors(
        self,
        *,
        score: float,
        components: dict[str, float],
        distance_m: float,
        ttc_seconds: float | None,
        closest_approach_distance_m: float,
        zone_type: ZoneType | str,
        calibration_confidence: float,
        predicted_collision: bool,
    ) -> float:
        zone = _zone_value(zone_type)
        hazardous_zone = zone in {
            ZoneType.FOOTPRINT.value,
            ZoneType.FORK_LOAD.value,
            ZoneType.FRONT_DANGER.value,
            ZoneType.SIDE_CRUSH.value,
        }
        strong_zone = zone in {
            ZoneType.FOOTPRINT.value,
            ZoneType.FORK_LOAD.value,
            ZoneType.SIDE_CRUSH.value,
        }
        distance_valid = self._distance_floor_allowed(calibration_confidence, zone)
        low_calibration = calibration_confidence < self.config.valid_distance_confidence
        floor = 0.0

        if distance_valid and distance_m <= self.config.close_distance_danger_m:
            floor = max(floor, self.config.danger_score)
            components["safety_floor_close_distance"] = max(
                0.0,
                self.config.danger_score - score,
            )

        if distance_valid and distance_m <= self.config.close_zone_critical_m and hazardous_zone:
            floor = max(floor, self.config.critical_score)
            components["safety_floor_close_hazard_zone"] = max(
                0.0,
                self.config.critical_score - max(score, floor),
            )

        if distance_valid and distance_m <= self.config.immediate_critical_distance_m:
            floor = max(floor, self.config.critical_score)
            components["safety_floor_immediate_distance"] = max(
                0.0,
                self.config.critical_score - max(score, floor),
            )

        if (
            low_calibration
            and distance_m <= self.config.low_cal_danger_distance_m
        ):
            floor = max(floor, self.config.danger_score)
            components["safety_floor_low_cal_close_distance"] = max(
                0.0,
                self.config.danger_score - max(score, floor),
            )

        if (
            low_calibration
            and distance_m <= self.config.low_cal_critical_distance_m
        ):
            floor = max(floor, self.config.critical_score)
            components["safety_floor_low_cal_immediate_distance"] = max(
                0.0,
                self.config.critical_score - max(score, floor),
            )

        if strong_zone:
            floor = max(floor, self.config.danger_score)
            components["safety_floor_strong_zone"] = max(
                0.0,
                self.config.danger_score - max(score, floor),
            )

        if (
            predicted_collision
            and closest_approach_distance_m <= self.config.actor_radius_m
            and distance_valid
            and distance_m <= self.config.close_distance_danger_m
        ):
            floor = max(floor, self.config.critical_score)
            components["safety_floor_cpa_overlap"] = max(
                0.0,
                self.config.critical_score - max(score, floor),
            )

        if predicted_collision and ttc_seconds is not None and ttc_seconds <= self.config.ttc_force_critical_sec:
            floor = max(floor, self.config.critical_score)
            components["safety_floor_ttc_critical"] = max(
                0.0,
                self.config.critical_score - max(score, floor),
            )

        return max(score, floor)

    def _distance_floor_allowed(self, calibration_confidence: float, zone: str) -> bool:
        if calibration_confidence >= self.config.valid_distance_confidence:
            return True
        if calibration_confidence >= self.config.high_confidence_distance:
            return True
        return zone in {
            ZoneType.FOOTPRINT.value,
            ZoneType.FORK_LOAD.value,
            ZoneType.SIDE_CRUSH.value,
        }

    def _level_for(self, score: float) -> RiskLevel:
        if score >= self.config.critical_score:
            return RiskLevel.CRITICAL
        if score >= self.config.danger_score:
            return RiskLevel.DANGER
        if score >= self.config.warning_score:
            return RiskLevel.WARNING
        return RiskLevel.MONITOR


def _zone_value(zone_type: ZoneType | str) -> str:
    if isinstance(zone_type, ZoneType):
        return zone_type.value
    return str(zone_type)


def _motion_value(relative_motion_class: RelativeMotionClass | str) -> str:
    if isinstance(relative_motion_class, RelativeMotionClass):
        return relative_motion_class.value
    return str(relative_motion_class)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
