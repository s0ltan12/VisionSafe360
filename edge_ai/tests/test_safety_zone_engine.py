import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.safety_zone_engine import SafetyZoneEngine
from src.models.detection import Detection


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_person_entering_danger_zone_emits_zone_event():
    engine = SafetyZoneEngine()
    engine.set_camera_zones("CAM-01", [{
        "id": "CSZ-1",
        "name": "Danger Zone",
        "zone_type": "danger",
        "polygon": [{"x": 100, "y": 100}, {"x": 300, "y": 100}, {"x": 300, "y": 300}, {"x": 100, "y": 300}],
        "source_width": 640,
        "source_height": 480,
        "rules": {"severity": "Critical", "cooldown_sec": 0},
    }])

    events = engine.analyze(
        [_det("person", (140, 120, 180, 180), track_id=7)],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    assert len(events) == 1
    assert events[0].event_type == "zone_person_entered"
    assert events[0].metadata["safety_zone_id"] == "CSZ-1"
    assert events[0].metadata["object_class"] == "person"


def test_forklift_entering_pedestrian_zone_emits_specific_violation():
    engine = SafetyZoneEngine()
    engine.set_camera_zones("CAM-01", [{
        "id": "CSZ-2",
        "name": "Pedestrian Lane",
        "zone_type": "pedestrian_only",
        "polygon": [{"x": 0, "y": 0}, {"x": 200, "y": 0}, {"x": 200, "y": 200}, {"x": 0, "y": 200}],
        "source_width": 640,
        "source_height": 480,
        "rules": {"severity": "High", "cooldown_sec": 0},
    }])

    events = engine.analyze(
        [_det("forklift", (50, 50, 100, 100), track_id=11)],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    assert [event.event_type for event in events] == ["zone_forklift_entered_pedestrian_zone"]


def test_dwell_limit_emits_once_while_inside():
    engine = SafetyZoneEngine()
    engine.set_camera_zones("CAM-01", [{
        "id": "CSZ-3",
        "name": "Restricted",
        "zone_type": "restricted",
        "polygon": [{"x": 0, "y": 0}, {"x": 200, "y": 0}, {"x": 200, "y": 200}, {"x": 0, "y": 200}],
        "source_width": 640,
        "source_height": 480,
        "rules": {"allowed_classes": ["person"], "dwell_time_limit_sec": 2, "cooldown_sec": 0},
    }])
    det = _det("person", (50, 50, 100, 100), track_id=4)

    engine.analyze([det], camera_id="CAM-01", frame_number=1, timestamp=100.0, frame_shape=(480, 640, 3))
    events = engine.analyze([det], camera_id="CAM-01", frame_number=2, timestamp=103.0, frame_shape=(480, 640, 3))
    repeated = engine.analyze([det], camera_id="CAM-01", frame_number=3, timestamp=104.0, frame_shape=(480, 640, 3))

    assert any(event.event_type == "zone_dwell_time_exceeded" for event in events)
    assert not any(event.event_type == "zone_dwell_time_exceeded" for event in repeated)
