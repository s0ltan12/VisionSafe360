# Model Specification 3 — Fall Detection
**Document Version:  **1.0
**Date:  **2026-02-18
**Author:  **VisionSafe360 AI Research Team
**Classification:  **Internal Technical Specification

## 1. Model Objective
### 1.1 Problem Statement
Falls are the leading cause of death in the construction industry and the second-leading cause of workplace fatalities overall (Bureau of Labor Statistics). In 2022, 700 workers died from falls in the U.S. alone. Beyond falls from heights (ladders, scaffolding), slip-and-fall incidents on the same level account for 27% of all workplace injuries (National Safety Council). Rapid detection of a fall event enables immediate medical response, which is critical — in cardiac arrest or head trauma cases, survival rates decrease by 10% for every minute without intervention.
### 1.2 Detection Scope
The model must detect when a person transitions from an upright/normal posture to a fallen state.
**Fall Event Types:**

| Type             | Description                                       | Severity |
| ---------------- | ------------------------------------------------- | -------- |
| Sudden Collapse  | Person collapses vertically (cardiac, heatstroke) | CRITICAL |
| Trip/Slip Fall   | Person trips and falls to the ground              | HIGH     |
| Gradual Fall     | Person slowly slumps to the ground (fatigue)      | HIGH     |
| Fall from Height | Person falls from elevated position               | CRITICAL |

**Non-Fall Events (must NOT trigger alert):**

| Event               | Description                                    |
| ------------------- | ---------------------------------------------- |
| Bending Down        | Person bends to pick up an object              |
| Sitting             | Person sits on a chair, crate, or ground       |
| Lying Intentionally | Worker resting during break in designated area |
| Crawling            | Worker crawling in confined space              |
| Kneeling            | Worker kneeling to perform a task              |

### 1.3 Technical Challenge
Fall detection is fundamentally a **temporal event recognition** problem, not a single-frame classification. The challenge is distinguishing between:
- Intentional transitions to ground level (bending, sitting, kneeling)
- Involuntary falls (sudden, uncontrolled descent)
This requires analyzing the **dynamics** of the person's movement — speed of descent, body orientation change rate, post-fall immobility — not just a single frame.
### 1.4 Business Impact
- Immediate emergency response (< 30 seconds from fall to alert) can be life-saving.
- Regulatory requirement in many jurisdictions for lone worker monitoring.
- Insurance premium reduction for facilities with automated fall detection.

## 2. Industry Benchmark Research
### 2.1 Approach Taxonomy
Fall detection methods are broadly categorized into three families:

| Category         | Description                                     | Pros                  | Cons                              |
| ---------------- | ----------------------------------------------- | --------------------- | --------------------------------- |
| Pose-based       | Use skeleton keypoints to analyze body geometry | Interpretable, robust | Requires accurate pose estimation |
| Appearance-based | CNN classifies frames as fall/no-fall           | Simple pipeline       | Poor temporal reasoning           |
| Spatiotemporal   | 3D CNNs or RNNs analyzing video clips           | Best accuracy         | High compute, latency             |

### 2.2 Academic State-of-the-Art

| Study                                        | Year | Approach                          | Accuracy | Precision | Recall | F1    | Dataset           |
| -------------------------------------------- | ---- | --------------------------------- | -------- | --------- | ------ | ----- | ----------------- |
| Tran et al., "SlowFast for Fall Detection"   | 2023 | SlowFast R50 (3D CNN)             | 97.8%    | 96.2%     | 97.1%  | 96.6% | UR Fall           |
| Chen et al., "YOLO-Pose + LSTM Fall"         | 2023 | Pose estimation + LSTM sequence   | 96.5%    | 95.1%     | 97.8%  | 96.4% | Multiple datasets |
| Kong et al., "Skeleton-based Fall Detection" | 2022 | ST-GCN on keypoints               | 97.2%    | 95.8%     | 96.9%  | 96.3% | NTU RGB+D 120     |
| Li et al., "Lightweight Fall Detection"      | 2023 | MoveNet + rule-based + CNN verify | 94.1%    | 93.0%     | 95.2%  | 94.1% | Custom industrial |
| Wang et al., "Two-stage Fall Detector"       | 2022 | YOLOv5 + aspect ratio + velocity  | 93.7%    | 91.5%     | 96.0%  | 93.7% | Le2i + custom     |

### 2.3 Key Insights from Literature
1. **Pose-based methods** achieve the best balance of accuracy and interpretability.
1. **Temporal analysis is essential** — single-frame methods suffer from high false positive rates (sitting/bending classified as falls).
1. **Two-stage approaches** (detect person → analyze fall) outperform single-stage on real-world data.
1. **The "lying on ground" verification** after initial fall detection reduces false positives by 30–50%.
1. **Real-world accuracy drops 5–15%** compared to lab datasets due to occlusion, varied clothing, and camera angles.
### 2.4 Fall Detection Datasets

| Dataset             | Samples | Environment  | Simulated/Real | Public  |
| ------------------- | ------- | ------------ | -------------- | ------- |
| UR Fall Detection   | 70      | Laboratory   | Simulated      | Yes     |
| Le2i Fall           | 221     | Home/office  | Simulated      | Yes     |
| MCFD (Multi-camera) | 24 seq  | Nursing home | Simulated      | Yes     |
| UP-Fall             | 850     | Laboratory   | Simulated      | Yes     |
| NTU RGB+D 120       | 114,480 | Laboratory   | Simulated      | Yes     |
| High-Quality Fall   | 520     | Varied       | Real + Sim     | Partial |

## 3. Recommended Model Architecture
### 3.1 Approach Comparison for Edge Deployment

| Approach                     | Edge Latency | Accuracy  | False Positive Rate | Complexity |
| ---------------------------- | ------------ | --------- | ------------------- | ---------- |
| SlowFast 3D CNN              | ~200 ms      | Very High | Low                 | Very High  |
| ST-GCN on keypoints          | ~100 ms      | Very High | Low                 | High       |
| Pose + LSTM                  | ~60 ms       | High      | Medium              |            |
| Pose + Rule-based            | ~40 ms       | Medium    | Medium-High         | Low        |
| Pose + Rule + CNN verify     | ~55 ms       | High      | Low                 | Medium     |
| Bounding box heuristics only | ~5 ms        | Low       | High                | Very Low   |

### 3.2 Recommended Architecture: Two-Stage Pose-Based Fall Detection
**Stage 1: Real-Time Fall Candidate Detection (every frame)**
Person Detection (YOLOv8s) → Pose Estimation (YOLO-Pose) → Geometric Rule Engine → Fall Candidate
The geometric rule engine analyzes per-frame pose features:

| Feature                   | Description                                       | Fall Indicator          |
| ------------------------- | ------------------------------------------------- | ----------------------- |
| Bounding Box Aspect Ratio | Width/Height of person bbox                       | > 1.0 (wider than tall) |
| Hip-to-Ground Height      | Normalized Y-coordinate of hip keypoint           | < 0.3 of initial height |
| Torso Angle               | Angle of shoulder-hip vector relative to vertical | > 60° from vertical     |
| Head Position             | Y-coordinate of head relative to body bbox        | Below hip level         |
| Vertical Velocity         | Frame-to-frame descent rate of centroid           | > threshold px/frame    |

**Stage 2: Temporal Verification (triggered by Stage 1)**
When Stage 1 flags a fall candidate, a temporal buffer of the last 1–2 seconds of pose data is analyzed:

| Temporal Feature     | Description                                       |
| -------------------- | ------------------------------------------------- |
| Descent Duration     | Time from upright to ground-level                 |
| Post-Fall Immobility | Person remains in ground position for > 3 seconds |
| Velocity Profile     | Sudden spike → deceleration (vs. gradual descent) |
| Pre-Fall Posture     | Was person upright immediately before?            |

**Decision Logic:**

| IF (aspect_ratio > 1.0) AND (hip_height < threshold) AND (descent_velocity > threshold):     fall_candidate = True      IF fall_candidate AND (immobile_duration > 3 seconds):     fall_confirmed = True → Trigger CRITICAL alert      IF fall_candidate AND (person resumes upright within 3 seconds):     fall_dismissed → Log as "stumble" event, WARNING alert |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

### 3.3 Pose Estimation Model Selection

| Model             | Keypoints | Latency (Jetson) | AP (COCO) | Edge Suitability |
| ----------------- | --------- | ---------------- | --------- | ---------------- |
| YOLO-Pose (v8s)   | 17        | ~35 ms           | 69.0      | Excellent        |
| MoveNet Lightning | 17        | ~12 ms           | 53.0      | Good             |
| MoveNet Thunder   | 17        | ~30 ms           | 64.0      | Good             |
| MediaPipe Pose    | 33        | ~25 ms           | N/A       | Good             |
| HRNet-W32         | 17        | ~120 ms          | 74.4      | Poor             |
| ViTPose-S         | 17        | ~80 ms           | 73.8      | Moderate         |

**Recommendation: YOLO-Pose (YOLOv8s-pose)**
Rationale:
- **Single model** performs both person detection AND pose estimation (no separate detector needed).
- Shares the same YOLOv8s backbone architecture as Models 1 and 2.
- Can potentially share early backbone features if models are unified.
- 17 COCO keypoints include all needed joints (ankles, knees, hips, shoulders, head).
- TensorRT-compatible for Jetson deployment.
### 3.4 Multi-Person Fall Detection
The system must handle multiple people simultaneously:
- YOLO-Pose natively detects multiple persons with individual pose estimates.
- ByteTrack assigns persistent IDs to maintain per-person fall state.
- Each tracked person has an independent fall-state machine: UPRIGHT → FALL_CANDIDATE → FALL_CONFIRMED → FALL_RESOLVED.

## 4. Dataset Strategy
### 4.1 Dataset Requirements
Unlike object detection, fall detection requires **video sequences**, not single images:

| Data Type                      | Quantity        | Purpose                   |
| ------------------------------ | --------------- | ------------------------- |
| Fall event videos              | 500 sequences   | Positive training samples |
| Normal activity videos         | 2,000 sequences | Negative samples          |
| Confusing activity videos      | 500 sequences   | Hard negatives            |
| Industrial environment footage | 300 sequences   | Domain adaptation         |
| Total                          | ~3,300 seq      |                           |

### 4.2 Confusing Activities (Hard Negatives)
These are critical for reducing false positives:

| Activity            | Frequency in Workplace | Fall Confusion Risk |
| ------------------- | ---------------------- | ------------------- |
| Bending to pick up  | Very High              | Medium              |
| Sitting on ground   | Medium                 | High                |
| Kneeling at machine | High                   | Medium              |
| Lying down (break)  | Low                    | Very High           |
| Climbing ladder     | Medium                 | Low                 |
| Pushing heavy load  | Medium                 | Low                 |
| Stretching          | Low                    | Medium              |

### 4.3 Data Collection Strategy
**Phase 1: Public Dataset Compilation**
- Combine UR Fall, Le2i, UP-Fall datasets for initial training.
- Extract person pose sequences using YOLO-Pose.
**Phase 2: Simulated Industrial Falls**
- Record 200+ simulated fall events on-site with volunteers.
- Include variations: forward fall, backward fall, sideways fall, collapse.
- Record from the exact camera angles and heights used in deployment.
**Phase 3: Normal Activity Recording**
- Record 1,000+ normal work activity sequences from deployment cameras.
- Label activities: walking, bending, sitting, kneeling, carrying, etc.
**Phase 4: Continuous Learning**
- After deployment, flag all false positives/negatives for human review.
- Retrain quarterly with corrected labels.
### 4.4 Pose Data Augmentation

| Augmentation            | Description                                      |
| ----------------------- | ------------------------------------------------ |
| Temporal Speed Jitter   | Speed up / slow down fall sequences (0.5x–2.0x)  |
| Keypoint Noise          | Add Gaussian noise to keypoint positions (σ=3px) |
| Mirror                  | Horizontal flip of all sequences                 |
| Camera Angle Simulation | Adjust keypoint positions for different angles   |
| Partial Occlusion       | Randomly drop 2–3 keypoints per frame            |

## 5. Training Strategy
### 5.1 Two-Component Training
**Component A: Pose Estimation (YOLO-Pose)**
- Use pre-trained YOLOv8s-pose weights (trained on COCO).
- Fine-tune on industrial environment images for 20–30 epochs.
- Focus on improving pose accuracy for unusual body positions (bent, crouching, on ground).
**Component B: Fall Classifier (if using learned approach)**
- Input: Sequence of 30–60 frames of normalized pose keypoints (17 joints × 2 coordinates × T frames).
- Architecture: Lightweight 1D-CNN or 2-layer LSTM.
- Binary classification: fall / not-fall.
- Train on pose sequences extracted from video datasets.
### 5.2 Rule-Based vs. Learned Classifier

| Aspect               | Rule-Based              | Learned (LSTM/1D-CNN) |
| -------------------- | ----------------------- | --------------------- |
| Training data needed | None (hand-tuned)       | 1,000+ sequences      |
| Interpretability     | Full                    | Partial               |
| Accuracy             | 88–92%                  | 94–97%                |
| False positive rate  | 5–10%                   | 2–5%                  |
| Edge compute         | Negligible              | 3–10 ms               |
| Adaptability         | Manual threshold tuning | Retraining            |

**Recommendation: Start with rule-based, upgrade to learned classifier in V2.**
The rule-based approach is faster to deploy, fully interpretable (critical for safety certification), and can be tuned on-site without retraining. Once sufficient real-world data is collected (3–6 months of deployment), train a lightweight LSTM classifier for improved accuracy.
### 5.3 Threshold Calibration
The rule-based system has tunable thresholds that should be calibrated per-site:

| Threshold                   | Default Value | Calibration Method                                |
| --------------------------- | ------------- | ------------------------------------------------- |
| Aspect Ratio (fall)         | > 1.0         | Adjust for camera angle                           |
| Hip Height (normalized)     | < 0.30        | Measure average person height                     |
| Vertical Velocity           | > 15 px/frame | Scale with camera FPS and resolution              |
| Immobility Duration         | > 3 seconds   | Adjust for industry (shorter for high-risk zones) |
| Torso Angle (from vertical) | > 60°         | Consistent across sites                           |

### 5.4 Training Epochs & Schedule (for Learned Classifier)

| Phase             | Epochs | Learning Rate | Description              |
| ----------------- | ------ | ------------- | ------------------------ |
| Initial Training  | 50     | 1e-3          | Train on public datasets |
| Fine-Tuning       | 30     | 1e-4          | Fine-tune on site data   |
| Continuous Update | 10     | 5e-5          | Quarterly retraining     |

## 6. Evaluation Metrics
### 6.1 Primary Metrics

| Metric               | Definition                                     | Priority |
| -------------------- | ---------------------------------------------- | -------- |
| Sensitivity (Recall) | % of actual falls correctly detected           | CRITICAL |
| Specificity          | % of non-fall events correctly classified      | HIGH     |
| False Alarm Rate     | Number of false fall alerts per camera per day | HIGH     |
| Detection Latency    | Time from fall onset to alert                  | HIGH     |

### 6.2 Confusion Matrix Targets

|                 | Predicted: Fall | Predicted: No Fall |
| --------------- | --------------- | ------------------ |
| Actual: Fall    | TP (> 95%)      | FN (< 5%)          |
| Actual: No Fall | FP (< 3%)       | TN (> 97%)         |

### 6.3 Operational Metrics

| Metric                      | Definition                               | Target                 |
| --------------------------- | ---------------------------------------- | ---------------------- |
| Mean Detection Time         | Average seconds from fall onset to alert | < 5 seconds            |
| Maximum Detection Time      | Worst-case fall detection latency        | < 10 seconds           |
| False Alarms Per Camera/Day | Number of false fall alerts per day      | < 5                    |
| Fall Detection Rate (24h)   | % of falls detected during day AND night | > 95% day, > 85% night |

### 6.4 Performance Targets

| Metric                    | Minimum | Target | Best-in-Class |
| ------------------------- | ------- | ------ | ------------- |
| Sensitivity (Fall Recall) | 90.0%   | 95.0%  | 98.0%         |
| Specificity               | 92.0%   | 97.0%  | 99.0%         |
| F1 Score                  | 90.0%   | 95.0%  | 97.0%         |
| Detection Latency         | < 10 s  | < 5 s  | < 3 s         |
| False Alarms per cam/day  | < 10    | < 5    | < 1           |

## 7. Deployment Strategy
### 7.0 Development vs. Production Environments
Same laptop-first workflow as Models 1 and 2. All training, testing, and demos run on a laptop/desktop GPU. Edge deployment is the future production target.

| Phase        | Hardware                  | Model Format    | Notes                                |
| ------------ | ------------------------- | --------------- | ------------------------------------ |
| Development  | Laptop/Desktop (CUDA GPU) | PyTorch (.pt)   | Full development, training, testing  |
| Demo/Testing | Laptop/Desktop            | PyTorch or ONNX | Real-time demo with webcam or video  |
| Production   | NVIDIA Jetson Orin Nano   | TensorRT FP16   | Final edge deployment (future phase) |

### 7.1 Pipeline Latency Budget

| Component                         | Latency |
| --------------------------------- | ------- |
| YOLOv8s-Pose inference (TensorRT) | ~35 ms  |
| ByteTrack update                  | ~3 ms   |
| Geometric feature extraction      | < 1 ms  |
| Rule-based fall decision          | < 1 ms  |
| Total per frame                   | ~40 ms  |

The temporal verification (immobility check) operates over accumulated state, not per-frame — no additional compute.
### 7.2 Model Export

| Format        | Size   | Latency (Jetson Orin Nano) |
| ------------- | ------ | -------------------------- |
| PyTorch (.pt) | ~25 MB | ~80 ms                     |
| ONNX          | ~22 MB | ~55 ms                     |
| TensorRT FP16 | ~14 MB | ~35 ms                     |

### 7.3 State Machine on Edge
Each tracked person maintains a fall state machine on-device:

| UPRIGHT ──(fall indicators triggered)──► FALL_CANDIDATE FALL_CANDIDATE ──(immobile > 3s)──► FALL_CONFIRMED ──► Alert triggered FALL_CANDIDATE ──(person stands up)──► UPRIGHT (log as "stumble") FALL_CONFIRMED ──(manual reset by operator)──► UPRIGHT |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

State transitions are logged and sent to the backend as HazardEvent instances.
### 7.4 Night/Low-Light Considerations
Fall detection must work 24/7. Strategies:

| Challenge            | Mitigation                                   |
| -------------------- | -------------------------------------------- |
| Low ambient light    | IR-compatible cameras (most industrial CCTV) |
| Poor pose estimation | Increase keypoint confidence threshold       |
| Shadows/artifacts    | Train on low-light augmented data            |
| Thermal cameras      | Fine-tune pose model on thermal imagery (V2) |

## 8. Risks & Mitigation
### 8.1 Risk Matrix

| Risk                                        | Likelihood | Impact | Mitigation                                             |
| ------------------------------------------- | ---------- | ------ | ------------------------------------------------------ |
| Bending classified as fall (false alarm)    | High       | Medium | Temporal verification (3s immobility requirement)      |
| Person sitting on ground triggers alert     | Medium     |        | Designated rest zone exclusion, gradual descent filter |
| Occluded person — missed keypoints          | High       |        | Fall back to bounding box aspect ratio analysis        |
| Night / poor lighting reduces accuracy      | Medium     | High   | IR cameras, low-light training augmentation            |
| Slip-and-recovery missed (brief fall)       | Medium     | Low    | Log as "stumble" event, lower severity alert           |
| Person already on ground when camera starts | Low        | Medium | Initial state assumes standing, ignore static poses    |
| Multiple people occluding each other        | Medium     | High   | Per-person tracking, require minimum keypoint count    |
| Camera angle too steep (top-down view)      | Low        | High   | Vertical velocity less meaningful; use area change     |

### 8.2 Critical Safety Considerations
- **This is a life-safety system.** False negatives (missed falls) are categorically worse than false positives (false alarms).
- The system should **never** be the sole fall protection measure — it supplements, not replaces, physical safety systems (guardrails, harnesses, buddy systems).
- Alert escalation: if no operator acknowledgment within 60 seconds of a FALL_CONFIRMED alert, automatically escalate to emergency contacts and/or trigger audible siren.
### 8.3 Liability & Certification
- Document all detection capabilities and limitations clearly for facility operators.
- Do NOT market as "100% fall detection" — state measured sensitivity and conditions tested.
- Include clear disclaimer that the system is an aid, not a replacement for safety protocols.
- Consider IEC 62443 (industrial cybersecurity) and ISO 13849 (safety of machinery) compliance paths.

## 9. Final Performance Targets
### 9.1 Model Performance

| Metric                    | Minimum | Target | Best-in-Class |
| ------------------------- | ------- | ------ | ------------- |
| Fall Sensitivity (Recall) | 90.0%   | 95.0%  | 98.0%         |
| Specificity               | 92.0%   | 97.0%  | 99.0%         |
| F1 Score                  | 90.0%   | 95.0%  | 97.0%         |
| Detection Latency         | < 10 s  | < 5 s  | < 3 s         |
| False Alarms per cam/day  | < 10    | < 5    | < 1           |

### 9.2 Operational Performance

| Metric            | Minimum | Target  | Best-in-Class |
| ----------------- | ------- | ------- | ------------- |
| Pipeline Latency  | < 80 ms | < 45 ms | < 30 ms       |
| 24/7 Uptime       | 95%     | 99%     | 99.9%         |
| Night Sensitivity | 80%     | 90%     | 95%           |
| Throughput (FPS)  | ≥ 10    | ≥ 20    | ≥ 30          |

### 9.3 Deployment Targets

| Parameter            | Target                                 |
| -------------------- | -------------------------------------- |
| Pose Model           | YOLOv8s-Pose (TensorRT FP16)           |
| Fall Classifier (V1) | Rule-based geometric + temporal engine |
| Fall Classifier (V2) | Lightweight LSTM (< 1 MB)              |
| Combined Model Size  | < 15 MB                                |
| State per Person     | ~100 bytes (keypoint history buffer)   |
| Dev Hardware         | Laptop/Desktop with CUDA GPU           |
| Edge Hardware        | NVIDIA Jetson Orin Nano (production)   |

*End of Model 3 Specification — Fall Detection*
