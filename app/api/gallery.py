from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.gallery import GalleryItem
from app.models.user import User
import uuid

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class GalleryItemCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image_data: str          # base64 data URL or remote https:// URL
    is_featured: bool = False
    sort_order: int = 0


class GalleryItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_featured: Optional[bool] = None
    sort_order: Optional[int] = None


class GalleryItemOut(BaseModel):
    id: str
    title: Optional[str]
    description: Optional[str]
    image_data: str
    uploaded_by: str
    uploader_name: Optional[str]
    is_featured: bool
    sort_order: int
    created_at: str

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_admin(user: User) -> bool:
    """Any user whose name is in this list is considered an admin.
    You can expand this by adding an is_admin column to the User model later.
    For now admins are identified by email.
    """
    admin_emails = [
        # Add your admin emails here, e.g.:
        # "yourname@gmail.com",
    ]
    return user.email in admin_emails or True  # TODO: restrict after initial setup


def _item_to_dict(item: GalleryItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "image_data": item.image_data,
        "uploaded_by": item.uploaded_by,
        "uploader_name": item.uploader_name,
        "is_featured": item.is_featured,
        "sort_order": item.sort_order,
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/gallery")
def list_gallery(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Returns all gallery items, featured first, then sorted by sort_order desc, then newest first."""
    items = (
        db.query(GalleryItem)
        .order_by(
            GalleryItem.is_featured.desc(),
            GalleryItem.sort_order.desc(),
            GalleryItem.created_at.desc(),
        )
        .all()
    )
    return [_item_to_dict(i) for i in items]


@router.post("/gallery")
def add_gallery_item(
    payload: GalleryItemCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload a new gallery image. Any logged-in user can upload (admin restriction can be added later)."""
    user = db.query(User).filter(User.firebase_uid == current_user["uid"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    item = GalleryItem(
        id=str(uuid.uuid4()),
        title=payload.title,
        description=payload.description,
        image_data=payload.image_data,
        uploaded_by=user.id,
        uploader_name=user.name,
        is_featured=payload.is_featured,
        sort_order=payload.sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_to_dict(item)


@router.patch("/gallery/{item_id}")
def update_gallery_item(
    item_id: str,
    payload: GalleryItemUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update caption, featured status, or sort order. Only the uploader can edit."""
    user = db.query(User).filter(User.firebase_uid == current_user["uid"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    item = db.query(GalleryItem).filter(GalleryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Gallery item not found")

    if item.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own gallery items")

    if payload.title is not None:
        item.title = payload.title
    if payload.description is not None:
        item.description = payload.description
    if payload.is_featured is not None:
        item.is_featured = payload.is_featured
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order

    db.commit()
    db.refresh(item)
    return _item_to_dict(item)


@router.delete("/gallery/{item_id}")
def delete_gallery_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a gallery item. Only the uploader can delete their own items."""
    user = db.query(User).filter(User.firebase_uid == current_user["uid"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    item = db.query(GalleryItem).filter(GalleryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Gallery item not found")

    if item.uploaded_by != user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own gallery items")

    db.delete(item)
    db.commit()
    return {"success": True}
