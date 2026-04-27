# VisionSafe 360 Edge AI Lifecycle

## 1) System Overview

VisionSafe 360 runs a real-time edge safety pipeline that reads camera frames,
detects people and forklift proximity using YOLO-based inference, analyzes
hazards (fall risk, posture risk, proximity risk), aggregates events to reduce
noise, and routes confirmed incidents to delivery channels (backend API, FCM,
and siren) with offline resilience for degraded network conditions.

| Component | File | Responsibility |
| --- | --- | --- |
| Runtime settings | `edge_ai/src/config/settings.py` | Global constants and env-driven behavior |
| Profile config | `edge_ai/src/config/profile.py` + `edge_ai/profiles/*.yaml` | Feature toggles, schedules, and analyzer-level behavior per deployment mode |
| Stream ingestion | `edge_ai/src/streaming/stream_handler.py` | Capture frames, reconnect, and enforce latest-frame buffering |
| Inference orchestration | `edge_ai/src/config/inference/inference_engine.py` | Load models and run pose/proximity inference |
| Hazard analysis | `edge_ai/src/analysis/hazard_analyzer.py` | Fall-related hazard detection from tracked detections |
| Posture analysis | `edge_ai/src/analysis/posture_analyzer.py` | Ergonomic risk scoring from pose keypoints |
| Proximity analysis | `edge_ai/src/analysis/proximity_analyzer.py` | Person-forklift distance risk classification |
| Event lifecycle control | `edge_ai/src/analysis/event_aggregator.py` | Deduplicate/persist/escalate emitted hazard events |
| Alert routing | `edge_ai/src/alerts/alert_manager.py` | Policy-based routing to backend, FCM, siren; async queue worker |
| Delivery metrics model | `edge_ai/src/alerts/notification_service.py` | Per-frame sync and async delivery counters |
| FCM channel | `edge_ai/src/alerts/fcm_service.py` | Firebase push notification delivery |
| Siren channel | `edge_ai/src/alerts/siren_controller.py` | Local actuator trigger and cooldown handling |
| Backend channel | `edge_ai/src/integration/backend_client.py` | API submission with retry and SQLite offline queue |
| Pipeline runtime | `edge_ai/src/main.py` | End-to-end init, per-frame processing, and shutdown flow |
| Validation suite | `edge_ai/tests/*` | Regression checks for behavior and refactor safety |

**Key takeaway:** The system is intentionally modular so inference, safety logic,
and delivery reliability can evolve independently without breaking the pipeline.

## 2) Frame Lifecycle

### Phase 1: Capture and Buffer
- **Input:** camera index, file path, or RTSP source
- **Processing:** `StreamHandler` reads frames in a background thread and keeps
  only the latest frame in a bounded deque
- **Output:** `FrameBundle` containing frame bytes + metadata
- **File:** `edge_ai/src/streaming/stream_handler.py`

### Phase 2: Core Inference
- **Input:** `FrameBundle`
- **Processing:** pose model + tracker run each frame; optional proximity model
  runs per profile schedule
- **Output:** detections, tracks, keypoints, per-model latency
- **File:** `edge_ai/src/config/inference/inference_engine.py`

### Phase 3: Perception Stabilization
- **Input:** raw detections from inference
- **Processing:** temporal smoothing for track continuity and forklift hold
  smoothing to reduce flicker under frame skips
- **Output:** stabilized detections for analyzers and renderer
- **File:** `edge_ai/src/main.py` (`FrameProcessor`)

### Phase 4: Hazard Analysis
- **Input:** stabilized detections + pose results + timestamp
- **Processing:** fall analysis, ergonomic posture analysis, and forklift
  proximity risk analysis (based on enabled profile modules)
- **Output:** raw `HazardEvent` candidates
- **Files:** `edge_ai/src/analysis/hazard_analyzer.py`,
  `edge_ai/src/analysis/posture_analyzer.py`,
  `edge_ai/src/analysis/proximity_analyzer.py`

### Phase 5: Event Aggregation
- **Input:** candidate hazard events
- **Processing:** deduplication, persistence windows, cooldown, and severity
  escalation rules
- **Output:** emitted `HazardEvent` list for delivery
- **File:** `edge_ai/src/analysis/event_aggregator.py`

### Phase 6: Delivery and Telemetry
- **Input:** emitted events
- **Processing:** `AlertManager` routes events to backend/FCM/siren; backend
  failures queue to SQLite; per-frame delivery metrics are generated
- **Output:** channel side effects + structured delivery metrics
- **Files:** `edge_ai/src/alerts/alert_manager.py`,
  `edge_ai/src/integration/backend_client.py`,
  `edge_ai/src/alerts/fcm_service.py`,
  `edge_ai/src/alerts/siren_controller.py`

**Key takeaway:** A frame becomes an alert only after deterministic stages:
capture -> infer -> analyze -> aggregate -> route.

## 3) Data Flow

Camera source  
-> `StreamHandler`  
-> `FrameBundle`  
-> `InferenceEngine`  
-> detections / pose results  
-> analyzers (`HazardAnalyzer`, `PostureAnalyzer`, `ProximityAnalyzer`)  
-> `HazardEvent` candidates  
-> `EventAggregator`  
-> emitted `HazardEvent`  
-> `AlertManager`  
-> channels (`BackendClient`, `FCMService`, `SirenController`)

### Object handoff map
| From | To | Object |
| --- | --- | --- |
| StreamHandler | InferenceEngine | `FrameBundle` |
| InferenceEngine | FrameProcessor | pose results + detection list |
| FrameProcessor | analyzers | detection list / pose structures |
| analyzers | EventAggregator | `list[HazardEvent]` |
| EventAggregator | AlertManager | `list[HazardEvent]` |
| AlertManager | BackendClient | `HazardEvent` |
| AlertManager | FCMService | `HazardEvent` |
| AlertManager | SirenController | `HazardEvent` |
| AlertManager | pipeline telemetry | `dict` from `FrameDeliveryMetrics.to_dict()` |

**Key takeaway:** `HazardEvent` is the central contract across analysis,
aggregation, and alert delivery.

## 4) Configuration System

### `settings.py` vs `ProfileConfig` (YAML)
- Use `settings.py` for infrastructure/runtime defaults and environment-specific
  concerns (timeouts, backend URL, device behavior, delivery controls).
- Use profile YAML for scenario-level behavior (which analyzers are enabled,
  schedules, and profile-specific weights).
- `settings.py` answers: "How should this environment run?"
- profile YAML answers: "What safety behavior should this camera run?"

### Top 10 environment variables and effects
| Env Var | Effect |
| --- | --- |
| `VISIONSAFE_BACKEND_EVENTS_ENABLED` | Turns backend incident delivery on/off |
| `VISIONSAFE_BACKEND_URL` | Selects backend API base URL |
| `VISIONSAFE_BACKEND_TIMEOUT` | Sets API request timeout |
| `VISIONSAFE_BACKEND_MAX_RETRY` | Controls synchronous retry attempts |
| `VISIONSAFE_BACKEND_RETRY_BACKOFF` | Controls retry spacing sequence |
| `VISIONSAFE_OFFLINE_QUEUE_DB` | Changes SQLite offline queue location |
| `VISIONSAFE_OFFLINE_FLUSH_INTERVAL_SEC` | Changes periodic queue flush cadence |
| `VISIONSAFE_ALERT_ASYNC_DELIVERY_ENABLED` | Enables async channel delivery worker |
| `VISIONSAFE_FCM_ENABLED` | Enables/disables FCM push channel |
| `VISIONSAFE_WRITE_STEP2_REPORT` | Gates end-of-run report generation under `OUTPUT_DIR` |

**Key takeaway:** Environment variables tune infrastructure behavior, while
profiles tune detection strategy.

## 5) Key Classes and Relationships

- **`PipelineContext` (`main.py`)**  
  Owns runtime dependencies and mutable loop state (services, counters,
  schedules, and resources like writer/stream lifecycle).
- **`FrameProcessor` (`main.py`)**  
  Consumes one frame, performs infer -> analyze -> aggregate -> route, and
  returns frame-level output for rendering/writing.
- **`HazardEvent` (`models/hazard_event.py`)**  
  Normalized incident payload used by analyzers, aggregator, and channels.
- **`DeliveryResult` (`integration/backend_client.py`)**  
  Backend-specific outcome enum (`OK`, `FAILED`, `SKIPPED`) used by
  `AlertManager` to map delivery semantics accurately.

### Dependency shape
- `run_pipeline` creates `PipelineContext`
- `FrameProcessor` depends on `PipelineContext`
- analyzers produce `HazardEvent`
- `AlertManager` consumes `HazardEvent` and backend `DeliveryResult`
- telemetry serializes delivery outcomes via `FrameDeliveryMetrics`

**Key takeaway:** `PipelineContext` + `FrameProcessor` create a clean
orchestration boundary around the core lifecycle.

## 6) Bugs That Were Fixed

| Issue | Risk | Fix |
| --- | --- | --- |
| Delivery semantics ambiguity (`bool` return) | Disabled backend looked like delivery failure, causing incorrect metrics and policy decisions | Introduced enum `DeliveryResult` with `OK/FAILED/SKIPPED`; updated callers |
| Firebase app init check via internal `_apps` | Fragile behavior across SDK changes and multi-init contexts | Switched to `get_app()` with `ValueError` fallback to `initialize_app()` |
| Async metrics mixed delta vs cumulative meaning | Misleading observability and incident triage confusion | Added per-frame fields (`n_*_completed_this_frame`) and kept cumulative totals separate |
| Pipeline orchestration complexity in `run_pipeline` | Hard debugging, fragile edits, and high regression risk | Introduced `PipelineContext` + `FrameProcessor`, reduced `run_pipeline` to orchestration |
| Step report path and uncontrolled writes | Repo root pollution and CI hygiene issues | Gated report by env and forced `OUTPUT_DIR/<timestamp>_report.md` path |

**Key takeaway:** Most fixes reduced ambiguity and made operational behavior
explicit and testable.

## 7) Quick Review Q&A

### Junior (5)
1. **Q:** Why use a latest-frame buffer instead of a long queue?  
   **A:** It prioritizes real-time freshness over historical completeness.
2. **Q:** What object represents one safety incident?  
   **A:** `HazardEvent`.
3. **Q:** Where is backend retry logic implemented?  
   **A:** `BackendClient` in `integration/backend_client.py`.
4. **Q:** What decides whether posture analysis runs this frame?  
   **A:** Profile schedule + module enable flags.
5. **Q:** Where are per-frame metrics emitted?  
   **A:** `MetricsLogger.log_frame()` in `utils/logger.py`.

### Mid-level (5)
1. **Q:** Why keep sync and async delivery metrics separate?  
   **A:** To avoid conflating queue acceptance with actual channel completion.
2. **Q:** How does offline resilience work for backend outages?  
   **A:** Failed payloads are persisted in SQLite and retried via periodic flush.
3. **Q:** Why use an event aggregator after analyzers?  
   **A:** To suppress duplicates, enforce windows, and escalate severity sanely.
4. **Q:** What is the architectural value of `PipelineContext`?  
   **A:** It centralizes dependencies and mutable state for deterministic flow.
5. **Q:** Where should deployment-specific behavior be configured first?  
   **A:** Environment vars for infra, profile YAML for feature behavior.

### Senior (5)
1. **Q:** What is the strongest coupling risk in this architecture?  
   **A:** Schema drift between analyzer outputs and channel payload contracts.
2. **Q:** Which telemetry gap matters most for production SLOs?  
   **A:** Channel latency and queue age distribution, not only success counts.
3. **Q:** What failure mode remains after offline queue support?  
   **A:** Local disk growth/DB corruption under prolonged outage without quotas/GC policy.
4. **Q:** Why is enum-based delivery critical in distributed systems?  
   **A:** It preserves intent and avoids false equivalence between skip and fail states.
5. **Q:** What next refactor yields best maintainability ROI?  
   **A:** Extract explicit typed contracts for inference outputs and delivery metrics.

**Key takeaway:** The right abstractions are not only about code style; they
directly improve correctness, observability, and incident response quality.

