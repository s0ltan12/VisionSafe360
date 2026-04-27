"""Demo media routes for dashboard live monitoring.

All endpoints now require authentication to prevent anonymous access
to the edge_ai test video library.
"""
from __future__ import annotations

import cv2
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ...utils.security import get_current_user

router = APIRouter(
    prefix="/media",
    tags=["media"],
    dependencies=[Depends(get_current_user)],  # SECURITY: was unauthenticated
)

_VIDEOS_DIR = Path(__file__).resolve().parents[4] / "edge_ai" / "vids_test"

# Severity color coding in BGR (OpenCV format)
_COLOR_HIGH   = (0, 0, 255)    # Red
_COLOR_MEDIUM = (0, 215, 255)  # Yellow
_COLOR_NORMAL = (0, 200, 0)    # Green


def _draw_label(frame: Any, text: str, x: int, y: int, color: tuple) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale, thickness = 0.55, 2
    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    bg_tl = (x, max(0, y - text_h - baseline - 8))
    bg_br = (x + text_w + 10, y)
    cv2.rectangle(frame, bg_tl, bg_br, color, -1)
    cv2.putText(frame, text, (x + 5, y - 6), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)


def _annotate_timestamp(frame: Any) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    h, _w = frame.shape[:2]
    cv2.putText(frame, ts, (12, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)


def _detect_lightweight_events(frame: Any, prev_gray: Any) -> tuple[list[dict[str, Any]], Any]:
    """Motion-based lightweight detection for demo overlay (no heavy models)."""
    small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    if prev_gray is None:
        return [], gray
    delta = cv2.absdiff(prev_gray, gray)
    _, thresh = cv2.threshold(delta, 22, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results: list[dict[str, Any]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 500:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        x, y, w, h = x * 2, y * 2, w * 2, h * 2
        aspect_ratio = (w / h) if h else 1.0
        severity, label = "normal", "Person Normal"
        if aspect_ratio > 1.3:
            severity, label = "high", "Fall Detected"
        elif y < int(frame.shape[0] * 0.35):
            severity, label = "medium", "Helmet Missing"
        results.append({"bbox": (x, y, w, h), "label": label, "severity": severity})
    return results, gray


def _annotate_ai_results(frame: Any, detections: list[dict[str, Any]]) -> None:
    for item in detections:
        x, y, w, h = item["bbox"]
        color = {
            "high": _COLOR_HIGH,
            "medium": _COLOR_MEDIUM,
        }.get(item["severity"], _COLOR_NORMAL)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        _draw_label(frame, item["label"], x, y, color)


def _build_video_entry(path: Path, base_url: str) -> dict[str, str]:
    return {
        "id": path.stem,
        "name": path.stem.replace("_", " ").title(),
        "file_name": path.name,
        "zone": "Test Feed",
        "description": "Demo source served from edge_ai/vids_test for dashboard playback.",
        "stream_url": f"{base_url}/api/media/videos/{path.name}",
        "stream_feed_url": f"{base_url}/api/media/video_feed/{path.name}",
    }


@router.get("/videos")
def list_videos(request: Request) -> list[dict[str, str]]:
    if not _VIDEOS_DIR.exists():
        return []
    base_url = str(request.base_url).rstrip("/")
    return [_build_video_entry(p, base_url) for p in sorted(_VIDEOS_DIR.glob("*.mp4"))]


@router.get("/videos/{video_name}")
def get_video(video_name: str):
    video_path = (_VIDEOS_DIR / video_name).resolve()
    if not video_path.exists() or video_path.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)


@router.get("/video_feed/{video_name}")
def video_feed(video_name: str):
    video_path = (_VIDEOS_DIR / video_name).resolve()
    if not video_path.exists() or video_path.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Video not found")

    def frame_generator():
        capture = cv2.VideoCapture(str(video_path))
        prev_gray = None
        frame_idx = 0
        cached_detections: list[dict[str, Any]] = []
        try:
            while capture.isOpened():
                ok, frame = capture.read()
                if not ok:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    prev_gray = None
                    cached_detections = []
                    time.sleep(0.02)
                    continue
                frame_idx += 1
                if frame_idx % 2 == 0:
                    cached_detections, prev_gray = _detect_lightweight_events(frame, prev_gray)
                elif prev_gray is None:
                    _, prev_gray = _detect_lightweight_events(frame, prev_gray)
                _annotate_ai_results(frame, cached_detections)
                _annotate_timestamp(frame)
                ok, buffer = cv2.imencode(".jpg", frame)
                if not ok:
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        finally:
            capture.release()

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/upload")
async def upload_video(request: Request):
    """Upload a video file for AI processing.

    Accepts multipart form data with a 'file' field containing a video.
    Saves to edge_ai/vids_test/ and returns the video metadata.
    """
    import shutil
    from fastapi import UploadFile, File

    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "filename"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No file uploaded")

    filename = file.filename
    if not filename:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Empty filename")

    # Sanitize filename
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
    if not safe_name.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Only video files (.mp4, .avi, .mov, .mkv) are allowed")

    _VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _VIDEOS_DIR / safe_name

    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    base_url = str(request.base_url).rstrip("/")
    return _build_video_entry(dest, base_url)