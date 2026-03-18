"""
VisionSafe 360 — Model Capability Check (Pose-Only)

Minimal capability report for pose-only pipeline.
Kept for interface compatibility with existing code.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class ModelCapabilityReport:
    """Result of a model capability check."""

    def __init__(self) -> None:
        self.ppe_capable: bool = False
        self.ppe_missing: Set[str] = set()
        self.person_detected: bool = True
        self.warnings: List[str] = []
        self.model_classes: Dict[int, str] = {}

    @property
    def ppe_ready(self) -> bool:
        return False

    @property
    def has_person(self) -> bool:
        return self.person_detected

    def log_report(self) -> None:
        logger.info("Pose-only pipeline — no detector model capability check needed")
        for w in self.warnings:
            logger.warning("  %s", w)
