"""File-based incident evidence storage."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("visionsafe.evidence")

_DATA_URL_RE = re.compile(r"^data:(?P<mime>[-\w.]+/[-\w.+]+);base64,(?P<data>.+)$", re.DOTALL)
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


class EvidenceService:
    root = Path(
        os.getenv(
            "EVIDENCE_STORAGE_ROOT",
            str(Path.cwd() / "storage" / "evidence"),
        )
    )

    @classmethod
    def save_data_url(
        cls,
        *,
        camera_id: str,
        incident_id: str,
        data_url: str | None,
        kind: str,
        event_metadata: dict | None = None,
    ) -> str | None:
        if not data_url:
            return None
        match = _DATA_URL_RE.match(data_url)
        if not match:
            return data_url

        mime = match.group("mime")
        extension = _EXTENSIONS.get(mime, ".bin")
        folder = cls.root / cls._safe(camera_id or "unknown") / cls._safe(incident_id)
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{kind}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}{extension}"
        path = folder / filename
        try:
            path.write_bytes(base64.b64decode(match.group("data"), validate=True))
        except Exception as exc:
            logger.warning("failed to persist %s evidence for %s: %s", kind, incident_id, exc)
            return data_url

        metadata_path = folder / "metadata.json"
        metadata = cls._load_metadata(metadata_path)
        metadata.setdefault("incident_id", incident_id)
        metadata.setdefault("camera_id", camera_id)
        metadata.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        metadata.setdefault("files", []).append({
            "kind": kind,
            "path": str(path),
            "url_path": cls._url_path(camera_id, incident_id, filename),
            "mime_type": mime,
            "size_bytes": path.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": event_metadata or {},
        })
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        return cls._url_path(camera_id, incident_id, filename)

    @staticmethod
    def _load_metadata(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "unknown"

    @classmethod
    def _url_path(cls, camera_id: str, incident_id: str, filename: str) -> str:
        return (
            f"/storage/evidence/{cls._safe(camera_id or 'unknown')}/"
            f"{cls._safe(incident_id)}/{filename}"
        )
