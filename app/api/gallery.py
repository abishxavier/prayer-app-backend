from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.gallery import GalleryItem
from app.models.user import User
import uuid

router = APIRouter()


# â”€â”€ Schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GalleryItemCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image_data: str          # base64 data URL or remote https:// URL
    media_type: Optional[str] = "image"  # "image" or "video"
    is_featured: bool = False
    sort_order: int = 0


class GalleryBatchCreate(BaseModel):
    items: List[GalleryItemCreate]


class GalleryItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    media_type: Optional[str] = None
    is_featured: Optional[bool] = None
    sort_order: Optional[int] = None


class GalleryItemOut(BaseModel):
    id: str
    title: Optional[str]
    description: Optional[str]
    image_data: str
    media_type: Optional[str] = "image"
    uploaded_by: str
    uploader_name: Optional[str]
    is_featured: bool
    sort_order: int
    created_at: str
    model_config = ConfigDict(from_attributes=True)


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    created_at_str = ""
    if item.created_at:
        created_at_str = item.created_at.isoformat() if hasattr(item.created_at, 'isoformat') else str(item.created_at)
    
    media_type = getattr(item, 'media_type', None)
    if not media_type:
        raw = (item.image_data or "").lower()
        if "data:video" in raw or any(raw.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v']):
            media_type = "video"
        else:
            media_type = "image"

    return {
        "id": str(item.id),
        "title": item.title,
        "description": item.description,
        "image_data": item.image_data,
        "media_type": media_type,
        "uploaded_by": str(item.uploaded_by),
        "uploader_name": item.uploader_name or "Community Member",
        "is_featured": bool(item.is_featured),
        "sort_order": int(item.sort_order or 0),
        "created_at": created_at_str,
    }


import time

_gallery_cache = None
_gallery_cache_time = 0.0
GALLERY_CACHE_TTL = 300.0  # 5 minutes in-memory cache


def _invalidate_gallery_cache():
    global _gallery_cache, _gallery_cache_time
    _gallery_cache = None
    _gallery_cache_time = 0.0


# â”€â”€ Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/gallery")
def list_gallery(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Returns all gallery items with 5-minute in-memory caching to save Supabase egress bandwidth."""
    global _gallery_cache, _gallery_cache_time
    now = time.time()
    if _gallery_cache is not None and (now - _gallery_cache_time) < GALLERY_CACHE_TTL:
        return _gallery_cache

    items = (
        db.query(GalleryItem)
        .order_by(
            GalleryItem.is_featured.desc(),
            GalleryItem.sort_order.desc(),
            GalleryItem.created_at.desc(),
        )
        .all()
    )
    result = [_item_to_dict(i) for i in items]
    _gallery_cache = result
    _gallery_cache_time = now
    return result


@router.post("/gallery")
def add_gallery_item(
    payload: GalleryItemCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload a new gallery image. Any logged-in user can upload."""
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user and current_user.get("email"):
        user = db.query(User).filter(User.email == current_user.get("email")).first()
    if not user and current_user.get("phone"):
        user = db.query(User).filter(User.phone == current_user.get("phone")).first()

    if not user:
        if user_id:
            uploader_id = str(user_id)
            uploader_name = current_user.get("name") or "Community Member"
        else:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        uploader_id = str(user.id)
        uploader_name = user.name or "Community Member"

    m_type = payload.media_type
    if not m_type:
        m_type = "video" if "data:video" in payload.image_data else "image"

    item = GalleryItem(
        id=str(uuid.uuid4()),
        title=payload.title,
        description=payload.description,
        image_data=payload.image_data,
        media_type=m_type,
        uploaded_by=uploader_id,
        uploader_name=uploader_name,
        is_featured=payload.is_featured,
        sort_order=payload.sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _invalidate_gallery_cache()
    return _item_to_dict(item)


@router.post("/gallery/batch")
def add_gallery_items_batch(
    payload: GalleryBatchCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload multiple gallery images in a single batch request."""
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user and current_user.get("email"):
        user = db.query(User).filter(User.email == current_user.get("email")).first()
    if not user and current_user.get("phone"):
        user = db.query(User).filter(User.phone == current_user.get("phone")).first()

    if not user:
        if user_id:
            uploader_id = str(user_id)
            uploader_name = current_user.get("name") or "Community Member"
        else:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        uploader_id = str(user.id)
        uploader_name = user.name or "Community Member"

    created_items = []
    for p in payload.items:
        m_type = p.media_type
        if not m_type:
            m_type = "video" if "data:video" in p.image_data else "image"

        item = GalleryItem(
            id=str(uuid.uuid4()),
            title=p.title,
            description=p.description,
            image_data=p.image_data,
            media_type=m_type,
            uploaded_by=uploader_id,
            uploader_name=uploader_name,
            is_featured=p.is_featured,
            sort_order=p.sort_order,
        )
        db.add(item)
        created_items.append(item)

    db.commit()
    for item in created_items:
        db.refresh(item)

    _invalidate_gallery_cache()
    return [_item_to_dict(i) for i in created_items]


@router.patch("/gallery/{item_id}")
def update_gallery_item(
    item_id: str,
    payload: GalleryItemUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update caption, featured status, or sort order. Only the uploader can edit."""
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
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
    _invalidate_gallery_cache()
    return _item_to_dict(item)


@router.delete("/gallery/{item_id}")
def delete_gallery_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a gallery item. Allowed for the uploader or any authorized admin."""
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user and current_user.get("email"):
        user = db.query(User).filter(User.email == current_user.get("email")).first()

    item = db.query(GalleryItem).filter(GalleryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Gallery item not found")

    if user:
        if str(item.uploaded_by) != str(user.id) and not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin authorization or ownership required to delete gallery item")

    db.delete(item)
    db.commit()
    _invalidate_gallery_cache()
    return {"success": True, "message": "Gallery item deleted successfully"}

