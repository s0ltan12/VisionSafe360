# VisionSafe 360 — Step 4 Execution Plan (Edge AI Alerts & Integration)

> Date: 2026-03-21  
> Scope: edge_ai only  
> Priority: Finish alerting and backend integration before backend implementation details  
> Decision: FaceBlurrer is removed from the current scope

---

## 1. Executive Summary

This document defines the complete implementation plan for the remaining edge_ai modules:

1. AlertManager
2. FCM service
3. Siren controller
4. Backend client

The current pipeline already produces hazard events from analysis modules. The missing part is reliable event delivery and action routing.

Current Step-4 objective:

1. Consume emitted HazardEvent objects after EventAggregator.
2. Route each event by severity and policy.
3. Deliver notifications to mobile (FCM), local siren, and backend API.
4. Add offline queue + retry for backend reliability.
5. Keep all processing inside edge_ai; backend internals will be handled later.

Out of scope for now:

1. Face blurring
2. Dashboard websocket implementation from edge side (backend owns WS broadcast)
3. Full backend API implementation (edge will target stable API contracts only)

---

## 2. Current State Snapshot (edge_ai)

Already implemented and stable:

1. Stream handling and inference orchestration
2. Hazard analysis (fall, posture, proximity)
3. Event aggregation and cooldown logic
4. Profiles and scheduling
5. Offline evaluation harness

Still empty and must be implemented now:

1. src/alerts/alert_manager.py
2. src/alerts/fcm_service.py
3. src/alerts/siren_controller.py
4. src/alerts/notification_service.py
5. src/integration/backend_client.py

Also empty (kept out of current target):

1. src/privacy/face_blurrer.py

---

## 3. Functional Scope (Required Behavior)

## 3.1 Alert Routing Matrix

Default routing policy (configurable):

1. LOW: backend log only
2. MEDIUM: backend log + FCM (optional by profile)
3. HIGH: backend log + FCM
4. CRITICAL: backend log + FCM + siren trigger

Notes:

1. Since backend websocket is server-side concern, edge only sends event HTTP payloads.
2. Duplicate events are already reduced by EventAggregator, but AlertManager will add last-mile throttling guard.

## 3.2 Event Ingress Point

Integration point in pipeline loop:

1. raw events -> EventAggregator.process(...) -> emitted events
2. emitted events -> AlertManager.process_events(...)

AlertManager will be called once per frame with a list of emitted events (possibly empty).

## 3.3 Event Payload Contract (Edge -> Backend)

Minimum payload fields:

1. event_type
2. severity
3. camera_id
4. timestamp
5. frame_number
6. track_id
7. description
8. metadata
9. bbox

Transport format:

1. JSON over HTTP POST
2. JWT bearer token header (if configured)

---

## 4. Module Design and Responsibilities

## 4.1 AlertManager

Primary responsibility:

1. Single entry point for post-analysis actions.

Core API:

1. process_events(events: list[HazardEvent], frame=None) -> dict metrics

Internal flow per event:

1. Validate event object
2. Decide channels from severity + settings
3. Send to BackendClient (mandatory)
4. Send push via FCMService (based on policy)
5. Trigger SirenController for CRITICAL
6. Record local delivery status for metrics/debug

Non-functional requirements:

1. Must never crash pipeline loop
2. Any channel failure is logged and isolated
3. Returns per-channel success/failure counters

## 4.2 FCMService

Primary responsibility:

1. Send mobile push notifications for actionable hazards.

Core API:

1. send_event(event: HazardEvent) -> bool
2. send_payload(token: str, title: str, body: str, data: dict) -> bool

Modes:

1. Mock mode: enabled by default for development
2. Real mode: uses Firebase Admin credentials when available

Retry behavior:

1. Short retry (for transient network errors)
2. Permanent errors return False without crashing caller

Payload strategy:

1. Short title by severity
2. Body from event description
3. Data contains event metadata for app deep-linking

## 4.3 SirenController

Primary responsibility:

1. Trigger physical or simulated siren for CRITICAL events.

Core API:

1. trigger(event: HazardEvent, duration_sec: float | None = None) -> bool
2. stop() -> bool

Modes:

1. Mock mode (development): log only
2. GPIO mode (deployment): pin on/off control

Safety guards:

1. Cooldown window (avoid continuous retrigger)
2. Max active duration timeout
3. Idempotent stop behavior

## 4.4 BackendClient

Primary responsibility:

1. Reliable event delivery from edge_ai to backend API.

Core API:

1. submit_incident(event: HazardEvent) -> bool
2. submit_batch(events: list[HazardEvent]) -> tuple[int, int]
3. flush_offline_queue() -> dict

Transport design:

1. aiohttp async client or synchronous requests wrapper (choose one style and keep consistent)
2. Endpoint target: POST /incidents
3. Optional auth: Authorization: Bearer <token>

Reliability behavior:

1. If HTTP fails, persist event in local queue store
2. Queue flush on every N frames or time interval
3. Backoff retries for transient failures
4. Hard cap on queue size to prevent disk growth

Offline queue storage:

1. SQLite file in edge_ai root (recommended)
2. Table includes id, payload_json, created_at, retry_count, last_error

---

## 5. Configuration Changes (src/config/settings.py)

Add or finalize these settings:

1. ALERTS_ENABLED
2. ALERT_LOW_TO_BACKEND_ONLY
3. FCM_ENABLED
4. FCM_MOCK_MODE
5. FCM_CREDENTIALS_PATH
6. FCM_DEVICE_TOKENS (list or file path)
7. SIREN_ENABLED
8. SIREN_MOCK_MODE
9. SIREN_GPIO_PIN
10. SIREN_COOLDOWN_SEC
11. SIREN_MAX_ACTIVE_SEC
12. BACKEND_EVENTS_ENABLED
13. BACKEND_URL
14. BACKEND_INCIDENTS_PATH
15. BACKEND_AUTH_TOKEN
16. BACKEND_TIMEOUT
17. BACKEND_MAX_RETRY
18. BACKEND_RETRY_BACKOFF
19. OFFLINE_QUEUE_DB
20. OFFLINE_QUEUE_MAX_ROWS
21. OFFLINE_FLUSH_INTERVAL_SEC

Policy should be fully environment-driven to avoid code edits per site.

---

## 6. Integration Plan in main.py

Implementation sequence:

1. Initialize BackendClient, FCMService, SirenController
2. Inject them into AlertManager
3. After EventAggregator emits events, call AlertManager.process_events(emitted)
4. Add periodic backend_client.flush_offline_queue()
5. Add summary counters into MetricsLogger extra fields

New frame-level telemetry fields:

1. n_events_emitted
2. n_backend_ok
3. n_backend_failed
4. n_fcm_ok
5. n_fcm_failed
6. n_siren_triggers
7. offline_queue_size

---

## 7. Detailed Task Breakdown

## 7.1 Phase A — Contracts and Skeletons

1. Implement dataclasses/enums if needed for delivery status
2. Add method signatures and docstrings in the 4 target modules
3. Add settings constants and environment parsing

Exit criteria:

1. Modules import cleanly
2. Pipeline starts with all services in mock mode

## 7.2 Phase B — BackendClient Reliability

1. Implement submit_incident
2. Implement retry and timeout handling
3. Implement SQLite queue persistence
4. Implement flush_offline_queue and delete-on-success

Exit criteria:

1. Simulated backend failure stores events locally
2. Reconnect flushes queue successfully

## 7.3 Phase C — FCM and Siren

1. Implement FCM mock mode and real mode
2. Implement Siren mock mode and GPIO mode
3. Add per-channel cooldown/rate limits

Exit criteria:

1. CRITICAL event triggers siren exactly once within cooldown
2. HIGH/CRITICAL events produce push attempt logs

## 7.4 Phase D — AlertManager Orchestration

1. Implement routing matrix
2. Implement channel isolation (one failure does not stop others)
3. Return delivery summary object per frame

Exit criteria:

1. All severities route to expected channels
2. Summary counters appear in telemetry

## 7.5 Phase E — Pipeline Wiring + Eval

1. Wire AlertManager in main pipeline
2. Add evaluation checks in eval/run.py for delivery counters
3. Validate with existing clips and synthetic events

Exit criteria:

1. End-to-end edge flow from hazard detection to delivery works in mock mode
2. No FPS collapse from alerting layer

---

## 8. Testing Plan

Create/complete unit tests:

1. tests/test_alert_manager.py
2. tests/test_backend_client.py
3. tests/test_fcm_service.py
4. tests/test_siren_controller.py

Update/add integration tests:

1. tests/test_event_aggregator.py (handoff behavior)
2. tests/test_capability_check.py (service capability flags)

Minimum test scenarios:

1. LOW severity -> backend only
2. CRITICAL severity -> backend + FCM + siren
3. Backend timeout -> queued offline
4. Queue flush success after backend recovery
5. FCM failure does not block backend delivery
6. Siren cooldown suppresses rapid retriggers

Done quality bar:

1. All edge_ai tests pass
2. New modules have unit coverage for success and failure paths

---

## 9. Non-Functional Requirements

1. Alerting path must be non-blocking relative to inference loop as much as practical
2. Network failure must not crash the process
3. Disk queue must remain bounded
4. Logging must be structured and machine-readable
5. All new code follows current project typing/dataclass style

---

## 10. Risk Register (Step 4)

1. Backend not ready yet
Mitigation: strict API contract + offline queue + mock endpoint tests

2. FCM credential issues
Mitigation: keep mock mode default; validate credentials in startup check only

3. Siren hardware mismatch
Mitigation: abstract GPIO implementation and keep mock fallback

4. Alert flooding from noisy detections
Mitigation: keep EventAggregator as first filter and add channel throttling

5. Latency regression due to synchronous I/O
Mitigation: short timeouts, batched flush, optional async transport

---

## 11. Explicit Scope Decision: FaceBlurrer Removed

For current edge_ai completion, FaceBlurrer is excluded.

Practical impact:

1. No blur operation before backend submission
2. Snapshot media transmission should remain disabled or minimal until privacy requirements are revisited
3. Event metadata and text payloads continue normally

Future re-enable path (optional later):

1. Add privacy flag in settings
2. Integrate blur only on snapshot/image pipeline, not on core detection frames

---

## 12. Definition of Done (Edge AI First)

Step 4 is complete only when all are true:

1. AlertManager implemented and integrated into main loop
2. FCM service implemented with mock and real mode
3. Siren controller implemented with mock and GPIO mode
4. Backend client implemented with retry + offline queue + flush
5. FaceBlurrer excluded from runtime path (by design)
6. Unit/integration tests for these modules are passing
7. Eval run produces delivery metrics and stable performance
8. Final completion report generated with measured results

---

## 13. Execution Order (Recommended)

1. BackendClient
2. AlertManager
3. SirenController
4. FCMService
5. main.py wiring
6. tests
7. eval verification and closure report

Reason:

1. BackendClient is mandatory for all severities and provides the main reliability backbone.

---

## 14. Deliverables to Commit

Code deliverables:

1. Implemented alerts and integration modules
2. Updated settings and main wiring
3. Completed tests for all Step-4 modules

Documentation deliverables:

1. This execution plan
2. Step-4 completion report with real metrics
3. Known limitations and next-step notes before backend phase

