# Model Specification 2 — Vehicle Proximity Risk Detection
**Document Version:  **1.0
**Date:  **2026-02-18
**Author:  **VisionSafe360 AI Research Team
**Classification:  **Internal Technical Specification

## 1. Model Objective
### 1.1 Problem Statement
Vehicle-pedestrian collisions are among the most severe industrial accidents. OSHA reports that "struck-by vehicle" incidents account for approximately 75% of struck-by fatalities in construction, and forklift-pedestrian collisions cause approximately 85 deaths and 34,900 serious injuries annually in the United States alone (NIOSH). In manufacturing facilities and warehouses, the co-existence of forklifts, loaders, and pedestrian workers creates persistent proximity hazard zones.
### 1.2 Detection Scope
This model must detect the spatial relationship between vehicles and workers to determine unsafe proximity in real time.
**Object Classes:**

| Class ID | Class Name    | Description                            |
| -------- | ------------- | -------------------------------------- |
| 0        | person        | Pedestrian worker in the scene         |
| 1        | forklift      | Industrial forklift (all variants)     |
| 2        | loader        | Wheel loaders, skid steers             |
| 3        | truck         | Delivery trucks, dump trucks on site   |
| 4        | vehicle_other | Any other motorized industrial vehicle |

**Proximity Risk Levels:**

| Risk Level | Definition                                   | Threshold (approximate) |
| ---------- | -------------------------------------------- | ----------------------- |
| SAFE       | No vehicle-person pair within danger zone    | > 5 meters              |
| WARNING    | Person approaching vehicle operational area  | 3–5 meters              |
| DANGER     | Person within immediate collision risk zone  | 1–3 meters              |
| CRITICAL   | Imminent contact / overlap of bounding boxes | < 1 meter / overlapping |

### 1.3 Technical Challenge
Unlike PPE detection (single-object classification), proximity detection is a **relational reasoning** task. The model must:
1. Detect all persons and vehicles in the frame.
1. Estimate the spatial distance between each person-vehicle pair.
1. Classify the risk level.
This requires either monocular depth estimation or geometric calibration-based distance approximation — both with inherent limitations in single-camera CCTV setups.
### 1.4 Business Impact
A single forklift-pedestrian collision can result in fatalities, six-figure legal liability, OSHA investigations, and mandatory facility shutdowns. Real-time proximity alerting can prevent the most catastrophic workplace incidents.

## 2. Industry Benchmark Research
### 2.1 Academic State-of-the-Art

| Study / System                                      | Year | Approach                       | mAP@0.5 (detection) | Distance Error | Notes                            |
| --------------------------------------------------- | ---- | ------------------------------ | ------------------- | -------------- | -------------------------------- |
| Kim et al., "Vision-based Proximity Detection"      | 2022 | YOLOv5 + geometric calibration | 89.2%               | ±0.8 m         | Construction zone, single camera |
| Cai et al., "Forklift-Pedestrian Collision Warning" | 2021 | SSD + depth regression head    | 84.6%               | ±1.2 m         | Warehouse environment            |
| Park et al., "Real-time Zone Monitoring"            | 2023 | YOLOv8 + homography            | 92.1%               | ±0.5 m         | Calibrated camera, flat ground   |
| Martinez et al., "Monocular Distance for Safety"    | 2023 | YOLO + MiDaS depth             | 87.3%               | ±1.5 m         | Uncalibrated camera              |
| Seo et al., "Deep Learning Proximity Alert"         | 2022 | Faster R-CNN + projection      | 86.8%               | ±0.9 m         | Multi-class vehicle detection    |

### 2.2 Distance Estimation Method Comparison

| Method                      | Accuracy (distance) | Requires Calibration | Real-time | Robustness              |
| --------------------------- | ------------------- | -------------------- | --------- | ----------------------- |
| Homography (ground plane)   | ±0.3–0.5 m          | Yes (one-time)       | Yes       | High (flat ground only) |
| Bounding box height ratio   | ±0.8–1.5 m          | Partial              | Yes       | Medium                  |
| Monocular depth (MiDaS/DPT) | ±1.0–2.0 m          | No                   | Moderate  | Low-Medium              |
| Stereo vision               | ±0.1–0.3 m          | Yes (stereo rig)     | Yes       | High                    |
| LiDAR fusion                | ±0.05 m             | Yes (sensor fusion)  | Yes       | Very High               |

### 2.3 Target Metrics for VisionSafe360

| Metric                      | Minimum Acceptable | Competitive Target | Best-in-Class  |
| --------------------------- | ------------------ | ------------------ | -------------- |
| mAP@0.5 (vehicle detection) | 85.0%              | 91.0%              | 95.0%          |
| mAP@0.5 (person detection)  | 90.0%              | 95.0%              | 98.0%          |
| Distance estimation error   | ±1.5 m             | ±0.8 m             | ±0.3 m         |
| Proximity alert accuracy    | 80.0%              | 88.0%              | 95.0%          |
| False proximity alarm rate  | < 5 per hour       | < 2 per hour       | < 0.5 per hour |

## 3. Recommended Model Architecture
### 3.1 Approach Comparison
The vehicle proximity problem can be solved with three architectural approaches:
**Approach A: Detection + Geometric Distance (Recommended)**
Pipeline: YOLOv8 (detect persons + vehicles) → Homography Transform → Distance Calculation → Risk Classification
- Pros: Real-time, interpretable, accurate with camera calibration, lightweight.
- Cons: Requires one-time camera calibration, assumes flat ground plane.
**Approach B: Detection + Monocular Depth Estimation**
Pipeline: YOLOv8 (detect) → MiDaS v3 / Depth Anything (depth map) → 3D Position → Distance
- Pros: No calibration needed, works with any camera.
- Cons: Depth estimation adds 30–100ms latency, depth accuracy is ±1.5m (insufficient for safety-critical decisions), requires second neural network.
**Approach C: Detection + Tracking + Trajectory Prediction**
Pipeline: YOLOv8 (detect) → ByteTrack/BoT-SORT (track) → Kalman Filter (predict trajectory) → Collision Time Estimate
- Pros: Predicts future collisions before they happen, accounts for velocity.
- Cons: Complex pipeline, tracking errors propagate, requires tuning.
### 3.2 Recommended Architecture
**Primary: Approach A (Detection + Geometric Distance) with Approach C elements (Tracking)**
Rationale:
- Industrial CCTV cameras are fixed-position. One-time calibration (4 reference points on the ground plane) provides a homography matrix that converts pixel coordinates to real-world ground coordinates with ±0.3–0.5m accuracy — sufficient for safety zone classification.
- Adding ByteTrack on top provides temporal consistency and velocity estimation, enabling "closing speed" analysis.
- This approach requires no additional neural networks beyond YOLOv8, keeping the pipeline lightweight for edge deployment.
### 3.3 Detection Model Selection
Same YOLOv8s recommendation as Model 1 (PPE), but with different class training:

| Component           | Choice           | Justification                                           |
| ------------------- | ---------------- | ------------------------------------------------------- |
| Detection Model     | YOLOv8s          | Same model can detect persons AND vehicles              |
| Tracker             | ByteTrack        | Best open-source multi-object tracker, minimal overhead |
| Distance Estimation | Homography-based | ±0.5m accuracy with calibration, zero latency           |
| Risk Classifier     | Rule-based       | Threshold-based on calculated distance                  |

**Note:** Model 1 (PPE) and Model 2 (Vehicle Proximity) are developed **independently** by different team members. Each model is trained, tested, and maintained separately.
### 3.4 Independent Model Strategy
**Each model is a separate YOLOv8s instance with its own classes:**
**Model 1 — PPE Detection (separate team member):**

| Class ID | Class Name |
| -------- | ---------- |
| 0        | person     |
| 1        | helmet_on  |
| 2        | helmet_off |
| 3        | vest_on    |
| 4        | vest_off   |

**Model 2 — Vehicle Proximity (separate team member):**

| Class ID | Class Name    |
| -------- | ------------- |
| 0        | person        |
| 1        | forklift      |
| 2        | loader        |
| 3        | truck         |
| 4        | vehicle_other |

**Why separate models:**
- Two different team members work on them in parallel — merging would create blocking dependencies.
- Different datasets, training schedules, and hyperparameter tuning.
- Independent testing and validation — each model owner is responsible for their own metrics.
- Easier debugging — each model's failure modes are isolated.
**Future optimization (post-development):** After both models reach their target metrics, a unified model can be explored as an optimization to reduce inference cost. This is NOT a development-phase concern.

## 4. Dataset Strategy
### 4.1 Required Dataset Size

| Phase                          | Images  | Annotations           |
| ------------------------------ | ------- | --------------------- |
| Vehicle + Person Detection Set | 6,000   | ~18,000               |
| Proximity Scenarios            | 4,000   | ~20,000               |
| Validation                     | 2,000   | ~8,000                |
| Test                           | 1,000   | ~4,000                |
| Calibration Images             | 50–100  | Reference points only |
| Total                          | ~13,000 | ~50,000               |

### 4.2 Public Dataset Sources

| Dataset                   | Size       | Classes                | Quality  |
| ------------------------- | ---------- | ---------------------- | -------- |
| KITTI (vehicles)          | 7,481      | Car, Van, Truck, etc.  | High     |
| BDD100K (vehicles)        | 100,000    | Multiple vehicle types | High     |
| LVIS (forklift subset)    | ~500       | Forklift               | Medium   |
| Open Images v7 (forklift) | ~2,000     | Forklift               | Medium   |
| Custom warehouse footage  | To collect | Forklift, Person       | Required |
| COCO (person class)       | 64,000     | Person                 | High     |

**Critical gap:** Forklift-specific datasets are extremely limited. Custom data collection from the deployment site is mandatory.
### 4.3 Class Balance Strategy

| Class         | Expected Prevalence | Balancing Strategy                        |
| ------------- | ------------------- | ----------------------------------------- |
| person        | High (60%)          | Natural prevalence, no rebalancing needed |
| forklift      | Medium (20%)        | Augment with synthetic overlays           |
| loader        | Low (5%)            | Use transfer from general vehicle data    |
| truck         | Medium (10%)        | Adequate in BDD100K/KITTI                 |
| vehicle_other | Low (5%)            | Group rare vehicle types                  |

### 4.4 Data Augmentation Strategy
All augmentations from Model 1, plus:

| Augmentation               | Purpose                          | Parameters             |
| -------------------------- | -------------------------------- | ---------------------- |
| Scale Jitter (vehicles)    | Simulate distance variation      | 0.3–2.0x               |
| Partial Occlusion          | Vehicle behind shelving/walls    | 20–50% occlusion       |
| Background Diversification | Warehouse, factory, outdoor yard | Domain-specific scenes |
| Person-near-vehicle paste  | Create proximity training pairs  | Controlled placement   |

### 4.5 Calibration Data
For each deployment camera, collect:
- 4+ reference points on the ground plane with known real-world coordinates (measured with tape measure).
- Record these as (pixel_x, pixel_y) → (real_x_meters, real_y_meters) pairs.
- Compute homography matrix H using OpenCV findHomography.
- Validate by measuring known distances in the transformed space.

## 5. Training Strategy
### 5.1 Transfer Learning Approach
1. **Recommended: Train from COCO pre-trained weights.**
- COCO already contains car, truck, bus, and person classes — an excellent starting point.
- Fine-tune on industrial vehicle dataset (forklift, loader, etc.).
- Freeze backbone for 10 epochs, then unfreeze and fine-tune for 50–80 epochs.
- This model is **independent** of Model 1 (PPE) — trained by a different team member.
1. **Alternative: Train from scratch on custom dataset.**
- If COCO pre-trained weights perform poorly on industrial vehicles (forklifts are not in COCO), train from ImageNet-pretrained backbone.
- Requires more training data but avoids domain mismatch.
### 5.2 Hyperparameter Configuration
Same as Model 1, with the following modifications:

| Parameter         | Modification              | Justification                                  |
| ----------------- | ------------------------- | ---------------------------------------------- |
| Image Size        | 640 x 640 (same)          | Vehicles are larger objects, 640 is sufficient |
| Anchor Sizes      | Include larger anchors    | Vehicles occupy more pixels than PPE items     |
| Objectness Weight | Increase to 1.2           | Ensure large vehicle objects are detected      |
| Class Weight      | Rebalance for new classes | Prevent person class from dominating training  |

### 5.3 Loss Functions
Same composite YOLOv8 loss (CIoU + BCE + DFL) as Model 1.
**Custom modification:**
- Apply higher box loss weight for vehicle classes — accurate bounding boxes are essential because the distance calculation uses the bottom-center of the bounding box as the ground contact point.
### 5.4 Validation Strategy
- Standard 80/10/10 split for detection validation.
- **Additional proximity validation:** Create a curated set of 200 images with known person-vehicle distances (measured ground truth). Evaluate the full pipeline (detect → calibrate → distance) on this set.
- Report distance estimation MAE (mean absolute error) separately from detection mAP.

## 6. Evaluation Metrics
### 6.1 Primary Metrics — Detection

| Metric             | Definition                           | Priority |
| ------------------ | ------------------------------------ | -------- |
| mAP@0.5 (vehicles) | Mean AP for vehicle classes          | Highest  |
| mAP@0.5 (persons)  | Mean AP for person class             | Highest  |
| Recall (vehicles)  | Vehicle detection true positive rate | High     |

### 6.2 Primary Metrics — Proximity

| Metric                       | Definition                                        | Priority |
| ---------------------------- | ------------------------------------------------- | -------- |
| Distance MAE                 | Mean absolute error of estimated distance (m)     | Highest  |
| Proximity Classification Acc | Correct risk level (SAFE/WARNING/DANGER/CRITICAL) | Highest  |
| Alert True Positive Rate     | % of real danger situations correctly alerted     | Highest  |

### 6.3 Operational Metrics

| Metric                     | Definition                                 | Target       |
| -------------------------- | ------------------------------------------ | ------------ |
| False Proximity Alarm Rate | False danger alerts per camera per hour    | < 3 per hour |
| Missed Danger Rate         | Real DANGER situations not detected        | < 5%         |
| Proximity Latency          | Time from frame to proximity decision      | < 500 ms     |
| Tracking ID Stability      | % of frames where tracked ID is consistent | > 90%        |

### 6.4 Target Thresholds

| Metric                       | Minimum | Target | Best-in-Class |
| ---------------------------- | ------- | ------ | ------------- |
| mAP@0.5 (vehicles)           | 85.0%   | 91.0%  | 95.0%         |
| mAP@0.5 (persons)            | 90.0%   | 95.0%  | 98.0%         |
| Distance MAE                 | ±1.5 m  | ±0.8 m | ±0.3 m        |
| Proximity Classification Acc | 80.0%   | 88.0%  | 95.0%         |
| Tracking Consistency (MOTA)  | 60.0%   | 75.0%  | 85.0%         |

## 7. Deployment Strategy
### 7.0 Development vs. Production Environments
Same as Model 1: all development and testing is performed on a **laptop/desktop with CUDA GPU**. Edge deployment (Jetson) is the production target for a future phase.

| Phase        | Hardware                  | Model Format    | Notes                                |
| ------------ | ------------------------- | --------------- | ------------------------------------ |
| Development  | Laptop/Desktop (CUDA GPU) | PyTorch (.pt)   | Full development, training, testing  |
| Demo/Testing | Laptop/Desktop            | PyTorch or ONNX | Real-time demo with webcam or video  |
| Production   | NVIDIA Jetson Orin Nano   | TensorRT FP16   | Final edge deployment (future phase) |

### 7.1 Export Pipeline
**Development (laptop):** Use PyTorch .pt directly — no conversion needed.
**Production (edge):** PyTorch → ONNX → TensorRT FP16
Model 2 (Vehicle Proximity) is exported independently of Model 1 (PPE). Two separate .engine files run on the edge device.
### 7.2 Proximity Computation Overhead
The distance calculation is purely geometric (matrix multiplication) and adds negligible compute:

| Component            | Latency   |
| -------------------- | --------- |
| YOLOv8s inference    | ~30–40 ms |
| ByteTrack update     | ~2–5 ms   |
| Homography transform | < 1 ms    |
| Distance computation | < 1 ms    |
| Risk classification  | < 1 ms    |
| Total pipeline       | ~35–50 ms |

### 7.3 Multi-Camera Calibration
Each camera requires its own homography matrix. Store calibration data as JSON per camera:

| calibrations/ ├── cam_01_homography.json ├── cam_02_homography.json └── ... |
| --------------------------------------------------------------------------- |

Provide a calibration CLI tool that guides the operator through the 4-point ground plane mapping process.
### 7.4 Frame Scheduling
- Same adaptive strategy as Model 1.
- For proximity: when a vehicle AND person are both detected in the same frame, increase processing to every frame (30 FPS) until they separate by > 5 meters or one leaves the frame.

## 8. Risks & Mitigation
### 8.1 Common Failure Modes

| Failure Mode                              | Likelihood | Impact   | Mitigation                                                                               |
| ----------------------------------------- | ---------- | -------- | ---------------------------------------------------------------------------------------- |
| Forklift not detected (unseen model type) | Medium     | Critical | Diverse forklift training data, "vehicle_other" catch-all class                          |
| Person partially behind vehicle           | High       |          | Tracking maintains ID through brief occlusion                                            |
| Ground not flat (ramps, multi-level)      | Medium     | High     | Per-zone calibration, warn operator of limitation                                        |
| Homography drift (camera bumped/moved)    | Low        | Critical | Periodic auto-calibration check using reference points                                   |
| False proximity from stacked goods        | Medium     |          | Height-based filtering — detected objects below expected vehicle height are likely goods |
| Reflections on shiny floors               | Low        | Medium   | Include reflective surface data in training                                              |

### 8.2 Calibration Risks
- Homography assumes a flat ground plane. In environments with ramps, stairs, or multi-level areas, the distance estimation degrades significantly.
- **Mitigation:** Define separate calibration zones for different ground levels. Alert the operator if a camera covers areas with > 1 meter elevation change.
### 8.3 Tracking Failure Risks
- In crowded scenes (> 15 people + 3 vehicles), ByteTrack may experience ID switches.
- **Mitigation:** Use appearance features (Re-ID) in addition to IoU matching. BoT-SORT is a viable alternative with built-in Re-ID.
- Proximity alerts should be based on instantaneous distance (per-frame) rather than requiring tracking consistency — even if the track ID switches, the proximity danger is still detected.

## 9. Final Performance Targets
### 9.1 Model Performance

| Metric                    | Minimum | Target | Best-in-Class |
| ------------------------- | ------- | ------ | ------------- |
| mAP@0.5 (vehicle classes) | 85.0%   | 91.0%  | 95.0%         |
| mAP@0.5 (person class)    | 90.0%   | 95.0%  | 98.0%         |
| Distance Estimation MAE   | ±1.5 m  | ±0.8 m | ±0.3 m        |
| Proximity Alert Accuracy  | 80.0%   | 88.0%  | 95.0%         |
| Tracking MOTA             | 60.0%   | 75.0%  | 85.0%         |

### 9.2 Operational Performance

| Metric                 | Minimum  | Target  | Best-in-Class |
| ---------------------- | -------- | ------- | ------------- |
| Total Pipeline Latency | < 100 ms | < 50 ms | < 30 ms       |
| False Proximity Alarms | < 5/hr   | < 2/hr  | < 0.5/hr      |
| Missed DANGER events   | < 10%    | < 5%    | < 2%          |
| Throughput (FPS)       | ≥ 10     | ≥ 15    | ≥ 25          |

### 9.3 Deployment Targets

| Parameter            | Target                                     |
| -------------------- | ------------------------------------------ |
| Model Format         | PyTorch (dev) / TensorRT FP16 (production) |
| Additional Compute   | ByteTrack tracker + homography (< 5 ms)    |
| Calibration Required | Yes — one-time per camera (production)     |
| Model Size           | < 25 MB (independent model)                |
| Dev Hardware         | Laptop/Desktop with CUDA GPU               |
| Edge Hardware        | NVIDIA Jetson Orin Nano (production)       |

*End of Model 2 Specification — Vehicle Proximity Risk Detection*
