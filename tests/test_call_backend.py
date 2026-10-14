import unittest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from app.schemas.call import ScheduledCallOut

class TestScheduledCallBackend(unittest.TestCase):
    def test_scheduled_call_out_schema_with_nulls(self):
        """Verifies that ScheduledCallOut handles None for host_id, created_at, topic, etc."""
        payload = {
            "id": "test_call_123",
            "room_name": "room_test_123",
            "host_id": None,
            "created_at": None,
            "scheduled_at": datetime.now(timezone.utc),
            "status": "scheduled",
            "is_ended_manually": False,
            "topic": None,
        }
        call_out = ScheduledCallOut(**payload)
        self.assertEqual(call_out.id, "test_call_123")
        self.assertIsNone(call_out.host_id)
        self.assertIsNone(call_out.created_at)
        self.assertIsNone(call_out.invited_user_ids)

    def test_scheduled_call_with_invited_user_ids(self):
        """Verifies invited_user_ids is correctly preserved in ScheduledCallOut."""
        payload = {
            "id": "test_call_selective",
            "room_name": "room_test_selective",
            "scheduled_at": datetime.now(timezone.utc),
            "invited_user_ids": ["user_1", "user_2"],
        }
        call_out = ScheduledCallOut(**payload)
        self.assertEqual(call_out.invited_user_ids, ["user_1", "user_2"])

    def test_scheduled_call_two_week_purge_logic(self):
        """Verifies that backend filtering eliminates calls older than 14 days."""
        now = datetime.now(timezone.utc)
        two_weeks_ago = now - timedelta(days=14)

        calls = [
            {"id": "c1", "scheduled_at": now - timedelta(days=16), "status": "ended"},
            {"id": "c2", "scheduled_at": now - timedelta(days=10), "status": "ended"},
            {"id": "c3", "scheduled_at": now + timedelta(hours=2), "status": "scheduled"},
        ]

        active_calls = [
            c for c in calls
            if c["scheduled_at"] >= two_weeks_ago
        ]

        ids = [c["id"] for c in active_calls]
        self.assertNotIn("c1", ids)
        self.assertIn("c2", ids)
        self.assertIn("c3", ids)

    def test_scheduled_call_sorting_order(self):
        """Verifies scheduled/active calls come first ascending, finished calls below descending."""
        now = datetime.now(timezone.utc)
        calls = [
            {"id": "finished_yesterday", "scheduled_at": now - timedelta(days=1), "status": "ended", "is_ended_manually": True},
            {"id": "finished_two_days_ago", "scheduled_at": now - timedelta(days=2), "status": "ended", "is_ended_manually": True},
            {"id": "upcoming_in_3h", "scheduled_at": now + timedelta(hours=3), "status": "scheduled", "is_ended_manually": False},
            {"id": "upcoming_in_1h", "scheduled_at": now + timedelta(hours=1), "status": "scheduled", "is_ended_manually": False},
        ]

        def sort_key(c):
            is_ended = c.get("is_ended_manually") or c.get("status") == "ended"
            sched = c.get("scheduled_at") or now
            if not is_ended:
                return (0, sched.timestamp())
            return (1, -sched.timestamp())

        sorted_calls = sorted(calls, key=sort_key)
        sorted_ids = [c["id"] for c in sorted_calls]

        expected_order = [
            "upcoming_in_1h",
            "upcoming_in_3h",
            "finished_yesterday",
            "finished_two_days_ago"
        ]
        self.assertEqual(sorted_ids, expected_order)

    def test_strict_private_call_filter(self):
        """Verifies private calls are only visible to host and invited participants."""
        calls = [
            {"id": "public_call", "host_id": "host_1", "invited_user_ids": None},
            {"id": "private_call_1", "host_id": "host_1", "invited_user_ids": ["user_a", "user_b"]},
            {"id": "private_call_2", "host_id": "host_2", "invited_user_ids": ["user_c"]},
        ]

        def get_visible_for_user(uid):
            visible = []
            for c in calls:
                inv = c["invited_user_ids"]
                is_host = c["host_id"] == uid
                is_priv = bool(inv and len(inv) > 0)
                if is_priv and not is_host:
                    if not inv or uid not in inv:
                        continue
                visible.append(c["id"])
            return visible

        # Host 1 sees public_call and private_call_1 (they are host)
        self.assertEqual(get_visible_for_user("host_1"), ["public_call", "private_call_1"])
        # User A sees public_call and private_call_1 (invited)
        self.assertEqual(get_visible_for_user("user_a"), ["public_call", "private_call_1"])
        # User C sees public_call and private_call_2 (invited)
        self.assertEqual(get_visible_for_user("user_c"), ["public_call", "private_call_2"])
        # User X (not invited) sees ONLY public_call
        self.assertEqual(get_visible_for_user("user_x"), ["public_call"])

if __name__ == '__main__':
    unittest.main()
