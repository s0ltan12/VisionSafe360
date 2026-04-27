"""Structured audit logging for critical backend actions."""

from __future__ import annotations

import logging
import os
import uuid
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Request
from fastapi import WebSocket

from .logging_config import JsonFormatter


@lru_cache(maxsize=1)
def get_audit_logger() -> logging.Logger:
	logger = logging.getLogger("visionsafe.audit")
	if logger.handlers:
		return logger

	log_path = Path(os.getenv("AUDIT_LOG_PATH", str(Path(__file__).resolve().parents[2] / "logs" / "audit.log")))
	log_path.parent.mkdir(parents=True, exist_ok=True)

	handler = RotatingFileHandler(log_path, maxBytes=int(os.getenv("AUDIT_LOG_MAX_BYTES", "10485760")), backupCount=int(os.getenv("AUDIT_LOG_BACKUP_COUNT", "5")), encoding="utf-8")
	handler.setFormatter(JsonFormatter())

	logger.setLevel(logging.INFO)
	logger.propagate = False
	logger.addHandler(handler)
	return logger


def ensure_request_id(request_id: str | None) -> str:
	return request_id or str(uuid.uuid4())


def get_client_ip_from_request(request: Request) -> str:
	forwarded = request.headers.get("x-forwarded-for")
	if forwarded:
		candidate = forwarded.split(",", 1)[0].strip()
		if candidate:
			return candidate

	if request.client and request.client.host:
		return request.client.host

	return "unknown"


def get_client_ip_from_websocket(websocket: WebSocket) -> str:
	forwarded = websocket.headers.get("x-forwarded-for")
	if forwarded:
		candidate = forwarded.split(",", 1)[0].strip()
		if candidate:
			return candidate

	if websocket.client and websocket.client.host:
		return websocket.client.host

	return "unknown"


def audit_event(
	action: str,
	*,
	user_id: str | None,
	ip_address: str,
	request_id: str,
	outcome: str = "success",
	**extra: object,
) -> None:
	logger = get_audit_logger()
	logger.info(
		action,
		extra={
			"event": "audit_event",
			"action": action,
			"user_id": user_id,
			"ip_address": ip_address,
			"request_id": request_id,
			"outcome": outcome,
			**extra,
		},
	)
