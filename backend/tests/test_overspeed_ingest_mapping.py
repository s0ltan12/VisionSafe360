import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.app.models.enums import HazardTypeEnum
from backend.app.schemas.ingest import HazardEventPayload
from backend.app.services.ingest_service import _map_hazard_type, _normalise_payload


def test_forklift_overspeed_maps_to_overspeed_not_proximity():
    assert _map_hazard_type("forklift_overspeed") == HazardTypeEnum.Overspeed


def test_forklift_overspeed_payload_classification_stays_overspeed():
    event = _normalise_payload(
        HazardEventPayload(
            event_type="forklift_overspeed",
            severity="HIGH",
            camera_id="cam_01",
            timestamp=100.0,
            frame_number=1,
            track_id=42,
            description="Forklift overspeed danger (1.49m/s > 1.39m/s)",
            metadata={"forklift_track_id": 42},
        )
    )

    assert event.event_type == "forklift_overspeed"
    assert event.classification == "Forklift Overspeed"
