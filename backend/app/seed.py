"""Seed script — demo data for development and graduation project demo."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy.exc import OperationalError, ProgrammingError

from .config.database import SessionLocal, Base, engine
from .models import Alert, Area, Camera, Incident, User, SystemConfig, Zone
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
            id="ALT-1023", type="PPE", severity="High", zone="Factory Hall / Welding Station",
            area_id="AREA-FACTORY", area_name="Factory Hall", zone_id="ZONE-WELDING", zone_name="Welding Station",
            location_description="PPE compliance view over the welding station.",
            camera="CAM-04", camera_id="CAM-04", camera_name="Welding Station PPE View",
            occurred_at=_dt(hours_ago=1), status="New",
            description="No helmet detected on worker.",
            thumbnail="https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?q=80&w=800",
            confidence=98.4, created_at=_dt(hours_ago=1),
        ),
        Alert(
            id="ALT-1022", type="Proximity", severity="Medium", zone="Warehouse / Forklift Crossing",
            area_id="AREA-WAREHOUSE", area_name="Warehouse", zone_id="ZONE-FORKLIFT", zone_name="Forklift Crossing",
            location_description="Covers forklift crossing at the warehouse entrance.",
            camera="CAM-02", camera_id="CAM-02", camera_name="Warehouse Forklift Crossing",
            occurred_at=_dt(hours_ago=2), status="Acknowledged",
            description="Person too close to forklift operating zone.",
            thumbnail="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=800",
            confidence=91.2, created_at=_dt(hours_ago=2),
        ),
        Alert(
            id="ALT-1021", type="Fall", severity="High", zone="Loading Zone / Loading Dock",
            area_id="AREA-LOADING", area_name="Loading Zone", zone_id="ZONE-DOCK", zone_name="Loading Dock",
            location_description="Dock camera facing pallet loading and truck bay.",
            camera="CAM-03", camera_id="CAM-03", camera_name="Loading Dock 04",
            occurred_at=_dt(hours_ago=5), status="Resolved",
            description="Person detected falling from elevated platform.",
            thumbnail="https://images.unsplash.com/photo-1590105577767-e21a46b53002?q=80&w=800",
            confidence=95.8, created_at=_dt(hours_ago=5),
        ),
        Alert(
            id="ALT-1020", type="Intrusion", severity="Low", zone="Factory Hall / Welding Station",
            area_id="AREA-FACTORY", area_name="Factory Hall", zone_id="ZONE-WELDING", zone_name="Welding Station",
            location_description="PPE compliance view over the welding station.",
            camera="CAM-04", camera_id="CAM-04", camera_name="Welding Station PPE View",
            occurred_at=_dt(days_ago=1), status="Dismissed",
            description="Unauthorized entry in restricted welding zone.",
            thumbnail="https://images.unsplash.com/photo-1516937622598-f73fe5209aee?q=80&w=800",
            confidence=87.5, created_at=_dt(days_ago=1),
        ),
    ]

    areas = [
        Area(id="AREA-FACTORY", name="Factory Hall", description="Main production hall with workers, machinery, and material flow.", risk_level="High"),
        Area(id="AREA-WAREHOUSE", name="Warehouse", description="Storage aisles and forklift movement area.", risk_level="Medium"),
        Area(id="AREA-CHEMICAL", name="Chemical Area", description="Restricted storage and handling area for hazardous materials.", risk_level="Critical"),
        Area(id="AREA-ASSEMBLY", name="Assembly Area", description="Manual assembly and ergonomic monitoring stations.", risk_level="Medium"),
        Area(id="AREA-LOADING", name="Loading Zone", description="Docking, loading, and unloading operations.", risk_level="High"),
    ]

    zones = [
        Zone(id="ZONE-PROD-A", area_id="AREA-FACTORY", name="Production Line A", description="Conveyor entrance and active worker lane.", risk_level="High"),
        Zone(id="ZONE-FORKLIFT", area_id="AREA-WAREHOUSE", name="Forklift Crossing", description="Intersection between storage aisles and vehicle path.", risk_level="High"),
        Zone(id="ZONE-WELDING", area_id="AREA-FACTORY", name="Welding Station", description="PPE-controlled welding and hot-work station.", risk_level="High"),
        Zone(id="ZONE-DOCK", area_id="AREA-LOADING", name="Loading Dock", description="Truck loading bay and pallet transfer area.", risk_level="High"),
        Zone(id="ZONE-CHEM-STORE", area_id="AREA-CHEMICAL", name="Restricted Chemical Storage", description="Access-controlled chemical storage zone.", risk_level="Critical"),
        Zone(id="ZONE-ASSEMBLY-A", area_id="AREA-ASSEMBLY", name="Assembly Line A", description="Manual assembly benches and posture monitoring lane.", risk_level="Medium"),
    ]

    cameras = [
        Camera(id="CAM-01", name="Production Line A - Overhead View", area_id="AREA-FACTORY", area_name="Factory Hall",
               zone_id="ZONE-PROD-A", zone_name="Production Line A",
               zone="Factory Hall / Production Line A", status="Online",
               is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=800",
               fps=30, health=98, location_description="Mounted above conveyor entrance, facing worker lane.",
               supported_ai_capabilities=["fall", "ppe", "proximity", "ergonomics"], severity_profile="production_line",
               stream_url="rtsp://mediamtx:8554/cam_01"),
        Camera(id="CAM-02", name="Warehouse Forklift Crossing", area_id="AREA-WAREHOUSE", area_name="Warehouse",
               zone_id="ZONE-FORKLIFT", zone_name="Forklift Crossing",
               zone="Warehouse / Forklift Crossing", status="Online",
               is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=800",
               fps=25, health=94, location_description="Covers forklift crossing at the warehouse entrance.",
               supported_ai_capabilities=["ppe", "proximity"], severity_profile="forklift_zone",
               stream_url="rtsp://mediamtx:8554/cam_02"),
        Camera(id="CAM-03", name="Loading Dock 04", area_id="AREA-LOADING", area_name="Loading Zone",
               zone_id="ZONE-DOCK", zone_name="Loading Dock",
               zone="Loading Zone / Loading Dock", status="Offline",
               is_privacy_mode=True, thumbnail="https://images.unsplash.com/photo-1503694978374-8a2fa686963a?q=80&w=800",
               fps=0, health=0, location_description="Dock camera facing pallet loading and truck bay.",
               supported_ai_capabilities=["fall", "ppe", "proximity"], severity_profile="loading_dock",
               stream_url="rtsp://mediamtx:8554/cam_03"),
        Camera(id="CAM-04", name="Welding Station PPE View", area_id="AREA-FACTORY", area_name="Factory Hall",
               zone_id="ZONE-WELDING", zone_name="Welding Station",
               zone="Factory Hall / Welding Station", status="Online",
               is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?q=80&w=800",
               fps=24, health=91, location_description="PPE compliance view over the welding station.",
               supported_ai_capabilities=["ppe", "ergonomics"], severity_profile="hot_work"),
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
        User(id="1", name="Hisham", email="hisham@visionsafe.co",
             password_hash=hash_password("hisham123"), role="Admin", status="Active",
             created_at=_dt(days_ago=30)),
        User(id="2", name="Soltan", email="soltan@visionsafe.co",
             password_hash=hash_password("soltan123"), role="Admin", status="Active",
             created_at=_dt(days_ago=30)),
        User(id="3", name="Raneem", email="raneem@visionsafe.co",
             password_hash=hash_password("raneem123"), role="Safety Engineer", status="Active",
             created_at=_dt(days_ago=30)),
        User(id="4", name="John", email="john@visionsafe.co",
             password_hash=hash_password("john123"), role="Safety Engineer", status="Active",
             created_at=_dt(days_ago=30)),
        User(id="5", name="Shams", email="shams@visionsafe.co",
             password_hash=hash_password("shams123"), role="Data Analyst", status="Active",
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

    def upsert_or_update_by_id(model_cls, items):
        for item in items:
            existing = db.query(model_cls).filter(model_cls.id == item.id).first()
            if existing is None:
                db.add(item)
                continue
            for column in model_cls.__table__.columns:
                if column.primary_key:
                    continue
                value = getattr(item, column.name)
                if value is None:
                    continue
                setattr(existing, column.name, value)

    def upsert_config(configs):
        for cfg in configs:
            if not db.query(SystemConfig).filter(SystemConfig.key == cfg.key).first():
                db.add(cfg)

    try:
        upsert_or_update_by_id(Area, areas)
        upsert_or_update_by_id(Zone, zones)
        upsert_or_update_by_id(Alert, alerts)
        upsert_or_update_by_id(Camera, cameras)
        upsert_by_id(Incident, incidents)
        upsert_by_id(User, users)
        upsert_config(system_configs)
        db.commit()
    except (ProgrammingError, OperationalError):
        db.rollback()
        Base.metadata.create_all(bind=engine)
        upsert_or_update_by_id(Area, areas)
        upsert_or_update_by_id(Zone, zones)
        upsert_or_update_by_id(Alert, alerts)
        upsert_or_update_by_id(Camera, cameras)
        upsert_by_id(Incident, incidents)
        upsert_by_id(User, users)
        upsert_config(system_configs)
        db.commit()
    finally:
        db.close()

    print("[seed] Database seeded successfully!")

if __name__ == "__main__":
    seed()
