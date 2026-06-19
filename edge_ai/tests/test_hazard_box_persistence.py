"""
VisionSafe360 — Hazard box persistence (linger) tests.

The worker hazard box should stay visible for ``hazard_hold_sec`` after the
hazard event last appeared, so a dashboard operator can notice it even if
detection flickers — without affecting the real alert pipeline.
"""
from __future__ import annotations

import numpy as np

from edge_ai.src.config.ui_settings import UISettings
from edge_ai.src.models.hazard_event import HazardEvent
from edge_ai.src.models.severity import Severity
from edge_ai.src.ui.layers.hazards_layer import HazardsLayer
from edge_ai.src.ui.theme import DARK


def _event() -> HazardEvent:
    return HazardEvent(
        event_type="no_helmet",
        severity=Severity.HIGH,
        camera_id="cam-1",
        timestamp=0.0,
        frame_number=0,
        track_id=1,
        bbox=(40, 40, 200, 320),
        description="PPE missing: helmet",
    )


def _blank() -> np.ndarray:
    return np.zeros((400, 400, 3), dtype=np.uint8)


def test_box_lingers_within_hold_window():
    layer = HazardsLayer(DARK, UISettings(hazard_hold_sec=1.0))
    # Hazard present at t=0.
    layer.draw(_blank(), [_event()], now=0.0)
    # 0.7s later the event is gone, but still within the 1.0s hold → box drawn.
    frame = _blank()
    layer.draw(frame, [], now=0.7)
    assert frame.any(), "box should linger within the hold window"


def test_box_clears_after_hold_window():
    layer = HazardsLayer(DARK, UISettings(hazard_hold_sec=1.0))
    layer.draw(_blank(), [_event()], now=0.0)
    # 1.5s later → past the 1.0s hold → nothing drawn.
    frame = _blank()
    layer.draw(frame, [], now=1.5)
    assert not frame.any(), "box should disappear after the hold window expires"


def test_live_event_refreshes_hold():
    layer = HazardsLayer(DARK, UISettings(hazard_hold_sec=1.0))
    layer.draw(_blank(), [_event()], now=0.0)
    # Seen again at t=0.8 → resets last_seen.
    layer.draw(_blank(), [_event()], now=0.8)
    # At t=1.5 (0.7s after refresh) → still within hold.
    frame = _blank()
    layer.draw(frame, [], now=1.5)
    assert frame.any(), "a fresh sighting should restart the hold window"


def test_hold_disabled_clears_immediately():
    layer = HazardsLayer(DARK, UISettings(hazard_hold_sec=0.0))
    layer.draw(_blank(), [_event()], now=0.0)
    frame = _blank()
    layer.draw(frame, [], now=0.1)
    assert not frame.any(), "hold_sec=0 → no persistence"
