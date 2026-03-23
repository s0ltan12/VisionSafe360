"""Unit tests for BackendClient reliability behavior."""
import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
	sys.path.insert(0, str(_EDGE_AI_DIR))

from src.integration.backend_client import (
	BackendClient,
	BackendClientConfig,
	DeliveryResult as BackendDeliveryResult,
)
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity


class _Resp:
	def __init__(self, status_code: int, text: str = "") -> None:
		self.status_code = status_code
		self.text = text


class _SessionStub:
	def __init__(self, statuses: list[int]) -> None:
		self.statuses = list(statuses)
		self.calls = 0

	def post(self, url, json, timeout, headers):  # noqa: A002
		del url, json, timeout, headers
		self.calls += 1
		status = self.statuses.pop(0) if self.statuses else 500
		return _Resp(status, "stub")


def _event() -> HazardEvent:
	return HazardEvent(
		event_type="fall_confirmed",
		severity=Severity.CRITICAL,
		camera_id="cam_01",
		timestamp=100.0,
		frame_number=1,
		track_id=7,
		description="fall",
		metadata={},
	)


def test_backend_failure_is_queued(tmp_path: Path) -> None:
	db_path = tmp_path / "offline.db"
	cfg = BackendClientConfig(
		enabled=True,
		base_url="http://localhost:8000",
		incidents_path="/incidents",
		auth_token="",
		timeout_sec=0.01,
		max_retry=1,
		retry_backoff=(0.0,),
		offline_db=db_path,
		offline_queue_max_rows=100,
	)
	session = _SessionStub([500, 500])
	client = BackendClient(config=cfg, session=session, sleep_fn=lambda _: None)

	result = client.submit_incident(_event())
	assert result == BackendDeliveryResult.FAILED
	assert session.calls >= 1
	assert client.offline_queue_size() == 1


def test_flush_queue_success_after_recovery(tmp_path: Path) -> None:
	db_path = tmp_path / "offline.db"
	cfg = BackendClientConfig(
		enabled=True,
		base_url="http://localhost:8000",
		incidents_path="/incidents",
		auth_token="",
		timeout_sec=0.01,
		max_retry=0,
		retry_backoff=(0.0,),
		offline_db=db_path,
		offline_queue_max_rows=100,
	)

	failing = _SessionStub([500])
	client = BackendClient(config=cfg, session=failing, sleep_fn=lambda _: None)
	assert client.submit_incident(_event()) == BackendDeliveryResult.FAILED
	assert client.offline_queue_size() == 1

	recovering = _SessionStub([200])
	client._session = recovering
	stats = client.flush_offline_queue()

	assert stats["flushed"] == 1
	assert stats["remaining"] == 0
	assert client.offline_queue_size() == 0
