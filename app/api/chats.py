from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from app.ws.manager import manager

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.chat import Chat, ChatType
from app.models.chat_member import ChatMember, MemberRole
from app.models.message import Message
from app.models.blocked_user import BlockedUser
from app.models.user import User
from app.models.call import ScheduledCall
from app.schemas.chat import (
    ChatCreate, ChatOut, ChatMemberAdd, ChatMemberOut, ChatUpdate, ChatMemberRoleUpdate
)
from app.schemas.message import MessageCreate, MessageOut, MessageUpdate
from app.services.fcm import send_push_notification

router = APIRouter()


@router.post("/chats", response_model=ChatOut)
async def create_chat(payload: ChatCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]

    # If it is a direct chat and target_user_id is provided, check for existing chat
    if (payload.type == ChatType.direct or payload.type == "direct") and payload.target_user_id:
        # Check if direct chat already exists where both user_id and target_user_id are members
        user_chats = db.query(ChatMember.chat_id).join(Chat, Chat.id == ChatMember.chat_id).filter(
            Chat.type == ChatType.direct,
            ChatMember.user_id == user_id
        ).subquery()

        existing_member = db.query(ChatMember).filter(
            ChatMember.chat_id.in_(user_chats),
            ChatMember.user_id == payload.target_user_id
        ).first()

        if existing_member:
            chat_out = db.query(Chat).filter(Chat.id == existing_member.chat_id).first()
            my_membership = db.query(ChatMember).filter(
                ChatMember.chat_id == chat_out.id,
                ChatMember.user_id == user_id
            ).first()
            setattr(chat_out, "my_role", my_membership.role.value if my_membership and hasattr(my_membership.role, 'value') else "member")
            return chat_out

        # Create new direct chat and add both members atomically
        chat = Chat(
            name=payload.name,
            description=payload.description,
            type=payload.type,
            created_by=user_id,
            group_image=payload.group_image,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

        membership_creator = ChatMember(chat_id=chat.id, user_id=user_id, role=MemberRole.admin)
        membership_target = ChatMember(chat_id=chat.id, user_id=payload.target_user_id, role=MemberRole.member)
        db.add(membership_creator)
        db.add(membership_target)
        db.commit()

        chat_out = db.query(Chat).filter(Chat.id == chat.id).first()
        setattr(chat_out, "my_role", "admin")
        return chat_out

    # Default creation logic (e.g. for group chats or if target_user_id is not specified)
    chat = Chat(
        name=payload.name,
        description=payload.description,
        type=payload.type,
        created_by=user_id,
        group_image=payload.group_image,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    # Creator automatically becomes an admin member
    membership = ChatMember(chat_id=chat.id, user_id=user_id, role=MemberRole.admin)
    db.add(membership)
    db.commit()

    chat_out = db.query(Chat).filter(Chat.id == chat.id).first()
    setattr(chat_out, "my_role", "admin")
    return chat_out


def _verify_membership(db: Session, chat_id: str, user_id: str):
    membership = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this chat")
    return membership


@router.get("/chats/{chat_id}", response_model=ChatOut)
async def get_chat(chat_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat_dict = {
        "id": chat.id,
        "name": chat.name,
        "description": chat.description,
        "type": chat.type,
        "created_by": chat.created_by,
        "created_at": chat.created_at,
        "group_image": chat.group_image,
        "only_admins_can_post": chat.only_admins_can_post,
        "only_admins_can_edit_info": chat.only_admins_can_edit_info,
        "only_admins_can_add_members": chat.only_admins_can_add_members,
        "allow_prayer_requests": chat.allow_prayer_requests,
        "allow_calls": chat.allow_calls,
        "pinned_message": chat.pinned_message,
        "my_role": membership.role.value if hasattr(membership.role, 'value') else str(membership.role),
        "other_member_id": None,
        "other_member_name": None,
        "other_member_image": None,
        "other_member_phone": None,
        "other_member_last_seen": None,
        "other_member_status": None,
    }

    if chat.type == ChatType.direct or chat.type == "direct" or getattr(chat.type, 'value', '') == "direct":
        other_member = db.query(ChatMember).filter(
            ChatMember.chat_id == chat.id,
            ChatMember.user_id != user_id
        ).first()
        if other_member:
            other_user = db.query(User).filter(User.id == other_member.user_id).first()
            if other_user:
                chat_dict["other_member_id"] = other_user.id
                chat_dict["other_member_name"] = other_user.name
                chat_dict["other_member_image"] = other_user.profile_image
                chat_dict["other_member_phone"] = other_user.phone
                chat_dict["other_member_last_seen"] = other_user.last_seen
                is_live_online = manager.is_online(str(other_user.id))
                chat_dict["other_member_status"] = "online" if is_live_online else (other_user.status or "offline")

    return chat_dict


@router.put("/chats/{chat_id}", response_model=ChatOut)
async def update_chat(chat_id: str, payload: ChatUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    is_admin = (membership.role == MemberRole.admin or membership.role == "admin" or getattr(membership.role, 'value', '') == "admin" or chat.created_by == user_id)

    if chat.type != ChatType.direct and chat.only_admins_can_edit_info and not is_admin:
        raise HTTPException(status_code=403, detail="Only admins can edit this group info")

    actor = db.query(User).filter(User.id == user_id).first()
    actor_name = actor.name if actor else "Member"

    if chat.type != ChatType.direct and chat.type != "direct":
        if payload.name is not None and payload.name != chat.name:
            chat.name = payload.name
            sys_content = f"{actor_name} changed the group subject to \"{payload.name}\""
            sys_msg = Message(chat_id=chat_id, sender_id=user_id, content=sys_content, message_type=MessageType.system)
            db.add(sys_msg)
            db.commit()
            try:
                await manager.broadcast(chat_id, {
                    "type": "new_message",
                    "data": {
                        "id": str(sys_msg.id),
                        "chat_id": chat_id,
                        "sender_id": user_id,
                        "content": sys_content,
                        "message_type": "system",
                        "sender_name": actor_name,
                        "created_at": sys_msg.created_at.isoformat() if sys_msg.created_at else None,
                    }
                })
            except Exception:
                pass
        elif payload.group_image is not None and payload.group_image != chat.group_image:
            chat.group_image = payload.group_image
            sys_content = f"{actor_name} changed the group profile photo"
            sys_msg = Message(chat_id=chat_id, sender_id=user_id, content=sys_content, message_type=MessageType.system)
            db.add(sys_msg)
            db.commit()
            try:
                await manager.broadcast(chat_id, {
                    "type": "new_message",
                    "data": {
                        "id": str(sys_msg.id),
                        "chat_id": chat_id,
                        "sender_id": user_id,
                        "content": sys_content,
                        "message_type": "system",
                        "sender_name": actor_name,
                        "created_at": sys_msg.created_at.isoformat() if sys_msg.created_at else None,
                    }
                })
            except Exception:
                pass
        elif payload.name is not None:
            chat.name = payload.name
    else:
        if payload.name is not None:
            chat.name = payload.name

    if payload.description is not None:
        chat.description = payload.description
    if payload.group_image is not None:
        chat.group_image = payload.group_image

    # Admin only permission settings
    if is_admin:
        if payload.only_admins_can_post is not None:
            chat.only_admins_can_post = payload.only_admins_can_post
        if payload.only_admins_can_edit_info is not None:
            chat.only_admins_can_edit_info = payload.only_admins_can_edit_info
        if payload.only_admins_can_add_members is not None:
            chat.only_admins_can_add_members = payload.only_admins_can_add_members
        if payload.allow_prayer_requests is not None:
            chat.allow_prayer_requests = payload.allow_prayer_requests
        if payload.allow_calls is not None:
            chat.allow_calls = payload.allow_calls
        if payload.pinned_message is not None:
            chat.pinned_message = payload.pinned_message

    db.add(chat)
    db.commit()
    db.refresh(chat)

    try:
        await manager.broadcast(chat_id, {
            "type": "chat_updated",
            "data": {
                "id": chat.id,
                "name": chat.name,
                "description": chat.description,
                "group_image": chat.group_image,
                "only_admins_can_post": chat.only_admins_can_post,
                "pinned_message": chat.pinned_message,
            }
        })
    except Exception:
        pass

    setattr(chat, "my_role", membership.role.value if hasattr(membership.role, 'value') else str(membership.role))
    return chat


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    is_admin = (membership.role == MemberRole.admin or membership.role == "admin" or getattr(membership.role, 'value', '') == "admin" or chat.created_by == user_id)
    if not is_admin and chat.type != ChatType.direct:
        raise HTTPException(status_code=403, detail="Only admins can delete this group")

    # Delete linked scheduled calls, messages, members and the chat itself
    db.query(ScheduledCall).filter(ScheduledCall.chat_id == chat_id).delete()
    db.query(Message).filter(Message.chat_id == chat_id).delete()
    db.query(ChatMember).filter(ChatMember.chat_id == chat_id).delete()
    db.query(Chat).filter(Chat.id == chat_id).delete()
    db.commit()

    try:
        await manager.broadcast(chat_id, {
            "type": "chat_deleted",
            "chat_id": chat_id
        })
    except Exception:
        pass

    return {"status": "success", "message": "Chat deleted"}


@router.get("/chats", response_model=List[ChatOut])
async def list_my_chats(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]

    # 1. Fetch user's memberships in bulk
    my_memberships = db.query(ChatMember).filter(ChatMember.user_id == user_id).all()
    chat_ids = [m.chat_id for m in my_memberships]
    
    if not chat_ids:
        return []

    # 2. Fetch chats in bulk
    chats = db.query(Chat).filter(Chat.id.in_(chat_ids)).all()
    
    # 3. Fetch all memberships in these chats in bulk
    all_members = db.query(ChatMember).filter(ChatMember.chat_id.in_(chat_ids)).all()
    
    # Group memberships by chat_id
    from collections import defaultdict
    members_by_chat = defaultdict(list)
    for m in all_members:
        members_by_chat[m.chat_id].append(m)

    # 4. Find and fetch all "other users" for direct chats in bulk
    other_user_ids = set()
    for cid in chat_ids:
        for m in members_by_chat[cid]:
            if m.user_id != user_id:
                other_user_ids.add(m.user_id)
                
    other_users = db.query(User).filter(User.id.in_(other_user_ids)).all() if other_user_ids else []
    user_map = {u.id: u for u in other_users}

    # 5. Fetch latest messages for each chat in bulk
    from sqlalchemy import func
    subq = db.query(
        Message.chat_id,
        func.max(Message.created_at).label("max_created_at")
    ).filter(Message.chat_id.in_(chat_ids)).group_by(Message.chat_id).subquery()
    
    latest_messages = db.query(Message).join(
        subq,
        (Message.chat_id == subq.c.chat_id) & (Message.created_at == subq.c.max_created_at)
    ).all()
    latest_msg_map = {m.chat_id: m for m in latest_messages}

    # 6. Fetch unread counts for each chat in bulk
    unread_counts = db.query(
        Message.chat_id,
        func.count(Message.id).label("cnt")
    ).filter(
        Message.chat_id.in_(chat_ids),
        Message.sender_id != user_id,
        Message.is_read == False
    ).group_by(Message.chat_id).all()
    unread_map = {str(row.chat_id): row.cnt for row in unread_counts}

    result = []
    
    for chat in chats:
        # Find current user's membership role
        my_role = "member"
        for m in members_by_chat[chat.id]:
            if m.user_id == user_id:
                my_role = m.role.value if hasattr(m.role, 'value') else str(m.role)
                break

        latest_message = latest_msg_map.get(chat.id)
        last_msg_at = latest_message.created_at if latest_message else chat.created_at
        last_content = None
        if latest_message:
            if latest_message.is_deleted:
                last_content = "This message was deleted"
            elif latest_message.content and latest_message.content.startswith("data:image"):
                last_content = "📷 Photo"
            elif latest_message.content and latest_message.content.startswith("🎙️"):
                last_content = "🎙️ Voice note"
            else:
                last_content = latest_message.content

        chat_dict = {
            "id": chat.id,
            "name": chat.name,
            "description": chat.description,
            "type": chat.type,
            "created_by": chat.created_by,
            "created_at": chat.created_at,
            "group_image": chat.group_image,
            "only_admins_can_post": chat.only_admins_can_post,
            "only_admins_can_edit_info": chat.only_admins_can_edit_info,
            "only_admins_can_add_members": chat.only_admins_can_add_members,
            "allow_prayer_requests": chat.allow_prayer_requests,
            "allow_calls": chat.allow_calls,
            "pinned_message": chat.pinned_message,
            "my_role": my_role,
            "other_member_id": None,
            "other_member_name": None,
            "other_member_image": None,
            "other_member_phone": None,
            "other_member_last_seen": None,
            "other_member_status": None,
            "last_message_at": last_msg_at,
            "last_message_content": last_content,
            "unread_count": unread_map.get(str(chat.id), 0),
        }
        
        if chat.type == ChatType.direct or chat.type == "direct" or getattr(chat.type, 'value', '') == "direct":
            # Find the other member in this chat
            other_m = None
            for m in members_by_chat[chat.id]:
                if m.user_id != user_id:
                    other_m = m
                    break
            
            if other_m:
                other_user = user_map.get(other_m.user_id)
                if other_user:
                    chat_dict["other_member_id"] = other_user.id
                    chat_dict["other_member_name"] = other_user.name
                    chat_dict["other_member_image"] = other_user.profile_image
                    chat_dict["other_member_phone"] = other_user.phone
                    chat_dict["other_member_last_seen"] = other_user.last_seen
                    is_live_online = manager.is_online(str(other_user.id))
                    chat_dict["other_member_status"] = "online" if is_live_online else (other_user.status or "offline")
                    
        result.append(chat_dict)
        
    def _safe_sort_key(item):
        dt = item.get("last_message_at") or item.get("created_at")
        if dt is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if getattr(dt, "tzinfo", None) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    result.sort(key=_safe_sort_key, reverse=True)

    # Deduplicate direct chats by other member ID and phone number to never show duplicate contacts
    deduped_result = []
    seen_direct_keys = set()

    for item in result:
        is_group = (item["type"] == ChatType.group or item["type"] == "group" or getattr(item["type"], "value", "") == "group")
        if not is_group:
            other_id = item.get("other_member_id")
            other_phone = item.get("other_member_phone")
            clean_phone = "".join(c for c in (other_phone or "") if c.isdigit()) if other_phone else None
            
            # Key by other user id or cleaned phone
            key_id = f"user_{other_id}" if other_id else None
            key_phone = f"phone_{clean_phone[-10:]}" if clean_phone and len(clean_phone) >= 7 else None

            if (key_id and key_id in seen_direct_keys) or (key_phone and key_phone in seen_direct_keys):
                continue

            if key_id:
                seen_direct_keys.add(key_id)
            if key_phone:
                seen_direct_keys.add(key_phone)

        deduped_result.append(item)

    return deduped_result


@router.post("/chats/{chat_id}/members", response_model=ChatMemberOut)
async def add_member(chat_id: str, payload: ChatMemberAdd, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    my_membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat and chat.only_admins_can_add_members:
        is_admin = (my_membership.role == MemberRole.admin or my_membership.role == "admin" or getattr(my_membership.role, 'value', '') == "admin" or chat.created_by == user_id)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only admins can add members to this group")

    existing = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == payload.user_id
    ).first()
    if existing:
        return existing

    membership = ChatMember(chat_id=chat_id, user_id=payload.user_id, role=payload.role)
    db.add(membership)
    db.commit()
    db.refresh(membership)

    actor = db.query(User).filter(User.id == user_id).first()
    target = db.query(User).filter(User.id == payload.user_id).first()
    actor_name = actor.name if actor else "Member"
    target_name = target.name if target else "Member"
    sys_content = f"{actor_name} added {target_name}"

    sys_msg = Message(
        chat_id=chat_id,
        sender_id=user_id,
        content=sys_content,
        message_type=MessageType.system,
    )
    db.add(sys_msg)
    db.commit()
    db.refresh(sys_msg)

    try:
        await manager.broadcast(chat_id, {
            "type": "new_message",
            "data": {
                "id": str(sys_msg.id),
                "chat_id": chat_id,
                "sender_id": user_id,
                "content": sys_content,
                "message_type": "system",
                "sender_name": actor_name,
                "created_at": sys_msg.created_at.isoformat() if sys_msg.created_at else None,
            }
        })
    except Exception:
        pass

    return membership


@router.put("/chats/{chat_id}/members/{target_user_id}/role")
async def update_member_role(chat_id: str, target_user_id: str, payload: ChatMemberRoleUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    my_membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    is_admin = (my_membership.role == MemberRole.admin or my_membership.role == "admin" or getattr(my_membership.role, 'value', '') == "admin" or chat.created_by == user_id)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only admins can change member roles")

    target_membership = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == target_user_id
    ).first()
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found in group")

    # Prevent dismissing the group creator
    if chat and chat.created_by == target_user_id and payload.role != MemberRole.admin and payload.role != "admin":
        raise HTTPException(status_code=400, detail="The group creator cannot be dismissed as admin")

    target_membership.role = payload.role
    db.commit()

    actor = db.query(User).filter(User.id == user_id).first()
    target = db.query(User).filter(User.id == target_user_id).first()
    actor_name = actor.name if actor else "Admin"
    target_name = target.name if target else "Member"

    is_new_admin = (payload.role == MemberRole.admin or payload.role == "admin" or getattr(payload.role, 'value', '') == "admin")
    sys_content = f"{actor_name} made {target_name} an admin 👑" if is_new_admin else f"{actor_name} dismissed {target_name} as admin"

    sys_msg = Message(
        chat_id=chat_id,
        sender_id=user_id,
        content=sys_content,
        message_type=MessageType.system,
    )
    db.add(sys_msg)
    db.commit()
    db.refresh(sys_msg)

    try:
        await manager.broadcast(chat_id, {
            "type": "message",
            "data": {
                "id": str(sys_msg.id),
                "chat_id": chat_id,
                "sender_id": user_id,
                "content": sys_content,
                "message_type": "system",
                "sender_name": actor_name,
                "created_at": sys_msg.created_at.isoformat() if sys_msg.created_at else None,
            }
        })
    except Exception:
        pass

    role_val = payload.role.value if hasattr(payload.role, 'value') else str(payload.role)
    return {"status": "success", "user_id": target_user_id, "role": role_val}


@router.delete("/chats/{chat_id}/members/{target_user_id}")
async def remove_member(chat_id: str, target_user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    my_membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    is_admin = (my_membership.role == MemberRole.admin or my_membership.role == "admin" or getattr(my_membership.role, 'value', '') == "admin" or chat.created_by == user_id)

    # A user can remove themselves (Leave group), but removing others requires admin privilege
    if target_user_id != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Only admins can remove other members")

    target_membership = db.query(ChatMember).filter(
        ChatMember.chat_id == chat_id, ChatMember.user_id == target_user_id
    ).first()
    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found")

    actor = db.query(User).filter(User.id == user_id).first()
    target = db.query(User).filter(User.id == target_user_id).first()
    actor_name = actor.name if actor else "Member"
    target_name = target.name if target else "Member"
    sys_content = f"{target_name} left the group" if target_user_id == user_id else f"{actor_name} removed {target_name}"

    db.delete(target_membership)
    db.commit()

    sys_msg = Message(
        chat_id=chat_id,
        sender_id=user_id,
        content=sys_content,
        message_type=MessageType.system,
    )
    db.add(sys_msg)
    db.commit()
    db.refresh(sys_msg)

    try:
        await manager.broadcast(chat_id, {
            "type": "new_message",
            "data": {
                "id": str(sys_msg.id),
                "chat_id": chat_id,
                "sender_id": user_id,
                "content": sys_content,
                "message_type": "system",
                "sender_name": actor_name,
                "created_at": sys_msg.created_at.isoformat() if sys_msg.created_at else None,
            }
        })
    except Exception:
        pass

    return {"status": "success", "message": "Member removed"}


@router.get("/chats/{chat_id}/members", response_model=List[ChatMemberOut])
async def get_members(chat_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

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
async def get_messages(chat_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

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
            "content": msg.content if not msg.is_deleted else (msg.content if ("deleted by admin" in (msg.content or "")) else "This message was deleted"),
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
        
    return list(reversed(result))


@router.post("/chats/{chat_id}/messages", response_model=MessageOut)
async def send_message(chat_id: str, payload: MessageCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    my_membership = _verify_membership(db, chat_id, user_id)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat and chat.only_admins_can_post:
        is_admin = (my_membership.role == MemberRole.admin or my_membership.role == "admin" or getattr(my_membership.role, 'value', '') == "admin" or chat.created_by == user_id)
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only admins can send messages in this group")

    # Check if receiver has blocked sender in direct chat
    if chat and (chat.type == ChatType.direct or getattr(chat.type, 'value', '') == 'direct'):
        other_member = db.query(ChatMember).filter(ChatMember.chat_id == chat_id, ChatMember.user_id != user_id).first()
        if other_member:
            is_blocked = db.query(BlockedUser).filter(
                BlockedUser.user_id == other_member.user_id,
                BlockedUser.blocked_user_id == user_id
            ).first()
            if is_blocked:
                raise HTTPException(status_code=403, detail="You cannot send messages to this contact")

    message = Message(
        chat_id=chat_id,
        sender_id=user_id,
        content=payload.content,
        message_type=payload.message_type,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    
    user = db.query(User).filter(User.id == user_id).first()
    chat_name = chat.name if chat and chat.name else "JIPF Chat"

    # Broadcast directly in async event loop
    try:
        await manager.broadcast(chat_id, {
            "type": "message",
            "data": {
                "id": str(message.id),
                "chat_id": str(chat_id),
                "sender_id": str(user_id),
                "content": message.content,
                "message_type": message.message_type.value if hasattr(message.message_type, 'value') else str(message.message_type),
                "is_edited": message.is_edited,
                "is_deleted": message.is_deleted,
                "is_read": message.is_read,
                "created_at": message.created_at.isoformat(),
                "sender_name": user.name if user else None,
                "sender_image": user.profile_image if user else None,
                "sender_phone": user.phone if user else None,
            }
        })
    except Exception:
        pass

    # Push notifications to offline members
    try:
        members = db.query(ChatMember).filter(ChatMember.chat_id == chat_id, ChatMember.user_id != user_id).all()
        for member in members:
            member_user = db.query(User).filter(User.id == member.user_id).first()
            if member_user and member_user.device_token:
                title = f"{user.name if user else 'Someone'} ({chat_name})" if chat and getattr(chat.type, 'value', '') == 'group' else (user.name if user else 'New Message')
                body_preview = "📷 Photo" if (message.content and message.content.startswith("data:image")) else ("🎙️ Voice Note" if (message.content and message.content.startswith("🎙️")) else (message.content if len(message.content) < 100 else message.content[:97] + "..."))
                send_push_notification(
                    token=member_user.device_token,
                    title=title,
                    body=body_preview,
                    data={"chat_id": chat_id, "type": "message"}
                )
    except Exception:
        pass

    return {
        "id": str(message.id),
        "chat_id": str(message.chat_id),
        "sender_id": str(message.sender_id),
        "content": message.content,
        "message_type": message.message_type,
        "is_edited": message.is_edited,
        "is_deleted": message.is_deleted,
        "is_read": message.is_read,
        "created_at": message.created_at,
        "sender_name": user.name if user else None,
        "sender_image": user.profile_image if user else None,
        "sender_phone": user.phone if user else None,
    }


@router.put("/chats/{chat_id}/messages/{message_id}", response_model=MessageOut)
async def update_message(chat_id: str, message_id: str, payload: MessageUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    my_membership = _verify_membership(db, chat_id, user_id)

    message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    is_admin = (my_membership.role == MemberRole.admin or my_membership.role == "admin" or getattr(my_membership.role, 'value', '') == "admin" or (chat and chat.created_by == user_id))

    if message.sender_id != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="You can only edit your own messages")

    if payload.content is not None:
        message.content = payload.content
        message.is_edited = True
    
    if payload.is_deleted is not None:
        message.is_deleted = payload.is_deleted

    db.commit()
    db.refresh(message)
    
    try:
        await manager.broadcast(chat_id, {
            "type": "message_updated",
            "data": {
                "id": str(message.id),
                "content": message.content,
                "is_edited": message.is_edited,
                "is_deleted": message.is_deleted,
            }
        })
    except Exception:
        pass
    
    return message


@router.delete("/chats/{chat_id}/messages/{message_id}")
async def delete_message(chat_id: str, message_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    my_membership = _verify_membership(db, chat_id, user_id)

    message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    is_admin = (my_membership.role == MemberRole.admin or my_membership.role == "admin" or getattr(my_membership.role, 'value', '') == "admin" or (chat and chat.created_by == user_id))

    if message.sender_id != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Only sender or admin can delete this message")

    deleted_by_admin = (message.sender_id != user_id and is_admin)
    message.is_deleted = True
    message.content = "This message was deleted by admin" if deleted_by_admin else "This message was deleted"
    db.commit()
    
    try:
        await manager.broadcast(chat_id, {
            "type": "message_deleted",
            "data": {
                "id": str(message.id),
                "is_deleted": True,
                "content": message.content,
                "deleted_by_admin": deleted_by_admin
            }
        })
    except Exception:
        pass
    
    return {"status": "deleted", "content": message.content, "deleted_by_admin": deleted_by_admin}


@router.post("/chats/{chat_id}/read")
async def mark_messages_read(chat_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _verify_membership(db, chat_id, user_id)

    updated = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.sender_id != user_id,
        Message.is_read == False
    ).update({"is_read": True})
    
    db.commit()

    if updated > 0:
        try:
            await manager.broadcast(chat_id, {
                "type": "messages_read",
                "reader_id": user_id
            })
        except Exception:
            pass

    return {"status": "success"}


# ── User Blocking Endpoints ──

@router.post("/users/block/{target_user_id}")
async def block_user(target_user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    if target_user_id == user_id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")

    existing = db.query(BlockedUser).filter(
        BlockedUser.user_id == user_id, BlockedUser.blocked_user_id == target_user_id
    ).first()
    if not existing:
        blocked = BlockedUser(user_id=user_id, blocked_user_id=target_user_id)
        db.add(blocked)
        db.commit()
    return {"status": "success", "message": "User blocked successfully"}


@router.post("/users/unblock/{target_user_id}")
async def unblock_user(target_user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    db.query(BlockedUser).filter(
        BlockedUser.user_id == user_id, BlockedUser.blocked_user_id == target_user_id
    ).delete()
    db.commit()
    return {"status": "success", "message": "User unblocked successfully"}


@router.get("/users/blocked")
async def get_blocked_users(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    blocks = (
        db.query(BlockedUser, User.name, User.phone, User.profile_image)
        .join(User, BlockedUser.blocked_user_id == User.id)
        .filter(BlockedUser.user_id == user_id)
        .all()
    )
    return [
        {
            "id": b.id,
            "blocked_user_id": b.blocked_user_id,
            "name": name,
            "phone": phone,
            "profile_image": profile_image,
            "created_at": b.created_at
        }
        for b, name, phone, profile_image in blocks
    ]