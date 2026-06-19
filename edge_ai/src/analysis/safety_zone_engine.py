"""Static camera polygon safety-zone processing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity

Point = tuple[float, float]
Polygon = tuple[Point, ...]


@dataclass(slots=True)
class SafetyZone:
    id: str
    name: str
    zone_type: str
    polygon: Polygon
    source_width: int
    source_height: int
    color: str = "#f97316"
    enabled: bool = True
    priority: int = 100
    rules: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _ObjectZoneState:
    inside: bool = False
    entered_at: float | None = None
    last_seen: float = 0.0
    last_anchor: Point | None = None
    last_emit_at: dict[str, float] = field(default_factory=dict)
    dwell_emitted: bool = False


class SafetyZoneEngine:
    """Evaluate person/forklift tracks against configured camera polygons."""

    def __init__(self, *, stale_state_sec: float = 3.0) -> None:
        self._zones_by_camera: dict[str, list[SafetyZone]] = {}
        self._state: dict[tuple[str, str, str], _ObjectZoneState] = {}
        self._stale_state_sec = stale_state_sec

    def set_camera_zones(self, camera_id: str, raw_zones: Iterable[dict[str, Any]]) -> None:
        zones = []
        for raw in raw_zones:
            zone = self._parse_zone(raw)
            if zone is not None and zone.enabled:
                zones.append(zone)
        zones.sort(key=lambda zone: (zone.priority, zone.name))
        self._zones_by_camera[str(camera_id)] = zones

    def analyze(
        self,
        detections: Iterable[Detection],
        *,
        camera_id: str,
        frame_number: int,
        timestamp: float,
        frame_shape: tuple[int, ...] | None = None,
    ) -> list[HazardEvent]:
        zones = self._zones_by_camera.get(str(camera_id), [])
        if not zones:
            return []

        frame_height = int(frame_shape[0]) if frame_shape else None
        frame_width = int(frame_shape[1]) if frame_shape and len(frame_shape) > 1 else None
        events: list[HazardEvent] = []
        seen_keys: set[tuple[str, str, str]] = set()
        occupancy: dict[str, int] = {zone.id: 0 for zone in zones}

        zone_detections = [d for d in detections if d.class_name in {"person", "forklift"}]
        forklifts = [d for d in zone_detections if d.class_name == "forklift"]

        for det in zone_detections:
            stable_key = self._stable_key(camera_id, det)
            anchor = self._anchor(det)
            for zone in zones:
                polygon = self._scaled_polygon(zone, frame_width=frame_width, frame_height=frame_height)
                zone_key = (str(camera_id), zone.id, stable_key)
                if _is_forklift_zone_driver_exempt(zone, det, forklifts, polygon):
                    self._state.pop(zone_key, None)
                    continue

                seen_keys.add(zone_key)
                state = self._state.setdefault(zone_key, _ObjectZoneState())
                inside = _contains(anchor, polygon)
                crossed = state.last_anchor is not None and _segment_intersects_polygon(state.last_anchor, anchor, polygon)
                if inside:
                    occupancy[zone.id] += 1

                if inside and not state.inside:
                    state.inside = True
                    state.entered_at = timestamp
                    state.dwell_emitted = False
                    events.extend(self._events_for_zone(zone, det, camera_id, frame_number, timestamp, anchor, "enter", 0.0, occupancy[zone.id]))
                elif not inside and state.inside:
                    duration = max(0.0, timestamp - (state.entered_at or timestamp))
                    state.inside = False
                    state.entered_at = None
                    state.dwell_emitted = False
                    events.extend(self._events_for_zone(zone, det, camera_id, frame_number, timestamp, anchor, "exit", duration, occupancy[zone.id]))
                elif crossed and not inside:
                    events.extend(self._events_for_zone(zone, det, camera_id, frame_number, timestamp, anchor, "cross", 0.0, occupancy[zone.id]))

                if inside:
                    duration = max(0.0, timestamp - (state.entered_at or timestamp))
                    dwell_limit = _float_rule(zone.rules, "dwell_time_limit_sec")
                    if dwell_limit is not None and duration >= dwell_limit and not state.dwell_emitted:
                        events.extend(self._events_for_zone(zone, det, camera_id, frame_number, timestamp, anchor, "dwell_time_exceeded", duration, occupancy[zone.id]))
                        state.dwell_emitted = True

                state.last_seen = timestamp
                state.last_anchor = anchor

        for zone in zones:
            threshold = _int_rule(zone.rules, "occupancy_threshold")
            if threshold is not None and occupancy[zone.id] > threshold:
                synthetic = Detection(0, "person", 1.0, (0, 0, 0, 0), track_id=None)
                events.extend(self._events_for_zone(
                    zone, synthetic, camera_id, frame_number, timestamp, (0.0, 0.0),
                    "occupancy_threshold_exceeded", None, occupancy[zone.id], stable_key=f"occupancy:{zone.id}",
                ))

        self._expire_stale_state(timestamp, seen_keys)
        return self._apply_event_cooldowns(events, timestamp)

    def _events_for_zone(
        self,
        zone: SafetyZone,
        det: Detection,
        camera_id: str,
        frame_number: int,
        timestamp: float,
        anchor: Point,
        zone_event_type: str,
        duration_inside_sec: float | None,
        occupancy_count: int,
        stable_key: str | None = None,
    ) -> list[HazardEvent]:
        stable = stable_key or self._stable_key(camera_id, det)
        event_types = self._rule_event_types(zone, det.class_name, zone_event_type)
        severity = _severity(zone.rules.get("severity"))
        events: list[HazardEvent] = []
        for event_type in event_types:
            metadata = {
                "safety_zone": True,
                "safety_zone_id": zone.id,
                "safety_zone_name": zone.name,
                "safety_zone_type": zone.zone_type,
                "zone": zone.name,
                "zone_event_type": zone_event_type,
                "object_class": det.class_name,
                "stable_object_key": stable,
                "duration_inside_sec": round(duration_inside_sec, 3) if duration_inside_sec is not None else None,
                "occupancy_count": occupancy_count,
                "anchor_point": {"x": round(anchor[0], 3), "y": round(anchor[1], 3)},
                "zone_color": zone.color,
                "zone_priority": zone.priority,
                "zone_rules": zone.rules,
            }
            events.append(HazardEvent(
                event_type=event_type,
                severity=severity,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=det.track_id,
                bbox=det.bbox,
                description=self._description(zone, det.class_name, zone_event_type, event_type),
                metadata=metadata,
            ))
        return events

    def _apply_event_cooldowns(self, events: list[HazardEvent], timestamp: float) -> list[HazardEvent]:
        emitted = []
        for event in events:
            meta = event.metadata or {}
            key = (event.camera_id, str(meta.get("safety_zone_id")), str(meta.get("stable_object_key")))
            state = self._state.setdefault(key, _ObjectZoneState(last_seen=timestamp))
            cooldown = _float_rule(meta.get("zone_rules") or {}, "cooldown_sec") or 30.0
            if timestamp - state.last_emit_at.get(event.event_type, 0.0) < cooldown:
                continue
            state.last_emit_at[event.event_type] = timestamp
            emitted.append(event)
        return emitted

    @staticmethod
    def _rule_event_types(zone: SafetyZone, object_class: str, zone_event_type: str) -> list[str]:
        if zone_event_type == "exit":
            return ["zone_exit"]
        if zone_event_type == "cross":
            return ["zone_crossed"]
        if zone_event_type == "occupancy_threshold_exceeded":
            return ["zone_occupancy_threshold_exceeded"]
        if zone_event_type == "dwell_time_exceeded":
            return ["zone_dwell_time_exceeded"]
        denied = set(zone.rules.get("denied_classes") or [])
        allowed = set(zone.rules.get("allowed_classes") or ["person", "forklift"])
        if zone.zone_type in {"danger", "no_entry"} and object_class == "person":
            return ["zone_person_entered"]
        if zone.zone_type == "pedestrian_only" and object_class == "forklift":
            return ["zone_forklift_entered_pedestrian_zone"]
        if zone.zone_type in {"restricted", "forklift_only"} and object_class not in allowed:
            return ["zone_unauthorized_entry"]
        if object_class in denied:
            return ["zone_unauthorized_entry"]
        return ["zone_enter"]

    @staticmethod
    def _description(zone: SafetyZone, object_class: str, zone_event_type: str, event_type: str) -> str:
        if event_type == "zone_person_entered":
            return f"Person entered danger zone: {zone.name}"
        if event_type == "zone_forklift_entered_pedestrian_zone":
            return f"Forklift entered pedestrian zone: {zone.name}"
        if event_type == "zone_unauthorized_entry":
            return f"Unauthorized {object_class} entry into {zone.name}"
        if event_type == "zone_occupancy_threshold_exceeded":
            return f"Zone occupancy threshold exceeded: {zone.name}"
        if event_type == "zone_dwell_time_exceeded":
            return f"Time inside zone exceeded limit: {zone.name}"
        return f"{object_class.title()} {zone_event_type.replace('_', ' ')} zone: {zone.name}"

    @staticmethod
    def _parse_zone(raw: dict[str, Any]) -> SafetyZone | None:
        try:
            polygon = tuple((float(p["x"]), float(p["y"])) for p in raw.get("polygon") or [])
            if len(polygon) < 3:
                return None
            return SafetyZone(
                id=str(raw["id"]),
                name=str(raw.get("name") or raw["id"]),
                zone_type=str(raw.get("zone_type") or "custom"),
                polygon=polygon,
                source_width=int(raw.get("source_width") or 1),
                source_height=int(raw.get("source_height") or 1),
                color=str(raw.get("color") or "#f97316"),
                enabled=bool(raw.get("enabled", True)),
                priority=int(raw.get("priority") or 100),
                rules=dict(raw.get("rules") or {}),
            )
        except Exception:
            return None

    @staticmethod
    def _anchor(det: Detection) -> Point:
        x1, y1, x2, y2 = det.bbox
        if det.class_name == "person":
            return ((x1 + x2) / 2.0, float(y2))
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @staticmethod
    def _stable_key(camera_id: str, det: Detection) -> str:
        del camera_id
        if det.track_id is not None:
            return f"{det.class_name}:{det.track_id}"
        x1, y1, x2, y2 = det.bbox
        return f"{det.class_name}:bbox:{round((x1 + x2) / 20)}:{round((y1 + y2) / 20)}"

    @staticmethod
    def _scaled_polygon(zone: SafetyZone, *, frame_width: int | None, frame_height: int | None) -> Polygon:
        if not frame_width or not frame_height:
            return zone.polygon
        if frame_width == zone.source_width and frame_height == zone.source_height:
            return zone.polygon
        sx = frame_width / max(1, zone.source_width)
        sy = frame_height / max(1, zone.source_height)
        return tuple((x * sx, y * sy) for x, y in zone.polygon)

    def _expire_stale_state(self, timestamp: float, seen_keys: set[tuple[str, str, str]]) -> None:
        for key, state in list(self._state.items()):
            if key in seen_keys:
                continue
            if timestamp - state.last_seen > self._stale_state_sec:
                del self._state[key]


def _severity(raw: Any) -> Severity:
    return {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }.get(str(raw or "High").lower(), Severity.HIGH)


def _is_forklift_zone_driver_exempt(
    zone: SafetyZone,
    det: Detection,
    forklifts: list[Detection],
    zone_polygon: Polygon,
) -> bool:
    if zone.zone_type != "forklift_only" or det.class_name != "person" or not forklifts:
        return False
    person_center = _bbox_center(det.bbox)
    return any(
        _point_inside_bbox(person_center, forklift.bbox)
        and _contains(_bbox_center(forklift.bbox), zone_polygon)
        for forklift in forklifts
    )


def _bbox_center(bbox: tuple[int, int, int, int]) -> Point:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _point_inside_bbox(point: Point, bbox: tuple[int, int, int, int]) -> bool:
    x, y = point
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _float_rule(rules: dict[str, Any], key: str) -> float | None:
    value = rules.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_rule(rules: dict[str, Any], key: str) -> int | None:
    value = _float_rule(rules, key)
    return int(value) if value is not None else None


def _contains(point: Point, polygon: Polygon) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def _segment_intersects_polygon(start: Point, end: Point, polygon: Polygon) -> bool:
    if _contains(start, polygon) or _contains(end, polygon):
        return True
    return any(
        _segments_intersect(start, end, polygon[i], polygon[(i + 1) % len(polygon)])
        for i in range(len(polygon))
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)
