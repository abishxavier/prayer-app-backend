from pydantic import BaseModel


class LoginRequest(BaseModel):
    id_token: str  # Firebase ID token from the Flutter app


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    email: str