"""Analytics helpers for dashboard stats."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Alert, Camera, Incident, User


class AnalyticsService:
	@staticmethod
	def get_dashboard_stats(db: Session):
		total_alerts = db.query(Alert).count()
		active_alerts = db.query(Alert).filter(Alert.status == "New").count()
		resolved_alerts = db.query(Alert).filter(Alert.status == "Resolved").count()
		total_cameras = db.query(Camera).count()
		online_cameras = db.query(Camera).filter(Camera.status == "Online").count()
		total_incidents = db.query(Incident).count()
		total_users = db.query(User).count()

		return {
			"total_alerts": total_alerts,
			"active_alerts": active_alerts,
			"resolved_alerts": resolved_alerts,
			"total_cameras": total_cameras,
			"online_cameras": online_cameras,
			"offline_cameras": total_cameras - online_cameras,
			"total_incidents": total_incidents,
			"total_users": total_users,
		}