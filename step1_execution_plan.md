# VisionSafe 360 — Architecture Adjustment & Step 1 Execution Plan

> **Reviewer:** Senior AI Systems Architect
> **Date:** March 2, 2026
> **Target Runtime:** Dell/Lenovo laptop — Intel i5-13th Gen, NVIDIA RTX 4050 6GB VRAM, CUDA 12.x
> **Scope:** RTX 4050-specific architecture redesign + first implementation step

---

## Architecture Adjustment for RTX 4050

### Current Design Problems

The original spec assumes **three separate model instances** (PPE detector, Vehicle detector, Pose model) each loaded in VRAM simultaneously. On RTX 4050 (6GB), this is dangerous:

| Original model | Format | Estimated VRAM (FP16, bs=1) |
|---|---|---|
| YOLOv8s — PPE | FP16 | ~480 MB |
| YOLOv8s — Vehicle | FP16 | ~480 MB |
| YOLOv8s-Pose | FP16 | ~560 MB |
| CUDA context + PyTorch runtime | — | ~800 MB |
| Frame tensors (640×640×3, 4 cameras) | FP16 | ~100 MB |
| ByteTrack state + misc | — | ~200 MB |
| **Original total** | | **~2,620 MB — technically fits** |

The VRAM headroom looks acceptable at first glance, but the problem is **model switching overhead and fragmentation** when all three models are resident. The bigger architectural problem is **correctness**: running three separate detectors means the same person can be detected at different positions in Model 1 vs Model 2, making cross-model person association ambiguous. ByteTrack IDs from the PPE pipeline ≠ ByteTrack IDs from the Vehicle pipeline unless you force shared detection.

### Required Changes

**1. Consolidate to exactly 2 models:**

| Model slot | Purpose | Classes |
|---|---|---|
| **Model A — Unified Detector** | person, PPE states, vehicles | `person`, `helmet_on`, `helmet_off`, `vest_on`, `vest_off`, `forklift`, `loader`, `truck`, `vehicle_other` (9 classes) |
| **Model B — Pose Estimator** | keypoints for fall + ergonomics | 17 COCO keypoints on every detected person |

This eliminates the double-detection problem. A single person detection pass feeds both PPE analysis (class labels on that detection) and vehicle proximity (same bounding boxes, same track IDs). No cross-model association needed.

**2. Single ByteTrack instance per camera, consuming Model A output only:**

```
Model A output: List[Detection(bbox, class, confidence)]
         │
         ▼
ByteTrack(camera_id)  ← ONE instance per camera, runs ONCE per frame
         │
         ▼
TrackedDetections: List[Detection + track_id]
         │
    ┌────┴─────────────┐
    ▼                  ▼
HazardAnalyzer      PoseFilter
(PPE + Proximity)   (select person bboxes → Model B input)
```

**3. Latest-frame policy via `deque(maxlen=1)` — not a Queue:**

```python
# WRONG — causes latency buildup:
frame_queue = queue.Queue(maxsize=5)

# CORRECT — always processes the newest frame:
from collections import deque
frame_buffer: dict[str, deque] = {cam_id: deque(maxlen=1) for cam_id in cameras}
```

**4. Per-task FPS scheduling — explicit budgets:**

| Hazard task | Frequency | Rationale |
|---|---|---|
| Fall detection | Every frame (15 Hz) | Safety-critical, fast event |
| Vehicle proximity | Every frame when vehicle in scene; every 4th frame otherwise | Proximity is fast-moving |
| PPE compliance | Every 3rd frame (5 Hz) | Violations are sustained, not instantaneous |
| Ergonomic scoring | Every 10th frame (1.5 Hz) | Chronic risk, 10s window smoothing |

Implemented as frame counters per camera: `frame_counter[cam_id] % N == 0`.

**5. Homography stored and loaded per-camera at startup:**

```
edge_ai/calibrations/
├── cam_01.json   {"H": [[...],[...],[...]], "camera_id": "cam_01", "validated": true}
├── cam_02.json
└── ...
```

Loaded once into `HazardAnalyzer.__init__()` as `self.homography: dict[str, np.ndarray]`. Never re-loaded mid-run. Proximity computation uses `cv2.perspectiveTransform` with the per-camera matrix — only on frames where both a `person` AND a vehicle class are detected.

---

## Model Strategy

### YOLO11 vs YOLOv8 Decision

**Explicit verification required before writing a single training line:**

```bash
# Check what's actually available from Ultralytics
python3 -c "from ultralytics import YOLO; m = YOLO('yolo11s.pt'); print(m.info())"
python3 -c "from ultralytics import YOLO; m = YOLO('yolo11s-pose.pt'); print(m.info())"
```

**Decision table:**

| Model | Available as of March 2026 | Use |
|---|---|---|
| `yolo11s.pt` | Yes — released Oct 2024 | Use for Model A (Unified Detector) |
| `yolo11s-pose.pt` | Yes — released alongside YOLO11 | Use for Model B if inference validates |
| `yolo11n.pt` | Yes | Fallback if 11s too slow for 4-camera |
| `yolov8s-pose.pt` | Yes (stable) | Fallback for Model B if YOLO11-pose has issues |

**Default recommendation: YOLO11s for both models.** YOLO11s is ~10% faster than YOLOv8s at the same accuracy level on COCO, with a smaller parameter count. On RTX 4050 the latency difference is real (~28 ms vs ~35 ms per frame at 640px FP16).

### Model Size Recommendation for RTX 4050

**Model A — Unified Detector:**

| Size | mAP@COCO | Latency (RTX 4050, FP16, bs=1) | VRAM | Verdict |
|---|---|---|---|---|
| YOLO11n | 39.5 | ~12 ms | ~380 MB | Too low accuracy for PPE |
| **YOLO11s** | **47.0** | **~18 ms** | **~480 MB** | **Primary choice** |
| YOLO11m | 51.5 | ~32 ms | ~980 MB | Use only if n-camera budget allows |

**Model B — Pose Estimator:**

| Size | AP-pose@COCO | Latency (RTX 4050, FP16, bs=1) | VRAM | Verdict |
|---|---|---|---|---|
| YOLO11s-pose | 67.9 | ~20 ms | ~520 MB | **Primary choice** |
| yolov8s-pose | 69.0 | ~25 ms | ~540 MB | Fallback if 11s-pose unavailable |

**Total VRAM budget (2 models, 4 cameras):**

```
Model A resident:           480 MB
Model B resident:           520 MB
PyTorch + CUDA context:     750 MB
4× frame tensors (640²):    120 MB
ByteTrack state (4 cams):    80 MB
Activations during fwd:     300 MB (peak, single inference)
Python + OS overhead:       400 MB
─────────────────────────────────
TOTAL PEAK:               2,650 MB  (44% of 6GB)
SAFETY HEADROOM:          3,350 MB  (never goes above ~3.2GB with 4 cameras)
```

This configuration is safe. You have >3 GB free headroom, which allows future model upgrades or batch-size experiments without OOM.

### Memory-Safe Configuration Defaults

```python
# edge_ai/src/config/settings.py — HARD VALUES, not placeholders

DETECTOR_WEIGHTS    = "yolo11s.pt"          # or custom fine-tuned .pt
POSE_WEIGHTS        = "yolo11s-pose.pt"     # fallback: "yolov8s-pose.pt"
IMGSZ               = 640                   # DO NOT increase — each +64px costs ~15% VRAM
PRECISION           = "fp16"                # FP16 on CUDA: halves VRAM, ~2x faster
MAX_DET             = 50                    # cap at 50 detections per frame
CONF_THRESHOLD      = 0.35                  # higher = fewer FP, less NMS overhead
IOU_THRESHOLD       = 0.45                  # standard NMS
STREAM_BUFFER_SIZE  = 1                     # deque(maxlen=1) — latest-frame policy
DECODE_THREADS      = 1                     # per-camera RTSP decode thread
INFERENCE_DEVICE    = "cuda:0"
USE_TENSORRT        = False                 # False for development — PyTorch .pt is fine
                                            # TRT export only for production Jetson
TARGET_INPUT_FPS    = 15                    # RTSP read target
TARGET_INFERENCE_FPS = 10                   # effective after frame scheduling
```

**Why these numbers are safe for RTX 4050:**
- `imgsz=640`: Standard. Going to 1280 would double VRAM consumption and push latency to ~80ms — unacceptable.
- `fp16`: RTX 4050 has Tensor Cores optimized for FP16. This is the single highest-impact optimization: ~40% latency reduction vs FP32 at zero accuracy cost on detection tasks.
- `max_det=50`: A factory floor rarely has >20 people + 5 vehicles. 50 is a safe ceiling that prevents NMS from consuming 30ms on a crowded frame.
- `conf=0.35`: Low enough to catch PPE violations with partial occlusion; high enough to suppress background clutter that wastes NMS time.
- `TRT=False` during development: ONNX/TRT export adds 2–5 hours of compile time and requires exact CUDA/TRT version matching. PyTorch `.pt` with `fp16` is 80% of the production performance with zero setup friction.

---

## Inference Optimization Plan

### Async Pipeline Architecture

**Threading model for 1–4 cameras on RTX 4050:**

```
Thread layout (1 camera):
┌─────────────────────────────────────────────────────────────┐
│  Thread: RTSP-cam_01   │  OpenCV VideoCapture loop           │
│  Runs on: CPU core 0   │  Decode JPEG → numpy BGR frame      │
│  Output: deque[frame]  │  Rate: up to 30 FPS                 │
│                        │  Policy: deque(maxlen=1) drops old  │
└────────────┬────────────┘
             │  Latest frame available (non-blocking pop)
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Thread: Inference     │  Single GPU inference thread        │
│  Runs on: CPU + GPU    │  Polls all camera deques            │
│  Rate: ~10 FPS         │  Serialized CUDA calls (no concur.) │
│  Input: frame + cam_id │                                     │
│  Output: InferenceResult per camera per frame               │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Thread: Analysis      │  CPU-only, fast                     │
│  Runs on: CPU core 1   │  ByteTrack update                   │
│                        │  HazardAnalyzer rules               │
│                        │  PostureAnalyzer angles             │
│  Output: HazardEvent[] │                                     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Thread: Alerts        │  CPU-only, async I/O                │
│  Runs on: CPU core 2   │  AlertManager dedup + cooldown      │
│                        │  BackendClient HTTP POST            │
│                        │  FCMService push                    │
│  Uses: asyncio event   │                                     │
│        loop internally │                                     │
└─────────────────────────────────────────────────────────────┘
```

**Critical rule: One thread owns the GPU.** Do NOT run Model A and Model B inference in separate threads. GPU context switching between threads on RTX 4050 adds 10–30ms overhead per switch. Run them sequentially in the same inference thread:

```python
# inference_thread (pseudocode):
while running:
    for cam_id in active_cameras:
        if not frame_buffers[cam_id]:
            continue
        frame = frame_buffers[cam_id][0]   # deque latest

        # Frame scheduling
        fc = frame_counters[cam_id]
        frame_counters[cam_id] += 1

        # Model A — always (needed for fall + vehicle)
        det_results = model_a.predict(frame, device="cuda:0", half=True,
                                       conf=0.35, iou=0.45, max_det=50,
                                       verbose=False)[0]

        # Model B — only on fall/ergo schedule
        pose_results = None
        if fc % POSE_EVERY_N == 0:
            pose_results = model_b.predict(frame, device="cuda:0", half=True,
                                            conf=0.40, verbose=False)[0]

        inference_queue.put(InferenceResult(cam_id, frame, det_results, pose_results))
```

### Batching Policy

**Do NOT batch across cameras in V1.** Reasons:
- Batching 4 frames together requires all 4 cameras to produce a frame before inference runs → introduces up to 66ms of forced wait at 15 FPS input.
- On RTX 4050 with YOLO11s, single-frame inference is already ~18ms. Batch-of-4 inference is ~35ms (not 4×18ms — GPU has headroom). Net gain is marginal (~13ms total vs ~18ms×4 sequential = ~72ms for all 4).
- But sequential processing at 10 FPS per camera means 4 cameras × 18ms = 72ms per full cycle, achieving ~13.9 FPS effective throughput across 4 cameras simultaneously — perfectly adequate.

Batching becomes beneficial only when scaling to 8+ cameras. Defer to V2.

### Model A Inference Pass — Unified Class Map

The key design decision is the class mapping for the unified detector. Training must use this exact schema:

```python
UNIFIED_CLASS_MAP = {
    0: "person",
    1: "helmet_on",
    2: "helmet_off",
    3: "vest_on",
    4: "vest_off",
    5: "forklift",
    6: "loader",
    7: "truck",
    8: "vehicle_other",
}

# Consumer responsibilities:
# HazardAnalyzer.ppe_check   reads: classes 0–4
# HazardAnalyzer.proximity   reads: classes 0, 5–8
# ByteTrack                  tracks: all classes (separate tracker per class group if needed)
```

### Temporal Smoothing for Pose Pipeline

```python
# PostureAnalyzer maintains a per-person keypoint history
TEMPORAL_SMOOTH_WINDOW = 5     # frames — smooth keypoints over last 5 pose frames
ERGONOMIC_SCORE_WINDOW = 90    # frames at 1.5Hz = ~60 seconds for RULA exposure metric
FALL_VELOCITY_WINDOW   = 8     # frames at 15Hz = ~0.5 seconds for descent velocity

# Smoothing: exponential moving average on keypoints
alpha = 0.6  # new frame weight; 1-alpha = history weight
kp_smooth[track_id] = alpha * kp_new + (1 - alpha) * kp_smooth[track_id]
```

---

## Step 1 Execution Plan (Detailed)

### Technical Goal

Build a **single-camera, single-model proof-of-pipeline** that:
1. Reads a local `.mp4` file (simulates RTSP)
2. Runs YOLO11s detection (COCO-pretrained, no custom training yet)
3. Applies ByteTrack
4. Draws annotated output to screen or saves to file
5. Logs structured per-frame metrics to stdout
6. Handles simulated "camera drop" (EOF → reconnect/restart)
7. Proves the `deque(maxlen=1)` latest-frame policy is working by measuring dropped frame count

This is the **nervous system** of the entire project. Every downstream component (HazardAnalyzer, AlertManager, Backend) plugs into this pipe. Get it right now.

---

### Required Components (What to build in Step 1)

| Component | File | Responsibility |
|---|---|---|
| `Settings` | `edge_ai/src/config/settings.py` | Single source of truth for all numeric config |
| `FrameBundle` | `edge_ai/src/models/frame_bundle.py` | Dataclass: frame + camera_id + timestamp + frame_number |
| `InferenceResult` | `edge_ai/src/models/inference_result.py` | Dataclass: FrameBundle + detections + pose (nullable) |
| `Detection` | `edge_ai/src/models/detection.py` | Dataclass: class_id, class_name, conf, bbox, track_id |
| `StreamHandler` | `edge_ai/src/streaming/stream_handler.py` | RTSP/file reader, decode thread, deque buffer |
| `InferenceEngine` | `edge_ai/src/config/inference/inference_engine.py` | Model loading, `.predict()` wrapper, metric logging |
| `PipelineOrchestrator` | `edge_ai/src/main.py` | Main loop, ties StreamHandler → InferenceEngine |
| `MetricsLogger` | `edge_ai/src/utils/logger.py` | Structured JSON line logger for per-frame metrics |

**NOT in Step 1** (zero stubs, zero placeholder code):
- HazardAnalyzer, PostureAnalyzer, AlertManager, BackendClient, FCMService, SirenController, FaceBlurrer

---

### Folder Structure

```
edge_ai/
├── src/
│   ├── main.py                          # Entry point — PipelineOrchestrator
│   ├── config/
│   │   ├── settings.py                  # All constants — imgsz, fps, paths, thresholds
│   │   └── inference/
│   │       └── inference_engine.py      # YOLO11s wrapper + ByteTrack
│   ├── streaming/
│   │   └── stream_handler.py            # Decode thread + deque(maxlen=1)
│   ├── models/
│   │   ├── frame_bundle.py              # FrameBundle dataclass
│   │   ├── inference_result.py          # InferenceResult dataclass
│   │   ├── detection.py                 # Detection dataclass + UNIFIED_CLASS_MAP
│   │   ├── severity.py                  # Severity enum (stub — define now, use later)
│   │   └── hazard_event.py              # HazardEvent dataclass (stub — define now)
│   └── utils/
│       ├── logger.py                    # Structured JSON logger
│       └── drawing.py                   # cv2 bbox/label overlay
├── tests/
│   └── test_stream_handler.py
├── weights/
│   └── yolo11s.pt                       # Downloaded via: yolo download model=yolo11s
└── requirements.txt
```

---

### Minimal Runnable Prototype — Exact Specification

**Command to run:**
```bash
cd edge_ai
python src/main.py --source path/to/test.mp4 --cam-id cam_01 --show
```

**What it must do:**
1. `StreamHandler` spawns a thread that reads frames from `test.mp4` at native FPS (or capped at 30 FPS), places each decoded frame into `deque(maxlen=1, cam_id="cam_01")`.
2. Main inference loop polls the deque at a target rate of 15 Hz using a `time.sleep` throttle.
3. For each popped frame: run `InferenceEngine.run_detector(frame)` → returns `List[Detection]` (COCO classes for now — no custom training).
4. Pass detections through `ByteTrack.update()` → assign `track_id` to each `Detection`.
5. Call `drawing.draw_detections(frame, detections)` — render boxes with class name + track_id + confidence.
6. Emit one JSON log line per frame to stdout:

```json
{
  "ts": "2026-03-02T10:00:01.234Z",
  "cam_id": "cam_01",
  "frame_no": 142,
  "input_fps": 30.0,
  "inference_fps": 14.8,
  "inference_ms": 19.3,
  "n_detections": 4,
  "n_tracked": 3,
  "dropped_frames": 18,
  "vram_mb": 1240
}
```

7. If source reaches EOF (simulated camera drop): `StreamHandler` logs a WARNING and restarts `VideoCapture` from frame 0 (loop). Log `"reconnect_attempt": 1`.
8. `--show` flag opens a `cv2.imshow` window. Without it, writes annotated frames to `edge_ai/output/cam_01_out.mp4`.

**Inputs:** Any local `.mp4` file with people in it.
**Outputs:** Annotated video + JSON metric lines on stdout.

---

### Performance Target

| Metric | Target | Failure threshold |
|---|---|---|
| Inference FPS (1 camera) | ≥ 13 FPS | < 10 FPS → investigate |
| Inference latency (Model A, p50) | ≤ 22 ms | > 40 ms → wrong precision mode |
| Inference latency (Model A, p99) | ≤ 35 ms | > 60 ms → check VRAM pressure |
| VRAM usage (model resident + active) | ≤ 1,400 MB | > 2,000 MB → precision not FP16 |
| Dropped frame rate | ≥ 30% at 30 FPS input | < 5% means queue is backing up |
| Reconnect simulated drop recovery | ≤ 2 seconds | > 5 seconds → reconnect logic broken |
| CPU usage (inference thread) | ≤ 15% | > 50% → pre/post processing bottleneck |

> **Note on dropped frames:** A 30%+ drop rate at 30 FPS input with 15 FPS inference IS correct behavior — you are intentionally discarding old frames. If drop rate is 0%, the `deque(maxlen=1)` is not working (you may have accidentally used a `Queue` instead).

---

### Exact Implementation Details for Step 1

**`settings.py`:**
```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]  # edge_ai/

DETECTOR_WEIGHTS  = BASE_DIR / "weights" / "yolo11s.pt"
POSE_WEIGHTS      = BASE_DIR / "weights" / "yolo11s-pose.pt"
IMGSZ             = 640
PRECISION         = "fp16"          # half=True in .predict()
CONF_THRESHOLD    = 0.35
IOU_THRESHOLD     = 0.45
MAX_DET           = 50
INFERENCE_DEVICE  = "cuda:0"

TARGET_INPUT_FPS  = 30              # cap RTSP read rate
TARGET_INFER_FPS  = 15              # inference loop target

# Per-task scheduling (run Model B every N frames)
POSE_EVERY_N      = 3               # ~5 Hz at 15 FPS inference
PPE_EVERY_N       = 1               # every frame (uses Model A output, no extra inference)
PROXIMITY_EVERY_N = 1               # every frame
ERGONOMIC_EVERY_N = 10              # ~1.5 Hz

# Stream
RTSP_TIMEOUT_SEC  = 10
RTSP_MAX_RETRIES  = 5
RTSP_RETRY_BACKOFF= [1, 2, 4, 8, 16]  # seconds between retries

# Output
OUTPUT_DIR        = BASE_DIR / "output"
LOG_LEVEL         = "INFO"
```

**`stream_handler.py`:**
```python
import threading, time, cv2, logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from ..config.settings import TARGET_INPUT_FPS, RTSP_MAX_RETRIES, RTSP_RETRY_BACKOFF

@dataclass
class FrameBundle:
    frame: np.ndarray
    camera_id: str
    timestamp: float
    frame_number: int

class StreamHandler:
    def __init__(self, source: str, camera_id: str):
        self.source = source
        self.camera_id = camera_id
        self.buffer: deque = deque(maxlen=1)   # latest-frame policy
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.frame_count = 0
        self.dropped_count = 0
        self.last_fps_time = time.monotonic()
        self.input_fps = 0.0
        self._reconnect_count = 0
        self.log = logging.getLogger(f"StreamHandler.{camera_id}")

    def start(self):
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def get_frame(self) -> Optional[FrameBundle]:
        return self.buffer[0] if self.buffer else None

    def _capture_loop(self):
        frame_interval = 1.0 / TARGET_INPUT_FPS
        for attempt in range(RTSP_MAX_RETRIES + 1):
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                wait = RTSP_RETRY_BACKOFF[min(attempt, len(RTSP_RETRY_BACKOFF)-1)]
                self.log.warning(f"Cannot open source, retry {attempt+1} in {wait}s")
                time.sleep(wait)
                continue
            self._reconnect_count += 1
            self.log.info(f"Stream opened (attempt {self._reconnect_count})")
            t0 = time.monotonic()
            local_count = 0
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    self.log.warning("Stream EOF or read failure — reconnecting")
                    break
                now = time.monotonic()
                elapsed = now - t0
                expected = local_count * frame_interval
                if elapsed < expected:
                    time.sleep(expected - elapsed)
                bundle = FrameBundle(
                    frame=frame,
                    camera_id=self.camera_id,
                    timestamp=time.time(),
                    frame_number=self.frame_count,
                )
                # deque(maxlen=1): if buffer was full, old frame is auto-dropped
                old_length = len(self.buffer)
                self.buffer.append(bundle)
                if old_length == 1:
                    self.dropped_count += 1
                self.frame_count += 1
                local_count += 1
                # Rolling FPS
                if local_count % 30 == 0:
                    self.input_fps = 30.0 / (now - t0) if (now - t0) > 0 else 0
                    t0 = now
                    local_count = 0
            cap.release()
            if self._stop_event.is_set():
                break
        self.log.info("Capture loop terminated")
```

**`inference_engine.py`:**
```python
import time, logging
import numpy as np
import torch
from ultralytics import YOLO
from ..config.settings import (
    DETECTOR_WEIGHTS, POSE_WEIGHTS, IMGSZ, CONF_THRESHOLD,
    IOU_THRESHOLD, MAX_DET, INFERENCE_DEVICE
)
from ..models.detection import Detection, UNIFIED_CLASS_MAP
from ..models.frame_bundle import FrameBundle

class InferenceEngine:
    def __init__(self):
        self.log = logging.getLogger("InferenceEngine")
        self.device = INFERENCE_DEVICE
        self._detector: YOLO = None
        self._pose_model: YOLO = None
        self._detector_loaded = False
        self._pose_loaded = False

    def load_detector(self):
        self.log.info(f"Loading detector: {DETECTOR_WEIGHTS}")
        self._detector = YOLO(str(DETECTOR_WEIGHTS))
        # Warmup — 3 dummy passes to initialize CUDA kernels
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(3):
            self._detector.predict(dummy, device=self.device, half=True,
                                    conf=0.9, verbose=False)
        self._detector_loaded = True
        self.log.info("Detector ready")

    def load_pose(self):
        self.log.info(f"Loading pose model: {POSE_WEIGHTS}")
        self._pose_model = YOLO(str(POSE_WEIGHTS))
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(3):
            self._pose_model.predict(dummy, device=self.device, half=True,
                                      conf=0.9, verbose=False)
        self._pose_loaded = True
        self.log.info("Pose model ready")

    def run_detector(self, bundle: FrameBundle) -> tuple[list[Detection], float]:
        """Returns (detections, latency_ms)"""
        t0 = time.perf_counter()
        results = self._detector.predict(
            bundle.frame,
            device=self.device,
            half=True,
            imgsz=IMGSZ,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            max_det=MAX_DET,
            verbose=False
        )[0]
        latency_ms = (time.perf_counter() - t0) * 1000

        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            detections.append(Detection(
                class_id=cls_id,
                class_name=UNIFIED_CLASS_MAP.get(cls_id, f"class_{cls_id}"),
                confidence=float(box.conf[0]),
                bbox=(int(box.xyxy[0][0]), int(box.xyxy[0][1]),
                      int(box.xyxy[0][2]), int(box.xyxy[0][3])),
                track_id=None,
            ))
        return detections, latency_ms

    def run_pose(self, bundle: FrameBundle):
        """Returns (ultralytics Results object, latency_ms)"""
        t0 = time.perf_counter()
        results = self._pose_model.predict(
            bundle.frame,
            device=self.device,
            half=True,
            imgsz=IMGSZ,
            conf=0.40,
            verbose=False
        )[0]
        latency_ms = (time.perf_counter() - t0) * 1000
        return results, latency_ms

    def vram_used_mb(self) -> int:
        if torch.cuda.is_available():
            return int(torch.cuda.memory_allocated(self.device) / 1024 / 1024)
        return 0
```

---

### Offline Resilience (Step 1 Scope)

In Step 1, the BackendClient does not exist yet. However, the **queue infrastructure** must be established now or it will be retrofitted incorrectly later. Add this to `settings.py`:

```python
OFFLINE_QUEUE_DB   = BASE_DIR / "offline_queue.db"   # SQLite
BACKEND_URL        = "http://localhost:8000"
BACKEND_TIMEOUT    = 5.0      # seconds per request
BACKEND_MAX_RETRY  = 3
BACKEND_RETRY_BACKOFF = [2, 5, 15]   # seconds
```

The `offline_queue.db` is created but empty in Step 1. `BackendClient` in Step 4 will use it.

---

## Technical Acceptance Criteria

### Functional Acceptance

- [ ] `python src/main.py --source test.mp4 --cam-id cam_01` runs to completion without exception
- [ ] `cv2.imshow` window shows bounding boxes with class labels and track IDs
- [ ] Track IDs are stable across ≥ 10 consecutive frames for a non-occluded person
- [ ] `FrameBundle` dataclass is importable from `edge_ai/src/models/` by any other module
- [ ] `Detection` dataclass uses `UNIFIED_CLASS_MAP` — class indices 0–8 defined and testable
- [ ] `Severity` and `HazardEvent` stubs exist and are importable (even if empty bodies)
- [ ] EOF triggers a log line: `"level": "WARNING", "event": "stream_eof", "reconnect_attempt": 1`
- [ ] After EOF, stream restarts and inference continues without process restart
- [ ] JSON metric line is emitted to stdout for every processed frame

### Performance Acceptance

- [ ] Inference FPS ≥ 13 Hz measured over a 60-second run (1 camera, test.mp4)
- [ ] Model A p50 latency ≤ 22 ms (visible in JSON logs as `inference_ms`)
- [ ] VRAM usage ≤ 1,400 MB (visible in JSON logs as `vram_mb`)
- [ ] `dropped_frames` counter increases during run (confirms latest-frame policy active)
- [ ] `dropped_frames / frame_count` is between 30%–60% for a 30 FPS input with 15 FPS inference

### Failure Mode Acceptance

| Scenario | Expected behavior |
|---|---|
| Source `.mp4` does not exist | `StreamHandler` logs ERROR, retries 5 times with backoff, raises `RuntimeError` after all retries exhausted |
| CUDA not available | `InferenceEngine` falls back to `device="cpu"`, logs WARNING, continues (slower) |
| VRAM OOM during inference | `torch.cuda.OutOfMemoryError` caught, logged as CRITICAL, process exits with code 2 |
| Keyboard interrupt (Ctrl+C) | `StreamHandler.stop()` called, capture thread joins cleanly within 5 seconds |
| `test.mp4` corrupted mid-file | `ret=False` from `cap.read()` triggers reconnect logic same as EOF |
| `yolo11s.pt` not downloaded | Clear `FileNotFoundError` with message: "Download with: yolo download model=yolo11s" |

### Code Quality Acceptance

- [ ] All dataclasses in `edge_ai/src/models/` have type annotations on every field
- [ ] `settings.py` has zero hardcoded paths — all are relative to `BASE_DIR`
- [ ] `StreamHandler` is independently unit-testable with a mock video source
- [ ] `InferenceEngine.run_detector()` is independently testable with a numpy array input (no StreamHandler dependency)
- [ ] `test_stream_handler.py` contains ≥ 3 tests: normal read, EOF reconnect, stopped before start

---

*Step 1 is complete when all acceptance criteria above are checkboxed green. Nothing in Step 2 (HazardAnalyzer) begins until Step 1 passes all performance + failure mode criteria on the RTX 4050 machine.*
