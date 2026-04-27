"""Notification WebSocket manager for real-time dashboard delivery."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ...utils.security import get_user_from_token
from ...config.database import get_db

logger = logging.getLogger("visionsafe.ws.notifications")


class NotificationWSManager:
    """Manages WebSocket connections for real-time notification delivery."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.debug("notification client connected; total=%d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections = [c for c in self._connections if c is not ws]
        logger.debug("notification client disconnected; total=%d", len(self._connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast notification payload to all connected clients."""
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
