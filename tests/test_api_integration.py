import unittest
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.call import ScheduledCall
from app.core.security import create_access_token

client = TestClient(app)

class TestApiIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.test_uid = f"int-user-{uuid.uuid4()}"
        cls.device_id = f"device-{uuid.uuid4().hex[:8]}"
        cls.user = User(
            id=cls.test_uid,
            firebase_uid=f"firebase-{cls.test_uid}",
            name="Integration Tester",
            email=f"{cls.test_uid}@example.com"
        )
        cls.db.add(cls.user)
        cls.db.commit()
        cls.db.refresh(cls.user)

        cls.access_token = create_access_token({"sub": cls.test_uid})
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

        # Issue initial refresh token
        cls.rt_value = secrets.token_urlsafe(48)
        cls.refresh_token_obj = RefreshToken(
            user_id=cls.test_uid,
            token=cls.rt_value,
            device_id=cls.device_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )
        cls.db.add(cls.refresh_token_obj)
        cls.db.commit()

        cls.created_room_names = []

    @classmethod
    def tearDownClass(cls):
        try:
            # Clean up scheduled calls created during test
            for rname in cls.created_room_names:
                cls.db.query(ScheduledCall).filter(ScheduledCall.room_name == rname).delete()
            # Clean up refresh tokens
            cls.db.query(RefreshToken).filter(RefreshToken.user_id == cls.test_uid).delete()
            # Clean up test user
            cls.db.query(User).filter(User.id == cls.test_uid).delete()
            cls.db.commit()
        except Exception as e:
            cls.db.rollback()
            print(f"tearDownClass cleanup error: {e}")
        finally:
            cls.db.close()

    def test_01_auth_me_integration(self):
        """Test authentication bearer token integration with /auth/me."""
        resp = client.get("/auth/me", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], self.test_uid)
        self.assertEqual(data["name"], "Integration Tester")

    def test_02_auth_refresh_rotation_integration(self):
        """Test refresh token rotation flow with device binding."""
        resp = client.post("/auth/refresh", json={
            "refresh_token": self.rt_value,
            "device_id": self.device_id
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertNotEqual(data["refresh_token"], self.rt_value)

        # Update rt_value to rotated one for subsequent operations
        self.__class__.rt_value = data["refresh_token"]

    def test_03_app_version_integration(self):
        """Test public app version check endpoint."""
        resp = client.get("/api/app/version")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("latest_version", data)

    def test_04_schedule_call_lifecycle_integration(self):
        """Test complete lifecycle: schedule call -> list calls -> verify room -> token -> end meeting."""
        room_name = f"int_room_{uuid.uuid4().hex[:8]}"
        self.created_room_names.append(room_name)

        sched_time = datetime.now(timezone.utc) + timedelta(hours=2)
        sched_time_str = sched_time.isoformat()

        # 1. Schedule a new call
        create_payload = {
            "topic": "Integration Test Prayer Call",
            "room_name": room_name,
            "scheduled_at": sched_time_str,
            "access_type": "public",
            "waiting_room_enabled": False,
            "chat_enabled": True,
            "screen_share_enabled": True
        }
        create_resp = client.post("/calls/scheduled", json=create_payload, headers=self.auth_headers)
        self.assertIn(create_resp.status_code, [200, 201])
        call_data = create_resp.json()
        self.assertEqual(call_data["room_name"], room_name)
        self.assertEqual(call_data["topic"], "Integration Test Prayer Call")

        # 2. Verify call is listed in GET /calls/scheduled
        list_resp = client.get("/calls/scheduled", headers=self.auth_headers)
        self.assertEqual(list_resp.status_code, 200)
        items = list_resp.json()
        matched = [c for c in items if c["room_name"] == room_name]
        self.assertTrue(len(matched) > 0, "Newly created scheduled call should appear in calls list")

        # 3. Verify meeting room access
        verify_resp = client.get(f"/api/meetings/verify/{room_name}", headers=self.auth_headers)
        self.assertEqual(verify_resp.status_code, 200)
        verify_data = verify_resp.json()
        self.assertEqual(verify_data["room_name"], room_name)

        # 4. Generate Agora RTC Token for participant
        token_resp = client.get(f"/auth/rtc-token?channelName={room_name}&uid=12345", headers=self.auth_headers)
        self.assertEqual(token_resp.status_code, 200)
        token_data = token_resp.json()
        self.assertIn("token", token_data)
        self.assertIn("channelName", token_data)
        self.assertEqual(token_data["channelName"], room_name)

        # 5. End Meeting for Everyone
        end_resp = client.post(f"/calls/{room_name}/end", headers=self.auth_headers)
        self.assertEqual(end_resp.status_code, 200)
        end_data = end_resp.json()
        self.assertEqual(end_data.get("status"), "ok")

        # 6. Verify Scheduled Call in DB retains original scheduled_at time (no 4:46 PM regression)
        db_call = self.db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).first()
        self.assertIsNotNone(db_call)
        self.assertEqual(db_call.status, "ended")
        # Ensure scheduled_at is still future/original (+2 hours), not altered or subtracted by 2 hours
        diff_seconds = abs((db_call.scheduled_at.replace(tzinfo=timezone.utc) - sched_time).total_seconds())
        self.assertLess(diff_seconds, 60, "scheduled_at timestamp must be preserved without distortion")

        # 7. Rapid second end_meeting call should trigger debounce gracefully
        end_again_resp = client.post(f"/calls/{room_name}/end", headers=self.auth_headers)
        self.assertEqual(end_again_resp.status_code, 200)

    def test_05_testimonies_api_integration(self):
        """Test testimonies listing endpoint integration."""
        resp = client.get("/testimonies", headers=self.auth_headers)
        self.assertIn(resp.status_code, [200, 204])

    def test_06_gallery_api_integration(self):
        """Test gallery listing endpoint integration."""
        resp = client.get("/gallery", headers=self.auth_headers)
        self.assertIn(resp.status_code, [200, 204])

if __name__ == '__main__':
    unittest.main()
