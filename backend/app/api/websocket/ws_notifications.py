"""Notification WebSocket manager for real-time dashboard delivery."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ...utils.security import get_user_from_token
from ...config.database import get_db
from ...services.event_bus import NOTIFICATION_CHANNEL, get_event_redis, publish_notification

logger = logging.getLogger("visionsafe.ws.notifications")


class NotificationWSManager:
    """Per-instance notification fanout backed by Redis Pub/Sub."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._subscriber_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
            if self._subscriber_task is None or self._subscriber_task.done():
                self._subscriber_task = asyncio.create_task(self._subscribe())
        logger.debug("notification client connected; total=%d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections = [c for c in self._connections if c is not ws]
        logger.debug("notification client disconnected; total=%d", len(self._connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Persist and publish notification payload to all backend instances."""
        try:
            publish_notification(payload)
        except Exception:
            logger.exception("failed to publish notification websocket event")

    async def _broadcast_local(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, default=str)
        async with self._lock:
            clients = list(self._connections)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                self._connections = [c for c in self._connections if c not in dead]

    async def _subscribe(self) -> None:
        while True:
            pubsub = None
            try:
                redis = get_event_redis()
                pubsub = redis.pubsub()
                pubsub.subscribe(NOTIFICATION_CHANNEL)
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
                logger.exception("notification websocket Redis subscriber failed")
                await asyncio.sleep(2)
            finally:
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except Exception:
                        pass


notification_ws_manager = NotificationWSManager()

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/notifications")
async def notifications_websocket(
    ws: WebSocket,
    token: str = Query(default=""),
    db=Depends(get_db),
):
    """Real-time notification stream for the dashboard.

    Connect with: ws://<host>/ws/notifications?token=<jwt>
    """
    user = get_user_from_token(token, db)
    if user is None:
        await ws.close(code=4001, reason="Unauthorized")
        return
    await notification_ws_manager.connect(ws)
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                if data == "ping":
                    await ws.send_text("pong")
            except asyncio.TimeoutError:
                try:
                    await ws.send_text(json.dumps({"type": "keepalive"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await notification_ws_manager.disconnect(ws)
