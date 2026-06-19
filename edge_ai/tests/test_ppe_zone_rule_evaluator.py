import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.ppe_zone_rule_evaluator import PPEZoneRuleEvaluator
from src.analysis.safety_zone_engine import SafetyZoneEngine
from src.models.detection import Detection
from src.models.severity import Severity


def _person(track_id: int, bbox: tuple[int, int, int, int]) -> Detection:
    return Detection(class_id=0, class_name="person", confidence=0.95, bbox=bbox, track_id=track_id)


def _ppe(class_name: str, bbox: tuple[int, int, int, int]) -> Detection:
    return Detection(class_id=1, class_name=class_name, confidence=0.9, bbox=bbox)


def _engine_with_zones(zones: list[dict]) -> SafetyZoneEngine:
    engine = SafetyZoneEngine()
    engine.set_camera_zones("CAM-PPE", zones)
    return engine


def _zone(zone_id: str, polygon: list[dict], required_ppe: list[str]) -> dict:
    return {
        "id": zone_id,
        "name": f"Zone {zone_id}",
        "zone_type": "ppe_required",
        "polygon": polygon,
        "source_width": 640,
        "source_height": 480,
        "enabled": True,
        "rules": {
            "required_ppe": required_ppe,
            "severity": "High",
            "cooldown_sec": 0,
        },
    }


def _evaluate(engine: SafetyZoneEngine, ppe_detections: list[Detection], person: Detection):
    return PPEZoneRuleEvaluator(engine).evaluate(
        ppe_detections=ppe_detections,
        tracked_people=[person],
        camera_id="CAM-PPE",
        frame_number=1,
        timestamp=100.0,
        frame_shape=(480, 640, 3),
    )


def test_ppe_outside_zone_does_not_emit_alert_event() -> None:
    engine = _engine_with_zones([
        _zone(
            "A",
            [{"x": 0, "y": 0}, {"x": 120, "y": 0}, {"x": 120, "y": 120}, {"x": 0, "y": 120}],
            ["helmet"],
        )
    ])

    events = _evaluate(engine, [_ppe("helmet_off", (300, 80, 340, 120))], _person(1, (280, 40, 380, 220)))

    assert events == []


def test_ppe_inside_zone_emits_missing_required_item() -> None:
    engine = _engine_with_zones([
        _zone(
            "A",
            [{"x": 0, "y": 0}, {"x": 240, "y": 0}, {"x": 240, "y": 260}, {"x": 0, "y": 260}],
            ["helmet"],
        )
    ])

    events = _evaluate(engine, [_ppe("helmet_off", (70, 45, 110, 85))], _person(7, (50, 20, 160, 220)))

    assert len(events) == 1
    assert events[0].event_type == "ppe_missing"
    assert events[0].metadata["missing_ppe_items"] == ["helmet"]
    assert events[0].metadata["required_ppe"] == ["helmet"]
    assert events[0].metadata["safety_zone_id"] == "A"
    assert events[0].metadata["safety_zone_snapshot"]["id"] == "A"
    assert events[0].description == "Worker inside PPE Zone without Helmet track=7"


def test_multiple_required_ppe_items_emit_exact_missing_items() -> None:
    engine = _engine_with_zones([
        _zone(
            "A",
            [{"x": 0, "y": 0}, {"x": 260, "y": 0}, {"x": 260, "y": 260}, {"x": 0, "y": 260}],
            ["helmet", "vest", "gloves"],
        )
    ])

    events = _evaluate(
        engine,
        [
            _ppe("helmet_on", (70, 45, 110, 85)),
            _ppe("vest_off", (65, 90, 150, 160)),
            _ppe("gloves_off", (65, 150, 150, 190)),
        ],
        _person(7, (50, 20, 170, 230)),
    )

    assert len(events) == 1
    assert events[0].metadata["missing_ppe_items"] == ["vest", "gloves"]
    assert events[0].metadata["detected_ppe_items"] == ["helmet"]
    assert events[0].severity == Severity.HIGH
    assert events[0].description == "Worker inside PPE Zone missing Safety Vest and Gloves track=7"


def test_overlapping_ppe_zones_use_union_of_requirements() -> None:
    overlapping = [{"x": 0, "y": 0}, {"x": 300, "y": 0}, {"x": 300, "y": 300}, {"x": 0, "y": 300}]
    engine = _engine_with_zones([
        _zone("A", overlapping, ["helmet"]),
        _zone("B", overlapping, ["helmet", "gloves"]),
    ])

    events = _evaluate(engine, [_ppe("helmet_on", (70, 45, 110, 85))], _person(4, (50, 20, 170, 230)))

    assert len(events) == 1
    assert events[0].metadata["required_ppe"] == ["helmet", "gloves"]
    assert events[0].metadata["missing_ppe_items"] == ["gloves"]
    assert events[0].metadata["ppe_zone_ids"] == ["A", "B"]


def test_detected_required_ppe_inside_zone_does_not_emit() -> None:
    engine = _engine_with_zones([
        _zone(
            "A",
            [{"x": 0, "y": 0}, {"x": 240, "y": 0}, {"x": 240, "y": 260}, {"x": 0, "y": 260}],
            ["helmet", "vest"],
        )
    ])

    events = _evaluate(
        engine,
        [_ppe("helmet_on", (70, 45, 110, 85)), _ppe("safety_vest", (65, 90, 150, 160))],
        _person(7, (50, 20, 170, 230)),
    )

    assert events == []
