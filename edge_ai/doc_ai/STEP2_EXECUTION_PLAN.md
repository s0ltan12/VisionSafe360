# VisionSafe 360 — Step 2 Execution Plan

> **Reviewer:** Senior AI Systems Architect  
> **Date:** March 3, 2026  
> **Prerequisite:** Step 1 — PASSED (verified)  
> **Scope:** HazardAnalyzer + PostureAnalyzer + Pose model integration + pipeline wiring

---

## 1. Objective

Build the **analysis brain** that converts raw `List[Detection]` + pose keypoints into actionable `List[HazardEvent]` objects with severity classification. This is the core safety logic of VisionSafe 360 — every downstream component (AlertManager, BackendClient, Dashboard) consumes `HazardEvent` objects.

**What changes:**
- Two new modules get real code: `hazard_analyzer.py` and `posture_analyzer.py`
- `main.py` gains frame-counter scheduling and HazardAnalyzer/PostureAnalyzer integration
- `inference_engine.py` gets pose model loaded at startup (already has `load_pose()` and `run_pose()`)
- Pose weights (`yolo11s-pose.pt`) downloaded to `weights/`
- New settings constants for hazard thresholds
- Unit tests for both analyzers

**What does NOT change:**
- StreamHandler (Step 1, untouched)
- InferenceEngine API (already has `run_tracker()`, `run_pose()` — no interface changes)
- Data models (HazardEvent, Severity already defined)
- MetricsLogger format (new fields will be added non-breaking)

---

## 2. Architecture

```
StreamHandler (I/O thread)
       │
       ▼  deque(maxlen=1)
┌──────────────────────────────────────────────────────────────────┐
│  Main thread (owns GPU)                                          │
│                                                                  │
│  ┌─────────────────┐     ┌──────────────────────────────┐       │
│  │ InferenceEngine  │     │  Frame Counter Scheduler      │       │
│  │ .run_tracker()   │◄────│  fc % 1 → detector always     │       │
│  │ .run_pose()      │     │  fc % POSE_EVERY_N → pose     │       │
│  └────────┬─────────┘     └──────────────────────────────┘       │
│           │                                                      │
│           ▼                                                      │
│  ┌────────────────────┐   ┌────────────────────┐                │
│  │  HazardAnalyzer     │   │  PostureAnalyzer    │                │
│  │  .analyze(dets,cam) │   │  .analyze(pose,cam) │                │
│  │                     │   │                     │                │
│  │  • ppe_check()      │   │  • RULA/REBA scores │                │
│  │  • proximity()      │   │  • temporal EMA     │                │
│  │  • fall_detect()    │   │  • ergonomic events │                │
│  └────────┬────────────┘   └────────┬────────────┘                │
│           │                         │                            │
│           ▼                         ▼                            │
│      List[HazardEvent]        List[HazardEvent]                  │
│           │                         │                            │
│           └───────────┬─────────────┘                            │
│                       ▼                                          │
│              MetricsLogger + Drawing                             │
│              (annotated frame + JSON telemetry)                   │
└──────────────────────────────────────────────────────────────────┘
```

**Critical rule preserved:** ALL GPU calls (`run_tracker()`, `run_pose()`) happen in the main thread. HazardAnalyzer and PostureAnalyzer are **CPU-only** — they receive inference results and apply rule-based logic. Zero GPU calls inside analyzers.

---

## 3. Components to Implement

### 3.1 HazardAnalyzer (`src/analysis/hazard_analyzer.py`)

**Purpose:** Takes `List[Detection]` from `run_tracker()` and emits `List[HazardEvent]` based on three rule engines.

**Class API:**

```python
class HazardAnalyzer:
    def __init__(self) -> None:
        """Initialize cooldown trackers and fall state machines."""
        ...

    def analyze(
        self,
        detections: List[Detection],
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        """Run all sub-analyzers.  Returns list of events (may be empty)."""
        events = []
        events.extend(self._ppe_check(detections, camera_id, frame_number, timestamp))
        events.extend(self._proximity_check(detections, camera_id, frame_number, timestamp))
        events.extend(self._fall_detection(detections, camera_id, frame_number, timestamp))
        return events
```

#### 3.1.1 PPE Compliance Check (`_ppe_check`)

**Logic:**
1. Separate detections into `persons` (class_id=0) and PPE violations (`helmet_off`=2, `vest_off`=4).
2. For each PPE violation detection, find the nearest `person` detection by IoU overlap (bbox intersection).
3. Association threshold: IoU ≥ 0.3 (violation bbox should overlap significantly with person bbox).
4. If a person is associated with `helmet_off` → emit `HazardEvent(event_type="no_helmet", severity=HIGH)`.
5. If a person is associated with `vest_off` → emit `HazardEvent(event_type="no_vest", severity=MEDIUM)`.
6. If a person has BOTH → emit two separate events.
7. If `helmet_off` near a vehicle (classes 5-8) → escalate to `severity=CRITICAL` (person near machinery without helmet).

**Cooldown:** Per `(track_id, event_type)` pair, minimum 30 seconds between duplicate events. Uses a `dict[tuple[int|None, str], float]` mapping to last-event timestamp.

**Edge cases:**
- `track_id=None` (tracker lost the person) → use bbox center as fallback key
- Multiple persons, single violation → associate to highest-IoU person only
- No person detected but PPE violation class present → discard (orphan detection from model noise)

**Important — current state limitation:** We're running COCO-pretrained YOLO11s, which detects `person` (class 0) but NOT custom PPE classes (1-4). PPE check logic will be written and unit-tested with synthetic data, but will produce zero events in live runs until the custom fine-tuned model is trained. This is by design — build the logic now, swap the model later.

#### 3.1.2 Vehicle Proximity Check (`_proximity_check`)

**Logic:**
1. Extract `persons` (class_id=0) and `vehicles` (class_id in {5,6,7,8}).
2. For COCO weights: also map COCO vehicle classes → `vehicle_other`:
   - COCO `car`(2), `motorcycle`(3), `bus`(5), `truck`(7) → treat as vehicles
3. Compute bottom-center of each bbox: `bc = ((x1+x2)//2, y2)`.
4. For every (person, vehicle) pair, compute Euclidean distance between bottom-centers (pixel space).
5. Thresholds (configurable in `settings.py`):

   | Distance (px) | Severity | Event type |
   |---|---|---|
   | < 80 | CRITICAL | `proximity_critical` |
   | < 150 | HIGH | `proximity_high` |
   | < 250 | MEDIUM | `proximity_warning` |
   | ≥ 250 | — | No event |

6. For each person-vehicle pair that triggers: emit one `HazardEvent` with the closest vehicle info in `metadata`.

**Cooldown:** Per `(person_track_id, vehicle_track_id)` pair, 5 seconds for CRITICAL, 10 seconds for HIGH/MEDIUM.

**Future enhancement (not Step 2):** Homography transform for real-world meter distances. Step 2 uses pixel distance only.

**COCO class bridge:** Since we're running COCO weights, we need a mapping in the analyzer:
```python
COCO_VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
COCO_PERSON_CLASS = "person"
```
This allows proximity detection to work with COCO pretrained weights NOW, before custom training.

#### 3.1.3 Fall Detection (`_fall_detection`)

**Logic — per-person state machine:**

```
State diagram per track_id:

  NORMAL ──(trigger conditions)──► FALL_CANDIDATE ──(immobile >2s)──► FALL_CONFIRMED
    ▲                                    │                                  │
    │                                    │ (recovered)                     │
    └────────────────────────────────────┘                                  │
    ▲                                                                       │
    └───────────────── (cooldown expired, reset) ───────────────────────────┘
```

**Trigger conditions for NORMAL → FALL_CANDIDATE:**
1. Aspect ratio: `w/h > 1.0` (person bbox wider than tall → lying down)
2. Vertical velocity of centroid: `Δy > threshold` over last N frames (rapid downward movement)
3. Either condition alone is insufficient — need aspect ratio change (was < 0.8 in previous frames, now > 1.0)

**Per-person tracking state:**
```python
@dataclass
class PersonFallState:
    centroid_history: deque  # maxlen=FALL_VELOCITY_WINDOW (8 frames)
    aspect_ratio_history: deque  # maxlen=8
    state: str  # "normal", "candidate", "confirmed"
    candidate_since: float  # timestamp when entered candidate state
    last_event_time: float  # for cooldown
```

**Centroid velocity computation:**
```python
if len(centroid_history) >= 2:
    dy = centroid_history[-1][1] - centroid_history[0][1]  # y increases downward
    dt = len(centroid_history) - 1  # in frames
    velocity = dy / dt  # pixels/frame
```

**Thresholds:**
- `FALL_ASPECT_RATIO_THRESHOLD = 1.0` — bbox w/h ratio above which person may be lying
- `FALL_VELOCITY_THRESHOLD = 15.0` — pixels/frame downward velocity
- `FALL_CANDIDATE_TIMEOUT = 2.0` — seconds in candidate state before confirming
- `FALL_IMMOBILITY_THRESHOLD = 5.0` — max centroid movement (px) to count as "immobile"
- `FALL_COOLDOWN = 60.0` — seconds before same track_id can trigger again

**Confirmed fall:**
- `FALL_CANDIDATE` + immobile for >2 seconds → emit `HazardEvent(event_type="fall_confirmed", severity=CRITICAL)`
- `FALL_CANDIDATE` that recovers (stands back up, aspect ratio < 0.8) → reset to NORMAL, no event

**Track ID lifecycle:**
- When a `track_id` disappears from detections for >5 seconds, purge its state from the tracker dict.
- This prevents memory leak with long-running streams.

---

### 3.2 PostureAnalyzer (`src/analysis/posture_analyzer.py`)

**Purpose:** Consumes pose keypoints from `InferenceEngine.run_pose()` and computes ergonomic risk scores (simplified RULA/REBA).

**Class API:**

```python
class PostureAnalyzer:
    def __init__(self) -> None:
        """Initialize per-person keypoint history for temporal smoothing."""
        ...

    def analyze(
        self,
        pose_results: Any,  # Ultralytics Results object
        camera_id: str,
        frame_number: int,
        timestamp: float,
    ) -> List[HazardEvent]:
        """Compute ergonomic risk for each detected person."""
        ...
```

**COCO Keypoint indices (17 points):**
```python
KEYPOINT_NAMES = {
    0: "nose", 1: "left_eye", 2: "right_eye",
    3: "left_ear", 4: "right_ear",
    5: "left_shoulder", 6: "right_shoulder",
    7: "left_elbow", 8: "right_elbow",
    9: "left_wrist", 10: "right_wrist",
    11: "left_hip", 12: "right_hip",
    13: "left_knee", 14: "right_knee",
    15: "left_ankle", 16: "right_ankle",
}
```

**Joint angle computation:**
```python
def _angle_between(a, b, c) -> float:
    """Angle at point b formed by rays ba and bc, using law of cosines."""
    ba = a - b
    bc = c - b
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return np.degrees(np.arccos(np.clip(cosine, -1, 1)))
```

**Key angles for RULA assessment:**
| Angle | Points | Risk threshold |
|---|---|---|
| Trunk flexion | shoulder → hip → knee | > 45° = HIGH, > 20° = MEDIUM |
| Neck flexion | ear → shoulder → hip | > 40° = HIGH, > 20° = MEDIUM |
| Upper arm | elbow → shoulder → hip | > 90° = HIGH, > 45° = MEDIUM |
| Lower arm | wrist → elbow → shoulder | < 60° or > 100° = MEDIUM |

**Simplified RULA score mapping:**
```python
RULA_THRESHOLDS = {
    "LOW":      (1, 2),     # acceptable
    "MEDIUM":   (3, 4),     # investigate
    "HIGH":     (5, 6),     # investigate and change soon
    "CRITICAL": (7, 7),     # investigate and change immediately
}
```

**Temporal smoothing (EMA):**
```python
alpha = 0.6  # new frame weight
kp_smooth[track_id] = alpha * kp_new + (1 - alpha) * kp_smooth[track_id]
```
- `TEMPORAL_SMOOTH_WINDOW = 5` frames — smooth keypoints over last 5 pose frames
- `ERGONOMIC_SCORE_WINDOW = 90` frames at 1.5Hz ≈ 60 seconds for sustained exposure

**Event emission:**
- Score ≥ 5 sustained for > 30 seconds → `HazardEvent(event_type="poor_posture", severity=HIGH)`
- Score ≥ 7 at any point → `HazardEvent(event_type="dangerous_posture", severity=CRITICAL)`
- Cooldown: 60 seconds per `track_id`

**Keypoint confidence filter:**
- Discard keypoints with confidence < 0.5 — don't compute angles from uncertain joints.
- If any required keypoint for an angle is missing → skip that angle, don't guess.

---

### 3.3 Pipeline Wiring Changes (`main.py`)

**New frame-counter scheduling in the inference loop:**

```python
# Pseudocode for the modified main loop:

hazard_analyzer = HazardAnalyzer()
posture_analyzer = PostureAnalyzer()
frame_counter = 0

while not shutdown:
    bundle = stream.get_frame()
    if bundle is None:
        time.sleep(0.001)
        continue

    # ── Model A + ByteTrack (every frame) ───────────────
    detections, det_latency = engine.run_tracker(bundle)

    # ── Model B — Pose (every POSE_EVERY_N frames) ─────
    pose_results = None
    pose_latency = 0.0
    if frame_counter % POSE_EVERY_N == 0 and engine._pose_loaded:
        pose_results, pose_latency = engine.run_pose(bundle)

    # ── HazardAnalyzer (every frame — CPU only) ────────
    hazard_events = hazard_analyzer.analyze(
        detections, cam_id, bundle.frame_number, bundle.timestamp,
    )

    # ── PostureAnalyzer (every ERGONOMIC_EVERY_N — CPU only) ──
    if frame_counter % ERGONOMIC_EVERY_N == 0 and pose_results is not None:
        hazard_events.extend(posture_analyzer.analyze(
            pose_results, cam_id, bundle.frame_number, bundle.timestamp,
        ))

    frame_counter += 1

    # ── Log hazard events ──────────────────────────────
    for event in hazard_events:
        logger.warning("HAZARD: %s  severity=%s  cam=%s  track=%s",
                       event.event_type, event.severity.name,
                       event.camera_id, event.track_id)

    # ── Rest of loop unchanged (metrics, drawing, display) ──
```

**Drawing changes:**
- Add `draw_hazard_events(frame, events)` to `drawing.py` — render a colored alert banner on the frame for each active hazard.
- Fall detections: red overlay on the person bbox.
- Proximity warnings: orange line between person and vehicle.
- PPE violations: yellow icon/text on the person bbox.

**Metrics changes (non-breaking additions to JSON line):**
```json
{
    "...": "existing fields...",
    "n_hazard_events": 2,
    "pose_ms": 18.3,
    "hazard_types": ["proximity_high", "no_helmet"]
}
```

---

### 3.4 Settings Additions (`settings.py`)

```python
# ─── HazardAnalyzer thresholds ──────────────────────────────────
# PPE
PPE_IOU_THRESHOLD = 0.3              # min IoU to associate violation with person
PPE_COOLDOWN_SEC = 30.0              # per (track_id, event_type) cooldown

# Proximity (pixel distances — use homography in future step)
PROXIMITY_CRITICAL_PX = 80
PROXIMITY_HIGH_PX = 150
PROXIMITY_WARNING_PX = 250
PROXIMITY_COOLDOWN_CRITICAL = 5.0    # seconds
PROXIMITY_COOLDOWN_OTHER = 10.0      # seconds

# Fall detection
FALL_ASPECT_RATIO_THRESHOLD = 1.0    # w/h above this = potentially lying
FALL_VELOCITY_THRESHOLD = 15.0       # pixels/frame downward velocity
FALL_VELOCITY_WINDOW = 8             # frames to compute velocity over
FALL_CANDIDATE_TIMEOUT = 2.0         # seconds immobile to confirm
FALL_IMMOBILITY_THRESHOLD = 5.0      # max px movement = "immobile"
FALL_COOLDOWN_SEC = 60.0             # before same track re-fires
FALL_TRACK_PURGE_SEC = 5.0           # purge stale track state after this

# PostureAnalyzer
POSTURE_KEYPOINT_CONF_MIN = 0.5      # discard keypoints below this
POSTURE_EMA_ALPHA = 0.6              # temporal smoothing weight (0=all history, 1=all new)
POSTURE_SUSTAINED_THRESHOLD = 30.0   # seconds of poor posture before event
POSTURE_COOLDOWN_SEC = 60.0          # per track_id cooldown
TEMPORAL_SMOOTH_WINDOW = 5
ERGONOMIC_SCORE_WINDOW = 90          # frames at 1.5Hz ≈ 60s

# COCO-to-VisionSafe class bridge (for pretrained weights)
COCO_PERSON_ID = 0
COCO_VEHICLE_IDS = {2, 3, 5, 7}     # car, motorcycle, bus, truck in COCO
```

---

## 4. File Changes Summary

| File | Action | Description |
|---|---|---|
| `src/analysis/__init__.py` | **Edit** | Add exports for HazardAnalyzer, PostureAnalyzer |
| `src/analysis/hazard_analyzer.py` | **Write (new)** | ~250 lines — PPE, proximity, fall detection |
| `src/analysis/posture_analyzer.py` | **Write (new)** | ~200 lines — RULA scoring, EMA smoothing |
| `src/config/settings.py` | **Edit** | Add ~25 new threshold constants |
| `src/main.py` | **Edit** | Add frame-counter scheduling, analyzer calls, pose loading |
| `src/utils/drawing.py` | **Edit** | Add `draw_hazard_events()` function |
| `src/utils/logger.py` | **Edit** | Add optional `n_hazard_events`, `pose_ms`, `hazard_types` fields |
| `tests/test_hazard_analyzer.py` | **Write (new)** | ~150 lines — synthetic detection tests |
| `tests/test_posture_analyzer.py` | **Write (new)** | ~100 lines — synthetic keypoint tests |
| `weights/yolo11s-pose.pt` | **Download** | ~19 MB pose model |

**Estimated total new code:** ~700-800 lines (excluding tests: ~400 lines).

---

## 5. Implementation Order

Step 2 must be built in this exact sequence (dependencies flow downward):

```
Phase A: Foundation (no GPU needed)
├── 5.1  Add threshold constants to settings.py
├── 5.2  Implement HazardAnalyzer (PPE check)
├── 5.3  Implement HazardAnalyzer (proximity check)
├── 5.4  Implement HazardAnalyzer (fall detection state machine)
├── 5.5  Write test_hazard_analyzer.py — all tests pass with synthetic data
│
Phase B: Pose integration (needs GPU)
├── 5.6  Download yolo11s-pose.pt
├── 5.7  Implement PostureAnalyzer (angle computation + RULA scoring)
├── 5.8  Write test_posture_analyzer.py  
│
Phase C: Pipeline wiring
├── 5.9  Update main.py — frame scheduling + analyzer integration
├── 5.10 Update drawing.py — hazard event visualization
├── 5.11 Update logger.py — new telemetry fields
│
Phase D: Validation
├── 5.12 Run pipeline end-to-end with real video
└── 5.13 Verify hazard events appear in JSON telemetry + annotated frames
```

---

## 6. Acceptance Criteria

### Functional

- [ ] `HazardAnalyzer.analyze()` returns `List[HazardEvent]` — each event has valid `event_type`, `severity`, `camera_id`, `timestamp`, `track_id`
- [ ] PPE check correctly associates `helmet_off`/`vest_off` with nearest person by IoU
- [ ] Proximity check fires events when person bottom-center is within threshold distance of vehicle
- [ ] Fall detection state machine transitions: NORMAL → CANDIDATE → CONFIRMED with correct timing
- [ ] Cooldowns prevent duplicate events within configured windows
- [ ] PostureAnalyzer computes joint angles from COCO-17 keypoints
- [ ] Temporal EMA smoothing applied to keypoints before angle computation
- [ ] `pose_results=None` (non-pose frame) does not crash PostureAnalyzer
- [ ] Stale track state is purged after `FALL_TRACK_PURGE_SEC` of absence

### Performance

- [ ] HazardAnalyzer.analyze() adds < 1 ms per frame (CPU-only rules)
- [ ] PostureAnalyzer.analyze() adds < 2 ms per frame (CPU angle math)
- [ ] Pose model (`run_pose()`) adds ~15-25 ms only on scheduled frames (every 3rd)
- [ ] Total pipeline FPS ≥ 12 Hz with pose enabled (from 15 Hz without)
- [ ] Zero additional VRAM beyond the pose model (~520 MB)

### Testing

- [ ] `test_hazard_analyzer.py` — minimum 6 tests:
  1. PPE violation generates correct event
  2. PPE violation with cooldown → second event suppressed
  3. Proximity CRITICAL at close range
  4. Proximity no event at safe distance
  5. Fall candidate → confirmed after timeout
  6. Fall candidate → recovered (aspect ratio normalizes)
- [ ] `test_posture_analyzer.py` — minimum 4 tests:
  1. Good posture → no event
  2. Poor posture angles → HIGH severity event
  3. Low-confidence keypoints filtered out
  4. EMA smoothing reduces noise

### Integration

- [ ] Running `python src/main.py --source video.mp4 --cam-id cam_01` with a video containing people and vehicles produces proximity events in the JSON telemetry
- [ ] Annotated output video shows visual indicators for active hazards
- [ ] `"n_hazard_events"` field appears in JSON metric lines

---

## 7. Risk Analysis

| Risk | Impact | Mitigation |
|---|---|---|
| COCO weights don't detect PPE classes (1-4) | PPE check produces zero events | Logic is tested with synthetics; swapping to custom model later will activate it automatically |
| Pose model download fails (apostrophe path bug) | `load_pose()` crashes | Same `_resolve_weights()` + `os.path.relpath()` fix already in place |
| Fall detection too sensitive (false positives) | Alert spam | Conservative thresholds + 2s confirmation window + 60s cooldown |
| Fall detection too slow (missed real falls) | Safety gap | Runs every frame (15 Hz); 2s confirmation is fast enough for real falls |
| Pixel proximity inaccurate (perspective distortion) | Wrong distance estimates | Acknowledged — Step 2 uses pixel distance as proxy. Homography calibration comes in a later step |
| Two models in VRAM | OOM risk | 480 + 520 = 1000 MB models, + 750 MB CUDA = ~1750 MB total. Well within 6 GB |
| PostureAnalyzer on partial keypoints | Wrong angles | Skip angles where any required keypoint is below confidence threshold |

---

## 8. COCO Compatibility Bridge

Since we're running **COCO-pretrained** YOLO11s (80 classes), not the custom 9-class model yet, we need a compatibility layer in HazardAnalyzer:

```python
def _classify_detection(self, det: Detection) -> str:
    """Map detection to VisionSafe role: 'person', 'vehicle', 'ppe_violation', or 'other'."""
    name = det.class_name.lower()
    
    # Direct match (custom model)
    if det.class_id == 0 or name == "person":
        return "person"
    if name in ("helmet_off", "vest_off"):
        return "ppe_violation"
    if name in ("helmet_on", "vest_on"):
        return "ppe_ok"
    if det.class_id in (5, 6, 7, 8) or name in UNIFIED_CLASS_MAP.values():
        return "vehicle"
    
    # COCO fallback
    if name in ("car", "motorcycle", "bus", "truck"):
        return "vehicle"
    
    return "other"
```

This ensures the proximity checker works TODAY with COCO `car`/`truck` detections, and will seamlessly switch to `forklift`/`loader`/`truck`/`vehicle_other` when the custom model is trained.

---

## 9. Dependency Downloads

```bash
# Pose weights (run from edge_ai/)
cd edge_ai
curl -L -o weights/yolo11s-pose.pt \
  "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11s-pose.pt"

# Verify
python3 -c "
from ultralytics import YOLO
m = YOLO('weights/yolo11s-pose.pt')
print(f'Pose model loaded: {len(m.names)} classes, keypoint shape test OK')
"
```

No new pip dependencies — `numpy`, `opencv-python`, `ultralytics`, `torch` are already in `requirements.txt`.

---

## 10. Post-Step 2 State

After Step 2 is complete, the system will:
- **Detect** people and vehicles in real-time (COCO pretrained)
- **Track** them with ByteTrack (persistent IDs)
- **Analyze** PPE compliance (ready for custom model), vehicle proximity (pixel-based), falls (state machine)
- **Score** posture ergonomics (simplified RULA via pose keypoints)
- **Emit** structured `HazardEvent` objects with severity classification
- **Visualize** hazards on annotated video output
- **Log** hazard events in JSON telemetry

**What remains (Steps 3-6):**

| Step | Scope |
|---|---|
| Step 3 | AlertManager + severity-based routing (FCM, siren, WebSocket) |
| Step 4 | BackendClient + offline queue + JWT auth |
| Step 5 | Multi-camera orchestration (4 cameras, round-robin scheduling) |
| Step 6 | FaceBlurrer (GDPR privacy) + production hardening |

---

*Step 2 is accepted when all acceptance criteria in Section 6 are green. Proceed to implementation?*
