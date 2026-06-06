"""
VisionSafe 360 - ProximityAnalyzer

Rule-based forklift proximity hazards from detector outputs.

Inputs:
- Person detections (tracked from pose model)
- Forklift detections (from optional second detect model)

Outputs:
- Risk-derived forklift proximity HazardEvents:
  monitor, near_miss, warning, danger, critical.
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..config.settings import (
    DISTANCE_FALLBACK_METERS_PER_PIXEL,
    FORKLIFT_DEDUP_CENTER_RATIO,
    FORKLIFT_DEDUP_IOU,
    FORKLIFT_OVERSPEED_CONFIRMATION_SEC,
    PROXIMITY_RESOLUTION_GRACE_SEC,
    PROXIMITY_DANGER_PX,
    PROXIMITY_WARNING_PX,
    EventTypes,
)
from ..models.detection import Detection
from ..models.hazard_event import HazardEvent
from ..models.severity import Severity
from .collision_prediction import CollisionPredictionEngine
from .driver_suppression import DriverSuppression
from .distance_engine import DistanceEngine
from .dynamic_zone_engine import DynamicZoneEngine
from .forklift_tracker import ForkliftTracker
from .motion_engine import MotionEngine
from .proximity_event_generator import ProximityEventGenerator
from .proximity_event_generator import ProximityEventStage
from .proximity_policy import DynamicProximityPolicy
from .proximity_policy import ProximityLevel
from .risk_engine import OverspeedResult, RiskEngine, ZoneFlags

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ProximityRiskContext:
    zone_result: object
    collision_result: object
    policy_result: object
    risk_result: object
    tracking_confidence: float


@dataclass(slots=True)
class _OverspeedState:
    first_seen: float
    last_seen: float
    severity: str
    context: str
    confirmed: bool = False


@dataclass(slots=True)
class _WorkerSurrogateState:
    surrogate_id: int
    bbox: Tuple[int, int, int, int]
    center: Tuple[float, float]
    first_seen: float
    last_seen: float


def _center(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _distance_px(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _bottom_center(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x1, _y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, float(y2))


def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class ProximityAnalyzer:
    """Compute forklift-person proximity hazards from detections."""

    def __init__(
        self,
        danger_px: float = PROXIMITY_DANGER_PX,
        warning_px: float = PROXIMITY_WARNING_PX,
        calibration_mgr=None,
    ) -> None:
        self._danger_px = float(danger_px)
        self._warning_px = max(float(warning_px), self._danger_px)
        self._driver_suppression = DriverSuppression()
        self._forklift_tracker = ForkliftTracker()
        self._forklift_motion = MotionEngine()
        self._worker_motion = MotionEngine()
        self._distance_engine = DistanceEngine(calibration_mgr)
        self._proximity_policy = DynamicProximityPolicy()
        self._zone_engine = DynamicZoneEngine()
        self._collision_engine = CollisionPredictionEngine()
        self._risk_engine = RiskEngine()
        self._event_generator = ProximityEventGenerator()
        self._pair_first_seen: dict[tuple, float] = {}
        self._pair_last_seen: dict[tuple, float] = {}
        self._overspeed_states: dict[tuple, _OverspeedState] = {}
        self._worker_surrogates: dict[tuple[str, int], _WorkerSurrogateState] = {}
        self._next_worker_surrogate_id = 1

    def prepare_detections(
        self,
        detections: List[Detection],
        timestamp: float,
    ) -> List[Detection]:
        """Return one canonical tracked forklift representation per object.

        Raw proximity detections may contain overlapping forklift-class aliases.
        This method de-duplicates those boxes, applies the forklift tracker, and
        returns the only forklift objects downstream analysis/UI should consume.
        """
        persons = [d for d in detections if d.class_name == "person"]
        forklifts = _dedupe_forklifts([d for d in detections if d.class_name == "forklift"])
        self._forklift_tracker.update(forklifts, timestamp)
        return persons + forklifts

    def forklift_telemetry_events(
        self,
        detections: List[Detection],
        *,
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        """Return render-only forklift speed telemetry for the video overlay."""
        events: list[HazardEvent] = []
        for forklift in detections:
            if forklift.class_name != "forklift":
                continue
            track_key = ("forklift", forklift.track_id or id(forklift))
            point = _bottom_center(forklift.bbox)
            motion = self._forklift_motion.get(track_key)
            if motion is None or motion.timestamp < timestamp:
                motion = self._forklift_motion.update(
                    track_key,
                    point,
                    timestamp,
                    point_m=None,
                )
            events.append(HazardEvent(
                event_type="forklift_telemetry",
                severity=Severity.LOW,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=forklift.track_id,
                bbox=forklift.bbox,
                description=f"Forklift speed {motion.speed_mps:.2f}m/s",
                metadata={
                    "render_only": True,
                    "suppress_event": True,
                    "forklift_track_id": forklift.track_id,
                    "forklift_bbox": forklift.bbox,
                    **motion.metadata("forklift"),
                },
            ))
        return events

    def distance_telemetry_events(
        self,
        detections: List[Detection],
        *,
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        """Return render-only worker/forklift distance lines for the video overlay.

        These events never represent an operational alert.  They keep the
        distance line live even when the proximity risk is below persistence or
        monitor thresholds.
        """
        persons = [d for d in detections if d.class_name == "person"]
        forklifts = [d for d in detections if d.class_name == "forklift"]
        if not persons or not forklifts:
            return []

        events: list[HazardEvent] = []
        for person in persons:
            candidates = [
                (
                    self._distance_engine.compute(
                        camera_id=camera_id,
                        worker_bbox=person.bbox,
                        forklift_bbox=forklift.bbox,
                        detection_confidence=min(person.confidence, forklift.confidence),
                    ),
                    forklift,
                )
                for forklift in forklifts
            ]
            distance_result, forklift = min(candidates, key=lambda item: item[0].distance_m)
            events.append(HazardEvent(
                event_type="forklift_distance_telemetry",
                severity=Severity.LOW,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=person.track_id,
                bbox=person.bbox,
                description=f"Forklift distance {distance_result.distance_m:.2f}m",
                metadata={
                    "case_type": "forklift_distance_telemetry",
                    "render_only": True,
                    "suppress_event": True,
                    "forklift_track_id": forklift.track_id,
                    "worker_track_id": person.track_id,
                    "forklift_bbox": forklift.bbox,
                    **distance_result.metadata(),
                },
            ))
        return events

    def overspeed_events(
        self,
        detections: List[Detection],
        *,
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        """Return standalone forklift overspeed hazards, independent of proximity."""
        events: list[HazardEvent] = []
        persons = [d for d in detections if d.class_name == "person"]
        for forklift in detections:
            if forklift.class_name != "forklift":
                continue
            motion = self._forklift_motion_snapshot(forklift, timestamp)
            nearest_worker_distance_m, distance_confidence = self._nearest_worker_distance_context(
                camera_id,
                forklift,
                persons,
            )
            speed_confidence = self._speed_confidence(motion, distance_confidence)
            overspeed = self._risk_engine.check_overspeed(
                forklift_speed_mps=motion.speed_mps,
                distance_m=nearest_worker_distance_m,
                zone_flags=ZoneFlags(),
                track_age_seconds=motion.age_seconds,
                speed_confidence=speed_confidence,
                speed_source=motion.speed_source,
                raw_speed_mps=motion.raw_speed_mps,
            )
            if overspeed is None:
                self._clear_overspeed_state(camera_id, forklift)
                continue
            if not self._overspeed_confirmed(camera_id, forklift, overspeed, timestamp):
                continue
            events.append(
                self._emit_overspeed_event(
                    overspeed,
                    camera_id=camera_id,
                    frame_number=frame_number,
                    timestamp=timestamp,
                    forklift=forklift,
                )
            )
        return events

    @staticmethod
    def _assign_track_id(
        person_bbox: Tuple[int, int, int, int],
        tracked_people: List[Detection],
    ) -> Optional[int]:
        track_id, _method, _fallback = ProximityAnalyzer._assign_track_id_with_method(
            person_bbox,
            tracked_people,
        )
        return track_id

    @staticmethod
    def _assign_track_id_with_method(
        person_bbox: Tuple[int, int, int, int],
        tracked_people: List[Detection],
    ) -> tuple[Optional[int], str, bool]:
        """Match untracked person bbox to a tracked pose person by IoU or distance.

        Returns None when no plausible match is found; callers should treat that
        as an unattributed hazard rather than guessing a worker.
        """
        # 1. Try matching with normal IoU
        best_tid = None
        best_iou = 0.2
        for p in tracked_people:
            if p.track_id is None:
                continue
            iou = _iou(person_bbox, p.bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = p.track_id
        if best_tid is not None:
            return best_tid, "pose_iou", False

        # 2. Try matching with very low IoU (generous)
        best_iou = 0.02
        for p in tracked_people:
            if p.track_id is None:
                continue
            iou = _iou(person_bbox, p.bbox)
            if iou > best_iou:
                best_iou = iou
                best_tid = p.track_id
        if best_tid is not None:
            return best_tid, "pose_low_iou", False

        # 3. Try matching with center distance (within 250 pixels)
        min_dist = 250.0
        px, py = _center(person_bbox)
        for p in tracked_people:
            if p.track_id is None:
                continue
            tx, ty = _center(p.bbox)
            dist = math.hypot(px - tx, py - ty)
            if dist < min_dist:
                min_dist = dist
                best_tid = p.track_id
        if best_tid is not None:
            return best_tid, "pose_center_distance", False

        # 4. If exactly one tracked person exists in the frame, assign their track ID
        valid_tracks = [p.track_id for p in tracked_people if p.track_id is not None]
        if len(valid_tracks) == 1:
            return valid_tracks[0], "single_track_fallback", True

        return None, "unmatched", True

    def analyze(
        self,
        detections: List[Detection],
        tracked_pose_people: List[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
        detections_are_prepared: bool = False,
    ) -> List[HazardEvent]:
        if not detections_are_prepared:
            detections = self.prepare_detections(detections, timestamp)
        forklifts = [d for d in detections if d.class_name == "forklift"]
        persons = [d for d in detections if d.class_name == "person"]

        if not forklifts:
            return []
        if not persons:
            return self.overspeed_events(
                detections,
                camera_id=camera_id,
                frame_number=frame_number,
                timestamp=timestamp,
            )

        events: List[HazardEvent] = []
        used_worker_surrogates: set[int] = set()

        for person in persons:
            track_id = person.track_id
            track_method = "direct"
            track_fallback = False
            if track_id is None:
                track_id, track_method, track_fallback = self._assign_track_id_with_method(
                    person.bbox,
                    tracked_pose_people,
                )
                if track_id is not None:
                    person.track_id = track_id
            has_stable_worker_track = (
                track_id is not None
                and int(track_id) > 0
                and not track_fallback
            )
            worker_identity_key, worker_identity_source, worker_surrogate_id = self._worker_identity_key(
                camera_id=camera_id,
                person=person,
                timestamp=timestamp,
                has_stable_worker_track=has_stable_worker_track,
                track_id=track_id,
                used_surrogates=used_worker_surrogates,
            )

            distance_candidates = [
                (
                    self._distance_engine.compute(
                        camera_id=camera_id,
                        worker_bbox=person.bbox,
                        forklift_bbox=f.bbox,
                        detection_confidence=min(person.confidence, f.confidence),
                    ),
                    f,
                )
                for f in forklifts
            ]
            distance_result, near_forklift = min(
                distance_candidates,
                key=lambda item: item[0].distance_m,
            )
            forklift_motion = self._forklift_motion.update(
                ("forklift", near_forklift.track_id or id(near_forklift)),
                distance_result.forklift_bottom_center,
                timestamp,
                point_m=distance_result.forklift_ground_point,
            )
            worker_motion = self._worker_motion.update(
                ("worker", worker_identity_key),
                distance_result.worker_bottom_center,
                timestamp,
                point_m=distance_result.worker_ground_point,
            )

            driver_result = self._driver_suppression.evaluate(
                person,
                near_forklift,
                timestamp,
            )

            pair_key = self._pair_key(camera_id, near_forklift, worker_identity_key)
            operational_case_key = self._operational_case_key(camera_id, near_forklift, worker_identity_key)
            tracking_confidence = _tracking_confidence(
                person.track_id,
                near_forklift.track_id,
                worker_motion.age,
                forklift_motion.age,
            )
            risk_context = self._evaluate_risk_context(
                person=person,
                forklift=near_forklift,
                distance_result=distance_result,
                forklift_motion=forklift_motion,
                worker_motion=worker_motion,
                persistence_sec=self._pair_persistence(pair_key, timestamp),
                detection_confidence=min(person.confidence, near_forklift.confidence),
                tracking_confidence=tracking_confidence,
            )
            suppression_overridden = False
            if driver_result.driver_suppressed:
                self._log_driver_suppression_audit(
                    camera_id=camera_id,
                    frame_number=frame_number,
                    person=person,
                    forklift=near_forklift,
                    distance_result=distance_result,
                    driver_result=driver_result,
                    risk_context=risk_context,
                )
                if (
                    self._driver_suppression_override_allowed(driver_result)
                    and risk_context.risk_result.risk_score >= self._risk_engine.config.critical_score
                ):
                    suppression_overridden = True
                    logger.error(
                        "SUPPRESSION_OVERRIDE camera_id=%s frame=%s worker_track_id=%s "
                        "forklift_track_id=%s shadow_score=%.1f distance_m=%.2f zone=%s ttc=%s",
                        camera_id,
                        frame_number,
                        track_id,
                        near_forklift.track_id,
                        risk_context.risk_result.risk_score,
                        distance_result.distance_m,
                        risk_context.zone_result.zone_type.value,
                        risk_context.collision_result.ttc_seconds,
                    )
                else:
                    continue

            persistence_sec = self._update_pair_persistence(pair_key, timestamp)
            risk_context = self._evaluate_risk_context(
                person=person,
                forklift=near_forklift,
                distance_result=distance_result,
                forklift_motion=forklift_motion,
                worker_motion=worker_motion,
                persistence_sec=persistence_sec,
                detection_confidence=min(person.confidence, near_forklift.confidence),
                tracking_confidence=tracking_confidence,
            )
            zone_result = risk_context.zone_result
            collision_result = risk_context.collision_result
            policy_result = risk_context.policy_result
            risk_result = risk_context.risk_result
            event_decision = self._event_generator.decide(
                pair_key=pair_key,
                risk_result=risk_result,
                timestamp=timestamp,
            )
            if event_decision is None:
                continue

            proximity_metadata = {
                "case_type": "forklift_proximity",
                "operational_case_key": list(operational_case_key),
                "proximity_pair_key": list(pair_key),
                "forklift_bbox": near_forklift.bbox,
                "forklift_track_id": near_forklift.track_id,
                "worker_track_id": track_id,
                "worker_track_id_valid": has_stable_worker_track,
                "worker_track_id_fallback": not has_stable_worker_track,
                "worker_track_id_source": track_method if has_stable_worker_track else "fallback",
                "worker_track_match_method": track_method,
                "worker_identity_key": _metadata_key(worker_identity_key),
                "worker_identity_source": worker_identity_source,
                "worker_surrogate_id": worker_surrogate_id,
                "composite_eligible": has_stable_worker_track,
                **distance_result.metadata(),
                **forklift_motion.metadata("forklift"),
                **worker_motion.metadata("worker"),
                **zone_result.metadata(),
                **collision_result.metadata(),
                **policy_result.metadata(),
                **risk_result.metadata(),
                "risk_persistence_sec": round(persistence_sec, 3),
                "proximity_risk": event_decision.stage.value,
                "risk_level": event_decision.stage.value,
                "risk_score": round(risk_result.risk_score, 3),
                "risk": event_decision.stage.value,
                "proximity_stage_severity": event_decision.severity.name,
                "driver_suppression_overridden": suppression_overridden,
                **event_decision.metadata(),
                **driver_result.metadata(),
            }
            if event_decision.stage == ProximityEventStage.MONITOR:
                proximity_metadata.update(
                    {
                        "render_only": True,
                        "suppress_event": True,
                        "composite_eligible": False,
                    }
                )
            events.append(HazardEvent(
                event_type=event_decision.event_type,
                severity=event_decision.severity,
                camera_id=camera_id,
                timestamp=timestamp,
                frame_number=frame_number,
                track_id=track_id,
                bbox=person.bbox,
                description=(
                    f"Forklift proximity {event_decision.stage.value} "
                    f"(risk={risk_result.risk_score:.1f}, dist={distance_result.distance_m:.2f}m)"
                ),
                metadata=proximity_metadata,
            ))

        events.extend(
            self.overspeed_events(
                detections,
                camera_id=camera_id,
                frame_number=frame_number,
                timestamp=timestamp,
            )
        )
        return events

    def _emit_overspeed_event(
        self,
        overspeed: OverspeedResult,
        *,
        camera_id: str = "",
        frame_number: int = 0,
        timestamp: float = 0.0,
        forklift: Detection | None = None,
    ) -> HazardEvent:
        return HazardEvent(
            event_type=EventTypes.FORKLIFT_OVERSPEED,
            severity=_severity_from_overspeed(overspeed.severity),
            camera_id=camera_id,
            timestamp=timestamp,
            frame_number=frame_number,
            track_id=None if forklift is None else forklift.track_id,
            bbox=None if forklift is None else forklift.bbox,
            description=(
                f"Forklift overspeed {overspeed.severity} "
                f"({overspeed.speed_mps:.2f}m/s > {overspeed.limit_mps:.2f}m/s)"
            ),
            metadata={
                **overspeed.metadata(),
                "forklift_track_id": None if forklift is None else forklift.track_id,
                "forklift_bbox": None if forklift is None else forklift.bbox,
                "forklift_speed_mps": round(overspeed.speed_mps, 3),
            },
        )

    def _nearest_worker_distance_context(
        self,
        camera_id: str,
        forklift: Detection,
        persons: list[Detection],
    ) -> tuple[float | None, float]:
        if not persons:
            return None, 0.0
        results = [
            self._distance_engine.compute(
                camera_id=camera_id,
                worker_bbox=person.bbox,
                forklift_bbox=forklift.bbox,
                detection_confidence=min(person.confidence, forklift.confidence),
            )
            for person in persons
        ]
        if not results:
            return None, 0.0
        nearest = min(results, key=lambda item: item.distance_m)
        return nearest.distance_m, nearest.calibration_confidence

    def _nearest_worker_distance_m(
        self,
        camera_id: str,
        forklift: Detection,
        persons: list[Detection],
    ) -> float | None:
        if not persons:
            return None
        distances = [
            self._distance_engine.compute(
                camera_id=camera_id,
                worker_bbox=person.bbox,
                forklift_bbox=forklift.bbox,
                detection_confidence=min(person.confidence, forklift.confidence),
            ).distance_m
            for person in persons
        ]
        return min(distances) if distances else None

    def _speed_confidence(self, motion, distance_confidence: float) -> float:
        age_confidence = min(1.0, max(0.0, motion.age_seconds) / 2.0)
        source_confidence = (
            max(0.0, min(1.0, distance_confidence))
            if motion.speed_source == "ground_plane"
            else 0.45
        )
        speed_scale = max(motion.raw_speed_mps, motion.speed_mps, 1e-9)
        consistency = 1.0 - min(1.0, abs(motion.raw_speed_mps - motion.speed_mps) / speed_scale)
        return max(0.0, min(1.0, age_confidence * source_confidence * consistency))

    def _overspeed_confirmed(
        self,
        camera_id: str,
        forklift: Detection,
        overspeed: OverspeedResult,
        timestamp: float,
    ) -> bool:
        key = self._overspeed_key(camera_id, forklift)
        state = self._overspeed_states.get(key)
        if state is None or state.severity != overspeed.severity or state.context != overspeed.context:
            self._overspeed_states[key] = _OverspeedState(
                first_seen=timestamp,
                last_seen=timestamp,
                severity=overspeed.severity,
                context=overspeed.context,
            )
            return False
        state.last_seen = timestamp
        if timestamp - state.first_seen < FORKLIFT_OVERSPEED_CONFIRMATION_SEC:
            return False
        state.confirmed = True
        return True

    def _clear_overspeed_state(self, camera_id: str, forklift: Detection) -> None:
        self._overspeed_states.pop(self._overspeed_key(camera_id, forklift), None)

    @staticmethod
    def _overspeed_key(camera_id: str, forklift: Detection) -> tuple:
        return (
            camera_id,
            forklift.track_id if forklift.track_id is not None else ("forklift_bbox", _quantized_center(forklift.bbox)),
        )

    def _forklift_motion_snapshot(self, forklift: Detection, timestamp: float):
        track_key = ("forklift", forklift.track_id or id(forklift))
        point = _bottom_center(forklift.bbox)
        motion = self._forklift_motion.get(track_key)
        if motion is None or motion.timestamp < timestamp:
            motion = self._forklift_motion.update(
                track_key,
                point,
                timestamp,
                point_m=None,
            )
        return motion

    def _evaluate_risk_context(
        self,
        *,
        person: Detection,
        forklift: Detection,
        distance_result,
        forklift_motion,
        worker_motion,
        persistence_sec: float,
        detection_confidence: float,
        tracking_confidence: float,
    ) -> _ProximityRiskContext:
        zone_result = self._zone_engine.evaluate(
            forklift_bbox=forklift.bbox,
            worker_point=distance_result.worker_bottom_center,
            heading_px=forklift_motion.velocity_pxps,
            heading_confidence=forklift_motion.heading_confidence,
            speed_mps=forklift_motion.speed_mps,
        )
        collision_result = self._collision_engine.evaluate(
            forklift_position_m=_position_m(
                distance_result.forklift_bottom_center,
                distance_result.forklift_ground_point,
            ),
            worker_position_m=_position_m(
                distance_result.worker_bottom_center,
                distance_result.worker_ground_point,
            ),
            forklift_velocity_mps=forklift_motion.velocity_mps,
            worker_velocity_mps=worker_motion.velocity_mps,
            calibration_confidence=distance_result.calibration_confidence,
        )
        policy_result = self._proximity_policy.evaluate(
            distance_m=distance_result.distance_m,
            speed_mps=forklift_motion.speed_mps,
            calibration_confidence=distance_result.calibration_confidence,
        )
        risk_result = self._risk_engine.evaluate(
            distance_m=distance_result.distance_m,
            danger_radius_m=policy_result.danger_radius_m,
            warning_radius_m=policy_result.warning_radius_m,
            forklift_speed_mps=forklift_motion.speed_mps,
            worker_speed_mps=worker_motion.speed_mps,
            ttc_seconds=collision_result.ttc_seconds,
            closest_approach_distance_m=collision_result.closest_approach_distance_m,
            relative_motion_class=collision_result.relative_motion_class,
            zone_type=zone_result.zone_type,
            persistence_sec=persistence_sec,
            detection_confidence=detection_confidence,
            tracking_confidence=tracking_confidence,
            calibration_confidence=distance_result.calibration_confidence,
            predicted_collision=collision_result.predicted_collision,
            driver_suppressed=False,
        )
        return _ProximityRiskContext(
            zone_result=zone_result,
            collision_result=collision_result,
            policy_result=policy_result,
            risk_result=risk_result,
            tracking_confidence=tracking_confidence,
        )

    def _pair_persistence(self, pair_key: tuple, timestamp: float) -> float:
        self._purge_pair_state(timestamp)
        first_seen = self._pair_first_seen.get(pair_key)
        if first_seen is None:
            return 0.0
        return max(0.0, timestamp - first_seen)

    @staticmethod
    def _driver_suppression_override_allowed(driver_result) -> bool:
        return (
            driver_result.reason not in {"strong_overlap", "assigned_driver"}
            and not driver_result.driver_assigned
        )

    def _log_driver_suppression_audit(
        self,
        *,
        camera_id: str,
        frame_number: int,
        person: Detection,
        forklift: Detection,
        distance_result,
        driver_result,
        risk_context: _ProximityRiskContext,
    ) -> None:
        logger.warning(
            "DRIVER_SUPPRESSION_AUDIT camera_id=%s frame=%s worker_track_id=%s "
            "forklift_track_id=%s reason=%s shadow_score=%.1f risk_level=%s "
            "distance_m=%.2f distance_source=%s calibration_confidence=%.2f "
            "zone=%s ttc=%s cpa=%.2f overlap=%.3f cabin_overlap=%.3f",
            camera_id,
            frame_number,
            person.track_id,
            forklift.track_id,
            driver_result.reason,
            risk_context.risk_result.risk_score,
            risk_context.risk_result.risk_level.value,
            distance_result.distance_m,
            distance_result.distance_source,
            distance_result.calibration_confidence,
            risk_context.zone_result.zone_type.value,
            risk_context.collision_result.ttc_seconds,
            risk_context.collision_result.closest_approach_distance_m,
            driver_result.overlap_ratio,
            driver_result.cabin_overlap_ratio,
        )

    def _worker_identity_key(
        self,
        *,
        camera_id: str,
        person: Detection,
        timestamp: float,
        has_stable_worker_track: bool,
        track_id: Optional[int],
        used_surrogates: set[int],
    ) -> tuple | int:
        if has_stable_worker_track and track_id is not None:
            return track_id, "stable_track", None
        surrogate_id, source = self._resolve_worker_surrogate(
            camera_id=camera_id,
            bbox=person.bbox,
            timestamp=timestamp,
            used_surrogates=used_surrogates,
        )
        used_surrogates.add(surrogate_id)
        return ("worker_surrogate", surrogate_id), source, surrogate_id

    def _resolve_worker_surrogate(
        self,
        *,
        camera_id: str,
        bbox: Tuple[int, int, int, int],
        timestamp: float,
        used_surrogates: set[int],
    ) -> tuple[int, str]:
        self._purge_worker_surrogates(timestamp)
        center = _center(bbox)
        best_key = None
        best_score = float("inf")
        best_source = "surrogate_new"
        for key, state in self._worker_surrogates.items():
            state_camera_id, surrogate_id = key
            if state_camera_id != camera_id or surrogate_id in used_surrogates:
                continue
            age = timestamp - state.last_seen
            if age > PROXIMITY_RESOLUTION_GRACE_SEC:
                continue
            iou = _iou(bbox, state.bbox)
            distance = math.hypot(center[0] - state.center[0], center[1] - state.center[1])
            max_dim = max(
                1.0,
                float(bbox[2] - bbox[0]),
                float(bbox[3] - bbox[1]),
                float(state.bbox[2] - state.bbox[0]),
                float(state.bbox[3] - state.bbox[1]),
            )
            max_distance = max(80.0, max_dim * 1.75)
            if iou < 0.02 and distance > max_distance:
                continue
            score = distance - (iou * max_dim)
            if score < best_score:
                best_key = key
                best_score = score
                best_source = "surrogate_iou" if iou >= 0.02 else "surrogate_centroid"

        if best_key is None:
            surrogate_id = self._next_worker_surrogate_id
            self._next_worker_surrogate_id += 1
            best_key = (camera_id, surrogate_id)
            self._worker_surrogates[best_key] = _WorkerSurrogateState(
                surrogate_id=surrogate_id,
                bbox=bbox,
                center=center,
                first_seen=timestamp,
                last_seen=timestamp,
            )
            return surrogate_id, "surrogate_new"

        state = self._worker_surrogates[best_key]
        state.bbox = bbox
        state.center = center
        state.last_seen = timestamp
        return state.surrogate_id, best_source

    def _purge_worker_surrogates(self, timestamp: float) -> None:
        stale = [
            key for key, state in self._worker_surrogates.items()
            if timestamp - state.last_seen > PROXIMITY_RESOLUTION_GRACE_SEC
        ]
        for key in stale:
            self._worker_surrogates.pop(key, None)

    def _pair_key(self, camera_id: str, forklift: Detection, worker_identity_key) -> tuple:
        forklift_key = forklift.track_id if forklift.track_id is not None else ("forklift_bbox", _quantized_center(forklift.bbox))
        return camera_id, forklift_key, worker_identity_key

    def _operational_case_key(self, camera_id: str, forklift: Detection, worker_identity_key) -> tuple:
        forklift_key = forklift.track_id if forklift.track_id is not None else ("forklift_bbox", _quantized_center(forklift.bbox))
        return camera_id, forklift_key, worker_identity_key

    def _update_pair_persistence(self, pair_key: tuple, timestamp: float) -> float:
        self._purge_pair_state(timestamp)
        if pair_key not in self._pair_first_seen:
            self._pair_first_seen[pair_key] = timestamp
        self._pair_last_seen[pair_key] = timestamp
        return max(0.0, timestamp - self._pair_first_seen[pair_key])

    def _purge_pair_state(self, timestamp: float) -> None:
        stale = [
            key for key, last_seen in self._pair_last_seen.items()
            if timestamp - last_seen > 2.0
        ]
        for key in stale:
            self._pair_first_seen.pop(key, None)
            self._pair_last_seen.pop(key, None)


def _position_m(
    point_px: tuple[float, float],
    point_m: Optional[tuple[float, float]],
) -> tuple[float, float]:
    if point_m is not None:
        return point_m
    return (
        point_px[0] * DISTANCE_FALLBACK_METERS_PER_PIXEL,
        point_px[1] * DISTANCE_FALLBACK_METERS_PER_PIXEL,
    )


def _tracking_confidence(
    person_track_id: Optional[int],
    forklift_track_id: Optional[int],
    worker_age: int,
    forklift_age: int,
) -> float:
    base = 1.0 if person_track_id is not None and forklift_track_id is not None else 0.6
    age_confidence = min(1.0, max(0.0, min(worker_age, forklift_age)) / 3.0)
    return max(0.0, min(1.0, base * (0.5 + 0.5 * age_confidence)))


def _severity_from_overspeed(severity: str) -> Severity:
    if severity == "critical":
        return Severity.CRITICAL
    if severity == "danger":
        return Severity.HIGH
    return Severity.MEDIUM


def _quantized_center(bbox: Tuple[int, int, int, int]) -> tuple[int, int]:
    cx, cy = _center(bbox)
    return int(round(cx / 25.0) * 25), int(round(cy / 25.0) * 25)


def _metadata_key(value) -> list | int | str:
    if isinstance(value, tuple):
        return [_metadata_key(item) for item in value]
    if isinstance(value, list):
        return [_metadata_key(item) for item in value]
    return value


def _dedupe_forklifts(forklifts: List[Detection]) -> List[Detection]:
    kept: list[Detection] = []
    for det in sorted(forklifts, key=lambda item: item.confidence, reverse=True):
        if any(_same_forklift(det, existing) for existing in kept):
            continue
        kept.append(det)
    return kept


def _same_forklift(a: Detection, b: Detection) -> bool:
    if _iou(a.bbox, b.bbox) >= FORKLIFT_DEDUP_IOU:
        return True
    ax, ay = _center(a.bbox)
    bx, by = _center(b.bbox)
    center_distance = math.hypot(ax - bx, ay - by)
    max_dim = max(
        1.0,
        float(a.bbox[2] - a.bbox[0]),
        float(a.bbox[3] - a.bbox[1]),
        float(b.bbox[2] - b.bbox[0]),
        float(b.bbox[3] - b.bbox[1]),
    )
    return center_distance <= FORKLIFT_DEDUP_CENTER_RATIO * max_dim
