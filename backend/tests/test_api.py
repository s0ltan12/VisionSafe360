from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "visionsafe360_test_backend.db")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-with-32-characters"

from backend.app import main as app_main
from backend.app.config.database import Base, SessionLocal, engine
from backend.app.models import Alert, User
from backend.app.utils.security import hash_password


class BackendAPITestCase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		app_main.seed = lambda: None
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
		cls.client = TestClient(app_main.app)
		login = cls.client.post("/api/auth/login", json={"email": "alex.m@visionsafe.co", "password": "Admin123"})
		token = login.json()["access_token"]
		cls.auth_headers = {"Authorization": f"Bearer {token}"}

	@classmethod
	def tearDownClass(cls):
		Base.metadata.drop_all(bind=engine)
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
				"timestamp": "10:00 AM",
				"status": "New",
				"description": "Fall detected",
				"thumbnail": "https://example.com/image.jpg",
				"confidence": 98.0,
			},
		)
		self.assertEqual(create_alert.status_code, 201)

		stats = self.client.get("/api/stats", headers=self.auth_headers)
		self.assertEqual(stats.status_code, 200)
		self.assertEqual(stats.json()["total_alerts"], 1)
		self.assertEqual(stats.json()["total_users"], 2)

		delete_alert = self.client.delete("/api/alerts/ALT-9999", headers=self.auth_headers)
		self.assertEqual(delete_alert.status_code, 204)

		stats_after_delete = self.client.get("/api/stats", headers=self.auth_headers)
		self.assertEqual(stats_after_delete.status_code, 200)
		self.assertEqual(stats_after_delete.json()["total_alerts"], 0)


if __name__ == "__main__":
	unittest.main()
