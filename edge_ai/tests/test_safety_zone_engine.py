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


def test_person_in_danger_zone_emits_specific_alert():
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
    assert events[0].event_type == "zone_person_in_danger"
    assert events[0].description == "Worker in danger zone: Danger Zone"
    assert events[0].metadata["safety_zone_id"] == "CSZ-1"
    assert events[0].metadata["object_class"] == "person"
    assert events[0].metadata["safety_zone_snapshot"]["id"] == "CSZ-1"
    assert events[0].metadata["safety_zone_snapshot"]["polygon"][0] == {"x": 100.0, "y": 100.0}


def test_person_leaving_danger_zone_does_not_emit_operator_alert():
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
    engine.analyze(
        [_det("person", (140, 120, 180, 180), track_id=7)],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    events = engine.analyze(
        [_det("person", (340, 120, 380, 180), track_id=7)],
        camera_id="CAM-01",
        frame_number=2,
        timestamp=101.0,
        frame_shape=(480, 640, 3),
    )

    assert events == []


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

    assert [event.event_type for event in events] == ["zone_forklift_in_pedestrian_zone"]
    assert events[0].description == "Forklift in pedestrian walkway: Pedestrian Lane"


def test_no_entry_empty_allowed_classes_denies_person_and_respects_zero_cooldown():
    engine = SafetyZoneEngine()
    engine.set_camera_zones("CAM-01", [{
        "id": "CSZ-NO-ENTRY",
        "name": "Emergency Exit",
        "zone_type": "no_entry",
        "polygon": [{"x": 0, "y": 0}, {"x": 200, "y": 0}, {"x": 200, "y": 200}, {"x": 0, "y": 200}],
        "source_width": 640,
        "source_height": 480,
        "rules": {
            "allowed_classes": [],
            "denied_classes": ["person", "forklift"],
            "severity": "Critical",
            "cooldown_sec": 0,
        },
    }])

    person = _det("person", (50, 50, 100, 100), track_id=11)
    first = engine.analyze([person], camera_id="CAM-01", frame_number=1, timestamp=100.0, frame_shape=(480, 640, 3))
    engine.analyze([], camera_id="CAM-01", frame_number=2, timestamp=104.0, frame_shape=(480, 640, 3))
    second = engine.analyze([person], camera_id="CAM-01", frame_number=3, timestamp=105.0, frame_shape=(480, 640, 3))

    assert [event.event_type for event in first] == ["zone_person_in_danger"]
    assert [event.event_type for event in second] == ["zone_person_in_danger"]


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


def _forklift_zone_engine() -> SafetyZoneEngine:
    engine = SafetyZoneEngine()
    engine.set_camera_zones("CAM-01", [{
        "id": "CSZ-FORKLIFT",
        "name": "Forklift Lane",
        "zone_type": "forklift_only",
        "polygon": [{"x": 0, "y": 0}, {"x": 400, "y": 0}, {"x": 400, "y": 400}, {"x": 0, "y": 400}],
        "source_width": 640,
        "source_height": 480,
        "rules": {
            "allowed_classes": ["forklift"],
            "denied_classes": ["person"],
            "severity": "High",
            "cooldown_sec": 0,
        },
    }])
    return engine


def test_forklift_zone_ignores_driver_center_inside_forklift_box():
    engine = _forklift_zone_engine()

    events = engine.analyze(
        [
            _det("forklift", (100, 100, 300, 250), track_id=10),
            _det("person", (160, 115, 230, 245), track_id=1),
        ],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    assert not any(event.event_type == "zone_person_in_forklift_lane" for event in events)


def test_forklift_zone_alerts_for_worker_but_not_driver():
    engine = _forklift_zone_engine()

    events = engine.analyze(
        [
            _det("forklift", (100, 100, 300, 250), track_id=10),
            _det("person", (160, 115, 230, 245), track_id=1),
            _det("person", (320, 120, 370, 260), track_id=2),
        ],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    violations = [event for event in events if event.event_type == "zone_person_in_forklift_lane"]
    assert len(violations) == 1
    assert violations[0].track_id == 2
    assert violations[0].description == "Worker in forklift lane: Forklift Lane"


def test_forklift_zone_alerts_for_worker_alone():
    engine = _forklift_zone_engine()

    events = engine.analyze(
        [_det("person", (160, 115, 230, 245), track_id=1)],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    assert [event.event_type for event in events] == ["zone_person_in_forklift_lane"]
    assert events[0].track_id == 1


def test_forklift_zone_alerts_when_driver_exits_forklift_box():
    engine = _forklift_zone_engine()

    engine.analyze(
        [
            _det("forklift", (100, 100, 300, 250), track_id=10),
            _det("person", (160, 115, 230, 245), track_id=1),
        ],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )
    events = engine.analyze(
        [
            _det("forklift", (100, 100, 300, 250), track_id=10),
            _det("person", (305, 115, 365, 245), track_id=1),
        ],
        camera_id="CAM-01",
        frame_number=2,
        timestamp=101.0,
        frame_shape=(480, 640, 3),
    )

    assert [event.event_type for event in events] == ["zone_person_in_forklift_lane"]
    assert events[0].track_id == 1


def test_forklift_zone_requires_containing_forklift_to_be_inside_same_zone():
    engine = _forklift_zone_engine()

    events = engine.analyze(
        [
            _det("forklift", (350, 100, 550, 250), track_id=10),
            _det("person", (360, 115, 390, 245), track_id=1),
        ],
        camera_id="CAM-01",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )

    assert [event.event_type for event in events] == ["zone_person_in_forklift_lane"]
    assert events[0].track_id == 1
