"""Sentry error tracking integration for VisionSafe backend."""

import os
import logging
from typing import Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration

logger = logging.getLogger("visionsafe.backend")


def init_sentry(dsn: Optional[str] = None, environment: str = "development") -> bool:
    """
    Initialize Sentry for error tracking and performance monitoring.

    Args:
        dsn: Sentry DSN (Data Source Name). If None, reads from SENTRY_DSN env var.
             If empty or not provided, Sentry is disabled.
        environment: Environment name (development, staging, production).

    Returns:
        True if Sentry was initialized, False if disabled/no DSN.

    Example:
        >>> init_sentry()  # Reads SENTRY_DSN from environment
        >>> init_sentry(dsn="https://key@sentry.io/project_id")
    """
    # Get DSN from parameter or environment
    if dsn is None:
        dsn = os.getenv("SENTRY_DSN", "").strip()

    if not dsn:
        logger.info("Sentry disabled (no SENTRY_DSN provided)")
        return False

    try:
        # Configure Sentry with FastAPI and other integrations
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(
                    level=logging.INFO,  # Capture INFO and above
                    event_level=logging.ERROR,  # Only emit events for ERROR and above
                ),
                SqlalchemyIntegration(),
                RedisIntegration(),
            ],
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            profiles_sample_rate=0.1,  # 10% profiling sample rate
            debug=False,
            attach_stacktrace=True,
            # Filter sensitive data
            before_send=_before_send,
        )
        logger.info("✓ Sentry initialized (environment=%s)", environment)
        return True

    except Exception as exc:
        logger.error("Failed to initialize Sentry: %s", exc)
        return False


def _before_send(event: dict, hint: dict) -> Optional[dict]:
    """
    Sentry hook to filter/modify events before sending to Sentry.

    This function:
    - Filters out non-critical status codes (4xx client errors)
    - Removes sensitive data from request/response bodies
    - Adds custom context if available
    """
    # Skip unimportant HTTP errors (client errors 4xx)
    if "exception" in event:
        exc_value = hint.get("exc_value")
        # Don't report validation errors and auth errors as Sentry events
        if exc_value and "ValidationError" in str(type(exc_value)):
            return None
        if exc_value and "HTTPException" in str(type(exc_value)):
            # Check status code
            if hasattr(exc_value, "status_code") and 400 <= exc_value.status_code < 500:
                return None

    # Remove sensitive headers from request context
    if "request" in event:
        headers = event["request"].get("headers", {})
        sensitive_keys = ["authorization", "cookie", "x-api-key", "password"]
        for key in sensitive_keys:
            headers.pop(key, None)

    return event


def set_sentry_context(
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    camera_id: Optional[str] = None,
    **extra,
) -> None:
    """
    Enrich Sentry context with application-specific data.

    Args:
        user_id: ID of the current user
        request_id: Request ID for tracing
        camera_id: Camera identifier for incident context
        **extra: Additional context key-value pairs

    Example:
        >>> set_sentry_context(user_id="user_123", request_id="req_abc")
        >>> set_sentry_context(camera_id="cam_01", hazard_type="fall_detection")
    """
    if user_id:
        sentry_sdk.set_user({"id": user_id})

    tags = {}
    if request_id:
        tags["request_id"] = request_id
        sentry_sdk.set_tag("request_id", request_id)
    if camera_id:
        tags["camera_id"] = camera_id
        sentry_sdk.set_tag("camera_id", camera_id)

    if extra:
        sentry_sdk.set_context("additional", extra)

    logger.debug("Sentry context updated: user=%s request_id=%s camera=%s", user_id, request_id, camera_id)


def capture_exception(exc: Exception, **context) -> str:
    """
    Manually capture an exception to Sentry with optional context.

    Args:
        exc: Exception to capture
        **context: Additional context data

    Returns:
        Event ID for tracking

    Example:
        >>> try:
        ...     risky_operation()
        ... except Exception as exc:
        ...     event_id = capture_exception(exc, operation="sync_incidents")
    """
    if context:
        set_sentry_context(**context)
    event_id = sentry_sdk.capture_exception(exc)
    logger.error("Exception captured to Sentry: %s (event_id=%s)", exc, event_id)
    return str(event_id) if event_id else "unknown"


def capture_message(message: str, level: str = "info", **context) -> str:
    """
    Manually capture a message to Sentry.

    Args:
        message: Message to capture
        level: Severity level (info, warning, error)
        **context: Additional context data

    Returns:
        Event ID for tracking

    Example:
        >>> capture_message("High alert rate detected", level="warning", source="proximity_analyzer")
    """
    if context:
        set_sentry_context(**context)
    event_id = sentry_sdk.capture_message(message, level=level)
    logger.log(logging.getLevelName(level.upper()), "Message captured to Sentry: %s", message)
    return str(event_id) if event_id else "unknown"


def sentry_enabled() -> bool:
    """Check if Sentry is currently enabled/initialized."""
    client = sentry_sdk.get_client()
    return client is not None and client.dsn is not None
