import os
import json
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/bible", tags=["Bible"])

_bible_cache = None

def get_bible_data():
    global _bible_cache
    if _bible_cache is None:
        data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bible_data.json")
        if os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                _bible_cache = json.load(f)
        else:
            _bible_cache = {}
    return _bible_cache

@router.get("/{book_id}/{chapter}")
def get_chapter_verses(book_id: str, chapter: int):
    data = get_bible_data()
    clean_id = book_id.lower().strip()
    book = data.get(clean_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")

    chapter_str = str(chapter)
    verses = book.get(chapter_str)
    if not verses:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter} not found in book '{book_id}'")

    return {
        "book_id": clean_id,
        "chapter": chapter,
        "total_verses": len(verses),
        "verses": verses,
    }
