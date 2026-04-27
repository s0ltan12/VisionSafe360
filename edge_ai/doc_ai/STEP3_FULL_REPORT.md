# Step 3 Full Execution Report (VisionSafe360 Edge AI)

Prepared on: 2026-03-20  
Scope: Practical execution plan for Step 3 based on current repository state

---

## 1) Executive Summary

Step 3 is the **Model Training and Validation phase**.  
Your current Step 2 is already near production-readiness, so Step 3 should focus on:

1. Building/cleaning datasets per task.
2. Training or fine-tuning model weights per module.
3. Validating quality against measurable acceptance thresholds.
4. Exporting deployment-ready weights and integrating them into profiles/config.
5. Running offline and near-real pipeline evaluation before rollout.

This report is execution-focused and aligned with your existing runtime pipeline.

Source-of-truth alignment note:
1. Step 3 scope, tracks, and week ranges are aligned to `markdown.md` Phase 3 (Week 4-10, parallel tracks).
2. Quantitative Go/No-Go thresholds in this file use the same numeric targets documented in `markdown.md`.

---

## 2) Step 3 Objective (What must be achieved)

By the end of Step 3, you must have:

1. Stable task-specific weights for:
   - PPE detection
   - Vehicle/Forklift proximity detection
   - Pose model calibration for fall + ergonomics
2. Documented metrics for each model on held-out validation/test sets.
3. Updated weight paths in edge configs/profiles.
4. Evaluation artifacts proving end-to-end behavior on representative clips.
5. A Go/No-Go decision record for deployment to next phase.

---

## 3) Current Readiness Snapshot (from your current codebase)

### 3.1 What is already available

1. Working inference runtime and profile system.
2. Existing eval harness:
   - `eval/run.py` supports running clips through full pipeline and generating report JSON + annotated videos.
3. Existing `weights/` structure and profile-driven model loading.
4. Core analyzers and alerting flow are already implemented.

### 3.2 What is still missing for Step 3 completion

1. Formal training pipeline scripts/notebooks per model (if not already external).
2. Final curated datasets and labels with fixed class taxonomy.
3. Benchmark reports comparing baseline vs tuned weights.
4. Finalized acceptance sign-off document for Step 3.

---

## 4) Step 3 Scope by Model

## 4.1 Model A: PPE Detection

Goal:
- Detect person + PPE compliance classes with high recall for violations.

Execution:
1. Freeze class schema and label mapping.
2. Build train/val/test split with class balance checks.
3. Fine-tune from pretrained detector.
4. Evaluate per-class precision/recall, especially violation classes.
5. Select best checkpoint based on recall/false alarms tradeoff.

Acceptance gate:
- High recall on non-compliance classes and manageable false-positive rate on factory clips.

## 4.2 Model B: Vehicle/Forklift Proximity Detection

Goal:
- Reliable vehicle/forklift detection feeding proximity analyzer.

Execution:
1. Add forklift-heavy data from your real site domain.
2. Fine-tune detection model with class distribution monitoring.
3. Validate with proximity scenarios where person and vehicle co-exist.
4. Re-check distance-risk behavior after detector upgrade.

Acceptance gate:
- Strong vehicle detection in crowded/occluded frames and stable hazard triggering.

## 4.3 Model C: Fall Detection (Pose + rules calibration)

Goal:
- Maximize true fall recall while suppressing bending/kneeling false alarms.

Execution:
1. Validate pose model quality on fall-like movements.
2. Tune temporal/state thresholds using hard negatives.
3. Run controlled fall scenarios and regular work-motion clips.
4. Compare false alarm rate before/after threshold tuning.

Acceptance gate:
- Fall detection sensitivity is high with operationally acceptable false alarms.

## 4.4 Model D: Ergonomics (RULA/REBA on Pose)

Goal:
- Reliable posture risk scoring over sustained time windows.

Execution:
1. Validate keypoint angle stability under real camera perspectives.
2. Tune smoothing/windowing and risk thresholds.
3. Compare score outputs against manually reviewed posture samples.
4. Finalize alert threshold policy for medium/high risk posture.

Acceptance gate:
- Score trend consistency and actionable event generation in long sequences.

---

## 5) Data Plan (Mandatory before full training)

1. Define canonical class dictionary per task.
2. Build non-overlapping splits: train/val/test.
3. Ensure test set remains untouched until final model selection.
4. Add hard negatives intentionally:
   - PPE look-alikes
   - Bending without falling
   - Non-forklift machinery that resembles forklift shape
5. Write dataset manifest with source, counts, and quality notes.

Deliverables:
1. `data_manifest_step3.md` (counts, sources, class balance)
2. `labeling_guidelines_step3.md` (annotation rules)

---

## 6) Execution Timeline (Aligned to markdown.md Phase 3)

Week 4-5:
1. PPE track: dataset cleanup and relabeling to 5-class schema.
2. Vehicle track: vehicle class filtering + forklift subset sourcing + custom forklift data collection.
3. Fall track: pose-sequence extraction from fall datasets.
4. Ergonomics track: implement and unit-test RULA scoring tables.

Week 5-6:
1. PPE Stage 1 training (frozen backbone, 20 epochs).
2. Vehicle detection fine-tuning from COCO-pretrained baseline.
3. Fall threshold calibration on validation sequences.
4. Ergonomics REBA implementation and expert-comparison validation.

Week 6-7:
1. PPE Stage 2 full fine-tune with early stopping and hard-negative pass.
2. Vehicle homography calibration validation (distance MAE checks).
3. Fall on-site simulated events and false-alarm tuning.

Week 7-8:
1. PPE domain adaptation on site footage and export candidate weight.
2. Vehicle + ByteTrack validation and proximity end-to-end verification.
3. Keep top candidate checkpoints per track.

Week 8-10:
1. Final model selection on untouched test sets.
2. Integrate selected weights into `weights/`, `src/config/settings.py`, and `profiles/`.
3. Run offline eval harness package generation and Step 3 sign-off package.

---

## 7) Required Artifacts (Definition of Done for Step 3)

You should not close Step 3 until all items below exist:

1. Final selected weights per enabled module in `weights/`.
2. Model card per task including:
   - dataset version
   - training config
   - final metrics
   - known failure modes
3. Evaluation package:
   - `report.json`
   - sample annotated videos
   - telemetry jsonl
4. Updated profile/config references to chosen weights.
5. Step 3 completion report and Go/No-Go decision.

---

## 8) Validation Workflow You Can Run Now

Use the existing offline evaluator to validate candidate models on clips:

```bash
cd edge_ai
python -m eval.run --profile full_suite --clips eval/clips/*.mp4
```

Fast smoke pass (without writing annotated videos):

```bash
cd edge_ai
python -m eval.run --profile full_suite --clips eval/clips/*.mp4 --no-video
```

What to track from report output:
1. Event rate behavior consistency.
2. Latency percentiles (p50/p95/p99).
3. Track coverage stability.
4. Hazard-type distribution sanity.

---

## 9) Integration Steps After Choosing Final Weights

1. Copy selected model files into `weights/` subfolders.
2. Update model paths in:
   - `src/config/settings.py`
   - relevant profile YAMLs in `profiles/`
3. Run full-suite profile and at least one task-specific profile.
4. Confirm no fallback model is accidentally used unless intended.
5. Save final evaluation report in versioned folder.

---

## 10) Risk Register for Step 3 (Practical)

1. Data drift between training clips and real factory feed.
   - Mitigation: include recent site clips each iteration.
2. Overfitting to staged scenarios.
   - Mitigation: keep unseen test clips and mixed normal-operation footage.
3. False positives increasing after recall tuning.
   - Mitigation: gate by operational false alarm budget, not mAP only.
4. Latency regressions from heavier checkpoints.
   - Mitigation: track p95 latency and reject models that break runtime targets.

---

## 11) Go/No-Go Criteria (Step 3 Exit)

Track-level Go/No-Go thresholds (aligned to markdown.md):
1. PPE: mAP@0.5 >= 88% and Recall(helmet_off) >= 90%.
2. Vehicle: mAP@0.5 >= 88% and Distance MAE <= 1.2 m.
3. Fall: Sensitivity >= 92% and false alarms <= 8 per camera per day.
4. Ergonomics: RULA score +-1 match >= 80% vs expert assessments.

System-level Go if all are true:
1. All active tracks pass their numeric thresholds above.
2. Offline evaluation on representative clips is stable.
3. Runtime latency remains within acceptable bounds for deployment target.
4. Configs/profiles point to final weights and run without manual patching.

No-Go if any are true:
1. Any track fails its numeric threshold.
2. Metrics are unstable across clips.
3. High-risk events are missed in staged tests.
4. New weights break Step 2 runtime stability.

---

## 12) Immediate Next Actions (Today)

1. Freeze Step 3 success metrics per module in one page.
2. Create dataset manifest and split report.
3. Run baseline eval using current pipeline (`eval/run.py`).
4. Start first training/tuning cycle and compare against baseline.
5. Open `STEP3_COMPLETION_REPORT.md` template early and update continuously.

---

## 13) Final Note

Your best strategy is:
1. Keep Step 2 runtime stable as baseline.
2. Iterate Step 3 models in controlled loops.
3. Promote only models that improve safety quality without harming latency/stability.

This prevents rework and gives you a clean handoff to deployment hardening.
