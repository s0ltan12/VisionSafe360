import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.composite_hazard_engine import CompositeHazardEngine
from src.analysis.event_aggregator import EventAggregator
from src.analysis.zone_config_loader import ZoneConfigLoader
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity


def _event(
    event_type: str,
    *,
    track_id: int | None = 1,
    ts: float = 100.0,
    stable_worker: bool = True,
    forklift_track_id: int | None = 101,
) -> HazardEvent:
    metadata = {
        "worker_track_id": track_id if stable_worker else None,
        "worker_track_id_valid": stable_worker and track_id is not None,
        "worker_track_id_fallback": not stable_worker,
        "worker_track_id_source": "bytetrack" if stable_worker else "fallback",
        "composite_eligible": stable_worker and track_id is not None,
    }
    if "forklift" in event_type or "proximity" in event_type:
        metadata["forklift_track_id"] = forklift_track_id
        metadata["proximity_risk"] = "danger"
    return HazardEvent(
        event_type=event_type,
        severity=Severity.HIGH,
        camera_id="cam_01",
        timestamp=ts,
        frame_number=10,
        track_id=track_id,
        bbox=(10, 10, 100, 180),
        description=event_type,
        metadata=metadata,
    )


def test_composite_ppe_forklift_risk_for_same_track() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0, composite_cooldown_sec=8.0)

    assert engine.process([_event("ppe_missing_helmet", ts=100.0)], 100.0) == []
    emitted = engine.process([_event("forklift_proximity_danger", ts=100.4)], 100.4)

    assert len(emitted) == 1
    assert emitted[0].event_type == "COMPOSITE_PPE_FORKLIFT_RISK"
    assert emitted[0].severity == Severity.CRITICAL
    assert emitted[0].metadata["composite"] is True
    assert emitted[0].metadata["source_event_types"] == [
        "ppe_missing_helmet",
        "forklift_proximity_danger",
    ]
    assert emitted[0].metadata["correlation_id"]
    assert emitted[0].metadata["worker_track_id"] == 1
    assert emitted[0].metadata["component_hazards"][0]["label"] == "Missing Helmet"
    assert emitted[0].metadata["source_events"][0]["aggregation_key"]


def test_composite_does_not_cross_track_ids() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0)

    assert engine.process([_event("ppe_missing_helmet", track_id=1)], 100.0) == []
    emitted = engine.process([_event("forklift_proximity_danger", track_id=2)], 100.2)

    assert emitted == []


def test_composite_rejects_fallback_worker_track_id() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0)

    helmet = _event("ppe_missing_helmet", track_id=1, stable_worker=False)
    forklift = _event("forklift_proximity_danger", track_id=1, stable_worker=True)

    assert engine.process([helmet], 100.0) == []
    assert engine.process([forklift], 100.2) == []


def test_composite_rejects_null_worker_track_id() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0)

    helmet = _event("ppe_missing_helmet", track_id=None, stable_worker=False)
    forklift = _event("forklift_proximity_danger", track_id=None, stable_worker=False)

    assert engine.process([helmet, forklift], 100.0) == []


def test_composite_rejects_worker_track_without_stability_metadata() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0)

    helmet = _event("ppe_missing_helmet", track_id=7)
    forklift = _event("forklift_proximity_danger", track_id=7)
    helmet.metadata = {"worker_track_id": 7}
    forklift.metadata = {"worker_track_id": 7, "forklift_track_id": 101, "proximity_risk": "danger"}

    assert engine.process([helmet], 100.0) == []
    assert engine.process([forklift], 100.2) == []


def test_composite_source_events_can_be_suppressed() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0, composite_cooldown_sec=8.0)
    helmet = _event("ppe_missing_helmet", ts=100.0)
    forklift = _event("forklift_proximity_danger", ts=100.4)

    assert engine.process([helmet], 100.0) == []
    composites = engine.process([forklift], 100.4)
    remaining = engine.suppress_source_events([helmet, forklift], composites)

    assert len(composites) == 1
    assert remaining == []


def test_continuous_composite_exposure_emits_one_operational_event() -> None:
    engine = CompositeHazardEngine(temporal_window_sec=2.0, composite_cooldown_sec=8.0)
    aggregator = EventAggregator()

    frames = [
        (100.0, [_event("ppe_missing_helmet", ts=100.0)]),
        (100.4, [_event("forklift_proximity_danger", ts=100.4)]),
        (101.0, [_event("ppe_missing_helmet", ts=101.0), _event("forklift_proximity_danger", ts=101.0)]),
        (108.5, [_event("ppe_missing_helmet", ts=108.5), _event("forklift_proximity_danger", ts=108.5)]),
    ]

    emitted: list[HazardEvent] = []
    composite_heartbeats = 0
    for timestamp, source_events in frames:
        composites = engine.process(source_events, timestamp)
        composite_heartbeats += len(composites)
        if composites:
            source_events = engine.suppress_source_events(source_events, composites)
        emitted.extend(aggregator.process(source_events + composites, timestamp))

    assert composite_heartbeats == 3
    composite_events = [
        event for event in emitted
        if event.event_type == "COMPOSITE_PPE_FORKLIFT_RISK"
    ]
    assert len(composite_events) >= 1
    assert aggregator.active_count == 1


def test_zone_config_loader_attaches_camera_risk(tmp_path: Path) -> None:
    config = tmp_path / "zone_config.json"
    config.write_text(
        '{"camera_zones":{"cam_01":"zone_a"},"zones":{"zone_a":{"risk_level":"HIGH","display_name":"Loading"}}}',
        encoding="utf-8",
    )
    loader = ZoneConfigLoader(config)
    enriched = loader.enrich_event(_event("ppe_missing_helmet"))

    assert enriched.metadata["zone_config"]["risk_level"] == "HIGH"
    assert enriched.metadata["zone_risk"] == "HIGH"
    assert enriched.metadata["zone"] == "Loading"
