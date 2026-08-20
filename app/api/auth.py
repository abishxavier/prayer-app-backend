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


@router.post("/auth/presence")
def update_presence(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Updates the user's last_seen timestamp to now."""
    user_id = current_user.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        from sqlalchemy.sql import func
        user.last_seen = func.now()
        db.commit()
    return {"status": "ok"}


@router.post("/auth/delete-account")
def delete_account(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes the current user and cascades all related data safely."""
    from app.models.blocked_user import BlockedUser
    from app.models.chat_member import ChatMember
    from app.models.message import Message
    from app.models.prayer_request import PrayerRequest
    from app.models.prayer_response import PrayerResponse
    from app.models.call import ScheduledCall, CallLog
    from app.models.chat import Chat, ChatType

    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    try:
        # 1. Delete refresh tokens
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()

        # 2. Delete blocked user relationships
        db.query(BlockedUser).filter((BlockedUser.user_id == user_id) | (BlockedUser.blocked_user_id == user_id)).delete()

        # 3. Delete prayer responses by user AND prayer responses to user's prayer requests
        user_prayer_req_ids = [r.id for r in db.query(PrayerRequest.id).filter(PrayerRequest.user_id == user_id).all()]
        if user_prayer_req_ids:
            db.query(PrayerResponse).filter(PrayerResponse.request_id.in_(user_prayer_req_ids)).delete(synchronize_session=False)
        db.query(PrayerResponse).filter(PrayerResponse.user_id == user_id).delete()
        db.query(PrayerRequest).filter(PrayerRequest.user_id == user_id).delete()

        # 4. Delete call logs and scheduled calls
        db.query(CallLog).filter((CallLog.caller_id == user_id) | (CallLog.receiver_id == user_id)).delete()
        db.query(ScheduledCall).filter(ScheduledCall.host_id == user_id).delete()

        # 5. Delete sent messages
        db.query(Message).filter(Message.sender_id == user_id).delete()

        # 6. Delete chat memberships
        db.query(ChatMember).filter(ChatMember.user_id == user_id).delete()

        # 7. Handle direct chats created by user
        direct_chats = db.query(Chat).filter(Chat.created_by == user_id, (Chat.type == ChatType.direct) | (Chat.type == "direct")).all()
        for dc in direct_chats:
            db.query(Message).filter(Message.chat_id == dc.id).delete()
            db.query(ChatMember).filter(ChatMember.chat_id == dc.id).delete()
            db.delete(dc)

        # 8. Handle group chats created by user: reassign created_by or delete if empty
        group_chats = db.query(Chat).filter(Chat.created_by == user_id).all()
        for gc in group_chats:
            remaining_member = db.query(ChatMember).filter(ChatMember.chat_id == gc.id).first()
            if remaining_member:
                gc.created_by = remaining_member.user_id
                from app.models.chat_member import MemberRole
                remaining_member.role = MemberRole.admin
            else:
                db.query(Message).filter(Message.chat_id == gc.id).delete()
                db.delete(gc)

        # 9. Delete user record
        db.query(User).filter(User.id == user_id).delete()

        db.commit()
        return {"status": "ok", "message": "Account successfully deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")


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
    if payload.profile_visibility is not None:
        user.profile_visibility = payload.profile_visibility
    if payload.status is not None:
        user.status = payload.status
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/auth/me/device_token")
def update_device_token(payload: __import__('app.schemas.user', fromlist=['DeviceTokenUpdate']).DeviceTokenUpdate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Updates the current authenticated user's FCM device token."""
    user_id = current_user.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.device_token = payload.device_token
    db.add(user)
    db.commit()
    return {"status": "ok"}


@router.get("/auth/users/search", response_model=UserOut)
def search_user_by_phone(phone: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Searches for a user by their phone number."""
    import re
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
    user = db.query(User).filter(User.phone == clean_phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this phone number not found")
    return user


@router.post("/auth/users/match-phones")
def match_phones(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Given a list of phone numbers (from device contacts), returns which ones
    are registered JIPF members. Used for the WhatsApp-style 'Contacts on JIPF' screen.

    Request body: { "phones": ["+919876543210", "9876543210", ...] }
    Response: list of { id, name, phone, profile_image } for matched users
    """
    import re

    raw_phones: list = payload.get("phones", [])
    if not raw_phones:
        return []

    # Normalize all submitted numbers — strip non-digits, keep last 10 digits for matching
    def normalize(p: str) -> str:
        digits = re.sub(r'\D', '', p)
        return digits[-10:] if len(digits) >= 10 else digits

    normalized_map: dict[str, str] = {}  # normalized -> original
    for p in raw_phones:
        n = normalize(p)
        if n:
            normalized_map[n] = p

    # Fetch all users who have a phone set (excluding current user)
    caller_id = current_user.get("sub")
    all_users = db.query(User).filter(
        User.phone.isnot(None),
        User.id != caller_id,
    ).all()

    matched = []
    for user in all_users:
        user_normalized = normalize(user.phone or "")
        if user_normalized and user_normalized in normalized_map:
            matched.append({
                "id": user.id,
                "name": user.name,
                "phone": user.phone,
                "profile_image": user.profile_image,
                "username": user.username,
            })

    return matched


@router.get("/auth/users/{user_id}", response_model=UserOut)
def get_user_profile(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Gets another user's profile, respecting visibility settings."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Simple visibility logic
    # "nobody" -> hide profile image and bio/status maybe? Or just hide profile image
    # "contacts" -> for now treat as everyone, fully implement contacts later if needed
    if user.profile_visibility == "nobody":
        user.profile_image = None
        user.bio = None
        user.status = None
    
    return user


import time
import os
import re
# App ID is always required. Certificate is OPTIONAL:
# - If AGORA_APP_CERTIFICATE env var is set, tokens are generated (certificate mode).
# - If NOT set, we return an empty token so the client connects in App ID only mode.
# DO NOT hardcode the certificate here — a wrong certificate causes errInvalidToken.
DEFAULT_AGORA_APP_ID = "95d9ae080e1f45a6b669e1f7ceed021e"

@router.get("/auth/rtc-token")
def get_rtc_token(channelName: str, current_user: dict = Depends(get_current_user)):
    """Generates an Agora RTC token for the specified channel name.
    
    Returns an empty token (App ID only mode) unless AGORA_APP_CERTIFICATE env var
    is explicitly set. This avoids errInvalidToken when the Agora project is in App
    ID only mode.
    """
    app_id = (os.getenv("AGORA_APP_ID", "") or DEFAULT_AGORA_APP_ID).strip()
    # Only use certificate if explicitly provided via environment variable
    app_certificate = os.getenv("AGORA_APP_CERTIFICATE", "").strip()
    
    # Sanitize channel name to ensure strict ASCII alphanumeric compliance
    sanitized_channel = re.sub(r'[^a-zA-Z0-9_\-]', '_', channelName).strip('_')
    if not sanitized_channel:
        sanitized_channel = f"room_{int(time.time())}"
    
    # If no certificate configured, use App ID only mode (empty token)
    # This is the correct mode when Agora project has no App Certificate enabled
    if not app_certificate:
        return {"token": "", "appId": app_id, "channelName": sanitized_channel, "mode": "app_id_only"}
    
    try:
        privilege_expired_ts = int(time.time()) + 86400  # Valid for 24 hours
        token = RtcTokenBuilder.buildTokenWithUid(
            app_id,
            app_certificate,
            sanitized_channel,
            0,      # uid=0: server assigns a random uid
            1,      # role=Publisher
            privilege_expired_ts
        )
        return {"token": token, "appId": app_id, "channelName": sanitized_channel, "mode": "certificate"}
    except Exception as e:
        # Fallback to App ID only if token generator fails
        return {"token": "", "appId": app_id, "channelName": sanitized_channel, "mode": "app_id_only", "warning": str(e)}


@router.get("/auth/agora-debug")
def agora_debug():
    """Public diagnostic endpoint to check if Agora App ID and Certificate are configured."""
    app_id = (os.getenv("AGORA_APP_ID", "") or DEFAULT_AGORA_APP_ID).strip()
    app_cert = os.getenv("AGORA_APP_CERTIFICATE", "").strip()

    token = ""
    err = None
    if app_cert:
        try:
            token = RtcTokenBuilder.buildTokenWithUid(
                app_id,
                app_cert,
                "test_room",
                0,
                1,
                int(time.time()) + 86400
            )
        except Exception as e:
            err = str(e)

    return {
        "agora_app_id_prefix": app_id[:8] + "..." if len(app_id) >= 8 else app_id,
        "agora_app_id_length": len(app_id),
        "is_custom_app_id": bool(os.getenv("AGORA_APP_ID")),
        "certificate_configured": bool(app_cert),
        "certificate_length": len(app_cert),
        "certificate_prefix": app_cert[:4] + "..." if len(app_cert) >= 4 else "NOT_SET",
        "mode": "certificate" if app_cert else "app_id_only",
        "test_token_generated": bool(token),
        "test_token_length": len(token),
        "test_token_prefix": token[:10] if token else "",
        "token_generation_error": err,
    }