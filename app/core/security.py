from datetime import datetime, timedelta
from firebase_admin import auth as firebase_auth
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def verify_firebase_token(id_token: str) -> dict:
    """Verifies a Firebase ID token sent from the Flutter app. Raises HTTPException if invalid."""
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Creates our own app-level JWT, signed with jwt_secret."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """FastAPI dependency to protect routes. Use as: current_user: dict = Depends(get_current_user)"""
    token = credentials.credentials
    payload = decode_access_token(token)
    return payload


def get_optional_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(optional_security)) -> dict | None:
    """FastAPI dependency for optional auth. Returns user payload or None if token is missing/expired."""
    if not credentials or not credentials.credentials:
        return None
    try:
        return decode_access_token(credentials.credentials)
    except Exception:
        return None