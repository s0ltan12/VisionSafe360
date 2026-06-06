import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.dynamic_zone_engine import DynamicZoneEngine, ZoneType
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.models.detection import Detection


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_head_on_worker_is_in_front_zone():
    engine = DynamicZoneEngine()

    result = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(260.0, 130.0),
        heading_px=(1.0, 0.0),
        heading_confidence=1.0,
        speed_mps=0.6,
    )

    assert result.zone_type in {ZoneType.FORK_LOAD, ZoneType.FRONT_DANGER}
    assert ZoneType.FRONT_DANGER in result.active_zones


def test_rear_worker_is_in_rear_zone():
    engine = DynamicZoneEngine()

    result = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(60.0, 130.0),
        heading_px=(1.0, 0.0),
        heading_confidence=1.0,
        speed_mps=0.6,
    )

    assert result.zone_type == ZoneType.REAR_DANGER


def test_side_crossing_worker_is_in_side_crush_zone():
    engine = DynamicZoneEngine()

    result = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(150.0, 178.0),
        heading_px=(1.0, 0.0),
        heading_confidence=1.0,
        speed_mps=0.4,
    )

    assert result.zone_type == ZoneType.SIDE_CRUSH


def test_low_heading_confidence_widens_tight_aisle_side_zone():
    engine = DynamicZoneEngine()

    high_conf = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(150.0, 190.0),
        heading_px=(1.0, 0.0),
        heading_confidence=1.0,
        speed_mps=0.3,
    )
    low_conf = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(150.0, 190.0),
        heading_px=(1.0, 0.0),
        heading_confidence=0.0,
        speed_mps=0.3,
    )

    assert high_conf.zone_type == ZoneType.CLEAR
    assert low_conf.zone_type == ZoneType.SIDE_CRUSH
    assert low_conf.width_scale > high_conf.width_scale


def test_stationary_forklift_reduces_directional_zone_length():
    engine = DynamicZoneEngine()

    stationary = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(220.0, 130.0),
        heading_px=(1.0, 0.0),
        heading_confidence=1.0,
        speed_mps=0.0,
    )
    moving = engine.evaluate(
        forklift_bbox=(100, 100, 200, 160),
        worker_point=(220.0, 130.0),
        heading_px=(1.0, 0.0),
        heading_confidence=1.0,
        speed_mps=1.0,
    )

    assert stationary.front_length_px < moving.front_length_px
    assert stationary.directional_scale < moving.directional_scale


def test_proximity_event_includes_dynamic_zone_metadata():
    analyzer = ProximityAnalyzer()
    forklift = _det("forklift", (100, 100, 200, 160))
    worker = _det("person", (200, 95, 240, 135), track_id=7)

    events = analyzer.analyze(
        [worker, forklift],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert len(events) == 1
    assert events[0].metadata["dynamic_zone_type"] in {"fork_load", "front_danger"}
    assert "front_danger" in events[0].metadata["dynamic_zone_active"]
