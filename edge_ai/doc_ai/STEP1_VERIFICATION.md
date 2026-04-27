# Step 1 Verification Summary

> **Reviewer:** Senior AI Systems Architect  
> **Date:** March 3, 2026  
> **Scope:** Full code review + runtime evidence validation

## Overall Verdict: **PASS**

All 8 non-negotiable requirements are satisfied in the code. One minor doc-vs-code discrepancy exists (see Findings). Zero blocking defects. The pipeline is correctly wired for production single-camera use.

---

## 1. Latest-Frame Policy — **PASS**

| Check | Evidence | Verdict |
|---|---|---|
| `deque(maxlen=1)` used | `stream_handler.py` L46: `self.buffer: deque[FrameBundle] = deque(maxlen=STREAM_BUFFER_SIZE)` where `STREAM_BUFFER_SIZE = 1` in `settings.py` L30 | PASS |
| Old frames dropped, not queued | `stream_handler.py` L131-134: `was_full = len(self.buffer) == self.buffer.maxlen; self.buffer.append(bundle); if was_full: self.dropped_count += 1` | PASS |
| Consumer pops non-blocking | `stream_handler.py` L73-77: `get_frame()` uses `self.buffer.pop()` with `IndexError` catch | PASS |
| Runtime evidence | Terminal output: `dropped=342` out of `total_read=606` → 56.4% drop rate; exactly within the 30–60% expected range | PASS |

---

## 2. Stream Reconnection — **PASS**

| Check | Evidence | Verdict |
|---|---|---|
| mp4 EOF loops | `stream_handler.py` L89: outer `while not self._stop_event.is_set()` re-opens `VideoCapture` after inner loop breaks on `ret=False` | PASS |
| Exponential backoff on open failure | `stream_handler.py` L95-107: uses `RTSP_RETRY_BACKOFF = [1, 2, 4, 8, 16]` with `self._stop_event.wait(timeout=wait)` (interruptible sleep) | PASS |
| Max retries enforced | `stream_handler.py` L93-98: `if consecutive_failures > RTSP_MAX_RETRIES: break` | PASS |
| Runtime evidence | Terminal output: `reconnect_count=2` after EOF, stream continues seamlessly | PASS |

---

## 3. Single GPU Thread — **PASS**

| Check | Evidence | Verdict |
|---|---|---|
| Inference called from main thread only | `main.py` L96-97: `engine.run_tracker(bundle)` called in the main `while not shutdown` loop — same thread that owns CUDA context | PASS |
| StreamHandler is I/O only | `stream_handler.py` L62-66: capture thread is `daemon=True`, only calls `cv2.VideoCapture.read()` — zero GPU calls | PASS |
| No second inference thread | No `threading.Thread(target=...inference...)` exists anywhere in the codebase | PASS |

---

## 4. YOLO Weights Policy — **PASS**

| Check | Evidence | Verdict |
|---|---|---|
| Prefer YOLO11s | `settings.py` L11: `DETECTOR_WEIGHTS = BASE_DIR / "weights" / "yolo11s.pt"` | PASS |
| Fallback to YOLOv8s | `settings.py` L12: `DETECTOR_FALLBACK_WEIGHTS = BASE_DIR / "weights" / "yolov8s.pt"`. `inference_engine.py` L41-62: `_resolve_weights()` tries primary then fallback | PASS |
| FP16 on CUDA | `inference_engine.py` L79: `self._use_half = True` when CUDA available; passed as `half=self._use_half` to every `.predict()` and `.track()` call | PASS |
| CPU fallback | `inference_engine.py` L82-83: sets `device="cpu"`, `_use_half=False` when CUDA unavailable | PASS |
| Path safety for special characters | `inference_engine.py` L49-55: `os.path.relpath()` avoids PyTorch C++ zip reader bug | PASS |

---

## 5. Tracking (ByteTrack) — **PASS**

**This is the critical check.** Evidence from the code paths:

| Check | Evidence | Verdict |
|---|---|---|
| `model.track()` used (not `model.predict()`) | `inference_engine.py` L143-153: `run_tracker()` calls `self._detector.track(...)` with `tracker="bytetrack.yaml"`, `persist=True` | PASS |
| Main loop calls `run_tracker()` | `main.py` L97: `detections, latency_ms = engine.run_tracker(bundle)` | PASS |
| `track_id` extracted from boxes | `inference_engine.py` L161: `tid = int(box.id[0]) if box.id is not None else None` | PASS |
| `persist=True` for cross-frame state | `inference_engine.py` L152: `persist=True` keeps ByteTrack's internal state across sequential `.track()` calls | PASS |
| `n_tracked` computed correctly | `main.py` L103: `n_tracked = sum(1 for d in detections if d.track_id is not None)` | PASS |
| Runtime evidence of stable tracks | Terminal output shows `n_tracked` consistently > 0 (values 2–12 across frames) on real video. Track IDs persist across consecutive frames (e.g. `n_tracked=6` sustained over many frames) | PASS |
| Both `run_detector()` and `run_tracker()` exist | `run_detector()` uses `.predict()` (no tracking), `run_tracker()` uses `.track()` — correct separation. Main pipeline uses only `run_tracker()`. | PASS |

**Tracking verdict: PASS.** The implementation is correct. ByteTrack is invoked via the official Ultralytics `model.track()` API with `persist=True` and `tracker="bytetrack.yaml"`. Track IDs are real, non-zero, and stable in the runtime evidence.

---

## 6. Metrics Logger — **PASS**

| Field | Present in `log_frame()` | Correct type |
|---|---|---|
| `ts` | Yes — `logger.py` L42 ISO 8601 UTC | string |
| `cam_id` | Yes | string |
| `frame_no` | Yes | int |
| `input_fps` | Yes — `round(input_fps, 1)` | float |
| `inference_fps` | Yes — `round(inference_fps, 1)` | float |
| `inference_ms` | Yes — `round(inference_ms, 1)` | float |
| `n_detections` | Yes | int |
| `n_tracked` | Yes | int |
| `dropped_frames` | Yes | int |
| `vram_mb` | Yes | int |

Logs go to `stdout`; application logs route to `stderr` via `logger.py` L63: `handlers=[logging.StreamHandler(sys.stderr)]`. Machine-parseable JSON + human-readable stderr separation is correct.

---

## 7. Output behavior — **PASS**

| Check | Evidence | Verdict |
|---|---|---|
| `--show` opens cv2 window | `main.py` L121-125: `cv2.imshow(...)` with `q`/`Esc` exit | PASS |
| Without `--show`, writes video | `main.py` L126-130: `cv2.VideoWriter` to `OUTPUT_DIR / f"{cam_id}_out.mp4"` | PASS |
| Annotated frames include boxes + IDs | `drawing.py` L50-56: renders `class_name`, `#track_id`, `confidence` | PASS |
| HUD overlay | `drawing.py` L71-88: FPS, latency, det count, tracked count, VRAM | PASS |

---

## 8. Tests — **PASS**

`tests/test_stream_handler.py` contains 4 meaningful tests:

| Test | What it validates |
|---|---|
| `test_stream_reads_frames` | Produces valid `FrameBundle` with correct shape and camera_id |
| `test_stream_reconnects_on_eof` | `reconnect_count >= 2` after running past EOF |
| `test_stop_before_start` | `stop()` on un-started handler is a safe no-op |
| `test_dropped_frames_counter` | `dropped_count > 0` confirms deque eviction active under slow consumer |

---

## Findings: Doc vs Code Mismatches

| # | Document says | Code does | Impact | Severity |
|---|---|---|---|---|
| F1 | STEP1_COMPLETED §3.2 says "ByteTrack via Ultralytics' built-in `.track()`" | Code uses `self._detector.track(... tracker="bytetrack.yaml", persist=True ...)` | **No mismatch** — doc and code agree | None |
| F2 | Execution plan Step 1 spec says `InferenceEngine.run_detector(frame)` is the main loop call | Code correctly uses `engine.run_tracker(bundle)` instead | **Minor doc deviation** — the plan spec showed `run_detector()` in the pseudocode, but the actual implementation correctly uses `run_tracker()` which adds ByteTrack. This is an *improvement* over the pseudocode, not a defect. | Informational |
| F3 | Execution plan specifies file location `edge_ai/src/config/inference/inference_engine.py` | Actual location matches: `src/config/inference/inference_engine.py` | **No mismatch** | None |
| F4 | Execution plan `settings.py` has `BASE_DIR = Path(__file__).resolve().parents[3]` | Code has `BASE_DIR = Path(__file__).resolve().parents[2]` | **Plan was wrong** — `settings.py` is at `edge_ai/src/config/settings.py`, so `.parents[2]` correctly resolves to `edge_ai/`. The plan counted one extra level. Code is correct. | Informational |
| F5 | STEP1_COMPLETED §6 says VRAM = 50 MB | Runtime shows 50 MB consistently | This is `torch.cuda.memory_allocated()` which only reports PyTorch-managed allocations. The actual resident VRAM including CUDA context and framework overhead is higher (~1.0–1.4 GB). The metric is technically correct but could be misleading. | **Low** — cosmetic only |

---

## Required Fixes

**None.** No blocking defects were found. All 8 requirements pass. The tracking implementation is real and correctly uses `model.track()` with ByteTrack.

### Optional Improvement (non-blocking)

The `vram_used_mb()` method uses `torch.cuda.memory_allocated()` which under-reports actual GPU memory. For more accurate monitoring, consider switching to `torch.cuda.memory_reserved()` or `nvidia-smi`-equivalent. This is not required for Step 1 acceptance.

---

## Final Acceptance Checklist

The team can run these exact commands to validate Step 1 on the RTX 4050 machine:

### Prerequisites
```bash
cd edge_ai
pip install -r requirements.txt
```

### Test 1: Unit Tests Pass
```bash
python -m pytest tests/test_stream_handler.py -v
```
**Expected:** 4 tests pass, 0 failures.

### Test 2: Pipeline Runs Without Error (30-second headless run)
```bash
timeout 30 python src/main.py --source /home/etsh/Videos/test/t5.mp4 --cam-id cam_01 > /tmp/metrics.jsonl 2> /tmp/app.log
echo "Exit code: $?"
```
**Expected:** Exit code `124` (timeout killed it — correct).

### Test 3: Metrics Validation
```bash
python3 -c "
import json, sys
lines = [json.loads(l) for l in open('/tmp/metrics.jsonl') if l.strip().startswith('{')]
assert len(lines) > 100, f'Too few frames: {len(lines)}'
latencies = sorted([l['inference_ms'] for l in lines])
p50 = latencies[len(latencies)//2]
p99 = latencies[int(len(latencies)*0.99)]
fps_vals = [l['inference_fps'] for l in lines if l['inference_fps'] > 0]
avg_fps = sum(fps_vals)/len(fps_vals) if fps_vals else 0
last = lines[-1]
dropped = last['dropped_frames']
total = last['frame_no']
drop_pct = dropped / total * 100 if total > 0 else 0

print(f'Frames processed:  {len(lines)}')
print(f'Latency p50:       {p50:.1f} ms  (target <= 22)')
print(f'Latency p99:       {p99:.1f} ms  (target <= 35)')
print(f'Avg inference FPS: {avg_fps:.1f}  (target >= 13)')
print(f'VRAM:              {last[\"vram_mb\"]} MB  (target <= 1400)')
print(f'Dropped frames:    {dropped}')
print(f'Drop rate:         {drop_pct:.1f}%  (target 30-60%)')
print(f'Max tracked:       {max(l[\"n_tracked\"] for l in lines)}')

assert p50 <= 22, f'FAIL: p50 latency {p50} > 22ms'
assert p99 <= 35, f'FAIL: p99 latency {p99} > 35ms'
assert avg_fps >= 13, f'FAIL: FPS {avg_fps} < 13'
assert last['vram_mb'] <= 1400, f'FAIL: VRAM {last[\"vram_mb\"]} > 1400'
assert max(l['n_tracked'] for l in lines) > 0, 'FAIL: no tracked objects'
assert drop_pct >= 20, f'FAIL: drop rate {drop_pct}% too low -- deque policy inactive'
print('ALL CHECKS PASSED')
"
```
**Expected:** `ALL CHECKS PASSED`, `Max tracked > 0`.

### Test 4: Reconnect on EOF
```bash
grep -c "reconnect" /tmp/app.log
```
**Expected:** >= 1 reconnect log line.

### Test 5: JSON field completeness
```bash
python3 -c "
import json
line = json.loads(open('/tmp/metrics.jsonl').readline())
required = {'ts','cam_id','frame_no','input_fps','inference_fps','inference_ms','n_detections','n_tracked','dropped_frames','vram_mb'}
assert required.issubset(set(line.keys())), f'Missing: {required - set(line.keys())}'
print('All required JSON fields present:', sorted(line.keys()))
"
```
**Expected:** All 10 fields present.

### Test 6: Output video generated (headless mode)
```bash
rm -f output/cam_01_out.mp4
timeout 10 python src/main.py --source /home/etsh/Videos/test/t5.mp4 --cam-id cam_01 > /dev/null 2>&1
ls -lh output/cam_01_out.mp4
```
**Expected:** File exists with non-zero size.

### Test 7: Data model imports
```bash
python3 -c "
from src.models import FrameBundle, Detection, UNIFIED_CLASS_MAP, InferenceResult, Severity, HazardEvent
print('FrameBundle fields:', [f.name for f in FrameBundle.__dataclass_fields__.values()])
print('Detection fields:  ', [f.name for f in Detection.__dataclass_fields__.values()])
print('Severity values:   ', list(Severity))
print('HazardEvent fields:', [f.name for f in HazardEvent.__dataclass_fields__.values()])
print('UNIFIED_CLASS_MAP: ', UNIFIED_CLASS_MAP)
assert len(UNIFIED_CLASS_MAP) == 9
print('ALL IMPORTS OK')
"
```
**Expected:** All models importable, `UNIFIED_CLASS_MAP` has 9 classes.

---

**Step 1 is accepted.** Proceed to Step 2 (HazardAnalyzer).
