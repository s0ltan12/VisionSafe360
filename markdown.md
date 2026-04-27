# VisionSafe 360 — Complete Technical Analysis & Production Roadmap

> **Prepared by:** Senior AI Systems Architect
> **Date:** March 1, 2026
> **Status:** Pre-implementation — scaffold exists, zero code written
> **Classification:** Internal Technical Document

---

## EXECUTIVE SUMMARY

VisionSafe 360 is a real-time industrial workplace safety monitoring system that ingests live CCTV/RTSP video streams, runs four independent AI models in a shared inference pipeline, classifies hazard events by severity, and delivers multi-channel alerts (mobile push, WebSocket dashboard, physical siren) while logging all events to a central FastAPI backend.

**The system solves four distinct problems simultaneously:**

| Problem | AI Model | Urgency |
|---|---|---|
| PPE non-compliance (helmet/vest) | YOLOv8s object detection | High |
| Vehicle-pedestrian proximity | YOLOv8s + ByteTrack + homography | Critical |
| Fall detection (collapse, slip) | YOLOv8s-Pose + temporal state machine | Critical |
| Ergonomic overload (RULA/REBA) | YOLOv8s-Pose + scoring algorithm | Medium |

**Current State:** The project is fully documented to specification level. All folder structures and Python module stubs are created. All actual `.py` files are empty. `docker-compose.yml` is empty. `PROJECT_HANDOVER.md` is empty. This is a greenfield codebase with expert-level documentation — everything must be built.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Ultralytics YOLOv8, OpenCV, ByteTrack, Firebase FCM, Dash (dashboard), Docker, NVIDIA Jetson Orin Nano (production target), laptop/desktop CUDA GPU (development phase).

---

## SECTION 1 — TECHNICAL ARCHITECTURE BREAKDOWN

### 1.1 System Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FACTORY FLOOR                                │
│  [CCTV Cam 1]  [CCTV Cam 2]  [CCTV Cam N]  ←── RTSP Streams         │
└────────────────────────┬────────────────────────────────────────────┘
                         │ RTSP
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EDGE AI NODE (Jetson Orin Nano)                  │
│                                                                     │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐    │
│  │ StreamHandler│───▶│  InferenceEngine│───▶│  HazardAnalyzer  │    │
│  │ (Team 1)    │    │  (Team 2)        │    │  (Team 3)        │    │
│  │ RTSP → frame│    │  4 YOLO models   │    │  Rules + Scoring │    │
│  └─────────────┘    └──────────────────┘    └────────┬─────────┘    │
│                                                      │              │
│                     ┌────────────────────────────────▼──────────-┐  │
│                     │          AlertManager (Team 4)             │  │
│                     │  FaceBlurrer → FCM/Siren/WS → BackendClient│  │
│                     └────────────────────────────────────────────┘  │
└───────────────────────────────────────────┬─────────────────────────┘
                                            │ HTTP/WebSocket
                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     CLOUD/LOCAL BACKEND (FastAPI)                   │
│  [Auth] [Cameras API] [Incidents API] [Ergonomics API] [Analytics]  │
│  [PostgreSQL] [WebSocket Hub] [Snapshot Storage]                    │
└─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│               MONITORING SURFACES                                   │
│   [Dash Dashboard] ← WebSocket          [Mobile App] ← FCM Push     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Module-by-Module Breakdown

#### Team 1 — Streaming & Orchestration (`edge_ai/src/streaming/`, `edge_ai/src/main.py`)

**Role:** The entry point of all processing. Manages RTSP stream connections, handles reconnection logic, dequeues frames at target FPS, and dispatches frames to the inference engine. Runs one thread (or process) per camera.

**Key responsibilities:**
- RTSP reconnection with exponential backoff (up to 5 retries)
- Per-camera frame buffer with configurable skip rate (e.g., process every 2nd frame at 30 FPS live → 15 FPS effective)
- Frame object: carries `(numpy_frame, camera_id, timestamp, frame_number)`
- Graceful shutdown on SIGTERM (drain queues, log final state)
- Health check HTTP endpoint for monitoring

**Critical design decision:** Frame queues must be bounded (maxsize=2–5). An unbounded queue will cause memory overflow within minutes on high-FPS streams.

---

#### Team 2 — Detection & Inference (`edge_ai/src/config/inference/`)

**Role:** Manages the four YOLO model instances, runs inference on incoming frames, and returns structured detection results.

**Architecture reality check:** Per the specs, Models 1 and 2 are independent YOLOv8s detectors (different class sets). Model 3 uses YOLOv8s-Pose. Model 4 reuses Model 3's pose output (zero additional inference). In practice, this means:

| Inference call | Models active per frame | Approx latency |
|---|---|---|
| PPE check | YOLOv8s (5 PPE classes) | ~30–40 ms |
| Vehicle proximity | YOLOv8s (5 vehicle classes) + ByteTrack | ~35–50 ms |
| Fall + Ergonomics | YOLOv8s-Pose (shared) | ~35–40 ms |

Running all four in sequential single-threaded mode: ~100–130 ms/frame per camera.
Running PPE + Vehicle detection in parallel (two threads, separate GPU streams): ~55–70 ms bottleneck.

**Output contract:**
```python
@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[int,int,int,int]  # x1,y1,x2,y2
    track_id: Optional[int]       # from ByteTrack

@dataclass
class PoseResult:
    person_id: int
    keypoints: np.ndarray  # shape (17, 3) — x, y, confidence
    bbox: tuple[int,int,int,int]
```

---

#### Team 3 — Analysis & Classification (`edge_ai/src/analysis/`)

**Role:** The analytical brain. Takes `List[Detection]` + `List[PoseResult]` and determines if any hazard conditions are met, then constructs `HazardEvent` objects with severity classification.

**Four analyzers in one module:**

1. **PPE Violation Analyzer** — For each detected person, check if `helmet_off` or `vest_off` is detected in their bounding box region.
2. **Proximity Analyzer** — Load per-camera homography matrix, transform bottom-center of person and vehicle bounding boxes to real-world coordinates, compute Euclidean distance, classify: SAFE/WARNING/DANGER/CRITICAL.
3. **Fall State Machine** — Per tracked person: compute aspect ratio, hip height normalized, vertical centroid velocity. If criteria met → FALL_CANDIDATE. If candidate + immobile >3s → FALL_CONFIRMED.
4. **Ergonomic Scorer** — From pose keypoints, compute joint angles using law of cosines, look up RULA/REBA tables, compute scores, maintain temporal window for sustained exposure tracking.

**Cooldown mechanism:** Each hazard type per camera has a configurable cooldown (default: 30 seconds for PPE, 5 seconds for Fall/Proximity CRITICAL). Prevents alert flooding.

**Severity Enum:**
```python
class Severity(Enum):
    LOW = 1       # PPE warning, RULA 3-4
    MEDIUM = 2    # PPE violation, REBA medium
    HIGH = 3      # Proximity WARNING, sustained ergonomic
    CRITICAL = 4  # Fall, Proximity DANGER/CRITICAL, REBA ≥11
```

---

#### Team 4 — Alerts & Integration (`edge_ai/src/alerts/`, `edge_ai/src/integration/`)

**Role:** Routes `HazardEvent` objects to appropriate output channels based on severity policy. Also handles face privacy blurring and backend API communication.

**Routing policy:**

| Severity | Channels |
|---|---|
| LOW | Backend log only |
| MEDIUM | Backend log + WebSocket dashboard update |
| HIGH | Backend log + WebSocket + FCM push |
| CRITICAL | Backend log + WebSocket + FCM push + Siren trigger |

**BackendClient** is the HTTP bridge from edge to cloud:
- JWT-authenticated (edge device has a service account token)
- `POST /incidents` for all hazard events
- `POST /ergonomic-records` for REBA/RULA shift data
- Stores snapshot (blurred frame JPEG) as multipart upload
- Offline queue: when backend unreachable, persist to local SQLite, flush on reconnect (store-and-forward)

**FaceBlurrer** applies Gaussian blur on all detected face regions before any frame is stored or transmitted — GDPR/privacy compliance built into the pipeline.

---

### 1.3 Backend Architecture (`backend/`)

FastAPI application with the following route structure:

| Route | Method | Purpose |
|---|---|---|
| `/auth/login` | POST | JWT token issuance |
| `/cameras` | GET/POST/PUT/DELETE | Camera CRUD |
| `/incidents` | GET/POST | Event log, supports filter/pagination |
| `/ergonomics` | GET/POST | RULA/REBA records |
| `/analytics` | GET | Aggregated metrics (violation rates, heatmaps) |
| `/ws/alerts` | WebSocket | Real-time alert stream to dashboard |
| `/users` | CRUD | Admin user management |

**Database:** PostgreSQL via SQLAlchemy async ORM. Models: `User`, `Camera`, `Incident`, `ErgonomicRecord`.

---

### 1.4 Dashboard Architecture (`dashboard/`)

Plotly Dash application with 4 pages:
- **Live Streams** — Video player + real-time detection overlays via WebSocket
- **Incidents** — Filterable incident log table + severity timeline chart
- **Analytics** — Violation heatmaps, trend lines, worker risk profiles
- **Camera Management** — Camera registration, calibration wizard, health status

---

### 1.5 Component Dependency Graph

```
StreamHandler
    └──► InferenceEngine
              ├──► [PPE Model — YOLOv8s weights]
              ├──► [Vehicle Model — YOLOv8s weights]
              └──► [Pose Model — YOLOv8s-Pose weights]
                        │
                        ▼
                  HazardAnalyzer ◄── [homography JSON per camera]
                  PostureAnalyzer
                        │
                        ▼
                  AlertManager ◄── [severity policy config]
                  FaceBlurrer
                        │
                  ┌─────┼─────┐
                  ▼     ▼     ▼
              FCMService  SirenController  BackendClient
                                               │
                                          FastAPI Backend
                                               │
                                        PostgreSQL Database
                                               │
                                          Dash Dashboard
```

---

## SECTION 2 — AI MODEL STRATEGY

### 2.1 Model Architecture Decisions (Final)

| Model | Architecture | Why |
|---|---|---|
| PPE Detection | **YOLOv8s**, 5 classes | 90–92% mAP@0.5, 50–65 FPS on Jetson, 22 MB, Ultralytics ecosystem |
| Vehicle Proximity | **YOLOv8s**, 5 classes (separate weights) | COCO pre-training includes car/truck, fine-tune for forklift |
| Fall Detection | **YOLOv8s-Pose** + rule-based state machine | Integrated detection + 17 keypoints, ~35 ms, shared with Model 4 |
| Ergonomic Assessment | **YOLOv8s-Pose** (shared with Model 3) + algorithmic RULA/REBA | Zero additional inference cost |

---

### 2.2 Why NOT Alternative Architectures

| Rejected | Reason |
|---|---|
| RT-DETR | 2–3x compute cost for 1–2% mAP gain — unacceptable for edge multi-model pipeline |
| SlowFast 3D CNN (fall) | 200 ms latency, incompatible with real-time constraint |
| ST-GCN (fall) | Requires trained graph model, 100 ms, overkill for V1 |
| MiDaS depth (proximity) | ±1.5 m accuracy — too imprecise for safety-critical decisions |
| Stereo vision (proximity) | Requires hardware modification of existing CCTV |
| Unified single model (all 4 tasks) | Creates blocking development dependency between teams; deferred to future optimization |

---

### 2.3 Training Strategy Per Model

#### Model 1 — PPE Detection

**Data pipeline:**
```
SHEL5K (5K) + Hard Hat Workers/Kaggle (7K) + CHV Dataset (10K) + Pictor-v3 (2.5K)
→ De-duplicate by perceptual hash
→ Relabel to 5-class schema (person, helmet_on, helmet_off, vest_on, vest_off)
→ Class-aware sampling to achieve 20-30% violation class ratio
→ Augmentation pipeline: HSV, perspective, mosaic, motion blur, JPEG compression
→ Hard negative mining after epoch 50
→ 8K train / 2K val / 1K test split
```

**Training stages:**
1. Freeze backbone, train head only — 20 epochs, LR 1e-3
2. Unfreeze all, cosine annealing — 80–100 epochs, LR 1e-4 → 1e-6
3. Domain adaptation on site-specific frames — 10 epochs, LR 1e-5

**Loss modification:** Increase `cls` loss weight from 0.5 → 0.7 (classification matters more than pixel-perfect boxes for violation decisions).

**Targets:** mAP@0.5 ≥ 91%, Recall(`helmet_off`) ≥ 93%, inference latency < 40 ms.

---

#### Model 2 — Vehicle Proximity

**Data pipeline:**
```
COCO person class (64K filtered) + BDD100K vehicles + KITTI + Open Images forklift (~2K)
→ Custom forklift footage collection (mandatory — critical gap)
→ Augment proximity pairs: paste persons near vehicles at controlled distances
→ 6K detection + 4K proximity scenarios / 2K val / 1K test
```

**Homography calibration workflow** (per-camera, one-time setup):
```python
# 4 ground reference points (tape measure on factory floor)
src_points = np.float32([[px1,py1],[px2,py2],[px3,py3],[px4,py4]])  # pixel coords
dst_points = np.float32([[x1,y1],[x2,y2],[x3,y3],[x4,y4]])          # real-world meters
H = cv2.findHomography(src_points, dst_points)[0]
# Validation: known 3m distance between painted marks → verify computed = 3.0±0.5
```

**ByteTrack integration:** Maintains person and vehicle track IDs across frames. Proximity alert requires DANGER status in ≥ 2 consecutive frames to eliminate single-frame false positives.

---

#### Model 3 — Fall Detection

**Architecture:** YOLOv8s-Pose inherits from COCO pre-trained weights. The fall logic is NOT a trained classifier in V1 — it is a rule engine with calibrated thresholds.

**State machine thresholds (defaults — calibrate per deployment):**

| Feature | Threshold | Calibration factor |
|---|---|---|
| Bounding box aspect ratio | > 1.15 | Camera angle dependent |
| Normalized hip Y-coordinate | < 0.30 of max tracked height | Body size dependent |
| Vertical centroid velocity | > 25 px/frame @ 15 FPS | FPS/resolution dependent |
| Torso angle from vertical | > 65° | Camera tilt dependent |
| Post-fall immobility duration | > 3.0 seconds | Risk zone dependent |

**V2 roadmap:** After 3 months of deployment data, train a 2-layer LSTM on extracted pose sequences to replace the rule engine. Expected accuracy improvement: 88–92% → 94–97%.

---

#### Model 4 — Ergonomic Risk Assessment

**Pure algorithm, zero ML training required.** Runs on the same pose keypoints as Model 3.

**Angle computation pipeline:**
```python
def compute_trunk_flexion(pose_kp):
    mid_shoulder = (pose_kp[5][:2] + pose_kp[6][:2]) / 2
    mid_hip = (pose_kp[11][:2] + pose_kp[12][:2]) / 2
    trunk_vector = mid_shoulder - mid_hip
    vertical = np.array([0, -1])  # upward in image coords
    cos_angle = np.dot(trunk_vector, vertical) / (np.linalg.norm(trunk_vector) + 1e-8)
    return np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
```

Compute all 13 required angles → look up RULA Group A table → look up RULA Group B table → look up Table C → final score 1–7.

**Temporal aggregation:** 10-second sliding window of scores. Report moving average. Alert trigger: RULA ≥ 5 sustained for > 5 minutes OR instantaneous RULA = 7.

---

### 2.4 Dataset Summary

| Model | Total images/sequences | Key public datasets | Critical gap |
|---|---|---|---|
| PPE | ~12,000 images | SHEL5K, Hard Hat Workers, CHV, Pictor-v3 | Site-specific domain adaptation |
| Vehicle | ~13,000 images | COCO, BDD100K, KITTI, Open Images | Forklift-specific footage — must collect on site |
| Fall | ~3,300 video sequences | UR Fall, Le2i, UP-Fall, NTU RGB+D | Industrial simulated falls |
| Ergonomic | ~1,900 validation images | COCO (pose) | Ground-truth RULA/REBA expert assessments |

---

### 2.5 Evaluation Metrics Per Model

| Model | Primary metric | Secondary | Operational |
|---|---|---|---|
| PPE | mAP@0.5 ≥ 91% | Recall(`helmet_off`) ≥ 93% | False alarms < 2/hr/camera |
| Vehicle | mAP@0.5 ≥ 91%, Distance MAE ≤ 0.8 m | Proximity acc ≥ 88% | Missed danger < 5% |
| Fall | Sensitivity ≥ 95% (recall) | Specificity ≥ 97% | Detection latency < 5 s |
| Ergonomic | Joint angle MAE < 8° | RULA ±1 match ≥ 85% | Sustained risk detection ≥ 90% |

---

## SECTION 3 — DEVELOPMENT ROADMAP

### Phase 0 — Infrastructure Setup (Week 1–2)

**Goal:** Every team member can run code. Environments stable.

**Deliverables:**
- [ ] `docker-compose.yml` — PostgreSQL + FastAPI + Dash services
- [ ] `backend/requirements.txt` — FastAPI, SQLAlchemy, alembic, pydantic, python-jose
- [ ] `edge_ai/requirements.txt` — ultralytics, opencv-python, torch, bytetrack, firebase-admin
- [ ] `dashboard/requirements.txt` — dash, plotly, requests
- [ ] Shared Git branching strategy: `main` / `dev` / `feature/*` / `model/*`
- [ ] Pre-commit hooks: black formatter, ruff linter, pytest gate
- [ ] Backend Alembic migrations: `User`, `Camera`, `Incident`, `ErgonomicRecord` tables
- [ ] `.env.example` with all required environment variables documented

**Risks:** Python version conflicts between teams. Mitigation: standardize on Python 3.10, pin all dependency versions in requirements.txt from day one.

---

### Phase 1 — Backend API Foundation (Week 2–4)

**Goal:** A working REST API that edge and dashboard can both talk to.

**Deliverables:**
- [ ] `backend/app/config/settings.py` — env-based config with pydantic-settings
- [ ] `backend/app/config/database.py` — async SQLAlchemy engine + session factory
- [ ] All 4 SQLAlchemy models fully implemented (User, Camera, Incident, ErgonomicRecord)
- [ ] All Pydantic schemas (request/response validation)
- [ ] Auth service: password hashing (bcrypt), JWT issuance/validation
- [ ] Full CRUD routes for all entities
- [ ] WebSocket hub: authenticated WS endpoint that broadcasts `HazardEvent` JSON to connected clients
- [ ] Unit tests: ≥ 80% coverage on services layer
- [ ] Health check endpoint: `GET /health` returns server + DB status

**Milestone gate:** Postman/HTTPie confirms all API endpoints work end-to-end with a real PostgreSQL instance.

---

### Phase 2 — Edge AI Core Pipeline (Week 3–7, parallel with Phase 1)

**Goal:** Frames flow from RTSP → inference → hazard classification → alert with real video input.

#### Sub-phase 2A: Streaming (Team 1, Week 3–4)
- [ ] `StreamHandler` class: OpenCV `VideoCapture` with RTSP, threaded frame reader, bounded queue, reconnection logic
- [ ] `main.py` orchestrator: spawn one `StreamHandler` per camera URL, dispatch to inference engine
- [ ] Settings: configurable FPS cap, frame skip, camera URLs list
- [ ] Unit tests: mock RTSP source, verify frame object schema, verify reconnection attempts

#### Sub-phase 2B: Inference Engine (Team 2, Week 3–5)
- [ ] `InferenceEngine` class with deferred model loading (loads on first use, not at import)
- [ ] `load_model(path, device)` — supports CPU and CUDA auto-detection
- [ ] `run_ppe(frame)` → `List[Detection]`
- [ ] `run_vehicle(frame)` → `List[Detection]`
- [ ] `run_pose(frame)` → `List[PoseResult]`
- [ ] Model warmup on startup (pass dummy frames)
- [ ] Unit tests with pre-recorded test frames (no live camera needed)

> **Note for Team 2:** Use placeholder/stub model weights during development (run with random-weight YOLO or download a COCO-pretrained YOLOv8s as a functional placeholder). Replace with trained weights when ML training completes.

#### Sub-phase 2C: Analysis (Team 3, Week 4–6)
- [ ] `HazardAnalyzer.analyze(detections, poses, camera_id)` → `List[HazardEvent]`
- [ ] PPE violation logic: associate `helmet_off`/`vest_off` detections with person bounding boxes using IoU
- [ ] Proximity logic: load homography from JSON, transform coordinates, compute distances, classify risk level
- [ ] Fall state machine: per track_id state persistence, threshold logic, 3-second immobility timer
- [ ] `PostureAnalyzer.compute_angles(pose)` and `calculate_rula()`, `calculate_reba()` — implement full scoring tables
- [ ] Cooldown mechanism: `dict[camera_id + hazard_type] → last_alert_timestamp`
- [ ] Unit tests: hardcoded detection inputs → verify expected HazardEvent outputs

#### Sub-phase 2D: Alerts & Integration (Team 4, Week 5–7)
- [ ] `AlertManager.process_event(event)` → routes by severity
- [ ] `FaceBlurrer.blur_faces(frame)` using OpenCV DNN face detector
- [ ] `FCMService.send_push(token, payload)` — Firebase Admin SDK integration
- [ ] `SirenController.trigger_alarm()` — GPIO real + mock mode (env variable toggle)
- [ ] `BackendClient` — aiohttp async HTTP client, JWT header, POST /incidents, retry with exponential backoff, local SQLite offline queue
- [ ] Unit tests: mock HTTP calls, verify routing table, verify offline queue flush

**Milestone gate Phase 2:** Run `main.py` against a sample video file (MP4), see detection overlays drawn on output frames, see `HazardEvent` objects printed to stdout, see `POST /incidents` calls reaching the backend.

---

### Phase 3 — ML Model Training (Week 4–10, parallel tracks)

**Goal:** Replace COCO-pretrained placeholder weights with production-quality fine-tuned models.

#### ML Track 1 — PPE Model (1 team member, Week 4–8)

| Week | Task |
|---|---|
| 4–5 | Download + clean SHEL5K, Hard Hat Workers, CHV datasets. Relabel to 5-class schema using CVAT or Roboflow. |
| 5–6 | Stage 1 training: frozen backbone, 20 epochs. Evaluate on validation set. |
| 6–7 | Stage 2 training: full fine-tune, 100 epochs with early stopping. Hard negative mining pass. |
| 7–8 | Stage 3: domain adaptation on site footage. Evaluate final metrics. Export to ONNX. |

**Go/No-Go criteria:** mAP@0.5 ≥ 88%, Recall(`helmet_off`) ≥ 90%

#### ML Track 2 — Vehicle Proximity Model (1 team member, Week 4–8)

| Week | Task |
|---|---|
| 4–5 | Filter BDD100K + KITTI vehicle classes. Source Open Images forklift subset. Collect 200+ custom forklift images. |
| 5–6 | Train detection model (COCO pre-trained → fine-tune), evaluate vehicle mAP. |
| 6–7 | Implement + validate homography calibration tool. Measure distance MAE on known geometry. |
| 7–8 | Add ByteTrack, validate tracking MOTA, deploy proximity alert logic end-to-end. |

**Go/No-Go criteria:** mAP@0.5 ≥ 88%, Distance MAE ≤ 1.2 m

#### ML Track 3 — Fall Detection Pose Model (1 team member, Week 4–7)

| Week | Task |
|---|---|
| 4–5 | Download UR Fall, Le2i, UP-Fall datasets. Extract pose sequences using YOLOv8s-Pose (COCO weights). |
| 5–6 | Calibrate rule-engine thresholds on validation sequences. Measure sensitivity/specificity. |
| 6–7 | Record 100+ simulated fall events on-site. Fine-tune thresholds. Validate false alarm rate per day. |

**Go/No-Go criteria:** Fall Sensitivity ≥ 92%, False alarms ≤ 8/camera/day

#### ML Track 4 — Ergonomic Scorer (1 team member, Week 4–6)

| Week | Task |
|---|---|
| 4–5 | Implement full RULA algorithm (Group A, B, C tables). Unit test all table lookups with known cases from McAtamney & Corlett (1993). |
| 5–6 | Implement REBA algorithm. Validate against 20 ground-truth expert assessments. Implement temporal aggregation. |

**Go/No-Go criteria:** RULA score ±1 match ≥ 80% vs. expert assessments.

---

### Phase 4 — Dashboard & Mobile Integration (Week 6–9)

**Goal:** Operators can monitor the factory from a browser and mobile device.

**Deliverables:**
- [ ] Dash app layout with sidebar navigation (`dashboard/components/sidebar.py`)
- [ ] Live stream page: video frame display via WebSocket JPEG stream + detection overlay
- [ ] Incidents page: DataTable with severity filter, camera filter, time range; incident detail modal with blurred snapshot
- [ ] Analytics page: violation rate time-series chart, top-risk workers bar chart, violation heatmap overlay on camera plan
- [ ] Camera management page: add/edit camera form, calibration wizard, live health status
- [ ] Mobile app: notifications working via FCM (basic React Native / Flutter shell app)
- [ ] End-to-end WebSocket test: incident triggered on edge → visible in dashboard within 1 second

---

### Phase 5 — Integration, Testing & Hardening (Week 9–12)

**Goal:** The complete system runs reliably for 8+ hours without failure on real factory video.

**Testing strategy:**

| Level | What | Tools | Coverage target |
|---|---|---|---|
| Unit | Each class in isolation | pytest, unittest.mock | ≥ 80% on services |
| Integration | Edge pipeline with real video | pytest + video fixtures | All hazard types triggered |
| API contract | Backend endpoints | pytest + httpx | All routes 2xx + 4xx |
| Performance | Inference latency per camera | `time.perf_counter`, profiler | < 100 ms/frame |
| Stress | 4 cameras × 8 hours | continuous video loop | No memory leak, no crash |
| Real-world | On-site controlled scenarios | Human observers | ≥ 90% detection rate for staged events |

**Validation scenarios (controllable real-world tests):**
1. Volunteer removes helmet → system alerts within 3 seconds
2. Forklift enters 2m pedestrian zone → DANGER alert triggered
3. Volunteer simulates slip fall → alert within 5 seconds, no false alarm from bending
4. Volunteer maintains deep forward bend for 6 minutes → ergonomic WARNING generated
5. Edge node loses network connection → events queued locally, transmitted on reconnect
6. RTSP camera disconnects → stream handler reconnects within 30 seconds

---

### Phase 6 — Edge Deployment & Optimization (Week 12–14)

**Goal:** Export models to TensorRT FP16, deploy on Jetson Orin Nano, validate latency targets.

**Steps:**
```bash
# Export each model
yolo export model=ppe_v1.pt format=engine half=True device=0  # TensorRT FP16
yolo export model=vehicle_v1.pt format=engine half=True device=0
yolo export model=pose_v1.pt format=engine half=True device=0

# Validate latency on Jetson
python benchmark.py --models all --source factory_sample.mp4 --cameras 4
# Target: ≤ 100ms per frame across all 4 models, 4 cameras
```

**Multi-camera scheduling:** Implement adaptive frame processing — when no vehicles detected in a frame, reduce vehicle model inference to every 5th frame. When person + vehicle co-present, force every-frame processing.

---

## SECTION 4 — RISK & MITIGATION

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Forklift training data gap** | HIGH | CRITICAL | Manually photograph/film 200+ forklift images at deployment site immediately. Use `vehicle_other` class as catch-all. |
| **Fall false positives from bending/kneeling** | HIGH | HIGH | 3-second immobility requirement is the primary mitigation. Log "stumble" events separately. Tune aspect-ratio threshold per site. |
| **PPE class imbalance** (`helmet_off` rare) | HIGH | HIGH | Focal Loss + class-aware sampling + copy-paste augmentation of violation class. Monitor per-class AP separately. |
| **Homography breaks (camera bumped)** | MEDIUM | CRITICAL | Store 8 reference points (redundant). Auto-detect calibration drift by checking consistency of known static distance markers. |
| **RULA/REBA angle errors due to camera perspective** | HIGH | MEDIUM | Apply camera-angle correction factor. Report score as ±1 uncertainty range. Avoid deploying ergonomic cameras from extreme top-down angles. |
| **WebSocket overload (too many simultaneous incidents)** | MEDIUM | MEDIUM | Rate-limit WebSocket broadcast. Client-side throttling. Backend event queue with batch emit every 500ms. |
| **Edge device out of GPU memory** | MEDIUM | HIGH | Implement model loading priority. If OOM detected, unload ergonomic/PPE models, keep fall+proximity (life-safety first). |
| **Night shift poor pose estimation** | HIGH | HIGH | Verify IR camera compatibility with YOLO-Pose. Train on low-light augmented data. Increase confidence threshold at night. |
| **Team integration failures (contract mismatch)** | HIGH | HIGH | Define and freeze `Detection`, `PoseResult`, `HazardEvent` dataclass schemas in `edge_ai/src/models/` first. No team proceeds until schemas are agreed. |
| **Scope creep on model 4 (REBA complexity)** | MEDIUM | MEDIUM | Deliver RULA first (simpler). REBA is Phase 2 of model 4. |

---

## SECTION 5 — DEPLOYMENT STRATEGY

### 5.1 Development Environment (Immediate)

```yaml
# docker-compose.yml — minimum viable
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: visionsafe360
      POSTGRES_USER: vsadmin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: [postgres_data:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://vsadmin:${DB_PASSWORD}@postgres/visionsafe360
      SECRET_KEY: ${JWT_SECRET}
    depends_on: [postgres]
    ports: ["8000:8000"]

  dashboard:
    build: ./dashboard
    environment:
      BACKEND_URL: http://backend:8000
    depends_on: [backend]
    ports: ["8050:8050"]

# Edge AI runs OUTSIDE docker on the Jetson (or local GPU laptop)
```

### 5.2 Production Architecture (Jetson Orin Nano)

- **Models:** TensorRT FP16 `.engine` files in `edge_ai/weights/`
- **Service management:** `systemd` service for `edge_ai/src/main.py` — auto-start on boot, auto-restart on crash
- **Logging:** Structured JSON logs via `edge_ai/src/utils/logger.py` → local rotating file, ship to backend via BackendClient
- **Model updates:** Backend exposes model version endpoint. BackendClient checks on startup, downloads newer weights if available (OTA update mechanism)
- **Hardware watchdog:** GPIO-based watchdog timer — if main loop stalls > 60 seconds, reboot edge node

### 5.3 Scalability Path

| Scale | Architecture |
|---|---|
| 1–4 cameras, 1 site | Single Jetson Orin Nano + single backend instance (Docker Compose) |
| 5–16 cameras, 1 site | Two Jetson nodes (zone A, zone B) + single backend |
| Multi-site deployment | Backend deployed to cloud (AWS/GCP), each site has local Jetson(s), phone home to central API |
| 50+ cameras | Kafka message queue between edge and backend, backend becomes microservices, model serving via Triton Inference Server |

### 5.4 Latency Budget (Production)

```
RTSP capture          →  frame available:        0 ms  (reference)
Frame queue wait      →  inference start:        0–5 ms
PPE + Vehicle infer   →  TensorRT FP16 each:     ~30 ms  (parallel CUDA streams)
Pose inference        →  shared:                 ~35 ms
Total inference       →  worst case:             ~65 ms
Hazard analysis       →  CPU bound:              ~2 ms
Alert routing         →  async:                  ~1 ms
Backend POST          →  async aiohttp:          ~50–200 ms (network)
WebSocket broadcast   →  async:                  ~5 ms
FCM push delivery     →  Firebase SLA:           < 1 sec

TOTAL: Incident occurs → dashboard alert:  < 1 second (local)
       Incident occurs → mobile push:      < 2 seconds
       Fall → siren:                       < 500 ms (GPIO direct)
```

### 5.5 Monitoring & Logging Strategy

**Metrics to track (emit every 60 seconds):**
```json
{
  "timestamp": "2026-03-01T10:00:00Z",
  "camera_id": "cam_01",
  "fps_actual": 14.8,
  "inference_ms_p50": 65,
  "inference_ms_p99": 120,
  "hazard_events_last_60s": 3,
  "false_alarm_count_last_60s": 0,
  "queue_depth": 2,
  "gpu_memory_mb": 1840,
  "model_versions": {"ppe": "v1.2", "vehicle": "v1.1", "pose": "v1.0"}
}
```

**Alerting thresholds (operations team):**
- FPS drops below 10 → PagerDuty/email alert (camera processing degraded)
- GPU memory > 3 GB → warning (approaching OOM)
- Backend unreachable > 5 minutes → offline queue size growing
- Inference latency p99 > 200 ms → performance regression

### 5.6 Model Retraining Strategy

| Trigger | Action | Frequency |
|---|---|---|
| False positive rate > 3/hr/camera for 24 hrs | Add FP samples to training set, retrain with full pipeline | On demand |
| 30-day data collection cycle | Add site-specific samples, run Stage 3 domain adaptation | Monthly |
| New PPE type introduced (e.g. face shield) | Extend class set, full retraining | On demand |
| Accuracy degradation alert (mAP drops > 5% on validation set) | Full investigation + retrain | On demand |
| Quarterly review | Evaluate against updated dataset, baseline comparison | Quarterly |

**Retraining pipeline:**
```
New labeled data → merge with existing dataset
→ re-run training pipeline (Stage 2 from checkpoint, not from scratch)
→ run evaluation on held-out test set
→ compare metrics vs. deployed version
→ if better: deploy (OTA update) | if worse: investigate and discard
→ log retraining event with metrics to backend
```

---

## SECTION 6 — PROJECT MANAGEMENT

### 6.1 Team Structure

| Role | Count | Responsibilities |
|---|---|---|
| **ML Engineer — PPE** | 1 | Dataset curation, Model 1 training pipeline, metric evaluation |
| **ML Engineer — Vehicle** | 1 | Dataset curation, Model 2 training + homography calibration, ByteTrack integration |
| **ML/CV Engineer — Fall+Ergonomics** | 1 | Model 3 pose tuning, fall rule engine, RULA/REBA algorithm, Model 4 validation |
| **Backend Engineer** | 1 | FastAPI, PostgreSQL, auth, all API routes, WebSocket hub |
| **Edge Systems Engineer** | 1 | Teams 1+2+4 integration (StreamHandler, InferenceEngine, BackendClient, SirenController) |
| **Frontend Engineer** | 1 | Dash dashboard, all 4 pages, real-time video overlay |
| **Tech Lead / Architect** | 1 | Architecture decisions, integration contracts, code review, milestone gates, risk management |

### 6.2 Timeline Summary

| Phase | Duration | Calendar |
|---|---|---|
| Phase 0 — Infrastructure | 2 weeks | Weeks 1–2 |
| Phase 1 — Backend API | 3 weeks | Weeks 2–4 |
| Phase 2 — Edge Pipeline | 5 weeks | Weeks 3–7 |
| Phase 3 — ML Training (parallel) | 6 weeks | Weeks 4–10 |
| Phase 4 — Dashboard + Mobile | 4 weeks | Weeks 6–9 |
| Phase 5 — Integration & Testing | 4 weeks | Weeks 9–12 |
| Phase 6 — Edge Deployment | 2 weeks | Weeks 12–14 |
| **Total** | **14 weeks** | **~3.5 months** |

### 6.3 Development Workflow

- **Sprints:** 1-week sprints. Monday standup (15 min). Friday demo of working code.
- **Branching:** `feature/team1-stream-handler` → PR to `dev` → CI passes → merge. `dev` → `main` only at milestone gates.
- **Data schemas contract:** All inter-module data schemas (Detection, PoseResult, HazardEvent) MUST be implemented and merged to `dev` in Week 2 before any team writes code that depends on them. Schema changes require Tech Lead approval.
- **Definition of Done:** Feature is done when: code merged to dev, unit tests pass, feature visible in a running demo.

### 6.4 Codebase Structure (Final Target)

```
VisionSafe360/
├── backend/                      # FastAPI cloud/local backend
│   ├── app/
│   │   ├── main.py               # FastAPI app factory
│   │   ├── api/routes/           # All HTTP route handlers
│   │   ├── api/websocket/        # WS hub
│   │   ├── config/               # DB + settings
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic schemas
│   │   ├── services/             # Business logic layer
│   │   └── utils/                # JWT, password hashing
│   ├── migrations/               # Alembic DB migrations
│   ├── tests/                    # pytest test suite
│   └── requirements.txt
├── edge_ai/                      # Runs on Jetson or local GPU laptop
│   ├── src/
│   │   ├── main.py               # Orchestrator entry point
│   │   ├── streaming/            # Team 1 — RTSP handling
│   │   ├── config/inference/     # Team 2 — YOLO inference engine
│   │   ├── models/               # Shared data schemas (frozen early)
│   │   ├── analysis/             # Team 3 — Hazard + posture analysis
│   │   ├── alerts/               # Team 4 — Alert routing
│   │   ├── integration/          # Team 4 — Backend HTTP client
│   │   ├── privacy/              # Face blurring
│   │   ├── utils/                # Logger, drawing
│   │   └── config/
│   │       └── settings.py       # All config: thresholds, URLs, model paths
│   ├── weights/                  # .pt / .onnx / .engine model files
│   ├── calibrations/             # Per-camera homography JSON
│   └── tests/
├── dashboard/                    # Plotly Dash web UI
├── mobile_app/                   # Flutter/React Native
├── docs/                         # All specification documents
│   ├── model1_ppe_detection_spec.md
│   ├── model2_vehicle_proximity_spec.md
│   ├── model3_fall_detection_spec.md
│   ├── model4_pose_ergonomics_spec.md
│   └── team[1-4]_*_doc.md
└── docker-compose.yml
```

---

## SECTION 7 — FINAL RECOMMENDATIONS

### Priority Order for Teams Starting Now

1. **Immediately (this week):** Implement all data schemas in `edge_ai/src/models/` — `Detection`, `PoseResult`, `HazardEvent`, `Severity`, `Incident`, `Status`. Every team will code to these interfaces. Freeze them before any other code is written.

2. **Parallel track 1 (backend team):** Start `backend/app/config/database.py`, `settings.py`, then all SQLAlchemy models. Get Alembic working. Implement auth first (everything else needs it).

3. **Parallel track 2 (edge team):** Start `StreamHandler`. Use a local `.mp4` as a fake RTSP source (`cv2.VideoCapture("test.mp4")`). This removes the hardware dependency from development. Then `InferenceEngine` with COCO-pretrained YOLOv8s (no custom weights needed yet — any detections prove the pipeline works).

4. **ML engineers:** Begin data sourcing and annotation infrastructure immediately. The COCO-pretrained weights are your working baseline. You have time (Phase 3 runs 6 weeks) but data annotation is the long pole.

5. **Do NOT start with Jetson.** All development runs on laptop GPU. The edge device is only needed in Phase 6.

---

### The Three Highest-Risk Items to Watch

**Risk 1: Forklift data scarcity.** Open Images + LVIS have ~2,000 forklift images combined. This is insufficient for the industrial variation required. Assign one person to collect on-site forklift footage as their first deliverable in Week 1.

**Risk 2: Schema drift across teams.** In a distributed team, the most common failure mode is that Team 2 outputs a `Detection` and Team 3 expects a slightly different field name or type. Solve this permanently: create `edge_ai/src/models/` first, write `pytest` tests that import from it, and all four teams code to the same imports. Any schema change is a PR reviewed by all leads.

**Risk 3: Fall detection false alarm rate.** A system that cries wolf for every bending worker will be disabled by operators within a week. The 3-second immobility threshold is the primary guard. Validate it aggressively on the bending/kneeling hard-negative dataset before any real deployment demo.

---

### Architecture Decisions That Are Non-Negotiable

- **YOLOv8s as the foundation model for all vision tasks.** Shared Ultralytics ecosystem, one export path (ONNX → TensorRT), one training API. Do not introduce a second model framework.
- **Shared pose model (Model 3 + 4).** Running two separate pose estimation models for fall and ergonomics is wasteful. One inference, two analysis algorithms.
- **Rule-based fall detection in V1.** Training a temporal classifier requires data that doesn't exist yet. Ship the rule-based system on schedule. The LSTM upgrade is explicitly version 2.
- **Independent model weights (Model 1 vs. Model 2).** Despite both using YOLOv8s, they have different class sets, different training data, and different team owners. Do not merge training pipelines — it will create dependencies that slow both teams down.
- **FaceBlurrer is non-optional.** Every snapshot stored or transmitted MUST pass through the face blurrer. This is a GDPR hard requirement. Build it into the BackendClient, not as an optional post-processing step.

---

*This document represents the complete technical understanding and production-level execution plan for VisionSafe 360. All architecture decisions are grounded in the specification documents. All timelines assume a 6–7 person team working full-time on a graduation project schedule. The system is deployable in a real industrial factory under these specifications.*
