from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.testimony import Testimony
from app.models.user import User
from app.schemas.testimony import TestimonyCreate, TestimonyOut

router = APIRouter()


@router.post("/testimonies", response_model=TestimonyOut)
def create_testimony(
    payload: TestimonyCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    title = payload.title.strip()
    content = payload.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required")

    testimony = Testimony(
        user_id=user_id,
        user_name=user.name or "Prayer Member",
        user_image=user.profile_image,
        title=title,
        content=content,
        likes=0,
        shares=0
    )
    db.add(testimony)
    db.commit()
    db.refresh(testimony)
    return testimony


@router.get("/testimonies", response_model=List[TestimonyOut])
def get_testimonies(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Return all testimonies sorted with newest first
    testimonies = db.query(Testimony).order_by(Testimony.created_at.desc()).all()
    return testimonies


@router.post("/testimonies/{testimony_id}/like", response_model=TestimonyOut)
def like_testimony(
    testimony_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    testimony = db.query(Testimony).filter(Testimony.id == testimony_id).first()
    if not testimony:
        raise HTTPException(status_code=404, detail="Testimony not found")

    testimony.likes = (testimony.likes or 0) + 1
    db.commit()
    db.refresh(testimony)
    return testimony


@router.post("/testimonies/{testimony_id}/share", response_model=TestimonyOut)
def share_testimony(
    testimony_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    testimony = db.query(Testimony).filter(Testimony.id == testimony_id).first()
    if not testimony:
        raise HTTPException(status_code=404, detail="Testimony not found")

    testimony.shares = (testimony.shares or 0) + 1
    db.commit()
    db.refresh(testimony)
    return testimony


@router.delete("/testimonies/{testimony_id}")
def delete_testimony(
    testimony_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    testimony = db.query(Testimony).filter(Testimony.id == testimony_id).first()
    if not testimony:
        raise HTTPException(status_code=404, detail="Testimony not found")

    if testimony.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this testimony")

    db.delete(testimony)
    db.commit()
    return {"status": "success", "message": "Testimony deleted"}
