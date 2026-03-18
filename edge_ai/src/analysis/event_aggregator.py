"""
VisionSafe 360 — EventAggregator

Persistence + deduplication + cooldown layer that sits between raw hazard
detections and final event emission.  Prevents false-alarm flooding.

Design:
  - Each raw event is keyed by (camera_id, hazard_type, track_id).
  - Events must persist for a minimum duration before they are emitted.
  - After emission, a cooldown prevents re-emission of the same key.
  - During an active event window, severity can be escalated (not re-emitted).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..models.hazard_event import HazardEvent
from ..models.severity import Severity
from ..config.settings import (
    EVENT_AGGREGATION_WINDOW_SEC,
    EVENT_MAX_UPDATES_PER_WINDOW,
    FALL_COOLDOWN_SEC,
    FALL_PERSISTENCE_SEC,
)

logger = logging.getLogger(__name__)

# Type alias for composite cooldown keys
CooldownKey = Tuple  # (cam_id, event_type, track_id)


@dataclass
class PendingEvent:
    """An event in persistence phase (not yet emitted)."""
    event: HazardEvent
    first_seen: float
    last_seen: float
    frame_count: int = 1


@dataclass
class ActiveEvent:
    """An event that has been emitted and is in its aggregation window."""
    event: HazardEvent
    emitted_at: float
    last_update: float
    update_count: int = 0
    max_severity: Severity = Severity.LOW


class EventAggregator:
    """Persistence + cooldown + deduplication for hazard events."""

    def __init__(self) -> None:
        self._pending: Dict[CooldownKey, PendingEvent] = {}
        self._active: Dict[CooldownKey, ActiveEvent] = {}
        self._cooldowns: Dict[CooldownKey, float] = {}

    def process(
        self,
        raw_events: List[HazardEvent],
        timestamp: float,
    ) -> List[HazardEvent]:
        """Process raw events through persistence → cooldown → aggregation."""
        emitted: List[HazardEvent] = []
        seen_keys: set = set()

        for event in raw_events:
            key = self._make_key(event)
            seen_keys.add(key)

            if key in self._active:
                act = self._active[key]
                if timestamp - act.emitted_at < EVENT_AGGREGATION_WINDOW_SEC:
                    if (event.severity > act.max_severity
                            and act.update_count < EVENT_MAX_UPDATES_PER_WINDOW):
                        act.max_severity = event.severity
                        act.last_update = timestamp
                        act.update_count += 1
                        escalated = HazardEvent(
                            event_type=event.event_type,
                            severity=event.severity,
                            camera_id=event.camera_id,
                            timestamp=timestamp,
                            frame_number=event.frame_number,
                            track_id=event.track_id,
                            bbox=event.bbox,
                            description=f"{event.description} [escalated]",
                            metadata={**event.metadata, "escalated": True},
                        )
                        emitted.append(escalated)
                    continue
                else:
                    del self._active[key]

            if key in self._cooldowns and timestamp < self._cooldowns[key]:
                continue

            persistence_req = self._persistence_for(event.event_type)
            if persistence_req > 0:
                if key in self._pending:
                    pend = self._pending[key]
                    pend.last_seen = timestamp
                    pend.frame_count += 1
                    if timestamp - pend.first_seen >= persistence_req:
                        emitted.append(event)
                        self._active[key] = ActiveEvent(
                            event=event,
                            emitted_at=timestamp,
                            last_update=timestamp,
                            max_severity=event.severity,
                        )
                        self._cooldowns[key] = timestamp + self._cooldown_for(event)
                        del self._pending[key]
                else:
                    self._pending[key] = PendingEvent(
                        event=event,
                        first_seen=timestamp,
                        last_seen=timestamp,
                    )
            else:
                emitted.append(event)
                self._active[key] = ActiveEvent(
                    event=event,
                    emitted_at=timestamp,
                    last_update=timestamp,
                    max_severity=event.severity,
                )
                self._cooldowns[key] = timestamp + self._cooldown_for(event)

        # Expire pending events not seen this frame
        stale_pending = [
            k for k, v in self._pending.items()
            if k not in seen_keys and timestamp - v.last_seen > 0.5
        ]
        for k in stale_pending:
            del self._pending[k]

        # Expire old cooldowns
        stale_cooldowns = [k for k, t in self._cooldowns.items() if timestamp > t]
        for k in stale_cooldowns:
            del self._cooldowns[k]

        return emitted

    @staticmethod
    def _make_key(event: HazardEvent) -> CooldownKey:
        """Build composite key for deduplication."""
        return (event.camera_id, event.event_type, event.track_id or 0)

    @staticmethod
    def _persistence_for(event_type: str) -> float:
        """Required persistence duration in seconds before event emission."""
        if "fall" in event_type:
            return FALL_PERSISTENCE_SEC  # 0 — fall has its own state machine
        return 0.0  # posture, etc.

    @staticmethod
    def _cooldown_for(event: HazardEvent) -> float:
        """Cooldown duration after emission."""
        if "fall" in event.event_type:
            return FALL_COOLDOWN_SEC
        return 30.0  # default

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def active_count(self) -> int:
        return len(self._active)
