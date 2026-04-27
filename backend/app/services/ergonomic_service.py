"""Ergonomic risk record business logic."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import ErgonomicRecord
from ..schemas import ErgonomicRecordCreate


class ErgonomicService:
    @staticmethod
    def list(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        camera_id: str | None = None,
    ) -> tuple[list[ErgonomicRecord], int]:
        q = db.query(ErgonomicRecord)
        if camera_id:
            q = q.filter(ErgonomicRecord.camera_id == camera_id)
        total = q.count()
        items = q.order_by(ErgonomicRecord.recorded_at.desc()).offset(skip).limit(limit).all()
        return items, total

    @staticmethod
    def create(db: Session, payload: ErgonomicRecordCreate) -> ErgonomicRecord:
        record = ErgonomicRecord(**payload.model_dump())
        if record.id is None:
            record.id = str(uuid.uuid4())
        if record.recorded_at is None:
            record.recorded_at = datetime.now(timezone.utc)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_stats(db: Session) -> dict:
        from sqlalchemy import func
        total = db.query(ErgonomicRecord).count()
        high_risk = db.query(ErgonomicRecord).filter(
            ErgonomicRecord.risk_level.in_(["High", "Critical"])
        ).count()
        avg_rula = db.query(func.avg(ErgonomicRecord.rula_score)).scalar() or 0.0
        avg_reba = db.query(func.avg(ErgonomicRecord.reba_score)).scalar() or 0.0
        return {
            "total_records": total,
            "high_risk_count": high_risk,
            "avg_rula_score": round(float(avg_rula), 2),
            "avg_reba_score": round(float(avg_reba), 2),
        }
