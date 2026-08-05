from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.prayer_request import PrayerRequest
from app.models.prayer_response import PrayerResponse
from app.schemas.prayer import (
    PrayerRequestCreate, PrayerRequestOut, PrayerRequestUpdate,
    PrayerResponseCreate, PrayerResponseOut
)

router = APIRouter()


@router.post("/prayers", response_model=PrayerRequestOut)
def create_prayer(payload: PrayerRequestCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]

    prayer = PrayerRequest(
        user_id=user_id,
        content=payload.content,
        is_anonymous=payload.is_anonymous,
    )
    db.add(prayer)
    db.commit()
    db.refresh(prayer)
    return prayer


@router.get("/prayers", response_model=List[PrayerRequestOut])
def list_prayers(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    prayers = (
        db.query(PrayerRequest)
        .order_by(PrayerRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return prayers


def _get_prayer_or_404(db: Session, prayer_id: str) -> PrayerRequest:
    prayer = db.query(PrayerRequest).filter(PrayerRequest.id == prayer_id).first()
    if not prayer:
        raise HTTPException(status_code=404, detail="Prayer request not found")
    return prayer


@router.patch("/prayers/{prayer_id}", response_model=PrayerRequestOut)
def update_prayer_status(prayer_id: str, payload: PrayerRequestUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    prayer = _get_prayer_or_404(db, prayer_id)

    if prayer.user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the author can update this prayer request")

    prayer.status = payload.status
    db.commit()
    db.refresh(prayer)
    return prayer


@router.post("/prayers/{prayer_id}/responses", response_model=PrayerResponseOut)
def respond_to_prayer(prayer_id: str, payload: PrayerResponseCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    _get_prayer_or_404(db, prayer_id)

    response = PrayerResponse(
        prayer_request_id=prayer_id,
        user_id=user_id,
        response_type=payload.response_type,
        content=payload.content,
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


@router.get("/prayers/{prayer_id}/responses", response_model=List[PrayerResponseOut])
def list_prayer_responses(prayer_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_prayer_or_404(db, prayer_id)

    responses = (
        db.query(PrayerResponse)
        .filter(PrayerResponse.prayer_request_id == prayer_id)
        .order_by(PrayerResponse.created_at.asc())
        .all()
    )
    return responses