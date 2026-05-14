"""MVP worker job control routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ...config.database import get_db
from ...schemas import JobStartRequest, JobStatusResponse
from ...services.job_service import job_service
from ...utils.permissions import require_roles

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_roles("admin", "operator"))])


@router.post("/start", response_model=JobStatusResponse)
def start_job(
    payload: JobStartRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
	token: str | None = None
	if authorization and authorization.lower().startswith("bearer "):
		token = authorization.split(" ", 1)[1].strip()

	try:
		return job_service.start(
			source_name=payload.source_name,
			camera_id=payload.camera_id,
			auth_token=token,
			db=db,
		)
	except FileNotFoundError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc
	except RuntimeError as exc:
		raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
def stop_job(camera_id: str | None = Query(default=None)):
	try:
		return job_service.stop(camera_id)
	except RuntimeError as exc:
		raise HTTPException(status_code=409, detail=str(exc)) from exc
	except Exception as exc:
		raise HTTPException(status_code=500, detail="Failed to stop worker job") from exc


@router.get("/status")
def get_status(camera_id: str | None = Query(default=None)):
	return job_service.status(camera_id)
