"""Demo media routes for dashboard live monitoring."""

from __future__ import annotations

import cv2
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter(prefix="/api/media", tags=["media"])

_VIDEOS_DIR = Path(__file__).resolve().parents[4] / "edge_ai" / "vids_test"

# Severity color coding in BGR (OpenCV format)
_COLOR_HIGH = (0, 0, 255)      # Red
_COLOR_MEDIUM = (0, 215, 255)  # Yellow
_COLOR_NORMAL = (0, 200, 0)    # Green


def _draw_label(frame: Any, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
	font = cv2.FONT_HERSHEY_SIMPLEX
	font_scale = 0.55
	thickness = 2
	(text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
	bg_tl = (x, max(0, y - text_h - baseline - 8))
	bg_br = (x + text_w + 10, y)
	cv2.rectangle(frame, bg_tl, bg_br, color, -1)
	cv2.putText(
		frame,
		text,
		(x + 5, y - 6),
		font,
		font_scale,
		(0, 0, 0),
		thickness,
		cv2.LINE_AA,
	)


def _annotate_timestamp(frame: Any) -> None:
	ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	h, _w = frame.shape[:2]
	cv2.putText(
		frame,
		ts,
		(12, h - 16),
		cv2.FONT_HERSHEY_SIMPLEX,
		0.6,
		(255, 255, 255),
		2,
		cv2.LINE_AA,
	)


def _detect_lightweight_events(frame: Any, prev_gray: Any) -> tuple[list[dict[str, Any]], Any]:
	"""Detect motion regions and map them to lightweight AI-like labels.

	This stays CPU-light and does not run heavy models in the stream loop.
	"""
	small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
	gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
	gray = cv2.GaussianBlur(gray, (7, 7), 0)

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
		# Convert coordinates back to full frame
		x *= 2
		y *= 2
		w *= 2
		h *= 2

		aspect_ratio = (w / h) if h else 1.0
		severity = "normal"
		label = "Person Normal"

		# Heuristics for visual demo labels
		if aspect_ratio > 1.3:
			severity = "high"
			label = "Fall Detected"
		elif y < int(frame.shape[0] * 0.35):
			severity = "medium"
			label = "Helmet Missing"

		results.append({"bbox": (x, y, w, h), "label": label, "severity": severity})

	return results, gray


def _annotate_ai_results(frame: Any, detections: list[dict[str, Any]]) -> None:
	for item in detections:
		x, y, w, h = item["bbox"]
		label = item["label"]
		severity = item["severity"]

		if severity == "high":
			color = _COLOR_HIGH
		elif severity == "medium":
			color = _COLOR_MEDIUM
		else:
			color = _COLOR_NORMAL

		cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
		_draw_label(frame, label, x, y, color)


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
	return [_build_video_entry(path, base_url) for path in sorted(_VIDEOS_DIR.glob("*.mp4"))]


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

				# Run lightweight detection every 2nd frame and reuse latest results.
				if frame_idx % 2 == 0:
					cached_detections, prev_gray = _detect_lightweight_events(frame, prev_gray)
				elif prev_gray is None:
					_, prev_gray = _detect_lightweight_events(frame, prev_gray)

				_annotate_ai_results(frame, cached_detections)
				_annotate_timestamp(frame)

				ok, buffer = cv2.imencode(".jpg", frame)
				if not ok:
					continue

				chunk = buffer.tobytes()
				yield (
					b"--frame\r\n"
					b"Content-Type: image/jpeg\r\n\r\n" + chunk + b"\r\n"
				)
		finally:
			capture.release()

	return StreamingResponse(
		frame_generator(),
		media_type="multipart/x-mixed-replace; boundary=frame",
	)