# 1. Executive Summary
VisionSafe360 backend is the central control plane and system of record for industrial safety intelligence generated at edge nodes.

## Current Repository Status

This specification describes the target enterprise backend and now maps to the active implementation path in `backend/app`.

For the current shipped flow:
- Frontend: `dashboard/`
- Active backend: `backend/app` (entrypoint `backend/main.py`)
- Central database: one PostgreSQL instance for the dashboard backend
- Edge offline queue: local SQLite per edge node for buffered delivery only
- Deprecated prototype storage: `dashboard/db.ts` localStorage helper, no longer part of the active flow

The enterprise backend path is now the active path and should be the only backend source of truth.

It ingests incident and telemetry data from edge nodes (Jetson/laptop), stores structured records in PostgreSQL, stores evidence media in S3-compatible object storage (MinIO/S3), and exposes data to web dashboard and future mobile services through REST and WebSocket APIs.

Core responsibilities in v1:
- AuthN/AuthZ with RBAC across `admin`, `supervisor`, `viewer`, `edge_node` roles.
- Multi-tenant data isolation using strict `organization_id` scoping.
- Incident lifecycle management (new, acknowledged, resolved, escalated).
- Edge health/telemetry ingestion and operational visibility.
- Configuration distribution to edge nodes (profiles, thresholds, module toggles, schedules).
- Calibration and zone management per camera.
- Immutable audit logging for critical actions.

Integration with edge pipeline:
- Edge emits `HazardEvent` records and telemetry batches.
- Edge uploads snapshots/clips metadata (and optionally object upload via signed URL flow).
- Edge performs privacy preprocessing (face blur) before upload.
- Backend guarantees idempotent ingestion and reliable storage.

# 2. Non-Goals
The following are explicitly out of scope for backend v1:
- Running ML inference in backend.
- Real-time video transcoding/stream relay in backend.
- Full workflow engine (SLA queues, assignment boards, escalation automations beyond basic update records).
- Advanced analytics (heatmaps, predictive risk scoring, anomaly detection dashboards).
- Native push notification service implementation (FCM/SMS integration deferred to v2).
- Cross-region active-active deployment and disaster failover automation.
- Automated model training/registry pipeline.

# 3. System Architecture
## 3.1 End-to-End Flow
`Cameras -> Edge AI Node -> Backend API -> PostgreSQL/Object Storage -> Dashboard REST/WebSocket -> Admin/Analytics`

Detailed path:
1. Camera streams are processed on edge node by VisionSafe pipeline.
2. Edge detects hazards and emits `HazardEvent` plus periodic telemetry summaries.
3. Edge sends HTTPS requests to backend ingestion endpoints.
4. Backend validates schema, authenticates edge identity, applies idempotency checks, persists:
- relational data in PostgreSQL
- media metadata in PostgreSQL
- snapshots/clips in object storage
5. Backend pushes live incident/health updates over WebSocket channels.
6. Dashboard consumes REST (history, filters, configs) and WebSocket (real-time cards/alerts).
7. Admin users manage org/site/camera/zones/configs/calibration via REST.

## 3.2 Logical Components
- `api-gateway` (FastAPI app): REST + WebSocket + auth + validation.
- `ingestion-service` (module within backend app): incident/telemetry ingest, dedupe, idempotency.
- `config-service`: camera thresholds/profile/schedule versioning and edge pull contract.
- `incident-service`: lifecycle updates, evidence links, query filters.
- `telemetry-service`: rollup and health summaries.
- `storage-service`: signed URL generation and object key governance.
- `audit-service`: immutable action records.

## 3.3 Local-First and Offline Behavior
Edge nodes must keep safety detection active when WAN/LAN connection to backend is unavailable.

Required edge behavior:
- Continue local detection and local alerting offline.
- Persist outbound payloads to local store-and-forward queue (`SQLite` or append-only local files).
- Retry delivery with exponential backoff + jitter.
- Preserve original `event_timestamp` generated at edge.

Required backend behavior:
- Accept delayed events and maintain original event time.
- Record `ingested_at` separately from `event_timestamp`.
- Support idempotent inserts using `idempotency_key`.
- Handle out-of-order arrival.

Retry/backoff standard (edge):
- Initial retry: 2 seconds.
- Backoff: `min(2^attempt, 300)` seconds.
- Jitter: +/-20% randomization.
- Max local retention before dead-letter: 7 days.

# 4. Tech Stack
## 4.1 Recommended v1 Stack
- FastAPI
- PostgreSQL 15+
- Redis (optional but recommended)
- MinIO (dev/on-prem) or S3-compatible object store (prod)
- Alembic
- Docker Compose

## 4.2 Rationale
- FastAPI:
- Strong typing with Pydantic for strict edge payload validation.
- Native async support for high-concurrency ingestion and WebSocket.
- Automatic OpenAPI docs for rapid integration.

- PostgreSQL:
- Reliable ACID transactional integrity for incidents/audit.
- Excellent indexing support for time-series + filtered queries.
- JSONB for flexible metadata while keeping relational model strict.

- Redis:
- Short-lived cache for hot dashboards.
- Optional pub/sub fanout for multi-worker WebSocket event broadcasting.
- Optional queue support for background tasks.

- MinIO/S3:
- Durable object storage for snapshots/clips with presigned access.
- Compatible with industrial on-prem deployments.

- Alembic:
- Explicit schema migrations and reproducible rollout.

- Docker Compose:
- Practical single-host deployment for factory/on-prem pilots.
- Clear path to Kubernetes later.

## 4.3 Database Count for the Current Project

The current project should be understood as having one shared production database and one local edge-side buffer:

1. Central PostgreSQL database for the dashboard backend.
2. Local SQLite database on each edge device for offline incident queueing.

There is not a second shared application database unless `backend/app` is later implemented as a separate backend branch.

# 5. Data Model & Database Schema
## 5.1 Naming and Type Conventions
- Table names: plural snake_case.
- Primary key type: `uuid` (`gen_random_uuid()` default).
- Time fields: `timestamptz` in UTC.
- JSON payload extension: `jsonb`.
- Soft delete fields: `deleted_at timestamptz null` where needed.
- Severity enum: `low`, `medium`, `high`, `critical`.
- Incident status enum: `open`, `acknowledged`, `resolved`.

## 5.2 Tables
### organizations
Purpose: Tenant root; all domain records are scoped to one organization.

Fields:
- `id uuid pk`
- `name varchar(200) not null`
- `slug varchar(100) unique not null`
- `status varchar(20) not null default 'active'`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- none

Indexes:
- `ux_organizations_slug (slug unique)`
- `ix_organizations_status (status)`

### sites
Purpose: Physical industrial facility/factory under an organization.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `name varchar(200) not null`
- `code varchar(64) not null`
- `timezone varchar(64) not null`
- `address text null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`

Indexes:
- `ux_sites_org_code (organization_id, code unique)`
- `ix_sites_org (organization_id)`

### users
Purpose: Human users for dashboard/admin access.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `email varchar(320) not null`
- `password_hash varchar(255) not null`
- `full_name varchar(200) not null`
- `role varchar(20) not null` (`admin|supervisor|viewer`)
- `is_active boolean not null default true`
- `last_login_at timestamptz null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`

Indexes:
- `ux_users_org_email (organization_id, email unique)`
- `ix_users_org_role (organization_id, role)`

### edge_nodes
Purpose: Registered edge compute devices posting incidents/telemetry.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `site_id uuid not null`
- `node_code varchar(64) not null` (human-readable unique code per org)
- `display_name varchar(200) not null`
- `auth_key_hash varchar(255) not null` (for API key auth)
- `status varchar(20) not null default 'active'` (`active|disabled|maintenance`)
- `last_seen_at timestamptz null`
- `last_ip inet null`
- `agent_version varchar(64) null`
- `api_version varchar(16) not null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `site_id -> sites(id)`

Indexes:
- `ux_edge_nodes_org_code (organization_id, node_code unique)`
- `ix_edge_nodes_site (site_id)`
- `ix_edge_nodes_last_seen (last_seen_at desc)`

### cameras
Purpose: Camera inventory and runtime configuration.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `site_id uuid not null`
- `edge_node_id uuid not null`
- `camera_code varchar(64) not null`
- `name varchar(200) not null`
- `rtsp_url text not null`
- `is_enabled boolean not null default true`
- `profile varchar(32) not null` (`fall_only|proximity_only|ppe_only|full_suite`)
- `thresholds jsonb not null` (typed contract enforced at API)
- `schedule jsonb not null` (daily windows)
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `site_id -> sites(id)`
- `edge_node_id -> edge_nodes(id)`

Indexes:
- `ux_cameras_org_code (organization_id, camera_code unique)`
- `ix_cameras_site (site_id)`
- `ix_cameras_edge (edge_node_id)`
- `ix_cameras_enabled (is_enabled)`

### camera_calibrations
Purpose: Persist homography and measurement context for meter-level distance calculations.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `camera_id uuid not null`
- `version int not null`
- `homography_matrix jsonb not null` (3x3)
- `unit varchar(16) not null default 'meter'`
- `reference_points jsonb not null`
- `calibrated_by_user_id uuid null`
- `valid_from timestamptz not null`
- `valid_to timestamptz null`
- `status varchar(20) not null default 'active'` (`active|superseded|invalid`)
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `camera_id -> cameras(id)`
- `calibrated_by_user_id -> users(id)`

Indexes:
- `ix_calibrations_camera_status (camera_id, status)`
- `ux_calibrations_camera_version (camera_id, version unique)`
- `ix_calibrations_valid_from (valid_from desc)`

### zones
Purpose: Camera-scoped polygons for restricted/allowed areas and lane definitions.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `camera_id uuid not null`
- `name varchar(120) not null`
- `zone_type varchar(32) not null` (`restricted_area|forklift_lane|walkway|custom`)
- `polygon_points jsonb not null` (array of `{x,y}` normalized 0..1)
- `is_active boolean not null default true`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `camera_id -> cameras(id)`

Indexes:
- `ix_zones_camera_type (camera_id, zone_type)`
- `ix_zones_org_active (organization_id, is_active)`

### incidents
Purpose: Canonical hazard event records received from edge.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `site_id uuid not null`
- `edge_node_id uuid not null`
- `camera_id uuid not null`
- `external_event_id varchar(100) not null` (edge-generated stable ID)
- `idempotency_key varchar(120) not null`
- `event_timestamp timestamptz not null`
- `ingested_at timestamptz not null default now()`
- `hazard_type varchar(64) not null`
- `severity varchar(16) not null`
- `status varchar(20) not null default 'open'`
- `track_id varchar(64) null`
- `bbox jsonb not null` (`x1,y1,x2,y2` normalized)
- `metadata jsonb not null default '{}'::jsonb`
- `acknowledged_by_user_id uuid null`
- `acknowledged_at timestamptz null`
- `resolved_by_user_id uuid null`
- `resolved_at timestamptz null`
- `resolution_note text null`
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `site_id -> sites(id)`
- `edge_node_id -> edge_nodes(id)`
- `camera_id -> cameras(id)`
- `acknowledged_by_user_id -> users(id)`
- `resolved_by_user_id -> users(id)`

Indexes:
- `ux_incidents_org_idem (organization_id, idempotency_key unique)`
- `ux_incidents_org_external (organization_id, external_event_id unique)`
- `ix_incidents_time (event_timestamp desc)`
- `ix_incidents_org_time (organization_id, event_timestamp desc)`
- `ix_incidents_camera_time (camera_id, event_timestamp desc)`
- `ix_incidents_site_time (site_id, event_timestamp desc)`
- `ix_incidents_type_severity (hazard_type, severity)`
- `ix_incidents_status (status)`

### incident_updates
Purpose: Append-only timeline of incident lifecycle changes and operator notes.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `incident_id uuid not null`
- `update_type varchar(32) not null` (`created|severity_changed|acknowledged|resolved|reopened|note`)
- `old_value jsonb null`
- `new_value jsonb null`
- `note text null`
- `updated_by_user_id uuid null` (null for edge/system)
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `incident_id -> incidents(id)`
- `updated_by_user_id -> users(id)`

Indexes:
- `ix_incident_updates_incident_time (incident_id, created_at asc)`
- `ix_incident_updates_org_time (organization_id, created_at desc)`

### incident_evidence
Purpose: Media references tied to incidents.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `incident_id uuid not null`
- `evidence_type varchar(16) not null` (`snapshot|clip`)
- `object_key varchar(500) not null`
- `content_type varchar(100) not null`
- `size_bytes bigint not null`
- `sha256 varchar(64) null`
- `captured_at timestamptz not null`
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `incident_id -> incidents(id)`

Indexes:
- `ix_incident_evidence_incident (incident_id)`
- `ix_incident_evidence_org_time (organization_id, created_at desc)`

### telemetry_samples
Purpose: Aggregated telemetry samples (not every frame) for health and analytics.

Sampling policy:
- Edge aggregates frame metrics into 10-second windows.
- Edge sends batched samples every 30 seconds.
- Backend stores one row per camera per 10-second window.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `site_id uuid not null`
- `edge_node_id uuid not null`
- `camera_id uuid not null`
- `window_start timestamptz not null`
- `window_end timestamptz not null`
- `fps_avg numeric(6,2) not null`
- `latency_ms_p50 numeric(8,2) not null`
- `latency_ms_p95 numeric(8,2) not null`
- `vram_mb_avg numeric(8,2) null`
- `n_detections int not null`
- `n_tracked int not null`
- `n_hazards int not null`
- `hazard_types jsonb not null` (map hazard_type -> count)
- `pose_ms_avg numeric(8,2) null`
- `track_coverage numeric(5,2) null`
- `calibrated boolean not null`
- `raw jsonb null` (extra forward-compatible fields)
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `site_id -> sites(id)`
- `edge_node_id -> edge_nodes(id)`
- `camera_id -> cameras(id)`

Indexes:
- `ux_telemetry_cam_window (camera_id, window_start unique)`
- `ix_telemetry_org_time (organization_id, window_start desc)`
- `ix_telemetry_site_time (site_id, window_start desc)`
- `ix_telemetry_edge_time (edge_node_id, window_start desc)`

### model_versions
Purpose: Catalog model artifacts and profile compatibility.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `model_name varchar(100) not null`
- `model_type varchar(40) not null` (`ppe|fall|proximity|pose|composite`)
- `version varchar(64) not null`
- `weights_uri text not null`
- `checksum_sha256 varchar(64) not null`
- `supported_profiles jsonb not null`
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`

Indexes:
- `ux_model_versions_org_name_ver (organization_id, model_name, version unique)`
- `ix_model_versions_type (model_type)`

### model_deployments
Purpose: Track what profile/model bundle is deployed to each edge node/camera.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `edge_node_id uuid not null`
- `camera_id uuid null` (null means node-wide deployment)
- `profile varchar(32) not null`
- `deployment_config jsonb not null`
- `status varchar(20) not null` (`pending|active|failed|rolled_back`)
- `deployed_by_user_id uuid null`
- `deployed_at timestamptz null`
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`
- `edge_node_id -> edge_nodes(id)`
- `camera_id -> cameras(id)`
- `deployed_by_user_id -> users(id)`

Indexes:
- `ix_model_deployments_edge_time (edge_node_id, created_at desc)`
- `ix_model_deployments_camera_time (camera_id, created_at desc)`
- `ix_model_deployments_status (status)`

### audit_logs
Purpose: Immutable compliance record for security and critical system actions.

Fields:
- `id uuid pk`
- `organization_id uuid not null`
- `actor_type varchar(20) not null` (`user|edge_node|system`)
- `actor_id uuid null`
- `action varchar(120) not null`
- `resource_type varchar(60) not null`
- `resource_id uuid null`
- `request_id varchar(80) null`
- `ip inet null`
- `user_agent text null`
- `before jsonb null`
- `after jsonb null`
- `created_at timestamptz not null default now()`

Primary key:
- `id`

Foreign keys:
- `organization_id -> organizations(id)`

Indexes:
- `ix_audit_org_time (organization_id, created_at desc)`
- `ix_audit_action_time (action, created_at desc)`
- `ix_audit_resource (resource_type, resource_id)`

# 6. API Design (REST)
Base path: `/api/v1`

Auth headers:
- User JWT: `Authorization: Bearer <access_token>`
- Edge API key: `X-Edge-Key: <plain_key>` and `X-Edge-Node-Code: <node_code>`

Standard error format:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "camera_id is required",
    "details": [{"field": "camera_id", "issue": "missing"}],
    "request_id": "req_01HZY..."
  }
}
```

Error codes:
- `400` validation/format
- `401` unauthenticated
- `403` unauthorized
- `404` not found
- `409` conflict/idempotency violation
- `422` semantic validation
- `429` rate limited
- `500` internal

## 6.A Auth
### POST /auth/login
Auth: none

Request:
```json
{
  "email": "admin@factory-a.com",
  "password": "StrongPassword123!"
}
```

Response 200:
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "rft_01J...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "9b2d4f6a-3f0e-4e7e-b0eb-1f006f26f8d3",
    "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
    "email": "admin@factory-a.com",
    "full_name": "Factory Admin",
    "role": "admin"
  }
}
```

### POST /auth/refresh
Auth: refresh token in body

Request:
```json
{
  "refresh_token": "rft_01J..."
}
```

Response 200:
```json
{
  "access_token": "eyJhbGci...new",
  "refresh_token": "rft_01J...rotated",
  "token_type": "bearer",
  "expires_in": 900
}
```

Refresh strategy:
- Access token TTL: 15 minutes.
- Refresh token TTL: 30 days.
- Refresh token rotation on each call.
- Old refresh token immediately revoked.

### POST /auth/logout
Auth: user JWT

Request:
```json
{
  "refresh_token": "rft_01J..."
}
```

Response 204: empty body

Roles and access:
- `admin`: full CRUD and user/org config.
- `supervisor`: incident operations + camera/site reads + limited config.
- `viewer`: read-only.
- `edge_node`: ingest endpoints + config pull + heartbeat only.

## 6.B Organizations / Sites / Cameras
### POST /organizations
Auth: admin

Request:
```json
{
  "name": "Acme Manufacturing",
  "slug": "acme-mfg"
}
```

Response 201:
```json
{
  "id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "name": "Acme Manufacturing",
  "slug": "acme-mfg",
  "status": "active",
  "created_at": "2026-03-14T10:00:00Z"
}
```

### GET /organizations
Auth: admin

Response 200:
```json
{
  "items": [
    {
      "id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
      "name": "Acme Manufacturing",
      "slug": "acme-mfg",
      "status": "active"
    }
  ],
  "total": 1
}
```

### GET /organizations/{organization_id}
Auth: admin/supervisor/viewer (same org)

Response 200:
```json
{
  "id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "name": "Acme Manufacturing",
  "slug": "acme-mfg",
  "status": "active"
}
```

### PATCH /organizations/{organization_id}
Auth: admin

Request:
```json
{
  "name": "Acme Manufacturing Group",
  "status": "active"
}
```

### DELETE /organizations/{organization_id}
Auth: admin

Response 204: empty body

Response 200:
```json
{
  "id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "name": "Acme Manufacturing Group",
  "slug": "acme-mfg",
  "status": "active"
}
```

### POST /sites
Auth: admin

Request:
```json
{
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "name": "Factory A",
  "code": "FAC-A",
  "timezone": "Asia/Riyadh",
  "address": "Industrial Zone, Riyadh"
}
```

### GET /sites/{site_id}
Auth: admin/supervisor/viewer

Response 200:
```json
{
  "id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "name": "Factory A",
  "code": "FAC-A",
  "timezone": "Asia/Riyadh",
  "address": "Industrial Zone, Riyadh"
}
```

Response 201:
```json
{
  "id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "name": "Factory A",
  "code": "FAC-A",
  "timezone": "Asia/Riyadh"
}
```

### GET /sites?organization_id={organization_id}
Auth: admin/supervisor/viewer

Response 200:
```json
{
  "items": [
    {
      "id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
      "name": "Factory A",
      "code": "FAC-A",
      "timezone": "Asia/Riyadh"
    }
  ],
  "total": 1
}
```

### PATCH /sites/{site_id}
Auth: admin

Request:
```json
{
  "name": "Factory A - Main",
  "timezone": "Asia/Riyadh"
}
```

Response 200:
```json
{
  "id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "name": "Factory A - Main",
  "timezone": "Asia/Riyadh"
}
```

### DELETE /sites/{site_id}
Auth: admin

Response 204: empty body

### POST /cameras
Auth: admin/supervisor

Request:
```json
{
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "camera_code": "CAM-001",
  "name": "Packing Line 1",
  "rtsp_url": "rtsp://10.0.10.2/stream1",
  "profile": "full_suite",
  "thresholds": {
    "ppe_confidence_min": 0.5,
    "fall_confidence_min": 0.45,
    "proximity_meters_min": 2.0,
    "ergonomic_risk_min": 0.7
  },
  "schedule": {
    "timezone": "Asia/Riyadh",
    "windows": [
      {"day": "mon", "start": "06:00", "end": "18:00"},
      {"day": "tue", "start": "06:00", "end": "18:00"}
    ]
  },
  "is_enabled": true
}
```

### GET /cameras?site_id={site_id}&edge_node_id={edge_node_id}&is_enabled={bool}
Auth: admin/supervisor/viewer

Response 200:
```json
{
  "items": [
    {
      "id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
      "camera_code": "CAM-001",
      "name": "Packing Line 1",
      "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
      "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
      "profile": "full_suite",
      "is_enabled": true
    }
  ],
  "total": 1
}
```

Response 201:
```json
{
  "id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "camera_code": "CAM-001",
  "profile": "full_suite",
  "is_enabled": true,
  "thresholds": {
    "ppe_confidence_min": 0.5,
    "fall_confidence_min": 0.45,
    "proximity_meters_min": 2.0,
    "ergonomic_risk_min": 0.7
  }
}
```

### GET /cameras/{camera_id}
Auth: admin/supervisor/viewer

Response 200:
```json
{
  "id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "camera_code": "CAM-001",
  "name": "Packing Line 1",
  "profile": "full_suite",
  "thresholds": {
    "ppe_confidence_min": 0.5,
    "fall_confidence_min": 0.45,
    "proximity_meters_min": 2.0,
    "ergonomic_risk_min": 0.7
  },
  "schedule": {
    "timezone": "Asia/Riyadh",
    "windows": [{"day": "mon", "start": "06:00", "end": "18:00"}]
  },
  "is_enabled": true
}
```

### PATCH /cameras/{camera_id}
Auth: admin/supervisor

Request:
```json
{
  "profile": "proximity_only",
  "thresholds": {
    "proximity_meters_min": 2.5
  },
  "is_enabled": true
}
```

Response 200:
```json
{
  "id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "profile": "proximity_only",
  "is_enabled": true
}
```

### DELETE /cameras/{camera_id}
Auth: admin

Response 204: empty body

### POST /cameras/{camera_id}/calibrations
Auth: admin/supervisor

Request:
```json
{
  "version": 3,
  "unit": "meter",
  "homography_matrix": [
    [1.012, 0.021, -32.1],
    [0.003, 1.087, -18.4],
    [0.00001, 0.00002, 1.0]
  ],
  "reference_points": {
    "image_points": [[125, 340], [710, 352], [150, 620], [740, 650]],
    "world_points_m": [[0, 0], [5, 0], [0, 8], [5, 8]]
  },
  "valid_from": "2026-03-14T00:00:00Z"
}
```

Response 201:
```json
{
  "id": "4c629f6a-04f2-43f8-b13e-cfc33eb8f336",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "version": 3,
  "status": "active"
}
```

### GET /cameras/{camera_id}/calibrations/latest
Auth: admin/supervisor/viewer/edge_node

Response 200:
```json
{
  "id": "4c629f6a-04f2-43f8-b13e-cfc33eb8f336",
  "version": 3,
  "unit": "meter",
  "homography_matrix": [
    [1.012, 0.021, -32.1],
    [0.003, 1.087, -18.4],
    [0.00001, 0.00002, 1.0]
  ],
  "reference_points": {
    "image_points": [[125, 340], [710, 352], [150, 620], [740, 650]],
    "world_points_m": [[0, 0], [5, 0], [0, 8], [5, 8]]
  },
  "valid_from": "2026-03-14T00:00:00Z",
  "status": "active"
}
```

### POST /cameras/{camera_id}/zones
Auth: admin/supervisor

Request:
```json
{
  "name": "Forklift Lane A",
  "zone_type": "forklift_lane",
  "polygon_points": [
    {"x": 0.12, "y": 0.40},
    {"x": 0.82, "y": 0.42},
    {"x": 0.86, "y": 0.68},
    {"x": 0.10, "y": 0.66}
  ],
  "is_active": true
}
```

Response 201:
```json
{
  "id": "f0fbdd4b-95fc-4f55-9e1a-9fd91aa8f770",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "name": "Forklift Lane A",
  "zone_type": "forklift_lane",
  "is_active": true
}
```

### GET /cameras/{camera_id}/zones
Auth: admin/supervisor/viewer/edge_node

Response 200:
```json
{
  "items": [
    {
      "id": "f0fbdd4b-95fc-4f55-9e1a-9fd91aa8f770",
      "name": "Forklift Lane A",
      "zone_type": "forklift_lane",
      "polygon_points": [
        {"x": 0.12, "y": 0.40},
        {"x": 0.82, "y": 0.42},
        {"x": 0.86, "y": 0.68},
        {"x": 0.10, "y": 0.66}
      ],
      "is_active": true
    }
  ],
  "total": 1
}
```

### PATCH /zones/{zone_id}
Auth: admin/supervisor

Request:
```json
{
  "name": "Forklift Lane A (North)",
  "is_active": true
}
```

Response 200:
```json
{
  "id": "f0fbdd4b-95fc-4f55-9e1a-9fd91aa8f770",
  "name": "Forklift Lane A (North)",
  "is_active": true
}
```

### DELETE /zones/{zone_id}
Auth: admin/supervisor

Response 204: empty body

## 6.C Incidents (Hazard Events)
### POST /incidents
Auth: edge_node

Headers:
- `Idempotency-Key: inc_CAM-001_1741946400_track44_fall`

Request:
```json
{
  "api_version": "v1",
  "schema_version": "1.0.0",
  "external_event_id": "evt_20260314_101500_CAM001_00044",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "event_timestamp": "2026-03-14T10:15:00.123Z",
  "hazard_type": "fall_detected",
  "severity": "high",
  "track_id": "44",
  "bbox": {"x1": 0.31, "y1": 0.42, "x2": 0.49, "y2": 0.81},
  "metadata": {
    "profile": "fall_only",
    "confidence": 0.93,
    "calibrated": true,
    "distance_m": null,
    "zone_hits": ["walkway_1"]
  }
}
```

Response 201:
```json
{
  "id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
  "status": "open",
  "created_at": "2026-03-14T10:15:00.300Z"
}
```

Conflict response (duplicate idempotency key) 409:
```json
{
  "error": {
    "code": "IDEMPOTENCY_CONFLICT",
    "message": "Request already processed",
    "request_id": "req_01J..."
  }
}
```

### GET /incidents
Auth: admin/supervisor/viewer

Query params:
- `organization_id` (required)
- `site_id`
- `camera_id`
- `time_from` (ISO8601)
- `time_to` (ISO8601)
- `severity`
- `hazard_type`
- `acknowledged` (`true|false`)
- `status` (`open|acknowledged|resolved`)
- `page` default `1`
- `page_size` default `50`, max `200`

Example:
`GET /api/v1/incidents?organization_id=52a8...&site_id=47d0...&time_from=2026-03-14T00:00:00Z&time_to=2026-03-14T23:59:59Z&severity=high&acknowledged=false&page=1&page_size=50`

Response 200:
```json
{
  "items": [
    {
      "id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
      "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
      "event_timestamp": "2026-03-14T10:15:00.123Z",
      "hazard_type": "fall_detected",
      "severity": "high",
      "status": "open",
      "acknowledged_at": null
    }
  ],
  "page": 1,
  "page_size": 50,
  "total": 1
}
```

### GET /incidents/{incident_id}
Auth: admin/supervisor/viewer

Response 200:
```json
{
  "id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "event_timestamp": "2026-03-14T10:15:00.123Z",
  "hazard_type": "fall_detected",
  "severity": "high",
  "status": "open",
  "track_id": "44",
  "bbox": {"x1": 0.31, "y1": 0.42, "x2": 0.49, "y2": 0.81},
  "metadata": {
    "profile": "fall_only",
    "confidence": 0.93,
    "calibrated": true
  },
  "updates": [
    {
      "id": "f7914d42-3e6f-4fe6-b9c0-f1d77cdb9d48",
      "update_type": "created",
      "note": null,
      "created_at": "2026-03-14T10:15:00.300Z"
    }
  ],
  "evidence": []
}
```

### PATCH /incidents/{incident_id}
Auth: supervisor/admin

Request (acknowledge):
```json
{
  "action": "acknowledge",
  "note": "Supervisor informed floor manager"
}
```

Request (resolve):
```json
{
  "action": "resolve",
  "note": "False alarm - worker kneeling"
}
```

Response 200:
```json
{
  "id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
  "status": "acknowledged",
  "acknowledged_by_user_id": "9b2d4f6a-3f0e-4e7e-b0eb-1f006f26f8d3",
  "acknowledged_at": "2026-03-14T10:16:10Z"
}
```

### POST /incidents/{incident_id}/evidence
Auth: edge_node or supervisor/admin

Request:
```json
{
  "evidence_type": "snapshot",
  "object_key": "org_52a8/site_47d0/cam_CAM-001/2026/03/14/inc_9fa7773f/snapshot_20260314T101500123Z.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 184221,
  "sha256": "f2cbd0d7...",
  "captured_at": "2026-03-14T10:15:00.120Z"
}
```

Response 201:
```json
{
  "id": "26a8b8f6-d5a0-4fce-a3a3-3399c0663d77",
  "incident_id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
  "evidence_type": "snapshot",
  "object_key": "org_52a8/site_47d0/cam_CAM-001/2026/03/14/inc_9fa7773f/snapshot_20260314T101500123Z.jpg"
}
```

## 6.D Telemetry
### POST /telemetry/batch
Auth: edge_node

Request:
```json
{
  "api_version": "v1",
  "schema_version": "1.0.0",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "generated_at": "2026-03-14T10:16:00Z",
  "samples": [
    {
      "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
      "window_start": "2026-03-14T10:15:00Z",
      "window_end": "2026-03-14T10:15:10Z",
      "fps_avg": 27.4,
      "latency_ms_p50": 42.2,
      "latency_ms_p95": 58.6,
      "vram_mb_avg": 1460.5,
      "n_detections": 118,
      "n_tracked": 53,
      "n_hazards": 1,
      "hazard_types": {
        "fall_detected": 1
      },
      "pose_ms_avg": 9.7,
      "track_coverage": 0.87,
      "calibrated": true,
      "raw": {
        "pipeline": "vision_safe_main",
        "profile": "full_suite"
      }
    }
  ]
}
```

Response 202:
```json
{
  "accepted": 1,
  "rejected": 0,
  "request_id": "req_01J..."
}
```

### GET /telemetry/summary
Auth: admin/supervisor/viewer

Query params:
- `organization_id` required
- `site_id` optional
- `camera_id` optional
- `bucket` required (`hour|day`)
- `time_from` required
- `time_to` required

Response 200:
```json
{
  "bucket": "hour",
  "series": [
    {
      "ts": "2026-03-14T10:00:00Z",
      "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
      "fps_avg": 26.9,
      "latency_ms_p95": 61.4,
      "n_hazards": 5,
      "calibrated_ratio": 1.0
    }
  ]
}
```

### GET /health/edges
Auth: admin/supervisor/viewer

Query params:
- `organization_id` required
- `site_id` optional

Response 200:
```json
{
  "items": [
    {
      "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
      "node_code": "JETSON-A1",
      "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
      "last_seen_at": "2026-03-14T10:16:12Z",
      "online": true,
      "camera_health": [
        {
          "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
          "fps_last": 27.4,
          "latency_ms_p95_last": 58.6,
          "n_hazards_last_5m": 1,
          "calibrated": true
        }
      ]
    }
  ]
}
```

## 6.E Edge Management
### POST /edge/register
Auth: bootstrap secret (provisioning) or admin

Request:
```json
{
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "node_code": "JETSON-A1",
  "display_name": "Jetson Line A",
  "agent_version": "0.3.1",
  "api_version": "v1"
}
```

Response 201:
```json
{
  "id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "node_code": "JETSON-A1",
  "edge_api_key": "edge_live_12R...",
  "created_at": "2026-03-14T10:00:00Z"
}
```

### POST /edge/heartbeat
Auth: edge_node

Request:
```json
{
  "api_version": "v1",
  "schema_version": "1.0.0",
  "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "timestamp": "2026-03-14T10:16:12Z",
  "agent_version": "0.3.1",
  "uptime_sec": 86400,
  "cpu_percent": 64.1,
  "mem_percent": 71.3,
  "gpu_percent": 58.2,
  "active_profiles": {
    "CAM-001": "full_suite"
  },
  "calibration_status": {
    "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce": "ok"
  }
}
```

Response 200:
```json
{
  "status": "ok",
  "server_time": "2026-03-14T10:16:12.140Z"
}
```

### GET /edge/config/pull
Auth: edge_node

Query params:
- `edge_node_id` required
- `last_config_version` optional

Response 200:
```json
{
  "config_version": 12,
  "changed": true,
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "cameras": [
    {
      "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
      "camera_code": "CAM-001",
      "enabled": true,
      "profile": "full_suite",
      "thresholds": {
        "ppe_confidence_min": 0.5,
        "fall_confidence_min": 0.45,
        "proximity_meters_min": 2.0,
        "ergonomic_risk_min": 0.7
      },
      "schedule": {
        "timezone": "Asia/Riyadh",
        "windows": [{"day": "mon", "start": "06:00", "end": "18:00"}]
      },
      "zones": [
        {
          "id": "f0fbdd4b-95fc-4f55-9e1a-9fd91aa8f770",
          "zone_type": "forklift_lane",
          "polygon_points": [
            {"x": 0.12, "y": 0.40},
            {"x": 0.82, "y": 0.42},
            {"x": 0.86, "y": 0.68},
            {"x": 0.10, "y": 0.66}
          ]
        }
      ],
      "calibration": {
        "version": 3,
        "unit": "meter",
        "homography_matrix": [
          [1.012, 0.021, -32.1],
          [0.003, 1.087, -18.4],
          [0.00001, 0.00002, 1.0]
        ]
      }
    }
  ],
  "modules": {
    "fall_detection": true,
    "ppe_detection": true,
    "proximity_detection": true,
    "ergonomics": true
  }
}
```

### GET /edge/deployments
Auth: edge_node/admin/supervisor

Query params:
- `edge_node_id` required

Response 200:
```json
{
  "items": [
    {
      "deployment_id": "f0baf8e2-c444-4cd6-8f4f-7f37d3638ea4",
      "profile": "full_suite",
      "status": "active",
      "deployment_config": {
        "model_bundle": {
          "fall": "fall_v9_1.2.0",
          "ppe": "ppe_v11_2.0.1",
          "proximity": "prox_v8_1.8.4"
        }
      },
      "deployed_at": "2026-03-10T07:00:00Z"
    }
  ]
}
```

### POST /edge/deployments
Auth: admin

Request:
```json
{
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "edge_node_id": "2ef6482d-2041-4fa6-afd4-4c7fdf58d871",
  "profile": "full_suite",
  "deployment_config": {
    "model_bundle": {
      "fall": "fall_v9_1.2.0",
      "ppe": "ppe_v11_2.0.1",
      "proximity": "prox_v8_1.8.4"
    }
  }
}
```

Response 201:
```json
{
  "id": "e73edafe-03b2-4aeb-85ea-b88f327433a7",
  "status": "pending",
  "created_at": "2026-03-14T10:18:00Z"
}
```

# 7. WebSocket / Real-time Events
WebSocket endpoint: `/api/v1/ws`

Authentication:
- User: `Authorization` bearer token via query/header.
- Edge: not required for subscription in v1 (edge publishes via REST, backend emits WS).

Subscription message:
```json
{
  "action": "subscribe",
  "channels": [
    "incidents.site.47d03672-3f3f-43e1-b6e7-7f774d80f693",
    "health.site.47d03672-3f3f-43e1-b6e7-7f774d80f693"
  ]
}
```

Channels:
- `incidents.site.{site_id}`
- `incidents.camera.{camera_id}`
- `health.site.{site_id}`
- `health.camera.{camera_id}`
- `calibration.camera.{camera_id}`

## Event payloads
### IncidentEvent
```json
{
  "event_type": "incident.created",
  "event_id": "ws_01J...",
  "occurred_at": "2026-03-14T10:15:00.300Z",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "data": {
    "incident_id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
    "hazard_type": "fall_detected",
    "severity": "high",
    "status": "open",
    "event_timestamp": "2026-03-14T10:15:00.123Z"
  }
}
```

### CameraHealthEvent
```json
{
  "event_type": "camera.health",
  "event_id": "ws_01J...",
  "occurred_at": "2026-03-14T10:16:12.140Z",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "data": {
    "online": true,
    "fps_last": 27.4,
    "latency_ms_p95_last": 58.6,
    "n_hazards_last_5m": 1,
    "last_seen_at": "2026-03-14T10:16:12Z"
  }
}
```

### CalibrationStatusEvent
```json
{
  "event_type": "calibration.status",
  "event_id": "ws_01J...",
  "occurred_at": "2026-03-14T10:20:00Z",
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "data": {
    "calibration_version": 3,
    "status": "active",
    "valid_from": "2026-03-14T00:00:00Z",
    "valid_to": null
  }
}
```

Reconnect and heartbeat:
- Server sends `ping` frame every 20 seconds.
- Client responds with `pong` within 10 seconds.
- If 3 pings missed, server closes connection.
- Client reconnect policy: exponential backoff 1s, 2s, 4s ... max 30s with random jitter +/-25%.
- On reconnect, client resubscribes and performs REST backfill for missed events using `time_from=last_received_timestamp`.

# 8. Storage: Snapshots & Video Clips
Bucket strategy:
- `visionsafe-evidence` (single bucket per environment) or per-org bucket if policy requires strict physical isolation.

Object key format:
- Snapshot:
`org_{org_id}/site_{site_id}/cam_{camera_code}/{YYYY}/{MM}/{DD}/inc_{incident_id}/snapshot_{event_ts_ms}.jpg`
- Clip:
`org_{org_id}/site_{site_id}/cam_{camera_code}/{YYYY}/{MM}/{DD}/inc_{incident_id}/clip_{start_ts_ms}_{end_ts_ms}.mp4`

Signed URL flows:
1. Edge asks backend for upload URL:
- `POST /api/v1/storage/presign-upload`
2. Backend returns presigned PUT URL with 5-minute expiry.
3. Edge uploads object directly to S3/MinIO.
4. Edge calls `POST /incidents/{incident_id}/evidence` with final object key and metadata.

Signed read URL:
- Dashboard requests evidence access:
- `POST /api/v1/storage/presign-download`
- URL TTL default 120 seconds.

### POST /storage/presign-upload
Auth: edge_node or admin/supervisor

Request:
```json
{
  "organization_id": "52a8dacc-f2ba-4a96-a24c-c49a919d95a4",
  "site_id": "47d03672-3f3f-43e1-b6e7-7f774d80f693",
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "incident_id": "9fa7773f-a6f7-4d6f-8610-906a1416c53f",
  "evidence_type": "snapshot",
  "content_type": "image/jpeg",
  "size_bytes": 184221,
  "privacy_processed": true
}
```

Response 200:
```json
{
  "object_key": "org_52a8/site_47d0/cam_CAM-001/2026/03/14/inc_9fa7773f/snapshot_20260314T101500123Z.jpg",
  "upload_url": "https://s3.example.com/visionsafe-evidence/...",
  "expires_in_seconds": 300,
  "required_headers": {
    "Content-Type": "image/jpeg"
  }
}
```

### POST /storage/presign-download
Auth: admin/supervisor/viewer

Request:
```json
{
  "object_key": "org_52a8/site_47d0/cam_CAM-001/2026/03/14/inc_9fa7773f/snapshot_20260314T101500123Z.jpg"
}
```

Response 200:
```json
{
  "download_url": "https://s3.example.com/visionsafe-evidence/...",
  "expires_in_seconds": 120
}
```

Retention policy (v1 default):
- Snapshots: 90 days
- Clips: 30 days
- Resolved incidents evidence retention can be reduced by org policy.
- Lifecycle policies enforced at object storage layer.

Privacy constraints:
- Face blur must be performed at edge before upload.
- Backend rejects uploads with metadata `privacy_processed=false`.
- Evidence metadata must include `privacy_processed=true` and blur method.

# 9. Security Requirements
- TLS:
- All API/WS endpoints served via HTTPS/WSS only.
- TLS 1.2+ minimum.

- Auth strategy:
- Users: JWT access + rotating refresh token.
- Edge nodes: hashed API keys stored server-side; keys displayed once on registration.

- Rate limiting (baseline):
- `/auth/login`: 10 req/min per IP.
- `/incidents`: 600 req/min per edge node.
- `/telemetry/batch`: 120 req/min per edge node.
- Global: 2000 req/min per org.

- Input validation:
- Strict Pydantic schemas; reject unknown fields for ingestion endpoints.
- BBox values must be in `[0,1]` and `x1 < x2`, `y1 < y2`.
- Polygon minimum 3 points.

- Audit logging:
- Log all auth events, config updates, incident state changes, deployment changes, calibration updates.
- Audit log records are append-only; no update/delete API.

- Multi-tenant isolation:
- Every query and write path must enforce `organization_id` from token/key context.
- Never trust client-supplied org_id alone; compare with authenticated principal org scope.
- Row-level security (optional v1.1); mandatory org-scoped service layer in v1.

# 10. Reliability & Offline Resilience
Store-and-forward on edge:
- Queue incident and telemetry payloads in durable local storage.
- Queue items include `created_local_at`, `attempt_count`, `next_attempt_at`, `last_error`.

Idempotency:
- Required for `POST /incidents`.
- Header: `Idempotency-Key`.
- Backend stores org + key unique index and final response payload hash.

Retries and backoff:
- Edge retry schedule as defined in section 3.3.
- HTTP status handling:
- `5xx`, `429`, network timeout -> retry.
- `4xx` validation/auth -> dead-letter and local alert.

Deduplication strategy:
- Uniqueness tuple primary: `(organization_id, external_event_id)`.
- Secondary duplicate heuristic for safety:
- same `camera_id + track_id + hazard_type + event_timestamp rounded to 1s` within 3-second window.
- Secondary duplicates linked via `incident_updates` entry (`update_type=deduplicated`) if needed.

Clock skew handling:
- Accept event timestamps up to 24 hours old and 5 minutes in future.
- If outside range, store event but flag `metadata.clock_skew_flag=true`.
- Use `ingested_at` for pipeline processing order; use `event_timestamp` for analytics semantics.

# 11. Observability
Structured logs:
- JSON logs with keys:
- `timestamp`, `level`, `service`, `request_id`, `organization_id`, `site_id`, `edge_node_id`, `path`, `status_code`, `latency_ms`, `error_code`.

Metrics (Prometheus style):
- `http_requests_total{path,method,status}`
- `http_request_duration_ms_bucket{path,method}`
- `incidents_ingested_total{hazard_type,severity}`
- `incidents_deduplicated_total`
- `telemetry_samples_ingested_total`
- `edge_heartbeat_last_seen_seconds{edge_node_id}`
- `ws_connections_active`
- `db_query_duration_ms_bucket{query_name}`
- `object_storage_errors_total{operation}`

Tracing (optional but recommended):
- OpenTelemetry for request spans across API, DB, Redis, object storage.

Alert rules:
- Edge offline: no heartbeat for > 90 seconds.
- High event rate: `incidents_ingested_total` > configured threshold per site/min.
- High latency: P95 API latency > 500ms for 5 minutes.
- Calibration missing: camera has no active calibration while profile requires distance-based logic.

# 12. Deployment Guide
## 12.1 Docker Compose Example
```yaml
version: "3.9"
services:
  backend:
    build: ./backend
    container_name: visionsafe_backend
    env_file:
      - .env
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - minio
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

  postgres:
    image: postgres:15
    container_name: visionsafe_postgres
    environment:
      POSTGRES_DB: visionsafe
      POSTGRES_USER: visionsafe
      POSTGRES_PASSWORD: visionsafe_pass
    volumes:
      - pg_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    container_name: visionsafe_redis
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    container_name: visionsafe_minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"

volumes:
  pg_data:
  minio_data:
```

## 12.2 Required Environment Variables
```env
APP_ENV=production
API_PREFIX=/api/v1
JWT_SECRET=replace_me
JWT_ACCESS_TTL_SECONDS=900
JWT_REFRESH_TTL_SECONDS=2592000
DB_HOST=postgres
DB_PORT=5432
DB_NAME=visionsafe
DB_USER=visionsafe
DB_PASSWORD=visionsafe_pass
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=visionsafe-evidence
S3_REGION=us-east-1
S3_USE_SSL=false
RATE_LIMIT_ENABLED=true
CORS_ORIGINS=https://dashboard.example.com
```

## 12.3 Migration Steps
1. Start dependencies: `docker compose up -d postgres redis minio`.
2. Run migrations: `alembic upgrade head`.
3. Start backend: `docker compose up -d backend`.
4. Verify health: `GET /api/v1/health/live` returns `200`.

## 12.4 Initial Admin User Creation
Option A (preferred): management command.
```bash
python -m app.cli.create_admin \
  --organization-slug acme-mfg \
  --email admin@factory-a.com \
  --password 'StrongPassword123!' \
  --full-name 'Factory Admin'
```

Option B: one-time SQL seed migration with hashed password.

## 12.5 Backup Strategy
- PostgreSQL:
- Daily full `pg_dump` + 15-minute WAL archiving (if available).
- Retention: 30 daily backups + 12 monthly.

- Object storage:
- Bucket versioning enabled.
- Daily replication to secondary storage target.

- Restore drill:
- Monthly restore test into staging and API smoke tests.

## 12.6 Scaling Notes
- API workers: increase FastAPI/Uvicorn workers based on CPU cores.
- WebSocket scaling:
- Use Redis pub/sub for fanout across workers/instances.
- Sticky sessions not required when pub/sub broadcast is implemented.
- DB scaling:
- Add read replica for heavy analytics reads.
- Keep writes on primary.

# 13. Integration Contract with Edge AI
All ingestion payloads require:
- `api_version` (string, e.g., `v1`)
- `schema_version` (semver string, e.g., `1.0.0`)

## 13.1 HazardEvent Payload (exact contract)
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "api_version",
    "schema_version",
    "external_event_id",
    "organization_id",
    "site_id",
    "edge_node_id",
    "camera_id",
    "event_timestamp",
    "hazard_type",
    "severity",
    "bbox",
    "metadata"
  ],
  "properties": {
    "api_version": {"type": "string", "enum": ["v1"]},
    "schema_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "external_event_id": {"type": "string", "maxLength": 100},
    "organization_id": {"type": "string", "format": "uuid"},
    "site_id": {"type": "string", "format": "uuid"},
    "edge_node_id": {"type": "string", "format": "uuid"},
    "camera_id": {"type": "string", "format": "uuid"},
    "event_timestamp": {"type": "string", "format": "date-time"},
    "hazard_type": {"type": "string", "maxLength": 64},
    "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
    "track_id": {"type": ["string", "null"], "maxLength": 64},
    "bbox": {
      "type": "object",
      "additionalProperties": false,
      "required": ["x1", "y1", "x2", "y2"],
      "properties": {
        "x1": {"type": "number", "minimum": 0, "maximum": 1},
        "y1": {"type": "number", "minimum": 0, "maximum": 1},
        "x2": {"type": "number", "minimum": 0, "maximum": 1},
        "y2": {"type": "number", "minimum": 0, "maximum": 1}
      }
    },
    "metadata": {"type": "object"}
  }
}
```

## 13.2 TelemetryBatch Payload (exact contract)
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "api_version",
    "schema_version",
    "organization_id",
    "site_id",
    "edge_node_id",
    "generated_at",
    "samples"
  ],
  "properties": {
    "api_version": {"type": "string", "enum": ["v1"]},
    "schema_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "organization_id": {"type": "string", "format": "uuid"},
    "site_id": {"type": "string", "format": "uuid"},
    "edge_node_id": {"type": "string", "format": "uuid"},
    "generated_at": {"type": "string", "format": "date-time"},
    "samples": {
      "type": "array",
      "minItems": 1,
      "maxItems": 500,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "camera_id",
          "window_start",
          "window_end",
          "fps_avg",
          "latency_ms_p50",
          "latency_ms_p95",
          "n_detections",
          "n_tracked",
          "n_hazards",
          "hazard_types",
          "calibrated"
        ],
        "properties": {
          "camera_id": {"type": "string", "format": "uuid"},
          "window_start": {"type": "string", "format": "date-time"},
          "window_end": {"type": "string", "format": "date-time"},
          "fps_avg": {"type": "number", "minimum": 0},
          "latency_ms_p50": {"type": "number", "minimum": 0},
          "latency_ms_p95": {"type": "number", "minimum": 0},
          "vram_mb_avg": {"type": ["number", "null"], "minimum": 0},
          "n_detections": {"type": "integer", "minimum": 0},
          "n_tracked": {"type": "integer", "minimum": 0},
          "n_hazards": {"type": "integer", "minimum": 0},
          "hazard_types": {"type": "object"},
          "pose_ms_avg": {"type": ["number", "null"], "minimum": 0},
          "track_coverage": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
          "calibrated": {"type": "boolean"},
          "raw": {"type": ["object", "null"]}
        }
      }
    }
  }
}
```

## 13.3 EdgeHeartbeat Payload (exact contract)
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "api_version",
    "schema_version",
    "edge_node_id",
    "timestamp",
    "agent_version",
    "uptime_sec"
  ],
  "properties": {
    "api_version": {"type": "string", "enum": ["v1"]},
    "schema_version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "edge_node_id": {"type": "string", "format": "uuid"},
    "timestamp": {"type": "string", "format": "date-time"},
    "agent_version": {"type": "string", "maxLength": 64},
    "uptime_sec": {"type": "integer", "minimum": 0},
    "cpu_percent": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
    "mem_percent": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
    "gpu_percent": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
    "active_profiles": {"type": ["object", "null"]},
    "calibration_status": {"type": ["object", "null"]}
  }
}
```

## 13.4 Calibration Status Fields
Calibration status values in heartbeat and config pull responses:
- `ok`: active calibration available and valid.
- `missing`: no calibration found.
- `stale`: calibration exists but older than org policy threshold.
- `invalid`: calibration marked invalid by backend.

Calibration status object format:
```json
{
  "camera_id": "f1ad65b9-c5f7-4ec4-9538-0d80fc7f9fce",
  "status": "ok",
  "calibration_version": 3,
  "updated_at": "2026-03-14T10:10:00Z"
}
```

## 13.5 Versioning Strategy
- `api_version` governs endpoint behavior and URI namespace (`/api/v1`).
- `schema_version` governs payload shape and validation rules.
- Backward-compatible schema changes increase minor version (`1.1.0`).
- Breaking schema changes increase major version and require new API version (`v2`).
- Backend must support previous minor schema versions for at least 90 days.

# 14. Acceptance Criteria (Definition of Done)
- [ ] Backend service boots successfully via Docker Compose.
- [ ] `alembic upgrade head` completes and all required tables/indexes exist.
- [ ] Auth endpoints issue/refresh/revoke tokens correctly.
- [ ] RBAC enforcement verified for all roles (`admin`, `supervisor`, `viewer`, `edge_node`).
- [ ] Edge registration and heartbeat endpoints functional.
- [ ] Edge can post incidents with idempotency and deduplication behavior verified.
- [ ] Edge can post telemetry batch; summaries and health views return correct aggregates.
- [ ] Camera config pull endpoint returns thresholds/profile/schedule/zones/calibration accurately.
- [ ] Dashboard can subscribe WebSocket channels and receive live incident and health events.
- [ ] Incident acknowledge/resolve flows persist updates and audit logs.
- [ ] Evidence upload/download via signed URLs works with metadata persistence.
- [ ] Multi-tenant org isolation verified with integration tests.
- [ ] Core observability dashboards/alerts are operational.

# 15. Future Work
- Advanced analytics pipelines (trend forecasting, anomaly windows, seasonal baselines).
- Spatial heatmaps for incident density by zone/camera.
- Model registry and rollout control plane (canary deployment, rollback policy automation).
- Incident triage workflows with ownership, SLA timers, and escalation rules.
- Notification service integration (FCM, SMS, email, voice bridge).
- Multi-site executive dashboards with benchmarking and comparative KPIs.
- Policy engine for per-site compliance templates and automatic report generation.
