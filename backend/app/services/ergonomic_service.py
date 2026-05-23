"""Ergonomic risk record business logic."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models import ErgonomicRecord, RiskLevelEnum
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
    def get_stats(db: Session, days: int = 7) -> dict:
        high_risk_levels = [RiskLevelEnum.High, RiskLevelEnum.Critical]
        total = db.query(ErgonomicRecord).count()
        high_risk = db.query(ErgonomicRecord).filter(
            ErgonomicRecord.risk_level.in_(high_risk_levels)
        ).count()
        avg_rula = db.query(func.avg(ErgonomicRecord.rula_score)).scalar() or 0.0
        avg_reba = db.query(func.avg(ErgonomicRecord.reba_score)).scalar() or 0.0
        today = datetime.now(timezone.utc).date()
        start_day = today - timedelta(days=max(days - 1, 0))
        cutoff = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

        trend_rows = db.query(
            func.date(ErgonomicRecord.recorded_at).label("date"),
            func.avg(ErgonomicRecord.rula_score).label("avg_rula_score"),
            func.avg(ErgonomicRecord.reba_score).label("avg_reba_score"),
            func.count(ErgonomicRecord.id).label("count"),
        ).filter(
            ErgonomicRecord.recorded_at >= cutoff
        ).group_by(
            func.date(ErgonomicRecord.recorded_at)
        ).order_by("date").all()

        trend_index = {str(row.date): row for row in trend_rows}
        trend: list[dict] = []
        for offset in range(days):
            day_value = start_day + timedelta(days=offset)
            row = trend_index.get(day_value.isoformat())
            trend.append({
                "date": day_value.isoformat(),
                "avg_rula_score": round(float(row.avg_rula_score or 0.0), 2) if row else 0.0,
                "avg_reba_score": round(float(row.avg_reba_score or 0.0), 2) if row else 0.0,
                "count": int(row.count or 0) if row else 0,
            })

        high_risk_case = case(
            (ErgonomicRecord.risk_level.in_(high_risk_levels), 1),
            else_=0,
        )
        zone_rows = db.query(
            ErgonomicRecord.zone.label("zone"),
            func.count(ErgonomicRecord.id).label("count"),
            func.sum(high_risk_case).label("high_risk_count"),
            func.avg(ErgonomicRecord.rula_score).label("avg_rula_score"),
        ).group_by(
            ErgonomicRecord.zone
        ).order_by(
            func.sum(high_risk_case).desc(),
            func.count(ErgonomicRecord.id).desc(),
        ).all()

        zone_distribution = [{
            "zone": row.zone or "Unassigned",
            "count": int(row.count or 0),
            "high_risk_count": int(row.high_risk_count or 0),
            "avg_rula_score": round(float(row.avg_rula_score or 0.0), 2),
        } for row in zone_rows]

        risk_rows = db.query(
            ErgonomicRecord.risk_level.label("risk_level"),
            func.count(ErgonomicRecord.id).label("count"),
        ).group_by(ErgonomicRecord.risk_level).all()

        return {
            "total_records": total,
            "high_risk_count": high_risk,
            "avg_rula_score": round(float(avg_rula), 2),
            "avg_reba_score": round(float(avg_reba), 2),
            "trend": trend,
            "zone_distribution": zone_distribution,
            "risk_distribution": [{
                "risk_level": row.risk_level.value if hasattr(row.risk_level, "value") else str(row.risk_level),
                "count": int(row.count or 0),
            } for row in risk_rows],
        }
