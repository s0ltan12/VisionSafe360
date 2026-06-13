from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from contextlib import asynccontextmanager
from functools import partial

import anyio
import fastapi.dependencies.utils as fastapi_dependency_utils
import fastapi.routing as fastapi_routing
import httpx
import starlette.concurrency as starlette_concurrency

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"visionsafe360_test_backend_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-with-32-characters"


async def _run_in_threadpool_inline(func, *args, **kwargs):
	return func(*args, **kwargs)


@asynccontextmanager
async def _contextmanager_inline(cm):
	value = cm.__enter__()
	try:
		yield value
	except Exception as exc:
		if not cm.__exit__(type(exc), exc, None):
			raise
	else:
		cm.__exit__(None, None, None)


# The local Python 3.13/AnyIO sandbox blocks worker-thread execution. Patch
# FastAPI's test-time threadpool boundary so synchronous routes run inline.
fastapi_routing.run_in_threadpool = _run_in_threadpool_inline
fastapi_dependency_utils.run_in_threadpool = _run_in_threadpool_inline
fastapi_dependency_utils.contextmanager_in_threadpool = _contextmanager_inline
starlette_concurrency.run_in_threadpool = _run_in_threadpool_inline

from backend.app import main as app_main
from backend.app.api.routes import incidents as incidents_route
from backend.app.config.database import Base, SessionLocal, engine
from backend.app.models import Alert, User
from backend.app.services.login_rate_limit_service import login_rate_limit_service
from backend.app.services.rate_limit_service import rate_limit_service
from backend.app.utils.security import hash_password


async def _noop_broadcast(payload):
	return None


class ASGIClientAdapter:
	"""Synchronous wrapper around httpx ASGITransport for this runtime."""

	def __init__(self, app):
		self.app = app

	async def _request_async(self, method: str, url: str, **kwargs):
		transport = httpx.ASGITransport(app=self.app)
		async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
			return await client.request(method, url, **kwargs)

	def request(self, method: str, url: str, **kwargs):
		return anyio.run(partial(self._request_async, method, url, **kwargs))

	def get(self, url: str, **kwargs):
		return self.request("GET", url, **kwargs)

	def post(self, url: str, **kwargs):
		return self.request("POST", url, **kwargs)

	def patch(self, url: str, **kwargs):
		return self.request("PATCH", url, **kwargs)

	def delete(self, url: str, **kwargs):
		return self.request("DELETE", url, **kwargs)


class BackendAPITestCase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		app_main.seed = lambda: None
		login_rate_limit_service.check_and_consume = lambda ip_address: (True, 0)
		login_rate_limit_service.reset = lambda ip_address: None
		rate_limit_service.check_and_consume = lambda source_id: (True, 0)
		incidents_route.monitoring_service.record_incident = lambda source_id: None
		incidents_route.monitoring_service.record_rate_limited = lambda source_id: None
		incidents_route.incident_ws_manager.broadcast = _noop_broadcast
		engine.dispose()
		Base.metadata.drop_all(bind=engine)
		Base.metadata.create_all(bind=engine)
		with SessionLocal() as db:
			db.add(
				User(
					id="1",
					name="Alex Morgan",
					email="alex.m@visionsafe.co",
					password_hash=hash_password("Admin123"),
					role="Admin",
					status="Active",
				)
			)
			db.commit()
		cls.client = ASGIClientAdapter(app_main.app)
		login = cls.client.post("/api/auth/login", json={"email": "alex.m@visionsafe.co", "password": "Admin123"})
		token = login.json()["access_token"]
		cls.auth_headers = {"Authorization": f"Bearer {token}"}

	@classmethod
	def tearDownClass(cls):
		Base.metadata.drop_all(bind=engine)
		engine.dispose()
		if os.path.exists(TEST_DB_PATH):
			os.remove(TEST_DB_PATH)

	def test_login_and_me(self):
		response = self.client.post("/api/auth/login", json={"email": "alex.m@visionsafe.co", "password": "Admin123"})
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertIn("access_token", payload)

		auth_headers = {"Authorization": f"Bearer {payload['access_token']}"}
		me_response = self.client.get("/api/auth/me", headers=auth_headers)
		self.assertEqual(me_response.status_code, 200)
		self.assertEqual(me_response.json()["email"], "alex.m@visionsafe.co")

	def test_users_and_alerts_crud(self):
		create_user = self.client.post(
			"/api/users",
			headers=self.auth_headers,
			json={
				"id": "2",
				"name": "Sarah Chen",
				"email": "sarah.c@visionsafe.co",
				"password": "Safety123",
				"role": "Safety Engineer",
				"status": "Active",
			},
		)
		self.assertEqual(create_user.status_code, 201)

		duplicate_user = self.client.post(
			"/api/users",
			headers=self.auth_headers,
			json={
				"id": "3",
				"name": "Duplicate",
				"email": "sarah.c@visionsafe.co",
				"password": "Safety123",
				"role": "Safety Engineer",
				"status": "Active",
			},
		)
		self.assertEqual(duplicate_user.status_code, 400)

		create_alert = self.client.post(
			"/api/alerts",
			headers=self.auth_headers,
			json={
				"id": "ALT-9999",
				"type": "Fall",
				"severity": "High",
				"zone": "Zone X",
				"camera": "CAM-01",
				"timestamp": "2026-05-31T10:00:00Z",
				"status": "New",
				"description": "Fall detected",
				"thumbnail": "https://example.com/image.jpg",
				"video_evidence": "data:video/mp4;base64,AAAA",
				"confidence": 98.0,
			},
		)
		self.assertEqual(create_alert.status_code, 201)
		self.assertEqual(create_alert.json()["video_evidence"], "data:video/mp4;base64,AAAA")

		stats = self.client.get("/api/stats", headers=self.auth_headers)
		self.assertEqual(stats.status_code, 200)
		self.assertEqual(stats.json()["total_alerts"], 1)
		self.assertEqual(stats.json()["total_users"], 2)

		patch_alert_status = self.client.patch(
			"/api/alerts/ALT-9999",
			headers=self.auth_headers,
			json={"status": "Resolved"},
		)
		self.assertEqual(patch_alert_status.status_code, 409)

		delete_alert = self.client.delete("/api/alerts/ALT-9999", headers=self.auth_headers)
		self.assertEqual(delete_alert.status_code, 204)

		stats_after_delete = self.client.get("/api/stats", headers=self.auth_headers)
		self.assertEqual(stats_after_delete.status_code, 200)
		self.assertEqual(stats_after_delete.json()["total_alerts"], 0)

	def test_z_viewer_cannot_mutate_incident_lifecycle(self):
		with SessionLocal() as db:
			if db.query(User).filter(User.email == "viewer@visionsafe.co").first() is None:
				db.add(
					User(
						id="viewer-rbac",
						name="Read Only Analyst",
						email="viewer@visionsafe.co",
						password_hash=hash_password("Viewer123"),
						role="Data Analyst",
						status="Active",
					)
				)
				db.commit()

		login = self.client.post("/api/auth/login", json={"email": "viewer@visionsafe.co", "password": "Viewer123"})
		self.assertEqual(login.status_code, 200)
		viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

		create_incident = self.client.post(
			"/api/incidents",
			headers=self.auth_headers,
			json={
				"id": "INC-RBAC-VIEWER",
				"zone": "Zone RBAC",
				"classification": "Forklift Proximity",
				"severity": "High",
				"status": "Active",
				"root_cause": "Test",
				"corrective_action": "Test",
			},
		)
		self.assertEqual(create_incident.status_code, 201)

		read_incidents = self.client.get("/api/incidents/all?view=active", headers=viewer_headers)
		self.assertEqual(read_incidents.status_code, 200)

		acknowledge = self.client.patch("/api/incidents/INC-RBAC-VIEWER/acknowledge", headers=viewer_headers)
		self.assertEqual(acknowledge.status_code, 403)

		resolve = self.client.patch("/api/incidents/INC-RBAC-VIEWER/resolve", headers=viewer_headers)
		self.assertEqual(resolve.status_code, 403)


if __name__ == "__main__":
	unittest.main()
