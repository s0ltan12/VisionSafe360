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
_DEFAULT_MAX_FPS = 15
_DEFAULT_JPEG_QUALITY = 92
_DEFAULT_MAX_WIDTH = 0


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
        self._max_width = int(os.getenv("VISIONSAFE_STREAM_MAX_WIDTH", str(_DEFAULT_MAX_WIDTH)))
        self._frame_ttl_seconds = int(os.getenv("VISIONSAFE_STREAM_FRAME_TTL_SECONDS", "10"))
        self._min_interval = 1.0 / max(1, self._max_fps)
        self._last_publish: float = 0.0
        self._redis: Optional[object] = None
        self._available = False
        self._frames_published = 0
        self._rate_limited_skips = 0
        self._publish_failures = 0
        self._last_diag_log = 0.0

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
                "Frame publisher connected to Redis %s:%s key=%s signal=%s max_fps=%d quality=%d max_width=%d",
                host, port, self._latest_key, self._signal_channel, self._max_fps, self._jpeg_quality, self._max_width,
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
            self._rate_limited_skips += 1
            return False

        try:
            # Preserve source resolution by default. Operators can opt into a
            # bandwidth cap with VISIONSAFE_STREAM_MAX_WIDTH when needed.
            h, w = frame.shape[:2]
            if self._max_width > 0 and w > self._max_width:
                scale = self._max_width / w
                frame = cv2.resize(frame, (self._max_width, int(h * scale)), interpolation=cv2.INTER_AREA)

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
            if self._frames_published % 60 == 0 or (now - self._last_diag_log) >= 30:
                self._last_diag_log = now
                logger.info(
                    "frame publish stats camera_id=%s key=%s signal=%s published=%d rate_limited=%d quality=%d max_width=%d",
                    self._camera_id,
                    self._latest_key,
                    self._signal_channel,
                    self._frames_published,
                    self._rate_limited_skips,
                    self._jpeg_quality,
                    self._max_width,
                )
            return True
        except Exception:
            # Don't crash the pipeline for streaming failures.
            self._publish_failures += 1
            if self._frames_published == 0:
                logger.warning("Frame publish failed on first frame — Redis may be down")
            elif self._publish_failures % 60 == 0:
                logger.warning(
                    "frame publish failures camera_id=%s key=%s failures=%d",
                    self._camera_id,
                    self._latest_key,
                    self._publish_failures,
                )
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
