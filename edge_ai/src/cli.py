"""CLI argument parsing and entry point for the edge AI pipeline.

Extracted from main.py — preserves original CLI behavior unchanged.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config.profile import load_profile
from .config.settings import LOG_LEVEL
from .utils.logger import setup_logging
from .pipeline.orchestrator import run_pipeline
from .pipeline.multi_camera import run_multi_camera_pipeline

logger = logging.getLogger("PipelineOrchestrator")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="VisionSafe 360 — Real-time safety monitoring pipeline",
    )
    p.add_argument(
        "--source",
        help="Single source: path to .mp4 file, RTSP URL, or camera index (0 for webcam).",
    )
    p.add_argument(
        "--sources", nargs="+",
        help="Multiple sources for parallel processing (RTSP URLs or video files).",
    )
    p.add_argument(
        "--cam-id", default="cam_01",
        help="Logical camera identifier (default: cam_01). For multi-source, auto-increments.",
    )
    p.add_argument(
        "--show", action="store_true",
        help="Display annotated frames in cv2.imshow windows.",
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Run without GUI. Stream annotated frames to Redis for dashboard.",
    )
    p.add_argument(
        "--profile", default="full_suite",
        help="Profile name or path (default: full_suite).",
    )
    return p.parse_args()


def _validate_source(source: str) -> str | int:
    """Validate and normalize a single source path/URL/index."""
    is_camera_index = source.isdigit()
    is_rtsp = source.startswith("rtsp")
    if not is_camera_index and not is_rtsp and not Path(source).exists():
        logger.error("Source file not found: %s", source)
        sys.exit(1)
    if is_camera_index:
        return int(source)
    return source


def main() -> None:
    setup_logging(LOG_LEVEL)
    args = parse_args()

    # Determine sources list
    sources = []
    if args.sources:
        sources = [_validate_source(s) for s in args.sources]
    elif args.source:
        sources = [_validate_source(args.source)]
    else:
        logger.error("Either --source or --sources is required")
        sys.exit(1)

    profile = load_profile(args.profile)

    headless = getattr(args, 'headless', False)

    if len(sources) == 1:
        # Single camera - use original pipeline
        run_pipeline(source=sources[0], cam_id=args.cam_id, show=args.show, profile=profile, headless=headless)
    else:
        # Multiple cameras - use parallel pipeline with shared models
        run_multi_camera_pipeline(sources=sources, show=args.show, profile=profile)
