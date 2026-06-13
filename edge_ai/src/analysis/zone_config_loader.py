"""Load and apply zone risk metadata to edge hazard events."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from ..models.hazard_event import HazardEvent

logger = logging.getLogger(__name__)


class ZoneConfigLoader:
    """Runtime zone intelligence loaded from configs/zone_config.json."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else self._default_path()
        self._zones: dict[str, dict] = {}
        self._camera_map: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        if not self.config_path.exists():
            logger.info("zone config not found: %s", self.config_path)
            self._zones = {}
            self._camera_map = {}
            return
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("zone config load failed: %s", exc)
            self._zones = {}
            self._camera_map = {}
            return
        self._zones = {
            str(zone_id): dict(config)
            for zone_id, config in (raw.get("zones") or {}).items()
            if isinstance(config, dict)
        }
        self._camera_map = {
            str(camera_id): str(zone_id)
            for camera_id, zone_id in (raw.get("camera_zones") or {}).items()
        }

    def enrich_events(self, events: Iterable[HazardEvent]) -> list[HazardEvent]:
        return [self.enrich_event(event) for event in events]

    def enrich_event(self, event: HazardEvent) -> HazardEvent:
        config = self.zone_for_camera(event.camera_id, event.metadata or {})
        if not config:
            return event
        metadata = dict(event.metadata or {})
        metadata.setdefault("zone_config", config)
        metadata.setdefault("zone_risk", config.get("risk_level"))
        metadata.setdefault("zone_type", config.get("type"))
        metadata.setdefault("zone_display_name", config.get("display_name"))
        metadata.setdefault("zone", config.get("display_name") or config.get("zone_id"))
        return HazardEvent(
            event_type=event.event_type,
            severity=event.severity,
            camera_id=event.camera_id,
            timestamp=event.timestamp,
            frame_number=event.frame_number,
            track_id=event.track_id,
            bbox=event.bbox,
            description=event.description,
            metadata=metadata,
            camera_name=event.camera_name,
            worker_id=event.worker_id,
            worker_gpu_id=event.worker_gpu_id,
        )

    def zone_for_camera(self, camera_id: str, metadata: dict | None = None) -> dict | None:
        metadata = metadata or {}
        explicit = metadata.get("zone_id") or metadata.get("zone_key")
        zone_id = str(explicit) if explicit else self._camera_map.get(str(camera_id))
        if zone_id is None and len(self._zones) == 1:
            zone_id = next(iter(self._zones))
        if zone_id is None:
            return None
        config = self._zones.get(zone_id)
        if not config:
            return None
        return {"zone_id": zone_id, **config}

    @staticmethod
    def _default_path() -> Path:
        return Path(__file__).resolve().parents[3] / "configs" / "zone_config.json"
