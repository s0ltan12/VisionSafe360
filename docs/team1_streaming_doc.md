# Team 1 — Streaming & Orchestration

## 1. Overview

## 2. Scope
### 2.1 StreamHandler
### 2.2 main.py (Orchestrator)
### 2.3 config/settings.py

## 3. Class: StreamHandler
### 3.1 Attributes
### 3.2 Methods
### 3.3 RTSP Connection Lifecycle
### 3.4 Reconnection & Health Check Logic
### 3.5 Multi-Camera Threading Model

## 4. Orchestrator (main.py)
### 4.1 Initialization Sequence
### 4.2 Main Loop Architecture
### 4.3 Graceful Shutdown

## 5. Configuration
### 5.1 Camera URLs
### 5.2 Frame Settings (Size, FPS, Skip)
### 5.3 Timeouts & Retry Policy

## 6. Input / Output Contract
### 6.1 Output: Frame Object Format
### 6.2 Output: Metadata Passed to InferenceEngine

## 7. Dependencies

## 8. Error Handling

## 9. Unit Tests
### 9.1 test_stream_handler.py

## 10. Deliverables & Milestones
