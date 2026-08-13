from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.security import decode_access_token
from app.models.user import User
from app.models.chat_member import ChatMember
from app.models.message import Message
from app.ws.manager import manager

router = APIRouter()


def _get_db() -> Session:
    # WS endpoints can't use FastAPI's Depends(get_db) the same way as HTTP routes
    # in every setup, so we open/close a session manually per connection.
    return SessionLocal()


async def _authenticate(websocket: WebSocket, chat_id: str, token: str, db: Session) -> User | None:
    """
    Decodes the JWT and checks the user is a member of chat_id.
    Returns the User on success, or None (after closing the socket) on failure.
    """
    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return None

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Malformed token")
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
        return None

    is_member = (
        db.query(ChatMember)
        .filter(ChatMember.chat_id == chat_id, ChatMember.user_id == user.id)
        .first()
    )
    if not is_member:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not a member of this chat")
        return None

    return user


@router.websocket("/ws/chat/{chat_id}")
async def chat_websocket(websocket: WebSocket, chat_id: str, token: str = Query(...)):
    db = _get_db()
    user: User | None = None
    try:
        user = await _authenticate(websocket, chat_id, token, db)
        if user is None:
            return  # socket already closed inside _authenticate

        await manager.connect(chat_id, str(user.id), websocket)

        # Mark online + broadcast join, but only if this is genuinely a new
        # online transition (avoids spamming "joined" if they had another tab open)
        was_already_online = manager.online_users.get(str(user.id), 0) > 1
        if not was_already_online:
            user.status = "online"
            user.last_seen = datetime.now(timezone.utc)
            db.commit()
            await manager.broadcast(chat_id, {
                "type": "presence",
                "user_id": str(user.id),
                "status": "online",
            })

        try:
            while True:
                data = await websocket.receive_json()
                type_ = data.get("type")
                
                if type_ == "typing":
                    await manager.broadcast(chat_id, {
                        "type": "typing",
                        "user_id": str(user.id)
                    }, exclude_websocket=websocket)
                elif type_ == "stop_typing":
                    await manager.broadcast(chat_id, {
                        "type": "stop_typing",
                        "user_id": str(user.id)
                    }, exclude_websocket=websocket)

        except WebSocketDisconnect:
            pass

    finally:
        # Runs whether the loop exited via disconnect or an exception
        if user is not None:
            await manager.disconnect(chat_id, str(user.id), websocket)

            still_online = manager.is_online(str(user.id))
            if not still_online:
                user.status = "offline"
                user.last_seen = datetime.now(timezone.utc)
                db.commit()
                await manager.broadcast(chat_id, {
                    "type": "presence",
                    "user_id": str(user.id),
                    "status": "offline",
                })

        db.close()