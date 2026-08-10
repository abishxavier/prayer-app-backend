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
    try:
        # Create a temporary user
        uid = str(uuid.uuid4())
        user = User(id=uid, firebase_uid=f"smoke-{uid}", name="Smoke Tester", email=f"smoke-{uid}@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
        print("Created test user:", user.id)

        # Issue an access token and a refresh token (simulate login)
        access_token = create_access_token({"sub": user.id})
        rt_value = secrets.token_urlsafe(48)
        device_id = f"device-{str(uuid.uuid4())[:8]}"
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        refresh = RefreshToken(user_id=user.id, token=rt_value, device_id=device_id, expires_at=expires)
        db.add(refresh)
        db.commit()
        print("Inserted refresh token for device:", device_id)

        # Call /auth/me
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = client.get("/auth/me", headers=headers)
        print("GET /auth/me ->", resp.status_code, resp.json())

        # Call /auth/refresh (will rotate the refresh token) — include device_id in the request
        resp = client.post("/auth/refresh", json={"refresh_token": rt_value, "device_id": device_id})
        print("POST /auth/refresh ->", resp.status_code, resp.json())
        if resp.status_code == 200:
            body = resp.json()
            # rotate local pointer to the new refresh token so logout uses the correct value
            rt_value = body.get("refresh_token") or rt_value

        # Call /auth/logout using the (possibly rotated) refresh token and device_id
        resp = client.post("/auth/logout", json={"refresh_token": rt_value, "device_id": device_id})
        print("POST /auth/logout ->", resp.status_code, resp.json())

    except Exception as e:
        print("Smoke test failed:")
        traceback.print_exc()
    finally:
        # Cleanup: remove any refresh tokens for the test user and the user row
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
