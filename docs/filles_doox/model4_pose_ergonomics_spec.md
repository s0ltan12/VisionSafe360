# Model Specification 4 — Pose Estimation & Ergonomic Risk Assessment (RULA/REBA)
**Document Version:  **1.0
**Date:  **2026-02-18
**Author:  **VisionSafe360 AI Research Team
**Classification:  **Internal Technical Specification

## 1. Model Objective
### 1.1 Problem Statement
Musculoskeletal disorders (MSDs) account for 33% of all workplace injuries (Bureau of Labor Statistics) and cost U.S. employers over $20 billion annually in direct workers' compensation costs. MSDs develop gradually from sustained awkward postures, repetitive motions, and forceful exertions — making them invisible until the damage is done. Unlike acute hazards (falls, collisions), ergonomic risks are chronic and cumulative, requiring continuous monitoring rather than event detection.
Traditional ergonomic assessments (RULA/REBA) are conducted manually by trained ergonomists using observation checklists. This approach is expensive ($500–$2,000 per assessment), infrequent (annually or quarterly), and captures only a snapshot rather than the worker's habitual posture.
### 1.2 Detection Scope
The system must continuously estimate worker posture from video and compute real-time ergonomic risk scores.
**Ergonomic Assessment Frameworks:**

| Framework | Full Name                    | Focus Area               | Score Range | Risk Levels                                                                |
| --------- | ---------------------------- | ------------------------ | ----------- | -------------------------------------------------------------------------- |
| RULA      | Rapid Upper Limb Assessment  | Upper body, arms, wrists | 1–7         | 1–2: Acceptable, 3–4: Investigate, 5–6: Change soon, 7: Change immediately |
| REBA      | Rapid Entire Body Assessment | Full body, load handling | 1–15        | 1: Negligible, 2–3: Low, 4–7: Medium, 8–10: High, 11–15: Very High         |

### 1.3 Body Angles Required

| Joint Angle                 | RULA | REBA | Description                            |
| --------------------------- | ---- | ---- | -------------------------------------- |
| Neck Flexion/Extension      | ✓    |      | Forward/backward tilt of the head      |
| Neck Side Bend              | ✓    |      | Lateral tilt of the head               |
| Trunk Flexion/Extension     | ✓    |      | Forward lean of the torso              |
| Trunk Side Bend             | ✓    |      | Lateral bend of the torso              |
| Trunk Twist                 | ✓    |      | Rotational twist of the torso          |
| Upper Arm Flexion/Extension | ✓    |      | Shoulder angle (arm raised/lowered)    |
| Upper Arm Abduction         | ✓    |      | Arm raised sideways                    |
| Shoulder Raise              | ✓    |      | Shoulder shrugged upward               |
| Lower Arm Flexion           | ✓    |      | Elbow bend angle                       |
| Wrist Flexion/Extension     | ✓    |      | Wrist bend up/down                     |
| Wrist Deviation             | ✓    |      | Wrist lateral bend                     |
| Leg Position (support)      |      | ✓    | Standing balanced, unbalanced, sitting |
| Knee Flexion                |      | ✓    | Knee bend angle                        |
| Load/Force                  |      | ✓    | Weight being handled                   |

### 1.4 Business Impact
- Prevent long-term MSDs that result in permanent disability and lost-time injuries.
- Reduce workers' compensation claims (average MSD claim: $32,000).
- Provide continuous ergonomic monitoring instead of periodic manual assessments.
- Generate quantitative ergonomic reports for OSHA compliance and insurance documentation.
- Enable data-driven workstation design improvements.

## 2. Industry Benchmark Research
### 2.1 Vision-Based Ergonomic Assessment — State of the Art

| Study                                              | Year | Pose Model     | RULA/REBA | Angle Error | Score Accuracy | Environment   |
| -------------------------------------------------- | ---- | -------------- | --------- | ----------- | -------------- | ------------- |
| Antwi-Afari et al., "Deep Learning for Ergonomics" | 2023 | OpenPose       | RULA      | ±8.5°       | 78%            | Lab           |
| Li et al., "Automated REBA using MediaPipe"        | 2023 | MediaPipe Pose | REBA      | ±6.2°       | 82%            | Construction  |
| Yu et al., "Real-time Ergonomic Assessment"        | 2022 | HRNet-W48      | RULA+REBA | ±5.1°       | 86%            | Manufacturing |
| Kim et al., "Vision-based RULA Assessment"         | 2023 | YOLO-Pose      | RULA      | ±7.8°       | 80%            | Assembly line |
| Zhang et al., "Continuous Posture Monitoring"      | 2024 | ViTPose        | REBA      | ±4.5°       | 88%            | Lab + Field   |

### 2.2 Key Research Findings
1. **Angle accuracy is the bottleneck.** RULA/REBA scoring is sensitive to joint angles — a 10° error in trunk flexion can shift the score by 1–2 levels.
1. **2D pose estimation introduces systematic errors** due to perspective projection — a person facing sideways has foreshortened limbs that distort angle measurements.
1. **3D pose estimation** (lifting 2D keypoints to 3D) significantly improves angle accuracy but adds complexity and latency.
1. **Temporal averaging** of angles (over 5–10 seconds) reduces noise and improves score stability without affecting clinical relevance.
1. **Camera viewing angle matters.** Frontal and 45° views provide the best angle estimates; top-down views are nearly useless for ergonomic assessment.
### 2.3 Pose Estimation Model Comparison

| Model           | Keypoints | 2D AP (COCO) | 3D MPJPE (mm) | Latency (Jetson) | Suitability           |
| --------------- | --------- | ------------ | ------------- | ---------------- | --------------------- |
| MediaPipe Pose  | 33        | ~75*         | ~80*          | ~25 ms           | Good (more keypoints) |
| YOLO-Pose (v8s) | 17        | 69.0         | N/A (2D only) | ~35 ms           | Good (integrated det) |
| YOLO-Pose (v8m) | 17        | 71.2         | N/A (2D only) | ~55 ms           | Moderate              |
| HRNet-W32       | 17        | 74.4         | ~52           | ~120 ms          | Poor (too slow)       |
| HRNet-W48       | 17        | 75.1         | ~48           | ~160 ms          | Poor (too slow)       |
| ViTPose-S       | 17        | 73.8         | ~55           | ~80 ms           | Moderate              |
| MoveNet Thunder | 17        | 64.0         | N/A           | ~30 ms           | Good                  |

*MediaPipe uses a non-standard evaluation; approximate equivalent values shown.
### 2.4 Critical Insight: Keypoint Sufficiency
Standard COCO 17-keypoint format:

| Keypoint   | Available | Needed for RULA  | Needed for REBA |
| ---------- | --------- | ---------------- | --------------- |
| Nose       | ✓         | Neck estimation  |                 |
| Eyes (L/R) | ✓         | Head orientation |                 |
| Ears (L/R) | ✓         | Head orientation |                 |
| Shoulders  | ✓         | ✓ Upper arm      | ✓ Trunk, arms   |
| Elbows     | ✓         | ✓ Lower arm      |                 |
| Wrists     | ✓         | ✓ Wrist          |                 |
| Hips       | ✓         | ✓ Trunk angle    |                 |
| Knees      | ✓         | —                | ✓ Leg score     |
| Ankles     | ✓         | —                | ✓ Leg score     |

**Conclusion:** COCO 17 keypoints are **sufficient** for both RULA and REBA computation. Wrist deviation (RULA) cannot be directly measured from these keypoints — estimate from wrist-to-forearm alignment or default to neutral.

## 3. Recommended Model Architecture
### 3.1 Overall Pipeline

| YOLO-Pose (detect + pose) → Angle Calculator → RULA/REBA Scorer → Temporal Aggregator → Risk Alert |
| -------------------------------------------------------------------------------------------------- |

### 3.2 Component Selection

| Component            | Choice                    | Justification                                                   |
| -------------------- | ------------------------- | --------------------------------------------------------------- |
| Pose Estimation      | YOLOv8s-Pose              | Shared with Fall Detection (Model 3), integrated detection+pose |
| Angle Calculation    | Geometric (trigonometric) | Deterministic, no training needed                               |
| RULA/REBA Scoring    | Algorithmic               | Follows published scoring tables exactly                        |
| Temporal Aggregation | Sliding window avg        | 10-second window, smooths pose noise                            |
| Risk Alerting        | Threshold-based           | Alert when sustained RULA ≥ 5 or REBA ≥ 8                       |

### 3.3 Why Not a Separate Pose Model?
Model 3 (Fall Detection) already uses YOLOv8s-Pose. Ergonomic assessment can run on the **exact same pose output** — no additional inference is needed. The ergonomic analysis is purely computational:

| Processing Step                  | Additional Compute |
| -------------------------------- | ------------------ |
| Angle calculation (trigonometry) | < 0.5 ms           |
| RULA score computation           | < 0.1 ms           |
| REBA score computation           | < 0.1 ms           |
| Temporal averaging               | < 0.1 ms           |
| Total additional latency         | < 1 ms             |

### 3.4 Angle Calculation Method
Each body angle is computed from three keypoints using the law of cosines:
**Example — Trunk Flexion Angle:**
- Keypoints: shoulder (S), hip (H), knee (K) or virtual vertical reference
- Vector A: Hip → Shoulder
- Vector B: Hip → Vertical (0, -1) i.e., straight up
- Angle θ = arccos((A · B) / (|A| × |B|))
**All Required Angles:**

| Angle           | Keypoints Used                                | Computation                          |
| --------------- | --------------------------------------------- | ------------------------------------ |
| Neck Flexion    | Nose, Mid-Shoulder, Mid-Hip                   | Angle of nose-shoulder from vertical |
| Trunk Flexion   | Mid-Shoulder, Mid-Hip, vertical ref           | Angle of trunk from vertical         |
| Trunk Side Bend | Left-Shoulder, Right-Shoulder, horizontal ref | Tilt of shoulder line                |
| Upper Arm Angle | Elbow, Shoulder, Hip (same side)              | Shoulder flexion angle               |
| Lower Arm Angle | Wrist, Elbow, Shoulder (same side)            | Elbow flexion angle                  |
| Wrist Angle     | Wrist, Elbow, fingers (estimated)             | Wrist deviation from forearm axis    |
| Knee Angle      | Hip, Knee, Ankle (same side)                  | Knee flexion angle                   |

"Mid-Shoulder" = midpoint of left and right shoulder keypoints.
"Mid-Hip" = midpoint of left and right hip keypoints.
### 3.5 2D vs. 3D Angle Estimation

| Approach             | Angle Error | Complexity | Edge Feasible |
| -------------------- | ----------- | ---------- | ------------- |
| 2D (projected)       | ±8–12°      | Low        | Yes           |
| 2D + view correction | ±5–8°       | Medium     | Yes           |
| Lifting to 3D        | ±4–6°       | High       | Marginal      |

**Recommendation: 2D with view correction (V1), 3D lifting (V2)**
View correction applies known camera angle offsets to partially compensate for perspective distortion. If the camera is mounted at a known height and angle, a correction factor can adjust foreshortened angles.

## 4. Dataset Strategy
### 4.1 Dataset Requirements
Ergonomic assessment training requires pose estimation quality validation rather than traditional detection training:

| Data Category                   | Quantity        | Purpose                                |
| ------------------------------- | --------------- | -------------------------------------- |
| Pose estimation validation      | 500 images      | Verify keypoint accuracy               |
| Ground truth angle measurements | 200 sequences   | Compare computed angles vs. goniometer |
| RULA ground truth scores        | 100 assessments | Compare automated vs. expert RULA      |
| REBA ground truth scores        | 100 assessments | Compare automated vs. expert REBA      |
| Industrial posture library      | 1,000 images    | Common work postures catalog           |
| Total                           | ~1,900          |                                        |

### 4.2 Ground Truth Collection Protocol
To validate the angle computation, a trained ergonomist must:
1. Observe workers performing typical tasks.
1. Manually score RULA and REBA using standard worksheets.
1. Simultaneously capture video from the monitoring cameras.
1. Compare the automated scores with the manual expert scores.
**Agreement Target:** Automated RULA/REBA score within ±1 point of expert score in ≥ 80% of assessments.
### 4.3 Typical Industrial Postures for Testing

| Posture                         | RULA Risk | REBA Risk | Frequency in Industry |
| ------------------------------- | --------- | --------- | --------------------- |
| Standing upright, arms at sides | 1–2       |           | High                  |
| Standing, forward lean 20°      | 3–4       | 4–5       | High                  |
| Deep forward bend > 60°         | 6–7       | 8–10      | Medium                |
| Overhead reach                  | 5–6       | 7–8       | Medium                |
| Kneeling with twist             | 5–6       | 8–10      | Low                   |
| Seated computer work            | 3–4       |           | High (office areas)   |
| Lifting from ground             | 6–7       | 10–12     | Medium                |
| Repetitive arm motion           | 4–5       | 5–7       | High (assembly)       |

### 4.4 Pose Model Fine-Tuning Data
If pose accuracy is insufficient on industrial workers (heavy clothing, PPE):

| Data Source                    | Size       | Purpose                         |
| ------------------------------ | ---------- | ------------------------------- |
| COCO (pre-training, done)      | 200K+      | General pose knowledge          |
| Custom PPE-wearing workers     | 500 images | Industrial domain adaptation    |
| Hard hat / vest pose sequences | 300 images | Pose with safety gear occlusion |

## 5. Training Strategy
### 5.1 Pose Model (YOLOv8s-Pose)
Shared with Model 3 (Fall Detection). No separate training needed for ergonomic assessment — the same pose estimates feed both systems.
If fine-tuning is required:

| Phase                | Epochs | Learning Rate | Data Source              |
| -------------------- | ------ | ------------- | ------------------------ |
| COCO Pre-training    | Done   | —             | YOLOv8s-Pose weights     |
| Industrial Fine-tune | 20     | 1e-4          | Custom industrial images |
| PPE Occlusion Adapt  | 10     | 5e-5          | PPE-wearing workers      |

### 5.2 Angle Calibration
The angle computation is geometric (not learned), but requires calibration:

| Calibration Step                  | Method                                    |
| --------------------------------- | ----------------------------------------- |
| Camera angle compensation         | Measure camera tilt angle, apply rotation |
| Known-angle validation            | Compare computed angles vs. goniometer    |
| Scale factor (if 3D lifting used) | Calibrate depth scaling per camera        |
| Systematic bias correction        | Measure average error, apply offset       |

### 5.3 RULA Scoring Algorithm
The RULA score is computed algorithmically following McAtamney & Corlett (1993):
**Group A (Upper Limbs):**

| Upper Arm Position                | Score |
| --------------------------------- | ----- |
| 20° extension to 20° flexion      | 1     |
| > 20° extension OR 20–45° flexion | 2     |
| 45–90° flexion                    | 3     |
| > 90° flexion                     | 4     |
| +1 if shoulder raised             |       |
| +1 if upper arm abducted          |       |

| Lower Arm Position        | Score |
| ------------------------- | ----- |
| 60–100° flexion           | 1     |
| < 60° OR > 100° flexion   | 2     |
| +1 if arm crosses midline |       |

| Wrist Position          | Score |
| ----------------------- | ----- |
| Neutral                 | 1     |
| 0–15° flexion/extension | 2     |
| > 15° flexion/extension | 3     |
| +1 if wrist deviated    |       |

**Group B (Neck, Trunk, Legs):**

| Neck Position          | Score |
| ---------------------- | ----- |
| 0–10° flexion          | 1     |
| 10–20° flexion         | 2     |
| > 20° flexion          | 3     |
| Extension (looking up) | 4     |
| +1 if neck twisted     |       |
| +1 if neck side bent   |       |

| Trunk Position           | Score |
| ------------------------ | ----- |
| Upright / well supported | 1     |
| 0–20° flexion            | 2     |
| 20–60° flexion           | 3     |
| > 60° flexion            | 4     |
| +1 if trunk twisted      |       |
| +1 if trunk side bent    |       |

| Legs                     | Score |
| ------------------------ | ----- |
| Bilateral weight bearing | 1     |
| Unilateral or unstable   | 2     |

Table C combines Group A and B scores into a final score (1–7).
### 5.4 REBA Scoring Algorithm
Similar structure to RULA but includes load/force assessment and coupling factors. Follows Hignett & McAtamney (2000) published scoring tables.
**REBA adds:**
- Load/Force Score (0–3): weight of object being handled
- Coupling Score (0–3): quality of grip on the object
- Activity Score (+1 each): static posture > 1 min, repeated action, rapid changes
### 5.5 Sustained Posture Tracking
Ergonomic risk depends on **duration**, not just instantaneous posture. The system must track:

| Metric                   | Description                         | Alert Trigger          |
| ------------------------ | ----------------------------------- | ---------------------- |
| Sustained High RULA      | RULA ≥ 5 maintained for > 5 minutes | WARNING alert          |
| Sustained High REBA      | REBA ≥ 8 maintained for > 5 minutes | WARNING alert          |
| Cumulative Exposure      | Total minutes at RULA ≥ 5 per shift | Report at shift end    |
| Posture Change Frequency | Low variation = sustained risk      | Dashboard indicator    |
| Peak Risk Events         | Momentary RULA 7 or REBA ≥ 11       | Immediate DANGER alert |

## 6. Evaluation Metrics
### 6.1 Pose Accuracy Metrics

| Metric                   | Definition                                  | Target |
| ------------------------ | ------------------------------------------- | ------ |
| PCKh@0.5                 | Percentage of Correct Keypoints (head norm) | > 85%  |
| Joint Angle MAE          | Mean absolute error of computed angles (°)  | < 8°   |
| Critical Joint Angle MAE | MAE for trunk, neck, upper arm angles (°)   | < 6°   |

### 6.2 RULA/REBA Assessment Accuracy

| Metric                | Definition                                   | Target |
| --------------------- | -------------------------------------------- | ------ |
| Score Exact Match     | % of assessments where auto = expert score   | > 60%  |
| Score ±1 Match        | % within 1 point of expert score             | > 85%  |
| Risk Level Match      | % correct risk classification (4 levels)     | > 80%  |
| False High-Risk Rate  | % scored as high risk that expert scored low | < 10%  |
| Missed High-Risk Rate | % scored as low risk that expert scored high | < 5%   |

### 6.3 Operational Metrics

| Metric                      | Definition                               | Target       |
| --------------------------- | ---------------------------------------- | ------------ |
| Assessment Frequency        | RULA/REBA scores per worker per minute   | ≥ 6          |
| Sustained Posture Detection | % of sustained awkward postures detected | > 90%        |
| Report Generation           | Automatic shift-end ergonomic report     | < 30 seconds |

### 6.4 Performance Targets Summary

| Metric                     | Minimum | Target | Best-in-Class |
| -------------------------- | ------- | ------ | ------------- |
| Joint Angle MAE            | < 12°   | < 8°   | < 5°          |
| RULA Score ±1 Match        | 75%     | 85%    | 92%           |
| REBA Score ±1 Match        | 70%     | 82%    | 90%           |
| Risk Level Classification  | 75%     | 85%    | 92%           |
| Sustained Risk Detection   | 80%     | 90%    | 95%           |
| False High-Risk Alert Rate | < 15%   | < 10%  | < 5%          |

## 7. Deployment Strategy
### 7.0 Development vs. Production Environments
Same laptop-first workflow as all other models. The RULA/REBA computation is pure math — it works identically on any hardware.

| Phase        | Hardware                  | Model Format    | Notes                                |
| ------------ | ------------------------- | --------------- | ------------------------------------ |
| Development  | Laptop/Desktop (CUDA GPU) | PyTorch (.pt)   | Pose model + RULA/REBA algorithm     |
| Demo/Testing | Laptop/Desktop            | PyTorch or ONNX | Real-time demo with webcam or video  |
| Production   | NVIDIA Jetson Orin Nano   | TensorRT FP16   | Final edge deployment (future phase) |

### 7.1 Compute Cost (Incremental)
Since the pose estimation is shared with Model 3 (Fall Detection), the ergonomic analysis adds almost zero additional compute:

| Component                      | Additional Latency |
| ------------------------------ | ------------------ |
| Pose Estimation (YOLOv8s-Pose) | 0 ms (shared)      |
| Angle Calculation              | < 0.5 ms           |
| RULA Score                     | < 0.1 ms           |
| REBA Score                     | < 0.1 ms           |
| Temporal Aggregation           | < 0.1 ms           |
| Total Additional for Model 4   | < 1 ms             |

This is the most computationally efficient model — it is essentially free once the pose estimation is running.
### 7.2 Memory Requirements

| Data Structure                  | Size per Person | Purpose                      |
| ------------------------------- | --------------- | ---------------------------- |
| Keypoint buffer (10 sec window) | ~40 KB          | Temporal smoothing           |
| Angle history (per shift)       | ~200 KB         | Cumulative exposure tracking |
| RULA/REBA score history         | ~50 KB          | Risk trend reporting         |
| Total per tracked person        | ~300 KB         |                              |

For 10 simultaneous workers: ~3 MB total — negligible on Jetson.
### 7.3 Output Data
The ergonomic module produces structured data for the backend:
**Per-frame output (sent every 10 seconds, averaged):**

| Field                  | Type  | Description                          |
| ---------------------- | ----- | ------------------------------------ |
| worker_track_id        | int   | ByteTrack ID                         |
| timestamp              | float | Unix timestamp                       |
| rula_score             | int   | 1–7                                  |
| reba_score             | int   | 1–15                                 |
| trunk_angle            | float | Degrees from vertical                |
| neck_angle             | float | Degrees from neutral                 |
| upper_arm_angle_L      | float | Left upper arm angle                 |
| upper_arm_angle_R      | float | Right upper arm angle                |
| knee_angle_L           | float | Left knee angle                      |
| knee_angle_R           | float | Right knee angle                     |
| risk_level             | enum  | NEGLIGIBLE/LOW/MEDIUM/HIGH/VERY_HIGH |
| sustained_duration_sec | float | Seconds at current risk level        |

### 7.4 Dashboard Integration
The ergonomic data should power a real-time dashboard with:

| Dashboard Widget                        | Update Rate  |
| --------------------------------------- | ------------ |
| Live RULA/REBA score per worker         | Every 10 sec |
| Body angle heatmap (color-coded joints) | Every 10 sec |
| Sustained posture timeline              | Every 1 min  |
| Shift cumulative exposure chart         | Every 5 min  |
| Daily ergonomic summary report          | End of shift |
| Top 5 highest-risk postures captured    | End of shift |

## 8. Risks & Mitigation
### 8.1 Risk Matrix

| Risk                                        | Likelihood | Impact | Mitigation                                                                             |
| ------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------------------------- |
| Inaccurate angles from camera perspective   | High       |        | View correction, recommend 45° camera angle                                            |
| Heavy PPE obscures body shape/joints        | High       | Medium | Fine-tune pose model on PPE-wearing workers                                            |
| Multiple workers overlapping                | Medium     |        | Per-person tracking, reject low-confidence poses                                       |
| Worker facing away from camera              | Medium     | High   | Use bilateral keypoint visibility; flag "rear view"                                    |
| RULA/REBA score disagrees with expert       | Medium     |        | Continuous validation program with ergonomist                                          |
| Worker objects to continuous monitoring     | Medium     | High   | Privacy: face blurring, aggregate data, no individual tracking reports without consent |
| Camera angle changes (not recalibrated)     | Low        | High   | Auto-detect calibration drift via reference points                                     |
| Wrist/finger angles unmeasurable from video | High       | Low    | Default wrist to neutral + 1 (conservative)                                            |

### 8.2 Accuracy Limitations — Transparency
The system must clearly communicate its limitations:

| Limitation                                | Impact on Score | Communication                          |
| ----------------------------------------- | --------------- | -------------------------------------- |
| Cannot measure wrist deviation accurately | ±1 RULA         | Default to conservative estimate       |
| Cannot measure grip/coupling quality      | ±1 REBA         | Operator inputs load/coupling manually |
| Cannot detect trunk twist reliably in 2D  | ±1 RULA/REBA    | Flag as "twist not assessable"         |
| Load weight is unknown from video         | ±2 REBA         | Operator pre-configures task loads     |

### 8.3 Privacy Considerations
Continuous posture monitoring raises privacy concerns:

| Concern                    | Mitigation                                              |
| -------------------------- | ------------------------------------------------------- |
| Individual worker tracking | Face blurring (FaceBlurrer module), anonymized IDs      |
| Performance surveillance   | Reports show aggregate/team data by default             |
| Consent                    | Workers must be informed and consent documented         |
| Data retention             | Posture data aggregated daily, raw cleared after 7 days |
| Regulatory compliance      | Follow local labor laws on workplace monitoring         |

### 8.4 Ergonomist Validation Program
- Before deployment: validate automated scores against 50 expert assessments.
- First month: daily comparison of 5 random automated assessments vs. expert review.
- Ongoing: monthly spot-check of 10 assessments by certified ergonomist.
- Maintain a "confidence level" indicator that reflects validation agreement rate.

## 9. Final Performance Targets
### 9.1 Model Performance

| Metric                    | Minimum | Target | Best-in-Class |
| ------------------------- | ------- | ------ | ------------- |
| Joint Angle MAE           | < 12°   | < 8°   | < 5°          |
| RULA Score ±1 Match       | 75%     | 85%    | 92%           |
| REBA Score ±1 Match       | 70%     | 82%    | 90%           |
| Risk Level Classification | 75%     | 85%    | 92%           |
| Sustained Risk Detection  | 80%     | 90%    | 95%           |

### 9.2 Operational Performance

| Metric                    | Minimum | Target   | Best-in-Class |
| ------------------------- | ------- | -------- | ------------- |
| Additional Latency        | < 5 ms  | < 1 ms   | < 0.5 ms      |
| Assessment Rate           | 6/min   | 12/min   | 30/min        |
| Worker Capacity (per cam) | 3       | 6        | 10            |
| Shift Report Generation   | < 2 min | < 30 sec | < 10 sec      |

### 9.3 Deployment Targets

| Parameter             | Target                                    |
| --------------------- | ----------------------------------------- |
| Pose Model            | YOLOv8s-Pose (shared with Fall Detection) |
| Scoring Engine        | Algorithmic RULA/REBA (no ML needed)      |
| Additional Model Size | 0 MB (shared pose model)                  |
| Additional Memory     | ~300 KB per tracked worker                |
| Edge Hardware         | NVIDIA Jetson Orin Nano                   |
| Dev Hardware          | Laptop/Desktop with CUDA GPU              |
| Edge Hardware         | NVIDIA Jetson Orin Nano (production)      |
| Score Output Format   | JSON via BackendClient                    |

### 9.4 Cross-Model Resource Summary

| Model   | Name              | Inference Model       | Team Member | Additional Compute             | Total Pipeline Latency |
| ------- | ----------------- | --------------------- | ----------- | ------------------------------ | ---------------------- |
| Model 1 | PPE Detection     | YOLOv8s (independent) | Person 1    | —                              | ~30–40 ms              |
| Model 2 | Vehicle Proximity | YOLOv8s (independent) | Person 2    | ByteTrack + Homography (~5 ms) | ~35–50 ms              |
| Model 3 | Fall Detection    | YOLOv8s-Pose          | Person 3    | Rule engine (~1 ms)            | ~40 ms                 |
| Model 4 | Pose & Ergonomics | YOLOv8s-Pose (shared) | Person 4    | RULA/REBA calc (< 1 ms)        | < 1 ms additional      |

**Total system: 3 independent neural network models:**
- **YOLOv8s** (PPE) — trained and owned by Person 1
- **YOLOv8s** (Vehicle) — trained and owned by Person 2
- **YOLOv8s-Pose** — shared between Person 3 (Fall) and Person 4 (Ergonomics)
**Development environment:** All models train and run on laptop/desktop with CUDA GPU.
**Production target:** NVIDIA Jetson Orin Nano (future phase, same code, only model export format changes).

*End of Model 4 Specification — Pose Estimation & Ergonomic Risk Assessment (RULA/REBA)*
