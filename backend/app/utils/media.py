"""Shared helpers for video file upload + storage.

Used by both `routes/media.py` (legacy upload) and `routes/cameras.py`
(combined upload-and-create-camera).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, UploadFile


VIDEOS_DIR = Path(__file__).resolve().parents[2] / "edge_ai" / "vids_test"
MAX_UPLOAD_BYTES = int(os.getenv("MEDIA_UPLOAD_MAX_BYTES", str(1024 * 1024 * 1024)))
_CHUNK_SIZE = 1024 * 1024


def sanitize_video_filename(filename: str) -> str:
    safe_name = "".join(c for c in Path(filename).name if c.isalnum() or c in "._- ").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Empty filename")
    if not safe_name.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Only video files (.mp4, .avi, .mov, .mkv) are allowed")
    return safe_name


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
