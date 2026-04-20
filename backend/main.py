"""Entrypoint for running the active backend from the backend folder.

Run:
  uvicorn main:app --reload --port 8000
"""

from app.main import app
