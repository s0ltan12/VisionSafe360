# VisionSafe 360 — Step 2 Implementation Report

> **Task**: Modular Hazard Analysis & Ergonomic Scoring Pipeline  
> **Date**: June 2025  
> **Base**: Step 1 codebase (YOLO11s + ByteTrack + StreamHandler verified)  
> **Hardware**: NVIDIA RTX 4050 Laptop 6 GB VRAM, CUDA, Python 3.13

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What Was Built](#2-what-was-built)
3. [Files Created & Modified](#3-files-created--modified)
4. [Architecture & Design Decisions](#4-architecture--design-decisions)
5. [Profile System](#5-profile-system)
6. [HazardAnalyzer — Detailed Design](#6-hazardanalyzer--detailed-design)
7. [PostureAnalyzer — Detailed Design](#7-postureanalyzer--detailed-design)
8. [Pipeline Wiring (main.py)](#8-pipeline-wiring-mainpy)
9. [Drawing & Visualization](#9-drawing--visualization)
10. [Technologies & Libraries Used](#10-technologies--libraries-used)
11. [Unit Tests](#11-unit-tests)
12. [End-to-End Validation Results](#12-end-to-end-validation-results)
13. [Run Commands](#13-run-commands)
14. [Known Limitations & Future Work](#14-known-limitations--future-work)
15. [File-by-File Reference](#15-file-by-file-reference)

---

## 1. Executive Summary

Step 2 adds **hazard detection** (PPE compliance, person–vehicle proximity, fall detection) and **ergonomic risk scoring** (simplified RULA from pose keypoints) on top of the Step 1 detection-tracking pipeline. The design is **profile-driven**: a YAML config file controls which modules run, which weights they use, and at what frame-scheduling rate — zero code changes required to switch use cases.

**Key metrics (full_suite on RTX 4050):**

| Metric | Value |
|---|---|
| VRAM (detector only) | 50 MB |
| VRAM (detector + pose) | 69 MB |
| Inference FPS | ~15 FPS |
| Pose latency (first frame) | ~41 ms |
| Pose latency (steady state) | ~8–13 ms |
| Deterministic latency P50 | ~11 ms |
| Deterministic latency P99 | ~21 ms |
| Total unit tests | 31 (all passing) |

---

## 2. What Was Built

### New Capabilities

1. **Profile System** — YAML-based per-client module configuration
2. **HazardAnalyzer** — CPU-only rule engine with 3 sub-analyzers:
   - **PPE Compliance**: region-based helmet/vest violation detection with vehicle escalation
   - **Vehicle Proximity**: 3-tier distance-based person-vehicle alerts
   - **Fall Detection**: state machine (NORMAL → CANDIDATE → CONFIRMED) with immobility verification
3. **PostureAnalyzer** — Simplified RULA ergonomic scoring from COCO-17 keypoints with EMA smoothing
4. **Pose Model Integration** — YOLO11s-pose loaded conditionally based on profile
5. **Per-sub-module Scheduling** — frame-counter modulo for independent analysis rates
6. **Hazard Visualization** — color-coded overlays, severity banners, HUD hazard count

---

## 3. Files Created & Modified

### New Files (10)

| File | Lines | Purpose |
|---|---|---|
| `src/config/profile.py` | ~175 | Profile loader: YAML → typed `ProfileConfig` |
| `profiles/full_suite.yaml` | 42 | All modules enabled |
| `profiles/fall_only.yaml` | 39 | Fall detection only |
| `profiles/proximity_only.yaml` | 39 | Proximity detection only |
| `profiles/ppe_only.yaml` | 43 | PPE compliance only |
| `src/analysis/hazard_analyzer.py` | ~503 | HazardAnalyzer (PPE + proximity + fall) |
| `src/analysis/posture_analyzer.py` | ~274 | PostureAnalyzer (RULA scoring) |
| `tests/test_hazard_analyzer.py` | ~280 | 19 unit tests for HazardAnalyzer |
| `tests/test_posture_analyzer.py` | ~200 | 8 unit tests for PostureAnalyzer |
| `weights/yolo11s-pose.pt` | 20.3 MB | YOLO11s pose estimation model |

### Modified Files (4)

| File | Changes |
|---|---|
| `src/config/settings.py` | +~50 lines: profile dir, PPE/proximity/fall/posture thresholds, scheduling constants, COCO bridge |
| `src/analysis/__init__.py` | Added exports: `HazardAnalyzer`, `PostureAnalyzer`, `classify_detection` |
| `src/utils/drawing.py` | Added `draw_hazard_events()` function, `_SEVERITY_COLOURS` dict, updated `draw_hud()` with `n_hazards` and `pose_ms` kwargs |
| `src/main.py` | Complete rewrite (~324 lines): Step 2 orchestrator with profile-driven module loading, scheduling, hazard event pipeline |

---

## 4. Architecture & Design Decisions

### Core Principles

1. **GPU ownership**: Only `InferenceEngine` (main thread) touches the GPU. `HazardAnalyzer` and `PostureAnalyzer` are pure CPU.
2. **Profile-driven**: No `if/else` branches in code for module selection — profiles control everything.
3. **Zero-copy detection reuse**: Both PPE and proximity analyzers consume the same `List[Detection]` from Model A — no duplicate inference.
4. **Pluggable weights**: Each module in the profile has a `weights` field. Empty string = use shared detector/pose output. Non-empty = future support for dedicated models.
5. **Per-track cooldown deduplication**: Same (camera, track, event_type) won't fire again within cooldown period, preventing alert spam.
6. **Memory-bounded**: All history buffers use `collections.deque(maxlen=N)` — O(1) memory per track.
7. **Stale track purging**: Tracks not seen for `FALL_TRACK_PURGE_SEC` (5s) are garbage-collected automatically.

### Data Flow

```
Video Source
    │
    ▼
StreamHandler (deque maxlen=1, latest-frame policy)
    │
    ▼
InferenceEngine.run_tracker() ──→ List[Detection]
    │                                     │
    ▼                                     ├──→ HazardAnalyzer.analyze()
InferenceEngine.run_pose()                │      ├── _ppe_check()
    │                                     │      ├── _proximity_check()
    ▼                                     │      └── _fall_detection()
pose_results ──→ PostureAnalyzer.analyze() │
    │                                     │
    ▼                                     ▼
List[HazardEvent] ◄── merge ── List[HazardEvent]
    │
    ├──→ draw_hazard_events() (visual overlay)
    ├──→ draw_hud() (top-left stats)
    ├──→ logger.warning() (HAZARD log lines)
    └──→ metrics.log_frame() (JSON telemetry)
```

### Key Data Models

```python
# Already existed in Step 1:
@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    class_id: int
    class_name: str
    track_id: Optional[int]

# New in Step 2:
class Severity(IntEnum):
    LOW = 1       # informational
    MEDIUM = 2    # actionable (e.g. vest missing)
    HIGH = 3      # urgent (e.g. near forklift without helmet)
    CRITICAL = 4  # immediate (e.g. fall, collision imminent)

@dataclass
class HazardEvent:
    event_type: str           # "no_helmet", "proximity_critical", "fall_confirmed", etc.
    severity: Severity
    camera_id: str
    timestamp: float
    frame_number: int
    track_id: Optional[int]
    bbox: Optional[Tuple]
    description: str
    metadata: dict            # event-specific data
```

---

## 5. Profile System

### Architecture

```
profiles/
├── full_suite.yaml        # All capabilities enabled (default)
├── fall_only.yaml         # Minimal: just fall detection
├── proximity_only.yaml    # Just person-vehicle proximity
└── ppe_only.yaml          # Just PPE compliance
```

### Profile YAML Schema

```yaml
profile_name: <string>
description: <string>
modules:
  detector:
    enabled: true/false
    weights: ""           # empty = settings.DETECTOR_WEIGHTS
    schedule_every_n: 1
  tracker:
    enabled: true/false
  pose:
    enabled: true/false
    weights: ""           # empty = settings.POSE_WEIGHTS
    schedule_every_n: 3
  hazard_analyzer:
    enabled: true/false
    sub_modules:
      ppe:
        enabled: true/false
        weights: ""
        schedule_every_n: 1
      proximity:
        enabled: true/false
        weights: ""
        schedule_every_n: 1
      fall:
        enabled: true/false
        weights: ""
        schedule_every_n: 1
  posture_analyzer:
    enabled: true/false
    weights: ""
    schedule_every_n: 10
```

### Profile Loader Classes (src/config/profile.py)

- **`SubModuleConfig`**: `enabled`, `weights`, `schedule_every_n`
- **`ModuleConfig`**: `enabled`, `weights`, `schedule_every_n`, `sub_modules: Dict[str, SubModuleConfig]`
- **`ProfileConfig`**: `profile_name`, `description`, `modules: Dict[str, ModuleConfig]`
  - `.is_enabled(module)` → `bool`
  - `.get_weights(module)` → `str`
  - `.get_schedule(module)` → `int`
  - `.is_sub_enabled(module, sub_module)` → `bool`
  - `.get_sub_weights(module, sub_module)` → `str`
  - `.get_sub_schedule(module, sub_module)` → `int`
- **`load_profile(name_or_path)`**: resolves by name (in `profiles/` dir), absolute path, or falls back to `_default_profile()`

### VRAM Profiles

| Profile | Pose Loaded | VRAM |
|---|---|---|
| `full_suite` | Yes | ~69 MB |
| `proximity_only` | No | ~50 MB |
| `fall_only` | No | ~50 MB |
| `ppe_only` | No | ~50 MB |

---

## 6. HazardAnalyzer — Detailed Design

**File**: `src/analysis/hazard_analyzer.py` (~503 lines)  
**Nature**: CPU-only rule engine — zero GPU calls  
**Input**: `List[Detection]` from Model A + ByteTrack  
**Output**: `List[HazardEvent]`

### 6.1 Detection Classification

`classify_detection(det)` maps each detection to a VisionSafe role:

| Input | Output |
|---|---|
| COCO class 0 or name "person" | `"person"` |
| Name "helmet_off" or "vest_off" | `"ppe_violation"` |
| Name "helmet_on" or "vest_on" | `"ppe_ok"` |
| COCO IDs {2,3,5,7} or custom IDs {5,6,7,8} | `"vehicle"` |
| Everything else | `"other"` |

This bridge handles both COCO pretrained and custom-trained weights seamlessly.

### 6.2 PPE Compliance (`_ppe_check`)

**Algorithm**:
1. For each violation detection (`helmet_off` / `vest_off`):
2. For each person, compute a **region-based containment** score:
   - **Helmet**: top 35% of person bbox (`PPE_HELMET_REGION_TOP_PCT = 0.35`)
   - **Vest**: middle 45% starting below helmet region (`PPE_VEST_REGION_MID_PCT = 0.45`)
3. Score = `max(containment, IoU)` for robustness
4. Best-matching person with score ≥ `PPE_IOU_THRESHOLD` (0.3) gets the event
5. Base severity: `no_helmet` = HIGH, `no_vest` = MEDIUM
6. **Vehicle escalation**: if person without helmet is within `PROXIMITY_WARNING_PX` (250px) of any vehicle → CRITICAL
7. Cooldown: `PPE_COOLDOWN_SEC` (30s) per `(camera_id, track_id, event_type)`

### 6.3 Vehicle Proximity (`_proximity_check`)

**Algorithm**:
1. For each (person, vehicle) pair:
2. Compute Euclidean distance between **bottom-center** points of both bboxes
3. Classify into 3 tiers:

| Distance | Severity | Event Type | Cooldown |
|---|---|---|---|
| < 80 px | CRITICAL | `proximity_critical` | 5s |
| < 150 px | HIGH | `proximity_high` | 10s |
| < 250 px | MEDIUM | `proximity_warning` | 10s |
| ≥ 250 px | — | No event | — |

4. Cooldown key: `(camera_id, person_track, vehicle_track, "proximity")`

### 6.4 Fall Detection (`_fall_detection`)

**State machine** per track_id:

```
NORMAL ──(trigger)──→ CANDIDATE ──(immobile ≥ 2s)──→ CONFIRMED
   ▲                     │                              │
   └──(aspect_ratio < 0.8)──┘                          │
   └────────────(aspect_ratio < 0.8)────────────────────┘
```

**Trigger conditions** (in NORMAL state):
1. **Aspect ratio flip**: current `w/h > 1.0` AND person was upright (`w/h < 0.8`) in recent 3 frames
2. **Rapid downward velocity**: centroid Y-delta > 15 px/frame AND `w/h > 0.8`

**Confirmation** (in CANDIDATE state):
- Elapsed ≥ `FALL_CANDIDATE_TIMEOUT` (2s)
- Immobility: centroid movement < 5 px
- Area stability: jitter < 15% relative area change
- All history buffers: `deque(maxlen=8)`

**Cooldown**: 60s per track before re-firing

**Memory management**: `_purge_stale_tracks()` removes states for tracks absent > 5s

### Helper Functions

| Function | Purpose |
|---|---|
| `_bbox_area(bbox)` | Compute bbox area |
| `_bbox_centroid(bbox)` | Center point of bbox |
| `_bbox_bottom_center(bbox)` | Bottom-center for proximity distance |
| `_bbox_iou(a, b)` | Intersection over Union |
| `_bbox_containment(inner, outer)` | Fraction of inner inside outer |
| `_euclidean(a, b)` | Euclidean distance between 2D points |

---

## 7. PostureAnalyzer — Detailed Design

**File**: `src/analysis/posture_analyzer.py` (~274 lines)  
**Nature**: CPU-only  
**Input**: Ultralytics `Results` object with `.keypoints` attribute (from YOLO11s-pose)  
**Output**: `List[HazardEvent]`

### 7.1 COCO-17 Keypoint Map

```
0: Nose        5: L.Shoulder   10: R.Wrist    15: L.Ankle
1: L.Eye       6: R.Shoulder   11: L.Hip      16: R.Ankle
2: R.Eye       7: L.Elbow      12: R.Hip
3: L.Ear       8: R.Elbow      13: L.Knee
4: R.Ear       9: L.Wrist      14: R.Knee
```

### 7.2 Processing Pipeline

1. Extract `keypoints.xy` (N, 17, 2) and `keypoints.conf` (N, 17) from pose results
2. Retrieve track IDs from `boxes.id`
3. For each person:
   - **Confidence filter**: discard keypoints with conf < 0.5
   - **Minimum requirement**: both shoulders + both hips must pass filter
   - **EMA smoothing**: `smoothed = α × current + (1-α) × previous` (α = 0.6)
   - **RULA score computation**
   - **Event emission based on score**

### 7.3 Simplified RULA Scoring

Scores range from 1 (acceptable) to 7 (investigate immediately):

| Body Part | Angle Computation | Score Contribution |
|---|---|---|
| **Trunk flexion** | shoulder→hip→knee angle, deviation from 180° | >45° → 5, >20° → 3 |
| **Neck flexion** | ear→shoulder→hip angle | >40° → 5, >20° → 3 |
| **Upper arm** | elbow→shoulder→hip angle | >90° → 5, >45° → 3 |
| **Lower arm** | wrist→elbow→shoulder angle | <60° or >100° → 3 |

Final score = `min(max_contribution, 7)`

### 7.4 Event Emission

| Condition | Event Type | Severity |
|---|---|---|
| Score ≥ 7 (immediate) | `dangerous_posture` | CRITICAL |
| Score ≥ 5 sustained > 30s | `poor_posture` | HIGH |

**Temporal tracking**: `PersonPostureState` per track_id with:
- `smoothed_kps`: EMA-smoothed keypoint positions
- `score_history`: deque of recent RULA scores
- `high_score_start`: timestamp when sustained poor posture began
- Cooldown: 60s per track_id

### 7.5 Angle Computation

```python
def _angle_between(a, b, c) -> float:
    """Angle at point b formed by rays ba and bc (degrees)."""
    ba = a - b
    bc = c - b
    cos_val = dot(ba, bc) / (norm(ba) * norm(bc) + 1e-8)
    return degrees(arccos(clip(cos_val, -1.0, 1.0)))
```

---

## 8. Pipeline Wiring (main.py)

**File**: `src/main.py` (~324 lines)  
**Role**: Step 2 orchestrator — CLI entry point, module initialization, inference loop

### Initialization Sequence

1. Parse CLI args (`--source`, `--cam-id`, `--show`, `--profile`)
2. `load_profile(args.profile)` → `ProfileConfig`
3. `StreamHandler(source, camera_id)` → video reader with deque(maxlen=1)
4. `InferenceEngine()` → YOLO11s detector + ByteTrack
5. Conditional: `engine.load_pose()` if `profile.is_enabled("pose")`
6. Conditional: `HazardAnalyzer(ppe_enabled, proximity_enabled, fall_enabled)` if profile enables it
7. Conditional: `PostureAnalyzer()` if profile enables `posture_analyzer` AND pose loaded

### Inference Loop

```
Per frame:
  1. stream.get_frame() → FrameBundle (non-blocking, latest-frame)
  2. engine.run_tracker(bundle) → (List[Detection], det_latency_ms)
  3. if pose_enabled AND frame_counter % pose_every_n == 0:
       engine.run_pose(bundle) → (pose_results, pose_latency_ms)
  4. if hazard_analyzer AND scheduled sub-modules:
       hazard_analyzer.analyze(detections, scheduling_flags) → events
  5. if posture_analyzer AND pose_results AND frame_counter % ergo_every_n == 0:
       posture_analyzer.analyze(pose_results) → events (appended)
  6. Annotate frame (detections + hazards + HUD)
  7. Display (--show) or write to output/cam_id_out.mp4
  8. Throttle to TARGET_INFER_FPS (15 Hz)
```

### Scheduling Configuration

| Sub-Module | Default Rate | At 15 FPS |
|---|---|---|
| Detector + tracker | Every frame | 15 Hz |
| Pose (Model B) | Every 3rd frame | ~5 Hz |
| PPE check | Every frame | 15 Hz |
| Proximity check | Every frame | 15 Hz |
| Fall detection | Every frame | 15 Hz |
| Posture/RULA | Every 10th frame | ~1.5 Hz |

### Signal Handling

- `SIGINT` (Ctrl-C) and `SIGTERM` → graceful shutdown
- `finally` block: stop stream, release writer, destroy windows
- CUDA OOM on detector → `sys.exit(2)`, on pose → warning + skip frame

### JSON Telemetry

Every frame emits a structured JSON line to stdout:

```json
{
  "cam_id": "cam_01",
  "frame_no": 42,
  "input_fps": 30.0,
  "inference_fps": 15.2,
  "inference_ms": 11.3,
  "n_detections": 5,
  "n_tracked": 3,
  "dropped_frames": 0,
  "vram_mb": 69.0,
  "n_hazard_events": 1,
  "hazard_types": ["proximity_critical"],
  "pose_ms": 8.5
}
```

---

## 9. Drawing & Visualization

### `draw_hazard_events(frame, events)`

Severity-based visual overlays:

| Severity | Colour (BGR) | Visual |
|---|---|---|
| CRITICAL | (0, 0, 255) Red | Semi-transparent bbox overlay + thick border |
| HIGH | (0, 128, 255) Orange | Border + label |
| MEDIUM | (0, 255, 255) Yellow | Border + label |
| LOW | (255, 255, 0) Cyan | Label only |

Additionally: bottom alert banners showing `"⚠ {event_type} — {severity}"` for each event.

### Updated `draw_hud()`

Top-left HUD overlay now includes:
- `n_hazards` count (red if > 0)
- `pose_ms` latency display

---

## 10. Technologies & Libraries Used

### Core Stack

| Technology | Version / Details | Usage |
|---|---|---|
| **Python** | 3.13 | Runtime |
| **PyTorch** | (bundled with Ultralytics) | Tensor operations, model inference |
| **Ultralytics YOLO** | v8.4.0 assets | Detection (YOLO11s) and Pose (YOLO11s-pose) models |
| **CUDA** | FP16 (`half=True`) | GPU inference on RTX 4050 |
| **OpenCV** (`cv2`) | — | Video I/O, frame annotation, imshow display |
| **NumPy** | — | Joint angle computation, keypoint array ops |

### Standard Library

| Module | Usage |
|---|---|
| `dataclasses` | Typed configs (`ProfileConfig`, `PersonFallState`, `PersonPostureState`, `HazardEvent`) |
| `collections.deque` | Bounded history buffers (velocity, aspect ratio, area, score) |
| `math` | `sqrt` for Euclidean distance |
| `enum.IntEnum` | `Severity` levels |
| `logging` | Structured logging at WARNING level for hazard events |
| `signal` | Graceful shutdown (`SIGINT`, `SIGTERM`) |
| `argparse` | CLI argument parsing |
| `time` | Timestamps, cooldown tracking, FPS throttling |
| `pathlib.Path` | Cross-platform path handling |
| `typing` | Type annotations throughout |

### External Libraries

| Library | Usage |
|---|---|
| `pyyaml` | YAML profile parsing (`yaml.safe_load`) |
| `pytest` (9.0.2) | Unit test framework |
| `unittest.mock` | `MagicMock` for mocking Ultralytics Results objects in tests |

### Model Weights

| Weight File | Size | Source | Purpose |
|---|---|---|---|
| `weights/yolo11s.pt` | ~21 MB | Ultralytics (pre-existing Step 1) | COCO 80-class detection |
| `weights/yolo11s-pose.pt` | 20.3 MB | `github.com/ultralytics/assets/releases/download/v8.4.0/` | COCO-17 keypoint pose estimation |

### Design Patterns Used

| Pattern | Where |
|---|---|
| Strategy / Profile | Profile system — switch behavior via config, not code |
| State Machine | Fall detection: NORMAL → CANDIDATE → CONFIRMED |
| Observer / Event | HazardEvent emission → multiple consumers (logger, HUD, metrics) |
| Bridge | `classify_detection()` adapts COCO ↔ custom class IDs |
| Template Method | `analyze()` → delegates to scheduled sub-analyzers |
| EMA Filter | PostureAnalyzer temporal keypoint smoothing |

---

## 11. Unit Tests

### Test Suite Summary

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_hazard_analyzer.py` | 19 | PPE (6), Proximity (5), Fall (3), classify_detection (5) |
| `tests/test_posture_analyzer.py` | 8 | Score computation, events, confidence filter, EMA, angles |
| Step 1 regression tests | 4 | InferenceEngine, StreamHandler, face blurring, etc. |
| **Total** | **31** | **All passing** ✅ |

### HazardAnalyzer Tests (19)

**PPE Check (6)**:
- `test_helmet_detected` — correctly associates helmet_off violation to person
- `test_vest_detected` — correctly associates vest_off violation to person
- `test_cooldown_suppresses_duplicate` — same event within 30s is suppressed
- `test_cooldown_expired_fires_again` — event fires after cooldown expires
- `test_orphan_violation_discarded` — violation not matching any person is ignored
- `test_escalation_near_vehicle` — no_helmet escalates to CRITICAL when near vehicle

**Proximity Check (5)**:
- `test_critical_close_range` — distance < 80px → CRITICAL
- `test_high_range` — distance 80–150px → HIGH
- `test_safe_distance` — distance ≥ 250px → no event
- `test_coco_vehicle_detected` — COCO car (class 2) recognized as vehicle
- `test_cooldown` — proximity cooldown suppresses repeated events

**Fall Detection (3)**:
- `test_candidate_to_confirmed` — state machine progresses NORMAL → CANDIDATE → CONFIRMED
- `test_recovery_resets` — person standing back up resets to NORMAL
- `test_stale_track_purged` — track absent > 5s is garbage-collected

**classify_detection (5)**:
- person, car, truck, helmet_off, unknown class

### PostureAnalyzer Tests (8)

- `test_good_posture_no_event` — score < 5 produces no event
- `test_poor_posture_immediate_critical` — score ≥ 7 produces immediate CRITICAL event
- `test_low_confidence_filtered` — keypoints below 0.5 confidence are skipped
- `test_ema_smoothing_effect` — verifies EMA updates smoothed keypoints
- `test_none_pose_results` — gracefully handles None input
- `test_angle_right_angle` — 90° angle computation
- `test_angle_straight` — 180° angle computation
- `test_angle_zero` — degenerate case handling

---

## 12. End-to-End Validation Results

### Test 1: `proximity_only` profile (no pose model)

```
Command: python src/main.py --source test_video.mp4 --cam-id cam_01 --profile proximity_only
```

| Metric | Result |
|---|---|
| Frames processed | 188 |
| VRAM | 50 MB (detector only) |
| pose_ms | 0.0 (pose disabled) |
| Shutdown | Clean (Ctrl-C signal) |
| JSON fields present | `n_hazard_events`, `hazard_types`, `pose_ms` ✅ |

### Test 2: `full_suite` profile (detector + pose)

```
Command: python src/main.py --source test_video.mp4 --cam-id cam_01 --profile full_suite
```

| Metric | Result |
|---|---|
| Frames processed | 261 |
| VRAM | 69 MB (detector 50 + pose ~19) |
| pose_ms (first frame) | ~41 ms |
| pose_ms (steady state) | ~8–13 ms |
| Inference FPS | ~15 |
| Shutdown | Clean |

### Note on `n_hazard_events: 0`

All test videos showed zero hazard events. This is **expected** — the COCO pretrained detector:
- Does not produce `helmet_off` / `vest_off` classes (PPE requires custom weights)
- Proximity events depend on person + vehicle being in close pixel proximity
- Fall events require specific spatial/temporal conditions (aspect ratio flip + immobility)

Real hazard events will fire when:
1. Custom PPE weights are swapped in (replaces COCO detector)
2. Video footage contains the specific hazard scenarios

---

## 13. Run Commands

### Basic Run

```bash
cd edge_ai

# Full suite (all modules)
python src/main.py --source path/to/video.mp4 --cam-id cam_01

# With live display window
python src/main.py --source path/to/video.mp4 --cam-id cam_01 --show

# Specific profile
python src/main.py --source path/to/video.mp4 --cam-id cam_01 --profile proximity_only
python src/main.py --source path/to/video.mp4 --cam-id cam_01 --profile fall_only
python src/main.py --source path/to/video.mp4 --cam-id cam_01 --profile ppe_only
```

### Run Unit Tests

```bash
cd edge_ai
python -m pytest tests/ -v
```

### Available CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--source` | (required) | Path to .mp4 file or RTSP URL |
| `--cam-id` | `cam_01` | Logical camera identifier |
| `--show` | `false` | Display annotated frames in OpenCV window |
| `--profile` | `full_suite` | Profile name or YAML file path |

---

## 14. Known Limitations & Future Work

### Current Limitations

1. **COCO weights lack PPE classes**: No `helmet_off`/`vest_off` detections with pretrained YOLO11s. Custom Model A weights are needed for real PPE events.
2. **Pixel-distance proximity**: Proximity uses pixel distances, not real-world metric distances. Accuracy depends on camera angle and resolution.
3. **Single-camera**: `main.py` runs one camera. Multi-camera requires launching multiple processes or a future orchestrator.
4. **No backend integration yet**: Hazard events are logged/displayed but not POSTed to the backend API.
5. **Simplified RULA**: The ergonomic scoring uses a subset of the full RULA assessment (no wrist rotation, no load/force tables).
6. **Workspace path apostrophe**: The workspace path contains an apostrophe which causes PyTorch C++ reader failures with absolute paths. Mitigated by `os.path.relpath()` in `InferenceEngine._resolve_weights()`.

### Future Steps

- **Step 3**: Alert Manager, FCM push notifications, siren controller
- **Step 4**: Backend API integration (POST hazard events, camera registration)
- **Step 5**: Dashboard WebSocket streaming, real-time analytics
- Replace COCO weights with custom-trained PPE model
- Add depth estimation or camera calibration for metric proximity
- Multi-camera process pool with shared GPU

---

## 15. File-by-File Reference

### Constants & Config

```
src/config/settings.py      — ~115 lines — All numeric constants, paths, thresholds
src/config/profile.py       — ~175 lines — YAML→ProfileConfig loader with dataclasses
```

### YAML Profiles

```
profiles/full_suite.yaml    — All modules ON, default production profile
profiles/fall_only.yaml     — Only detector + tracker + fall detection
profiles/proximity_only.yaml— Only detector + tracker + proximity
profiles/ppe_only.yaml      — Only detector + tracker + PPE compliance
```

### Analysis Modules

```
src/analysis/__init__.py    — Package exports
src/analysis/hazard_analyzer.py — ~503 lines — PPE + proximity + fall rule engine
src/analysis/posture_analyzer.py — ~274 lines — RULA scoring from COCO-17 keypoints
```

### Pipeline & Visualization

```
src/main.py                 — ~324 lines — Step 2 orchestrator, CLI, inference loop
src/utils/drawing.py        — draw_hazard_events(), updated draw_hud()
```

### Model Weights

```
weights/yolo11s.pt          — ~21 MB — COCO 80-class detector (Step 1)
weights/yolo11s-pose.pt     — 20.3 MB — COCO-17 keypoint pose (Step 2)
```

### Unit Tests

```
tests/test_hazard_analyzer.py  — ~280 lines — 19 tests
tests/test_posture_analyzer.py — ~200 lines — 8 tests
```

---

## Settings Constants Added (Complete List)

```python
# Profile directory
PROFILES_DIR = BASE_DIR / "profiles"

# Model weight paths
POSE_WEIGHTS = BASE_DIR / "weights" / "yolo11s-pose.pt"
POSE_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "yolov8s-pose.pt"
PPE_WEIGHTS = ""
FALL_WEIGHTS = ""
PROXIMITY_WEIGHTS = ""
ERGONOMICS_WEIGHTS = ""

# COCO compatibility bridge
COCO_PERSON_ID = 0
COCO_VEHICLE_IDS = {2, 3, 5, 7}
COCO_VEHICLE_NAMES = {"car", "motorcycle", "bus", "truck"}

# Scheduling
POSE_EVERY_N = 3
PPE_EVERY_N = 1
PROXIMITY_EVERY_N = 1
FALL_EVERY_N = 1
ERGONOMIC_EVERY_N = 10

# PPE thresholds
PPE_IOU_THRESHOLD = 0.3
PPE_HELMET_REGION_TOP_PCT = 0.35
PPE_VEST_REGION_MID_PCT = 0.45
PPE_COOLDOWN_SEC = 30.0

# Proximity thresholds (pixels)
PROXIMITY_CRITICAL_PX = 80
PROXIMITY_HIGH_PX = 150
PROXIMITY_WARNING_PX = 250
PROXIMITY_COOLDOWN_CRITICAL = 5.0
PROXIMITY_COOLDOWN_OTHER = 10.0

# Fall detection
FALL_ASPECT_RATIO_THRESHOLD = 1.0
FALL_VELOCITY_THRESHOLD = 15.0
FALL_VELOCITY_WINDOW = 8
FALL_CANDIDATE_TIMEOUT = 2.0
FALL_IMMOBILITY_THRESHOLD = 5.0
FALL_AREA_JITTER_THRESHOLD = 0.15
FALL_COOLDOWN_SEC = 60.0
FALL_TRACK_PURGE_SEC = 5.0

# Posture/ergonomics
POSTURE_KEYPOINT_CONF_MIN = 0.5
POSTURE_EMA_ALPHA = 0.6
POSTURE_SUSTAINED_THRESHOLD = 30.0
POSTURE_COOLDOWN_SEC = 60.0
TEMPORAL_SMOOTH_WINDOW = 5
ERGONOMIC_SCORE_WINDOW = 90
```

---

*End of Step 2 Implementation Report*
