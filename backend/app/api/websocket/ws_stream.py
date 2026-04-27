"""WebSocket endpoint for real-time AI frame streaming.

Subscribes to Redis Pub/Sub channel ``visionsafe:stream:{camera_id}``
and relays JPEG frames to connected dashboard clients.

Connect with: ws://<host>/ws/stream/{camera_id}?token=<jwt>
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ...config.database import get_db
from ...utils.security import get_user_from_token

router = APIRouter(tags=["websocket"])
logger = logging.getLogger("visionsafe.ws.stream")


def _get_redis_sync():
    """Create a dedicated Redis connection for Pub/Sub (blocking subscriber)."""
    try:
        import redis

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD") or None
        db = int(os.getenv("REDIS_DB", "0"))

        return redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            socket_timeout=5.0,
            socket_connect_timeout=3.0,
            decode_responses=False,
        )
    except Exception as exc:
        logger.error("Failed to connect to Redis for stream: %s", exc)
        return None


@router.websocket("/ws/stream/{camera_id}")
async def stream_websocket(
    ws: WebSocket,
    camera_id: str,
    token: str = Query(default=""),
    db=Depends(get_db),
):
    """Stream AI-annotated JPEG frames from the edge pipeline to the dashboard.

    The edge_ai pipeline publishes frames to Redis Pub/Sub channel
    ``visionsafe:stream:{camera_id}``. This endpoint subscribes to that
    channel and forwards each JPEG frame as a binary WebSocket message.
    """
    # ── Auth ──────────────────────────────────────────────────────────
    user = get_user_from_token(token, db)
    if user is None:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    logger.info("Stream WS connected camera_id=%s user=%s", camera_id, user.id)

    channel = f"visionsafe:stream:{camera_id}"
    redis_conn: Optional[object] = None
    pubsub = None

    try:
        # ── Subscribe to Redis channel ───────────────────────────────
        redis_conn = _get_redis_sync()
        if redis_conn is None:
            await ws.send_json({"type": "error", "message": "Redis unavailable"})
            await ws.close(code=1011)
            return

        pubsub = redis_conn.pubsub()
        pubsub.subscribe(channel)
        logger.info("Subscribed to Redis channel=%s", channel)

        await ws.send_json({
            "type": "connected",
            "camera_id": camera_id,
            "channel": channel,
        })

        # ── Relay loop ───────────────────────────────────────────────
        while True:
            # Non-blocking get from pubsub with short timeout
            message = await asyncio.get_event_loop().run_in_executor(
                None, lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            )

            if message and message["type"] == "message":
                frame_data = message["data"]
                try:
                    await ws.send_bytes(frame_data)
                except Exception:
                    break

            # Check for incoming client messages (ping/close)
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=0.01)
                if data == "ping":
                    await ws.send_text("pong")
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Stream WS error camera_id=%s", camera_id)
    finally:
        if pubsub is not None:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:
                pass
        if redis_conn is not None:
            try:
                redis_conn.close()
            except Exception:
                pass
        logger.info("Stream WS disconnected camera_id=%s", camera_id)
