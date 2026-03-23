"""
VisionSafe 360 - Edge AI Configuration

All numeric constants and paths. Single source of truth.
Pose-only pipeline: fall detection + ergonomic risk assessment.
"""

import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean environment value with safe defaults."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """Parse float env var and fallback on malformed values."""

    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Parse int env var and fallback on malformed values."""

    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    """Parse comma-separated env var into a clean string list."""

    value = os.getenv(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


# --- Directories
BASE_DIR = Path(__file__).resolve().parents[2]  # edge_ai/
PROFILES_DIR = BASE_DIR / "profiles"
CALIBRATION_DIR = BASE_DIR / "calibration"

# --- Model weights (pose-only)
POSE_WEIGHTS = BASE_DIR / "weights" / "yolo11n-pose.pt"
POSE_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "yolov8n-pose.pt"

# --- Optional proximity/forklift detector (YOLO detect model)
PROXIMITY_WEIGHTS = BASE_DIR / "weights" / "forklift" / "best_forklift.pt"
PROXIMITY_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "forklift" / "yolov8n.pt"

# --- Inference parameters
IMGSZ = 640  # DO NOT increase - each +64px ~ +15% VRAM
PRECISION = "fp16"  # half=True on CUDA: halves VRAM, ~2× faster
CONF_THRESHOLD = 0.32  # slightly lower for better track continuity
IOU_THRESHOLD = 0.45  # standard NMS
MAX_DET = 50  # cap detections per frame
INFERENCE_DEVICE = "cuda:0"  # will fall back to "cpu" if CUDA unavailable

# Optional second model params (forklift/person proximity)
PROXIMITY_CONF_THRESHOLD = 0.35
PROXIMITY_IOU_THRESHOLD = 0.45
PROXIMITY_MAX_DET = 50

# When using generic COCO weights, forklift is often classified as "truck".
PROXIMITY_FORKLIFT_ALIASES = {"forklift", "truck"}

# Forklift-person proximity thresholds (pixels, when uncalibrated)
PROXIMITY_DANGER_PX = 80.0
PROXIMITY_WARNING_PX = 140.0

# --- FPS targets
TARGET_INPUT_FPS = 15  # cap RTSP / file read rate
TARGET_INFER_FPS = 15  # inference loop target

# --- Per-task scheduling (frame counter modulo)
POSE_EVERY_N = 1
FALL_EVERY_N = 1
ERGONOMIC_EVERY_N = 10  # ~1.5 Hz

# --- Stream / reconnect
RTSP_TIMEOUT_SEC = 10
RTSP_MAX_RETRIES = 5
RTSP_RETRY_BACKOFF = [1, 2, 4, 8, 16]  # seconds between retries
STREAM_BUFFER_SIZE = 1  # deque(maxlen=1) - latest-frame policy

# --- Output
OUTPUT_DIR = BASE_DIR / "output"
LOG_LEVEL = "INFO"

# Global debug toggle (env: VISIONSAFE_DEBUG=true/false)
DEBUG_MODE = os.getenv("VISIONSAFE_DEBUG", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Forklift detection smoothing for UI/proximity input only.
PROXIMITY_HOLD_FRAMES = 5

# Track-ID persistence across brief occlusions.
TRACK_ID_GRACE_FRAMES = 8

# --- Offline resilience (infrastructure for future steps)
DEFAULT_OFFLINE_QUEUE_DB = BASE_DIR / "offline_queue.db"

BACKEND_EVENTS_ENABLED = _env_bool("VISIONSAFE_BACKEND_EVENTS_ENABLED", True)

DEFAULT_BACKEND_URL = "http://localhost:8000"
BACKEND_URL = os.getenv("VISIONSAFE_BACKEND_URL", DEFAULT_BACKEND_URL)

BACKEND_INCIDENTS_PATH = os.getenv("VISIONSAFE_BACKEND_INCIDENTS_PATH", "/incidents")
BACKEND_AUTH_TOKEN = os.getenv("VISIONSAFE_BACKEND_AUTH_TOKEN", "")

DEFAULT_BACKEND_TIMEOUT = 5.0
BACKEND_TIMEOUT = _env_float("VISIONSAFE_BACKEND_TIMEOUT", DEFAULT_BACKEND_TIMEOUT)

DEFAULT_BACKEND_MAX_RETRY = 3
BACKEND_MAX_RETRY = _env_int(
    "VISIONSAFE_BACKEND_MAX_RETRY",
    DEFAULT_BACKEND_MAX_RETRY,
)

DEFAULT_BACKEND_RETRY_BACKOFF = [2, 5, 15]
_backend_retry_backoff_strs = _env_list(
    "VISIONSAFE_BACKEND_RETRY_BACKOFF",
    [str(x) for x in DEFAULT_BACKEND_RETRY_BACKOFF],
)
BACKEND_RETRY_BACKOFF = (
    [float(v) for v in _backend_retry_backoff_strs]
    if _backend_retry_backoff_strs
    else [0.5]
)

OFFLINE_QUEUE_DB = Path(
    os.getenv("VISIONSAFE_OFFLINE_QUEUE_DB", str(DEFAULT_OFFLINE_QUEUE_DB))
)
OFFLINE_QUEUE_MAX_ROWS = _env_int("VISIONSAFE_OFFLINE_QUEUE_MAX_ROWS", 5000)
OFFLINE_FLUSH_INTERVAL_SEC = _env_float(
    "VISIONSAFE_OFFLINE_FLUSH_INTERVAL_SEC",
    5.0,
)

# --- Alerting & integration (Step 4)
ALERTS_ENABLED = _env_bool("VISIONSAFE_ALERTS_ENABLED", True)
ALERT_MEDIUM_ENABLE_FCM = _env_bool("VISIONSAFE_ALERT_MEDIUM_ENABLE_FCM", True)
ALERT_ASYNC_DELIVERY_ENABLED = _env_bool(
    "VISIONSAFE_ALERT_ASYNC_DELIVERY_ENABLED",
    True,
)
ALERT_ASYNC_QUEUE_MAXSIZE = _env_int("VISIONSAFE_ALERT_ASYNC_QUEUE_MAXSIZE", 1024)
ALERT_ASYNC_POLL_TIMEOUT_SEC = _env_float("VISIONSAFE_ALERT_ASYNC_POLL_TIMEOUT_SEC", 0.1)

# --- FCM settings
FCM_ENABLED = _env_bool("VISIONSAFE_FCM_ENABLED", True)
FCM_MOCK_MODE = _env_bool("VISIONSAFE_FCM_MOCK_MODE", True)
FCM_CREDENTIALS_PATH = os.getenv("VISIONSAFE_FCM_CREDENTIALS_PATH", "")
FCM_DEVICE_TOKENS = _env_list("VISIONSAFE_FCM_DEVICE_TOKENS", [])

# --- Siren settings
SIREN_ENABLED = _env_bool("VISIONSAFE_SIREN_ENABLED", True)
SIREN_MOCK_MODE = _env_bool("VISIONSAFE_SIREN_MOCK_MODE", True)
SIREN_GPIO_PIN = _env_int("VISIONSAFE_SIREN_GPIO_PIN", 18)
SIREN_COOLDOWN_SEC = _env_float("VISIONSAFE_SIREN_COOLDOWN_SEC", 5.0)
SIREN_MAX_ACTIVE_SEC = _env_float("VISIONSAFE_SIREN_MAX_ACTIVE_SEC", 2.0)

# --- HazardAnalyzer - Fall detection
FALL_ASPECT_RATIO_THRESHOLD = 0.85  # w/h above which person may be lying
FALL_HIP_RATIO_THRESHOLD = 0.2  # hip position below this = falling
FALL_HIP_RECOVERY_THRESHOLD = 0.6  # hip position above this = recovered
FALL_VELOCITY_THRESHOLD = 15.0  # pixels/frame downward velocity
FALL_VELOCITY_WINDOW = 8  # frames to compute velocity over
FALL_CANDIDATE_TIMEOUT = 2.0  # seconds in fall position to confirm
FALL_IMMOBILITY_THRESHOLD = 5.0  # max px movement to count as "immobile"
FALL_AREA_JITTER_THRESHOLD = 0.15  # max relative area change for immobility
FALL_COOLDOWN_SEC = 60.0  # before same track re-fires
FALL_TRACK_PURGE_SEC = 5.0  # purge stale track state

# --- PostureAnalyzer thresholds
POSTURE_KEYPOINT_CONF_MIN = 0.5  # discard keypoints below this
POSTURE_EMA_ALPHA = 0.6  # temporal smoothing weight
POSTURE_SUSTAINED_THRESHOLD = 3.0  # seconds of poor posture before event
POSTURE_COOLDOWN_SEC = 60.0  # per track_id cooldown
TEMPORAL_SMOOTH_WINDOW = 5
ERGONOMIC_SCORE_WINDOW = 90  # frames at 1.5Hz ~ 60s

# --- Event Persistence / Aggregation
FALL_PERSISTENCE_SEC = 0.0  # fall already has candidate->confirm
EVENT_AGGREGATION_WINDOW_SEC = 5.0  # aggregate repeated events within window
EVENT_MAX_UPDATES_PER_WINDOW = 3  # max severity escalations per window

# --- Calibration (camera -> ground-plane)
DEFAULT_PIXELS_PER_METER = 0.0  # 0 = uncalibrated (pixel mode)

