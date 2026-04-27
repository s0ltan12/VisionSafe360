# Model Specification 1 — PPE Detection (Helmet & Vest)
**Document Version:  **1.0
**Date:  **2026-02-18
**Author:  **VisionSafe360 AI Research Team
**Classification:  **Internal Technical Specification

## 1. Model Objective
### 1.1 Problem Statement
Personal Protective Equipment (PPE) non-compliance remains the leading contributing factor in preventable industrial fatalities. According to the U.S. Bureau of Labor Statistics (BLS), head injuries account for approximately 9% of all workplace fatalities, while high-visibility vest violations correlate with 17% of struck-by incidents in construction and manufacturing environments.
### 1.2 Detection Scope
The PPE detection model must identify and classify the following states for each detected worker in a video frame:

| Class ID | Class Name | Description                                    |
| -------- | ---------- | ---------------------------------------------- |
| 0        | person     | Human worker detected in scene                 |
| 1        | helmet_on  | Worker wearing a hard hat / safety helmet      |
| 2        | helmet_off | Worker not wearing required head protection    |
| 3        | vest_on    | Worker wearing high-visibility safety vest     |
| 4        | vest_off   | Worker not wearing required visibility garment |

### 1.3 Operational Requirements
- Must operate on live RTSP camera feeds at 15–30 FPS.
- Must handle multiple workers simultaneously (target: up to 20 persons per frame).
- Must function under real industrial CCTV conditions: variable lighting, occlusion, motion blur, camera angles from 3–15 meters distance.
- Must maintain detection reliability across diverse worker demographics (skin tone, body size, clothing variation).
### 1.4 Business Impact
Each missed violation represents a potential injury or regulatory fine. Each false alarm degrades operator trust and increases alert fatigue. The model must balance sensitivity (catching real violations) with precision (minimizing false alarms).

## 2. Industry Benchmark Research
### 2.1 Academic State-of-the-Art

| Study / System                                   | Year | Architecture     | Dataset Size  | mAP@0.5 | Recall | Notes                         |
| ------------------------------------------------ | ---- | ---------------- | ------------- | ------- | ------ | ----------------------------- |
| Wang et al., "PPE Detection using YOLOv5"        | 2022 | YOLOv5s          | 5,000 images  | 91.2%   | 88.4%  | Construction site, 3 classes  |
| Nath et al., "Deep Learning for PPE Compliance"  | 2020 | Faster R-CNN     | 10,000 images | 88.4%   | 84.7%  | Hard hat only                 |
| Delhi et al., "Helmet Detection in Construction" | 2020 | SSD MobileNet v2 | 5,000 images  | 83.9%   | 80.2%  | Mobile deployment             |
| Fang et al., "Detecting PPE with YOLO variants"  | 2023 | YOLOv8m          | 21,000 images | 93.7%   | 91.0%  | Multi-class PPE, construction |
| Li et al., "Lightweight PPE Detection on Edge"   | 2023 | YOLOv8n          | 8,500 images  | 89.1%   | 85.3%  | Jetson Nano deployment        |
| Otgonbold et al., "SHEL5K Benchmark"             | 2022 | YOLOv5m          | 5,000 images  | 90.4%   | 87.6%  | Standardized benchmark        |

### 2.2 Industrial Deployments (Reported)

| Vendor / System | Reported Accuracy | Latency        | Notes                                    |
| --------------- | ----------------- | -------------- | ---------------------------------------- |
| Intenseye       | > 95% (claimed)   | < 2 sec        | Cloud + Edge hybrid, proprietary dataset |
| Voxel AI        | > 92% (claimed)   | Real-time      | Multi-camera industrial                  |
| SmartVid.io     | > 90% (claimed)   | Near real-time | Construction-specific                    |
| Protex AI       | > 93% (claimed)   | < 1 sec        | Manufacturing floor deployment           |

**Note:** Vendor claims are marketing figures and typically measured on curated datasets. Real-world performance in novel environments is typically 5–10% lower.
### 2.3 Target Metrics for VisionSafe360
Given the benchmarks above, the following targets represent realistic, competitive, and aspirational goals:

| Metric              | Minimum Acceptable | Competitive Target | Best-in-Class |
| ------------------- | ------------------ | ------------------ | ------------- |
| mAP@0.5 (all PPE)   | 85.0%              | 91.0%              | 95.0%         |
| mAP@0.5:0.95        | 55.0%              | 65.0%              | 72.0%         |
| Recall (helmet_off) | 88.0%              | 93.0%              | 97.0%         |
| Recall (vest_off)   | 85.0%              | 90.0%              | 95.0%         |
| Precision (overall) | 82.0%              | 88.0%              | 93.0%         |
| Inference latency   | < 80 ms            | < 40 ms            | < 20 ms       |

## 3. Recommended Model Architecture
### 3.1 Architecture Comparison

| Architecture | mAP@0.5 (PPE) | FPS (Jetson Orin) | Model Size | Occlusion Handling | Training Ecosystem  |
| ------------ | ------------- | ----------------- | ---------- | ------------------ | ------------------- |
| YOLOv5s      | 89–91%        | 55–65 FPS         | 14 MB      | Moderate           | Mature, Ultralytics |
| YOLOv5m      | 91–93%        | 35–45 FPS         | 42 MB      | Good               | Mature, Ultralytics |
| YOLOv8n      | 87–89%        | 70–90 FPS         | 6.2 MB     | Moderate           | Latest, Ultralytics |
| YOLOv8s      | 90–92%        | 50–65 FPS         | 22 MB      | Good               | Latest, Ultralytics |
| YOLOv8m      | 92–94%        | 30–40 FPS         | 52 MB      | Very Good          | Latest, Ultralytics |
| YOLO-NAS-s   | 91–93%        | 45–55 FPS         | 30 MB      | Good               | Deci.ai, AutoNAC    |
| RT-DETR-l    | 93–95%        | 20–25 FPS         | 65 MB      | Excellent          | Transformer-based   |

### 3.2 Tradeoff Analysis
**YOLOv8s vs YOLOv8m:**
- YOLOv8s provides the best speed-accuracy tradeoff for edge deployment. It achieves within 2% mAP of the medium variant while running 60% faster on edge GPUs.
- YOLOv8m is preferred if the deployment hardware has sufficient compute (e.g., Jetson AGX Orin) and multi-camera processing is not required on a single device.
**YOLOv8 vs YOLO-NAS:**
- YOLO-NAS uses Neural Architecture Search to optimize the backbone automatically. It can achieve comparable accuracy to YOLOv8m at lower latency.
- However, YOLO-NAS has a less mature training ecosystem, fewer community resources, and more complex export pipelines.
- For a graduation project with limited time, YOLOv8 is the pragmatic choice due to Ultralytics' unified API, extensive documentation, and straightforward TensorRT export.
**RT-DETR (Transformer-based):**
- Achieves superior accuracy especially for small objects and occluded targets.
- However, the computational cost is 2–3x higher than YOLOv8s, making it impractical for multi-camera edge deployment.
- Not recommended for this project phase.
### 3.3 Recommendation
**Primary: YOLOv8s** (small variant)
Rationale:
- Achieves 90–92% mAP@0.5 on PPE benchmarks — within the competitive target range.
- Runs at 50–65 FPS on Jetson Orin Nano, leaving compute headroom for pose estimation in the same pipeline.
- 22 MB model size fits comfortably in edge GPU memory alongside other models.
- Ultralytics provides one-command export to ONNX and TensorRT.
- Extensive pre-trained COCO weights provide strong transfer learning foundation (person class already learned).
- Mature augmentation pipeline (Mosaic, MixUp, HSV augmentation) built into the training framework.
**Fallback: YOLOv8m** — if hardware budget allows Jetson AGX Orin or if accuracy on helmet_off class is below 90% with YOLOv8s after fine-tuning.

## 4. Dataset Strategy
### 4.1 Required Dataset Size
Based on the 5-class detection task with industrial variability:

| Phase                 | Images   | Annotations |
| --------------------- | -------- | ----------- |
| Initial Training      | 8,000    | ~35,000     |
| Validation            | 2,000    | ~8,500      |
| Test (held-out)       | 1,000    | ~4,500      |
| Domain Adaptation Set | 500–1000 | ~2,000      |
| Total                 | ~12,000  | ~50,000     |

### 4.2 Public Dataset Sources

| Dataset                   | Size   | Classes               | Quality |
| ------------------------- | ------ | --------------------- | ------- |
| SHEL5K (Safety Helmet)    | 5,000  | Helmet on/off, Person | High    |
| Hard Hat Workers (Kaggle) | 7,000  | Helmet, Head, Person  | Medium  |
| GDUT-HWD                  | 3,174  | Helmet, Head          | Medium  |
| Pictor-v3 (PPE)           | 2,496  | Helmet, Vest, Person  | High    |
| CHV Dataset               | 10,000 | Construction PPE      | High    |

### 4.3 Class Balance Strategy
PPE datasets inherently suffer from class imbalance — compliant workers (helmet_on, vest_on) significantly outnumber violators (helmet_off, vest_off) in most industrial footage.
**Target distribution:**

| Class      | Target % | Strategy                          |
| ---------- | -------- | --------------------------------- |
| person     | 100%     | Present in every image            |
| helmet_on  | 40–50%   | Natural prevalence                |
| helmet_off | 20–30%   | Oversample via augmentation       |
| vest_on    | 40–50%   | Natural prevalence                |
| vest_off   | 15–25%   | Oversample + synthetic generation |

**Techniques:**
- Class-aware sampling during training batch construction.
- Focal Loss to down-weight easy (compliant) examples and focus on hard (violation) cases.
- Copy-paste augmentation: paste helmet_off heads onto compliant worker bodies.
### 4.4 Data Augmentation Strategy

| Augmentation         | Purpose                                 | Parameters                  |
| -------------------- | --------------------------------------- | --------------------------- |
| Mosaic (4-image)     | Multi-scale learning, context diversity | Default YOLO mosaic         |
| MixUp                | Regularization, boundary smoothing      | alpha = 0.15                |
| HSV Shift            | Lighting robustness                     | H: ±0.015, S: ±0.7, V: ±0.4 |
| Random Perspective   | Camera angle variation                  | degrees=2, translate=0.1    |
| Random Flip          | Horizontal symmetry                     | p=0.5                       |
| Random Crop + Resize | Simulate distance variation             | scale: 0.5–1.5              |
| Motion Blur          | CCTV motion artifact simulation         | kernel: 3–7 pixels          |
| JPEG Compression     | Simulate low-quality CCTV encoding      | quality: 50–95              |
| Gaussian Noise       | Sensor noise in low-light               | sigma: 5–25                 |

### 4.5 Hard Negative Mining
After initial training, run inference on unlabeled industrial footage and collect:
- False positives: non-PPE objects detected as PPE (e.g., colored hair bands → helmet, colored shirts → vest).
- Hard negatives: crowded scenes, partially occluded workers, workers behind machinery.
Re-annotate these hard samples and add them to the training set for a second round of fine-tuning.
### 4.6 Synthetic Data Usage
- Use Blender or Unity to render synthetic workers with and without PPE in industrial environments.
- Synthetic data is most useful for rare classes (vest_off in dark environments).
- Recommended ratio: 70% real + 30% synthetic maximum (higher synthetic ratios degrade real-world performance).

## 5. Training Strategy
### 5.1 Transfer Learning Approach
1. **Stage 1 — Backbone Freeze:** Load YOLOv8s pre-trained on COCO. Freeze the backbone (first 10 layers) and train only the detection head for 20 epochs on the PPE dataset. Learning rate: 1e-3.
1. **Stage 2 — Full Fine-Tuning:** Unfreeze all layers. Train for 80–120 additional epochs with cosine annealing learning rate schedule. Initial LR: 1e-4, final LR: 1e-6.
1. **Stage 3 — Domain Adaptation:** Fine-tune for 10–15 epochs on site-specific data (captured from actual deployment cameras) with very low learning rate (1e-5).
### 5.2 Hyperparameter Configuration

| Parameter          | Recommended Value | Justification                                |
| ------------------ | ----------------- | -------------------------------------------- |
| Optimizer          | AdamW             | Better generalization than SGD on small data |
| Learning Rate      | 1e-3 → 1e-6       | Cosine annealing schedule                    |
| Batch Size         | 16–32             | Largest that fits in GPU memory              |
| Image Size         | 640 x 640         | Standard YOLO input, sufficient for PPE      |
| Weight Decay       | 0.0005            | Regularization                               |
| Warmup Epochs      | 3                 | Stable gradient initialization               |
| Label Smoothing    | 0.1               | Reduces overconfidence                       |
| Mosaic Probability | 1.0 (first 80%)   | Disable in last 20% of training              |
| Close Mosaic Epoch | Last 10 epochs    | Fine-grained feature learning                |

### 5.3 Loss Functions
YOLOv8 uses a composite loss:
- **Box Loss (CIoU):** Measures bounding box regression quality. CIoU penalizes center distance, aspect ratio, and overlap simultaneously.
- **Classification Loss (BCE with Focal weighting):** Binary cross-entropy per class with focal modulation (gamma=1.5) to handle class imbalance.
- **Distribution Focal Loss (DFL):** YOLOv8-specific loss for discrete probability distribution of box boundaries. Improves localization accuracy.
**Custom modification for PPE:**
- Increase cls loss weight from default 0.5 to 0.7 — classification accuracy matters more than pixel-perfect boxes for PPE compliance decisions.
### 5.4 Validation Strategy
- Use 80/10/10 split (train/validation/test).
- Monitor validation mAP@0.5 as the primary checkpoint criterion.
- Apply early stopping with patience of 20 epochs on validation loss.
- Final evaluation exclusively on the held-out test set (never used during training or hyperparameter tuning).
### 5.5 Cross-Validation Consideration
- Full k-fold cross-validation is computationally expensive for object detection.
- Recommended alternative: **stratified single split** with careful class distribution matching.
- If compute budget allows, perform 3-fold validation and report mean ± std of mAP.

## 6. Evaluation Metrics
### 6.1 Primary Metrics

| Metric       | Definition                                        | Priority |
| ------------ | ------------------------------------------------- | -------- |
| mAP@0.5      | Mean Average Precision at IoU threshold 0.5       | Highest  |
| mAP@0.5:0.95 | Mean AP averaged over IoU 0.5 to 0.95 (step 0.05) | High     |
| Recall@0.5   | True positive rate per class at IoU 0.5           | High     |

### 6.2 Secondary Metrics

| Metric        | Definition                            | Priority |
| ------------- | ------------------------------------- | -------- |
| Precision@0.5 | Positive predictive value per class   | Medium   |
| F1 Score      | Harmonic mean of precision and recall | Medium   |
| Per-class AP  | AP breakdown for each PPE class       | Medium   |

### 6.3 Operational Metrics

| Metric                    | Definition                           | Target       |
| ------------------------- | ------------------------------------ | ------------ |
| False Alarm Rate          | False positives per camera per hour  | < 2 per hour |
| Missed Violation Rate     | False negatives on actual violations | < 8%         |
| End-to-End Latency        | Frame capture → alert decision       | < 3 seconds  |
| Inference Latency (model) | Single frame inference time          | < 40 ms      |
| Throughput                | Frames per second per camera         | ≥ 15 FPS     |

### 6.4 Per-Class Target Thresholds

| Class      | Minimum AP@0.5 | Target AP@0.5 | Best-in-Class |
| ---------- | -------------- | ------------- | ------------- |
| person     | 90.0%          | 95.0%         | 98.0%         |
| helmet_on  | 85.0%          | 91.0%         | 95.0%         |
| helmet_off | 82.0%          | 89.0%         | 94.0%         |
| vest_on    | 84.0%          | 90.0%         | 94.0%         |
| vest_off   | 80.0%          | 87.0%         | 92.0%         |

## 7. Deployment Strategy
### 7.0 Development vs. Production Environments
The project follows a **laptop-first development** workflow. All training, testing, and demos are performed on a standard laptop/desktop with a CUDA GPU. Edge deployment (Jetson) is the final production target but is NOT required during development.

| Phase        | Hardware                  | Model Format    | Notes                                |
| ------------ | ------------------------- | --------------- | ------------------------------------ |
| Development  | Laptop/Desktop (CUDA GPU) | PyTorch (.pt)   | Full development, training, testing  |
| Demo/Testing | Laptop/Desktop            | PyTorch or ONNX | Real-time demo with webcam or video  |
| Production   | NVIDIA Jetson Orin Nano   | TensorRT FP16   | Final edge deployment (future phase) |

**Important:** All code, training, and inference work identically on laptop and edge. The only difference is the model export format for optimized performance on Jetson hardware.
### 7.1 Export Pipeline
**Development (laptop):** Use PyTorch .pt directly — no conversion needed.
**Production (edge):**

| PyTorch (.pt) → ONNX (.onnx) → TensorRT (.engine) |
| ------------------------------------------------- |

1. **ONNX Export:** yolo export model=best.pt format=onnx opset=17 simplify=True
1. **TensorRT Conversion:** Use trtexec or Ultralytics built-in TensorRT export with FP16 precision.
1. **Validation:** Compare ONNX and TensorRT outputs against PyTorch baseline — mAP drop must be < 0.5%.
### 7.2 Model Optimization Techniques

| Technique              | Expected Speedup | Accuracy Impact | Recommended |
| ---------------------- | ---------------- | --------------- | ----------- |
| FP16 Quantization      | 1.5–2.0x         | < 0.3% mAP drop | Yes         |
| INT8 Quantization      | 2.0–3.0x         | 0.5–2.0% drop   | Conditional |
| Structured Pruning     | 1.2–1.5x         | 0.5–1.5% drop   | Optional    |
| Knowledge Distillation | N/A (training)   | +1–2% accuracy  | Yes         |
| Channel Pruning (YOLO) | 1.3–1.8x         | 1.0–2.0% drop   | Optional    |

**Recommendation:**
- Deploy with **FP16 TensorRT** as the baseline — provides significant speedup with negligible accuracy loss.
- Use **INT8** only if FP16 does not meet the latency target on the specific edge hardware.
- Apply **knowledge distillation** during training: train YOLOv8s (student) using YOLOv8m (teacher) predictions as soft labels — this can recover 1–2% mAP.
### 7.3 Frame Scheduling
- Process every frame at full resolution is unnecessary and wasteful.
- Recommended strategy: **Adaptive frame skipping.**
- Normal mode: Process every 2nd frame (15 FPS effective from 30 FPS input).
- Alert mode: When a violation is detected, switch to every frame processing for the next 5 seconds to confirm and track the violator.
- Idle mode: If no persons are detected for 30 seconds, reduce to every 5th frame.

## 8. Risks & Mitigation
### 8.1 Common Failure Modes

| Failure Mode                      | Likelihood | Impact | Mitigation                                                  |
| --------------------------------- | ---------- | ------ | ----------------------------------------------------------- |
| Helmet misclassified as hard hat  | Medium     |        | Include diverse helmet types in dataset                     |
| Vest color confused with clothing | High       |        | Train with diverse clothing colors, not just neon yellow    |
| Small person at distance          | High       | Medium | Multi-scale training, smaller anchor sizes                  |
| Occluded worker behind machinery  | High       |        | Train with occlusion augmentation, track-based confirmation |
| Night / low-light conditions      | Medium     | High   | Low-light augmentation, IR camera support                   |
| Camera angle variation            | Medium     |        | Include top-down and side-angle data                        |
| Reflective surfaces / glare       | Low        | Medium | Glare augmentation in training pipeline                     |

### 8.2 Dataset Bias Risks
- **Geographic bias:** Most public PPE datasets are from East Asian or North American construction sites. Ensure representation of the target deployment region.
- **Demographic bias:** Model must perform equally across skin tones, body sizes, and gender. Validate with disaggregated metrics.
- **Seasonal bias:** Workers wear different underlayers in summer vs winter, changing the visual appearance of PPE compliance. Include seasonal variation.
### 8.3 False Positive Mitigation
- **Temporal smoothing:** Require a violation to persist for ≥ 3 consecutive frames before triggering an alert.
- **Confidence threshold tuning:** Set per-class confidence thresholds (not a single global threshold) optimized on the validation F1 curve.
- **Zone filtering:** Only trigger alerts in designated work zones, not in break areas or offices visible to the camera.

## 9. Final Performance Targets
### 9.1 Model Performance

| Metric              | Minimum | Target | Best-in-Class |
| ------------------- | ------- | ------ | ------------- |
| mAP@0.5 (all)       | 85.0%   | 91.0%  | 95.0%         |
| mAP@0.5:0.95 (all)  | 55.0%   | 65.0%  | 72.0%         |
| Recall (helmet_off) | 88.0%   | 93.0%  | 97.0%         |
| Recall (vest_off)   | 85.0%   | 90.0%  | 95.0%         |
| Precision (overall) | 82.0%   | 88.0%  | 93.0%         |
| F1 (overall)        | 83.0%   | 89.0%  | 94.0%         |

### 9.2 Operational Performance

| Metric                    | Minimum | Target  | Best-in-Class |
| ------------------------- | ------- | ------- | ------------- |
| Inference Latency         | < 80 ms | < 40 ms | < 20 ms       |
| End-to-End Latency        | < 5 sec | < 3 sec | < 1 sec       |
| False Alarms / cam / hour | < 5     | < 2     | < 0.5         |
| Throughput (FPS)          | ≥ 10    | ≥ 15    | ≥ 25          |
| Persons per Frame (max)   | 10      | 20      | 30+           |

### 9.3 Deployment Targets

| Parameter            | Target                               |
| -------------------- | ------------------------------------ |
| Model Format         | TensorRT FP16                        |
| Model Size (on disk) | < 25 MB                              |
| GPU Memory Usage     | < 500 MB                             |
| Dev Hardware         | Laptop/Desktop with CUDA GPU         |
| Edge Hardware        | NVIDIA Jetson Orin Nano (production) |
| Fallback Hardware    | NVIDIA Jetson Xavier NX              |

*End of Model 1 Specification — PPE Detection*
