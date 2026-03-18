"""
Severity — hazard severity levels.
Stub: defined now for importability, fully used from Step 2 onward.
"""
from enum import IntEnum


class Severity(IntEnum):
    """Hazard severity classification (ISO 12100 inspired)."""
    LOW = 1          # informational — e.g. ergonomic score slightly elevated
    MEDIUM = 2       # actionable — e.g. vest missing in non-critical zone
    HIGH = 3         # urgent — e.g. person near forklift without helmet
    CRITICAL = 4     # immediate — e.g. fall detected, collision imminent
