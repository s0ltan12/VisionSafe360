"""Shared helpers for video file upload + storage.

Used by both `routes/media.py` (legacy upload) and `routes/cameras.py`
(combined upload-and-create-camera).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile


VIDEOS_DIR = Path(__file__).resolve().parents[2] / "edge_ai" / "vids_test"
THUMBNAILS_DIR = VIDEOS_DIR / "thumbnails"
MAX_UPLOAD_BYTES = int(os.getenv("MEDIA_UPLOAD_MAX_BYTES", str(1024 * 1024 * 1024)))
_CHUNK_SIZE = 1024 * 1024
_THUMBNAIL_JPEG_QUALITY = int(os.getenv("MEDIA_THUMBNAIL_JPEG_QUALITY", "85"))
_THUMBNAIL_MAX_WIDTH = int(os.getenv("MEDIA_THUMBNAIL_MAX_WIDTH", "960"))
_logger = logging.getLogger("visionsafe.media")


def sanitize_video_filename(filename: str) -> str:
    safe_name = "".join(c for c in Path(filename).name if c.isalnum() or c in "._- ").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Empty filename")
    if not safe_name.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Only video files (.mp4, .avi, .mov, .mkv) are allowed")
    return safe_name


def thumbnail_path_for(video_filename: str) -> Path:
    """Where the thumbnail JPEG lives for a given video filename."""
    return THUMBNAILS_DIR / f"{Path(video_filename).stem}.jpg"


def generate_thumbnail(video_filename: str, force: bool = False) -> Optional[Path]:
    """Extract the first decodable frame of ``video_filename`` and cache it.

    Returns the thumbnail path on success, or ``None`` if the file can't be
    opened or no frame is available. ``force=True`` overwrites an existing
    cached thumbnail.
    """
    video_path = (VIDEOS_DIR / video_filename).resolve()
    if not video_path.exists() or video_path.parent != VIDEOS_DIR.resolve():
        return None

    out_path = thumbnail_path_for(video_filename)
    if out_path.exists() and not force:
        return out_path

    try:
        import cv2  # imported lazily so the util stays import-cheap

        capture = cv2.VideoCapture(str(video_path))
        try:
            # Skip past potential black lead-in / decode metadata frames.
            ok, frame = False, None
            for _ in range(5):
                ok, frame = capture.read()
                if ok and frame is not None:
                    break
            if not ok or frame is None:
                return None

            height, width = frame.shape[:2]
            if width > _THUMBNAIL_MAX_WIDTH:
                scale = _THUMBNAIL_MAX_WIDTH / float(width)
                new_size = (_THUMBNAIL_MAX_WIDTH, max(1, int(round(height * scale))))
                frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

            THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _THUMBNAIL_JPEG_QUALITY])
            if not ok:
                return None
            out_path.write_bytes(buf.tobytes())
            return out_path
        finally:
            capture.release()
    except Exception:
        _logger.exception("failed to generate thumbnail for %s", video_filename)
        return None


async def stream_upload_to_videos_dir(file: UploadFile) -> str:
    """Save an UploadFile to VIDEOS_DIR using a .part temp + atomic rename.

    Returns the final sanitized filename (without path). Raises HTTPException
    on oversize or filename problems. Caller is responsible for `await file.close()`.
    """
    safe_name = sanitize_video_filename(file.filename or "")
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = VIDEOS_DIR / safe_name
    tmp_dest = dest.with_suffix(dest.suffix + ".part")

    total = 0
    try:
        with open(tmp_dest, "wb") as output:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video file is too large")
                output.write(chunk)
        tmp_dest.replace(dest)
    except Exception:
        if tmp_dest.exists():
            tmp_dest.unlink(missing_ok=True)
        raise
    return safe_name
