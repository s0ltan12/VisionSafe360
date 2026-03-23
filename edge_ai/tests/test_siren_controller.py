"""Unit tests for SirenController."""
import sys
import time
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
	sys.path.insert(0, str(_EDGE_AI_DIR))

from src.alerts.siren_controller import SirenConfig, SirenController
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity


def _event() -> HazardEvent:
	return HazardEvent(
		event_type="fall_confirmed",
		severity=Severity.CRITICAL,
		camera_id="cam_01",
		timestamp=100.0,
		frame_number=1,
		track_id=1,
		description="critical",
		metadata={},
	)


def test_siren_cooldown_suppresses_retrigger() -> None:
	siren = SirenController(
		SirenConfig(
			enabled=True,
			mock_mode=True,
			gpio_pin=18,
			cooldown_sec=1.0,
			max_active_sec=0.2,
		)
	)

	assert siren.trigger(_event()) is True
	assert siren.trigger(_event()) is False


def test_siren_stop_is_idempotent() -> None:
	siren = SirenController(
		SirenConfig(
			enabled=True,
			mock_mode=True,
			gpio_pin=18,
			cooldown_sec=0.0,
			max_active_sec=0.1,
		)
	)
	assert siren.stop() is True
	assert siren.stop() is True


def test_siren_auto_stop_on_tick() -> None:
	siren = SirenController(
		SirenConfig(
			enabled=True,
			mock_mode=True,
			gpio_pin=18,
			cooldown_sec=0.0,
			max_active_sec=0.05,
		)
	)
	assert siren.trigger(_event()) is True
	time.sleep(0.06)
	siren.tick()
	assert siren.stop() is True
