from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.chat import ChatType
from app.models.chat_member import MemberRole


class ChatCreate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: ChatType = ChatType.direct
    group_image: Optional[str] = None


class ChatUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    group_image: Optional[str] = None
    only_admins_can_post: Optional[bool] = None
    only_admins_can_edit_info: Optional[bool] = None
    only_admins_can_add_members: Optional[bool] = None
    allow_prayer_requests: Optional[bool] = None
    allow_calls: Optional[bool] = None
    pinned_message: Optional[str] = None


class ChatOut(BaseModel):
    id: str
    name: Optional[str]
    description: Optional[str] = None
    group_image: Optional[str] = None
    type: ChatType
    created_by: str
    created_at: datetime
    only_admins_can_post: Optional[bool] = False
    only_admins_can_edit_info: Optional[bool] = False
    only_admins_can_add_members: Optional[bool] = False
    allow_prayer_requests: Optional[bool] = True
    allow_calls: Optional[bool] = True
    pinned_message: Optional[str] = None
    my_role: Optional[str] = "member"
    other_member_id: Optional[str] = None
    other_member_name: Optional[str] = None
    other_member_phone: Optional[str] = None
    other_member_image: Optional[str] = None
    other_member_last_seen: Optional[datetime] = None
    last_message_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatMemberAdd(BaseModel):
    user_id: str
    role: MemberRole = MemberRole.member


class ChatMemberRoleUpdate(BaseModel):
    role: MemberRole


class ChatMemberOut(BaseModel):
    id: str
    chat_id: str
    user_id: str
    role: MemberRole
    joined_at: datetime
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_profile_image: Optional[str] = None

    class Config:
        from_attributes = True