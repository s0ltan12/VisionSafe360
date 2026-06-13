import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.motion_engine import MotionEngine, MotionState


def test_parked_forklift_classifies_stationary():
    engine = MotionEngine(ema_alpha=1.0)

    engine.update("forklift-1", (100.0, 100.0), 100.0, point_m=(0.0, 0.0))
    snap = engine.update("forklift-1", (100.0, 100.0), 101.0, point_m=(0.0, 0.0))

    assert snap.speed_mps == 0.0
    assert snap.state == MotionState.STATIONARY


def test_slow_forklift_classifies_creeping():
    engine = MotionEngine(ema_alpha=1.0)

    engine.update("forklift-1", (100.0, 100.0), 100.0, point_m=(0.0, 0.0))
    snap = engine.update("forklift-1", (110.0, 100.0), 101.0, point_m=(0.2, 0.0))

    assert 0.10 <= snap.speed_mps <= 0.30
    assert snap.state == MotionState.CREEPING


def test_accelerating_forklift_classifies_moving_and_has_heading():
    engine = MotionEngine(ema_alpha=1.0)

    engine.update("forklift-1", (100.0, 100.0), 100.0, point_m=(0.0, 0.0))
    snap = engine.update("forklift-1", (150.0, 100.0), 101.0, point_m=(0.8, 0.0))

    assert snap.speed_mps > 0.30
    assert snap.state == MotionState.MOVING
    assert snap.heading == (1.0, 0.0)
    assert snap.heading_confidence > 0.0
