"""
VisionSafe 360 — Edge AI Pipeline Orchestrator (Pose-Only)

Single-camera, pose-based analysis pipeline:
  python src/main.py --source path/to/test.mp4 --cam-id cam_01 --show
  python src/main.py --source path/to/test.mp4 --cam-id cam_01 --profile full_suite

Capabilities: fall detection + ergonomic risk assessment (RULA/REBA).
Single pose model provides person detection, tracking, and keypoints.

Design invariants:
  • deque(maxlen=1) latest-frame policy — old frames dropped, not queued.
  • ONE thread owns the GPU (this main thread after StreamHandler starts).
  • Pose model + ByteTrack in a single serial loop.
  • HazardAnalyzer + PostureAnalyzer are CPU-only (no GPU calls inside).
  • Profile-driven module enable/disable — no code changes needed.
"""
import os as _os
import sys
from pathlib import Path

# ── Force Qt/OpenCV to use X11 (XCB) on Wayland ────────────────────
# Without this, cv2.imshow renders a black window on Wayland compositors.
if _os.environ.get("XDG_SESSION_TYPE") == "wayland":
    _os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# Suppress Ultralytics auto-update and verbose stdout pollution
_os.environ.setdefault("YOLO_VERBOSE", "false")

# ── Ensure edge_ai/src is on sys.path when run as script ───────────
_SCRIPT_DIR = Path(__file__).resolve().parent          # edge_ai/src
_EDGE_AI_DIR = _SCRIPT_DIR.parent                       # edge_ai/
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
