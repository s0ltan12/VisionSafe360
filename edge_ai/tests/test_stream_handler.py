"""
Tests for StreamHandler — Step 1 acceptance criteria.

Run:  cd edge_ai && python -m pytest tests/test_stream_handler.py -v
"""
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.streaming.stream_handler import StreamHandler


def _create_test_video(path: str, n_frames: int = 60, fps: int = 30) -> str:
    """Write a tiny .mp4 with solid-colour frames for testing."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (320, 240))
    for i in range(n_frames):
        frame = np.full((240, 320, 3), fill_value=(i * 4) % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture()
def test_video(tmp_path: Path) -> str:
    """Fixture: creates a 60-frame test .mp4."""
    return _create_test_video(str(tmp_path / "test.mp4"), n_frames=60, fps=30)


# ── Test 1: Normal read ────────────────────────────────────────────

def test_stream_reads_frames(test_video: str) -> None:
    """StreamHandler should produce at least one FrameBundle from a valid video."""
    sh = StreamHandler(source=test_video, camera_id="test_cam")
    sh.start()
    time.sleep(0.5)  # let capture thread run

    bundle = sh.get_frame()
    assert bundle is not None, "Expected at least one frame from test video"
    assert bundle.camera_id == "test_cam"
    assert bundle.frame.shape == (240, 320, 3)
    assert bundle.frame_number >= 0

    sh.stop()
    assert not sh.is_running


# ── Test 2: EOF triggers reconnect ─────────────────────────────────

def test_stream_reconnects_on_eof(test_video: str) -> None:
    """After reaching EOF, StreamHandler should reopen and continue."""
    sh = StreamHandler(source=test_video, camera_id="eof_cam")
    sh.start()

    # Let it run long enough to hit EOF at least once (60 frames @ 30 FPS ≈ 2s)
    time.sleep(4.0)

    assert sh.reconnect_count >= 2, (
        f"Expected ≥ 2 reconnects; got {sh.reconnect_count}"
    )
    assert sh.total_frames_read > 60, (
        f"Expected > 60 frames read (looped); got {sh.total_frames_read}"
    )

    sh.stop()


# ── Test 3: Stopped before start ───────────────────────────────────

def test_stop_before_start() -> None:
    """Calling stop() on an un-started handler should not raise."""
    sh = StreamHandler(source="nonexistent.mp4", camera_id="ghost_cam")
    sh.stop()  # must not throw
    assert not sh.is_running


# ── Test 4: Dropped frames counter ─────────────────────────────────

def test_dropped_frames_counter(test_video: str) -> None:
    """deque(maxlen=1) must drop frames when consumer is slow."""
    sh = StreamHandler(source=test_video, camera_id="drop_cam")
    sh.start()

    # Simulate a slow consumer — don't read for 2 seconds
    time.sleep(2.0)

    assert sh.dropped_count > 0, (
        f"Expected dropped frames > 0; got {sh.dropped_count} "
        "(deque(maxlen=1) policy may not be active)"
    )

    sh.stop()
