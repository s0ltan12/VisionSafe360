"""Demo media routes for dashboard live monitoring.

All endpoints now require authentication to prevent anonymous access
to the edge_ai test video library.
"""
from __future__ import annotations

import cv2
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ...utils.permissions import require_roles

router = APIRouter(
    prefix="/media",
    tags=["media"],
    dependencies=[Depends(require_roles("admin", "operator", "viewer"))],  # SECURITY: was unauthenticated
)

_VIDEOS_DIR = Path(__file__).resolve().parents[3] / "edge_ai" / "vids_test"
_MAX_UPLOAD_BYTES = int(os.getenv("MEDIA_UPLOAD_MAX_BYTES", str(1024 * 1024 * 1024)))
_CHUNK_SIZE = 1024 * 1024

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


def _sanitize_video_filename(filename: str) -> str:
    safe_name = "".join(c for c in Path(filename).name if c.isalnum() or c in "._- ").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Empty filename")
    if not safe_name.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Only video files (.mp4, .avi, .mov, .mkv) are allowed")
    return safe_name


def _build_video_entry(path: Path) -> dict[str, str]:
    # Known demo files that come with the repo
    known_demos = {"v1.mp4", "v2.mp4", "v3.mp4", "v4.mp4"}
    video_type = "demo" if path.name.lower() in known_demos else "upload"

    return {
        "id": path.stem,
        "name": path.stem.replace("_", " ").title(),
        "file_name": path.name,
        "type": video_type,
        "zone": "Test Feed",
        "description": f"Video source ({path.name}) ready for AI analysis and playback.",
        "stream_url": f"/api/media/videos/{path.name}",
        "stream_feed_url": f"/api/media/video_feed/{path.name}",
    }


def _guess_media_type(path: Path) -> str:
    import mimetypes

    mime_type, _ = mimetypes.guess_type(path)
    return mime_type or "application/octet-stream"


def _iter_file_range(path: Path, start: int, end: int):
    with open(path, "rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None
    value = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
    if "-" not in value:
        return None
    start_text, end_text = value.split("-", 1)
    if start_text == "":
        suffix_length = int(end_text) if end_text.isdigit() else 0
        if suffix_length <= 0:
            return None
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        if not start_text.isdigit():
            return None
        start = int(start_text)
        end = int(end_text) if end_text.isdigit() else file_size - 1
    if start >= file_size or end < start:
        raise HTTPException(status_code=416, detail="Requested range not satisfiable")
    return start, min(end, file_size - 1)

@router.get("/videos")
def list_videos(request: Request) -> list[dict[str, str]]:
    if not _VIDEOS_DIR.exists():
        return []
    files = []
    for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv"):
        files.extend(_VIDEOS_DIR.glob(ext))
    return [_build_video_entry(p) for p in sorted(files)]


@router.get("/videos/{video_name}")
def get_video(video_name: str, request: Request):
    video_path = (_VIDEOS_DIR / video_name).resolve()
    if not video_path.exists() or video_path.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Video not found")
    media_type = _guess_media_type(video_path)
    file_size = video_path.stat().st_size
    range_value = _parse_range_header(request.headers.get("range"), file_size)
    common_headers = {"Accept-Ranges": "bytes"}
    if range_value is None:
        return FileResponse(
            video_path,
            media_type=media_type,
            filename=video_path.name,
            headers={**common_headers, "Content-Length": str(file_size)},
        )

    start, end = range_value
    content_length = end - start + 1
    return StreamingResponse(
        _iter_file_range(video_path, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            **common_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
        },
    )


@router.delete("/videos/{video_name}", status_code=204)
def delete_video(video_name: str):
    video_path = (_VIDEOS_DIR / video_name).resolve()
    if not video_path.exists() or video_path.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Video not found")
    if not video_path.is_file():
        raise HTTPException(status_code=400, detail="Source is not a removable video file")
    video_path.unlink()
    return Response(status_code=204)


@router.patch("/videos/{video_name}")
def rename_video(video_name: str, payload: dict[str, str] = Body(...)) -> dict[str, str]:
    video_path = (_VIDEOS_DIR / video_name).resolve()
    if not video_path.exists() or video_path.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Video not found")
    if not video_path.is_file():
        raise HTTPException(status_code=400, detail="Source is not a removable video file")

    requested_name = payload.get("file_name") or payload.get("name") or ""
    safe_name = _sanitize_video_filename(requested_name)
    dest = (_VIDEOS_DIR / safe_name).resolve()
    if dest.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid destination filename")
    if dest.exists() and dest != video_path:
        raise HTTPException(status_code=409, detail="A source with that filename already exists")
    if dest != video_path:
        video_path.rename(dest)
    return _build_video_entry(dest)


@router.get("/video_feed/{video_name}")
def video_feed(video_name: str):
    video_path = (_VIDEOS_DIR / video_name).resolve()
    if not video_path.exists() or video_path.parent != _VIDEOS_DIR.resolve():
        raise HTTPException(status_code=404, detail="Video not found")

    def frame_generator():
        capture = cv2.VideoCapture(str(video_path))
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_delay = 1.0 / fps if fps > 0 else 1.0 / 30.0

        prev_gray = None
        frame_idx = 0
        cached_detections: list[dict[str, Any]] = []
        try:
            while capture.isOpened():
                start_time = time.time()
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

                elapsed = time.time() - start_time
                sleep_time = frame_delay - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            capture.release()

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file for AI processing.

    Accepts multipart form data with a 'file' field containing a video.
    Saves to edge_ai/vids_test/ and returns the video metadata.
    """
    safe_name = _sanitize_video_filename(file.filename or "")

    _VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _VIDEOS_DIR / safe_name
    tmp_dest = dest.with_suffix(dest.suffix + ".part")

    total = 0
    try:
        with open(tmp_dest, "wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video file is too large")
                output.write(chunk)
        tmp_dest.replace(dest)
    except Exception:
        if tmp_dest.exists():
            tmp_dest.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return _build_video_entry(dest)
