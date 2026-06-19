"""Correlate raw hazards into elevated composite worker-risk events."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

from ..models.hazard_event import HazardEvent
from ..models.severity import Severity


@dataclass(slots=True)
class _SeenEvent:
    event: HazardEvent
    seen_at: float


@dataclass(slots=True)
class _WorkerIdentityState:
    first_seen: float
    last_seen: float
    observations: int = 0


class CompositeHazardEngine:
    """Short-lived same-worker hazard correlation.

    Composite events are intentionally generated before EventAggregator so the
    existing persistence, cooldown, evidence, and delivery layers remain the
    source of truth for final emission.
    """

    def __init__(
        self,
        *,
        temporal_window_sec: float = 2.0,
        max_center_distance_px: float = 180.0,
        composite_cooldown_sec: float = 8.0,
        min_identity_observations: int = 2,
    ) -> None:
        self.temporal_window_sec = temporal_window_sec
        self.max_center_distance_px = max_center_distance_px
        self.composite_cooldown_sec = composite_cooldown_sec
        self.min_identity_observations = max(1, int(min_identity_observations))
        self._recent: dict[tuple[str, int], list[_SeenEvent]] = {}
        self._last_emitted: dict[tuple[str, int, str], float] = {}
        self._identity_state: dict[tuple[str, int], _WorkerIdentityState] = {}

    def process(self, events: Iterable[HazardEvent], timestamp: float) -> list[HazardEvent]:
        source_events = [
            (event, worker_key)
            for event in events
            if (worker_key := self._worker_key(event)) is not None
        ]
        composites: list[HazardEvent] = []
        emitted_this_frame: set[tuple[str, int, str]] = set()

        self._purge(timestamp)
        for event, key in source_events:
            state = self._update_identity_state(key, timestamp)
            bucket = self._recent.setdefault(key, [])
            candidates = [seen.event for seen in bucket if self._is_near(event, seen.event)]
            candidates.append(event)

            if state.observations < self.min_identity_observations:
                bucket.append(_SeenEvent(event=event, seen_at=timestamp))
                continue

            for composite_type, matched in self._match_composites(candidates):
                emit_key = (event.camera_id, key[1], composite_type)
                if emit_key in emitted_this_frame:
                    continue
                composite = self._build_composite(composite_type, matched, event, timestamp, key[1])
                composites.append(composite)
                emitted_this_frame.add(emit_key)
                self._last_emitted[emit_key] = timestamp

            bucket.append(_SeenEvent(event=event, seen_at=timestamp))

        return composites

    @staticmethod
    def suppress_source_events(
        events: Iterable[HazardEvent],
        composite_events: Iterable[HazardEvent],
    ) -> list[HazardEvent]:
        """Drop source events that were represented by a composite hazard."""

        suppressed = {
            (
                source.get("event_type"),
                source.get("frame_number"),
                source.get("track_id"),
                source.get("timestamp"),
            )
            for composite in composite_events
            for source in ((composite.metadata or {}).get("source_events") or [])
            if isinstance(source, dict)
        }
        suppressed_keys = {
            tuple(source.get("aggregation_key"))
            for composite in composite_events
            for source in ((composite.metadata or {}).get("source_events") or [])
            if isinstance(source, dict) and source.get("aggregation_key")
        }
        if not suppressed:
            if not suppressed_keys:
                return list(events)
        return [
            event
            for event in events
            if (
                (
                    event.event_type,
                    event.frame_number,
                    event.track_id,
                    event.timestamp,
                )
                not in suppressed
                and _aggregation_key(event) not in suppressed_keys
            )
        ]

    def _purge(self, now: float) -> None:
        cutoff = now - self.temporal_window_sec
        for key in list(self._recent):
            self._recent[key] = [seen for seen in self._recent[key] if seen.seen_at >= cutoff]
            if not self._recent[key]:
                del self._recent[key]
        cooldown_cutoff = now - self.composite_cooldown_sec
        for key, emitted_at in list(self._last_emitted.items()):
            if emitted_at < cooldown_cutoff:
                del self._last_emitted[key]
        for key, state in list(self._identity_state.items()):
            if state.last_seen < cutoff:
                del self._identity_state[key]

    def _update_identity_state(self, key: tuple[str, int], timestamp: float) -> _WorkerIdentityState:
        state = self._identity_state.get(key)
        if state is None:
            state = _WorkerIdentityState(first_seen=timestamp, last_seen=timestamp, observations=1)
            self._identity_state[key] = state
            return state
        state.last_seen = timestamp
        state.observations += 1
        return state

    def _match_composites(
        self,
        events: list[HazardEvent],
    ) -> list[tuple[str, list[HazardEvent]]]:
        ppe_helmet = [event for event in events if self._is_missing_helmet(event)]
        ppe_vest = [event for event in events if self._is_missing_vest(event)]
        proximity = [event for event in events if self._is_proximity(event)]
        forklift_danger = [event for event in proximity if self._is_forklift_danger(event)]
        fall = [event for event in events if self._is_fall(event)]

        matched: list[tuple[str, list[HazardEvent]]] = []
        if ppe_helmet and forklift_danger:
            matched.append(("COMPOSITE_PPE_FORKLIFT_RISK", [ppe_helmet[-1], forklift_danger[-1]]))
        if ppe_vest and proximity and not forklift_danger:
            matched.append(("COMPOSITE_PPE_PROXIMITY_RISK", [ppe_vest[-1], proximity[-1]]))
        if fall and proximity:
            matched.append(("COMPOSITE_FALL_PROXIMITY_RISK", [fall[-1], proximity[-1]]))
        return matched

    def _build_composite(
        self,
        event_type: str,
        source_events: list[HazardEvent],
        anchor: HazardEvent,
        timestamp: float,
        worker_track_id: int,
    ) -> HazardEvent:
        forklift_source = next((event for event in source_events if self._is_proximity(event)), None)
        ppe_source = next((event for event in source_events if "ppe" in event.event_type.lower()), None)
        forklift_metadata = forklift_source.metadata if forklift_source and isinstance(forklift_source.metadata, dict) else {}
        ppe_metadata = ppe_source.metadata if ppe_source and isinstance(ppe_source.metadata, dict) else {}
        source_metadata = [
            event.metadata if isinstance(event.metadata, dict) else {}
            for event in source_events
        ]
        forklift_track_id = forklift_metadata.get("forklift_track_id")
        correlation_id = _correlation_id(
            camera_id=anchor.camera_id,
            event_type=event_type,
            worker_track_id=worker_track_id,
            forklift_track_id=forklift_track_id,
        )
        source_refs = [
            {
                "event_type": event.event_type,
                "severity": event.severity.name,
                "frame_number": event.frame_number,
                "timestamp": event.timestamp,
                "track_id": event.track_id,
                "worker_track_id": _metadata_worker_track_id(event),
                "forklift_track_id": (
                    (event.metadata or {}).get("forklift_track_id")
                    if isinstance(event.metadata, dict) else None
                ),
                "bbox": event.bbox,
                "description": event.description,
                "aggregation_key": _aggregation_key(event),
            }
            for event in source_events
        ]
        metadata = {
            **ppe_metadata,
            **forklift_metadata,
            "composite": True,
            "correlation_id": correlation_id,
            "worker_track_id": worker_track_id,
            "worker_track_id_valid": True,
            "worker_track_id_fallback": False,
            "worker_track_id_source": "composite_verified",
            "forklift_track_id": forklift_track_id,
            "source_events": source_refs,
            "source_event_types": [event.event_type for event in source_events],
            "component_hazards": [_component_hazard(event) for event in source_events],
            "correlation_window_sec": self.temporal_window_sec,
            "component_metadata": source_metadata,
        }
        return HazardEvent(
            event_type=event_type,
            severity=Severity.CRITICAL,
            camera_id=anchor.camera_id,
            timestamp=timestamp,
            frame_number=anchor.frame_number,
            track_id=worker_track_id,
            bbox=anchor.bbox,
            description=self._description(event_type, source_events),
            metadata=metadata,
            camera_name=anchor.camera_name,
            worker_id=anchor.worker_id,
            worker_gpu_id=anchor.worker_gpu_id,
        )

    def _is_near(self, first: HazardEvent, second: HazardEvent) -> bool:
        if first.camera_id != second.camera_id or self._worker_key(first) != self._worker_key(second):
            return False
        if first.bbox is None or second.bbox is None:
            return True
        return self._center_distance(first.bbox, second.bbox) <= self.max_center_distance_px

    @staticmethod
    def _worker_key(event: HazardEvent) -> Optional[tuple[str, int]]:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        if metadata.get("composite_eligible") is not True:
            return None
        if metadata.get("worker_track_id_valid") is not True:
            return None
        if metadata.get("worker_track_id_fallback") is not False:
            return None
        source = str(metadata.get("worker_track_id_source") or "").lower()
        if source in {"fallback", "single_track_fallback", "unknown", "unmatched"}:
            return None
        raw_tid = metadata.get("worker_track_id")
        if raw_tid is None:
            return None
        try:
            tid = int(raw_tid)
        except (TypeError, ValueError):
            return None
        if tid <= 0:
            return None
        return event.camera_id, tid

    @staticmethod
    def _center_distance(
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
    ) -> float:
        ax = (a[0] + a[2]) / 2.0
        ay = (a[1] + a[3]) / 2.0
        bx = (b[0] + b[2]) / 2.0
        by = (b[1] + b[3]) / 2.0
        return math.hypot(ax - bx, ay - by)

    @staticmethod
    def _is_missing_helmet(event: HazardEvent) -> bool:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        missing_items = metadata.get("missing_ppe_items") or metadata.get("ppe_items") or []
        lowered = event.event_type.lower()
        return (
            "helmet" in lowered
            or "no_helmet" in lowered
            or any("helmet" in str(item).lower() for item in missing_items)
        )

    @staticmethod
    def _is_missing_vest(event: HazardEvent) -> bool:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        missing_items = metadata.get("missing_ppe_items") or metadata.get("ppe_items") or []
        lowered = event.event_type.lower()
        return (
            "vest" in lowered
            or "no_vest" in lowered
            or any("vest" in str(item).lower() for item in missing_items)
        )

    @staticmethod
    def _is_proximity(event: HazardEvent) -> bool:
        lowered = event.event_type.lower()
        return "proximity" in lowered or "forklift" in lowered

    @staticmethod
    def _is_forklift_danger(event: HazardEvent) -> bool:
        lowered = event.event_type.lower()
        risk = str((event.metadata or {}).get("proximity_risk") or "").lower()
        return "forklift" in lowered and ("danger" in lowered or "danger" in risk or event.severity >= Severity.HIGH)

    @staticmethod
    def _is_fall(event: HazardEvent) -> bool:
        return "fall" in event.event_type.lower()

    @staticmethod
    def _description(event_type: str, source_events: list[HazardEvent]) -> str:
        source = ", ".join(event.event_type for event in source_events)
        return f"{event_type}: correlated hazards detected ({source})"


def _metadata_worker_track_id(event: HazardEvent) -> Optional[int]:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    raw_tid = metadata.get("worker_track_id")
    if raw_tid is None:
        return None
    try:
        return int(raw_tid)
    except (TypeError, ValueError):
        return None


def _aggregation_key(event: HazardEvent) -> tuple:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    lowered = event.event_type.lower()
    if metadata.get("composite") and metadata.get("correlation_id"):
        return (event.camera_id, event.event_type, "correlation", metadata["correlation_id"])
    operational_case_id = metadata.get("operational_case_id")
    if lowered == "forklift_proximity" and operational_case_id:
        return (event.camera_id, "forklift_proximity", "case", operational_case_id)
    if "proximity" in lowered or "forklift" in lowered:
        base_key = metadata.get("operational_case_key") or metadata.get("proximity_pair_key")
        if isinstance(base_key, (list, tuple)):
            return (event.camera_id, "forklift_proximity", "base", tuple(base_key))
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


def _correlation_id(
    *,
    camera_id: str,
    event_type: str,
    worker_track_id: int,
    forklift_track_id: object,
) -> str:
    forklift_part = f"forklift:{forklift_track_id}" if forklift_track_id is not None else "forklift:unknown"
    return f"{camera_id}:worker:{worker_track_id}:{forklift_part}:{event_type}"


def _component_hazard(event: HazardEvent) -> dict:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    lowered = event.event_type.lower()
    missing_items = metadata.get("missing_ppe_items") or metadata.get("ppe_items") or []
    if missing_items:
        label = "Missing " + ", ".join(str(item).replace("_", " ").title() for item in missing_items)
        category = "PPE"
    elif "helmet" in lowered:
        label = "Missing Helmet"
        category = "PPE"
    elif "vest" in lowered:
        label = "Missing Vest"
        category = "PPE"
    elif "forklift" in lowered or "proximity" in lowered:
        risk = str(metadata.get("proximity_risk") or "").replace("_", " ").title()
        label = f"Forklift Proximity {risk}".strip()
        category = "Forklift"
    else:
        label = event.event_type.replace("_", " ").title()
        category = "Hazard"
    return {
        "label": label,
        "category": category,
        "event_type": event.event_type,
        "severity": event.severity.name,
        "track_id": event.track_id,
        "worker_track_id": _metadata_worker_track_id(event),
        "frame_number": event.frame_number,
        "timestamp": event.timestamp,
        "bbox": event.bbox,
    }
