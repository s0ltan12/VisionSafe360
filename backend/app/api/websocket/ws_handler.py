"""WebSocket handlers for realtime incident updates."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...config.database import SessionLocal
from ...services.monitoring_service import monitoring_service
from ...utils.security import get_user_from_token


router = APIRouter()
logger = logging.getLogger("visionsafe.websocket")


def serialize_incident(incident) -> dict:
	return {
		"id": incident.id,
		"zone": incident.zone,
		"classification": incident.classification,
		"severity": str(incident.severity),
		"root_cause": incident.root_cause,
		"corrective_action": incident.corrective_action,
		"created_at": incident.created_at,
	}


class IncidentWebSocketManager:
	"""In-memory broadcaster for incident events."""

	def __init__(self) -> None:
		self._connections: set[WebSocket] = set()

	async def connect(self, websocket: WebSocket) -> None:
		await websocket.accept()
		self._connections.add(websocket)

	def disconnect(self, websocket: WebSocket) -> None:
		self._connections.discard(websocket)

	async def broadcast(self, payload: dict) -> None:
		dead: list[WebSocket] = []
		for websocket in list(self._connections):
			try:
				await websocket.send_json(payload)
			except Exception:
				dead.append(websocket)
		for websocket in dead:
			self.disconnect(websocket)


incident_ws_manager = IncidentWebSocketManager()


def _extract_ws_token(websocket: WebSocket) -> str | None:
	authorization = websocket.headers.get("authorization")
	if authorization and authorization.lower().startswith("bearer "):
		token = authorization.split(" ", 1)[1].strip()
		if token:
			return token

	query_token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
	if query_token:
		return query_token.strip()

	return None


@router.websocket("/ws/incidents")
async def incidents_ws(websocket: WebSocket):
	token = _extract_ws_token(websocket)
	if not token:
		logger.warning("ws unauthorized: missing token", extra={"event": "ws_unauthorized"})
		await websocket.close(code=1008, reason="Unauthorized")
		return

	db = SessionLocal()
	try:
		user = get_user_from_token(token, db)
	finally:
		db.close()

	if user is None:
		logger.warning("ws unauthorized: invalid token", extra={"event": "ws_unauthorized"})
		await websocket.close(code=1008, reason="Unauthorized")
		return

	await incident_ws_manager.connect(websocket)
	active = monitoring_service.ws_connected()
	logger.info(
		"ws connected",
		extra={"event": "ws_connected", "ws_connections": active},
	)
	try:
		await websocket.send_json(
			{
				"type": "connected",
				"timestamp": datetime.now(timezone.utc).isoformat(),
				"message": "incident stream connected",
			}
		)
		while True:
			# Keep connection alive; ignore incoming payloads for this MVP.
			await websocket.receive_text()
	except WebSocketDisconnect:
		incident_ws_manager.disconnect(websocket)
		active = monitoring_service.ws_disconnected()
		logger.info(
			"ws disconnected",
			extra={"event": "ws_disconnected", "ws_connections": active},
		)
	except Exception:
		incident_ws_manager.disconnect(websocket)
		active = monitoring_service.ws_disconnected()
		logger.exception(
			"ws error",
			extra={"event": "ws_error", "ws_connections": active},
		)
