"""Encode a list of annotated frames into a 3-second MP4 evidence clip.

The clip is returned as a base64 data URL (``data:video/mp4;base64,...``)
suitable for storage in the backend Alert row and playback in the dashboard.
A still-image poster/thumbnail JPEG is also extracted from the center frame
for backward-compatible list-view previews.
"""
from __future__ import annotations

import base64
import bisect
import logging
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)

# Type alias matching FrameRingBuffer entries.
_FrameEntry = Tuple[np.ndarray, float]


# ── Encoding helpers ─────────────────────────────────────────────────

def _resize_frame(frame: np.ndarray, max_width: int) -> np.ndarray:
    """Downscale frame if wider than max_width, preserving aspect ratio."""
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    new_w = max_width
    new_h = max(1, int(h * scale))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _encode_jpeg_data_url(frame: np.ndarray, quality: int = 72) -> Optional[str]:
    """Encode a single frame as a JPEG base64 data URL."""
    try:
        ok, buf = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        if not ok:
            return None
        payload = base64.b64encode(buf).decode("ascii")
        return f"data:image/jpeg;base64,{payload}"
    except Exception as exc:
        logger.warning("jpeg encode failed: %s", exc)
        return None


def _sample_centered_clip(
    frames: List[_FrameEntry],
    *,
    event_timestamp: Optional[float],
    target_duration_sec: float,
    fps: int,
) -> tuple[List[_FrameEntry], int, float]:
    """Sample a fixed-duration clip with the event at the midpoint.

    The ring buffer can provide slightly uneven frame timing. Browser evidence
    should still be a predictable 3s artifact, so we sample a fixed timeline
    and duplicate nearest frames when the input is sparse.
    """
    ordered = sorted(frames, key=lambda item: item[1])
    playback_fps = max(1.0, float(fps))
    duration = max(0.1, float(target_duration_sec))
    frame_count = max(1, int(round(duration * playback_fps)))
    event_ts = (
        float(event_timestamp)
        if event_timestamp is not None
        else (ordered[0][1] + ordered[-1][1]) / 2.0
    )

    event_offset_sec = duration / 2.0
    center_idx = min(frame_count - 1, max(0, int(round(event_offset_sec * playback_fps))))
    start_ts = event_ts - event_offset_sec
    timestamps = [ts for _, ts in ordered]

    sampled: List[_FrameEntry] = []
    for i in range(frame_count):
        target_ts = start_ts + (i / playback_fps)
        idx = bisect.bisect_left(timestamps, target_ts)
        if idx <= 0:
            chosen_idx = 0
        elif idx >= len(timestamps):
            chosen_idx = len(timestamps) - 1
        else:
            before = timestamps[idx - 1]
            after = timestamps[idx]
            chosen_idx = idx if abs(after - target_ts) < abs(target_ts - before) else idx - 1
        frame, _ = ordered[chosen_idx]
        sampled.append((frame, target_ts))

    return sampled, center_idx, frame_count / playback_fps


# ── Public API ───────────────────────────────────────────────────────

class ClipEncodeResult:
    """Result of encoding a video evidence clip.

    Attributes:
        video_data_url: base64 MP4 data URL (``data:video/mp4;base64,...``).
        thumbnail_data_url: JPEG data URL of the center (hazard moment) frame.
        frame_width: Encoded frame width in pixels.
        frame_height: Encoded frame height in pixels.
        duration_sec: Actual clip duration in seconds.
        n_frames: Total frames encoded.
    """

    __slots__ = (
        "video_data_url",
        "thumbnail_data_url",
        "frame_width",
        "frame_height",
        "duration_sec",
        "n_frames",
    )

    def __init__(
        self,
        video_data_url: str,
        thumbnail_data_url: Optional[str],
        frame_width: int,
        frame_height: int,
        duration_sec: float,
        n_frames: int,
    ) -> None:
        self.video_data_url = video_data_url
        self.thumbnail_data_url = thumbnail_data_url
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.duration_sec = duration_sec
        self.n_frames = n_frames


def encode_clip(
    frames: List[_FrameEntry],
    fps: int = settings.EVIDENCE_CLIP_VIDEO_FPS,
    max_width: int = settings.EVIDENCE_CLIP_MAX_WIDTH,
    jpeg_quality: int = settings.EVIDENCE_CLIP_JPEG_QUALITY,
    target_duration_sec: float = settings.EVIDENCE_CLIP_DURATION_SEC,
    event_timestamp: Optional[float] = None,
) -> Optional[ClipEncodeResult]:
    """Encode a sequence of annotated frames into a base64 MP4 data URL.

    The center frame (approximate hazard moment) is also extracted as a
    JPEG thumbnail for backward-compatible list-view previews.

    Args:
        frames: Ordered list of ``(frame_bgr, timestamp)`` tuples.
        fps: Playback FPS for the encoded video.
        max_width: Downscale frames wider than this (preserves aspect ratio).
        jpeg_quality: JPEG compression quality for the poster thumbnail.

    Returns:
        ``ClipEncodeResult`` on success; ``None`` if encoding fails or the
        frame list is empty.

    Failure Behavior:
        Never raises. All exceptions are caught and logged; the caller
        receives ``None`` and should fall back to single-frame snapshot.
    """
    if not frames:
        logger.warning("video_clip_encoder: no frames to encode")
        return None

    sampled_frames, center_idx, duration_sec = _sample_centered_clip(
        frames,
        event_timestamp=event_timestamp,
        target_duration_sec=target_duration_sec,
        fps=fps,
    )
    playback_fps = len(sampled_frames) / duration_sec

    # ── Resize first frame to determine output dimensions ──────────
    sample = _resize_frame(sampled_frames[0][0], max_width)
    h, w = sample.shape[:2]
    # H.264/yuv420p playback support expects even dimensions.
    w = max(2, w - (w % 2))
    h = max(2, h - (h % 2))

    # ── Extract center frame as poster thumbnail ───────────────────
    center_frame = _resize_frame(sampled_frames[center_idx][0], max_width)
    thumbnail_data_url = _encode_jpeg_data_url(center_frame, jpeg_quality)

    # ── Write frames to a temporary MP4 file ──────────────────────
    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)  # release fd so VideoWriter can open the file

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_path, fourcc, playback_fps, (w, h))
        if not writer.isOpened():
            logger.warning("video_clip_encoder: VideoWriter failed to open")
            return None

        for frame_bgr, _ in sampled_frames:
            resized = _resize_frame(frame_bgr, max_width)
            # Ensure exact dimensions match writer (guards against odd sizes)
            if resized.shape[1] != w or resized.shape[0] != h:
                resized = cv2.resize(resized, (w, h))
            writer.write(resized)

        writer.release()

        browser_mp4 = _transcode_to_h264(tmp_path)
        read_path = browser_mp4 or tmp_path

        # ── Read encoded bytes and base64-encode ───────────────────
        with open(read_path, "rb") as fh:
            raw = fh.read()

        if not raw:
            logger.warning("video_clip_encoder: encoded file is empty")
            return None

        b64 = base64.b64encode(raw).decode("ascii")
        video_data_url = f"data:video/mp4;base64,{b64}"

        logger.debug(
            "video_clip_encoder: encoded n_frames=%d w=%d h=%d fps=%.1f "
            "size_kb=%.1f duration_sec=%.2f",
            len(sampled_frames),
            w,
            h,
            playback_fps,
            len(raw) / 1024,
            duration_sec,
        )

        return ClipEncodeResult(
            video_data_url=video_data_url,
            thumbnail_data_url=thumbnail_data_url,
            frame_width=w,
            frame_height=h,
            duration_sec=duration_sec,
            n_frames=len(sampled_frames),
        )

    except Exception as exc:
        logger.exception("video_clip_encoder: encoding failed: %s", exc)
        return None

    finally:
        # Always clean up the temp file.
        for path in (tmp_path, f"{tmp_path}.h264.mp4" if tmp_path else None):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


def _transcode_to_h264(input_path: str) -> Optional[str]:
    """Return a browser-playable H.264 MP4 path, or None to keep original."""
    if not shutil.which("ffmpeg"):
        logger.warning("video_clip_encoder: ffmpeg not found; using mp4v fallback")
        return None

    output_path = f"{input_path}.h264.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        input_path,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as exc:
        logger.warning("video_clip_encoder: h264 transcode failed: %s", exc)
        return None

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        logger.warning("video_clip_encoder: h264 transcode produced empty output")
        return None
    return output_path
