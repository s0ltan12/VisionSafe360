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
# Accuracy-first default: use the larger YOLO11s pose checkpoint when available.
POSE_WEIGHTS = BASE_DIR / "weights" / "yolo11s-pose.pt"
POSE_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "yolo11n-pose.pt"

# --- Optional proximity/forklift detector (YOLO detect model)
PROXIMITY_WEIGHTS = BASE_DIR / "weights" / "forklift" / "best_forklift.pt"
PROXIMITY_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "forklift" / "yolov8n.pt"

# --- Optional PPE detector (SH17 trained model)
PPE_WEIGHTS = BASE_DIR / "weights" / "ppe" / "best_ppe.pt"
PPE_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "ppe" / "yolov8n.pt"

# --- Inference parameters
IMGSZ = 640  # DO NOT increase - each +64px ~ +15% VRAM
PRECISION = "fp32"  # accuracy-first default; switch to fp16 for throughput
CONF_THRESHOLD = 0.38  # stricter default to reduce false positives
IOU_THRESHOLD = 0.50  # slightly stricter NMS for cleaner boxes
MAX_DET = 50  # cap detections per frame
INFERENCE_DEVICE = "cuda:0"  # will fall back to "cpu" if CUDA unavailable

# Optional second model params (forklift/person proximity)
PROXIMITY_CONF_THRESHOLD = 0.40
PROXIMITY_IOU_THRESHOLD = 0.50
PROXIMITY_MAX_DET = 50

# Optional third model params (PPE)
PPE_CONF_THRESHOLD = 0.30
PPE_IOU_THRESHOLD = 0.50
PPE_MAX_DET = 100
PPE_MISSING_PERSISTENCE_SEC = _env_float("VISIONSAFE_PPE_MISSING_PERSISTENCE_SEC", 3.0)
PROXIMITY_PERSISTENCE_SEC = _env_float("VISIONSAFE_PROXIMITY_PERSISTENCE_SEC", 1.0)

# When using generic COCO weights, forklift is often classified as "truck".
PROXIMITY_FORKLIFT_ALIASES = {"forklift", "truck"}


class EventTypes:
    FORKLIFT_OVERSPEED = "forklift_overspeed"


# Forklift-person proximity thresholds (pixels, when uncalibrated)
PROXIMITY_DANGER_PX = 80.0
PROXIMITY_WARNING_PX = 140.0

# Driver/operator suppression.  These are deliberately geometric so the
# system does not require a dedicated driver model or new training data.
DRIVER_SUPPRESSION_STRONG_OVERLAP_RATIO = _env_float(
    "VISIONSAFE_DRIVER_SUPPRESSION_STRONG_OVERLAP_RATIO",
    0.45,
)
DRIVER_SUPPRESSION_CABIN_OVERLAP_RATIO = _env_float(
    "VISIONSAFE_DRIVER_SUPPRESSION_CABIN_OVERLAP_RATIO",
    0.25,
)
DRIVER_SUPPRESSION_CANDIDATE_SEC = _env_float(
    "VISIONSAFE_DRIVER_SUPPRESSION_CANDIDATE_SEC",
    0.5,
)
DRIVER_SUPPRESSION_ASSIGN_SEC = _env_float(
    "VISIONSAFE_DRIVER_SUPPRESSION_ASSIGN_SEC",
    1.0,
)
DRIVER_SUPPRESSION_OCCLUSION_TIMEOUT_SEC = _env_float(
    "VISIONSAFE_DRIVER_SUPPRESSION_OCCLUSION_TIMEOUT_SEC",
    2.0,
)
DRIVER_SUPPRESSION_EXIT_SEC = _env_float(
    "VISIONSAFE_DRIVER_SUPPRESSION_EXIT_SEC",
    0.75,
)

# Lightweight post-detection forklift tracking.  The proximity detector does
# not currently emit track IDs, so this keeps IDs stable without retraining.
FORKLIFT_TRACK_MAX_LOST_FRAMES = _env_int(
    "VISIONSAFE_FORKLIFT_TRACK_MAX_LOST_FRAMES",
    12,
)
FORKLIFT_TRACK_MATCH_IOU = _env_float(
    "VISIONSAFE_FORKLIFT_TRACK_MATCH_IOU",
    0.05,
)
FORKLIFT_TRACK_MAX_CENTER_DISTANCE_PX = _env_float(
    "VISIONSAFE_FORKLIFT_TRACK_MAX_CENTER_DISTANCE_PX",
    220.0,
)
FORKLIFT_DEDUP_IOU = _env_float("VISIONSAFE_FORKLIFT_DEDUP_IOU", 0.45)
FORKLIFT_DEDUP_CENTER_RATIO = _env_float(
    "VISIONSAFE_FORKLIFT_DEDUP_CENTER_RATIO",
    0.35,
)
FORKLIFT_SPEED_LIMIT_MPS = _env_float("VISIONSAFE_FORKLIFT_SPEED_LIMIT_MPS", 2.78)
FORKLIFT_PEDESTRIAN_ZONE_LIMIT_MPS = _env_float(
    "VISIONSAFE_FORKLIFT_PEDESTRIAN_ZONE_LIMIT_MPS",
    1.39,
)
FORKLIFT_SPEED_WARNING_FACTOR = _env_float(
    "VISIONSAFE_FORKLIFT_SPEED_WARNING_FACTOR",
    0.80,
)
FORKLIFT_OVERSPEED_CRITICAL_FACTOR = _env_float(
    "VISIONSAFE_FORKLIFT_OVERSPEED_CRITICAL_FACTOR",
    1.50,
)
FORKLIFT_OVERSPEED_MIN_TRACK_AGE_SEC = _env_float(
    "VISIONSAFE_FORKLIFT_OVERSPEED_MIN_TRACK_AGE_SEC",
    2.0,
)
FORKLIFT_OVERSPEED_CONFIRMATION_SEC = _env_float(
    "VISIONSAFE_FORKLIFT_OVERSPEED_CONFIRMATION_SEC",
    1.0,
)
FORKLIFT_OVERSPEED_SPEED_DEADBAND_MPS = _env_float(
    "VISIONSAFE_FORKLIFT_OVERSPEED_SPEED_DEADBAND_MPS",
    0.5,
)
FORKLIFT_OVERSPEED_MIN_CONFIDENCE = _env_float(
    "VISIONSAFE_FORKLIFT_OVERSPEED_MIN_CONFIDENCE",
    0.60,
)
FORKLIFT_OVERSPEED_PIXEL_MAX_SEVERITY = os.getenv(
    "VISIONSAFE_FORKLIFT_OVERSPEED_PIXEL_MAX_SEVERITY",
    "danger",
).strip().lower()

# Motion state thresholds.  Speeds are metres/second when calibration is
# available; pixel speed uses a conservative fallback only in degraded mode.
MOTION_STATIONARY_SPEED_MPS = _env_float(
    "VISIONSAFE_MOTION_STATIONARY_SPEED_MPS",
    0.10,
)
MOTION_CREEPING_SPEED_MPS = _env_float(
    "VISIONSAFE_MOTION_CREEPING_SPEED_MPS",
    0.30,
)
MOTION_EMA_ALPHA = _env_float("VISIONSAFE_MOTION_EMA_ALPHA", 0.35)
MOTION_MIN_HEADING_SPEED_MPS = _env_float(
    "VISIONSAFE_MOTION_MIN_HEADING_SPEED_MPS",
    0.15,
)
MOTION_FALLBACK_METERS_PER_PIXEL = _env_float(
    "VISIONSAFE_MOTION_FALLBACK_METERS_PER_PIXEL",
    0.01,
)
DISTANCE_FALLBACK_METERS_PER_PIXEL = _env_float(
    "VISIONSAFE_DISTANCE_FALLBACK_METERS_PER_PIXEL",
    0.01,
)

# Dynamic forklift safety bubble, in metres.  These replace fixed pixel
# proximity thresholds when the enterprise policy is active.
PROXIMITY_DANGER_BASE_M = _env_float("VISIONSAFE_PROXIMITY_DANGER_BASE_M", 1.0)
PROXIMITY_DANGER_SPEED_GAIN = _env_float("VISIONSAFE_PROXIMITY_DANGER_SPEED_GAIN", 0.8)
PROXIMITY_DANGER_MIN_M = _env_float("VISIONSAFE_PROXIMITY_DANGER_MIN_M", 1.0)
PROXIMITY_DANGER_MAX_M = _env_float("VISIONSAFE_PROXIMITY_DANGER_MAX_M", 4.0)
PROXIMITY_WARNING_BASE_M = _env_float("VISIONSAFE_PROXIMITY_WARNING_BASE_M", 2.0)
PROXIMITY_WARNING_SPEED_GAIN = _env_float("VISIONSAFE_PROXIMITY_WARNING_SPEED_GAIN", 1.5)
PROXIMITY_WARNING_MIN_M = _env_float("VISIONSAFE_PROXIMITY_WARNING_MIN_M", 2.0)
PROXIMITY_WARNING_MAX_M = _env_float("VISIONSAFE_PROXIMITY_WARNING_MAX_M", 8.0)
PROXIMITY_LOW_CONFIDENCE_RADIUS_SCALE = _env_float(
    "VISIONSAFE_PROXIMITY_LOW_CONFIDENCE_RADIUS_SCALE",
    0.15,
)

# Dynamic forklift zones are generated in image space from bbox footprint and
# track heading.  Meter-level risk thresholds remain handled by proximity policy.
FORKLIFT_ZONE_FRONT_BASE_RATIO = _env_float("VISIONSAFE_FORKLIFT_ZONE_FRONT_BASE_RATIO", 0.80)
FORKLIFT_ZONE_FRONT_SPEED_GAIN = _env_float("VISIONSAFE_FORKLIFT_ZONE_FRONT_SPEED_GAIN", 0.35)
FORKLIFT_ZONE_REAR_BASE_RATIO = _env_float("VISIONSAFE_FORKLIFT_ZONE_REAR_BASE_RATIO", 0.60)
FORKLIFT_ZONE_REAR_SPEED_GAIN = _env_float("VISIONSAFE_FORKLIFT_ZONE_REAR_SPEED_GAIN", 0.25)
FORKLIFT_ZONE_FORK_BASE_RATIO = _env_float("VISIONSAFE_FORKLIFT_ZONE_FORK_BASE_RATIO", 0.70)
FORKLIFT_ZONE_FORK_SPEED_GAIN = _env_float("VISIONSAFE_FORKLIFT_ZONE_FORK_SPEED_GAIN", 0.25)
FORKLIFT_ZONE_SIDE_BASE_RATIO = _env_float("VISIONSAFE_FORKLIFT_ZONE_SIDE_BASE_RATIO", 0.28)
FORKLIFT_ZONE_SIDE_SPEED_GAIN = _env_float("VISIONSAFE_FORKLIFT_ZONE_SIDE_SPEED_GAIN", 0.08)
FORKLIFT_ZONE_HEADING_UNCERTAINTY_WIDTH_GAIN = _env_float(
    "VISIONSAFE_FORKLIFT_ZONE_HEADING_UNCERTAINTY_WIDTH_GAIN",
    0.75,
)
FORKLIFT_ZONE_STATIONARY_DIRECTIONAL_SCALE = _env_float(
    "VISIONSAFE_FORKLIFT_ZONE_STATIONARY_DIRECTIONAL_SCALE",
    0.50,
)

# Relative motion and collision prediction.
COLLISION_PREDICTION_HORIZON_SEC = _env_float("VISIONSAFE_COLLISION_PREDICTION_HORIZON_SEC", 5.0)
COLLISION_MIN_CLOSING_SPEED_MPS = _env_float("VISIONSAFE_COLLISION_MIN_CLOSING_SPEED_MPS", 0.05)
COLLISION_STATIONARY_REL_SPEED_MPS = _env_float("VISIONSAFE_COLLISION_STATIONARY_REL_SPEED_MPS", 0.05)
COLLISION_CROSSING_DISTANCE_M = _env_float("VISIONSAFE_COLLISION_CROSSING_DISTANCE_M", 1.5)
COLLISION_PARALLEL_COSINE = _env_float("VISIONSAFE_COLLISION_PARALLEL_COSINE", 0.75)
COLLISION_ACTOR_RADIUS_M = _env_float("VISIONSAFE_COLLISION_ACTOR_RADIUS_M", 0.6)

# Dynamic risk scoring thresholds.
RISK_WARNING_SCORE = _env_float("VISIONSAFE_RISK_WARNING_SCORE", 45.0)
RISK_DANGER_SCORE = _env_float("VISIONSAFE_RISK_DANGER_SCORE", 65.0)
RISK_CRITICAL_SCORE = _env_float("VISIONSAFE_RISK_CRITICAL_SCORE", 85.0)
RISK_TTC_WARNING_SEC = _env_float("VISIONSAFE_RISK_TTC_WARNING_SEC", 6.0)
RISK_TTC_DANGER_SEC = _env_float("VISIONSAFE_RISK_TTC_DANGER_SEC", 3.0)
RISK_TTC_CRITICAL_SEC = _env_float("VISIONSAFE_RISK_TTC_CRITICAL_SEC", 1.5)
RISK_SPEED_REFERENCE_MPS = _env_float("VISIONSAFE_RISK_SPEED_REFERENCE_MPS", 2.0)
RISK_PERSISTENCE_FULL_SEC = _env_float("VISIONSAFE_RISK_PERSISTENCE_FULL_SEC", 2.0)

# Risk-driven proximity event generation.  Scores below monitor remain
# metadata-only and are not emitted into the alert pipeline.
PROXIMITY_EVENT_MONITOR_SCORE = _env_float("VISIONSAFE_PROXIMITY_EVENT_MONITOR_SCORE", 30.0)
PROXIMITY_EVENT_NEAR_MISS_SCORE = _env_float("VISIONSAFE_PROXIMITY_EVENT_NEAR_MISS_SCORE", 35.0)
PROXIMITY_EVENT_DEESCALATION_HOLD_SEC = _env_float(
    "VISIONSAFE_PROXIMITY_EVENT_DEESCALATION_HOLD_SEC",
    0.75,
)
PROXIMITY_EVENT_STATE_TTL_SEC = _env_float("VISIONSAFE_PROXIMITY_EVENT_STATE_TTL_SEC", 2.0)
PROXIMITY_RESOLUTION_GRACE_SEC = _env_float("VISIONSAFE_PROXIMITY_RESOLUTION_GRACE_SEC", 5.0)
PROXIMITY_REOPEN_GRACE_SEC = _env_float("VISIONSAFE_PROXIMITY_REOPEN_GRACE_SEC", 30.0)
PROXIMITY_POST_RESOLUTION_COOLDOWN_SEC = _env_float(
    "VISIONSAFE_PROXIMITY_POST_RESOLUTION_COOLDOWN_SEC",
    60.0,
)

# --- FPS targets
TARGET_INPUT_FPS = 20  # cap RTSP / file read rate
TARGET_INFER_FPS = 20  # inference loop target

# --- Per-task scheduling (frame counter modulo)
POSE_EVERY_N = 1
FALL_EVERY_N = 1
ERGONOMIC_EVERY_N = 10  # ~1.5 Hz

# --- Stream / reconnect
RTSP_TIMEOUT_SEC = 10
RTSP_MAX_RETRIES = 5
RTSP_RETRY_BACKOFF = [1, 2, 4, 8, 16]  # seconds between retries
# Latest-frame policy: keep only the newest frame available.
STREAM_BUFFER_SIZE = max(1, _env_int("VISIONSAFE_STREAM_BUFFER_SIZE", 1))
# For deterministic analytics (and unit tests), default to looping files.
LOOP_FILE_SOURCE = _env_bool("VISIONSAFE_LOOP_FILE_SOURCE", True)

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

BACKEND_INCIDENTS_PATH = os.getenv("VISIONSAFE_BACKEND_INCIDENTS_PATH", "/api/incidents")
BACKEND_SAFETY_ZONES_PATH_TEMPLATE = os.getenv(
    "VISIONSAFE_BACKEND_SAFETY_ZONES_PATH_TEMPLATE",
    "/api/edge/cameras/{camera_id}/safety-zones",
)
BACKEND_AUTH_TOKEN = os.getenv("VISIONSAFE_BACKEND_AUTH_TOKEN", "")
BACKEND_SOURCE_ID = os.getenv("VISIONSAFE_BACKEND_SOURCE_ID", "")
BACKEND_CAMERA_NAME = os.getenv("VISIONSAFE_BACKEND_CAMERA_NAME", "")
BACKEND_WORKER_ID = os.getenv("VISIONSAFE_BACKEND_WORKER_ID", "")
BACKEND_WORKER_GPU_ID = os.getenv("VISIONSAFE_BACKEND_WORKER_GPU_ID", "")

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
OFFLINE_FLUSH_MAX_PER_CYCLE = _env_int(
    "VISIONSAFE_OFFLINE_FLUSH_MAX_PER_CYCLE",
    1,
)
OFFLINE_SHUTDOWN_FLUSH_LIMIT = _env_int(
    "VISIONSAFE_OFFLINE_SHUTDOWN_FLUSH_LIMIT",
    1,
)

SAFETY_ZONES_ENABLED = _env_bool("VISIONSAFE_SAFETY_ZONES_ENABLED", True)
SAFETY_ZONES_REFRESH_INTERVAL_SEC = _env_float(
    "VISIONSAFE_SAFETY_ZONES_REFRESH_INTERVAL_SEC",
    30.0,
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
FALL_ASPECT_RATIO_THRESHOLD = 0.90  # w/h above which person may be lying
FALL_HIP_RATIO_THRESHOLD = 0.2  # hip position below this = falling
FALL_HIP_RECOVERY_THRESHOLD = 0.6  # hip position above this = recovered
FALL_VELOCITY_THRESHOLD = 15.0  # pixels/frame downward velocity
FALL_VELOCITY_WINDOW = 8  # frames to compute velocity over
FALL_CANDIDATE_TIMEOUT = 2.5  # seconds in fall position to confirm
FALL_IMMOBILITY_THRESHOLD = 5.0  # max px movement to count as "immobile"
FALL_AREA_JITTER_THRESHOLD = 0.15  # max relative area change for immobility
FALL_SEATED_GUARD_DY = 6.0  # if vertical motion is below this, treat as stable low posture
FALL_SEATED_GUARD_AR_SPREAD = 0.10  # low aspect-ratio variation suggests seated/static posture
FALL_COOLDOWN_SEC = _env_float("VISIONSAFE_FALL_COOLDOWN_SEC", 50.0)  # before same track re-fires
FALL_TRACK_PURGE_SEC = 5.0  # purge stale track state

# --- PostureAnalyzer thresholds
POSTURE_KEYPOINT_CONF_MIN = 0.5  # discard keypoints below this
POSTURE_EMA_ALPHA = 0.6  # temporal smoothing weight
POSTURE_SUSTAINED_THRESHOLD = 4.0  # seconds of poor posture before event
POSTURE_COOLDOWN_SEC = _env_float("VISIONSAFE_POSTURE_COOLDOWN_SEC", 50.0)  # per track_id cooldown
TEMPORAL_SMOOTH_WINDOW = 5
ERGONOMIC_SCORE_WINDOW = 90  # frames at 1.5Hz ~ 60s

# --- Event Persistence / Aggregation
FALL_PERSISTENCE_SEC = 0.0  # fall already has candidate->confirm
HAZARD_COOLDOWN_SEC = _env_float("VISIONSAFE_HAZARD_COOLDOWN_SEC", 50.0)
EVENT_AGGREGATION_WINDOW_SEC = 5.0  # aggregate repeated events within window
EVENT_MAX_UPDATES_PER_WINDOW = 3  # max severity escalations per window
SEVERITY_ZONE_WEIGHT = _env_float("VISIONSAFE_SEVERITY_ZONE_WEIGHT", 1.0)
SEVERITY_DURATION_WEIGHT = _env_float("VISIONSAFE_SEVERITY_DURATION_WEIGHT", 1.0)
SEVERITY_COUNT_WEIGHT = _env_float("VISIONSAFE_SEVERITY_COUNT_WEIGHT", 1.0)
ESCALATION_ENABLED = _env_bool("VISIONSAFE_ESCALATION_ENABLED", True)
ESCALATION_MEDIUM_SEC = _env_float("VISIONSAFE_ESCALATION_MEDIUM_SEC", 60.0)
ESCALATION_HIGH_SEC = _env_float("VISIONSAFE_ESCALATION_HIGH_SEC", 180.0)
ESCALATION_CRITICAL_SEC = _env_float("VISIONSAFE_ESCALATION_CRITICAL_SEC", 300.0)
SMART_COOLDOWN_RESET_ON_ESCALATION = _env_bool(
    "VISIONSAFE_SMART_COOLDOWN_RESET_ON_ESCALATION",
    True,
)

# --- Evidence video clip settings (replaces single-frame snapshot)
EVIDENCE_CLIP_ENABLED = _env_bool("VISIONSAFE_EVIDENCE_CLIP_ENABLED", True)
# Total clip duration in seconds; hazard event falls at the midpoint.
EVIDENCE_CLIP_DURATION_SEC = _env_float("VISIONSAFE_EVIDENCE_CLIP_DURATION_SEC", 3.0)
# Half of the above — frames collected before and after the event.
EVIDENCE_CLIP_HALF_SEC = EVIDENCE_CLIP_DURATION_SEC / 2.0
# Max width for clip frames (downscaled for bandwidth efficiency).
EVIDENCE_CLIP_MAX_WIDTH = _env_int("VISIONSAFE_EVIDENCE_CLIP_MAX_WIDTH", 640)
# JPEG quality for the poster thumbnail extracted from the clip center frame.
EVIDENCE_CLIP_JPEG_QUALITY = _env_int("VISIONSAFE_EVIDENCE_CLIP_JPEG_QUALITY", 72)
# FPS used when encoding the video clip (matches TARGET_INFER_FPS).
EVIDENCE_CLIP_VIDEO_FPS = _env_int("VISIONSAFE_EVIDENCE_CLIP_VIDEO_FPS", 20)
# How long to wait for post-event frames before clip assembly (≥ half duration).
EVIDENCE_CLIP_POST_WAIT_SEC = _env_float("VISIONSAFE_EVIDENCE_CLIP_POST_WAIT_SEC", 1.5)

# --- Calibration (camera -> ground-plane)
DEFAULT_PIXELS_PER_METER = 0.0  # 0 = uncalibrated (pixel mode)
