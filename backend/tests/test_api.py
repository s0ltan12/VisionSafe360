from __future__ import annotations

import os
import tempfile
import unittest
import uuid
import yaml
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
from backend.app.models import Alert, Camera, User
from backend.app.services.login_rate_limit_service import login_rate_limit_service
from backend.app.services.rate_limit_service import rate_limit_service
from backend.app.services import job_service as job_service_module
from backend.app.services.worker_tasks import _build_dynamic_profile
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

	def put(self, url: str, **kwargs):
		return self.request("PUT", url, **kwargs)

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

	def test_safety_zone_type_applies_locked_defaults(self):
		with SessionLocal() as db:
			if db.query(Camera).filter(Camera.id == "CAM-ZONES").first() is None:
				db.add(Camera(id="CAM-ZONES", name="Zone Camera", zone="Factory / Test", status="Online"))
				db.commit()

		create_zone = self.client.post(
			"/api/cameras/CAM-ZONES/safety-zones",
			headers=self.auth_headers,
			json={
				"name": "Forklift Lane",
				"zone_type": "forklift_only",
				"polygon": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}],
				"source_width": 1280,
				"source_height": 720,
				"rules": {
					"allowed_classes": ["person", "forklift"],
					"denied_classes": [],
					"occupancy_threshold": 9,
					"dwell_time_limit_sec": 99,
					"cooldown_sec": 99,
					"severity": "Low",
				},
			},
		)
		self.assertEqual(create_zone.status_code, 201)
		zone = create_zone.json()
		self.assertEqual(zone["rules"]["allowed_classes"], ["forklift"])
		self.assertEqual(zone["rules"]["denied_classes"], ["person"])
		self.assertEqual(zone["rules"]["occupancy_threshold"], 1)
		self.assertEqual(zone["rules"]["dwell_time_limit_sec"], 0)
		self.assertEqual(zone["rules"]["cooldown_sec"], 10)
		self.assertEqual(zone["rules"]["severity"], "High")

		custom_denied_all = self.client.patch(
			f"/api/safety-zones/{zone['id']}",
			headers=self.auth_headers,
			json={
				"zone_type": "custom",
				"rules": {
					"allowed_classes": [],
					"denied_classes": ["person", "forklift"],
					"occupancy_threshold": 0,
					"dwell_time_limit_sec": 0,
					"cooldown_sec": 0,
					"severity": "Critical",
				},
			},
		)
		self.assertEqual(custom_denied_all.status_code, 422)

	def test_ppe_zone_required_ppe_validation_and_persistence(self):
		with SessionLocal() as db:
			if db.query(Camera).filter(Camera.id == "CAM-PPE-ZONES").first() is None:
				db.add(Camera(id="CAM-PPE-ZONES", name="PPE Zone Camera", zone="Factory / PPE", status="Online"))
				db.commit()

		create_zone = self.client.post(
			"/api/cameras/CAM-PPE-ZONES/safety-zones",
			headers=self.auth_headers,
			json={
				"name": "Helmet and Glasses",
				"zone_type": "ppe_required",
				"polygon": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}],
				"source_width": 1280,
				"source_height": 720,
				"required_ppe": ["helmet", "safety-vest", "goggles"],
				"rules": {
					"allowed_classes": [],
					"denied_classes": ["person", "forklift"],
					"required_ppe": ["gloves"],
					"occupancy_threshold": 2,
					"dwell_time_limit_sec": 9,
					"cooldown_sec": 999,
					"severity": "Low",
				},
			},
		)
		self.assertEqual(create_zone.status_code, 201)
		zone = create_zone.json()
		self.assertEqual(zone["required_ppe"], ["helmet", "vest", "safety_glasses"])
		self.assertEqual(zone["rules"]["required_ppe"], ["helmet", "vest", "safety_glasses"])
		self.assertEqual(zone["rules"]["allowed_classes"], [])
		self.assertEqual(zone["rules"]["denied_classes"], ["person", "forklift"])
		self.assertEqual(zone["rules"]["occupancy_threshold"], 2)
		self.assertEqual(zone["rules"]["dwell_time_limit_sec"], 9)
		self.assertEqual(zone["rules"]["cooldown_sec"], 999)
		self.assertEqual(zone["rules"]["severity"], "Low")

		list_response = self.client.get("/api/cameras/CAM-PPE-ZONES/safety-zones", headers=self.auth_headers)
		self.assertEqual(list_response.status_code, 200)
		listed = next(item for item in list_response.json() if item["id"] == zone["id"])
		self.assertEqual(listed["required_ppe"], ["helmet", "vest", "safety_glasses"])

		edge_response = self.client.get("/api/edge/cameras/CAM-PPE-ZONES/safety-zones", headers=self.auth_headers)
		self.assertEqual(edge_response.status_code, 200)
		edge_zone = next(item for item in edge_response.json()["zones"] if item["id"] == zone["id"])
		self.assertEqual(edge_zone["rules"]["required_ppe"], ["helmet", "vest", "safety_glasses"])
		self.assertEqual(edge_zone["rules"]["occupancy_threshold"], 2)
		self.assertEqual(edge_zone["rules"]["dwell_time_limit_sec"], 9)
		self.assertEqual(edge_zone["rules"]["cooldown_sec"], 999)

		update_zone = self.client.patch(
			f"/api/safety-zones/{zone['id']}",
			headers=self.auth_headers,
			json={
				"required_ppe": ["gloves", "face mask"],
				"rules": {
					"allowed_classes": ["person"],
					"denied_classes": ["forklift"],
					"occupancy_threshold": 4,
					"dwell_time_limit_sec": 30,
					"cooldown_sec": 12,
					"severity": "High",
				},
			},
		)
		self.assertEqual(update_zone.status_code, 200)
		self.assertEqual(update_zone.json()["required_ppe"], ["gloves", "face_mask"])
		self.assertEqual(update_zone.json()["rules"]["allowed_classes"], ["person"])
		self.assertEqual(update_zone.json()["rules"]["denied_classes"], ["forklift"])
		self.assertEqual(update_zone.json()["rules"]["occupancy_threshold"], 4)
		self.assertEqual(update_zone.json()["rules"]["dwell_time_limit_sec"], 30)
		self.assertEqual(update_zone.json()["rules"]["cooldown_sec"], 12)
		self.assertEqual(update_zone.json()["rules"]["severity"], "High")

		clear_zone = self.client.patch(
			f"/api/safety-zones/{zone['id']}",
			headers=self.auth_headers,
			json={"required_ppe": None},
		)
		self.assertEqual(clear_zone.status_code, 200)
		self.assertEqual(clear_zone.json()["required_ppe"], [])

		put_zone = self.client.put(
			f"/api/safety-zones/{zone['id']}",
			headers=self.auth_headers,
			json={"required_ppe": ["ear protection", "boots"]},
		)
		self.assertEqual(put_zone.status_code, 200)
		self.assertEqual(put_zone.json()["required_ppe"], ["ear_protection", "safety_shoes"])
		self.assertEqual(put_zone.json()["rules"]["required_ppe"], ["ear_protection", "safety_shoes"])

	def test_ppe_zone_rejects_invalid_and_duplicate_required_ppe(self):
		with SessionLocal() as db:
			if db.query(Camera).filter(Camera.id == "CAM-PPE-VALIDATION").first() is None:
				db.add(Camera(id="CAM-PPE-VALIDATION", name="PPE Validation Camera", zone="Factory / PPE", status="Online"))
				db.commit()

		base_payload = {
			"name": "Invalid PPE",
			"zone_type": "ppe_required",
			"polygon": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}],
			"source_width": 1280,
			"source_height": 720,
		}
		invalid = self.client.post(
			"/api/cameras/CAM-PPE-VALIDATION/safety-zones",
			headers=self.auth_headers,
			json={**base_payload, "required_ppe": ["helmet", "cape"]},
		)
		self.assertEqual(invalid.status_code, 422)

		duplicate = self.client.post(
			"/api/cameras/CAM-PPE-VALIDATION/safety-zones",
			headers=self.auth_headers,
			json={**base_payload, "required_ppe": ["vest", "safety_vest"]},
		)
		self.assertEqual(duplicate.status_code, 422)

	def test_camera_start_passes_selected_ai_profile_to_worker_job(self):
		class FakeLock:
			def __enter__(self):
				return self

			def __exit__(self, exc_type, exc, tb):
				return False

		class FakeStateConnection:
			def lock(self, *args, **kwargs):
				return FakeLock()

		class FakeQueue:
			name = "test-queue"

			def enqueue(self, func, *, kwargs, **options):
				self.kwargs = kwargs
				self.options = options
				return type("FakeJob", (), {"id": "job-ai-profile"})()

		fake_queue = FakeQueue()
		original_queue = job_service_module.get_job_queue
		original_state_connection = job_service_module.get_state_connection
		original_select_worker = job_service_module.select_worker
		original_set_state = job_service_module.set_job_state
		original_get_state = job_service_module.get_job_state
		original_cancel = job_service_module.JobService._cancel_pending_jobs_for_camera
		try:
			job_service_module.get_job_queue = lambda queue_name: fake_queue
			job_service_module.get_state_connection = lambda: FakeStateConnection()
			job_service_module.select_worker = lambda: None
			job_service_module.set_job_state = lambda *args, **kwargs: None
			job_service_module.get_job_state = lambda camera_id: {}
			job_service_module.JobService._cancel_pending_jobs_for_camera = lambda self, camera_id, exclude_job_id=None: None

			with SessionLocal() as db:
				camera = db.query(Camera).filter(Camera.id == "CAM-AI-PROFILE").first()
				if camera is None:
					db.add(
						Camera(
							id="CAM-AI-PROFILE",
							name="AI Profile Camera",
							zone="Factory / Forklift Lane",
							stream_url="v1.mp4",
							source_type="file",
							severity_profile="custom:proximity+ergonomics",
							supported_ai_capabilities=["proximity", "ergonomics"],
							ai_alert_cooldown_sec=12,
						)
					)
				else:
					camera.stream_url = "v1.mp4"
					camera.source_type = "file"
					camera.severity_profile = "custom:proximity+ergonomics"
					camera.supported_ai_capabilities = ["proximity", "ergonomics"]
					camera.ai_alert_cooldown_sec = 12
				db.commit()

			response = self.client.post("/api/cameras/CAM-AI-PROFILE/start", headers=self.auth_headers)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(fake_queue.kwargs["edge_capabilities"], ["proximity", "ergonomics"])
			self.assertEqual(fake_queue.kwargs["edge_alert_cooldown_sec"], 12)
		finally:
			job_service_module.get_job_queue = original_queue
			job_service_module.get_state_connection = original_state_connection
			job_service_module.select_worker = original_select_worker
			job_service_module.set_job_state = original_set_state
			job_service_module.get_job_state = original_get_state
			job_service_module.JobService._cancel_pending_jobs_for_camera = original_cancel

	def test_dynamic_worker_profile_contains_dashboard_cooldown(self):
		profile_path = _build_dynamic_profile(["ppe", "fall", "ergonomics"], "full_suite", 17)
		with open(profile_path, "r", encoding="utf-8") as handle:
			profile = yaml.safe_load(handle)

		self.assertEqual(profile["alert_policy"]["cooldown_sec"], 17.0)
		self.assertTrue(profile["modules"]["ppe_analyzer"]["enabled"])
		self.assertTrue(profile["modules"]["hazard_analyzer"]["sub_modules"]["fall"]["enabled"])
		self.assertTrue(profile["modules"]["posture_analyzer"]["enabled"])


if __name__ == "__main__":
	unittest.main()
