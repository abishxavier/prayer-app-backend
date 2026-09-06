from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ScheduledCallCreate(BaseModel):
    topic: str
    description: Optional[str] = None
    call_type: str = "Prayer Meeting"
    room_name: Optional[str] = None
    scheduled_at: datetime
    password: Optional[str] = None
    access_type: Optional[str] = "public"
    waiting_room_enabled: Optional[bool] = False
    chat_enabled: Optional[bool] = True
    screen_share_enabled: Optional[bool] = True


class InstantMeetingCreate(BaseModel):
    topic: Optional[str] = "Instant Meeting"
    call_type: Optional[str] = "Video Call"
    password: Optional[str] = None
    access_type: Optional[str] = "public"
    waiting_room_enabled: Optional[bool] = False
    chat_enabled: Optional[bool] = True
    screen_share_enabled: Optional[bool] = True


class ScheduledCallOut(BaseModel):
    id: str
    topic: str
    description: Optional[str] = None
    call_type: Optional[str] = "Prayer Meeting"
    room_name: str
    meeting_code: Optional[str] = None
    access_type: Optional[str] = "public"
    status: Optional[str] = "active"
    waiting_room_enabled: Optional[bool] = False
    chat_enabled: Optional[bool] = True
    screen_share_enabled: Optional[bool] = True
    has_password: Optional[bool] = False
    host_id: str
    host_name: Optional[str] = None
    scheduled_at: datetime
    created_at: datetime
    active_participants_count: Optional[int] = 0
    total_joined_count: Optional[int] = 0
    left_count: Optional[int] = 0
    can_join: Optional[bool] = False
    is_live: Optional[bool] = False
    is_expired: Optional[bool] = False
    minutes_until: Optional[int] = None

    class Config:
        from_attributes = True


class MeetingVerifyResponse(BaseModel):
    room_name: str
    meeting_code: Optional[str] = None
    topic: str
    host_name: str
    host_id: str
    is_current_user_host: bool = False
    can_join: bool = True
    is_ended: bool = False
    requires_password: bool = False
    requires_waiting_room: bool = False
    chat_enabled: bool = True
    screen_share_enabled: bool = True


class MeetingPasswordVerifyRequest(BaseModel):
    room_name_or_code: str
    password: str


class CallLogCreate(BaseModel):
    receiver_id: str
    status: str = "missed"
    call_type: str = "audio"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

class CallLogOut(BaseModel):
    id: str
    caller_id: str
    caller_name: Optional[str] = None
    caller_image: Optional[str] = None
    receiver_id: str
    receiver_name: Optional[str] = None
    receiver_image: Optional[str] = None
    status: str
    call_type: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MeetingIntentionCreate(BaseModel):
    intention: str
    is_private: Optional[bool] = False

class MeetingIntentionUpdate(BaseModel):
    is_featured: Optional[bool] = None
    is_prayed: Optional[bool] = None

class MeetingIntentionOut(BaseModel):
    id: str
    room_name: str
    user_id: str
    user_name: str
    user_image: Optional[str] = None
    intention: str
    is_private: bool = False
    is_featured: bool = False
    is_prayed: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class CallParticipantRegister(BaseModel):
    uid: int
    name: str
    photo: Optional[str] = None
    is_host: bool = False
    is_screen_sharing: Optional[bool] = False
    is_hand_raised: Optional[bool] = False

class CallParticipantOut(BaseModel):
    uid: int
    user_id: str
    name: str
    photo: Optional[str] = None
    is_host: bool = False
    is_screen_sharing: bool = False
    is_hand_raised: bool = False
    last_seen: datetime

    class Config:
        from_attributes = True


class MeetingMessageCreate(BaseModel):
    message: str

class MeetingMessageOut(BaseModel):
    id: str
    room_name: str
    sender_id: str
    sender_name: str
    sender_image: Optional[str] = None
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserReportCreate(BaseModel):
    reported_user_id: str
    reason: str
    meeting_id: Optional[str] = None

class UserReportOut(BaseModel):
    id: str
    reporter_id: str
    reported_user_id: str
    meeting_id: Optional[str] = None
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class BlockedUserCreate(BaseModel):
    blocked_user_id: str

class BlockedUserOut(BaseModel):
    id: str
    user_id: str
    blocked_user_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class WaitingRoomAction(BaseModel):
    room_name: str
    uid: int
    user_id: str
    action: str # admit or reject
