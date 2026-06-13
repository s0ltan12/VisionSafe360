"""Composite edge severity scoring."""
from __future__ import annotations

from ..config.settings import (
    SEVERITY_COUNT_WEIGHT,
    SEVERITY_DURATION_WEIGHT,
    SEVERITY_ZONE_WEIGHT,
)
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity


class SeverityEngine:
    """Score severity from hazard type, zone risk, duration, proximity, and count."""

    def compute(
        self,
        event: HazardEvent,
        zone_config: dict | None = None,
        active_duration_sec: float = 0.0,
        concurrent_events: int = 1,
    ) -> Severity:
        base = float(event.severity)
        score = (
            base
            + self._zone_risk_score(zone_config or {}) * SEVERITY_ZONE_WEIGHT
            + self._hazard_type_score(event.event_type)
            + self._duration_score(active_duration_sec) * SEVERITY_DURATION_WEIGHT
            + self._count_score(concurrent_events) * SEVERITY_COUNT_WEIGHT
            + self._proximity_score(event)
        )
        return max(event.severity, self._score_to_severity(score))

    @staticmethod
    def _zone_risk_score(zone_config: dict) -> float:
        risk = str(zone_config.get("risk_level", "")).upper()
        return {
            "LOW": 0.0,
            "MEDIUM": 0.25,
            "HIGH": 0.5,
            "CRITICAL": 0.9,
        }.get(risk, 0.0)

    @staticmethod
    def _hazard_type_score(event_type: str) -> float:
        lowered = event_type.lower()
        if "fall" in lowered:
            return 0.9
        if "danger" in lowered or "collision" in lowered:
            return 0.6
        if "forklift" in lowered or "proximity" in lowered:
            return 0.35
        if "ppe" in lowered or "helmet" in lowered or "vest" in lowered:
            return 0.15
        return 0.0

    @staticmethod
    def _duration_score(duration_sec: float) -> float:
        if duration_sec >= 300:
            return 0.9
        if duration_sec >= 180:
            return 0.6
        if duration_sec >= 60:
            return 0.3
        return 0.0

    @staticmethod
    def _count_score(concurrent_events: int) -> float:
        if concurrent_events >= 4:
            return 0.6
        if concurrent_events >= 2:
            return 0.25
        return 0.0

    @staticmethod
    def _proximity_score(event: HazardEvent) -> float:
        metadata = event.metadata or {}
        if metadata.get("risk_engine") == "dynamic_multifactor":
            return 0.0
        risk = str(metadata.get("proximity_risk") or metadata.get("risk") or "").lower()
        if "danger" in risk or "critical" in risk:
            return 0.5
        if "warning" in risk:
            return 0.2
        return 0.0

    @staticmethod
    def _score_to_severity(score: float) -> Severity:
        if score >= 4.0:
            return Severity.CRITICAL
        if score >= 3.0:
            return Severity.HIGH
        if score >= 2.0:
            return Severity.MEDIUM
        return Severity.LOW
