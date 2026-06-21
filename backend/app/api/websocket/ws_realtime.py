"""WebSocket handlers for dashboard realtime refresh events."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ...config.database import get_db
from ...services.event_bus import (
    ANALYTICS_CHANNEL,
    ERGONOMICS_CHANNEL,
    get_event_redis,
    publish_analytics,
    publish_ergonomics,
)
from ...utils.security import get_user_from_token

logger = logging.getLogger("visionsafe.ws.realtime")
router = APIRouter(tags=["websocket"])


class RealtimeWSManager:
    """Redis-backed fanout manager for lightweight dashboard refresh events."""

    def __init__(self, *, channel: str, publish) -> None:
        self.channel = channel
        self._publish = publish
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._subscriber_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
            if self._subscriber_task is None or self._subscriber_task.done():
                self._subscriber_task = asyncio.create_task(self._subscribe())

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections = [client for client in self._connections if client is not ws]

    async def broadcast(self, payload: dict[str, Any]) -> None:
        try:
            self._publish(payload)
        except Exception:
            logger.exception("failed to publish realtime websocket event channel=%s", self.channel)

    async def _broadcast_local(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._connections)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def _subscribe(self) -> None:
        while True:
            pubsub = None
            try:
                redis = get_event_redis()
                pubsub = redis.pubsub()
                pubsub.subscribe(self.channel)
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
                logger.exception("realtime websocket Redis subscriber failed channel=%s", self.channel)
                await asyncio.sleep(2)
            finally:
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except Exception:
                        pass


ergonomics_ws_manager = RealtimeWSManager(
    channel=ERGONOMICS_CHANNEL,
    publish=publish_ergonomics,
)
analytics_ws_manager = RealtimeWSManager(
    channel=ANALYTICS_CHANNEL,
    publish=publish_analytics,
)


async def _dashboard_stream(
    ws: WebSocket,
    *,
    token: str,
    db,
    manager: RealtimeWSManager,
    stream_name: str,
) -> None:
    user = get_user_from_token(token, db)
    if user is None:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(ws)
    try:
        await ws.send_json({
            "type": "connected",
            "stream": stream_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                if data == "ping":
                    await ws.send_json({"type": "pong", "stream": stream_name})
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({
                        "type": "keepalive",
                        "stream": stream_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)


@router.websocket("/ws/ergonomics")
async def ergonomics_websocket(
    ws: WebSocket,
    token: str = Query(default=""),
    db=Depends(get_db),
):
    await _dashboard_stream(
        ws,
        token=token,
        db=db,
        manager=ergonomics_ws_manager,
        stream_name="ergonomics",
    )


@router.websocket("/ws/analytics")
async def analytics_websocket(
    ws: WebSocket,
    token: str = Query(default=""),
    db=Depends(get_db),
):
    await _dashboard_stream(
        ws,
        token=token,
        db=db,
        manager=analytics_ws_manager,
        stream_name="analytics",
    )
