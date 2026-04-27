# VisionSafe 360 — Project Handover Document

## Current Source of Truth

- The active backend is `backend/app` (entrypoint `backend/main.py`).
- The frontend in `dashboard/` consumes that backend through `dashboard/api.ts`.
- The `backend/app` tree now contains the active implementation.

## What is complete

- Edge AI pipeline and Step 4 alert integration are implemented.
- Dashboard UI is mostly built and connected to the active backend.
- The backend provides CRUD for alerts, cameras, incidents, users, plus dashboard stats.
- Seed data and PostgreSQL table definitions exist for the current backend.

## What still needs work

- Production auth and RBAC.
- Real-time backend delivery and live monitoring data.
- Deployment orchestration with Docker Compose.
- Production auth and RBAC hardening on top of the active backend.

## Database Summary

- One central PostgreSQL database is used by the active backend.
- Edge AI also uses a local SQLite file for offline incident buffering on each node; that is not a shared system database.
- `dashboard/db.ts` was a legacy localStorage prototype and is no longer part of the active architecture.

## Recommended Rule

- Keep backend development only under `backend/app` to avoid drift.
