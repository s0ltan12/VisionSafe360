# Team 2 — Detection & Inference

## 1. Overview

## 2. Scope
### 2.1 InferenceEngine
### 2.2 Detection (Data Model)

## 3. Class: InferenceEngine
### 3.1 Attributes
### 3.2 Methods
### 3.3 YOLO Detection Pipeline
### 3.4 Pose Estimation Pipeline
### 3.5 Model Loading & Warmup
### 3.6 GPU / CPU Device Selection
### 3.7 Confidence & NMS Thresholds

## 4. Data Model: Detection
### 4.1 Fields (class_name, confidence, bounding_box)

## 5. Class Mapping
### 5.1 PPE Classes (helmet, vest, gloves, boots, goggles)
### 5.2 Person Detection
### 5.3 Pose Keypoints (17 COCO)

## 6. Model Files
### 6.1 weights/ Directory Structure
### 6.2 Model Versioning

## 7. Performance Targets
### 7.1 Inference Time (< 100ms / frame)
### 7.2 Optimization (TensorRT, ONNX)

## 8. Input / Output Contract
### 8.1 Input: Frame from StreamHandler
### 8.2 Output: List<Detection> + PoseResult

## 9. Dependencies

## 10. Unit Tests
### 10.1 test_inference_engine.py

## 11. Deliverables & Milestones
