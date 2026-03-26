"""
VisionSafe 360 — Profile Loader

Reads a YAML profile and exposes a typed ProfileConfig that controls
which modules are active, which weights they use, and scheduling rates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

from .settings import (
    BASE_DIR,
    PROFILES_DIR,
    POSE_EVERY_N,
    FALL_EVERY_N,
    ERGONOMIC_EVERY_N,
)

logger = logging.getLogger(__name__)


# ─── Typed config dataclasses ───────────────────────────────────────

@dataclass
class SubModuleConfig:
    enabled: bool = False
    weights: str = ""            # empty → use shared detector output
    schedule_every_n: int = 1


@dataclass
class ModuleConfig:
    enabled: bool = False
    weights: str = ""
    schedule_every_n: int = 1
    sub_modules: Dict[str, SubModuleConfig] = field(default_factory=dict)


@dataclass
class ProfileConfig:
    """Parsed profile — drives the module registry."""
    profile_name: str = "default"
    description: str = ""
    modules: Dict[str, ModuleConfig] = field(default_factory=dict)
    # Raw ``ui:`` section from the profile YAML — consumed by UISettings
    ui_config: dict = field(default_factory=dict)
    # Source for person tracking: "pose" (default) or "ppe"
    person_tracker_source: str = "pose"

    # ── Convenience accessors ───────────────────────────────────────

    def is_enabled(self, module_name: str) -> bool:
        m = self.modules.get(module_name)
        return m.enabled if m else False

    def get_weights(self, module_name: str) -> str:
        m = self.modules.get(module_name)
        return m.weights if m else ""

    def get_schedule(self, module_name: str) -> int:
        m = self.modules.get(module_name)
        return m.schedule_every_n if m else 1

    def is_sub_enabled(self, module_name: str, sub_name: str) -> bool:
        m = self.modules.get(module_name)
        if not m or not m.enabled:
            return False
        sm = m.sub_modules.get(sub_name)
        return sm.enabled if sm else False

    def get_sub_weights(self, module_name: str, sub_name: str) -> str:
        m = self.modules.get(module_name)
        if not m:
            return ""
        sm = m.sub_modules.get(sub_name)
        return sm.weights if sm else ""

    def get_sub_schedule(self, module_name: str, sub_name: str) -> int:
        m = self.modules.get(module_name)
        if not m:
            return 1
        sm = m.sub_modules.get(sub_name)
        return sm.schedule_every_n if sm else 1


# ─── Loader ─────────────────────────────────────────────────────────

def _parse_sub_modules(raw: dict) -> Dict[str, SubModuleConfig]:
    result: Dict[str, SubModuleConfig] = {}
    for name, cfg in raw.items():
        if isinstance(cfg, dict):
            result[name] = SubModuleConfig(
                enabled=cfg.get("enabled", False),
                weights=cfg.get("weights", ""),
                schedule_every_n=cfg.get("schedule_every_n", 1),
            )
    return result


def _parse_module(raw: dict) -> ModuleConfig:
    subs = {}
    if "sub_modules" in raw and isinstance(raw["sub_modules"], dict):
        subs = _parse_sub_modules(raw["sub_modules"])
    return ModuleConfig(
        enabled=raw.get("enabled", False),
        weights=raw.get("weights", ""),
        schedule_every_n=raw.get("schedule_every_n", 1),
        sub_modules=subs,
    )


def load_profile(name_or_path: Optional[str] = None) -> ProfileConfig:
    """Load a profile by name (looked up in profiles/) or by absolute path.

    Returns a default full_suite config if name_or_path is None or missing.
    """
    if name_or_path is None:
        name_or_path = "full_suite"

    # Resolve path
    path = Path(name_or_path)
    if not path.exists():
        # Try profiles/ directory
        path = PROFILES_DIR / f"{name_or_path}.yaml"
    if not path.exists():
        path = PROFILES_DIR / name_or_path
    if not path.exists():
        logger.warning(
            "Profile '%s' not found — using built-in full_suite defaults",
            name_or_path,
        )
        return _default_profile()

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    profile = ProfileConfig(
        profile_name=data.get("profile_name", path.stem),
        description=data.get("description", ""),
    )
    modules_raw = data.get("modules", {})
    for mod_name, mod_cfg in modules_raw.items():
        if isinstance(mod_cfg, dict):
            profile.modules[mod_name] = _parse_module(mod_cfg)

    profile.ui_config = data.get("ui", {})
    profile.person_tracker_source = str(
        data.get("person_tracker_source", "pose")
    ).strip().lower()
    if profile.person_tracker_source not in {"pose", "ppe"}:
        logger.warning(
            "Invalid person_tracker_source='%s' in profile; falling back to 'pose'",
            profile.person_tracker_source,
        )
        profile.person_tracker_source = "pose"

    logger.info("Loaded profile: %s — %s", profile.profile_name, profile.description)
    return profile


def _default_profile() -> ProfileConfig:
    """Hardcoded full_suite fallback (pose-only pipeline)."""
    return ProfileConfig(
        profile_name="full_suite",
        description="Fall detection + ergonomic assessment (built-in default)",
        modules={
            "pose": ModuleConfig(enabled=True, schedule_every_n=POSE_EVERY_N),
            "hazard_analyzer": ModuleConfig(
                enabled=True,
                sub_modules={
                    "fall": SubModuleConfig(enabled=True, schedule_every_n=FALL_EVERY_N),
                },
            ),
            "posture_analyzer": ModuleConfig(
                enabled=True, schedule_every_n=ERGONOMIC_EVERY_N,
            ),
        },
    )
