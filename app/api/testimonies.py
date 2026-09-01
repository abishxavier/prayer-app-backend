from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.testimony import Testimony, TestimonyLike
from app.models.user import User
from app.schemas.testimony import TestimonyCreate, TestimonyUpdate, TestimonyOut

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
        image_url=payload.image_url,
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


@router.put("/testimonies/{testimony_id}", response_model=TestimonyOut)
def update_testimony(
    testimony_id: str,
    payload: TestimonyUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    testimony = db.query(Testimony).filter(Testimony.id == testimony_id).first()
    if not testimony:
        raise HTTPException(status_code=404, detail="Testimony not found")

    # Author check: only creator can edit their testimony
    if testimony.user_id != user_id:
        raise HTTPException(status_code=403, detail="You can only edit your own testimony")

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        testimony.title = title

    if payload.content is not None:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        testimony.content = content

    if payload.image_url is not None:
        # If passed as empty string or "CLEAR", set to None, else store URL/base64
        testimony.image_url = None if payload.image_url in ("", "CLEAR") else payload.image_url

    db.commit()
    db.refresh(testimony)
    return testimony


@router.post("/testimonies/{testimony_id}/like")
def like_testimony(
    testimony_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    testimony = db.query(Testimony).filter(Testimony.id == testimony_id).first()
    if not testimony:
        raise HTTPException(status_code=404, detail="Testimony not found")

    # Check if user already liked this testimony
    existing_like = db.query(TestimonyLike).filter(
        TestimonyLike.testimony_id == testimony_id,
        TestimonyLike.user_id == user_id
    ).first()

    if existing_like:
        # Unlike: remove the like record and decrement count
        db.delete(existing_like)
        testimony.likes = max((testimony.likes or 1) - 1, 0)
        is_liked = False
    else:
        # Like: add a like record and increment count
        new_like = TestimonyLike(testimony_id=testimony_id, user_id=user_id)
        db.add(new_like)
        testimony.likes = (testimony.likes or 0) + 1
        is_liked = True

    db.commit()
    db.refresh(testimony)

    return {
        "id": testimony.id,
        "user_id": testimony.user_id,
        "user_name": testimony.user_name,
        "user_image": testimony.user_image,
        "title": testimony.title,
        "content": testimony.content,
        "image_url": testimony.image_url,
        "likes": testimony.likes,
        "shares": testimony.shares,
        "created_at": testimony.created_at.isoformat() if testimony.created_at else None,
        "is_liked_by_me": is_liked,
    }


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
