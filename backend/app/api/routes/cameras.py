"""Camera routes with stream control endpoints."""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...schemas import CameraCreate, CameraOut, CameraUpdate
from ...services.camera_service import CameraService
from ...services.job_service import job_service
from ...utils.media import stream_upload_to_videos_dir
from ...utils.permissions import require_roles

router = APIRouter(
    prefix="/cameras",
    tags=["cameras"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)


@router.get("", response_model=List[CameraOut])
def get_cameras(db: Session = Depends(get_db)):
    """Return all cameras (no pagination needed — camera counts are small)."""
    items, _ = CameraService.list(db, skip=0, limit=10_000)
    return items


@router.post("", response_model=CameraOut, status_code=201)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    return CameraService.create(db, payload)


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: str, payload: CameraUpdate, db: Session = Depends(get_db)):
    updated = CameraService.update(db, camera_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Camera not found")
    return updated


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    if not CameraService.delete(db, camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")


@router.post("/upload", response_model=CameraOut, status_code=201)
async def upload_and_create_camera(
    file: UploadFile = File(...),
    name: str = Form(...),
    zone: str = Form(...),
    area_name: Optional[str] = Form(None),
    zone_name: Optional[str] = Form(None),
    location_description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a video file and register it as a Camera source in one shot.

    Used by the unified "Add Source" modal when the user picks the
    "Video File" source type. Avoids orphan files that would occur with
    a two-step upload-then-create flow.
    """
    try:
        safe_name = await stream_upload_to_videos_dir(file)
    finally:
        await file.close()

    payload = CameraCreate(
        name=name,
        zone=zone,
        area_name=area_name,
        zone_name=zone_name,
        location_description=location_description,
        stream_url=safe_name,
        source_type="file",
        status="Online",
        fps=0,
        health=100,
    )
    return CameraService.create(db, payload)


# ── Stream control endpoints ──────────────────────────────────────────

@router.post("/{camera_id}/start")
def start_camera_stream(
    camera_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Start AI detection on a camera's configured stream_url.

    Looks up the camera in DB, resolves its stream_url, and enqueues the
    edge AI worker job. Returns job status + stream source info.
    """
    camera = CameraService.get(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

    if not camera.stream_url:
        raise HTTPException(
            status_code=422,
            detail=f"Camera '{camera_id}' has no stream_url configured. "
                   "Update stream_url via PATCH /api/cameras/{camera_id} first.",
        )

    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    try:
        status = job_service.start(
            source_name=camera.stream_url,
            camera_id=camera_id,
            auth_token=token,
            db=db,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Mark camera as Online/Streaming
    CameraService.update(db, camera_id, CameraUpdate(status="Online"))

    return {
        "job_id": status.get("source_name"),
        "status": "streaming",
        "source": camera.stream_url,
        "camera_id": camera_id,
        "camera_name": camera.name,
        "ws_stream_url": f"/ws/stream/{camera_id}",
        "worker": status,
    }


@router.post("/{camera_id}/stop")
def stop_camera_stream(
    camera_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Stop the AI detection worker and mark camera as offline."""
    camera = CameraService.get(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

    status = job_service.stop(camera_id)
    CameraService.update(db, camera_id, CameraUpdate(status="Offline"))

    return {
        "status": "stopped",
        "camera_id": camera_id,
        "camera_name": camera.name,
        "worker": status,
    }


@router.get("/{camera_id}/status")
def get_camera_stream_status(
    camera_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return camera info combined with current job/stream status."""
    camera = CameraService.get(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

    job_status = job_service.status(camera_id)
    is_this_camera_running = (
        job_status.get("running")
        and job_status.get("camera_id") == camera_id
    )

    return {
        "camera_id": camera.id,
        "camera_name": camera.name,
        "zone": camera.zone,
        "status": camera.status,
        "stream_url": camera.stream_url,
        "ws_stream_url": f"/ws/stream/{camera_id}",
        "streaming": is_this_camera_running,
        "job": job_status if is_this_camera_running else None,
    }
