"""Seed script for demo data in the active backend."""

from __future__ import annotations

from .config.database import SessionLocal
from .models import Alert, Camera, Incident, User
from .utils.security import hash_password


def seed() -> None:
    db = SessionLocal()

    print("[seed] Seeding database...")

    alerts = [
        Alert(id="ALT-1023", type="PPE", severity="High", zone="Zone A - Welding", camera="CAM-04", timestamp="10:42 AM", status="New", description="No helmet detected on worker.", thumbnail="https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?q=80&w=800", confidence=98.4),
        Alert(id="ALT-1022", type="Proximity", severity="Medium", zone="Zone B - Forklift", camera="CAM-02", timestamp="10:15 AM", status="Acknowledged", description="Person too close to forklift operating zone.", thumbnail="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=800", confidence=91.2),
        Alert(id="ALT-1021", type="Fall", severity="High", zone="Zone C - Loading", camera="CAM-07", timestamp="09:30 AM", status="Resolved", description="Person detected falling from elevated platform.", thumbnail="https://images.unsplash.com/photo-1590105577767-e21a46b53002?q=80&w=800", confidence=95.8),
        Alert(id="ALT-1020", type="Intrusion", severity="Low", zone="Zone A - Welding", camera="CAM-04", timestamp="08:12 AM", status="Dismissed", description="Unauthorized entry in restricted welding zone.", thumbnail="https://images.unsplash.com/photo-1516937622598-f73fe5209aee?q=80&w=800", confidence=87.5),
    ]

    cameras = [
        Camera(id="CAM-01", name="Main Production Floor", zone="Zone A", status="Online", is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=800", fps=30, health=98),
        Camera(id="CAM-02", name="Warehouse Entrance", zone="Zone B", status="Online", is_privacy_mode=False, thumbnail="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=800", fps=25, health=94),
        Camera(id="CAM-03", name="Logistics Dock 04", zone="Zone C", status="Offline", is_privacy_mode=True, thumbnail="https://images.unsplash.com/photo-1503694978374-8a2fa686963a?q=80&w=800", fps=0, health=0),
    ]

    incidents = [
        Incident(id="INC-2024-001", zone="Zone B - Forklift", classification="Near Miss", severity="High", root_cause="Driver blind spot in narrow aisle", corrective_action="Install convex mirrors at intersections", created_at="2024-10-25"),
        Incident(id="INC-2024-002", zone="Zone A - Welding", classification="Minor Injury", severity="Medium", root_cause="Sparks bypassed face shield", corrective_action="Replace shields and review PPE standard", created_at="2024-10-26"),
    ]

    users = [
        User(id="1", name="Alex Morgan", email="alex.m@visionsafe.co", password_hash=hash_password("admin"), role="Admin", status="Active"),
        User(id="2", name="Sarah Chen", email="sarah.c@visionsafe.co", password_hash=hash_password("safety"), role="Safety Engineer", status="Active"),
        User(id="3", name="Jordan Lee", email="analyst@visionsafe.co", password_hash=hash_password("analyst"), role="Data Analyst", status="Active"),
    ]

    def upsert_by_id(model_cls, items):
        for item in items:
            existing = db.query(model_cls).filter(model_cls.id == item.id).first()
            if existing is None:
                db.add(item)
                continue
            for key, value in item.__dict__.items():
                if key.startswith("_"):
                    continue
                setattr(existing, key, value)

    upsert_by_id(Alert, alerts)
    upsert_by_id(Camera, cameras)
    upsert_by_id(Incident, incidents)
    upsert_by_id(User, users)

    db.commit()
    db.close()
    print("[seed] Database seeded successfully!")


if __name__ == "__main__":
    seed()