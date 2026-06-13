import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.models.detection import Detection
from src.smoothing.detection_smoother import DetectionSmoother


def _det(class_name: str, bbox, track_id=None):
    return Detection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_detection_smoother_does_not_inject_forklift_ghosts():
    smoother = DetectionSmoother(grace_frames=3)
    forklift = _det("forklift", (100, 100, 240, 220), track_id=10)

    first = smoother.smooth([forklift])
    second = smoother.smooth([])

    assert first == [forklift]
    assert second == []


def test_detection_smoother_still_injects_person_ghosts():
    smoother = DetectionSmoother(grace_frames=3)
    person = _det("person", (100, 100, 160, 240), track_id=3)

    first = smoother.smooth([person])
    second = smoother.smooth([])

    assert first == [person]
    assert second == [person]
