# VisionSafe 360 — Edge AI Module

Real-time industrial safety monitoring using computer vision and AI.

## 🎯 Features

- **Fall Detection** — Real-time detection of worker falls using pose estimation
- **PPE Compliance** — Detection of safety helmets, vests, and other equipment
- **Forklift Proximity** — Alert when workers are too close to moving vehicles
- **Ergonomic Analysis** — Assessment of worker posture and repetitive strain risks
- **Multi-Camera Support** — Process multiple RTSP/video streams simultaneously
- **Offline Resilience** — Queue events when backend is unavailable

## 📋 Requirements

- Python 3.10+
- NVIDIA GPU with CUDA 12.x (RTX 4050+ recommended)
- 6GB+ VRAM

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd edge_ai
pip install -r requirements.txt
```

### 2. Run with Video File

```bash
python -m src.main --source path/to/video.mp4 --profile full_suite --show
```

### 3. Run with RTSP Stream

```bash
python -m src.main --source rtsp://camera_ip:554/stream --profile full_suite
```

## 📁 Project Structure

```
edge_ai/
├── src/
│   ├── main.py                    # Entry point & orchestrator
│   ├── config/
│   │   ├── settings.py            # All configuration constants
│   │   ├── profile.py             # Profile loading
│   │   └── inference/
│   │       └── inference_engine.py # YOLO + ByteTrack engine
│   ├── streaming/
│   │   └── stream_handler.py      # RTSP/video stream handling
│   ├── analysis/
│   │   ├── hazard_analyzer.py     # PPE, proximity, fall detection
│   │   ├── posture_analyzer.py    # Ergonomic risk assessment
│   │   ├── proximity_analyzer.py  # Vehicle-person distance
│   │   ├── event_aggregator.py    # Event deduplication
│   │   └── calibration.py         # Camera calibration
│   ├── alerts/
│   │   ├── alert_manager.py       # Alert routing
│   │   ├── fcm_service.py         # Firebase notifications
│   │   └── siren_controller.py    # Physical siren control
│   ├── integration/
│   │   └── backend_client.py      # Backend API client
│   ├── models/
│   │   ├── detection.py           # Detection dataclass
│   │   └── frame_bundle.py        # Frame container
│   ├── ui/
│   │   └── renderer.py            # Annotation rendering
│   └── utils/
│       ├── logger.py              # Logging setup
│       └── drawing.py             # CV2 drawing utilities
├── weights/                       # Model weights
│   ├── yolo11n-pose.pt           # Pose estimation model
│   ├── ppe/
│   │   └── best_ppe.pt           # PPE detection model (SH17)
│   └── forklift/
│       └── best_forklift.pt      # Forklift detection model
├── calibration/                   # Camera calibration files
│   └── calibration_tool.py       # Calibration utility
├── configs/
│   └── sh17_classes.yaml         # PPE class definitions
├── profiles/                      # Feature profiles
│   ├── full_suite.yaml           # All features enabled
│   ├── ppe_only.yaml             # PPE detection only
│   └── fall_only.yaml            # Fall detection only
├── eval/                          # Evaluation harness
│   └── run.py                    # Offline evaluation
└── tests/                         # Unit tests
```

## ⚙️ Configuration

### Profiles

Profiles control which features are enabled:

```yaml
# profiles/full_suite.yaml
pose:
  enabled: true
  schedule: 1
hazard_analyzer:
  enabled: true
  ppe:
    enabled: true
    schedule: 3
  proximity:
    enabled: true
    schedule: 1
  fall:
    enabled: true
    schedule: 1
posture_analyzer:
  enabled: true
  schedule: 10
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VISIONSAFE_DEBUG` | `false` | Enable debug logging |
| `VISIONSAFE_BACKEND_URL` | `http://localhost:8000` | Backend API URL |
| `VISIONSAFE_BACKEND_EVENTS_ENABLED` | `true` | Send events to backend |
| `VISIONSAFE_FCM_ENABLED` | `false` | Enable Firebase notifications |
| `VISIONSAFE_SIREN_ENABLED` | `false` | Enable physical siren |

## 📊 Model Weights

### Required Models

| Model | Path | Purpose |
|-------|------|---------|
| Pose | `weights/yolo11n-pose.pt` | Person detection + keypoints |
| PPE | `weights/ppe/best_ppe.pt` | Safety equipment detection |
| Forklift | `weights/forklift/best_forklift.pt` | Vehicle detection |

### PPE Classes (SH17 Dataset)

```
0: person, 1: ear, 2: ear-mufs, 3: face, 4: face-guard,
5: face-mask, 6: foot, 7: tool, 8: glasses, 9: gloves,
10: helmet, 11: hands, 12: head, 13: medical-suit,
14: shoes, 15: safety-suit, 16: safety-vest
```

## 🎥 Camera Calibration

For accurate proximity measurements, calibrate each camera:

```bash
python calibration/calibration_tool.py --camera cam_01 --video path/to/video.mp4
```

This creates a homography matrix for perspective correction.

## 🧪 Testing

```bash
# Run unit tests
python -m pytest tests/ -v

# Run evaluation on test clips
python -m eval.run --clips eval/clips/*.mp4 --profile full_suite
```

## 📈 Performance

On RTX 4050 (6GB VRAM):

| Metric | Value |
|--------|-------|
| Inference FPS | 15-20 Hz |
| Pose Latency | ~25ms |
| PPE Latency | ~15ms |
| VRAM Usage | ~2.5GB |
| Track Coverage | >85% |

## 🔧 Troubleshooting

### CUDA Out of Memory

```bash
# Reduce batch size / image size
export VISIONSAFE_IMGSZ=480
```

### Stream Connection Issues

```bash
# Increase timeout
export VISIONSAFE_RTSP_TIMEOUT_SEC=30
```

### No Detections

1. Check model weights exist in `weights/`
2. Verify profile enables required features
3. Check confidence thresholds in `settings.py`

## 📄 License

Proprietary — VisionSafe 360 Graduation Project

## 👥 Contributors

- Hisham Mohamed
- Mohamed Soltan
- Raneem 
- jhon 
- shames
