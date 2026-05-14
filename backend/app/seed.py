"""Seed script — demo data for development and graduation project demo."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy.exc import OperationalError, ProgrammingError

from .config.database import SessionLocal, Base, engine
from .models import Alert, Camera, Incident, User, SystemConfig
from .utils.security import hash_password

_NOW = datetime.now(timezone.utc)


def _dt(days_ago: int = 0, hours_ago: int = 0) -> datetime:
    return _NOW - timedelta(days=days_ago, hours=hours_ago)


def seed() -> None:
    db = SessionLocal()
    print("[seed] Seeding database...")
    Base.metadata.create_all(bind=engine)

    # ── Safe migration: add stream_url column if it doesn't exist ──────
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS stream_url VARCHAR(512)"
            ))
            conn.commit()
        print("[seed] Migration: stream_url column ensured on cameras table.")
    except Exception as exc:
        print(f"[seed] Migration warning (non-fatal): {exc}")

    alerts = [
        Alert(
            id="ALT-1023", type="PPE", severity="High", zone="Zone A - Welding",
            camera="CAM-04", occurred_at=_dt(hours_ago=1), status="New",
            description="No helmet detected on worker.",
            thumbnail="https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?q=80&w=800",
            confidence=98.4, created_at=_dt(hours_ago=1),
        ),
        Alert(
            id="ALT-1022", type="Proximity", severity="Medium", zone="Zone B - Forklift",
            camera="CAM-02", occurred_at=_dt(hours_ago=2), status="Acknowledged",
            description="Person too close to forklift operating zone.",
            thumbnail="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=800",
            confidence=91.2, created_at=_dt(hours_ago=2),
        ),
        Alert(
            id="ALT-1021", type="Fall", severity="High", zone="Zone C - Loading",
            camera="CAM-07", occurred_at=_dt(hours_ago=5), status="Resolved",
            description="Person detected falling from elevated platform.",
            thumbnail="https://images.unsplash.com/photo-1590105577767-e21a46b53002?q=80&w=800",
            confidence=95.8, created_at=_dt(hours_ago=5),
        ),
        Alert(
            id="ALT-1020", type="Intrusion", severity="Low", zone="Zone A - Welding",
            camera="CAM-04", occurred_at=_dt(days_ago=1), status="Dismissed",
            description="Unauthorized entry in restricted welding zone.",
            thumbnail="https://images.unsplash.com/photo-1516937622598-f73fe5209aee?q=80&w=800",
            confidence=87.5, created_at=_dt(days_ago=1),
        ),
    ]

    cameras = [
        Camera(id="CAM-01", name="Main Production Floor", zone="Zone A", status="Online",
               is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=800",
               fps=30, health=98,
               stream_url="rtsp://mediamtx:8554/cam_01"),
        Camera(id="CAM-02", name="Warehouse Entrance", zone="Zone B", status="Online",
               is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=800",
               fps=25, health=94,
               stream_url="rtsp://mediamtx:8554/cam_02"),
        Camera(id="CAM-03", name="Logistics Dock 04", zone="Zone C", status="Offline",
               is_privacy_mode=True, thumbnail="https://images.unsplash.com/photo-1503694978374-8a2fa686963a?q=80&w=800",
               fps=0, health=0,
               stream_url="rtsp://mediamtx:8554/cam_03"),
    ]

    incidents = [
        Incident(id="INC-2024-001", zone="Zone B - Forklift", classification="Near Miss",
                 severity="High", root_cause="Driver blind spot in narrow aisle",
                 corrective_action="Install convex mirrors at intersections",
                 created_at=_dt(days_ago=7)),
        Incident(id="INC-2024-002", zone="Zone A - Welding", classification="Minor Injury",
                 severity="Medium", root_cause="Sparks bypassed face shield",
                 corrective_action="Replace shields and review PPE standard",
                 created_at=_dt(days_ago=6)),
        Incident(id="INC-2024-003", zone="Zone C - Loading", classification="Property Damage",
                 severity="Low", root_cause="Forklift clipped rack during reversing",
                 corrective_action="Add proximity sensors on forklifts",
                 created_at=_dt(days_ago=3)),
    ]

    users = [
        User(id="1", name="Alex Morgan", email="alex.m@visionsafe.co",
             password_hash=hash_password("Admin123"), role="Admin", status="Active",
             created_at=_dt(days_ago=30)),
        User(id="2", name="Sarah Chen", email="sarah.c@visionsafe.co",
             password_hash=hash_password("Safety123"), role="Safety Engineer", status="Active",
             created_at=_dt(days_ago=30)),
        User(id="3", name="Jordan Lee", email="analyst@visionsafe.co",
             password_hash=hash_password("Analyst123"), role="Data Analyst", status="Active",
             created_at=_dt(days_ago=30)),
    ]

    system_configs = [
        SystemConfig(key="system.facility_name", value="VisionSafe Industrial Facility",
                     value_type="string", description="Name of the monitored facility"),
        SystemConfig(key="system.timezone", value="UTC", value_type="string",
                     description="Operational timezone"),
        SystemConfig(key="system.alert_retention_days", value="90", value_type="int",
                     description="Number of days to keep alert records"),
        SystemConfig(key="system.notifications.email_enabled", value="false", value_type="bool",
                     description="Enable email notifications"),
    ]

    def upsert_by_id(model_cls, items):
        for item in items:
            existing = db.query(model_cls).filter(model_cls.id == item.id).first()
            if existing is None:
                db.add(item)

    def upsert_config(configs):
        for cfg in configs:
            if not db.query(SystemConfig).filter(SystemConfig.key == cfg.key).first():
                db.add(cfg)

    try:
        upsert_by_id(Alert, alerts)
        upsert_by_id(Camera, cameras)
        upsert_by_id(Incident, incidents)
        upsert_by_id(User, users)
        upsert_config(system_configs)
        db.commit()
    except (ProgrammingError, OperationalError):
        db.rollback()
        Base.metadata.create_all(bind=engine)
        upsert_by_id(Alert, alerts)
        upsert_by_id(Camera, cameras)
        upsert_by_id(Incident, incidents)
        upsert_by_id(User, users)
        upsert_config(system_configs)
        db.commit()
    finally:
        db.close()

    print("[seed] Database seeded successfully!")

    # ── Patch stream_url on existing cameras that are missing it ──────
    _stream_url_map = {
        "CAM-01": "rtsp://mediamtx:8554/cam_01",
        "CAM-02": "rtsp://mediamtx:8554/cam_02",
        "CAM-03": "rtsp://mediamtx:8554/cam_03",
    }
    db2 = SessionLocal()
    try:
        for cam_id, stream_url in _stream_url_map.items():
            cam = db2.query(Camera).filter(Camera.id == cam_id).first()
            if cam and not cam.stream_url:
                cam.stream_url = stream_url
        db2.commit()
        print("[seed] stream_url patched on existing cameras.")
    except Exception as exc:
        db2.rollback()
        print(f"[seed] stream_url patch warning (non-fatal): {exc}")
    finally:
        db2.close()



if __name__ == "__main__":
    seed()