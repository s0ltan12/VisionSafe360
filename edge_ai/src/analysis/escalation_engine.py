"""Time-based active hazard escalation."""
from __future__ import annotations

from typing import Optional

from ..config.settings import (
    ESCALATION_CRITICAL_SEC,
    ESCALATION_ENABLED,
    ESCALATION_HIGH_SEC,
    ESCALATION_MEDIUM_SEC,
)
from ..models.severity import Severity


class EscalationEngine:
    """Auto-escalate severity based on incident duration."""

    def __init__(self) -> None:
        self._last_by_key: dict[tuple, Severity] = {}

    def check(
        self,
        key: tuple,
        active_since: float,
        current_severity: Severity,
        now: float,
    ) -> Optional[Severity]:
        if not ESCALATION_ENABLED:
            return None

        elapsed = max(0.0, now - active_since)
        target = current_severity
        if elapsed >= ESCALATION_CRITICAL_SEC:
            target = Severity.CRITICAL
        elif elapsed >= ESCALATION_HIGH_SEC:
            target = Severity.HIGH
        elif elapsed >= ESCALATION_MEDIUM_SEC:
            target = Severity.MEDIUM

        last = max(current_severity, self._last_by_key.get(key, current_severity))
        if target > last:
            self._last_by_key[key] = target
            return target
        return None

    def clear(self, key: tuple) -> None:
        self._last_by_key.pop(key, None)
