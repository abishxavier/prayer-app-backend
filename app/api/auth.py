from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import get_db
from app.core.security import verify_firebase_token, create_access_token
from app.schemas.auth import LoginRequest, LoginResponse
from app.models.user import User

router = APIRouter()


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

    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        name=user.name,
        email=user.email,
    )