from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import get_db
from app.core.security import verify_firebase_token, create_access_token, get_current_user
from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse, LogoutRequest
from app.schemas.user import UserOut, UserUpdate
from app.models.user import User
from app.models.refresh_token import RefreshToken
from datetime import datetime, timedelta, timezone
import secrets
from typing import List
from app.schemas.auth import DeviceOut, RevokeOthersRequest
from agora_token_builder import RtcTokenBuilder
import os

router = APIRouter()

AGORA_APP_ID = os.getenv("AGORA_APP_ID", "")
AGORA_APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE", "")


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    decoded = verify_firebase_token(payload.id_token)

    firebase_uid = decoded.get("uid")
    email = decoded.get("email")
    name = decoded.get("name") or (email.split("@")[0] if email else "User")

    if not firebase_uid or not email:
        raise HTTPException(status_code=400, detail="Firebase token missing required fields")

    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()

    if not user:
        user = User(
            firebase_uid=firebase_uid,
            name=name,
            email=email,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(data={"sub": user.id, "firebase_uid": firebase_uid})

    # create a refresh token (random string) and store it with expiry, bound to a device if provided
    rt_value = secrets.token_urlsafe(48)
    rt_expires = datetime.now(timezone.utc) + timedelta(days=30)
    refresh = RefreshToken(
        user_id=user.id,
        token=rt_value,
        device_id=payload.device_id,
        device_info=payload.device_info,
        expires_at=rt_expires,
    )
    db.add(refresh)
    db.commit()

    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        name=user.name,
        email=user.email,
        )


@router.get("/auth/devices", response_model=List[DeviceOut])
def list_devices(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """List active (non-revoked) refresh tokens (devices) for the current user."""
    user_id = current_user.get("sub")
    tokens = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id)
        .order_by(RefreshToken.created_at.desc())
        .all()
    )

    return tokens


@router.post("/auth/devices/{device_id}/revoke")
def revoke_device(device_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke all refresh tokens for a specific device_id for the current user."""
    user_id = current_user.get("sub")
    tokens = db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.device_id == device_id, RefreshToken.revoked == False).all()
    if not tokens:
        return {"status": "ok", "revoked": 0}
    count = 0
    for t in tokens:
        t.revoked = True
        db.add(t)
        count += 1
    db.commit()
    return {"status": "ok", "revoked": count}


@router.post("/auth/devices/revoke-others")
def revoke_other_devices(payload: RevokeOthersRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke all devices for the current user except the one provided in keep_device_id (if any).

    If keep_device_id is omitted, revokes all devices.
    """
    user_id = current_user.get("sub")
    keep = payload.keep_device_id
    query = db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
    if keep:
        query = query.filter(RefreshToken.device_id != keep)

    tokens = query.all()
    count = 0
    for t in tokens:
        t.revoked = True
        db.add(t)
        count += 1
    db.commit()
    return {"status": "ok", "revoked": count}


@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a refresh token for a new access token.

    This implementation rotates refresh tokens: the old token is revoked and a new
    refresh token is issued and returned to the client. This limits the usefulness
    of a stolen refresh token.
    """
    token = payload.refresh_token
    old = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not old or old.revoked:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if old.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Enforce device binding: require device_id match if provided
    req_device = payload.device_id
    if req_device is None:
        raise HTTPException(status_code=400, detail="device_id is required for refresh")
    if old.device_id is not None and old.device_id != req_device:
        # Possible token misuse from a different device
        # Revoke the old token and deny the request
        old.revoked = True
        old.last_used_at = datetime.now(timezone.utc)
        db.add(old)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token device mismatch")

    # Mark old token last_used and revoke it
    now = datetime.now(timezone.utc)
    old.last_used_at = now
    old.revoked = True
    db.add(old)

    # Issue new refresh token bound to same device and record last_used_at
    new_rt = secrets.token_urlsafe(48)
    new_expires = datetime.now(timezone.utc) + timedelta(days=30)
    new_refresh = RefreshToken(user_id=old.user_id, token=new_rt, device_id=req_device, expires_at=new_expires, last_used_at=now)
    db.add(new_refresh)

    # Commit the rotation
    db.commit()

    # Issue new access token
    access_token = create_access_token(data={"sub": old.user_id})
    return RefreshResponse(access_token=access_token, refresh_token=new_rt)


@router.post("/auth/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    """Revoke a refresh token to log out.

    If device_id is provided, prefer revoking the token matching device_id.
    Client should delete local tokens after a successful logout.
    """
    token = payload.refresh_token
    req_device = payload.device_id
    refresh = None
    if token:
        refresh = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not refresh and req_device:
        # Try to find a refresh token for this user/device (idempotent best-effort)
        refresh = db.query(RefreshToken).filter(RefreshToken.device_id == req_device, RefreshToken.revoked == False).first()
    if not refresh:
        return {"status": "ok"}
    refresh.revoked = True
    db.add(refresh)
    db.commit()
    return {"status": "ok"}


@router.get("/auth/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns the current authenticated user's profile."""
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.post("/auth/delete-account")
def delete_account(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes the current user and all associated refresh tokens."""
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    # Delete all refresh tokens
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()

    # Delete user record
    db.query(User).filter(User.id == user_id).delete()

    db.commit()
    return {"status": "ok", "message": "Account successfully deleted"}


@router.put("/auth/me", response_model=UserOut)
def update_profile(payload: UserUpdate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Updates the current authenticated user's profile."""
    user_id = current_user.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if payload.name is not None:
        user.name = payload.name
    if payload.phone is not None:
        import re
        user.phone = re.sub(r'[\s\-\(\)]', '', payload.phone)
    if payload.profile_image is not None:
        user.profile_image = payload.profile_image
    if payload.status is not None:
        user.status = payload.status
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/auth/users/search", response_model=UserOut)
def search_user_by_phone(phone: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Searches for a user by their phone number."""
    import re
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
    user = db.query(User).filter(User.phone == clean_phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this phone number not found")
    return user


@router.get("/auth/rtc-token")
def get_rtc_token(channelName: str, current_user: dict = Depends(get_current_user)):
    """Generates an Agora RTC token for the specified channel name."""
    if not AGORA_APP_ID or not AGORA_APP_CERTIFICATE:
        raise HTTPException(
            status_code=500,
            detail="Agora credentials not configured on backend"
        )
    
    # Generate token (Uid = 0 allows any uid, Role = 1 is Publisher, expires in 24 hours)
    token = RtcTokenBuilder.buildTokenWithUid(
        AGORA_APP_ID,
        AGORA_APP_CERTIFICATE,
        channelName,
        0,
        1,
        86400
    )
    
    return {"token": token, "appId": AGORA_APP_ID}