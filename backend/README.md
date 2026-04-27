# VisionSafe 360 — Backend API

This is the active backend for the project.

## Structure

- `backend/app/main.py`: FastAPI app and routes.
- `backend/app/config/database.py`: SQLAlchemy engine/session.
- `backend/app/models/models.py`: ORM models.
- `backend/app/schemas/schemas.py`: Pydantic schemas.
- `backend/app/api/routes/`: feature routers for alerts, cameras, incidents, users, auth, media, and stats.
- `backend/app/services/`: business logic layer.
- `backend/app/seed.py`: demo data seeding.
- `backend/main.py`: top-level uvicorn entrypoint.
- `backend/migrations/`: Alembic migrations.

## Run

From `backend/`:

`pip install -r requirements.txt`

`alembic upgrade head`

`python -m app.seed`

`uvicorn main:app --reload --port 8000`

`python -m unittest discover -s tests -p 'test_*.py'`

## Auth

- `POST /api/auth/login`
- `GET /api/auth/me`
- All CRUD and analytics endpoints require a Bearer token.

Demo media:

- `GET /api/media/videos`
- `GET /api/media/videos/{video_name}`
- `GET /api/media/video_feed/{video_name}`
- These endpoints expose the sample MP4 files from `edge_ai/vids_test/` for dashboard playback.

Worker jobs:

- `POST /api/jobs/start`
- `POST /api/jobs/stop`
- `GET /api/jobs/status`
- These endpoints control the MVP edge worker process from the dashboard.

Demo seeded credentials:

- `alex.m@visionsafe.co` / `admin`
- `sarah.c@visionsafe.co` / `safety`
- `analyst@visionsafe.co` / `analyst`
