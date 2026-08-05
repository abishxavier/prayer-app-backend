from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.chat import Chat
from app.models.chat_member import ChatMember, MemberRole
from app.models.message import Message
from app.schemas.chat import ChatCreate, ChatOut, ChatMemberAdd, ChatMemberOut
from app.schemas.message import MessageCreate, MessageOut

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
    return chats


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


@router.get("/chats/{chat_id}/messages", response_model=List[MessageOut])
def get_messages(chat_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return list(reversed(messages))  # return oldest-first for natural chat reading order


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
    return message