from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "visionsafe360_test_incident_lifecycle.db")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-with-32-characters"

from backend.app.config.database import Base, SessionLocal, engine
from backend.app.models import Alert, Camera, CameraSafetyZone, CameraSafetyZoneEvent, Incident, IncidentEvent, Notification, User
from backend.app.models.enums import HazardTypeEnum, IncidentStatusEnum, StatusEnum
from backend.app.schemas.ingest import HazardEventPayload
from backend.app.schemas import IncidentCreate
from backend.app.schemas.incident import IncidentUpdate
from backend.app.services.ingest_service import IngestService
from backend.app.services.incident_service import IncidentService
from backend.app.services.safety_zone_service import SafetyZoneService
from backend.app.services.sla_service import SLAService


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_module():
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def _composite_incident_id(correlation_id: str) -> str:
    digest = hashlib.sha1(correlation_id.encode("utf-8")).hexdigest()[:16]
    return f"INC-COMP-{digest}"


def _proximity_incident_id(operational_case_id: str) -> str:
    digest = hashlib.sha1(operational_case_id.encode("utf-8")).hexdigest()[:16]
    return f"INC-PROX-{digest}"


def _proximity_payload(
    *,
    operational_case_id: str,
    timestamp: float,
    lifecycle: str,
    stage: str,
    severity: str,
    frame_number: int,
    worker_track_id: int = 7,
    forklift_track_id: int = 101,
) -> HazardEventPayload:
    return HazardEventPayload(
        event_type="forklift_proximity",
        severity=severity,
        camera_id="cam_proximity_lifecycle",
        timestamp=timestamp,
        frame_number=frame_number,
        track_id=worker_track_id,
        description=f"Forklift proximity {stage}",
        metadata={
            "case_type": "forklift_proximity",
            "operational_case_id": operational_case_id,
            "operational_case_key": ["cam_proximity_lifecycle", forklift_track_id, worker_track_id],
            "event_lifecycle": lifecycle,
            "risk_level": stage,
            "risk_score": {
                "monitor": 30.0,
                "warning": 50.0,
                "danger": 70.0,
                "critical": 90.0,
            }.get(stage, 0.0),
            "proximity_alert_stage": stage,
            "worker_track_id": worker_track_id,
            "forklift_track_id": forklift_track_id,
        },
    )


def test_incident_lifecycle_transitions_compute_duration():
    with SessionLocal() as db:
        actor = User(
            id="u-lifecycle",
            name="Lifecycle Operator",
            email="life@example.com",
            password_hash="x",
            role="Safety Engineer",
            status="Active",
        )
        db.add(actor)
        incident = IncidentService.create(
            db,
            IncidentCreate(
                id="INC-LIFE-1",
                zone="Zone Lifecycle",
                classification="PPE Violation",
                severity="Medium",
                root_cause="Under Investigation",
                corrective_action="Pending Review",
            ),
        )

        assert incident.status.value == "New"

        acknowledged = IncidentService.acknowledge(db, incident.id, actor=actor)
        assert acknowledged is not None
        assert acknowledged.status.value == "Acknowledged"
        assert acknowledged.acknowledged_at is not None
        assert acknowledged.acknowledged_by == actor.name

        resolved = IncidentService.resolve(db, incident.id, actor=actor)
        assert resolved is not None
        assert resolved.status.value == "Resolved"
        assert resolved.resolved_at is not None
        assert resolved.resolved_by == actor.name
        assert isinstance(resolved.duration_seconds, int)


def test_incident_list_orders_by_severity_then_created_at():
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        low = IncidentService.create(
            db,
            IncidentCreate(
                id="INC-SORT-LOW",
                zone="Zone Sort",
                classification="Low Risk",
                severity="Low",
                created_at=now,
            ),
        )
        critical = IncidentService.create(
            db,
            IncidentCreate(
                id="INC-SORT-CRIT",
                zone="Zone Sort",
                classification="Critical Risk",
                severity="Critical",
                created_at=now - timedelta(seconds=30),
            ),
        )

        items, _ = IncidentService.list(db, skip=0, limit=10)
        ids = [item.id for item in items]
        assert ids.index(critical.id) < ids.index(low.id)


def test_incident_generic_update_rejects_severity_bypass():
    with SessionLocal() as db:
        incident = IncidentService.create(
            db,
            IncidentCreate(
                id="INC-SEVERITY-BYPASS",
                zone="Zone Update",
                classification="PPE Violation",
                severity="Medium",
            ),
        )

        try:
            IncidentService.update(db, incident.id, IncidentUpdate(severity="Critical"))
            assert False, "severity update should require incident command endpoint"
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400


def test_sla_service_records_breach_timeline_event():
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        incident = IncidentService.create(
            db,
            IncidentCreate(
                id="INC-SLA-ACK",
                zone="Zone SLA",
                classification="Critical Hazard",
                severity="Critical",
                status=IncidentStatusEnum.Active,
                started_at=now - timedelta(minutes=3),
                created_at=now - timedelta(minutes=3),
            ),
        )

        checked = SLAService.check_incident(db, incident.id, now=now)
        assert checked is not None
        assert checked.sla_breached_at is not None
        assert checked.sla_ack_breached_at is not None
        assert checked.sla_breach_count == 1

        events = IncidentService.list_events(db, incident.id)
        assert any(event.action == "sla_breached" for event in events)


def test_ingest_preserves_critical_and_creates_linked_alert_signal():
    with SessionLocal() as db:
        payload = HazardEventPayload(
            id="INC-CRITICAL-CONVERTED",
            zone="Zone Critical",
            classification="Composite Fall Proximity Risk",
            severity="Critical",
            camera_id="cam_critical",
            root_cause="Critical composite hazard",
            metadata={"event_type": "COMPOSITE_FALL_PROXIMITY_RISK"},
        )

        result = IngestService.process(db, payload)

        assert result.status == "accepted"
        incident = IncidentService.get(db, "INC-CRITICAL-CONVERTED")
        assert incident is not None
        assert incident.severity.value == "Critical"
        alert = db.query(Alert).filter(Alert.incident_id == incident.id).first()
        assert alert is not None
        assert alert.severity.value == "Critical"
        assert alert.incident_id == incident.id


def test_same_second_same_worker_ppe_ingest_creates_one_notification_thread():
    with SessionLocal() as db:
        base = {
            "severity": "High",
            "camera_id": "CAM-PPE-DEDUPE",
            "timestamp": 1781713179.2,
            "frame_number": 915,
            "track_id": 1,
        }

        first = IngestService.process(
            db,
            HazardEventPayload(
                **base,
                event_type="ppe_missing",
                description="PPE missing helmet, gloves track=1",
                metadata={
                    "worker_track_id": 1,
                    "missing_ppe_items": ["helmet", "gloves"],
                    "display_title": "PPE missing helmet, gloves",
                },
            ),
        )
        second = IngestService.process(
            db,
            HazardEventPayload(
                **base,
                event_type="ppe_missing_gloves",
                description="PPE missing: gloves track=1",
                metadata={"worker_track_id": 1, "ppe_item": "gloves"},
            ),
        )

        assert first.status == "accepted"
        assert second.status == "duplicate"
        incident = db.query(Incident).filter(Incident.id == first.incident_id).first()
        assert incident is not None
        assert incident.classification == "PPE missing helmet, gloves"
        alert = db.query(Alert).filter(Alert.incident_id == first.incident_id).first()
        assert alert is not None
        assert alert.description == "PPE missing helmet, gloves track=1"
        notifications = (
            db.query(Notification)
            .filter(Notification.message.like(f"{first.incident_id}:%"))
            .all()
        )
        assert len(notifications) == 1


def test_safety_zone_ingest_creates_dashboard_alert_notification_and_zone_event():
    with SessionLocal() as db:
        db.add(
            Camera(
                id="CAM-ZONE-INGEST",
                name="Zone Ingest Camera",
                zone="Factory / Danger Zone",
                status="Online",
            )
        )
        db.add(
            CameraSafetyZone(
                id="CSZ-INGEST",
                camera_id="CAM-ZONE-INGEST",
                name="Danger Zone",
                zone_type="danger",
                polygon=[
                    {"x": 100, "y": 100},
                    {"x": 300, "y": 100},
                    {"x": 300, "y": 300},
                    {"x": 100, "y": 300},
                ],
                source_width=640,
                source_height=480,
                rules={"severity": "Critical", "cooldown_sec": 0},
            )
        )
        db.commit()

        payload = HazardEventPayload(
            event_type="zone_person_entered",
            severity="Critical",
            camera_id="CAM-ZONE-INGEST",
            timestamp=100.0,
            frame_number=12,
            track_id=7,
            bbox=[140, 120, 180, 180],
            description="Person entered danger zone: Danger Zone",
            metadata={
                "safety_zone": True,
                "safety_zone_id": "CSZ-INGEST",
                "safety_zone_name": "Danger Zone",
                "zone_event_type": "enter",
                "object_class": "person",
                "stable_object_key": "person:7",
                "anchor_point": {"x": 160, "y": 180},
                "safety_zone_snapshot": {
                    "id": "CSZ-INGEST",
                    "name": "Danger Zone",
                    "zone_type": "danger",
                    "polygon": [
                        {"x": 100, "y": 100},
                        {"x": 300, "y": 100},
                        {"x": 300, "y": 300},
                        {"x": 100, "y": 300},
                    ],
                    "coordinate_space": "source_pixels",
                    "source_width": 640,
                    "source_height": 480,
                    "color": "#f97316",
                    "enabled": True,
                    "priority": 100,
                },
            },
        )

        result = IngestService.process(db, payload)

        assert result.status == "accepted"
        alert = db.query(Alert).filter(Alert.id == result.alert_id).first()
        assert alert is not None
        assert alert.description == "Worker in danger zone: Danger Zone"
        assert alert.type == HazardTypeEnum.Intrusion
        assert alert.zone_id == "CSZ-INGEST"
        assert alert.zone_name == "Danger Zone"
        assert alert.status == StatusEnum.New
        assert alert.event_metadata["safety_zone_snapshot"]["id"] == "CSZ-INGEST"
        assert db.query(Notification).filter(Notification.message.like(f"{result.incident_id}:%")).count() == 1

        zone_event = db.query(CameraSafetyZoneEvent).filter(
            CameraSafetyZoneEvent.zone_id == "CSZ-INGEST",
            CameraSafetyZoneEvent.alert_id == alert.id,
        ).first()
        assert zone_event is not None
        assert zone_event.event_type == "enter"
        assert zone_event.object_class == "person"
        assert zone_event.track_id == 7


def test_legacy_safety_zone_exit_payload_is_ignored():
    with SessionLocal() as db:
        payload = HazardEventPayload(
            event_type="zone_exit",
            severity="Medium",
            camera_id="CAM-ZONE-INGEST",
            timestamp=101.0,
            frame_number=13,
            track_id=7,
            description="Person exit zone: Danger Zone",
            metadata={
                "safety_zone": True,
                "safety_zone_id": "CSZ-INGEST",
                "safety_zone_name": "Danger Zone",
                "zone_event_type": "exit",
                "object_class": "person",
            },
        )

        result = IngestService.process(db, payload)

        assert result.status == "ignored"
        assert result.incident_id is None
        assert result.alert_id is None


def test_safety_zone_event_schema_accepts_fractional_dwell_duration():
    with SessionLocal() as db:
        if db.query(Camera).filter(Camera.id == "CAM-ZONE-FLOAT").first() is None:
            db.add(
                Camera(
                    id="CAM-ZONE-FLOAT",
                    name="Zone Float Camera",
                    zone="Factory / Float Zone",
                    status="Online",
                )
            )
        if db.query(CameraSafetyZone).filter(CameraSafetyZone.id == "CSZ-FLOAT").first() is None:
            db.add(
                CameraSafetyZone(
                    id="CSZ-FLOAT",
                    camera_id="CAM-ZONE-FLOAT",
                    name="Float Zone",
                    zone_type="danger",
                    polygon=[
                        {"x": 0, "y": 0},
                        {"x": 100, "y": 0},
                        {"x": 100, "y": 100},
                    ],
                    source_width=640,
                    source_height=480,
                    rules={},
                )
            )
        SafetyZoneService.record_event(
            db,
            zone_id="CSZ-FLOAT",
            camera_id="CAM-ZONE-FLOAT",
            event_type="dwell_time_exceeded",
            object_class="person",
            track_id=4,
            stable_object_key="person:4",
            severity="High",
            occurred_at=datetime.now(timezone.utc),
            duration_inside_sec=1.386,
        )
        db.commit()

        event = SafetyZoneService.list_events(db, camera_id="CAM-ZONE-FLOAT")[0]
        assert event.duration_inside_sec == 1.386


def test_incident_lifecycle_commands_sync_linked_alert_signal():
    with SessionLocal() as db:
        actor = User(
            id="u-alert-sync",
            name="Alert Sync Operator",
            email="alert-sync@example.com",
            password_hash="x",
            role="Safety Engineer",
            status="Active",
        )
        db.add(actor)
        payload = HazardEventPayload(
            id="INC-ALERT-SYNC",
            zone="Zone Alert Sync",
            classification="PPE Forklift Risk",
            severity="High",
            camera_id="cam_alert_sync",
            metadata={"event_type": "COMPOSITE_PPE_FORKLIFT_RISK"},
        )
        result = IngestService.process(db, payload)
        assert result.status == "accepted"

        incident = IncidentService.get(db, "INC-ALERT-SYNC")
        assert incident is not None
        alert = db.query(Alert).filter(Alert.incident_id == incident.id).first()
        assert alert is not None
        assert alert.status == StatusEnum.New

        acknowledged = IncidentService.acknowledge(db, incident.id, actor=actor)
        assert acknowledged is not None
        db.refresh(alert)
        assert alert.status == StatusEnum.Acknowledged
        assert alert.acknowledged_by == actor.name
        assert alert.acknowledged_at is not None

        resolved = IncidentService.resolve(db, incident.id, actor=actor)
        assert resolved is not None
        db.refresh(alert)
        assert alert.status == StatusEnum.Resolved
        assert alert.resolved_by == actor.name
        assert alert.resolved_at is not None


def test_sla_service_ignores_false_positive_history_incidents():
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        incident = IncidentService.create(
            db,
            IncidentCreate(
                id="INC-SLA-FALSE-POSITIVE",
                zone="Zone SLA",
                classification="Dismissed Hazard",
                severity="Critical",
                status=IncidentStatusEnum.False_Positive,
                started_at=now - timedelta(minutes=30),
                created_at=now - timedelta(minutes=30),
            ),
        )

        checked = SLAService.check_incident(db, incident.id, now=now)
        db.refresh(incident)

        assert checked is not None
        assert incident.sla_breached_at is None
        assert incident.sla_breach_count == 0


def test_composite_ingest_merges_sources_and_emits_single_stream():
    with SessionLocal() as db:
        source_ts = 1_780_000_001.25
        source_camera = "cam_composite_lifecycle"
        source_track_id = 77
        ppe_payload = HazardEventPayload(
            event_type="PPE_MISSING_HELMET",
            severity="HIGH",
            camera_id=source_camera,
            timestamp=source_ts,
            frame_number=11,
            track_id=source_track_id,
            description="Missing helmet",
            metadata={
                "track_id": source_track_id,
                "worker_track_id": source_track_id,
            },
        )
        forklift_payload = HazardEventPayload(
            event_type="FORKLIFT_PROXIMITY_DANGER",
            severity="HIGH",
            camera_id=source_camera,
            timestamp=source_ts,
            frame_number=12,
            track_id=source_track_id,
            description="Forklift proximity danger",
            metadata={
                "track_id": source_track_id,
                "worker_track_id": source_track_id,
                "forklift_track_id": 501,
            },
        )

        ppe_result = IngestService.process(db, ppe_payload)
        forklift_result = IngestService.process(db, forklift_payload)
        assert ppe_result.status == "accepted"
        assert forklift_result.status == "accepted"
        assert db.query(Incident).filter(Incident.id == ppe_result.incident_id).first() is not None
        assert db.query(Incident).filter(Incident.id == forklift_result.incident_id).first() is not None
        assert db.query(Alert).filter(Alert.incident_id.in_([ppe_result.incident_id, forklift_result.incident_id])).count() == 2
        assert db.query(Notification).filter(Notification.message.like(f"{ppe_result.incident_id}:%")).count() == 1
        assert db.query(Notification).filter(Notification.message.like(f"{forklift_result.incident_id}:%")).count() == 1

        correlation_id = f"{source_camera}:worker:{source_track_id}:forklift:501:COMPOSITE_PPE_FORKLIFT_RISK"
        composite_id = _composite_incident_id(correlation_id)
        composite_payload = HazardEventPayload(
            event_type="COMPOSITE_PPE_FORKLIFT_RISK",
            severity="CRITICAL",
            camera_id=source_camera,
            timestamp=source_ts + 0.5,
            frame_number=13,
            track_id=source_track_id,
            description="Worker has PPE violation during forklift proximity danger",
            metadata={
                "composite": True,
                "correlation_id": correlation_id,
                "track_id": source_track_id,
                "worker_track_id": source_track_id,
                "forklift_track_id": 501,
                "component_hazards": [
                    {
                        "label": "Missing Helmet",
                        "event_type": "PPE_MISSING_HELMET",
                        "severity": "HIGH",
                        "track_id": source_track_id,
                        "worker_track_id": source_track_id,
                        "timestamp": source_ts,
                        "frame_number": 11,
                    },
                    {
                        "label": "Forklift Proximity Danger",
                        "event_type": "FORKLIFT_PROXIMITY_DANGER",
                        "severity": "HIGH",
                        "track_id": source_track_id,
                        "worker_track_id": source_track_id,
                        "forklift_track_id": 501,
                        "timestamp": source_ts,
                        "frame_number": 12,
                    },
                ],
                "source_events": [
                    {
                        "event_type": "PPE_MISSING_HELMET",
                        "severity": "HIGH",
                        "track_id": source_track_id,
                        "worker_track_id": source_track_id,
                        "timestamp": source_ts,
                        "frame_number": 11,
                    },
                    {
                        "event_type": "FORKLIFT_PROXIMITY_DANGER",
                        "severity": "HIGH",
                        "track_id": source_track_id,
                        "worker_track_id": source_track_id,
                        "forklift_track_id": 501,
                        "timestamp": source_ts,
                        "frame_number": 12,
                    },
                ],
                "source_event_types": ["PPE_MISSING_HELMET", "FORKLIFT_PROXIMITY_DANGER"],
            },
        )

        composite_result = IngestService.process(db, composite_payload)

        assert composite_result.status == "accepted"
        assert composite_result.incident_id == composite_id
        assert db.query(Incident).filter(Incident.id == composite_id).count() == 1
        assert db.query(Incident).filter(Incident.id.in_([ppe_result.incident_id, forklift_result.incident_id])).count() == 0
        assert db.query(Alert).filter(Alert.incident_id == composite_id).count() == 1
        assert db.query(Alert).filter(Alert.incident_id.in_([ppe_result.incident_id, forklift_result.incident_id])).count() == 0
        assert db.query(Notification).filter(Notification.message.like(f"{composite_id}:%")).count() == 1
        assert db.query(Notification).filter(Notification.message.like(f"{ppe_result.incident_id}:%")).count() == 0
        assert db.query(Notification).filter(Notification.message.like(f"{forklift_result.incident_id}:%")).count() == 0

        events = db.query(IncidentEvent).filter(IncidentEvent.incident_id == composite_id).all()
        actions = [event.action for event in events]
        assert actions.count("composite_created") == 1
        assert actions.count("source_hazard_attached") == 2
        assert actions.count("source_incidents_merged") == 1
        attached = [event for event in events if event.action == "source_hazard_attached"]
        attached_types = {
            event.event_metadata["component_hazard"]["event_type"]
            for event in attached
        }
        assert attached_types == {"PPE_MISSING_HELMET", "FORKLIFT_PROXIMITY_DANGER"}

        duplicate_result = IngestService.process(db, composite_payload)

        assert duplicate_result.status == "duplicate"
        assert duplicate_result.incident_id == composite_id
        assert db.query(Incident).filter(Incident.id == composite_id).count() == 1
        assert db.query(Alert).filter(Alert.incident_id == composite_id).count() == 1
        assert db.query(Notification).filter(Notification.message.like(f"{composite_id}:%")).count() == 1


def test_operational_proximity_updates_one_incident_alert_and_notification_stream():
    with SessionLocal() as db:
        case_id = "prox:cam_proximity_lifecycle:forklift:101:worker:7:epoch:100"
        incident_id = _proximity_incident_id(case_id)
        events = [
            _proximity_payload(
                operational_case_id=case_id,
                timestamp=100.0,
                lifecycle="created",
                stage="monitor",
                severity="LOW",
                frame_number=1,
            ),
            _proximity_payload(
                operational_case_id=case_id,
                timestamp=150.0,
                lifecycle="escalated",
                stage="warning",
                severity="MEDIUM",
                frame_number=2,
            ),
            _proximity_payload(
                operational_case_id=case_id,
                timestamp=200.0,
                lifecycle="escalated",
                stage="critical",
                severity="CRITICAL",
                frame_number=3,
            ),
            _proximity_payload(
                operational_case_id=case_id,
                timestamp=250.0,
                lifecycle="deescalated",
                stage="warning",
                severity="MEDIUM",
                frame_number=4,
            ),
            _proximity_payload(
                operational_case_id=case_id,
                timestamp=305.0,
                lifecycle="resolved",
                stage="monitor",
                severity="LOW",
                frame_number=5,
            ),
        ]

        results = [IngestService.process(db, payload) for payload in events]

        assert results[0].status == "accepted"
        assert [result.incident_id for result in results] == [incident_id] * len(results)
        assert db.query(Incident).filter(Incident.id == incident_id).count() == 1
        assert db.query(Alert).filter(Alert.incident_id == incident_id).count() == 1
        assert db.query(Notification).filter(Notification.message.like(f"{incident_id}:%")).count() == 2
        assert db.query(Notification).filter(
            Notification.message.like(f"{incident_id}:%Critical%")
        ).count() == 1

        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        assert incident is not None
        assert incident.status == IncidentStatusEnum.Resolved
        assert incident.severity.value == "Low"
        alert = db.query(Alert).filter(Alert.incident_id == incident_id).first()
        assert alert is not None
        assert alert.status == StatusEnum.Resolved

        actions = [
            event.action
            for event in db.query(IncidentEvent)
            .filter(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at.asc())
            .all()
        ]
        assert actions == [
            "created",
            "risk_escalated",
            "risk_escalated",
            "risk_deescalated",
            "resolved",
        ]


def test_operational_proximity_reopen_updates_same_case():
    with SessionLocal() as db:
        case_id = "prox:cam_proximity_lifecycle:forklift:101:worker:7:epoch:500"
        incident_id = _proximity_incident_id(case_id)

        IngestService.process(db, _proximity_payload(
            operational_case_id=case_id,
            timestamp=500.0,
            lifecycle="created",
            stage="monitor",
            severity="LOW",
            frame_number=1,
        ))
        IngestService.process(db, _proximity_payload(
            operational_case_id=case_id,
            timestamp=506.0,
            lifecycle="resolved",
            stage="monitor",
            severity="LOW",
            frame_number=2,
        ))
        reopened = IngestService.process(db, _proximity_payload(
            operational_case_id=case_id,
            timestamp=515.0,
            lifecycle="reopened",
            stage="warning",
            severity="MEDIUM",
            frame_number=3,
        ))

        assert reopened.incident_id == incident_id
        assert db.query(Incident).filter(Incident.id == incident_id).count() == 1
        assert db.query(Alert).filter(Alert.incident_id == incident_id).count() == 1
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        assert incident.status == IncidentStatusEnum.Active
        actions = [
            event.action
            for event in db.query(IncidentEvent)
            .filter(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at.asc())
            .all()
        ]
        assert "reopened" in actions


def test_composite_attaches_to_active_proximity_operational_case():
    with SessionLocal() as db:
        case_id = "prox:cam_composite_parent:forklift:101:worker:7:epoch:900"
        incident_id = _proximity_incident_id(case_id)
        proximity_result = IngestService.process(db, _proximity_payload(
            operational_case_id=case_id,
            timestamp=900.0,
            lifecycle="created",
            stage="danger",
            severity="HIGH",
            frame_number=1,
        ))
        assert proximity_result.incident_id == incident_id

        composite_payload = HazardEventPayload(
            event_type="COMPOSITE_PPE_FORKLIFT_RISK",
            severity="CRITICAL",
            camera_id="cam_proximity_lifecycle",
            timestamp=901.0,
            frame_number=2,
            track_id=7,
            description="Composite PPE forklift risk",
            metadata={
                "composite": True,
                "correlation_id": "cam_proximity_lifecycle:worker:7:forklift:101:COMPOSITE_PPE_FORKLIFT_RISK",
                "parent_operational_case_id": case_id,
                "worker_track_id": 7,
                "forklift_track_id": 101,
                "component_hazards": [
                    {
                        "label": "Missing Helmet",
                        "event_type": "ppe_missing_helmet",
                        "severity": "HIGH",
                        "track_id": 7,
                        "worker_track_id": 7,
                    },
                    {
                        "label": "Forklift Proximity Danger",
                        "event_type": "forklift_proximity",
                        "severity": "HIGH",
                        "track_id": 7,
                        "worker_track_id": 7,
                        "forklift_track_id": 101,
                    },
                ],
                "source_event_types": ["ppe_missing_helmet", "forklift_proximity"],
            },
        )

        composite_result = IngestService.process(db, composite_payload)

        assert composite_result.status == "updated"
        assert composite_result.incident_id == incident_id
        assert db.query(Incident).filter(Incident.id == incident_id).count() == 1
        assert db.query(Incident).filter(
            Incident.id == _composite_incident_id(
                "cam_proximity_lifecycle:worker:7:forklift:101:COMPOSITE_PPE_FORKLIFT_RISK"
            )
        ).count() == 0
        assert db.query(Alert).filter(Alert.incident_id == incident_id).count() == 1
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        assert incident.severity.value == "Critical"
        actions = [
            event.action
            for event in db.query(IncidentEvent)
            .filter(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at.asc())
            .all()
        ]
        assert "composite_attached" in actions
        assert actions.count("source_hazard_attached") == 2
