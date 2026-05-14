"""Adaptive WebSocket endpoint for real-time AI frame streaming."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from redis import Redis

from ...config.database import get_db
from ...utils.security import get_user_from_token

router = APIRouter(tags=["websocket"])
logger = logging.getLogger("visionsafe.ws.stream")


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _stream_db() -> int:
    if os.getenv("REDIS_STREAMING_DB") is not None:
        return int(os.getenv("REDIS_STREAMING_DB", "3"))
    return int(os.getenv("REDIS_DB", "3"))


@lru_cache(maxsize=1)
def get_stream_redis() -> Redis:
    prefix = "REDIS_STREAMING"
    return Redis(
        host=os.getenv(f"{prefix}_HOST", os.getenv("REDIS_HOST", "localhost")),
        port=int(os.getenv(f"{prefix}_PORT", os.getenv("REDIS_PORT", "6379"))),
        password=os.getenv(f"{prefix}_PASSWORD", os.getenv("REDIS_PASSWORD", "")) or None,
        db=_stream_db(),
        ssl=_to_bool(os.getenv(f"{prefix}_SSL", os.getenv("REDIS_SSL")), default=False),
        socket_timeout=float(os.getenv("REDIS_STREAM_SOCKET_TIMEOUT", "5")),
        socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "5")),
        decode_responses=False,
    )


def _frame_key(camera_id: str) -> str:
    return f"visionsafe:stream:{camera_id}:latest"


def _signal_channel(camera_id: str) -> str:
    return f"visionsafe:stream:{camera_id}:signals"


@dataclass(eq=False)
class StreamClient:
    ws: WebSocket
    max_fps: float
    queue: asyncio.Queue[bytes | None] = field(default_factory=lambda: asyncio.Queue(maxsize=1))
    last_sent: float = 0.0


class CameraStreamHub:
    """One Redis subscriber per camera per backend instance, adaptive local fanout."""

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._clients: set[StreamClient] = set()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._frames_forwarded = 0
        self._last_diag_log = 0.0

    async def add(self, client: StreamClient) -> None:
        async with self._lock:
            self._clients.add(client)
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._redis_loop())
            logger.info(
                "stream client added camera_id=%s subscribers=%d max_fps=%.1f",
                self.camera_id,
                len(self._clients),
                client.max_fps,
            )

    async def remove(self, client: StreamClient) -> None:
        async with self._lock:
            self._clients.discard(client)
            subscribers = len(self._clients)
        await client.queue.put(None)
        logger.info("stream client removed camera_id=%s subscribers=%d", self.camera_id, subscribers)

    async def _fanout(self, frame: bytes) -> None:
        now = time.monotonic()
        async with self._lock:
            clients = list(self._clients)
        for client in clients:
            min_interval = 1.0 / max(1.0, client.max_fps)
            if now - client.last_sent < min_interval:
                continue
            client.last_sent = now
            if client.queue.full():
                try:
                    client.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                client.queue.put_nowait(frame)
            except asyncio.QueueFull:
                pass
        self._frames_forwarded += 1
        if self._frames_forwarded % 60 == 0:
            logger.info(
                "stream fanout stats camera_id=%s forwarded=%d subscribers=%d channel=%s key=%s",
                self.camera_id,
                self._frames_forwarded,
                len(clients),
                _signal_channel(self.camera_id),
                _frame_key(self.camera_id),
            )

    async def _redis_loop(self) -> None:
        channel = _signal_channel(self.camera_id)
        pubsub = None
        try:
            redis = get_stream_redis()
            pubsub = redis.pubsub()
            pubsub.subscribe(channel)
            logger.info(
                "stream hub subscribed camera_id=%s channel=%s key=%s",
                self.camera_id,
                channel,
                _frame_key(self.camera_id),
            )
            latest = await asyncio.get_running_loop().run_in_executor(None, lambda: redis.get(_frame_key(self.camera_id)))
            if latest:
                logger.info("stream hub cache hit camera_id=%s initial_frame=true", self.camera_id)
                await self._fanout(latest)
            while True:
                async with self._lock:
                    if not self._clients:
                        logger.info("stream hub idle camera_id=%s unsubscribing", self.camera_id)
                        return
                message = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                )
                if not message:
                    continue
                frame = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: redis.get(_frame_key(self.camera_id)),
                )
                if frame:
                    self._last_diag_log = time.monotonic()
                    await self._fanout(frame)
        except Exception:
            logger.exception("stream hub failed camera_id=%s", self.camera_id)
            await asyncio.sleep(1)
        finally:
            if pubsub is not None:
                try:
                    pubsub.close()
                except Exception:
                    pass


class StreamHubRegistry:
    def __init__(self) -> None:
        self._hubs: dict[str, CameraStreamHub] = {}
        self._lock = asyncio.Lock()

    async def get(self, camera_id: str) -> CameraStreamHub:
        async with self._lock:
            hub = self._hubs.get(camera_id)
            if hub is None:
                hub = CameraStreamHub(camera_id)
                self._hubs[camera_id] = hub
            return hub


stream_hubs = StreamHubRegistry()


async def _send_loop(client: StreamClient) -> None:
    while True:
        frame = await client.queue.get()
        if frame is None:
            return
        await client.ws.send_bytes(frame)


async def _receive_loop(ws: WebSocket) -> None:
    while True:
        data = await ws.receive_text()
        if data == "ping":
            await ws.send_text("pong")


@router.websocket("/ws/stream/{camera_id}")
async def stream_websocket(
    ws: WebSocket,
    camera_id: str,
    token: str = Query(default=""),
    max_fps: float = Query(default=8.0, ge=1.0, le=30.0),
    db=Depends(get_db),
):
    """Relay latest annotated frames with per-client adaptive frame rate."""

    user = get_user_from_token(token, db)
    if user is None:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    client = StreamClient(ws=ws, max_fps=max_fps)
    hub = await stream_hubs.get(camera_id)
    await hub.add(client)
    logger.info(
        "Stream WS connected camera_id=%s user=%s max_fps=%s channel=%s key=%s",
        camera_id,
        user.id,
        max_fps,
        _signal_channel(camera_id),
        _frame_key(camera_id),
    )

    sender = asyncio.create_task(_send_loop(client))
    receiver = asyncio.create_task(_receive_loop(ws))
    try:
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Stream WS error camera_id=%s", camera_id)
    finally:
        await hub.remove(client)
        logger.info("Stream WS disconnected camera_id=%s", camera_id)
