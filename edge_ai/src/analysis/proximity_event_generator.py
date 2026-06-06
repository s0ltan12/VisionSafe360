"""Risk-score driven forklift proximity event generation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..config.settings import (
    PROXIMITY_EVENT_DEESCALATION_HOLD_SEC,
    PROXIMITY_EVENT_MONITOR_SCORE,
    PROXIMITY_EVENT_NEAR_MISS_SCORE,
    RISK_CRITICAL_SCORE,
    RISK_DANGER_SCORE,
    RISK_WARNING_SCORE,
)
from ..models.severity import Severity
from .risk_engine import RiskResult


class ProximityEventStage(str, Enum):
    MONITOR = "monitor"
    NEAR_MISS = "near_miss"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class ProximityLifecycle(str, Enum):
    CREATED = "created"
    ACTIVE_UPDATE = "active_update"
    ESCALATED = "escalated"
    DEESCALATED = "deescalated"


@dataclass(slots=True)
class ProximityEventGeneratorConfig:
    monitor_score: float = PROXIMITY_EVENT_MONITOR_SCORE
    near_miss_score: float = PROXIMITY_EVENT_NEAR_MISS_SCORE
    warning_score: float = RISK_WARNING_SCORE
    danger_score: float = RISK_DANGER_SCORE
    critical_score: float = RISK_CRITICAL_SCORE
    deescalation_hold_sec: float = PROXIMITY_EVENT_DEESCALATION_HOLD_SEC


@dataclass(slots=True)
class ProximityEventDecision:
    stage: ProximityEventStage
    candidate_stage: ProximityEventStage
    event_type: str
    severity: Severity
    deescalation_held: bool
    lifecycle: ProximityLifecycle
    previous_stage: ProximityEventStage | None

    def metadata(self) -> dict:
        return {
            "proximity_event_policy": "risk_score",
            "proximity_alert_stage": self.stage.value,
            "proximity_candidate_stage": self.candidate_stage.value,
            "proximity_event_deescalation_held": self.deescalation_held,
            "event_lifecycle": self.lifecycle.value,
            "proximity_previous_stage": self.previous_stage.value if self.previous_stage else None,
        }


@dataclass(slots=True)
class _PairEventState:
    stage: ProximityEventStage
    changed_at: float
    last_seen: float


class ProximityEventGenerator:
    """Map risk scores to a canonical proximity event with lifecycle metadata."""

    def __init__(self, config: ProximityEventGeneratorConfig | None = None) -> None:
        self.config = config or ProximityEventGeneratorConfig()
        self._states: dict[tuple, _PairEventState] = {}

    def decide(
        self,
        *,
        pair_key: tuple,
        risk_result: RiskResult,
        timestamp: float,
    ) -> ProximityEventDecision | None:
        candidate = self._candidate_stage(risk_result.risk_score)
        if candidate is None:
            return None

        state = self._states.get(pair_key)
        deescalation_held = False
        stage = candidate
        previous_stage = state.stage if state is not None else None
        lifecycle = ProximityLifecycle.CREATED
        if state is None:
            self._states[pair_key] = _PairEventState(
                stage=stage,
                changed_at=timestamp,
                last_seen=timestamp,
            )
        else:
            if _rank(candidate) < _rank(state.stage) and timestamp - state.changed_at < self.config.deescalation_hold_sec:
                stage = state.stage
                deescalation_held = True
            if stage != state.stage:
                lifecycle = (
                    ProximityLifecycle.ESCALATED
                    if _rank(stage) > _rank(state.stage)
                    else ProximityLifecycle.DEESCALATED
                )
                state.stage = stage
                state.changed_at = timestamp
            else:
                lifecycle = ProximityLifecycle.ACTIVE_UPDATE
            state.last_seen = timestamp

        return ProximityEventDecision(
            stage=stage,
            candidate_stage=candidate,
            event_type="forklift_proximity",
            severity=_severity_for(stage),
            deescalation_held=deescalation_held,
            lifecycle=lifecycle,
            previous_stage=previous_stage,
        )

    def _candidate_stage(self, risk_score: float) -> ProximityEventStage | None:
        score = max(0.0, risk_score)
        if score >= self.config.critical_score:
            return ProximityEventStage.CRITICAL
        if score >= self.config.danger_score:
            return ProximityEventStage.DANGER
        if score >= self.config.warning_score:
            return ProximityEventStage.WARNING
        if score >= self.config.near_miss_score:
            return ProximityEventStage.NEAR_MISS
        if score >= self.config.monitor_score:
            return ProximityEventStage.MONITOR
        return None

    def clear(self, pair_key: tuple) -> None:
        self._states.pop(pair_key, None)


def _severity_for(stage: ProximityEventStage) -> Severity:
    return {
        ProximityEventStage.MONITOR: Severity.LOW,
        ProximityEventStage.NEAR_MISS: Severity.MEDIUM,
        ProximityEventStage.WARNING: Severity.MEDIUM,
        ProximityEventStage.DANGER: Severity.HIGH,
        ProximityEventStage.CRITICAL: Severity.CRITICAL,
    }[stage]


def _rank(stage: ProximityEventStage) -> int:
    return {
        ProximityEventStage.MONITOR: 0,
        ProximityEventStage.NEAR_MISS: 1,
        ProximityEventStage.WARNING: 2,
        ProximityEventStage.DANGER: 3,
        ProximityEventStage.CRITICAL: 4,
    }[stage]
