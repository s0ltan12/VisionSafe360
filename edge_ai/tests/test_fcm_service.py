"""Unit tests for FCMService."""
import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
	sys.path.insert(0, str(_EDGE_AI_DIR))

from src.alerts.fcm_service import FCMConfig, FCMService
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity


def _event() -> HazardEvent:
	return HazardEvent(
		event_type="proximity_warning",
		severity=Severity.HIGH,
		camera_id="cam_01",
		timestamp=100.0,
		frame_number=1,
		track_id=10,
		description="warning",
		metadata={},
	)


def test_mock_mode_success() -> None:
	service = FCMService(
		FCMConfig(
			enabled=True,
			mock_mode=True,
			credentials_path="",
			device_tokens=("token_1",),
			retry_once=True,
		)
	)
	assert service.send_event(_event()) is True


def test_real_mode_failure_returns_false_without_crash() -> None:
	service = FCMService(
		FCMConfig(
			enabled=True,
			mock_mode=False,
			credentials_path="/missing/file.json",
			device_tokens=("token_1",),
			retry_once=True,
		)
	)
	assert service.send_event(_event()) is False
