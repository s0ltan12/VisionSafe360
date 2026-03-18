"""
StreamHandler — RTSP / file video reader with deque(maxlen=1) latest-frame policy.

Spawns a daemon thread that continuously decodes frames and drops stale ones.
"""
import logging
import threading
import time
from collections import deque
from typing import Optional

import cv2

from ..config.settings import (
    RTSP_MAX_RETRIES,
    RTSP_RETRY_BACKOFF,
    STREAM_BUFFER_SIZE,
    TARGET_INPUT_FPS,
)
from ..models.frame_bundle import FrameBundle

logger = logging.getLogger(__name__)


class StreamHandler:
    """Captures frames from a video source using a background thread.

    Design contract:
    - ``buffer`` is a ``deque(maxlen=1)`` — always holds only the newest frame.
    - Old frames are *silently discarded* by the deque itself.
    - ``dropped_count`` increments every time a new frame overwrites an unconsumed one.
    """

    def __init__(self, source: str | int, camera_id: str) -> None:
        # Convert numeric string to int for cv2.VideoCapture (webcam index)
        if isinstance(source, str) and source.isdigit():
            self.source: str | int = int(source)
        else:
            self.source: str | int = source
        self.camera_id: str = camera_id

        # Latest-frame buffer — the centrepiece of the architecture
        self.buffer: deque[FrameBundle] = deque(maxlen=STREAM_BUFFER_SIZE)

        # Threading
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Metrics (read from main thread — no lock needed for monotonic counters)
        self.total_frames_read: int = 0
        self.dropped_count: int = 0
        self.reconnect_count: int = 0
        self.input_fps: float = 0.0

    # ── public API ──────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the capture daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("StreamHandler already running — ignoring start()")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop, name=f"capture-{self.camera_id}", daemon=True
        )
        self._thread.start()
        logger.info("Capture thread started for %s", self.camera_id)

    def stop(self) -> None:
        """Signal the capture thread to stop and wait up to 5 s for it to join."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Capture thread stopped for %s", self.camera_id)

    def get_frame(self) -> Optional[FrameBundle]:
        """Non-blocking pop of the latest frame (or ``None`` if empty)."""
        try:
            return self.buffer.pop()
        except IndexError:
            return None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── internal ────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Main capture loop with reconnect-on-EOF behaviour.

        On EOF (simulated camera drop from .mp4): immediately reopen and continue.
        On open failure (bad URL / missing file): retry with exponential backoff,
        up to RTSP_MAX_RETRIES consecutive failures before giving up.
        """
        frame_interval = 1.0 / TARGET_INPUT_FPS
        consecutive_failures = 0

        while not self._stop_event.is_set():
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                consecutive_failures += 1
                if consecutive_failures > RTSP_MAX_RETRIES:
                    logger.error(
                        "Max retries (%d) exhausted for %s — giving up",
                        RTSP_MAX_RETRIES, self.source,
                    )
                    break
                wait = RTSP_RETRY_BACKOFF[
                    min(consecutive_failures - 1, len(RTSP_RETRY_BACKOFF) - 1)
                ]
                logger.warning(
                    "Cannot open source %s — retry %d/%d in %ds",
                    self.source, consecutive_failures, RTSP_MAX_RETRIES, wait,
                )
                if self._stop_event.wait(timeout=wait):
                    break
                continue

            # Successfully opened — reset failure counter
            consecutive_failures = 0
            self.reconnect_count += 1
            logger.info(
                "Stream opened: source=%s  reconnect_count=%d",
                self.source, self.reconnect_count,
            )

            # ── per-session read loop ───────────────────────────────
            t0 = time.monotonic()
            local_count = 0

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    logger.warning(
                        "Stream EOF or read failure — reconnecting  "
                        "cam_id=%s  reconnect_attempt=%d",
                        self.camera_id, self.reconnect_count,
                    )
                    break  # outer loop will re-open

                now = time.monotonic()

                # Throttle to TARGET_INPUT_FPS
                expected_time = t0 + local_count * frame_interval
                sleep_time = expected_time - now
                if sleep_time > 0:
                    time.sleep(sleep_time)

                bundle = FrameBundle(
                    frame=frame,
                    camera_id=self.camera_id,
                    timestamp=time.time(),
                    frame_number=self.total_frames_read,
                )

                # deque(maxlen=1): if buffer was full, the old frame is auto-evicted
                was_full = len(self.buffer) == self.buffer.maxlen
                self.buffer.append(bundle)
                if was_full:
                    self.dropped_count += 1

                self.total_frames_read += 1
                local_count += 1

                # Rolling FPS — recalculate every 30 frames
                if local_count % 30 == 0:
                    elapsed = time.monotonic() - t0
                    self.input_fps = 30.0 / elapsed if elapsed > 0 else 0.0
                    t0 = time.monotonic()
                    local_count = 0

            cap.release()

        logger.info("Capture loop terminated for %s", self.camera_id)
