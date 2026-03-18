"""
Structured JSON logger — emits one JSON line per processed frame to stdout.
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict


class MetricsLogger:
    """Emits structured JSON metric lines.

    Each call to ``log_frame()`` writes a single newline-delimited JSON object
    to stdout (or a file handle).  Designed for machine parsing downstream.
    """

    def __init__(self, stream=None) -> None:
        self._stream = stream or sys.stdout
        self._start_time = time.monotonic()
        self._frame_count = 0

    def log_frame(
        self,
        cam_id: str,
        frame_no: int,
        input_fps: float,
        inference_fps: float,
        inference_ms: float,
        n_detections: int,
        n_tracked: int,
        dropped_frames: int,
        vram_mb: int,
        **extra: Any,
    ) -> None:
        """Emit one JSON line for a processed frame."""
        self._frame_count += 1
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "cam_id": cam_id,
            "frame_no": frame_no,
            "input_fps": round(input_fps, 1),
            "inference_fps": round(inference_fps, 1),
            "inference_ms": round(inference_ms, 1),
            "n_detections": n_detections,
            "n_tracked": n_tracked,
            "dropped_frames": dropped_frames,
            "vram_mb": vram_mb,
        }
        if extra:
            record.update(extra)
        line = json.dumps(record, ensure_ascii=False)
        self._stream.write(line + "\n")
        self._stream.flush()


def setup_logging(level: str = "INFO") -> None:
    """Configure human-readable logging for library / application messages."""
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
