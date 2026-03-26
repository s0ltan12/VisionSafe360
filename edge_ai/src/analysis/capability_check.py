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


def check_model_capabilities(
    class_names: Dict[int, str],
    ppe_enabled: bool,
    proximity_enabled: bool,
    fall_enabled: bool,
) -> ModelCapabilityReport:
    """Return a lightweight compatibility report for current detector classes."""
    report = ModelCapabilityReport()
    report.model_classes = class_names or {}

    lower_names = {str(v).strip().lower() for v in report.model_classes.values()}
    report.person_detected = "person" in lower_names

    if (ppe_enabled or fall_enabled) and not report.person_detected:
        report.warnings.append(
            "Detector model does not expose a 'person' class; person-driven analyzers may degrade."
        )

    if proximity_enabled and "forklift" not in lower_names:
        report.warnings.append(
            "Detector model does not expose a 'forklift' class; proximity events may be unavailable."
        )

    if ppe_enabled:
        report.warnings.append(
            "Pose-only capability check does not validate PPE classes. PPE readiness is handled at runtime."
        )

    return report
