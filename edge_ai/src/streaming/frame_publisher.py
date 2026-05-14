"""Redis-based frame publisher for headless dashboard streaming.

Publishes JPEG-encoded annotated frames to Redis so that the backend can relay
the latest annotated frame to connected dashboard clients via WebSocket.

Usage inside the pipeline::

    publisher = FramePublisher(camera_id="cam_01")
    publisher.publish(annotated_frame)  # numpy BGR frame
    publisher.close()

Latest-frame key: ``visionsafe:stream:{camera_id}:latest``
Signal channel: ``visionsafe:stream:{camera_id}:signals``
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import cv2

logger = logging.getLogger("visionsafe.streaming.frame_publisher")

# Publish at most this many frames per second to avoid flooding Redis.
_DEFAULT_MAX_FPS = 12
_DEFAULT_JPEG_QUALITY = 70


class FramePublisher:
    """Publish annotated video frames to Redis Pub/Sub for dashboard streaming."""

    def __init__(
        self,
        camera_id: str = "cam_01",
        max_fps: int | None = None,
        jpeg_quality: int | None = None,
    ) -> None:
        self._camera_id = camera_id
        self._latest_key = f"visionsafe:stream:{camera_id}:latest"
        self._signal_channel = f"visionsafe:stream:{camera_id}:signals"
        self._max_fps = max_fps or int(os.getenv("VISIONSAFE_STREAM_MAX_FPS", str(_DEFAULT_MAX_FPS)))
        self._jpeg_quality = jpeg_quality or int(os.getenv("VISIONSAFE_STREAM_JPEG_QUALITY", str(_DEFAULT_JPEG_QUALITY)))
        self._frame_ttl_seconds = int(os.getenv("VISIONSAFE_STREAM_FRAME_TTL_SECONDS", "10"))
        self._min_interval = 1.0 / max(1, self._max_fps)
        self._last_publish: float = 0.0
        self._redis: Optional[object] = None
        self._available = False
        self._frames_published = 0

        self._connect()

    def _connect(self) -> None:
        """Best-effort Redis connection — never raises."""
        try:
            import redis

            host = os.getenv("REDIS_STREAMING_HOST", os.getenv("REDIS_HOST", "localhost"))
            port = int(os.getenv("REDIS_STREAMING_PORT", os.getenv("REDIS_PORT", "6379")))
            password = os.getenv("REDIS_STREAMING_PASSWORD", os.getenv("REDIS_PASSWORD") or "") or None
            db = int(os.getenv("REDIS_STREAMING_DB", os.getenv("REDIS_DB", "3")))

            self._redis = redis.Redis(
                host=host,
                port=port,
                password=password,
                db=db,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                decode_responses=False,
            )
            self._redis.ping()
            self._available = True
            logger.info(
                "Frame publisher connected to Redis %s:%s key=%s signal=%s max_fps=%d quality=%d",
                host, port, self._latest_key, self._signal_channel, self._max_fps, self._jpeg_quality,
            )
        except Exception as exc:
            self._available = False
            logger.warning("Frame publisher: Redis unavailable (%s) — frames will not be streamed", exc)

    @property
    def is_available(self) -> bool:
        return self._available

    def publish(self, frame) -> bool:
        """Encode and publish a BGR numpy frame to Redis.

        Returns True if published, False if skipped (rate limit or unavailable).
        """
        if not self._available or self._redis is None:
            return False

        # Rate limiting
        now = time.monotonic()
        if (now - self._last_publish) < self._min_interval:
            return False

        try:
            # Resize for bandwidth: max 960px wide
            h, w = frame.shape[:2]
            if w > 960:
                scale = 960 / w
                frame = cv2.resize(frame, (960, int(h * scale)))

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
            if not ok:
                return False

            payload = buf.tobytes()
            pipe = self._redis.pipeline()
            pipe.setex(self._latest_key, self._frame_ttl_seconds, payload)
            pipe.publish(self._signal_channel, str(time.time()).encode("ascii"))
            pipe.execute()
            self._last_publish = now
            self._frames_published += 1
            return True
        except Exception:
            # Don't crash the pipeline for streaming failures.
            if self._frames_published == 0:
                logger.warning("Frame publish failed on first frame — Redis may be down")
            return False

    def close(self) -> None:
        """Clean shutdown."""
        logger.info(
            "Frame publisher closing — published %d frames on key=%s signal=%s",
            self._frames_published, self._latest_key, self._signal_channel,
        )
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None
            self._available = False
