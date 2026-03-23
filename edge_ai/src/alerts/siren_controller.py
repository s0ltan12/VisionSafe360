"""Siren control abstraction for CRITICAL hazards."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ..config import settings
from ..models.hazard_event import HazardEvent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SirenConfig:
	"""Configuration for siren behavior."""

	enabled: bool = settings.SIREN_ENABLED
	mock_mode: bool = settings.SIREN_MOCK_MODE
	gpio_pin: int = settings.SIREN_GPIO_PIN
	cooldown_sec: float = settings.SIREN_COOLDOWN_SEC
	max_active_sec: float = settings.SIREN_MAX_ACTIVE_SEC


class SirenController:
	"""Trigger/stop siren with cooldown and runtime safety guards."""

	def __init__(self, config: Optional[SirenConfig] = None) -> None:
		"""Initialize controller.

		Args:
			config: Optional runtime configuration override.

		Returns:
			None.

		Failure Behavior:
			Never raises; GPIO setup failures are logged and controller degrades
			to no-op behavior for the current process.
		"""

		self.config = config or SirenConfig()
		self._last_trigger_at = 0.0
		self._active_until = 0.0
		self._is_active = False
		self._gpio = None
		self._gpio_ready = False

		if self.config.enabled and not self.config.mock_mode:
			self._setup_gpio()

	def trigger(self, event: HazardEvent, duration_sec: float | None = None) -> bool:
		"""Trigger siren for a CRITICAL event.

		Args:
			event: HazardEvent that caused the trigger attempt.
			duration_sec: Optional override for active duration.

		Returns:
			True if siren was triggered, otherwise False.

		Failure Behavior:
			Never raises. Cooldown conflicts or GPIO failures return False.
		"""

		if not self.config.enabled:
			return False

		now = time.time()
		self.tick(now)

		if now - self._last_trigger_at < self.config.cooldown_sec:
			logger.info(
				"siren suppressed by cooldown event_type=%s severity=%s camera_id=%s",
				event.event_type,
				event.severity.name,
				event.camera_id,
			)
			return False

		active_duration = float(duration_sec or self.config.max_active_sec)
		self._last_trigger_at = now
		self._active_until = now + max(0.1, active_duration)
		self._is_active = True

		if self.config.mock_mode:
			logger.warning(
				"siren mock trigger event_type=%s severity=%s camera_id=%s",
				event.event_type,
				event.severity.name,
				event.camera_id,
			)
			return True

		if not self._gpio_ready:
			logger.error("siren gpio not ready")
			self._is_active = False
			return False

		try:
			self._gpio.output(self.config.gpio_pin, self._gpio.HIGH)
			logger.warning(
				"siren gpio trigger event_type=%s severity=%s camera_id=%s pin=%s",
				event.event_type,
				event.severity.name,
				event.camera_id,
				self.config.gpio_pin,
			)
			return True
		except Exception as exc:
			logger.exception("siren gpio trigger failed: %s", exc)
			self._is_active = False
			return False

	def stop(self) -> bool:
		"""Stop currently active siren.

		Args:
			None.

		Returns:
			True when call succeeds (including idempotent no-op).

		Failure Behavior:
			Never raises. GPIO failures are logged and False is returned.
		"""

		if not self._is_active:
			return True

		self._is_active = False
		self._active_until = 0.0

		if self.config.mock_mode:
			logger.info("siren mock stop")
			return True

		if not self._gpio_ready:
			return False

		try:
			self._gpio.output(self.config.gpio_pin, self._gpio.LOW)
			logger.info("siren gpio stop pin=%s", self.config.gpio_pin)
			return True
		except Exception as exc:
			logger.exception("siren gpio stop failed: %s", exc)
			return False

	def tick(self, now: float | None = None) -> None:
		"""Enforce max active duration in a non-blocking way.

		Args:
			now: Optional timestamp override for deterministic tests.

		Returns:
			None.

		Failure Behavior:
			Never raises; internal stop errors are handled by ``stop``.
		"""

		if not self._is_active:
			return
		t = now if now is not None else time.time()
		if t >= self._active_until:
			self.stop()

	def _setup_gpio(self) -> None:
		# Set up GPIO backend lazily for deployment targets.

		try:
			try:
				import Jetson.GPIO as gpio  # type: ignore
			except Exception:
				import RPi.GPIO as gpio  # type: ignore

			self._gpio = gpio
			gpio.setwarnings(False)
			gpio.setmode(gpio.BCM)
			gpio.setup(self.config.gpio_pin, gpio.OUT, initial=gpio.LOW)
			self._gpio_ready = True
		except Exception as exc:
			self._gpio_ready = False
			logger.exception("siren gpio setup failed: %s", exc)
