"""
InferenceEngine — Pose-only YOLO model with FP16 inference and ByteTrack.

Design:
- Owns the GPU.  Only ONE thread ever calls methods on this class.
- Loads pose model at startup (provides person detection + keypoints).
- Uses Ultralytics built-in ByteTrack tracker (``model.track(...)``).
"""
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Any

import numpy as np

from ..settings import (
    BASE_DIR,
    CONF_THRESHOLD,
    IMGSZ,
    INFERENCE_DEVICE,
    IOU_THRESHOLD,
    MAX_DET,
    PRECISION,
    POSE_FALLBACK_WEIGHTS,
    POSE_WEIGHTS,
    PROXIMITY_CONF_THRESHOLD,
    PROXIMITY_FALLBACK_WEIGHTS,
    PROXIMITY_FORKLIFT_ALIASES,
    PROXIMITY_IOU_THRESHOLD,
    PROXIMITY_MAX_DET,
    PROXIMITY_WEIGHTS,
    PPE_CONF_THRESHOLD,
    PPE_FALLBACK_WEIGHTS,
    PPE_IOU_THRESHOLD,
    PPE_MAX_DET,
    PPE_WEIGHTS,
)
from ...models.detection import Detection
from ...models.frame_bundle import FrameBundle

logger = logging.getLogger(__name__)

# Custom ByteTrack config with higher track_buffer for better re-identification
_CUSTOM_TRACKER_CFG = Path(__file__).resolve().parent.parent / "bytetrack.yaml"


def _resolve_weights(primary: Path, fallback: Path, label: str) -> str:
    """Return the first weight file that exists as a safe string path.

    PyTorch's C++ PytorchStreamReader can fail on absolute paths containing
    special characters (e.g. apostrophes, non-ASCII).  We use os.path.relpath()
    to produce a relative path from the CWD which avoids this issue.
    """
    for candidate in (primary, fallback):
        if candidate.exists():
            if candidate == fallback:
                logger.warning(
                    "%s weights not found at %s — falling back to %s",
                    label, primary, fallback,
                )
            # Prefer relative path to avoid C++ zip reader bugs with special chars
            try:
                rel = os.path.relpath(candidate)
                if os.path.exists(rel):
                    return rel
            except ValueError:
                pass
            return str(candidate)
    # Neither exists — return model name for Ultralytics auto-download
    logger.info(
        "%s weights not found locally. Attempting Ultralytics auto-download for %s ...",
        label, primary.name,
    )
    return primary.stem  # e.g. "yolo11n-pose" — Ultralytics will attempt download


class InferenceEngine:
    """Pose-only YOLO engine with ByteTrack tracking."""

    def __init__(self) -> None:
        self._pose_model = None
        self._pose_loaded = False
        self._proximity_model = None
        self._proximity_loaded = False
        self._proximity_names = {}
        self._ppe_model = None
        self._ppe_loaded = False
        self._ppe_names = {}

        # Resolve actual device
        import torch
        if "cuda" in INFERENCE_DEVICE and torch.cuda.is_available():
            self.device = INFERENCE_DEVICE
            self._use_half = PRECISION.lower() == "fp16"
            logger.info(
                "CUDA available — using %s with %s",
                self.device,
                "FP16" if self._use_half else "FP32",
            )
        else:
            self.device = "cpu"
            self._use_half = False
            logger.warning("CUDA not available — falling back to CPU (FP32, slower)")

    # ── Model loading ───────────────────────────────────────────────

    def load_pose(self) -> None:
        from ultralytics import YOLO

        weights = _resolve_weights(POSE_WEIGHTS, POSE_FALLBACK_WEIGHTS, "Pose")
        logger.info("Loading pose model: %s", weights)

        try:
            self._pose_model = YOLO(weights)
        except Exception as exc:
            logger.critical("Failed to load pose weights: %s", exc)
            sys.exit(1)

        dummy = np.zeros((IMGSZ, IMGSZ, 3), dtype=np.uint8)
        for _ in range(3):
            self._pose_model.predict(
                dummy, device=self.device, half=self._use_half,
                conf=0.9, verbose=False, imgsz=IMGSZ,
            )
        self._pose_loaded = True
        logger.info("Pose model ready")

    def load_proximity(self, profile_weights: str = "") -> bool:
        """Load optional forklift/person detector.

        If ``profile_weights`` is set and the path exists (relative to ``edge_ai/``),
        it is used; otherwise falls back to ``PROXIMITY_WEIGHTS`` / ``PROXIMITY_FALLBACK_WEIGHTS``.

        Returns True if model loaded, False if weights are unavailable.
        """
        from ultralytics import YOLO

        candidate: Path | None = None
        source_label = ""
        if profile_weights and profile_weights.strip():
            pw = Path(profile_weights.strip())
            if not pw.is_absolute():
                pw = BASE_DIR / pw
            if pw.exists():
                candidate = pw
                source_label = f"profile({profile_weights.strip()})"

        if candidate is None and PROXIMITY_WEIGHTS.exists():
            candidate = PROXIMITY_WEIGHTS
            source_label = "primary(best_forklift.pt)"
        if candidate is None and PROXIMITY_FALLBACK_WEIGHTS.exists():
            candidate = PROXIMITY_FALLBACK_WEIGHTS
            source_label = "fallback(yolov8n.pt)"

        if candidate is None:
            logger.warning(
                "Proximity model disabled: no weights found at %s or %s",
                PROXIMITY_WEIGHTS,
                PROXIMITY_FALLBACK_WEIGHTS,
            )
            return False

        try:
            rel = os.path.relpath(candidate)
            weights = rel if os.path.exists(rel) else str(candidate)
        except ValueError:
            weights = str(candidate)
        logger.info("Loading proximity model from %s: %s", source_label, weights)

        try:
            self._proximity_model = YOLO(weights)
            self._proximity_names = {
                int(k): str(v).strip().lower()
                for k, v in getattr(self._proximity_model, "names", {}).items()
            }
            self._proximity_loaded = True
            logger.info("Proximity model ready: %s", source_label)
            logger.info("Proximity classes available: %s", list(self._proximity_names.values()))
            return True
        except Exception as exc:
            logger.error("Failed to load proximity model: %s", exc)
            self._proximity_model = None
            self._proximity_names = {}
            self._proximity_loaded = False
            return False

    def load_ppe(self, profile_weights: str = "") -> bool:
        """Load optional PPE detector.

        Supports profile override path, then falls back to PPE_WEIGHTS and
        PPE_FALLBACK_WEIGHTS.
        """
        from ultralytics import YOLO

        candidate: Path | None = None
        source_label = ""
        if profile_weights and profile_weights.strip():
            pw = Path(profile_weights.strip())
            if not pw.is_absolute():
                pw = BASE_DIR / pw
            if pw.exists():
                candidate = pw
                source_label = f"profile({profile_weights.strip()})"

        if candidate is None and PPE_WEIGHTS.exists():
            candidate = PPE_WEIGHTS
            source_label = "primary(yolo9e.pt)"
        if candidate is None and PPE_FALLBACK_WEIGHTS.exists():
            candidate = PPE_FALLBACK_WEIGHTS
            source_label = "fallback(best_ppe.pt)"

        if candidate is None:
            logger.warning(
                "PPE model disabled: no weights found at %s or %s",
                PPE_WEIGHTS,
                PPE_FALLBACK_WEIGHTS,
            )
            return False

        try:
            rel = os.path.relpath(candidate)
            weights = rel if os.path.exists(rel) else str(candidate)
        except ValueError:
            weights = str(candidate)
        logger.info("Loading PPE model from %s: %s", source_label, weights)

        try:
            self._ppe_model = YOLO(weights)
            self._ppe_names = {
                int(k): str(v).strip().lower()
                for k, v in getattr(self._ppe_model, "names", {}).items()
            }
            self._ppe_loaded = True
            logger.info("PPE model ready: %s", source_label)
            logger.info("PPE classes available: %s", list(self._ppe_names.values()))
            return True
        except Exception as exc:
            logger.error("Failed to load PPE model: %s", exc)
            self._ppe_model = None
            self._ppe_names = {}
            self._ppe_loaded = False
            return False

    # ── Inference ───────────────────────────────────────────────────

    def run_pose_tracker(self, bundle: FrameBundle) -> Tuple[Any, List[Detection], float]:
        """Run pose model with ByteTrack — returns (raw_pose_results, tracked_detections, latency_ms).

        The pose model detects persons and their keypoints simultaneously.
        ByteTrack provides persistent track IDs for each person.
        """
        assert self._pose_loaded, "Call load_pose() first"
        t0 = time.perf_counter()

        tracker_cfg = str(_CUSTOM_TRACKER_CFG) if _CUSTOM_TRACKER_CFG.exists() else "bytetrack.yaml"
        results = self._pose_model.track(
            bundle.frame,
            device=self.device,
            half=self._use_half,
            imgsz=IMGSZ,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            max_det=MAX_DET,
            tracker=tracker_cfg,
            persist=True,
            verbose=False,
        )[0]

        latency_ms = (time.perf_counter() - t0) * 1000.0

        detections: List[Detection] = []
        if results.boxes is not None and len(results.boxes):
            for box in results.boxes:
                tid = int(box.id[0]) if box.id is not None else None
                detections.append(Detection(
                    class_id=0,
                    class_name="person",
                    confidence=float(box.conf[0]),
                    bbox=(
                        int(box.xyxy[0][0]), int(box.xyxy[0][1]),
                        int(box.xyxy[0][2]), int(box.xyxy[0][3]),
                    ),
                    track_id=tid,
                ))

        return results, detections, latency_ms

    def run_pose(self, bundle: FrameBundle) -> Tuple[Any, float]:
        """Run pose model (predict only, no tracking).  Returns (raw Results, latency_ms)."""
        assert self._pose_loaded, "Call load_pose() first"
        t0 = time.perf_counter()
        results = self._pose_model.predict(
            bundle.frame,
            device=self.device,
            half=self._use_half,
            imgsz=IMGSZ,
            conf=0.40,
            verbose=False,
        )[0]
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return results, latency_ms

    def run_proximity(self, bundle: FrameBundle) -> Tuple[List[Detection], float]:
        """Run optional detect model for forklift/person proximity."""
        if not self._proximity_loaded:
            return [], 0.0

        t0 = time.perf_counter()
        results = self._proximity_model.predict(
            bundle.frame,
            device=self.device,
            half=self._use_half,
            imgsz=IMGSZ,
            conf=PROXIMITY_CONF_THRESHOLD,
            iou=PROXIMITY_IOU_THRESHOLD,
            max_det=PROXIMITY_MAX_DET,
            verbose=False,
        )[0]
        latency_ms = (time.perf_counter() - t0) * 1000.0

        detections: List[Detection] = []
        if results.boxes is not None and len(results.boxes):
            for box in results.boxes:
                cid = int(box.cls[0])
                cname = self._proximity_names.get(cid, str(cid)).lower()
                norm = cname.replace("-", "_").replace(" ", "_")

                # Keep only classes needed by this pipeline.
                if (norm in PROXIMITY_FORKLIFT_ALIASES
                        or ("fork" in norm and "lift" in norm)):
                    cname = "forklift"
                if cname not in {"forklift", "person"}:
                    continue

                detections.append(Detection(
                    class_id=cid,
                    class_name=cname,
                    confidence=float(box.conf[0]),
                    bbox=(
                        int(box.xyxy[0][0]), int(box.xyxy[0][1]),
                        int(box.xyxy[0][2]), int(box.xyxy[0][3]),
                    ),
                    track_id=None,
                ))

        return detections, latency_ms

    def run_ppe(self, bundle: FrameBundle) -> Tuple[List[Detection], float]:
        """Run optional PPE detector and normalize relevant classes for UI panels."""
        if not self._ppe_loaded:
            return [], 0.0

        t0 = time.perf_counter()
        results = self._ppe_model.predict(
            bundle.frame,
            device=self.device,
            half=self._use_half,
            imgsz=IMGSZ,
            conf=PPE_CONF_THRESHOLD,
            iou=PPE_IOU_THRESHOLD,
            max_det=PPE_MAX_DET,
            verbose=False,
        )[0]
        latency_ms = (time.perf_counter() - t0) * 1000.0

        detections: List[Detection] = []
        if results.boxes is not None and len(results.boxes):
            for box in results.boxes:
                cid = int(box.cls[0])
                cname = self._ppe_names.get(cid, str(cid)).lower()
                norm = cname.replace("-", "_").replace(" ", "_")

                # Normalize SH17-style classes to panel-friendly names.
                if norm in {"helmet", "hardhat", "hard_hat", "helmet_on"}:
                    mapped = "helmet_on"
                elif norm in {"head", "helmet_off", "no_helmet", "bare_head"}:
                    mapped = "helmet_off"
                elif norm in {"gloves", "glove", "gloves_on"}:
                    mapped = "gloves_on"
                elif norm in {"hands", "hand", "bare_hands", "no_gloves", "gloves_off"}:
                    mapped = "gloves_off"
                elif norm in {"glasses", "goggles", "eye_protection"}:
                    mapped = "glasses"
                elif norm in {"face_mask", "face-mask", "mask"}:
                    mapped = "face_mask"
                elif norm in {"face_guard", "face-guard", "shield"}:
                    mapped = "face_guard"
                elif norm in {"ear_mufs", "ear_muffs", "hearing_protection"}:
                    mapped = "ear_muffs"
                elif norm in {"ear"}:
                    mapped = "ear"
                elif norm in {"face"}:
                    mapped = "face"
                elif norm in {"safety_vest", "safety-vest", "vest", "vest_on"}:
                    mapped = "safety_vest"
                elif norm in {"vest_off", "no_vest"}:
                    mapped = "vest_off"
                elif norm in {"safety_suit", "coverall", "coveralls"}:
                    mapped = "safety_suit"
                elif norm in {"medical_suit", "hazmat"}:
                    mapped = "medical_suit"
                elif norm in {"shoes", "boots", "safety_shoes"}:
                    mapped = "shoes"
                elif norm in {"foot", "bare_foot"}:
                    mapped = "bare_foot"
                elif norm in {"tool"}:
                    mapped = "tool"
                else:
                    continue

                detections.append(Detection(
                    class_id=cid,
                    class_name=mapped,
                    confidence=float(box.conf[0]),
                    bbox=(
                        int(box.xyxy[0][0]), int(box.xyxy[0][1]),
                        int(box.xyxy[0][2]), int(box.xyxy[0][3]),
                    ),
                    track_id=None,
                ))

        return detections, latency_ms

    def run_ppe_person_tracker(self, bundle: FrameBundle) -> Tuple[List[Detection], float]:
        """Track persons using PPE model (SH17) with ByteTrack for robust IDs."""
        if not self._ppe_loaded:
            return [], 0.0

        t0 = time.perf_counter()
        tracker_cfg = str(_CUSTOM_TRACKER_CFG) if _CUSTOM_TRACKER_CFG.exists() else "bytetrack.yaml"
        results = self._ppe_model.track(
            bundle.frame,
            device=self.device,
            half=self._use_half,
            imgsz=IMGSZ,
            conf=PPE_CONF_THRESHOLD,
            iou=PPE_IOU_THRESHOLD,
            max_det=PPE_MAX_DET,
            tracker=tracker_cfg,
            persist=True,
            verbose=False,
        )[0]
        latency_ms = (time.perf_counter() - t0) * 1000.0

        detections: List[Detection] = []
        if results.boxes is not None and len(results.boxes):
            for box in results.boxes:
                cid = int(box.cls[0])
                cname = self._ppe_names.get(cid, str(cid)).lower()
                norm = cname.replace("-", "_").replace(" ", "_")
                if norm != "person":
                    continue

                tid = int(box.id[0]) if box.id is not None else None
                detections.append(Detection(
                    class_id=cid,
                    class_name="person",
                    confidence=float(box.conf[0]),
                    bbox=(
                        int(box.xyxy[0][0]), int(box.xyxy[0][1]),
                        int(box.xyxy[0][2]), int(box.xyxy[0][3]),
                    ),
                    track_id=tid,
                ))

        return detections, latency_ms

    # ── Diagnostics ─────────────────────────────────────────────────

    @staticmethod
    def vram_used_mb() -> int:
        """Current VRAM allocated (MB).  Returns 0 on CPU."""
        try:
            import torch
            if torch.cuda.is_available():
                return int(torch.cuda.memory_allocated() / (1024 * 1024))
        except Exception:
            pass
        return 0
