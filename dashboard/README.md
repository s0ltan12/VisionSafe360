# VisionSafe 360 Dashboard

React dashboard for the VisionSafe 360 project.

This workspace uses the dashboard package as the frontend and the FastAPI service in `backend/app` as the active backend implementation.

## Run locally

Prerequisites:
- Node.js
- Python 3.10+
- PostgreSQL accessible on `localhost:5432` or via `DATABASE_URL`

1. Start the backend:
   `cd ../backend && python -m uvicorn main:app --reload --port 8000`
2. Start the frontend:
   `npm install`
   `npm run dev`

## Notes

- The frontend API client points to `http://localhost:8000`.
- The legacy localStorage database helper was retired from the active flow.
