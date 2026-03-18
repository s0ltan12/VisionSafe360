"""
main.py
-------
VisionSafe360 — Model 4: Pose Estimation & Ergonomic Risk Assessment
Entry point. Runs the full real-time pipeline:
    Camera / Video -> YOLO11-Pose -> Angles -> RULA/REBA -> Tracker -> Display

Usage
-----
    # live camera
    python main.py

    # video file
    python main.py --source path/to/video.mp4

    # adjust thresholds
    python main.py --rula-threshold 4 --duration 5 --load-kg 5
"""

import argparse
import time
import sys
import cv2

try:
    from ultralytics import YOLO
except ImportError:
    print("[ERROR] ultralytics not installed. Run:  pip install ultralytics")
    sys.exit(1)

from angles    import compute_angles, AngleSmoother
from scoring   import compute_rula, compute_reba
from tracker   import PostureTracker
from visualizer import (draw_skeleton, draw_angle_labels,
                         draw_worker_panel, draw_global_alert, draw_fps)


# ── configuration ──────────────────────────────────────────────────────────────
DEFAULT_MODEL       = "yolo11n-pose.pt"   # nano = fastest; swap to yolo11s-pose.pt for better accuracy
CONF_THRESHOLD      = 0.5                 # minimum YOLO detection confidence
KP_CONF_THRESHOLD   = 0.5                 # minimum keypoint confidence (in angles.py)
SIDE                = "left"              # which arm to use for RULA upper-limb group


def parse_args():
    p = argparse.ArgumentParser(description="VisionSafe360 — Ergonomic Risk Assessment")
    p.add_argument("--source",         default=0,   help="Camera index or video file path")
    p.add_argument("--model",          default=DEFAULT_MODEL)
    p.add_argument("--rula-threshold", default=5,   type=int)
    p.add_argument("--reba-threshold", default=7,   type=int)
    p.add_argument("--duration",       default=3.0, type=float, help="Seconds of bad posture before alert")
    p.add_argument("--load-kg",        default=0.0, type=float, help="Weight being carried (kg)")
    p.add_argument("--muscle-use",     action="store_true",     help="Flag if posture is static/repetitive")
    p.add_argument("--show-angles",    action="store_true",     help="Overlay angle values on frame")
    p.add_argument("--save",           default=None,            help="Path to save output video")
    return p.parse_args()


def run(args):
    # ── load model ─────────────────────────────────────────────────────────────
    print(f"[INFO] Loading model: {args.model}")
    model = YOLO(args.model)

    # ── open video source ──────────────────────────────────────────────────────
    source = int(args.source) if str(args.source).isdigit() else args.source
    cap    = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"[ERROR] Cannot open source: {source}")
        sys.exit(1)

    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30
    w       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[INFO] Source: {w}x{h} @ {fps_src:.1f} FPS")

    # ── optional video writer ──────────────────────────────────────────────────
    writer = None
    if args.save:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(args.save, fourcc, fps_src, (w, h))
        print(f"[INFO] Saving output to: {args.save}")

    # ── per-worker state ───────────────────────────────────────────────────────
    smoothers = {}    # worker_id -> AngleSmoother
    tracker   = PostureTracker(
        rula_threshold=args.rula_threshold,
        reba_threshold=args.reba_threshold,
        duration_sec=args.duration,
    )

    # ── FPS counter ────────────────────────────────────────────────────────────
    fps_counter = 0
    fps_display = 0.0
    fps_timer   = time.monotonic()

    print("[INFO] Running — press Q to quit\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # ── YOLO inference ─────────────────────────────────────────────────────
        results = model(frame, conf=CONF_THRESHOLD, verbose=False)

        active_ids = []

        for result in results:
            if result.keypoints is None:
                continue

            kp_data   = result.keypoints.xy.cpu().numpy()    # (N, 17, 2)
            kp_confs  = result.keypoints.conf.cpu().numpy()  # (N, 17)
            boxes     = result.boxes.xyxy.cpu().numpy()       # (N, 4)

            for worker_id, (keypoints, confs, box) in enumerate(
                    zip(kp_data, kp_confs, boxes)):

                active_ids.append(worker_id)

                # ── smoother init ───────────────────────────────────────────────
                if worker_id not in smoothers:
                    smoothers[worker_id] = AngleSmoother()

                # ── angle computation ───────────────────────────────────────────
                raw_angles      = compute_angles(keypoints, confs, side=SIDE)
                smoothed_angles = smoothers[worker_id].update(raw_angles)

                # ── scoring ─────────────────────────────────────────────────────
                rula_result = compute_rula(
                    smoothed_angles,
                    muscle_use=args.muscle_use,
                    load_kg=args.load_kg,
                )
                reba_result = compute_reba(
                    smoothed_angles,
                    load_kg=args.load_kg,
                )

                # ── duration tracking ───────────────────────────────────────────
                state = tracker.update(worker_id, rula_result, reba_result,
                                       smoothed_angles)

                # ── draw skeleton ───────────────────────────────────────────────
                draw_skeleton(frame, keypoints, confs, KP_CONF_THRESHOLD)

                if args.show_angles:
                    draw_angle_labels(frame, keypoints, confs, smoothed_angles)

                # ── draw score panel ────────────────────────────────────────────
                # stack panels vertically, one per worker
                panel_y = 10 + worker_id * 120
                draw_worker_panel(frame, state, panel_x=10, panel_y=panel_y)

        # ── remove workers that left the frame ─────────────────────────────────
        gone = set(tracker.workers.keys()) - set(active_ids)
        for wid in gone:
            tracker.remove_worker(wid)
            smoothers.pop(wid, None)

        # ── global alert banner ─────────────────────────────────────────────────
        if tracker.get_active_alerts():
            draw_global_alert(frame)

        # ── FPS overlay ─────────────────────────────────────────────────────────
        fps_counter += 1
        elapsed = time.monotonic() - fps_timer
        if elapsed >= 1.0:
            fps_display = fps_counter / elapsed
            fps_counter = 0
            fps_timer   = time.monotonic()
        draw_fps(frame, fps_display)

        # ── display & save ──────────────────────────────────────────────────────
        cv2.imshow("VisionSafe360 — Ergonomic Risk Assessment", frame)
        if writer:
            writer.write(frame)

        # ── console log (every 30 frames) ───────────────────────────────────────
        if fps_counter % 30 == 0:
            print(f"[Frame] {tracker.summary()}")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # ── cleanup ────────────────────────────────────────────────────────────────
    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()
    print("[INFO] Done.")


if __name__ == "__main__":
    run(parse_args())
