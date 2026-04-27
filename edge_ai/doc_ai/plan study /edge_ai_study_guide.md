# Edge AI Module - Complete Study Guide

## 📋 Overview

The **edge_ai** module is the core computer vision and AI processing pipeline for VisionSafe 360. It runs on edge devices (cameras, edge servers) and performs real-time safety monitoring.

**Total Files:** 50 Python files (~3,500 lines of code)  
**Key Technologies:** YOLOv8, PyTorch, OpenCV, ByteTrack  
**Main Entry Point:** `src/main.py`

---

## 🎯 Study Progression Path

### Level 1: Foundation - Data Models & Configuration (START HERE)
Understand the data structures and configuration before diving into logic.

### Level 2: Core Pipeline - Entry Point & Orchestration
Learn how the system initializes and coordinates components.

### Level 3: Inference & Detection - Computer Vision Core
Understand model loading, inference, and detection extraction.

### Level 4: Analysis Modules - Safety Logic
Deep dive into fall detection, ergonomics, and proximity analysis.

### Level 5: Integration & Alerts - External Communication
Learn how the system communicates with backend and sends alerts.

### Level 6: UI & Visualization - Display Layer
Understand how detections and events are rendered.

### Level 7: Advanced - Streaming, Quality, Calibration
Master advanced features and optimizations.

---

## 📚 LEVEL 1: Foundation - Data Models & Configuration

### 1.1 Data Models (src/models/)
**Purpose:** Core data structures used throughout the pipeline

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `detection.py` | ~80 | ⭐⭐⭐ | Detection class - represents detected objects (person, vehicle, PPE) |
| `inference_result.py` | ~60 | ⭐⭐⭐ | Container for model inference output |
| `hazard_event.py` | ~100 | ⭐⭐⭐ | Hazard event structure (falls, proximity violations) |
| `frame_bundle.py` | ~50 | ⭐⭐ | Bundles frame + metadata for processing |
| `incident.py` | ~70 | ⭐⭐ | Incident reporting structure |
| `severity.py` | ~30 | ⭐⭐ | Severity levels (LOW, MEDIUM, HIGH, CRITICAL) |
| `status.py` | ~40 | ⭐⭐ | State enums (NORMAL, WARNING, DANGER) |

**Study Order:**
1. Start with `detection.py` - the most fundamental structure
2. Read `severity.py` and `status.py` - simple enums
3. Study `hazard_event.py` - how events are structured
4. Check `inference_result.py` - model output container
5. Review `frame_bundle.py` and `incident.py` for context

**Key Questions to Answer:**
- What information does a Detection contain?
- How are hazard events structured?
- What severity levels exist and when are they used?
- How do detections relate to hazard events?

---

### 1.2 Configuration System (src/config/)

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `settings.py` | 230 | ⭐⭐⭐ | Central configuration - all constants and env vars |
| `profile.py` | 183 | ⭐⭐⭐ | Profile system - feature enable/disable |
| `ui_settings.py` | ~100 | ⭐⭐ | UI configuration (colors, fonts, layout) |

**Profile Files (profiles/):**
- `full_suite.yaml` - All features enabled (production)
- `fall_only.yaml` - Only fall detection
- `ppe_only.yaml` - Only PPE detection
- `proximity_only.yaml` - Only proximity detection

**Study Order:**
1. Read `settings.py` from top to bottom - understand all constants
2. Study `profile.py` - learn how profiles work
3. Check `full_suite.yaml` - see a complete profile
4. Review `ui_settings.py` - understand UI configuration

**Key Questions:**
- What can be configured via environment variables?
- How do profiles enable/disable features?
- What are the default thresholds for fall detection, ergonomics, etc.?
- How does the UI configuration affect rendering?

---

## 📚 LEVEL 2: Core Pipeline - Entry Point & Orchestration

### 2.1 Main Pipeline Orchestrator

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `main.py` | ~700 | ⭐⭐⭐ | **START HERE** - Main entry point and orchestration |
| `demo_pipeline.py` | 600+ | ⭐⭐ | Demo/testing script with synthetic data |

**main.py Structure:**
```
1. Imports and environment setup (lines 1-80)
2. Pipeline orchestrator class (lines 80-500)
   - Initialization
   - Main processing loop
   - Shutdown handling
3. Argument parsing and entry point (lines 500-700)
```

**Study Approach for main.py:**
1. **First pass (30 min):** Read the docstring and main() function - understand command-line args
2. **Second pass (1 hour):** Study the PipelineOrchestrator class initialization
3. **Third pass (2 hours):** Deep dive into the main processing loop
4. **Fourth pass (1 hour):** Understand shutdown and cleanup

**Key Sections to Focus On:**
- `__init__()` - How components are initialized
- `run()` - The main processing loop
- Frame acquisition and inference
- Event collection and handling
- FPS regulation and performance monitoring

**Key Questions:**
- What is the order of component initialization?
- How does the main loop work (while loop structure)?
- How is GPU ownership managed?
- What happens when shutdown is triggered?
- How are frames dropped when inference can't keep up?

---

## 📚 LEVEL 3: Inference & Detection - Computer Vision Core

### 3.1 Inference Engine

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `inference_engine.py` | ~400 | ⭐⭐⭐ | Model loading, inference, tracking |

**What InferenceEngine Does:**
- Loads YOLOv8 models (pose, PPE, objects)
- Runs inference on frames
- Integrates ByteTrack for object tracking
- Extracts detections with track IDs
- Manages model lifecycle

**Study Approach:**
1. Read class docstring and __init__()
2. Study load_models() - understand model initialization
3. Deep dive into infer() - the main inference method
4. Understand tracking integration
5. Study detection extraction and filtering

**Key Concepts:**
- **Pose model:** Detects people + 17 keypoints per person
- **ByteTrack:** Assigns consistent track IDs across frames
- **Non-maximum suppression (NMS):** Filters overlapping detections
- **Confidence thresholding:** Filters low-quality detections

**Key Questions:**
- How are models loaded from weights files?
- What is the inference pipeline flow?
- How does ByteTrack maintain track IDs?
- How are keypoints extracted from pose model?
- What confidence thresholds are used?

---

### 3.2 Streaming & Frame Acquisition

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `stream_handler.py` | 212 | ⭐⭐⭐ | Video stream handling with threading |

**What StreamHandler Does:**
- Opens video sources (file, camera, RTSP)
- Runs frame acquisition in separate thread
- Uses deque(maxlen=1) for latest-frame policy
- Handles stream errors and reconnection

**Study Approach:**
1. Understand the threading model
2. Study the latest-frame policy (deque)
3. Learn error handling and reconnection
4. Understand synchronization (locks)

**Key Concepts:**
- **Latest-frame policy:** Old frames are dropped, not queued
- **Producer-consumer pattern:** StreamHandler produces, main.py consumes
- **Thread safety:** Using locks for shared state

**Key Questions:**
- Why use deque(maxlen=1) instead of a queue?
- How does the streaming thread work?
- What happens when frames can't be read?
- How is thread synchronization handled?

---

## 📚 LEVEL 4: Analysis Modules - Safety Logic (MOST IMPORTANT)

### 4.1 Fall Detection (Hazard Analysis)

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `hazard_analyzer.py` | 338 | ⭐⭐⭐ | **CRITICAL** - Fall detection state machine |

**What HazardAnalyzer Does:**
- Monitors person poses for fall indicators
- Implements multi-stage fall detection
- Tracks fall state (STANDING → FALLING → FALLEN → RECOVERY)
- Triggers alerts on confirmed falls

**Fall Detection Stages:**
1. **STANDING** - Normal upright position
2. **FALLING** - Rapid height decrease detected
3. **FALLEN** - Person on ground (confirmed)
4. **RECOVERY** - Getting back up

**Study Approach:**
1. Read the docstring - understand the state machine
2. Study the fall detection thresholds in settings.py
3. Deep dive into analyze() method
4. Understand state transitions
5. Study false positive prevention

**Key Concepts:**
- **Keypoint analysis:** Using hip/shoulder positions to detect orientation
- **Height tracking:** Monitoring vertical position changes
- **Temporal smoothing:** Requiring consistency over multiple frames
- **State machine:** Prevents false positives from single-frame glitches

**Key Questions:**
- What keypoints are used for fall detection?
- How is "height" calculated from keypoints?
- What thresholds trigger fall detection?
- How does the state machine prevent false positives?
- How long must a person be down to trigger an alert?

---

### 4.2 Ergonomic Analysis (Posture Assessment)

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `posture_analyzer.py` | 273 | ⭐⭐⭐ | RULA/REBA ergonomic scoring |
| `scoring.py` | 356 | ⭐⭐⭐ | RULA/REBA calculation algorithms |
| `angles.py` | 155 | ⭐⭐ | Angle calculation utilities |

**What PostureAnalyzer Does:**
- Calculates joint angles from pose keypoints
- Computes RULA (Rapid Upper Limb Assessment) score
- Computes REBA (Rapid Entire Body Assessment) score
- Identifies ergonomic risk levels (LOW, MEDIUM, HIGH)

**RULA vs REBA:**
- **RULA:** Focus on upper body (arms, wrists, neck)
- **REBA:** Whole body assessment (includes legs, trunk)

**Study Approach:**
1. Start with `angles.py` - understand angle calculations
2. Study RULA/REBA theory (Google: "RULA REBA ergonomics")
3. Deep dive into `scoring.py` - understand scoring algorithms
4. Study `posture_analyzer.py` - integration and thresholding

**Key Concepts:**
- **Joint angles:** Calculated from 3 keypoints (e.g., shoulder-elbow-wrist)
- **Risk zones:** Certain angles increase injury risk
- **Scoring tables:** Standard RULA/REBA lookup tables
- **Composite score:** Multiple angle scores combined

**Key Questions:**
- How are joint angles calculated from keypoints?
- What angles are considered risky?
- How is the final RULA/REBA score computed?
- What score thresholds trigger warnings?
- How often are posture assessments performed?

---

### 4.3 Proximity Detection

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `proximity_analyzer.py` | 116 | ⭐⭐⭐ | Person-vehicle distance monitoring |
| `calibration.py` | 136 | ⭐⭐ | Camera calibration for depth |

**What ProximityAnalyzer Does:**
- Detects dangerous proximity between people and vehicles (forklifts, etc.)
- Uses bounding box distance in pixels
- Optionally uses camera calibration for real-world distance
- Triggers alerts when people enter danger zones

**Danger Zones:**
- **CRITICAL:** < 1 meter
- **WARNING:** 1-2 meters
- **SAFE:** > 2 meters

**Study Approach:**
1. Understand pixel-based distance calculation
2. Study calibration.py for depth estimation
3. Learn danger zone thresholds
4. Understand temporal filtering (PROXIMITY_HOLD_FRAMES)

**Key Concepts:**
- **Bounding box distance:** Minimum distance between person and vehicle boxes
- **Camera calibration:** Converting pixels to real-world meters
- **Temporal filtering:** Requiring sustained proximity before alerting
- **Multi-object tracking:** Tracking multiple people and vehicles

**Key Questions:**
- How is distance calculated in pixels?
- How does calibration improve accuracy?
- What are the danger zone thresholds?
- How is temporal filtering implemented?
- How are vehicle types classified?

---

### 4.4 Event Aggregation & Track Quality

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `event_aggregator.py` | 174 | ⭐⭐⭐ | Collects and deduplicates events |
| `track_quality.py` | 255 | ⭐⭐ | Monitors detection quality |
| `capability_check.py` | ~80 | ⭐ | Feature availability checks |

**What EventAggregator Does:**
- Collects events from all analyzers (fall, posture, proximity)
- Deduplicates events (same person, same type)
- Assigns unique event IDs
- Prepares events for backend transmission

**What TrackQualityMonitor Does:**
- Monitors track stability (track ID changes)
- Measures keypoint quality
- Detects occlusions
- Filters unreliable detections

**Study Approach:**
1. Understand event deduplication logic
2. Study quality metrics
3. Learn how track stability is measured

**Key Questions:**
- How are duplicate events prevented?
- What makes a track "high quality"?
- When are detections filtered out?
- How does track stability affect analysis?

---

## 📚 LEVEL 5: Integration & Alerts - External Communication

### 5.1 Backend Integration

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `backend_client.py` | 442 | ⭐⭐⭐ | **LARGEST FILE** - Backend API communication |

**What BackendClient Does:**
- Sends events to backend REST API
- Implements offline queue (SQLite) when backend unavailable
- Handles authentication
- Retries failed requests
- Batches events for efficiency

**Offline Queue System:**
- Events stored in local SQLite DB when offline
- Automatically flushed when connection restored
- Prevents data loss during network outages

**Study Approach:**
1. Understand the offline queue architecture
2. Study event sending and retry logic
3. Learn authentication handling
4. Understand batching strategy

**Key Concepts:**
- **Offline-first design:** System works without backend
- **SQLite queue:** Local persistence
- **Exponential backoff:** Retry strategy
- **Event batching:** Multiple events per request

**Key Questions:**
- How does the offline queue work?
- What triggers queue flushing?
- How are authentication tokens managed?
- What happens if the backend is down for hours?
- How many events are batched together?

---

### 5.2 Alert System

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `alert_manager.py` | 554 | ⭐⭐⭐ | **LARGEST ALERT FILE** - Orchestrates alerts |
| `fcm_service.py` | 173 | ⭐⭐ | Firebase Cloud Messaging integration |
| `notification_service.py` | 191 | ⭐⭐ | Multi-channel notification routing |
| `siren_controller.py` | 185 | ⭐⭐ | Physical siren control (GPIO/relay) |

**What AlertManager Does:**
- Receives hazard events from analyzers
- Determines alert priority and channels
- Routes alerts to appropriate services (FCM, siren, email, etc.)
- Implements alert deduplication and cooldowns
- Tracks alert history

**Alert Channels:**
1. **FCM Push Notifications:** Mobile alerts
2. **Siren:** Physical audible alarm
3. **Backend API:** For dashboard display
4. (Future: Email, SMS, Slack, etc.)

**Study Approach:**
1. Start with `alert_manager.py` - understand orchestration
2. Study `fcm_service.py` - learn push notifications
3. Review `siren_controller.py` - understand hardware control
4. Check `notification_service.py` - see multi-channel routing

**Key Concepts:**
- **Alert deduplication:** Prevent alert spam
- **Cooldown periods:** Minimum time between repeated alerts
- **Priority-based routing:** Critical alerts use all channels
- **Firebase Admin SDK:** Server-side push notifications

**Key Questions:**
- How does alert deduplication work?
- What triggers a siren vs just a push notification?
- How long are alert cooldowns?
- How is Firebase configured?
- What happens if FCM is unavailable?

---

## 📚 LEVEL 6: UI & Visualization - Display Layer

### 6.1 Rendering System

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `renderer.py` | 207 | ⭐⭐⭐ | Main rendering orchestrator |
| `theme.py` | 89 | ⭐⭐ | Color schemes and styling |
| `drawing.py` | 184 | ⭐⭐ | Low-level drawing utilities |

**What SafetyOverlayRenderer Does:**
- Orchestrates multiple UI layers
- Renders detections, events, HUD, banners
- Applies theme configuration
- Manages draw order (layers)

**Study Approach:**
1. Understand layer architecture
2. Study rendering pipeline
3. Learn theme system
4. Check drawing utilities

---

### 6.2 UI Layers (src/ui/layers/)

| File | Lines | Purpose |
|------|-------|---------|
| `detections_layer.py` | ~100 | Draw bounding boxes and labels |
| `pose_layer.py` | ~120 | Draw skeleton keypoints |
| `hazards_layer.py` | ~100 | Highlight hazard events |
| `hud_layer.py` | ~150 | FPS, stats, metrics |
| `worker_panel_layer.py` | ~130 | Per-worker info panels |
| `zones_layer.py` | ~80 | Danger zones and regions |
| `banners_layer.py` | ~90 | Alert banners at top |

**Layer Rendering Order (bottom to top):**
1. Zones (danger zones, calibration regions)
2. Detections (bounding boxes)
3. Pose (skeletons)
4. Hazards (event highlights)
5. Worker panels (info boxes)
6. HUD (stats)
7. Banners (alerts)

**Study Approach:**
1. Start with `detections_layer.py` - simplest
2. Study `pose_layer.py` - keypoint rendering
3. Check `hazards_layer.py` - event visualization
4. Review other layers for completeness

**Key Concepts:**
- **Layer composition:** Each layer draws independently
- **Transparency:** Layers use alpha blending
- **Conditional rendering:** Layers enabled by profile
- **OpenCV drawing:** Using cv2.rectangle, cv2.circle, cv2.putText

**Key Questions:**
- How are layers composed?
- What colors represent different severity levels?
- How are skeletons drawn from keypoints?
- How are labels positioned?

---

## 📚 LEVEL 7: Advanced - Utilities & Optimization

### 7.1 Logging & Metrics

| File | Lines | Priority | Purpose |
|------|-------|----------|---------|
| `logger.py` | 66 | ⭐⭐ | Structured logging and metrics |

**What MetricsLogger Does:**
- Tracks FPS, inference time, event counts
- Structured JSON logging
- Performance monitoring
- Telemetry output

---

## 🎓 Recommended Study Sequence

### Week 1: Foundation
**Day 1-2:** Data models (Level 1.1)
- [ ] Read all files in `src/models/`
- [ ] Create a class diagram

**Day 3-4:** Configuration (Level 1.2)
- [ ] Study `settings.py` and `profile.py`
- [ ] Try modifying a profile

**Day 5-7:** Main pipeline (Level 2)
- [ ] Deep dive into `main.py`
- [ ] Trace the main loop execution
- [ ] Run with `--show` flag and observe

### Week 2: Core Detection
**Day 1-2:** Inference engine (Level 3.1)
- [ ] Study `inference_engine.py`
- [ ] Understand ByteTrack integration

**Day 3-4:** Streaming (Level 3.2)
- [ ] Study `stream_handler.py`
- [ ] Understand threading model

**Day 5-7:** Fall detection (Level 4.1)
- [ ] Deep dive into `hazard_analyzer.py`
- [ ] Trace a fall detection scenario
- [ ] Test with `demo_pipeline.py --part C`

### Week 3: Analysis & Safety
**Day 1-3:** Ergonomics (Level 4.2)
- [ ] Study `scoring.py` and `posture_analyzer.py`
- [ ] Learn RULA/REBA theory
- [ ] Test with real video

**Day 4-5:** Proximity (Level 4.3)
- [ ] Study `proximity_analyzer.py`
- [ ] Understand calibration
- [ ] Test with `demo_pipeline.py --part B`

**Day 6-7:** Event aggregation (Level 4.4)
- [ ] Study `event_aggregator.py`
- [ ] Understand deduplication

### Week 4: Integration & UI
**Day 1-2:** Backend integration (Level 5.1)
- [ ] Study `backend_client.py`
- [ ] Understand offline queue

**Day 3-4:** Alerts (Level 5.2)
- [ ] Study alert system files
- [ ] Understand FCM integration

**Day 5-7:** UI & Visualization (Level 6)
- [ ] Study rendering system
- [ ] Understand layer architecture
- [ ] Customize UI theme

---

## 🔍 Key Files Quick Reference

### Must-Read (Start Here):
1. **main.py** (700 lines) - Entry point and orchestration
2. **inference_engine.py** (400 lines) - Model and tracking
3. **hazard_analyzer.py** (338 lines) - Fall detection
4. **backend_client.py** (442 lines) - Backend communication
5. **alert_manager.py** (554 lines) - Alert orchestration

### Important Supporting Files:
6. **settings.py** (230 lines) - Configuration
7. **profile.py** (183 lines) - Profile system
8. **posture_analyzer.py** (273 lines) - Ergonomics
9. **scoring.py** (356 lines) - RULA/REBA algorithms
10. **stream_handler.py** (212 lines) - Frame acquisition

### Size by Category:
- **Largest:** `alert_manager.py` (554 lines)
- **Core Logic:** `hazard_analyzer.py` (338 lines)
- **Integration:** `backend_client.py` (442 lines)
- **Algorithms:** `scoring.py` (356 lines)

---

## 🛠️ Hands-On Exercises

### Exercise 1: Run and Observe
```bash
cd edge_ai
python src/main.py --source path/to/video.mp4 --cam-id cam_01 --show
```
**Goals:**
- Observe the UI rendering
- Watch FPS and inference time
- See detections and tracking in action

### Exercise 2: Modify Fall Thresholds
1. Edit `src/config/settings.py`
2. Change `FALL_HEIGHT_THRESHOLD_RATIO`
3. Test with `demo_pipeline.py --part C`
4. Observe how sensitivity changes

### Exercise 3: Create Custom Profile
1. Copy `profiles/fall_only.yaml`
2. Disable UI layers you don't need
3. Adjust thresholds
4. Test with `--profile your_profile`

### Exercise 4: Trace a Fall Event
1. Set breakpoints in `hazard_analyzer.py`
2. Run with debugger on fall video
3. Step through state machine
4. Observe state transitions

### Exercise 5: Study Offline Queue
1. Disconnect from backend
2. Generate events
3. Check SQLite database
4. Reconnect and observe flushing

---

## 📊 Code Metrics Summary

| Category | Files | Lines | Complexity |
|----------|-------|-------|------------|
| Core Pipeline | 2 | ~1100 | High |
| Analysis | 9 | ~1800 | High |
| Integration | 1 | ~440 | Medium |
| Alerts | 4 | ~1100 | Medium |
| UI/Rendering | 10 | ~800 | Low |
| Models/Data | 8 | ~400 | Low |
| Config | 4 | ~500 | Low |
| Utils | 3 | ~250 | Low |
| **Total** | **50** | **~6400** | **Medium-High** |

---

## 🎯 Learning Objectives Checklist

By the end of this study, you should be able to:

### Core Understanding:
- [ ] Explain the complete pipeline flow from camera to alert
- [ ] Describe how fall detection works in detail
- [ ] Explain RULA/REBA scoring algorithms
- [ ] Understand ByteTrack and object tracking
- [ ] Explain the offline queue mechanism

### Practical Skills:
- [ ] Run the pipeline with different profiles
- [ ] Modify detection thresholds
- [ ] Create custom profiles
- [ ] Debug issues with logging
- [ ] Add new UI layers

### Advanced Topics:
- [ ] Optimize inference performance
- [ ] Add new analysis modules
- [ ] Integrate new alert channels
- [ ] Implement custom calibration
- [ ] Add new detection models

---

## 💡 Pro Tips

1. **Start with `demo_pipeline.py`** - It shows all features in action
2. **Use `--show` flag** - Visual feedback helps understanding
3. **Read docstrings** - They're comprehensive and helpful
4. **Trace with print statements** - Add logging to follow execution
5. **Test incrementally** - Modify one thing, test, repeat
6. **Use profiles** - Disable features to simplify learning
7. **Study commits** - Git history shows design evolution
8. **Ask "why?"** - Understanding rationale is as important as "how"

---

## 🚀 Next Steps After Mastery

1. **Optimize performance** - Profile and improve FPS
2. **Add new detections** - Implement new safety features
3. **Improve accuracy** - Fine-tune thresholds and algorithms
4. **Multi-camera** - Study parallel processing
5. **Deploy to edge** - Set up on real hardware
6. **Contribute** - Fix bugs, add features, improve docs

---

Good luck with your studies! 🎓
