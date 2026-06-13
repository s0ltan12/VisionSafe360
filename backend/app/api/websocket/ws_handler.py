"""WebSocket handlers for realtime incident updates."""

from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...config.database import SessionLocal
from ...utils.audit_logger import audit_event, ensure_request_id, get_client_ip_from_websocket
from ...services.monitoring_service import monitoring_service
from ...utils.security import get_user_from_token
from ...services.event_bus import INCIDENT_CHANNEL, publish_incident, get_event_redis


router = APIRouter()
logger = logging.getLogger("visionsafe.websocket")


def serialize_incident(incident) -> dict:
	def _iso(value):
		return value.isoformat() if value else None

	return {
		"id": incident.id,
		"zone": incident.zone,
		"classification": incident.classification,
		"severity": incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
		"camera_id": getattr(incident, "camera_id", None),
		"camera_name": getattr(incident, "camera_name", None),
		"worker_id": getattr(incident, "worker_id", None),
		"worker_gpu_id": getattr(incident, "worker_gpu_id", None),
		"status": incident.status.value if hasattr(getattr(incident, "status", None), "value") else str(getattr(incident, "status", "New")),
		"started_at": _iso(getattr(incident, "started_at", None)),
		"validated_at": _iso(getattr(incident, "validated_at", None)),
		"acknowledged_at": _iso(getattr(incident, "acknowledged_at", None)),
		"acknowledged_by": getattr(incident, "acknowledged_by", None),
		"resolved_at": _iso(getattr(incident, "resolved_at", None)),
		"resolved_by": getattr(incident, "resolved_by", None),
		"archived_at": _iso(getattr(incident, "archived_at", None)),
		"duration_seconds": getattr(incident, "duration_seconds", None),
		"escalation_count": getattr(incident, "escalation_count", 0),
		"root_cause": incident.root_cause,
		"corrective_action": incident.corrective_action,
		"created_at": _iso(incident.created_at),
	}


class IncidentWebSocketManager:
	"""Per-instance websocket fanout backed by Redis Pub/Sub."""

	def __init__(self) -> None:
		self._connections: set[WebSocket] = set()
		self._lock = asyncio.Lock()
		self._subscriber_task: asyncio.Task | None = None

	async def connect(self, websocket: WebSocket) -> None:
		await websocket.accept()
		async with self._lock:
			self._connections.add(websocket)
			if self._subscriber_task is None or self._subscriber_task.done():
				self._subscriber_task = asyncio.create_task(self._subscribe())

	async def disconnect(self, websocket: WebSocket) -> None:
		async with self._lock:
			self._connections.discard(websocket)

	async def broadcast(self, payload: dict) -> None:
		try:
			incident = payload.get("incident") if isinstance(payload, dict) else None
			if isinstance(incident, dict):
				logger.debug(
					"broadcast incident payload incident_id=%s camera_id=%s worker_id=%s worker_gpu_id=%s",
					incident.get("id"),
					incident.get("camera_id"),
					incident.get("worker_id"),
					incident.get("worker_gpu_id"),
				)
			publish_incident(payload)
		except Exception:
			logger.exception("failed to publish incident websocket event")

	async def _broadcast_local(self, payload: dict) -> None:
		dead: list[WebSocket] = []
		async with self._lock:
			connections = list(self._connections)
		for websocket in connections:
			try:
				await websocket.send_json(payload)
			except Exception:
				dead.append(websocket)
		for websocket in dead:
			await self.disconnect(websocket)

	async def _subscribe(self) -> None:
		while True:
			pubsub = None
			try:
				redis = get_event_redis()
				pubsub = redis.pubsub()
				pubsub.subscribe(INCIDENT_CHANNEL)
				while True:
					message = await asyncio.get_running_loop().run_in_executor(
						None,
						lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
					)
					if not message:
						async with self._lock:
							if not self._connections:
								return
						continue
					await self._broadcast_local(json.loads(message["data"]))
			except Exception:
				logger.exception("incident websocket Redis subscriber failed")
				await asyncio.sleep(2)
			finally:
				if pubsub is not None:
					try:
						pubsub.close()
					except Exception:
						pass


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
	request_id = ensure_request_id(websocket.headers.get("x-request-id") or str(uuid.uuid4()))
	ip_address = get_client_ip_from_websocket(websocket)
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
	audit_event(
		"websocket_connect",
		user_id=user.id,
		ip_address=ip_address,
		request_id=request_id,
		outcome="success",
		ws_connections=active,
	)
	disconnect_reason = "success"
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
		disconnect_reason = "disconnect"
	except Exception:
		disconnect_reason = "error"
		logger.exception(
			"ws error",
			extra={"event": "ws_error", "ws_connections": active},
		)
	finally:
		await incident_ws_manager.disconnect(websocket)
		active = monitoring_service.ws_disconnected()
		logger.info(
			"ws disconnected",
			extra={"event": "ws_disconnected", "ws_connections": active},
		)
		audit_event(
			"websocket_disconnect",
			user_id=user.id,
			ip_address=ip_address,
			request_id=request_id,
			outcome=disconnect_reason,
			ws_connections=active,
		)
