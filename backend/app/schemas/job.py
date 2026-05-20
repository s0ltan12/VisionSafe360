"""Edge AI job control schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class JobStartRequest(BaseModel):
    source_name: Optional[str] = None  # filename, rtsp://, or None → resolve from camera.stream_url
    camera_id: str = "cam_01"


class JobStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    source_name: Optional[str] = None
    camera_id: Optional[str] = None
    started_at: Optional[float] = None
    last_error: Optional[str] = None
    last_exit_code: Optional[int] = None
