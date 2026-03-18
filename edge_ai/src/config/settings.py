"""
VisionSafe 360 — Edge AI Configuration
All numeric constants and paths. Single source of truth.

Pose-only pipeline: fall detection + ergonomic risk assessment.
"""
import os
from pathlib import Path

# ─── Directory roots ────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[2]  # edge_ai/
PROFILES_DIR = BASE_DIR / "profiles"

# ─── Model weights (pose-only) ─────────────────────────────────────
POSE_WEIGHTS = BASE_DIR / "weights" / "yolo11n-pose.pt"
POSE_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "yolov8n-pose.pt"

# Optional proximity/forklift detector (YOLO detect model)
PROXIMITY_WEIGHTS = BASE_DIR / "forklift" / "best_forklift.pt"
PROXIMITY_FALLBACK_WEIGHTS = BASE_DIR / "forklift" / "yolov8n.pt"

# ─── Inference parameters ───────────────────────────────────────────
IMGSZ = 640                     # DO NOT increase — each +64px ≈ +15% VRAM
PRECISION = "fp16"              # half=True on CUDA: halves VRAM, ~2× faster
CONF_THRESHOLD = 0.32           # slightly lower for better track continuity
IOU_THRESHOLD = 0.45            # standard NMS
MAX_DET = 50                    # cap detections per frame
INFERENCE_DEVICE = "cuda:0"     # will fall back to "cpu" if CUDA unavailable

# Optional second model params (forklift/person proximity)
PROXIMITY_CONF_THRESHOLD = 0.35
PROXIMITY_IOU_THRESHOLD = 0.45
PROXIMITY_MAX_DET = 50

# When using generic COCO weights, forklift is often classified as "truck".
PROXIMITY_FORKLIFT_ALIASES = {"forklift", "truck"}

# Forklift-person proximity thresholds (pixels, when uncalibrated)
PROXIMITY_DANGER_PX = 80.0
PROXIMITY_WARNING_PX = 140.0

# ─── FPS targets ────────────────────────────────────────────────────
TARGET_INPUT_FPS = 15           # cap RTSP / file read rate
TARGET_INFER_FPS = 15           # inference loop target

# ─── Per-task scheduling (frame counter modulo) ─────────────────────
POSE_EVERY_N = 1                # every frame (pose is the primary model now)
FALL_EVERY_N = 1                # every frame
ERGONOMIC_EVERY_N = 10          # ~1.5 Hz

# ─── Stream / reconnect ────────────────────────────────────────────
RTSP_TIMEOUT_SEC = 10
RTSP_MAX_RETRIES = 5
RTSP_RETRY_BACKOFF = [1, 2, 4, 8, 16]  # seconds between retries
STREAM_BUFFER_SIZE = 1          # deque(maxlen=1) — latest-frame policy

# ─── Output ─────────────────────────────────────────────────────────
OUTPUT_DIR = BASE_DIR / "output"
LOG_LEVEL = "INFO"

# Global debug toggle (env: VISIONSAFE_DEBUG=true/false)
DEBUG_MODE = os.getenv("VISIONSAFE_DEBUG", "false").strip().lower() in {
	"1", "true", "yes", "on",
}

# Forklift detection smoothing for UI/proximity input only.
# Raw model outputs remain unchanged.
PROXIMITY_HOLD_FRAMES = 5

# Track-ID persistence across brief occlusions.
TRACK_ID_GRACE_FRAMES = 8

# ─── Offline resilience (infrastructure for future steps) ───────────
OFFLINE_QUEUE_DB = BASE_DIR / "offline_queue.db"
BACKEND_URL = "http://localhost:8000"
BACKEND_TIMEOUT = 5.0           # seconds per request
BACKEND_MAX_RETRY = 3
BACKEND_RETRY_BACKOFF = [2, 5, 15]  # seconds

# ─── HazardAnalyzer — Fall detection ───────────────────────────────
FALL_ASPECT_RATIO_THRESHOLD = 0.85       # w/h above which person may be lying
FALL_HIP_RATIO_THRESHOLD = 0.2           # hip position below this = falling
FALL_HIP_RECOVERY_THRESHOLD = 0.6        # hip position above this = recovered
FALL_VELOCITY_THRESHOLD = 15.0           # pixels/frame downward velocity
FALL_VELOCITY_WINDOW = 8                 # frames to compute velocity over
FALL_CANDIDATE_TIMEOUT = 2.0             # seconds in fall position to confirm
FALL_IMMOBILITY_THRESHOLD = 5.0          # max px movement to count as "immobile"
FALL_AREA_JITTER_THRESHOLD = 0.15        # max relative area change for immobility
FALL_COOLDOWN_SEC = 60.0                 # before same track re-fires
FALL_TRACK_PURGE_SEC = 5.0              # purge stale track state

# ─── PostureAnalyzer thresholds ─────────────────────────────────────
POSTURE_KEYPOINT_CONF_MIN = 0.5          # discard keypoints below this
POSTURE_EMA_ALPHA = 0.6                  # temporal smoothing weight
POSTURE_SUSTAINED_THRESHOLD = 3.0        # seconds of poor posture before event
POSTURE_COOLDOWN_SEC = 60.0              # per track_id cooldown
TEMPORAL_SMOOTH_WINDOW = 5
ERGONOMIC_SCORE_WINDOW = 90              # frames at 1.5Hz ≈ 60s

# ─── Event Persistence / Aggregation ───────────────────────────────
FALL_PERSISTENCE_SEC = 0.0              # fall already has candidate→confirm
EVENT_AGGREGATION_WINDOW_SEC = 5.0      # aggregate repeated events within window
EVENT_MAX_UPDATES_PER_WINDOW = 3        # max severity escalations per window

# ─── Calibration (camera → ground-plane) ───────────────────────────
CALIBRATION_DIR = BASE_DIR / "calibration"
DEFAULT_PIXELS_PER_METER = 0.0          # 0 = uncalibrated (pixel mode)
