from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.core.security import create_access_token
from datetime import datetime, timedelta, timezone
import secrets
import uuid
import traceback

client = TestClient(app)


def run_smoke_test():
    db = SessionLocal()
    user = None
    rt_value = None
    device_id = None
    try:
        # Create a temporary user
        uid = str(uuid.uuid4())
        user = User(id=uid, firebase_uid=f"smoke-{uid}", name="Smoke Tester", email=f"smoke-{uid}@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
        print("Created test user:", user.id)

        # Issue access token and a device-bound refresh token
        access_token = create_access_token({"sub": user.id})
        rt_value = secrets.token_urlsafe(48)
        device_id = f"device-{str(uuid.uuid4())[:8]}"
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        refresh = RefreshToken(user_id=user.id, token=rt_value, device_id=device_id, expires_at=expires)
        db.add(refresh)
        db.commit()
        print("Inserted refresh token for device:", device_id)

        headers = {"Authorization": f"Bearer {access_token}"}

        # List devices
        resp = client.get("/auth/devices", headers=headers)
        print("GET /auth/devices ->", resp.status_code, resp.json())

        # Revoke device
        resp = client.post(f"/auth/devices/{device_id}/revoke", headers=headers)
        print(f"POST /auth/devices/{device_id}/revoke ->", resp.status_code, resp.json())

        # Re-add a refresh token and test revoke-others
        rt_value2 = secrets.token_urlsafe(48)
        device2 = f"device-{str(uuid.uuid4())[:8]}"
        refresh2 = RefreshToken(user_id=user.id, token=rt_value2, device_id=device2, expires_at=expires)
        db.add(refresh2)
        db.commit()
        print("Inserted second refresh token for device:", device2)

        # Revoke others keeping device2
        resp = client.post("/auth/devices/revoke-others", headers=headers, json={"keep_device_id": device2})
        print("POST /auth/devices/revoke-others ->", resp.status_code, resp.json())

        # Check devices again and print last_used_at values
        resp = client.get("/auth/devices", headers=headers)
        print("GET /auth/devices (after revocations) ->", resp.status_code, resp.json())

    except Exception as e:
        print("Smoke test failed:")
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            if user:
                db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete()
                db.query(User).filter(User.id == user.id).delete()
            db.commit()
        except Exception:
            print("Cleanup failed:")
            traceback.print_exc()
        db.close()


if __name__ == "__main__":
    run_smoke_test()
