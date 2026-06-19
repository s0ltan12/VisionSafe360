import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.ppe_analyzer import PPEAnalyzer
from src.models.detection import Detection
from src.models.severity import Severity
from src.ui.layers.hazards_layer import build_hazard_label
from src.ui.layers.worker_panel_layer import _hazard_panel_lines


def _person(track_id: int, bbox: tuple[int, int, int, int]) -> Detection:
    return Detection(
        class_id=0,
        class_name="person",
        confidence=0.95,
        bbox=bbox,
        track_id=track_id,
    )


def _ppe(class_name: str, bbox: tuple[int, int, int, int], confidence: float = 0.9) -> Detection:
    return Detection(
        class_id=2,
        class_name=class_name,
        confidence=confidence,
        bbox=bbox,
    )


def test_same_worker_multiple_ppe_misses_emit_one_hazard_event() -> None:
    analyzer = PPEAnalyzer()

    events = analyzer.analyze(
        ppe_detections=[
            _ppe("helmet_off", (50, 20, 90, 60), confidence=0.91),
            _ppe("gloves_off", (70, 110, 115, 145), confidence=0.86),
        ],
        tracked_people=[_person(1, (40, 10, 150, 220))],
        camera_id="cam_01",
        frame_number=915,
        timestamp=1781713179.0,
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "ppe_missing"
    assert event.severity == Severity.HIGH
    assert event.track_id == 1
    assert event.metadata["missing_ppe_items"] == ["helmet", "gloves"]
    assert event.metadata["ppe_source_event_types"] == [
        "ppe_missing_helmet",
        "ppe_missing_gloves",
    ]
    assert event.metadata["display_title"] == "PPE missing helmet, gloves"
    assert event.description == "PPE missing helmet, gloves track=1"
    assert build_hazard_label(event, calibrated=False) == "[!] PPE MISSING HELMET, GLOVES"
    assert _hazard_panel_lines(event) == [
        "PPE HELMET MISSING",
        "PPE GLOVES MISSING",
    ]
    assert len(event.metadata["ppe_detections"]) == 2


def test_different_workers_keep_separate_ppe_hazard_events() -> None:
    analyzer = PPEAnalyzer()

    events = analyzer.analyze(
        ppe_detections=[
            _ppe("helmet_off", (50, 20, 90, 60)),
            _ppe("vest_off", (250, 70, 310, 150)),
        ],
        tracked_people=[
            _person(1, (40, 10, 150, 220)),
            _person(2, (220, 20, 340, 230)),
        ],
        camera_id="cam_01",
        frame_number=916,
        timestamp=1781713180.0,
    )

    assert len(events) == 2
    assert {event.track_id for event in events} == {1, 2}
    assert all(event.event_type == "ppe_missing" for event in events)
