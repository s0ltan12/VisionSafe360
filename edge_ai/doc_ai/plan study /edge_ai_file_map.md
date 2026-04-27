# Edge AI - File Map & Quick Navigation

## 📁 Directory Structure with Descriptions

```
edge_ai/
├── demo_pipeline.py              [600 lines] Demo script with 3 scenarios (track/proximity/fall)
├── requirements.txt              Configuration for dependencies
├── requirements.dev.txt          Dev dependencies
│
├── src/
│   ├── main.py                   [700 lines] ⭐⭐⭐ MAIN ENTRY POINT - Start here!
│   │
│   ├── config/                   Configuration and settings
│   │   ├── settings.py           [230 lines] ⭐⭐⭐ All constants and env vars
│   │   ├── profile.py            [183 lines] ⭐⭐⭐ Profile system (feature toggle)
│   │   ├── ui_settings.py        [100 lines] ⭐⭐  UI configuration
│   │   ├── bytetrack.yaml        ByteTrack tracker configuration
│   │   └── inference/
│   │       └── inference_engine.py [400 lines] ⭐⭐⭐ Model loading + inference + tracking
│   │
│   ├── models/                   Data structures (read first!)
│   │   ├── detection.py          [80 lines]  ⭐⭐⭐ Detection class (person/vehicle/PPE)
│   │   ├── inference_result.py   [60 lines]  ⭐⭐⭐ Model output container
│   │   ├── hazard_event.py       [100 lines] ⭐⭐⭐ Hazard event structure
│   │   ├── frame_bundle.py       [50 lines]  ⭐⭐  Frame + metadata bundle
│   │   ├── incident.py           [70 lines]  ⭐⭐  Incident reporting
│   │   ├── severity.py           [30 lines]  ⭐⭐  Severity levels enum
│   │   └── status.py             [40 lines]  ⭐⭐  State enums
│   │
│   ├── streaming/                Frame acquisition
│   │   └── stream_handler.py     [212 lines] ⭐⭐⭐ Video stream handling (threaded)
│   │
│   ├── analysis/                 🔥 CORE SAFETY LOGIC - Most important!
│   │   ├── hazard_analyzer.py    [338 lines] ⭐⭐⭐ Fall detection state machine
│   │   ├── posture_analyzer.py   [273 lines] ⭐⭐⭐ RULA/REBA ergonomic scoring
│   │   ├── scoring.py            [356 lines] ⭐⭐⭐ RULA/REBA algorithms
│   │   ├── proximity_analyzer.py [116 lines] ⭐⭐⭐ Person-vehicle proximity
│   │   ├── event_aggregator.py   [174 lines] ⭐⭐⭐ Event collection & dedup
│   │   ├── track_quality.py      [255 lines] ⭐⭐  Track stability monitoring
│   │   ├── calibration.py        [136 lines] ⭐⭐  Camera calibration for depth
│   │   ├── angles.py             [155 lines] ⭐⭐  Joint angle calculations
│   │   └── capability_check.py   [80 lines]  ⭐   Feature availability
│   │
│   ├── integration/              External communication
│   │   └── backend_client.py     [442 lines] ⭐⭐⭐ Backend API + offline queue
│   │
│   ├── alerts/                   Alert system
│   │   ├── alert_manager.py      [554 lines] ⭐⭐⭐ Alert orchestration (largest!)
│   │   ├── fcm_service.py        [173 lines] ⭐⭐  Firebase push notifications
│   │   ├── notification_service.py [191 lines] ⭐⭐  Multi-channel routing
│   │   └── siren_controller.py   [185 lines] ⭐⭐  Physical siren control
│   │
│   ├── ui/                       Visualization layer
│   │   ├── renderer.py           [207 lines] ⭐⭐⭐ Main rendering orchestrator
│   │   ├── theme.py              [89 lines]  ⭐⭐  Color schemes
│   │   └── layers/               Individual render layers
│   │       ├── detections_layer.py    [100 lines] ⭐⭐ Bounding boxes
│   │       ├── pose_layer.py          [120 lines] ⭐⭐ Skeleton rendering
│   │       ├── hazards_layer.py       [100 lines] ⭐⭐ Event highlights
│   │       ├── hud_layer.py           [150 lines] ⭐⭐ Stats overlay
│   │       ├── worker_panel_layer.py  [130 lines] ⭐⭐ Per-worker panels
│   │       ├── zones_layer.py         [80 lines]  ⭐⭐ Danger zones
│   │       └── banners_layer.py       [90 lines]  ⭐⭐ Alert banners
│   │
│   └── utils/                    Helper functions
│       ├── logger.py             [66 lines]  ⭐⭐  Structured logging
│       └── drawing.py            [184 lines] ⭐⭐  Low-level drawing utils
│
├── profiles/                     Feature profiles
│   ├── full_suite.yaml           All features enabled
│   ├── fall_only.yaml            Only fall detection
│   ├── ppe_only.yaml             Only PPE detection
│   └── proximity_only.yaml       Only proximity detection
│
├── configs/                      Model configurations
│   └── sh17_classes.yaml         PPE class definitions
│
├── weights/                      Model weights (not in repo)
│   └── *.pt                      Download separately
│
├── tests/                        Test suite
├── eval/                         Evaluation scripts
└── calibration/                  Calibration data
```

---

## 🎯 Study Order by File

### Week 1: Foundation & Core Pipeline

**Day 1: Data Models (2-3 hours)**
```
1. src/models/detection.py          - Detection class
2. src/models/severity.py           - Severity levels
3. src/models/status.py             - State enums
4. src/models/hazard_event.py       - Event structure
5. src/models/inference_result.py   - Model output
6. src/models/frame_bundle.py       - Frame container
7. src/models/incident.py           - Incident structure
```

**Day 2: Configuration (2-3 hours)**
```
1. src/config/settings.py           - All constants (READ TOP TO BOTTOM)
2. profiles/full_suite.yaml         - Example profile
3. src/config/profile.py            - Profile loading system
4. src/config/ui_settings.py        - UI configuration
```

**Day 3-4: Main Pipeline (4-6 hours)**
```
1. src/main.py (lines 1-100)        - Imports and setup
2. src/main.py (lines 100-300)      - PipelineOrchestrator.__init__()
3. src/main.py (lines 300-600)      - Main processing loop
4. src/main.py (lines 600-700)      - Argument parsing and entry
```

**Day 5: Inference Engine (3-4 hours)**
```
1. src/config/inference/inference_engine.py  - Read top to bottom
   Focus on:
   - load_models()
   - infer()
   - ByteTrack integration
```

**Day 6: Streaming (2-3 hours)**
```
1. src/streaming/stream_handler.py  - Frame acquisition threading
   Focus on:
   - Threading model
   - Latest-frame policy (deque)
   - Error handling
```

**Day 7: Run and Experiment (2-3 hours)**
```
1. demo_pipeline.py                 - Study the demo script
2. Run: python src/main.py --source video.mp4 --cam-id cam_01 --show
3. Run: python demo_pipeline.py --part A
4. Run: python demo_pipeline.py --part B
5. Run: python demo_pipeline.py --part C
```

---

### Week 2: Analysis Modules (Core Safety Logic)

**Day 1-2: Fall Detection (6-8 hours)** ⭐⭐⭐
```
1. src/analysis/hazard_analyzer.py  - Fall detection state machine
   Read order:
   - Docstring (state machine diagram)
   - __init__() (initialization)
   - analyze() (main analysis method)
   - State transition methods
   - _check_fall_indicators()
   
2. Test: python demo_pipeline.py --part C
```

**Day 3-4: Ergonomics (6-8 hours)** ⭐⭐⭐
```
1. src/analysis/angles.py           - Angle calculation utilities
2. External: Read about RULA/REBA (Google search, 30 min)
3. src/analysis/scoring.py          - RULA/REBA algorithms
   Focus on:
   - calculate_rula()
   - calculate_reba()
   - Scoring tables
4. src/analysis/posture_analyzer.py - Integration and thresholds
```

**Day 5: Proximity Detection (3-4 hours)** ⭐⭐⭐
```
1. src/analysis/calibration.py      - Camera calibration
2. src/analysis/proximity_analyzer.py - Distance calculation
   Focus on:
   - Pixel-based distance
   - Danger zones
   - Temporal filtering
   
3. Test: python demo_pipeline.py --part B
```

**Day 6: Event Aggregation (2-3 hours)**
```
1. src/analysis/event_aggregator.py - Event collection
   Focus on:
   - Deduplication logic
   - Event ID assignment
   - Batching for backend
```

**Day 7: Track Quality (2-3 hours)**
```
1. src/analysis/track_quality.py    - Quality monitoring
2. src/analysis/capability_check.py - Feature checks
```

---

### Week 3: Integration & Alerts

**Day 1-2: Backend Integration (6-8 hours)** ⭐⭐⭐
```
1. src/integration/backend_client.py - Backend API client
   Focus on:
   - Offline queue (SQLite)
   - Event sending logic
   - Retry mechanism
   - Authentication
   - Batch flushing
```

**Day 3-4: Alert System (6-8 hours)** ⭐⭐⭐
```
1. src/alerts/alert_manager.py      - Alert orchestration (largest file!)
   Focus on:
   - Alert routing
   - Deduplication
   - Cooldown periods
   - Priority handling

2. src/alerts/fcm_service.py        - Firebase push notifications
3. src/alerts/notification_service.py - Multi-channel routing
4. src/alerts/siren_controller.py   - Siren control
```

**Day 5-7: Review and Experiments**
```
1. Trace end-to-end flow: Detection → Event → Alert → Backend
2. Test offline queue: Disconnect and reconnect
3. Test alerts with different severities
4. Modify alert thresholds
```

---

### Week 4: UI & Visualization

**Day 1-2: Rendering Core (4-5 hours)**
```
1. src/ui/theme.py                  - Color schemes
2. src/utils/drawing.py             - Low-level drawing
3. src/ui/renderer.py               - Main orchestrator
   Focus on:
   - Layer composition
   - Rendering pipeline
   - Theme application
```

**Day 3-5: UI Layers (6-8 hours)**
```
1. src/ui/layers/detections_layer.py - Bounding boxes (start here, simplest)
2. src/ui/layers/pose_layer.py       - Skeleton rendering
3. src/ui/layers/hazards_layer.py    - Event highlights
4. src/ui/layers/hud_layer.py        - Stats overlay
5. src/ui/layers/worker_panel_layer.py - Info panels
6. src/ui/layers/zones_layer.py      - Danger zones
7. src/ui/layers/banners_layer.py    - Alert banners
```

**Day 6-7: Customization**
```
1. Modify theme colors
2. Add custom UI layer
3. Change HUD layout
4. Customize worker panels
```

---

## 🚀 Quick Start Commands

### Run Basic Pipeline
```bash
cd edge_ai
python src/main.py --source path/to/video.mp4 --cam-id cam_01 --show
```

### Run with Profile
```bash
python src/main.py --source video.mp4 --cam-id cam_01 --profile fall_only --show
```

### Run Demo Pipeline
```bash
# All demos
python demo_pipeline.py

# Track stability analysis
python demo_pipeline.py --part A

# Proximity events
python demo_pipeline.py --part B

# Fall simulation
python demo_pipeline.py --part C
```

### Run with Telemetry
```bash
python src/main.py --source video.mp4 --cam-id cam_01 --telemetry /tmp/telemetry.jsonl
```

---

## 📊 File Complexity & Priority Matrix

| Complexity | Priority | Files |
|------------|----------|-------|
| High | High | `main.py`, `inference_engine.py`, `hazard_analyzer.py`, `alert_manager.py` |
| High | Medium | `scoring.py`, `backend_client.py`, `posture_analyzer.py` |
| Medium | High | `stream_handler.py`, `proximity_analyzer.py`, `event_aggregator.py` |
| Medium | Medium | `fcm_service.py`, `renderer.py`, `track_quality.py`, `calibration.py` |
| Low | High | `settings.py`, `profile.py`, `detection.py`, `hazard_event.py` |
| Low | Medium | All UI layers, `theme.py`, `logger.py` |
| Low | Low | `__init__.py` files, small utilities |

**Study Recommendation:**
- Start with: Low complexity + High priority
- Then: Medium complexity + High priority  
- Then: High complexity + High priority
- Finally: Everything else

---

## 🔍 Grep Patterns for Exploration

### Find all TODO/FIXME comments
```bash
grep -r "TODO\|FIXME" edge_ai/src/
```

### Find all configuration constants
```bash
grep -r "^[A-Z_].*=" edge_ai/src/config/settings.py
```

### Find all class definitions
```bash
grep -r "^class " edge_ai/src/
```

### Find all main functions/entry points
```bash
grep -r "if __name__ == .__main__." edge_ai/
```

### Find all environment variable usage
```bash
grep -r "os.getenv\|os.environ" edge_ai/src/
```

---

## 💡 Study Tips

1. **Use VSCode/IDE:** Jump to definition is invaluable
2. **Keep notes:** Document your understanding as you go
3. **Draw diagrams:** Visualize the architecture
4. **Run code:** See it in action with real videos
5. **Modify and test:** Best way to learn
6. **Read commits:** `git log` shows design evolution
7. **Ask questions:** Use comments to mark unclear areas
8. **Trace execution:** Use print/logging to follow flow

---

## 🎓 Mastery Checklist

### Foundation
- [ ] Understand all data models
- [ ] Know all configuration options
- [ ] Can explain the main loop
- [ ] Understand inference + tracking

### Core Logic
- [ ] Can explain fall detection algorithm
- [ ] Understand RULA/REBA scoring
- [ ] Know proximity detection logic
- [ ] Understand event aggregation

### Integration
- [ ] Know how offline queue works
- [ ] Understand alert routing
- [ ] Can trace event → backend → dashboard

### Practical
- [ ] Can run with different profiles
- [ ] Can modify thresholds
- [ ] Can customize UI
- [ ] Can debug issues

---

Happy studying! 🚀
