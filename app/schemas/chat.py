from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.chat import ChatType
from app.models.chat_member import MemberRole


class ChatCreate(BaseModel):
    name: Optional[str] = None
    type: ChatType = ChatType.direct


class ChatOut(BaseModel):
    id: str
    name: Optional[str]
    type: ChatType
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMemberAdd(BaseModel):
    user_id: str
    role: MemberRole = MemberRole.member


class ChatMemberOut(BaseModel):
    id: str
    chat_id: str
    user_id: str
    role: MemberRole
    joined_at: datetime

    class Config:
        from_attributes = True