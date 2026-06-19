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

import hashlib
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
    HAZARD_COOLDOWN_SEC,
    PPE_MISSING_PERSISTENCE_SEC,
    PROXIMITY_POST_RESOLUTION_COOLDOWN_SEC,
    PROXIMITY_PERSISTENCE_SEC,
    PROXIMITY_REOPEN_GRACE_SEC,
    PROXIMITY_RESOLUTION_GRACE_SEC,
    SMART_COOLDOWN_RESET_ON_ESCALATION,
)
from .escalation_engine import EscalationEngine
from .severity_engine import SeverityEngine

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


@dataclass
class ProximityCaseState:
    """Operational lifecycle state for one worker/forklift exposure."""
    base_key: Tuple
    operational_case_id: str
    created_at: float
    last_seen: float
    current_stage: Optional[str] = None
    max_stage_rank: int = -1
    resolved_at: Optional[float] = None


class EventAggregator:
    """Persistence + cooldown + deduplication for hazard events."""

    def __init__(self, hazard_cooldown_sec: Optional[float] = None) -> None:
        self._pending: Dict[CooldownKey, PendingEvent] = {}
        self._active: Dict[CooldownKey, ActiveEvent] = {}
        self._cooldowns: Dict[CooldownKey, float] = {}
        self._proximity_cases: Dict[Tuple, ProximityCaseState] = {}
        self._hazard_cooldown_sec = max(0.0, float(hazard_cooldown_sec)) if hazard_cooldown_sec is not None else HAZARD_COOLDOWN_SEC
        self._severity_engine = SeverityEngine()
        self._escalation_engine = EscalationEngine()

    def process(
        self,
        raw_events: List[HazardEvent],
        timestamp: float,
    ) -> List[HazardEvent]:
        """Process raw events through persistence → cooldown → aggregation."""
        raw_events = [
            event
            for event in raw_events
            if not (isinstance(event.metadata, dict) and event.metadata.get("suppress_event"))
        ]
        raw_events = [
            self._prepare_proximity_event(event, timestamp)
            for event in raw_events
        ]
        composite_source_keys = {
            source_key
            for event in raw_events
            if self._is_composite(event)
            for source_key in self._source_keys_for_composite(event)
        }
        if composite_source_keys:
            for source_key in composite_source_keys:
                self._clear_key(source_key)
            raw_events = [
                event for event in raw_events
                if self._is_composite(event) or self._make_key(event) not in composite_source_keys
            ]

        emitted: List[HazardEvent] = []
        seen_keys: set = set()

        for event in raw_events:
            key = self._make_key(event)
            seen_keys.add(key)

            if key in self._active:
                act = self._active[key]
                active_duration = timestamp - act.emitted_at
                within_update_window = active_duration < EVENT_AGGREGATION_WINDOW_SEC
                computed_severity = self._severity_engine.compute(
                    event,
                    self._zone_config_for(event),
                    active_duration,
                    concurrent_events=len(self._active),
                )
                event = self._with_severity(event, computed_severity, timestamp, active_duration)
                act.last_update = timestamp
                act.event = event
                lifecycle = self._event_lifecycle(event)
                if self._is_operational_proximity(event) and lifecycle in {
                    "escalated",
                    "deescalated",
                    "reopened",
                }:
                    emitted.append(self._lifecycle_event(event, lifecycle, timestamp, active_duration))
                    continue
                if (
                    not self._is_operational_proximity(event)
                    and not within_update_window
                    and timestamp >= self._cooldowns.get(key, 0.0)
                ):
                    repeated = self._with_lifecycle(event, "repeated", timestamp)
                    emitted.append(repeated)
                    self._active[key] = ActiveEvent(
                        event=repeated,
                        emitted_at=timestamp,
                        last_update=timestamp,
                        max_severity=repeated.severity,
                    )
                    self._cooldowns[key] = timestamp + self._cooldown_for(event)
                    continue
                timed_escalation = self._escalation_engine.check(
                    key,
                    act.emitted_at,
                    act.max_severity,
                    timestamp,
                )
                next_severity = max(event.severity, timed_escalation or event.severity)
                can_emit_raw_update = within_update_window and act.update_count < EVENT_MAX_UPDATES_PER_WINDOW
                should_emit = next_severity > act.max_severity and (timed_escalation is not None or can_emit_raw_update)
                if should_emit:
                    act.max_severity = next_severity
                    act.update_count += 1
                    escalated = self._escalated_event(event, next_severity, timestamp, active_duration)
                    if SMART_COOLDOWN_RESET_ON_ESCALATION:
                        self._cooldowns[key] = timestamp + self._cooldown_for(event)
                    emitted.append(escalated)
                continue

            if key in self._cooldowns and timestamp < self._cooldowns[key]:
                continue

            if self._is_operational_proximity(event) and self._event_lifecycle(event) == "reopened":
                event = self._with_lifecycle(event, "reopened", timestamp)
                emitted.append(event)
                self._active[key] = ActiveEvent(
                    event=event,
                    emitted_at=timestamp,
                    last_update=timestamp,
                    max_severity=event.severity,
                )
                self._cooldowns[key] = timestamp + self._cooldown_for(event)
                continue

            persistence_req = self._persistence_for(event.event_type)
            if persistence_req > 0:
                if key in self._pending:
                    pend = self._pending[key]
                    pend.last_seen = timestamp
                    pend.frame_count += 1
                    if timestamp - pend.first_seen >= persistence_req:
                        active_duration = timestamp - pend.first_seen
                        severity = self._severity_engine.compute(
                            event,
                            self._zone_config_for(event),
                            active_duration,
                            concurrent_events=max(1, len(self._active) + 1),
                        )
                        event = self._with_severity(event, severity, timestamp, active_duration)
                        event = self._with_lifecycle(event, "created", timestamp)
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
                event = self._with_severity(
                    event,
                    self._severity_engine.compute(
                        event,
                        self._zone_config_for(event),
                        0.0,
                        concurrent_events=max(1, len(self._active) + 1),
                    ),
                    timestamp,
                    0.0,
                )
                event = self._with_lifecycle(event, "created", timestamp)
                emitted.append(event)
                self._active[key] = ActiveEvent(
                    event=event,
                    emitted_at=timestamp,
                    last_update=timestamp,
                    max_severity=event.severity,
                )
                self._cooldowns[key] = timestamp + self._cooldown_for(event)

        # Promote operational proximity candidates that satisfied persistence
        # during a brief detector gap before applying stale pending cleanup.
        for k, pend in list(self._pending.items()):
            if k in seen_keys:
                continue
            if not self._is_operational_proximity(pend.event):
                continue
            persistence_req = self._persistence_for(pend.event.event_type)
            if persistence_req <= 0 or timestamp - pend.first_seen < persistence_req:
                continue
            if timestamp - pend.last_seen > 0.5:
                continue
            active_duration = timestamp - pend.first_seen
            event = self._with_severity(
                pend.event,
                self._severity_engine.compute(
                    pend.event,
                    self._zone_config_for(pend.event),
                    active_duration,
                    concurrent_events=max(1, len(self._active) + 1),
                ),
                timestamp,
                active_duration,
            )
            event = self._with_lifecycle(event, "created", timestamp)
            emitted.append(event)
            self._active[k] = ActiveEvent(
                event=event,
                emitted_at=timestamp,
                last_update=timestamp,
                max_severity=event.severity,
            )
            self._cooldowns[k] = timestamp + self._cooldown_for(event)
            del self._pending[k]

        # Expire pending events not seen this frame
        stale_pending = [
            k for k, v in self._pending.items()
            if k not in seen_keys and timestamp - v.last_seen > 0.5
        ]
        for k in stale_pending:
            del self._pending[k]

        # Expire or explicitly resolve active hazards once they disappear.
        for k, v in list(self._active.items()):
            if k in seen_keys:
                continue
            stale_for = timestamp - v.last_update
            if self._is_operational_proximity(v.event):
                if stale_for > PROXIMITY_RESOLUTION_GRACE_SEC:
                    resolved = self._resolved_event(v.event, timestamp, stale_for)
                    emitted.append(resolved)
                    self._mark_proximity_resolved(v.event, timestamp)
                    del self._active[k]
                    self._cooldowns.pop(k, None)
                    self._escalation_engine.clear(k)
                continue
            if stale_for > EVENT_AGGREGATION_WINDOW_SEC:
                del self._active[k]
                self._escalation_engine.clear(k)

        # Expire old cooldowns
        stale_cooldowns = [k for k, t in self._cooldowns.items() if timestamp > t]
        for k in stale_cooldowns:
            del self._cooldowns[k]

        return emitted

    @staticmethod
    def _make_key(event: HazardEvent) -> CooldownKey:
        """Build composite key for deduplication."""
        metadata = event.metadata or {}
        lowered = event.event_type.lower()
        if lowered == "forklift_overspeed":
            forklift_track_id = metadata.get("forklift_track_id")
            return (
                event.camera_id,
                "forklift_overspeed",
                "forklift",
                forklift_track_id if forklift_track_id is not None else event.track_id or 0,
            )
        if metadata.get("composite") and metadata.get("correlation_id"):
            return (
                event.camera_id,
                event.event_type,
                "correlation",
                metadata["correlation_id"],
            )
        if metadata.get("safety_zone") and metadata.get("safety_zone_id"):
            return (
                event.camera_id,
                event.event_type,
                "zone",
                metadata.get("safety_zone_id"),
                "object",
                metadata.get("stable_object_key") or event.track_id or 0,
            )
        operational_case_id = metadata.get("operational_case_id")
        if lowered == "forklift_proximity" and operational_case_id:
            return (
                event.camera_id,
                "forklift_proximity",
                "case",
                operational_case_id,
            )
        if "proximity" in lowered or "forklift" in lowered:
            base_key = EventAggregator._proximity_base_key(event)
            if base_key is not None:
                return (
                    event.camera_id,
                    "forklift_proximity",
                    "base",
                    base_key,
                )
            forklift_track_id = metadata.get("forklift_track_id")
            if forklift_track_id is not None:
                return (
                    event.camera_id,
                    event.event_type,
                    "forklift",
                    forklift_track_id,
                    "worker",
                    event.track_id or 0,
                )
        return (event.camera_id, event.event_type, event.track_id or 0)

    @staticmethod
    def _persistence_for(event_type: str) -> float:
        """Required persistence duration in seconds before event emission."""
        if event_type.startswith("COMPOSITE_"):
            return 0.0
        if event_type == "forklift_overspeed":
            return 0.0
        if event_type.startswith("zone_"):
            return 0.0
        if "fall" in event_type:
            return FALL_PERSISTENCE_SEC  # 0 — fall has its own state machine
        if event_type.startswith("ppe_") or event_type in {"no_helmet", "no_vest"}:
            return PPE_MISSING_PERSISTENCE_SEC
        if "proximity" in event_type or "forklift" in event_type:
            return PROXIMITY_PERSISTENCE_SEC
        return 0.0  # posture, etc.

    def _cooldown_for(self, event: HazardEvent) -> float:
        """Cooldown duration after emission."""
        if "fall" in event.event_type:
            return self._hazard_cooldown_sec
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        if event.event_type.startswith("zone_"):
            rules = metadata.get("zone_rules") if isinstance(metadata.get("zone_rules"), dict) else {}
            try:
                return float(rules.get("cooldown_sec", self._hazard_cooldown_sec))
            except (TypeError, ValueError):
                return self._hazard_cooldown_sec
        return self._hazard_cooldown_sec

    @staticmethod
    def _zone_config_for(event: HazardEvent) -> dict:
        metadata = event.metadata or {}
        zone_config = metadata.get("zone_config")
        if isinstance(zone_config, dict):
            return zone_config
        risk_level = metadata.get("zone_risk") or metadata.get("risk_level")
        return {"risk_level": risk_level} if risk_level else {}

    @staticmethod
    def _with_severity(
        event: HazardEvent,
        severity: Severity,
        timestamp: float,
        active_duration_sec: float,
    ) -> HazardEvent:
        if severity == event.severity and "active_duration_sec" in (event.metadata or {}):
            return event
        return HazardEvent(
            event_type=event.event_type,
            severity=severity,
            camera_id=event.camera_id,
            timestamp=timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=event.description,
            metadata={**event.metadata, "active_duration_sec": round(active_duration_sec, 3)},
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    @staticmethod
    def _escalated_event(
        event: HazardEvent,
        severity: Severity,
        timestamp: float,
        active_duration_sec: float,
    ) -> HazardEvent:
        return HazardEvent(
            event_type=event.event_type,
            severity=severity,
            camera_id=event.camera_id,
            timestamp=timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=f"{event.description} [escalated]",
            metadata={
                **event.metadata,
                "escalated": True,
                "active_duration_sec": round(active_duration_sec, 3),
                "escalated_to": severity.name,
            },
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    def _prepare_proximity_event(self, event: HazardEvent, timestamp: float) -> HazardEvent:
        if not self._is_proximity_event(event):
            return event

        base_key = self._proximity_base_key(event)
        if base_key is None:
            return event

        state = self._proximity_cases.get(base_key)
        lifecycle = self._event_lifecycle(event)
        if state is None:
            state = self._new_proximity_case(base_key, timestamp)
            self._proximity_cases[base_key] = state
            lifecycle = "created"
        elif state.resolved_at is not None:
            elapsed = timestamp - state.resolved_at
            if elapsed <= PROXIMITY_REOPEN_GRACE_SEC:
                state.resolved_at = None
                lifecycle = "reopened"
            elif elapsed >= PROXIMITY_POST_RESOLUTION_COOLDOWN_SEC:
                state = self._new_proximity_case(base_key, timestamp)
                self._proximity_cases[base_key] = state
                lifecycle = "created"
            else:
                return self._with_proximity_case_metadata(
                    event,
                    state,
                    lifecycle="suppressed_post_resolution_cooldown",
                    timestamp=timestamp,
                    suppress=True,
                )

        stage = self._proximity_stage(event)
        if lifecycle in {"created", "active_update"} and state.current_stage is not None and stage is not None:
            previous_rank = _stage_rank(state.current_stage)
            current_rank = _stage_rank(stage)
            if current_rank > previous_rank:
                lifecycle = "escalated"
            elif current_rank < previous_rank:
                lifecycle = "deescalated"

        if stage is not None:
            state.current_stage = stage
            state.max_stage_rank = max(state.max_stage_rank, _stage_rank(stage))
        state.last_seen = timestamp

        return self._with_proximity_case_metadata(event, state, lifecycle=lifecycle, timestamp=timestamp)

    @staticmethod
    def _is_proximity_event(event: HazardEvent) -> bool:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        lowered = event.event_type.lower()
        return (
            metadata.get("case_type") == "forklift_proximity"
            or lowered == "forklift_proximity"
            or lowered.startswith("forklift_proximity_")
        )

    @staticmethod
    def _is_operational_proximity(event: HazardEvent) -> bool:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        return bool(metadata.get("operational_case_id")) and (
            metadata.get("case_type") == "forklift_proximity"
            or event.event_type.lower() == "forklift_proximity"
        )

    @staticmethod
    def _proximity_base_key(event: HazardEvent) -> Optional[Tuple]:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        raw = metadata.get("operational_case_key") or metadata.get("proximity_pair_key")
        if isinstance(raw, (list, tuple)):
            return tuple(_freeze_key_part(item) for item in raw)
        forklift_track_id = metadata.get("forklift_track_id")
        worker_track_id = metadata.get("worker_track_id", event.track_id)
        if forklift_track_id is None or worker_track_id is None:
            return None
        return (event.camera_id, forklift_track_id, worker_track_id)

    def _new_proximity_case(self, base_key: Tuple, timestamp: float) -> ProximityCaseState:
        return ProximityCaseState(
            base_key=base_key,
            operational_case_id=_proximity_case_id(base_key, timestamp),
            created_at=timestamp,
            last_seen=timestamp,
        )

    @staticmethod
    def _with_proximity_case_metadata(
        event: HazardEvent,
        state: ProximityCaseState,
        *,
        lifecycle: str,
        timestamp: float,
        suppress: bool = False,
    ) -> HazardEvent:
        metadata = dict(event.metadata or {})
        metadata.update(
            {
                "case_type": "forklift_proximity",
                "operational_case_id": state.operational_case_id,
                "operational_case_key": list(state.base_key),
                "operational_case_created_at": round(state.created_at, 3),
                "event_lifecycle": lifecycle,
                "lifecycle": lifecycle,
                "case_last_seen_at": round(timestamp, 3),
            }
        )
        if suppress:
            metadata["suppress_event"] = True
        return HazardEvent(
            event_type="forklift_proximity",
            severity=event.severity,
            camera_id=event.camera_id,
            timestamp=event.timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=event.description,
            metadata=metadata,
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    @staticmethod
    def _event_lifecycle(event: HazardEvent) -> str:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        return str(metadata.get("event_lifecycle") or metadata.get("lifecycle") or "active_update")

    @staticmethod
    def _proximity_stage(event: HazardEvent) -> Optional[str]:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        stage = metadata.get("proximity_alert_stage") or metadata.get("risk_level") or metadata.get("proximity_risk")
        return str(stage).lower() if stage is not None else None

    @staticmethod
    def _with_lifecycle(event: HazardEvent, lifecycle: str, timestamp: float) -> HazardEvent:
        metadata = {**event.metadata, "event_lifecycle": lifecycle, "lifecycle": lifecycle}
        return HazardEvent(
            event_type=event.event_type,
            severity=event.severity,
            camera_id=event.camera_id,
            timestamp=timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=event.description,
            metadata=metadata,
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    @staticmethod
    def _lifecycle_event(
        event: HazardEvent,
        lifecycle: str,
        timestamp: float,
        active_duration_sec: float,
    ) -> HazardEvent:
        metadata = {
            **event.metadata,
            "event_lifecycle": lifecycle,
            "lifecycle": lifecycle,
            "active_duration_sec": round(active_duration_sec, 3),
        }
        return HazardEvent(
            event_type=event.event_type,
            severity=event.severity,
            camera_id=event.camera_id,
            timestamp=timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=event.description,
            metadata=metadata,
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    @staticmethod
    def _resolved_event(event: HazardEvent, timestamp: float, stale_for: float) -> HazardEvent:
        metadata = {
            **event.metadata,
            "event_lifecycle": "resolved",
            "lifecycle": "resolved",
            "resolved": True,
            "resolution_grace_sec": PROXIMITY_RESOLUTION_GRACE_SEC,
            "stale_for_sec": round(stale_for, 3),
        }
        return HazardEvent(
            event_type=event.event_type,
            severity=event.severity,
            camera_id=event.camera_id,
            timestamp=timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=f"{event.description} [resolved]",
            metadata=metadata,
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    def _mark_proximity_resolved(self, event: HazardEvent, timestamp: float) -> None:
        base_key = self._proximity_base_key(event)
        if base_key is None:
            return
        state = self._proximity_cases.get(base_key)
        if state is not None:
            state.resolved_at = timestamp
            state.last_seen = timestamp

    @staticmethod
    def _is_composite(event: HazardEvent) -> bool:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        return bool(metadata.get("composite"))

    @staticmethod
    def _source_keys_for_composite(event: HazardEvent) -> set[CooldownKey]:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        source_events = metadata.get("source_events")
        if not isinstance(source_events, list):
            return set()
        keys: set[CooldownKey] = set()
        for source in source_events:
            if not isinstance(source, dict):
                continue
            key = source.get("aggregation_key")
            if isinstance(key, (list, tuple)):
                key_tuple = tuple(key)
                keys.add(key_tuple)
                normalized = _legacy_proximity_key_to_base(key_tuple)
                if normalized is not None:
                    keys.add(normalized)
        return keys

    def _clear_key(self, key: CooldownKey) -> None:
        self._pending.pop(key, None)
        self._active.pop(key, None)
        self._cooldowns.pop(key, None)
        self._escalation_engine.clear(key)
        if len(key) == 4 and key[1] == "forklift_proximity" and key[2] == "base":
            for active_key, active in list(self._active.items()):
                if self._proximity_base_key(active.event) == key[3]:
                    self._active.pop(active_key, None)
                    self._cooldowns.pop(active_key, None)
                    self._escalation_engine.clear(active_key)
            for pending_key, pending in list(self._pending.items()):
                if self._proximity_base_key(pending.event) == key[3]:
                    self._pending.pop(pending_key, None)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def active_count(self) -> int:
        return len(self._active)


def _freeze_key_part(value):
    if isinstance(value, list):
        return tuple(_freeze_key_part(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_key_part(item) for item in value)
    return value


def _proximity_case_id(base_key: Tuple, timestamp: float) -> str:
    camera_id, forklift_key, worker_key = base_key
    epoch = int(timestamp)
    raw = f"{camera_id}|{forklift_key}|{worker_key}|{epoch}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return (
        f"prox:{_case_part(camera_id)}:"
        f"forklift:{_case_part(forklift_key)}:"
        f"worker:{_case_part(worker_key)}:"
        f"epoch:{epoch}:"
        f"{digest}"
    )


def _case_part(value) -> str:
    return str(value).replace(" ", "_").replace("/", "-").replace(":", "-")


def _stage_rank(stage: str) -> int:
    return {
        "monitor": 0,
        "near_miss": 1,
        "warning": 2,
        "danger": 3,
        "critical": 4,
    }.get(str(stage).lower(), -1)


def _legacy_proximity_key_to_base(key: Tuple) -> Optional[Tuple]:
    if len(key) == 6 and str(key[1]).lower().startswith("forklift_proximity_"):
        return (key[0], "forklift_proximity", "base", (key[0], key[3], key[5]))
    return None
