"""MVP worker job control routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from ...schemas import JobStartRequest, JobStatusResponse
from ...services.job_service import job_service
from ...utils.security import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.post("/start", response_model=JobStatusResponse)
def start_job(payload: JobStartRequest, authorization: str | None = Header(default=None)):
	token: str | None = None
	if authorization and authorization.lower().startswith("bearer "):
		token = authorization.split(" ", 1)[1].strip()

	try:
		return job_service.start(
			source_name=payload.source_name,
			camera_id=payload.camera_id,
			auth_token=token,
		)
	except FileNotFoundError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc
	except RuntimeError as exc:
		raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop", response_model=JobStatusResponse)
def stop_job():
	return job_service.stop()


@router.get("/status", response_model=JobStatusResponse)
def get_status():
	return job_service.status()