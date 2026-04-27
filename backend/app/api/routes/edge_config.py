"""Edge AI configuration control endpoint.

Allows the dashboard to read and update edge AI pipeline settings
(detection toggles, confidence thresholds, model selection) without
requiring a manual restart of the edge AI process.

Settings are persisted in the SystemConfig table and read by the
edge pipeline on each inference cycle via an optional /api/edge/config poll.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...models import SystemConfig
from ...schemas import SystemConfigOut
from ...utils.permissions import require_roles

router = APIRouter(
    prefix="/edge",
    tags=["edge-ai"],
)

_DEFAULTS: dict[str, dict] = {
    "edge.fall_detection.enabled":    {"value": "true",  "value_type": "bool",  "description": "Enable fall detection"},
    "edge.ppe_detection.enabled":     {"value": "true",  "value_type": "bool",  "description": "Enable PPE detection"},
    "edge.proximity_detection.enabled": {"value": "true","value_type": "bool",  "description": "Enable forklift proximity detection"},
    "edge.ergonomics.enabled":        {"value": "true",  "value_type": "bool",  "description": "Enable ergonomic risk analysis"},
    "edge.fall_detection.conf":       {"value": "0.38",  "value_type": "float", "description": "Fall detection confidence threshold"},
    "edge.ppe_detection.conf":        {"value": "0.30",  "value_type": "float", "description": "PPE detection confidence threshold"},
    "edge.proximity_detection.conf":  {"value": "0.40",  "value_type": "float", "description": "Proximity detection confidence threshold"},
    "edge.pose_model":                {"value": "yolo11s-pose.pt", "value_type": "string", "description": "Active pose model filename"},
    "edge.target_fps":                {"value": "15",    "value_type": "int",   "description": "Inference target FPS"},
    "edge.face_blur.enabled":         {"value": "false", "value_type": "bool",  "description": "Blur faces in output frames"},
}


def _ensure_defaults(db: Session) -> None:
    """Seed default edge AI config keys if not already present."""
    for key, meta in _DEFAULTS.items():
        if not db.query(SystemConfig).filter(SystemConfig.key == key).first():
            db.add(SystemConfig(key=key, **meta))
    db.commit()


@router.get("/config", response_model=list[SystemConfigOut])
def get_edge_config(db: Session = Depends(get_db)):
    """Return current edge AI configuration settings (readable by any authenticated user)."""
    _ensure_defaults(db)
    keys = list(_DEFAULTS.keys())
    return db.query(SystemConfig).filter(SystemConfig.key.in_(keys)).order_by(SystemConfig.key).all()


@router.put("/config/{key}", response_model=SystemConfigOut, dependencies=[Depends(require_roles("admin"))])
def update_edge_config(key: str, value: str, db: Session = Depends(get_db)):
    """Update an edge AI configuration value (admin only).

    The edge AI pipeline polls this endpoint periodically and applies
    changes on the next inference cycle.
    """
    _ensure_defaults(db)
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown edge config key: {key}")
    row.value = value
    db.commit()
    db.refresh(row)
    return row
