# VisionSafe360 — Safety Failure Modes & Mitigations

> **Audience**: Engineering team, auditors, deployment ops.  
> **Scope**: The three "killer issues" that commonly destroy Safety-AI products in
> the field, plus the hardening layers added to prevent them.

---

## 1. False Alarm Flooding

### Problem

Raw per-frame detections produce far more events than humans or downstream
systems can process.  A single worker without a helmet triggers one
`no_helmet` event **every single frame** (~15–30 per second).  Within minutes
the alert queue is saturated, operators learn to ignore it, and real critical
events are lost in noise.

### Root Cause

The original `HazardAnalyzer` emitted events the instant a rule triggered,
with only per-pair cooldowns that were too short and had no persistence gate
(a single flickering detection frame could fire an alert).

### Mitigation — `EventAggregator`

| Layer | Purpose | Settings constant |
|-------|---------|-------------------|
| **Persistence** | An event must persist for *N* seconds of continuous detection before it is emitted. | `PPE_PERSISTENCE_SEC = 1.5`, `PROXIMITY_PERSISTENCE_SEC = 0.5`, `FALL_PERSISTENCE_SEC = 0.0` |
| **Deduplication** | Events with the same composite key `(camera_id, event_type, track_id [, vehicle_track_id])` are merged, with severity escalated to the worst seen during the window. | `EVENT_AGGREGATION_WINDOW_SEC = 5.0` |
| **Cooldown / Rate Limit** | After emission, the same key is silenced for the remainder of the aggregation window. Max updates per window are capped. | `EVENT_MAX_UPDATES_PER_WINDOW = 3` |

**File**: `src/analysis/event_aggregator.py`

### Validation

- **Before**: run a 60-second clip → count raw events.
- **After**: same clip through `EventAggregator` → count emitted events.
- Expected reduction: 80–95% fewer alerts with zero true-positive loss for
  events lasting > persistence threshold.

---

## 2. Pixel-Space Proximity (Uncalibrated Distances)

### Problem

The proximity analyzer measures the Euclidean distance **in pixels** between a
person's foot-point and a vehicle's foot-point.  In a perspective scene, 100 px
near the camera is ~1 m, while 100 px far from the camera is ~8 m.  The system
either over-alerts (far objects look close) or under-alerts (near objects look
far apart in pixels).

### Root Cause

No camera calibration was performed.  All thresholds were pixel constants
(`PROXIMITY_CRITICAL_PX = 100`, etc.).

### Mitigation — `CalibrationManager`

1. **Per-camera homography**: Operators provide 4 ground-plane reference points
   with known real-world coordinates, stored in `calibration/<cam_id>.json`.
2. **Pixel → metre transform**: `CalibrationManager.compute_distance(cam_id, pt_a, pt_b)`
   projects both points through the homography and returns the distance in
   metres.
3. **Graceful fallback**: If no calibration file exists, the system falls back to
   pixel-mode and shows a prominent **"UNCALIBRATED: PX MODE"** warning on the
   HUD.  Logs also tag events with `calibrated: false` in metadata.
4. **Metre-based thresholds**: `PROXIMITY_CRITICAL_M = 2.0`, `PROXIMITY_HIGH_M = 4.0`,
   `PROXIMITY_WARNING_M = 7.0` — derived from OSHA/construction safety standards.

**File**: `src/analysis/calibration.py`

### Calibration JSON Format

```json
{
  "cam_id": "cam_01",
  "image_points": [[100, 500], [600, 500], [600, 200], [100, 200]],
  "world_points": [[0, 0], [10, 0], [10, 20], [0, 20]],
  "unit": "metres"
}
```

Or a pre-computed 3×3 homography matrix:

```json
{
  "cam_id": "cam_01",
  "homography": [[0.1, 0.0, -10], [0.0, 0.1, -50], [0.0, 0.0, 1.0]],
  "unit": "metres"
}
```

### Validation

- Run the pipeline on a clip with known distances between markers.
- Verify the HUD shows "UNCALIBRATED: PX MODE" when no JSON exists.
- Verify event metadata contains `"calibrated": true` and `"distance_m"` when
  a calibration file is present.

---

## 3. No Evaluation Harness

### Problem

Without a repeatable, automated way to measure the system's output on reference
clips, there is no way to detect regressions.  A model weight update or
threshold change can silently double the false alarm rate with no one noticing
until the system is deployed.

### Root Cause

The project had no offline evaluation script.  Testing was manual
("run and eyeball the cv2 window").

### Mitigation — `eval/run.py`

An offline evaluation harness that:

1. Reads N reference video clips frame-by-frame (no deque-drop — every frame
   is processed for deterministic results).
2. Runs the full pipeline (detector + tracker + hazard analyzer + event
   aggregation) per clip.
3. Captures per-frame telemetry as JSONL.
4. Outputs annotated videos with all overlays.
5. Produces a structured `report.json` with:
   - `event_rate_per_min` — proxy for false alarm density
   - `avg_latency_ms`, `p50/p95/p99_latency_ms` — inference performance
   - `track_stability` — ByteTrack coverage ratio
   - `id_switches_per_min` — tracking correctness
   - Per-event-type counts
   - Calibration status

### Usage

```bash
# Full suite on all clips
python -m eval.run --profile full_suite --clips eval/clips/*.mp4

# Specific profile, no video output (faster)
python -m eval.run --profile ppe_only --clips eval/clips/ppe_test.mp4 --no-video
```

### CI Integration

Compare `report.json` fields across runs:
- `event_rate_per_min` should not increase by > 20% from baseline.
- `p95_latency_ms` should not exceed 50 ms on target hardware.
- `track_stability` should remain > 0.85.

---

## Supporting Components

### TrackQualityMonitor (`src/analysis/track_quality.py`)

Monitors ByteTrack tracking health in real time:
- **Track coverage**: fraction of detections that have a valid track_id.
- **ID switches/min**: rate of tracker re-ID events.
- **Display ID remapping**: assigns stable, monotonically-increasing display IDs
  that don't jump when ByteTrack reassigns raw IDs.  The raw IDs are preserved
  internally for cooldown/deduplication logic; only the rendered label changes.

### Model Capability Check (`src/analysis/capability_check.py`)

At startup, inspects the model's class map:
- Checks for PPE classes (`helmet_off`, `vest_off`, etc.).
- Checks for vehicle classes (custom or COCO fallback).
- Logs **explicit warnings** like:
  > "PPE events will NOT fire until PPE model weights are installed"
  
  This prevents silent misconfiguration where COCO weights are loaded but
  PPE detection is expected.

---

## Settings Reference

All new constants live in `src/config/settings.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `PPE_PERSISTENCE_SEC` | 1.5 | Seconds a PPE violation must persist before emitting |
| `PROXIMITY_PERSISTENCE_SEC` | 0.5 | Seconds a proximity event must persist |
| `FALL_PERSISTENCE_SEC` | 0.0 | Falls emit immediately (already confirmed by state machine) |
| `EVENT_AGGREGATION_WINDOW_SEC` | 5.0 | Dedup/cooldown window |
| `EVENT_MAX_UPDATES_PER_WINDOW` | 3 | Max severity escalations per window |
| `PROXIMITY_CRITICAL_M` | 2.0 | Calibrated critical threshold (metres) |
| `PROXIMITY_HIGH_M` | 4.0 | Calibrated high threshold |
| `PROXIMITY_WARNING_M` | 7.0 | Calibrated warning threshold |
| `PPE_REQUIRED_CLASSES` | `{helmet_off, vest_off}` | Classes that trigger PPE alerts |
| `PPE_ALL_CLASSES` | `{helmet_on, helmet_off, vest_on, vest_off}` | Full PPE class set |
| `VEHICLE_CUSTOM_CLASSES` | `{forklift, excavator, crane, dump_truck}` | Custom vehicle classes |
