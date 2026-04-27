# Team 3 — Analysis & Classification

## 1. Overview

## 2. Scope
### 2.1 HazardAnalyzer
### 2.2 PostureAnalyzer
### 2.3 HazardEvent (Data Model)
### 2.4 Severity (Enum)

## 3. Class: HazardAnalyzer
### 3.1 Attributes (thresholds, cooldown_tracker)
### 3.2 Method: analyze(detections, poses)
### 3.3 Method: classify_severity(event)
### 3.4 PPE Violation Rules
### 3.5 Fall Detection Logic
### 3.6 Unsafe Proximity Calculation
### 3.7 Cooldown Mechanism

## 4. Class: PostureAnalyzer
### 4.1 Attributes (angle_thresholds)
### 4.2 Method: analyze_posture(pose)
### 4.3 Method: calculate_rula(pose)
### 4.4 Method: calculate_reba(pose)
### 4.5 Angle Calculations (back, neck, knee)
### 4.6 Sustained Posture Tracking

## 5. Data Model: HazardEvent
### 5.1 Fields (hazard_type, severity, timestamp)

## 6. Enum: Severity
### 6.1 LOW / MEDIUM / HIGH / CRITICAL

## 7. Business Rules
### 7.1 Zone-Based Rules
### 7.2 Shift-Aware Analysis

## 8. Input / Output Contract
### 8.1 Input: Detection + PoseResult from InferenceEngine
### 8.2 Output: List<HazardEvent> with Severity

## 9. Dependencies

## 10. Unit Tests
### 10.1 test_hazard_analyzer.py
### 10.2 test_posture_analyzer.py

## 11. Deliverables & Milestones
