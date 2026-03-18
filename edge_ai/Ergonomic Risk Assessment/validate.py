"""
validate.py
-----------
Validation tool: compare automated RULA/REBA scores against
expert ergonomist scores for a set of test images / video frames.

How to use
----------
1. Collect 50 images of workers in various postures.
2. Have a certified ergonomist score each image manually (RULA + REBA).
3. Fill in EXPERT_SCORES below (or load from a CSV).
4. Run:  python validate.py --images-dir /path/to/images/

The tool will print agreement rate and flag cases where the
automated score differs from the expert by more than 1 point.
"""

import argparse
import os
import csv
import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    print("[ERROR] Run: pip install ultralytics")
    raise

from angles  import compute_angles, AngleSmoother
from scoring import compute_rula, compute_reba


# ── expert scores template ─────────────────────────────────────────────────────
# Format: { "image_filename.jpg": {"rula": X, "reba": Y} }
# Fill this in with your ergonomist's scores before running.
EXPERT_SCORES = {
    # "worker_001.jpg": {"rula": 3, "reba": 4},
    # "worker_002.jpg": {"rula": 6, "reba": 8},
}


def load_expert_scores_csv(path):
    """Load expert scores from CSV with columns: filename, rula, reba"""
    scores = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scores[row["filename"]] = {
                "rula": int(row["rula"]),
                "reba": int(row["reba"]),
            }
    return scores


def score_image(model, image_path):
    """Run the full pipeline on a single image and return scores."""
    frame = cv2.imread(image_path)
    if frame is None:
        return None, None

    results = model(frame, conf=0.5, verbose=False)
    smoother = AngleSmoother(window=1)  # no smoothing for single images

    for result in results:
        if result.keypoints is None:
            continue
        kp_data  = result.keypoints.xy.cpu().numpy()
        kp_confs = result.keypoints.conf.cpu().numpy()

        if len(kp_data) == 0:
            continue

        # use the first detected person
        keypoints = kp_data[0]
        confs     = kp_confs[0]

        raw     = compute_angles(keypoints, confs)
        angles  = smoother.update(raw)
        rula    = compute_rula(angles)
        reba    = compute_reba(angles)
        return rula["final_score"], reba["final_score"]

    return None, None


def run_validation(images_dir, model_path, expert_csv=None):
    model = YOLO(model_path)

    expert = EXPERT_SCORES.copy()
    if expert_csv and os.path.exists(expert_csv):
        expert.update(load_expert_scores_csv(expert_csv))

    if not expert:
        print("[WARN] No expert scores loaded. Add scores to EXPERT_SCORES dict or provide --expert-csv")
        return

    image_files = [f for f in os.listdir(images_dir)
                   if f.lower().endswith((".jpg", ".jpeg", ".png"))]

    total   = 0
    agree_rula = 0
    agree_reba = 0
    mismatches = []

    for fname in sorted(image_files):
        if fname not in expert:
            continue

        path       = os.path.join(images_dir, fname)
        auto_rula, auto_reba = score_image(model, path)

        if auto_rula is None:
            print(f"  [SKIP] {fname} — no person detected")
            continue

        exp_rula = expert[fname]["rula"]
        exp_reba = expert[fname]["reba"]
        diff_rula = abs(auto_rula - exp_rula)
        diff_reba = abs(auto_reba - exp_reba)

        ok_rula = diff_rula <= 1
        ok_reba = diff_reba <= 1
        total  += 1
        if ok_rula: agree_rula += 1
        if ok_reba: agree_reba += 1

        status = "OK" if (ok_rula and ok_reba) else "MISMATCH"
        print(f"  [{status}] {fname:<30} "
              f"RULA: auto={auto_rula} expert={exp_rula} diff={diff_rula} | "
              f"REBA: auto={auto_reba} expert={exp_reba} diff={diff_reba}")

        if status == "MISMATCH":
            mismatches.append({"file": fname, "auto_rula": auto_rula,
                                "exp_rula": exp_rula, "auto_reba": auto_reba,
                                "exp_reba": exp_reba})

    if total == 0:
        print("[WARN] No matching images found.")
        return

    print(f"\n{'='*60}")
    print(f"  Total images evaluated : {total}")
    print(f"  RULA agreement (±1 pt) : {agree_rula}/{total} = {agree_rula/total*100:.1f}%")
    print(f"  REBA agreement (±1 pt) : {agree_reba}/{total} = {agree_reba/total*100:.1f}%")
    target = 80.0
    rula_pass = (agree_rula / total * 100) >= target
    reba_pass = (agree_reba / total * 100) >= target
    print(f"  Target (80%)           : RULA={'PASS' if rula_pass else 'FAIL'}  REBA={'PASS' if reba_pass else 'FAIL'}")
    print(f"{'='*60}\n")

    if mismatches:
        print("  Cases to review:")
        for m in mismatches:
            print(f"    {m['file']}: RULA {m['auto_rula']} vs {m['exp_rula']} | "
                  f"REBA {m['auto_reba']} vs {m['exp_reba']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--images-dir",  required=True)
    p.add_argument("--model",       default="yolo11n-pose.pt")
    p.add_argument("--expert-csv",  default=None, help="CSV with columns: filename, rula, reba")
    args = p.parse_args()
    run_validation(args.images_dir, args.model, args.expert_csv)
