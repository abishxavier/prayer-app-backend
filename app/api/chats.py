from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.ws.manager import manager

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.chat import Chat, ChatType
from app.models.chat_member import ChatMember, MemberRole
from app.models.message import Message
from app.schemas.chat import ChatCreate, ChatOut, ChatMemberAdd, ChatMemberOut
from app.schemas.message import MessageCreate, MessageOut, MessageUpdate

router = APIRouter()


@router.post("/chats", response_model=ChatOut)
def create_chat(payload: ChatCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]

    chat = Chat(name=payload.name, type=payload.type, created_by=user_id)
    db.add(chat)
    db.commit()
    db.refresh(chat)

    # Creator automatically becomes an admin member
    membership = ChatMember(chat_id=chat.id, user_id=user_id, role=MemberRole.admin)
    db.add(membership)
    db.commit()

    return chat


@router.get("/chats", response_model=List[ChatOut])
def list_my_chats(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]

    chat_ids = db.query(ChatMember.chat_id).filter(ChatMember.user_id == user_id).subquery()
    chats = db.query(Chat).filter(Chat.id.in_(chat_ids)).all()
    
    result = []
    from app.models.user import User
    
    for chat in chats:
        chat_dict = {
            "id": chat.id,
            "name": chat.name,
            "type": chat.type,
            "created_by": chat.created_by,
            "created_at": chat.created_at,
            "other_member_name": None,
            "other_member_image": None,
        }
        
        if chat.type == ChatType.direct or chat.type == "direct" or chat.type.value == "direct":
            other_member = db.query(ChatMember).filter(
                ChatMember.chat_id == chat.id, 
                ChatMember.user_id != user_id
            ).first()
            if other_member:
                other_user = db.query(User).filter(User.id == other_member.user_id).first()
                if other_user:
                    chat_dict["other_member_name"] = other_user.name
                    chat_dict["other_member_image"] = other_user.profile_image
                    chat_dict["other_member_phone"] = other_user.phone
                    chat_dict["other_member_last_seen"] = other_user.last_seen
                    
        latest_message = db.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.desc()).first()
        chat_dict["last_message_at"] = latest_message.created_at if latest_message else chat.created_at
        
        result.append(chat_dict)
        
    result.sort(key=lambda x: x["last_message_at"], reverse=True)
    return result


def _verify_membership(db: Session, chat_id: str, user_id: str):
    membership = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this chat")
    return membership


@router.post("/chats/{chat_id}/members", response_model=ChatMemberOut)
def add_member(chat_id: str, payload: ChatMemberAdd, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    existing = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == payload.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this chat")

    membership = ChatMember(chat_id=chat_id, user_id=payload.user_id, role=payload.role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.get("/chats/{chat_id}/members", response_model=List[ChatMemberOut])
def get_members(chat_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    from app.models.user import User

    members = (
        db.query(ChatMember, User.name, User.phone, User.profile_image)
        .join(User, ChatMember.user_id == User.id)
        .filter(ChatMember.chat_id == chat_id)
        .all()
    )
    
    result = []
    for member, name, phone, profile_image in members:
        member_dict = {
            "id": member.id,
            "chat_id": member.chat_id,
            "user_id": member.user_id,
            "role": member.role,
            "joined_at": member.joined_at,
            "user_name": name,
            "user_phone": phone,
            "user_profile_image": profile_image,
        }
        result.append(member_dict)

    return result


@router.get("/chats/{chat_id}/messages", response_model=List[MessageOut])
def get_messages(chat_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    from app.models.user import User

    messages = (
        db.query(Message, User.name, User.profile_image, User.phone)
        .join(User, Message.sender_id == User.id)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    result = []
    for msg, name, profile_image, phone in messages:
        msg_dict = {
            "id": msg.id,
            "chat_id": msg.chat_id,
            "sender_id": msg.sender_id,
            "content": msg.content if not msg.is_deleted else "This message was deleted",
            "message_type": msg.message_type,
            "is_edited": msg.is_edited,
            "is_deleted": msg.is_deleted,
            "is_read": msg.is_read,
            "created_at": msg.created_at,
            "sender_name": name,
            "sender_image": profile_image,
            "sender_phone": phone,
        }
        result.append(msg_dict)
        
    return list(reversed(result))  # return oldest-first for natural chat reading order


@router.post("/chats/{chat_id}/messages", response_model=MessageOut)
def send_message(chat_id: str, payload: MessageCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    message = Message(
        chat_id=chat_id,
        sender_id=user_id,
        content=payload.content,
        message_type=payload.message_type,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # fetch sender info
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()

    import asyncio
    from app.services.fcm import send_push_notification
    from app.models.chat import Chat
    
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    chat_name = chat.name if chat and chat.name else "JIPF Chat"

    async def notify_members():
        # broadcast WebSocket
        await manager.broadcast(chat_id, {
            "type": "message",
            "data": {
                "id": str(message.id),
                "chat_id": str(chat_id),
                "sender_id": str(user_id),
                "content": message.content,
                "message_type": message.message_type.value,
                "is_edited": message.is_edited,
                "is_deleted": message.is_deleted,
                "is_read": message.is_read,
                "created_at": message.created_at.isoformat(),
                "sender_name": user.name if user else None,
                "sender_image": user.profile_image if user else None,
                "sender_phone": user.phone if user else None,
            }
        })

        # send push notification to all other members
        members = db.query(ChatMember).filter(ChatMember.chat_id == chat_id, ChatMember.user_id != user_id).all()
        for member in members:
            member_user = db.query(User).filter(User.id == member.user_id).first()
            if member_user and member_user.device_token:
                title = f"{user.name if user else 'Someone'} ({chat_name})" if chat and chat.type.value == 'group' else (user.name if user else 'New Message')
                send_push_notification(
                    token=member_user.device_token,
                    title=title,
                    body=message.content,
                    data={"chat_id": chat_id, "type": "message"}
                )

    asyncio.create_task(notify_members())
    
    return message


@router.put("/chats/{chat_id}/messages/{message_id}", response_model=MessageOut)
def update_message(chat_id: str, message_id: str, payload: MessageUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message.sender_id != user_id:
        raise HTTPException(status_code=403, detail="You can only edit your own messages")

    if payload.content is not None:
        message.content = payload.content
        message.is_edited = True
    
    if payload.is_deleted is not None:
        message.is_deleted = payload.is_deleted

    db.commit()
    db.refresh(message)
    
    # Broadcast edit/delete
    import asyncio
    asyncio.create_task(manager.broadcast(chat_id, {
        "type": "message_updated",
        "data": {
            "id": str(message.id),
            "content": message.content,
            "is_edited": message.is_edited,
            "is_deleted": message.is_deleted,
        }
    }))
    
    return message

@router.delete("/chats/{chat_id}/messages/{message_id}")
def delete_message(chat_id: str, message_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message.sender_id != user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own messages")

    message.is_deleted = True
    db.commit()
    
    import asyncio
    asyncio.create_task(manager.broadcast(chat_id, {
        "type": "message_deleted",
        "data": {"id": str(message.id)}
    }))
    
    return {"status": "deleted"}

@router.post("/chats/{chat_id}/read")
def mark_messages_read(chat_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    # Mark all messages sent by OTHERS in this chat as read
    updated = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.sender_id != user_id,
        Message.is_read == False
    ).update({"is_read": True})
    
    db.commit()

    if updated > 0:
        import asyncio
        asyncio.create_task(manager.broadcast(chat_id, {
            "type": "messages_read",
            "reader_id": user_id
        }))

    return {"status": "success"}