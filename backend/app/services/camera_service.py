"""Camera business logic with pagination support."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Camera
from ..schemas import CameraCreate, CameraUpdate


class CameraService:
    @staticmethod
    def list(db: Session, skip: int = 0, limit: int = 200) -> tuple[list[Camera], int]:
        total = db.query(Camera).count()
        items = db.query(Camera).order_by(Camera.name).offset(skip).limit(limit).all()
        return items, total

    @staticmethod
    def get(db: Session, camera_id: str) -> Camera | None:
        return db.query(Camera).filter(Camera.id == camera_id).first()

    @staticmethod
    def create(db: Session, payload: CameraCreate) -> Camera:
        camera = Camera(**payload.model_dump())
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera

    @staticmethod
    def update(db: Session, camera_id: str, payload: CameraUpdate) -> Camera | None:
        camera = CameraService.get(db, camera_id)
        if not camera:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(camera, field, value)
        db.commit()
        db.refresh(camera)
        return camera

    @staticmethod
    def delete(db: Session, camera_id: str) -> bool:
        camera = CameraService.get(db, camera_id)
        if not camera:
            return False
        db.delete(camera)
        db.commit()
        return True