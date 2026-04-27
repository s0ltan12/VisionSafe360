# Sentry Integration Snippets

Quick copy-paste examples for integrating Sentry into your routes and services.

## 1. Basic Exception Handling

```python
from app.utils.sentry_integration import capture_exception

@app.post("/api/incidents")
async def create_incident(incident: IncidentSchema):
    try:
        result = await service.create(incident)
        return result
    except Exception as exc:
        capture_exception(exc, operation="create_incident")
        raise
```

## 2. With User and Request Context

```python
from app.utils.sentry_integration import set_sentry_context, capture_exception
from fastapi import Request

@app.post("/api/incidents")
async def create_incident(
    request: Request,
    incident: IncidentSchema,
    current_user: User = Depends(get_current_user),
):
    # Set context at start of request
    set_sentry_context(
        user_id=current_user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    
    try:
        result = await service.create(incident)
        return result
    except Exception as exc:
        capture_exception(exc, incident_zone=incident.zone)
        raise
```

## 3. Camera/Incident Context

```python
from app.utils.sentry_integration import set_sentry_context, capture_exception

async def process_frame(frame, camera_id: str):
    set_sentry_context(camera_id=camera_id)
    
    try:
        detections = model.detect(frame)
        return detections
    except Exception as exc:
        capture_exception(exc, frame_shape=frame.shape)
        raise
```

## 4. Backend/Redis Error Handling

```python
from app.utils.sentry_integration import capture_exception

async def sync_incidents_to_backend():
    try:
        incidents = await fetch_offline_queue()
        await backend.post_incidents(incidents)
    except Exception as exc:
        # Manual capture but don't break - queue will retry
        capture_exception(exc, operation="backend_sync", queue_size=len(incidents))
        logger.error("Backend sync failed, will retry later")
```

## 5. Alert Manager Integration

```python
from app.utils.sentry_integration import set_sentry_context, capture_message

async def process_hazard_event(event: HazardEvent, camera_id: str):
    set_sentry_context(
        camera_id=camera_id,
        incident_type=event.event_type,
        severity=event.severity.name,
    )
    
    if event.severity == Severity.CRITICAL:
        capture_message(
            f"Critical hazard: {event.event_type}",
            level="error",
            track_id=event.track_id,
        )
```

## 6. In Services

```python
# app/services/incident_service.py
from app.utils.sentry_integration import capture_exception

class IncidentService:
    async def create(self, incident: IncidentSchema):
        try:
            result = await self.db.add(incident)
            return result
        except IntegrityError as exc:
            # Duplicate incident
            capture_exception(exc, incident_zone=incident.zone, duplicate=True)
            raise
        except Exception as exc:
            capture_exception(exc, operation="create_incident")
            raise
```

## 7. In WebSocket Handler

```python
from app.utils.sentry_integration import set_sentry_context, capture_exception

@router.websocket("/ws/incidents")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    request_id = websocket.headers.get("x-request-id")
    
    set_sentry_context(request_id=request_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Process
    except Exception as exc:
        capture_exception(exc, channel="incidents")
        raise
    finally:
        await websocket.close()
```

## 8. Middleware Context Enrichment

Already implemented in `app/main.py`:

```python
# Automatically adds request_id to every error in the request
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    # ... setup ...
    if sentry_enabled():
        set_sentry_context(request_id=request_id)
    # ... handle request ...
```

## 9. Check if Sentry is Enabled

```python
from app.utils.sentry_integration import sentry_enabled, capture_exception

if sentry_enabled():
    capture_exception(exc)
else:
    logger.error("Sentry not configured, logging to file only", exc_info=True)
```

## 10. Batch Operations with Sentry

```python
from app.utils.sentry_integration import set_sentry_context, capture_message

async def process_batch_incidents(incidents: list[Incident]):
    for idx, incident in enumerate(incidents):
        try:
            set_sentry_context(batch_index=idx, total=len(incidents))
            await process_single(incident)
        except Exception as exc:
            capture_exception(exc, incident_id=incident.id, batch_index=idx)
            continue  # Don't break batch processing
    
    capture_message(f"Batch complete: {len(incidents)} processed", level="info")
```

## Configuration in Your Code

If you need to override Sentry settings:

```python
# In app/config/settings.py or similar
import os

SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "development")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))

# Then in init call:
from app.utils.sentry_integration import init_sentry
init_sentry(dsn=SENTRY_DSN, environment=SENTRY_ENVIRONMENT)
```

## Common Patterns

### Error Category Tagging

```python
capture_exception(
    exc,
    category="database",
    operation="query_incidents",
    table="incidents",
)

# Later filter in Sentry: tag:category:database
```

### Success Tracking

```python
capture_message(
    f"Incident delivery successful",
    level="info",
    incident_count=len(incidents),
    backend="https://backend.visionsafe.local",
)
```

### Performance Alerts

```python
import time

start = time.time()
try:
    result = await expensive_operation()
    duration = time.time() - start
    if duration > 1.0:  # More than 1 second
        capture_message(
            f"Slow operation: {duration:.2f}s",
            level="warning",
            operation="expensive_operation",
            duration_ms=int(duration * 1000),
        )
except Exception as exc:
    capture_exception(exc, operation="expensive_operation")
```

## Testing Locally

```bash
# Set a test DSN (non-real)
export SENTRY_DSN="https://test@sentry.io/123"

# Trigger test error
curl -X POST http://localhost:8000/api/test-error

# Check logs
grep -i "sentry" backend.log
```

## Disabling Sentry Locally

```bash
# Don't set SENTRY_DSN in .env
# Sentry will be disabled automatically
```

## References

- Full docs: [SENTRY_INTEGRATION.md](SENTRY_INTEGRATION.md)
- [Sentry Python SDK](https://github.com/getsentry/sentry-python)
- [Sentry FastAPI Integration](https://docs.sentry.io/platforms/python/integrations/fastapi/)
