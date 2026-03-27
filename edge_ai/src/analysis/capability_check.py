"""
VisionSafe 360 — Model Capability Check

Capability report for the multi-model pipeline (pose, PPE, proximity).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class ModelCapabilityReport:
    """Result of a model capability check."""

    def __init__(self) -> None:
        self.pose_capable: bool = False
        self.ppe_capable: bool = False
        self.proximity_capable: bool = False
        self.fall_capable: bool = False
        self.warnings: List[str] = []

    @property
    def ppe_ready(self) -> bool:
        return self.ppe_capable

    @property
    def vehicle_mode(self) -> str:
        return "forklift" if self.proximity_capable else "none"

    def log_report(self) -> None:
        logger.info("═══ Model Capability Report ═══")
        logger.info("  Pose:      %s", "✓" if self.pose_capable else "✗")
        logger.info("  PPE:       %s", "✓" if self.ppe_capable else "✗")
        logger.info("  Proximity: %s", "✓" if self.proximity_capable else "✗")
        logger.info("  Fall:      %s", "✓" if self.fall_capable else "✗")
        for w in self.warnings:
            logger.warning("  ⚠ %s", w)


def check_model_capabilities(
    pose_enabled: bool = False,
    ppe_enabled: bool = False,
    proximity_enabled: bool = False,
    fall_enabled: bool = False,
) -> ModelCapabilityReport:
    """Return a capability report based on enabled features."""
    report = ModelCapabilityReport()
    
    report.pose_capable = pose_enabled
    report.ppe_capable = ppe_enabled
    report.proximity_capable = proximity_enabled
    report.fall_capable = fall_enabled and pose_enabled  # Fall requires pose
    
    if fall_enabled and not pose_enabled:
        report.warnings.append(
            "Fall detection requires pose model — disabled."
        )
    
    if not pose_enabled and not ppe_enabled:
        report.warnings.append(
            "No detection models enabled — pipeline may produce no output."
        )
    
    return report
