"""Minimal edge_ai live monitoring worker example.

This example intentionally stays simple:
- reads a local MP4 file with OpenCV
- overlays a status bar for preview
- emits demo incidents to the backend when motion spikes or on a timer

It is not a replacement for the full edge_ai pipeline. It is a clean MVP
reference for integrating video processing with the dashboard/backend stack.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2

from src.integration.backend_client import BackendClient
from src.models.hazard_event import HazardEvent
from src.models.severity import Severity
from src.utils.logger import setup_logging


logger = logging.getLogger("edge_ai.live_monitoring_worker")


def build_incident(camera_id: str, frame_number: int, reason: str, severity: Severity) -> HazardEvent:
	return HazardEvent(
		event_type="live_monitoring_demo",
		severity=severity,
		camera_id=camera_id,
		timestamp=time.time(),
		frame_number=frame_number,
		description=f"Demo incident: {reason}",
		metadata={"source": "edge_ai.examples.live_monitoring_worker", "reason": reason},
	)


def main() -> int:
	setup_logging()
	parser = argparse.ArgumentParser(description="Run a minimal live monitoring worker")
	parser.add_argument("--source", required=True, help="Path to an input MP4 file")
	parser.add_argument("--camera-id", default="cam_01", help="Camera identifier")
	parser.add_argument("--preview", action="store_true", help="Show a local preview window")
	parser.add_argument("--output", help="Optional annotated output MP4 path")
	args = parser.parse_args()

	source_path = Path(args.source).expanduser().resolve()
	if not source_path.exists():
		raise FileNotFoundError(source_path)

	logger.info("worker starting source=%s camera_id=%s", source_path, args.camera_id)

	capture = cv2.VideoCapture(str(source_path))
	if not capture.isOpened():
		raise RuntimeError(f"Failed to open {source_path}")

	width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
	height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
	fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
	writer = None
	if args.output:
		fourcc = cv2.VideoWriter_fourcc(*"mp4v")
		writer = cv2.VideoWriter(args.output, fourcc, fps, (width, height))

	backend = BackendClient()
	previous_gray = None
	frame_number = 0
	last_emit = 0.0

	while True:
		ok, frame = capture.read()
		if not ok:
			break

		frame_number += 1
		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		gray = cv2.GaussianBlur(gray, (21, 21), 0)

		motion_score = 0.0
		if previous_gray is not None:
			delta = cv2.absdiff(previous_gray, gray)
			motion_score = float(delta.mean())

		previous_gray = gray

		if motion_score > 7.5 or (time.time() - last_emit) > 8.0:
			severity = Severity.HIGH if motion_score > 12.0 else Severity.MEDIUM
			result = backend.submit_incident_fast(
				build_incident(
					camera_id=args.camera_id,
					frame_number=frame_number,
					reason=f"motion_score={motion_score:.1f}",
					severity=severity,
				),
			)
			logger.info(
				"incident emission result=%s frame=%s score=%.1f",
				result.value,
				frame_number,
				motion_score,
			)
			last_emit = time.time()

		cv2.putText(
			frame,
			f"{args.camera_id}  frame={frame_number}  motion={motion_score:.1f}",
			(24, 42),
			cv2.FONT_HERSHEY_SIMPLEX,
			1.0,
			(0, 165, 255),
			2,
			cv2.LINE_AA,
		)

		if writer is not None:
			writer.write(frame)

		if args.preview:
			cv2.imshow("VisionSafe360 Live Monitoring Worker", frame)
			if cv2.waitKey(1) & 0xFF == 27:
				break

	capture.release()
	if writer is not None:
		writer.release()
	if args.preview:
		cv2.destroyAllWindows()
	logger.info("worker stopped source=%s camera_id=%s", source_path, args.camera_id)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())