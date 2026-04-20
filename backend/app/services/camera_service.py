"""Camera business logic."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Camera
from ..schemas import CameraCreate, CameraUpdate


class CameraService:
	@staticmethod
	def list(db: Session):
		return db.query(Camera).all()

	@staticmethod
	def get(db: Session, camera_id: str):
		return db.query(Camera).filter(Camera.id == camera_id).first()

	@staticmethod
	def create(db: Session, payload: CameraCreate):
		camera = Camera(**payload.model_dump())
		db.add(camera)
		db.commit()
		db.refresh(camera)
		return camera

	@staticmethod
	def update(db: Session, camera_id: str, payload: CameraUpdate):
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