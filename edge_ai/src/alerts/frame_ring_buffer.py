"""Thread-safe circular frame buffer for alert evidence video clips.

Stores the last N annotated frames so that when a hazard event fires,
we can retrieve a window of frames from before the event and continue
collecting frames afterward to build a centered 3-second clip.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import List, Optional, Tuple

import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)

# Each stored entry: (frame_bgr, timestamp_float)
_FrameEntry = Tuple[np.ndarray, float]


@dataclass
class PendingClip:
    """State for a clip that has had its pre-event frames captured and is
    still collecting post-event frames."""

    pre_frames: List[_FrameEntry]          # frames before event
    event_timestamp: float                 # when the event fired
    post_frames: List[_FrameEntry]         # frames after event (fills in)
    post_target_sec: float                 # how many seconds of post-event to collect
    assembled: bool = False                # True once post collection finished


class FrameRingBuffer:
    """Circular buffer that stores annotated frames for evidence clip assembly.

    Design:
    - ``push()`` is called every frame by FrameProcessor (inference thread).
    - ``start_clip()`` is called when a hazard event fires; it snapshots the
      pre-event frames and returns a ``PendingClip`` that will accumulate
      post-event frames via subsequent ``push()`` calls.
    - ``is_clip_complete()`` returns True once the post-event window is full.
    - Thread-safe: a single Lock protects both the ring deque and all pending
      clips.

    Args:
        buffer_sec: Seconds of frames to retain in the ring (pre-event window).
        fps: Expected inference FPS used to size the ring.
    """

    def __init__(
        self,
        buffer_sec: float = settings.EVIDENCE_CLIP_HALF_SEC,
        fps: int = settings.EVIDENCE_CLIP_VIDEO_FPS,
    ) -> None:
        # Add 20% headroom to handle FPS spikes.
        capacity = max(1, int(buffer_sec * fps * 1.2))
        self._ring: deque[_FrameEntry] = deque(maxlen=capacity)
        self._lock = Lock()
        self._pending_clips: list[PendingClip] = []

    # ── Public API ───────────────────────────────────────────────────

    def push(self, frame: np.ndarray, timestamp: Optional[float] = None) -> None:
        """Push one annotated frame into the ring and deliver it to any
        pending clips that are still waiting for post-event frames.

        Args:
            frame: Annotated BGR frame (will be cloned for isolation).
            timestamp: Frame capture time; defaults to ``time.time()``.
        """
        ts = timestamp if timestamp is not None else time.time()
        # Clone to avoid mutation if the caller reuses the buffer.
        entry: _FrameEntry = (frame.copy(), ts)

        with self._lock:
            self._ring.append(entry)
            # Deliver frame to any pending clips awaiting post-event frames.
            for clip in self._pending_clips:
                if clip.assembled:
                    continue
                post_elapsed = ts - clip.event_timestamp
                if post_elapsed <= clip.post_target_sec:
                    clip.post_frames.append(entry)
                else:
                    clip.assembled = True

    def start_clip(
        self,
        event_timestamp: Optional[float] = None,
        pre_sec: float = settings.EVIDENCE_CLIP_HALF_SEC,
        post_sec: float = settings.EVIDENCE_CLIP_HALF_SEC,
    ) -> PendingClip:
        """Snapshot pre-event frames and create a PendingClip.

        Call this immediately when a hazard event fires. Post-event frames
        will be automatically accumulated by subsequent ``push()`` calls.

        Args:
            event_timestamp: When the event fired; defaults to ``time.time()``.
            pre_sec: How many seconds of past frames to include.
            post_sec: How many seconds of future frames to collect.

        Returns:
            A ``PendingClip`` whose ``assembled`` flag will become True once
            the post-event window is complete.
        """
        ts = event_timestamp if event_timestamp is not None else time.time()

        with self._lock:
            cutoff = ts - pre_sec
            pre_frames: List[_FrameEntry] = [
                (f.copy(), t) for f, t in self._ring if t >= cutoff
            ]
            clip = PendingClip(
                pre_frames=pre_frames,
                event_timestamp=ts,
                post_frames=[],
                post_target_sec=post_sec,
            )
            self._pending_clips.append(clip)

        logger.debug(
            "frame_ring_buffer: clip started pre_frames=%d event_ts=%.3f",
            len(pre_frames),
            ts,
        )
        return clip

    def all_frames(self, clip: PendingClip) -> List[_FrameEntry]:
        """Return all frames in chronological order for a completed clip.

        Args:
            clip: A ``PendingClip`` (``assembled`` should be True).

        Returns:
            Ordered list of ``(frame, timestamp)`` tuples.
        """
        with self._lock:
            return list(clip.pre_frames) + list(clip.post_frames)

    def cleanup_clip(self, clip: PendingClip) -> None:
        """Remove a PendingClip from tracking once encoding is complete."""
        with self._lock:
            try:
                self._pending_clips.remove(clip)
            except ValueError:
                pass

    @property
    def ring_size(self) -> int:
        """Current number of frames in the ring."""
        with self._lock:
            return len(self._ring)

    @property
    def pending_count(self) -> int:
        """Number of clips still collecting post-event frames."""
        with self._lock:
            return sum(1 for c in self._pending_clips if not c.assembled)
