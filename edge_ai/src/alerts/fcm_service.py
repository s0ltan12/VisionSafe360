"""Firebase Cloud Messaging service.

Default behavior is mock mode to keep local development dependency-free while
preserving the same API used in production.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import settings
from ..models.hazard_event import HazardEvent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FCMConfig:
	"""Configuration for FCMService."""

	enabled: bool = settings.FCM_ENABLED
	mock_mode: bool = settings.FCM_MOCK_MODE
	credentials_path: str = settings.FCM_CREDENTIALS_PATH
	device_tokens: tuple[str, ...] = tuple(settings.FCM_DEVICE_TOKENS)
	retry_once: bool = True


class FCMService:
	"""Send hazard notifications through FCM.

	The service never raises to callers; errors are logged and converted to a
	``False`` return value.
	"""

	def __init__(self, config: Optional[FCMConfig] = None) -> None:
		"""Create service with lazy Firebase initialization.

		Args:
			config: Optional configuration override.

		Returns:
			None.

		Failure Behavior:
			Never raises during initialization; invalid Firebase setup is
			deferred to first real send attempt.
		"""

		self.config = config or FCMConfig()
		self._firebase_ready = False
		self._warned_no_tokens = False

	def send_event(self, event: HazardEvent) -> bool:
		"""Send one hazard event notification.

		Args:
			event: HazardEvent to be sent to devices.

		Returns:
			True if at least one notification send succeeds; False otherwise.

		Failure Behavior:
			Never raises; all failures are converted into a False result.
		"""

		title = f"VisionSafe {event.severity.name}"
		body = event.description or event.event_type
		data = {
			"event_type": event.event_type,
			"severity": event.severity.name,
			"camera_id": event.camera_id,
			"camera_name": event.camera_name or event.camera_id,
			"worker_id": event.worker_id or "",
			"worker_gpu_id": event.worker_gpu_id or "",
			"frame_number": str(event.frame_number),
			"timestamp": str(event.timestamp),
			"track_id": "" if event.track_id is None else str(event.track_id),
		}
		return self.send_payload(title=title, body=body, data=data)

	def send_payload(self, title: str, body: str, data: dict) -> bool:
		"""Send a prepared payload to all configured tokens.

		Args:
			title: Notification title.
			body: Notification body text.
			data: Key-value payload for client-side handling.

		Returns:
			True when delivery succeeds to at least one recipient.

		Failure Behavior:
			Never raises. If configured tokens are missing or the provider
			fails, returns False.
		"""

		if not self.config.enabled:
			return False

		if not self.config.device_tokens:
			if not self._warned_no_tokens:
				logger.warning("FCM enabled but no device tokens configured")
				self._warned_no_tokens = True
			return False

		if self.config.mock_mode:
			logger.info(
				"fcm mock send title=%s body=%s tokens=%d",
				title,
				body,
				len(self.config.device_tokens),
			)
			return True

		attempts = 2 if self.config.retry_once else 1
		for attempt in range(attempts):
			ok = self._send_real(title=title, body=body, data=data)
			if ok:
				return True
			if attempt == 0 and attempts > 1:
				logger.warning("FCM send failed, retrying once")
		return False

	def _send_real(self, title: str, body: str, data: dict) -> bool:
		# Send payload using Firebase Admin SDK.

		try:
			if not self._firebase_ready and not self._ensure_firebase_app():
				return False

			from firebase_admin import messaging

			success = 0
			for token in self.config.device_tokens:
				message = messaging.Message(
					token=token,
					notification=messaging.Notification(title=title, body=body),
					data={k: str(v) for k, v in data.items()},
				)
				try:
					messaging.send(message)
					success += 1
				except Exception as exc:
					logger.warning("fcm token send failed token=%s error=%s", token[-8:], exc)

			return success > 0
		except Exception as exc:
			logger.exception("fcm send failed: %s", exc)
			return False

	def _ensure_firebase_app(self) -> bool:
		# Initialize Firebase app once.

		try:
			import firebase_admin
			from firebase_admin import credentials

			cred_path = Path(self.config.credentials_path)
			if not cred_path.exists():
				logger.error("FCM credentials file not found: %s", cred_path)
				return False

			try:
				firebase_admin.get_app()
			except ValueError:
				firebase_admin.initialize_app(
					credentials.Certificate(str(cred_path))
				)
			self._firebase_ready = True
			return True
		except Exception as exc:
			logger.exception("FCM init failed: %s", exc)
			self._firebase_ready = False
			return False
