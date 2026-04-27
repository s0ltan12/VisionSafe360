# Team 4 — Alerts & Integration

## 1. Overview

## 2. Scope
### 2.1 AlertManager
### 2.2 NotificationService (Interface)
### 2.3 FCMService
### 2.4 SirenController
### 2.5 FaceBlurrer
### 2.6 BackendClient

## 3. Class: AlertManager
### 3.1 Attributes (severity_policy)
### 3.2 Method: process_event(event)
### 3.3 Method: route_alert(event)
### 3.4 Routing Logic (Critical → Siren + Push, Low → Log Only)
### 3.5 Escalation Policy

## 4. Interface: NotificationService
### 4.1 Method: send_push(user, payload)
### 4.2 Method: send_websocket(event)

## 5. Class: FCMService
### 5.1 Attributes (firebase_app)
### 5.2 Firebase Setup & Configuration
### 5.3 Push Notification Payload Format

## 6. Class: SirenController
### 6.1 Attributes (gpio_pin)
### 6.2 Method: trigger_alarm()
### 6.3 Method: stop_alarm()
### 6.4 GPIO Wiring & Mock Mode

## 7. Class: FaceBlurrer
### 7.1 Attributes (blur_strength)
### 7.2 Method: blur_faces(frame)
### 7.3 Face Detection Method
### 7.4 Blur Application

## 8. Class: BackendClient
### 8.1 API Endpoints (POST /incidents, POST /ergonomic-records)
### 8.2 JWT Authentication
### 8.3 Retry & Timeout Logic
### 8.4 Offline Queue (Store-and-Forward)
### 8.5 Snapshot Upload

## 9. Input / Output Contract
### 9.1 Input: HazardEvent from HazardAnalyzer
### 9.2 Output: API Calls to Backend

## 10. Dependencies

## 11. Unit Tests
### 11.1 test_alert_manager.py
### 11.2 test_fcm_service.py
### 11.3 test_siren_controller.py
### 11.4 test_face_blurrer.py
### 11.5 test_backend_client.py

## 12. Deliverables & Milestones
