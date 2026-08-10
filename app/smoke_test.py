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
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        refresh = RefreshToken(user_id=user.id, token=rt_value, expires_at=expires)
        db.add(refresh)
        db.commit()
        print("Inserted refresh token")

        # Call /auth/me
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = client.get("/auth/me", headers=headers)
        print("GET /auth/me ->", resp.status_code, resp.json())

        # Call /auth/refresh
        resp = client.post("/auth/refresh", json={"refresh_token": rt_value})
        print("POST /auth/refresh ->", resp.status_code, resp.json())

        # Call /auth/logout
        resp = client.post("/auth/logout", json={"refresh_token": rt_value})
        print("POST /auth/logout ->", resp.status_code, resp.json())

    except Exception as e:
        print("Smoke test failed:")
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            if rt_value:
                db.query(RefreshToken).filter(RefreshToken.token == rt_value).delete()
            if user:
                db.query(User).filter(User.id == user.id).delete()
            db.commit()
        except Exception:
            print("Cleanup failed:")
            traceback.print_exc()
        db.close()


if __name__ == "__main__":
    run_smoke_test()
