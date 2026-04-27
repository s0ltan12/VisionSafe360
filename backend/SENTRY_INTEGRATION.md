# Sentry Integration Guide

Sentry is an error tracking and performance monitoring platform integrated into VisionSafe backend to catch unhandled exceptions, track performance, and provide debugging context.

## Quick Setup

### 1. Get a Sentry Account and DSN

1. Create a free account at https://sentry.io/
2. Create a new project (select FastAPI/Python)
3. Copy your DSN (Data Source Name) - looks like: `https://key@sentry.io/project_id`

### 2. Set Environment Variable

Add to your `.env` file:

```bash
SENTRY_DSN=https://key@sentry.io/project_id
```

Or for deployment (docker-compose, k8s, etc.):

```bash
export SENTRY_DSN=https://key@sentry.io/project_id
```

### 3. Start the Backend

```bash
cd backend
python -m uvicorn app.main:app --reload
```

Sentry will automatically initialize on startup. Check logs:

```
✓ Sentry initialized (environment=development)
```

## What Gets Tracked

### Automatic Capture

✅ **Unhandled Exceptions**
- Any exception that reaches FastAPI's exception handler
- CUDA/GPU errors
- Database connection failures
- Redis errors

✅ **HTTP Errors**
- 5xx server errors (automatically sent)
- Validation errors are filtered (4xx client errors not sent by default)

✅ **Performance Monitoring**
- Request duration
- Database query timing (via SQLAlchemy integration)
- Redis command timing (via Redis integration)

✅ **Logging Integration**
- ERROR and CRITICAL level logs automatically captured
- Structured JSON logs preserved in Sentry

### Request Context (Automatic)

Each error includes:
- **request_id**: Unique trace ID (from X-Request-ID header)
- **HTTP method, path, status code**
- **Query parameters and headers** (sensitive data filtered)
- **User context** (if set manually)

## Manual Error Capture

### Capture Exceptions

```python
from app.utils.sentry_integration import capture_exception

try:
    risky_operation()
except Exception as exc:
    event_id = capture_exception(exc, operation="sync_camera_config")
    logger.error("Operation failed, reported to Sentry: %s", event_id)
```

### Capture Messages

```python
from app.utils.sentry_integration import capture_message

capture_message("High alert rate detected", level="warning", source="proximity_analyzer")
```

## Enriching Context

### Set User Information

```python
from app.utils.sentry_integration import set_sentry_context

# When user logs in
set_sentry_context(user_id=user.id)

# Later in request
set_sentry_context(user_id=user.id, request_id=request.state.request_id)
```

### Add Custom Context

```python
set_sentry_context(
    user_id="user_123",
    request_id="req_abc",
    camera_id="cam_01",
    incident_type="fall_detection",
    model_version="v2.1",
)
```

Context automatically includes in Sentry issue details.

## Example: Incident Route with Sentry

```python
from fastapi import APIRouter, Depends, Request
from app.utils.sentry_integration import set_sentry_context, capture_exception

router = APIRouter()

@router.post("/api/incidents")
async def create_incident(
    request: Request,
    incident: IncidentSchema,
    current_user: User = Depends(require_roles("admin", "operator")),
):
    # Enrich Sentry with context
    set_sentry_context(
        user_id=current_user.id,
        request_id=getattr(request.state, "request_id", None),
        incident_type=incident.classification,
    )
    
    try:
        # Create incident logic
        result = await incident_service.create(incident)
        return result
    except Exception as exc:
        # Manual capture with additional context
        capture_exception(exc, operation="create_incident", incident_zone=incident.zone)
        raise
```

## Configuration Reference

### Environment Variables

```bash
# Required for Sentry
SENTRY_DSN=https://key@sentry.io/project_id

# Optional (all have defaults)
SENTRY_ENVIRONMENT=production       # or: development, staging
SENTRY_TRACES_SAMPLE_RATE=0.1       # 10% of transactions
SENTRY_PROFILES_SAMPLE_RATE=0.1     # 10% of profiles
```

### What's Filtered

**Sensitive data automatically excluded:**
- Authorization headers
- API keys
- Passwords
- Cookies
- Personal information in request bodies

**HTTP Status Codes (not sent to Sentry):**
- 4xx client errors (validation, auth failures) - logged but not sent
- 400, 401, 403, 404, 409, 422 etc. filtered

## Viewing Issues

1. Go to https://sentry.io/ and log in
2. Select your VisionSafe project
3. Issues tab shows all captured errors
4. Click an issue to see:
   - Full stack trace
   - Request context (headers, path, method)
   - User information
   - Custom tags and context
   - Breadcrumb trail (recent log events)
   - Performance metrics

### Filtering Issues

On the Issues page:
- Filter by environment: `environment:production`
- Filter by user: `user.id:user_123`
- Filter by request: `request_id:req_abc`
- Filter by tag: `camera_id:cam_01`

## Alerts and Notifications

### Set Up Alerts

1. Go to Sentry → Project Settings → Alerts
2. Create alert rules:
   - "When a new issue is created"
   - "When event frequency exceeds 10 per hour"
   - "When an error in production occurs"

3. Configure notifications:
   - Email
   - Slack
   - PagerDuty
   - Webhook

### Example Alert

```
Alert: New Issue in Production
Rule: Environment is 'production' AND is_regression()
Action: Send email + post to Slack #incidents channel
```

## Performance Monitoring

### Traces

Sentry captures distributed traces of requests:
- Request duration
- Database query time
- Redis operations
- API calls

View in: Transactions tab → Click request to see timeline

### Profiles

CPU profiling (10% sample rate):
- Flame graphs showing CPU usage
- Identify slow functions
- Memory allocation

## Testing Integration

### Verify Sentry is Connected

```python
from app.utils.sentry_integration import sentry_enabled

if sentry_enabled():
    print("✓ Sentry is active")
else:
    print("✗ Sentry is disabled (check SENTRY_DSN)")
```

### Send Test Error

```bash
# In Python shell
from app.utils.sentry_integration import capture_message
capture_message("Test: VisionSafe Sentry integration working", level="info")

# Check Sentry dashboard - should appear within 30 seconds
```

## Docker Deployment

### docker-compose

```yaml
services:
  backend:
    environment:
      - SENTRY_DSN=https://key@sentry.io/project_id
    # ... rest of config
```

### Kubernetes

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sentry-config
data:
  sentry-dsn: aHR0cHM6Ly9rZXlAc2VudHJ5LmlvL3Byb2plY3RfaWQ=  # base64

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: visionsafe-backend
spec:
  template:
    spec:
      containers:
      - name: backend
        env:
        - name: SENTRY_DSN
          valueFrom:
            secretKeyRef:
              name: sentry-config
              key: sentry-dsn
```

## Troubleshooting

### Sentry Not Capturing Errors

**Check 1**: Verify Sentry is initialized
```bash
# In logs, should see:
# ✓ Sentry initialized (environment=development)
```

**Check 2**: Verify DSN is valid
```python
from app.utils.sentry_integration import sentry_enabled
print(sentry_enabled())  # Should be True
```

**Check 3**: Verify error is not filtered
- 4xx errors are filtered (by design)
- Use `capture_exception()` to force send
- Check Sentry dashboard for rejection reasons

### Too Many Events

**Problem**: Sentry hitting quota or too noisy

**Solution**:
1. Reduce `traces_sample_rate` (default 0.1 = 10%)
2. Adjust `before_send` in `sentry_integration.py` to filter more
3. Set up Release tracking to see only new errors
4. Disable in development:

```bash
# Don't set SENTRY_DSN in development .env
```

## Best Practices

1. ✅ **Always set request_id** - helps trace issues across services
2. ✅ **Set user context** - know which user hit the error
3. ✅ **Use custom tags** - add camera_id, incident_type, etc.
4. ✅ **Avoid sensitive data** - passwords, tokens are auto-filtered
5. ✅ **Use levels appropriately** - info, warning, error, critical
6. ✅ **Link Sentry issues to incidents** - use Sentry releases feature
7. ✅ **Test in staging** - verify alerts before production
8. ✅ **Set up Slack/email alerts** - get notified of production errors

## References

- **Sentry Documentation**: https://docs.sentry.io/
- **Sentry FastAPI Integration**: https://docs.sentry.io/platforms/python/integrations/fastapi/
- **Performance Monitoring**: https://docs.sentry.io/product/performance/
- **Release Tracking**: https://docs.sentry.io/product/releases/

## Support

For issues with Sentry integration:
1. Check logs: `grep -i sentry backend.log`
2. Verify DSN in environment: `echo $SENTRY_DSN`
3. Consult Sentry docs: https://docs.sentry.io/
4. Contact Sentry support: https://sentry.io/support/
