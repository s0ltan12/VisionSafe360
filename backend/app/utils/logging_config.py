"""Structured logging setup for backend services."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
	"""Format log records as single-line JSON."""

	_BASE_FIELDS = {
		"name",
		"msg",
		"args",
		"levelname",
		"levelno",
		"pathname",
		"filename",
		"module",
		"exc_info",
		"exc_text",
		"stack_info",
		"lineno",
		"funcName",
		"created",
		"msecs",
		"relativeCreated",
		"thread",
		"threadName",
		"processName",
		"process",
		"message",
		"asctime",
	}

	def format(self, record: logging.LogRecord) -> str:
		payload: dict[str, object] = {
			"ts": datetime.now(timezone.utc).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": record.getMessage(),
		}

		for key, value in record.__dict__.items():
			if key in self._BASE_FIELDS:
				continue
			payload[key] = value

		if record.exc_info:
			payload["exception"] = self.formatException(record.exc_info)

		return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
	"""Configure application-wide logging once."""

	level_name = os.getenv("LOG_LEVEL", "INFO").upper()
	level = getattr(logging, level_name, logging.INFO)
	json_logs = os.getenv("LOG_JSON", "true").strip().lower() in {"1", "true", "yes", "on"}

	handler = logging.StreamHandler(sys.stdout)
	if json_logs:
		handler.setFormatter(JsonFormatter())
	else:
		handler.setFormatter(
			logging.Formatter(
				"%(asctime)s %(levelname)-8s %(name)s %(message)s",
				datefmt="%Y-%m-%d %H:%M:%S",
			)
		)

	root = logging.getLogger()
	root.handlers.clear()
	root.addHandler(handler)
	root.setLevel(level)
