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

    def test_07_private_meeting_token_security(self):
        """Test that private meetings strictly reject unauthenticated and uninvited users."""
        from app.models.call import ScheduledCall
        private_room = f"priv_room_{uuid.uuid4().hex[:8]}"
        self.created_room_names.append(private_room)

        # Host creates private meeting inviting only 'invited_friend_999'
        sched = ScheduledCall(
            topic="Private Prayer",
            room_name=private_room,
            host_id=self.test_uid,
            invited_user_ids="invited_friend_999",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
            access_type="invite_only",
            status="created"
        )
        self.db.add(sched)
        self.db.commit()

        # 1. Unauthenticated request -> Must return 401
        resp_unauth = client.get(f"/auth/rtc-token?channelName={private_room}&uid=99")
        self.assertEqual(resp_unauth.status_code, 401)

        # 2. Authenticated user who is NOT invited -> Must return 403
        uninvited_uid = f"uninvited-{uuid.uuid4().hex[:6]}"
        uninvited_token = create_access_token({"sub": uninvited_uid})
        resp_uninvited = client.get(
            f"/auth/rtc-token?channelName={private_room}&uid=99",
            headers={"Authorization": f"Bearer {uninvited_token}"}
        )
        self.assertEqual(resp_uninvited.status_code, 403)

        # 3. Host request -> Must succeed with 200
        resp_host = client.get(
            f"/auth/rtc-token?channelName={private_room}&uid=1",
            headers=self.auth_headers
        )
        self.assertEqual(resp_host.status_code, 200)
        self.assertIn("token", resp_host.json())

        # 4. Invited user request -> Must succeed with 200
        invited_token = create_access_token({"sub": "invited_friend_999"})
        resp_invited = client.get(
            f"/auth/rtc-token?channelName={private_room}&uid=2",
            headers={"Authorization": f"Bearer {invited_token}"}
        )
        self.assertEqual(resp_invited.status_code, 200)

    def test_08_blocked_user_token_rejection(self):
        """Test that blocked users are rejected with 403 when requesting an RTC token."""
        from app.models.call import BlockedUser, ScheduledCall
        blocked_target_uid = f"blocked-user-{uuid.uuid4().hex[:6]}"
        room_name = f"block_room_{uuid.uuid4().hex[:8]}"
        self.created_room_names.append(room_name)

        # 1. Create blocked user in users table to satisfy foreign key and commit immediately
        blocked_user = User(
            id=blocked_target_uid,
            firebase_uid=f"fb-{blocked_target_uid}",
            name="Blocked Person",
            email=f"{blocked_target_uid}@example.com"
        )
        self.db.add(blocked_user)
        self.db.commit()

        block_entry = None
        try:
            sched = ScheduledCall(
                topic="Public Prayer But User Blocked",
                room_name=room_name,
                host_id=self.test_uid,
                scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
                access_type="public",
                status="active"
            )
            self.db.add(sched)

            # 2. Block the user
            block_entry = BlockedUser(user_id=self.test_uid, blocked_user_id=blocked_target_uid)
            self.db.add(block_entry)
            self.db.commit()

            # 3. Blocked user attempts to acquire token
            blocked_token = create_access_token({"sub": blocked_target_uid})
            resp = client.get(
                f"/auth/rtc-token?channelName={room_name}&uid=55",
                headers={"Authorization": f"Bearer {blocked_token}"}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("blocked", resp.json()["detail"].lower())
        finally:
            # Cleanup block entry and user safely
            try:
                if block_entry and block_entry in self.db:
                    self.db.delete(block_entry)
                self.db.delete(blocked_user)
                self.db.commit()
            except Exception:
                self.db.rollback()

    def test_09_host_authorization_enforcement(self):
        """Test that non-host callers cannot end meetings, delete meetings, or manage waiting rooms."""
        from app.models.call import ScheduledCall
        room_name = f"host_auth_{uuid.uuid4().hex[:8]}"
        self.created_room_names.append(room_name)

        sched = ScheduledCall(
            topic="Host Auth Test Call",
            room_name=room_name,
            host_id=self.test_uid,
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
            access_type="public",
            status="active"
        )
        self.db.add(sched)
        self.db.commit()

        attacker_token = create_access_token({"sub": f"attacker-{uuid.uuid4().hex[:6]}"})
        attacker_headers = {"Authorization": f"Bearer {attacker_token}"}

        # 1. Non-host attempts to end meeting -> 403
        resp_end = client.post(f"/calls/{room_name}/end", headers=attacker_headers)
        self.assertEqual(resp_end.status_code, 403)

        # 2. Non-host attempts to delete meeting -> 403
        resp_del = client.delete(f"/calls/scheduled/{room_name}", headers=attacker_headers)
        self.assertEqual(resp_del.status_code, 403)

        # 3. Non-host attempts to view waiting room -> 403
        resp_wait = client.get(f"/api/meetings/{room_name}/waiting", headers=attacker_headers)
        self.assertEqual(resp_wait.status_code, 403)

        # 4. Host can view waiting room -> 200
        resp_host_wait = client.get(f"/api/meetings/{room_name}/waiting", headers=self.auth_headers)
        self.assertEqual(resp_host_wait.status_code, 200)

        # 5. Host can delete meeting -> 200
        resp_host_del = client.delete(f"/calls/scheduled/{room_name}", headers=self.auth_headers)
        self.assertEqual(resp_host_del.status_code, 200)
        self.assertEqual(resp_host_del.json()["deleted"], 1)

    def test_10_empty_topic_validation(self):
        """Test that empty or whitespace-only meeting topics are rejected with 400 Bad Request."""
        payload = {
            "topic": "    ",
            "room_name": "room_blank_topic",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
        resp = client.post("/calls/scheduled", json=payload, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cannot be empty", resp.json()["detail"].lower())

    def test_11_participant_media_state_sync(self):
        """Test participant registration preserves is_video_muted and is_audio_muted."""
        room_name = f"sync_room_{uuid.uuid4().hex[:8]}"
        self.created_room_names.append(room_name)

        reg_payload = {
            "uid": 505,
            "name": "Sync Participant",
            "is_host": False,
            "is_video_muted": True,
            "is_audio_muted": True
        }
        reg_resp = client.post(f"/calls/{room_name}/participants", json=reg_payload, headers=self.auth_headers)
        self.assertEqual(reg_resp.status_code, 200)
        p_data = reg_resp.json()["participant"]
        self.assertTrue(p_data["is_video_muted"])
        self.assertTrue(p_data["is_audio_muted"])

        # Fetch participants list
        get_resp = client.get(f"/calls/{room_name}/participants", headers=self.auth_headers)
        self.assertEqual(get_resp.status_code, 200)
        parts = get_resp.json()
        match = [p for p in parts if p["uid"] == 505]
        self.assertTrue(len(match) > 0)
        self.assertTrue(match[0]["is_video_muted"])
        self.assertTrue(match[0]["is_audio_muted"])

if __name__ == '__main__':
    unittest.main()
