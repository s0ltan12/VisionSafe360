"""
Unit tests for ModelCapabilityReport — pose-only stub.

Tests:
  1. ppe_ready always False
  2. has_person always True
  3. log_report runs without error
"""
import sys
from pathlib import Path

import pytest

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.capability_check import ModelCapabilityReport


class TestModelCapabilityReport:
    def test_ppe_not_ready(self):
        """Pose-only pipeline: PPE is never ready."""
        report = ModelCapabilityReport()
        assert report.ppe_ready is False

    def test_has_person(self):
        """Pose model always detects person class."""
        report = ModelCapabilityReport()
        assert report.has_person is True

    def test_log_report_no_crash(self):
        """log_report() should run without errors."""
        report = ModelCapabilityReport()
        report.log_report()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
