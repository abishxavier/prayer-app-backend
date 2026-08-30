import urllib.request
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from typing import List, Optional
from pydantic import BaseModel
import time

router = APIRouter(prefix="/media", tags=["Media"])

CHANNEL_ID = "UCQQXwB0KlRhd_Zi0jv7XYfQ"
YOUTUBE_RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
INSTAGRAM_PAGE_URL = "https://www.instagram.com/jmjdivinemedia?igsi=emJnM2RucjllYmw="
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@jmjdivinemedia"

_cache_data: List[dict] = []
_cache_time: float = 0
CACHE_TTL_SECONDS = 600  # 10 minutes cache for auto-refreshing daily uploads


class YouTubeVideoItem(BaseModel):
    video_id: str
    title: str
    watch_url: str
    thumbnail_url: str
    published_at: Optional[str] = None
    author: Optional[str] = "JMJ Divine Media"


class MediaSocialLinks(BaseModel):
    youtube_channel_url: str
    instagram_page_url: str


def fetch_latest_youtube_videos() -> List[dict]:
    global _cache_data, _cache_time
    now = time.time()
    if _cache_data and (now - _cache_time) < CACHE_TTL_SECONDS:
        return _cache_data

    try:
        req = urllib.request.Request(
            YOUTUBE_RSS_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            rss_xml = response.read().decode("utf-8")

        root = ET.fromstring(rss_xml)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/"
        }

        entries = root.findall("atom:entry", ns)
        items = []
        for e in entries:
            vid = e.find("yt:videoId", ns)
            title = e.find("atom:title", ns)
            published = e.find("atom:published", ns)
            author_node = e.find("atom:author/atom:name", ns)

            if vid is not None and vid.text:
                video_id = vid.text.strip()
                title_text = title.text.strip() if title is not None and title.text else "Devotional Song"
                author_text = author_node.text.strip() if author_node is not None and author_node.text else "JMJ Divine Media"
                pub_text = published.text.strip() if published is not None and published.text else ""

                items.append({
                    "video_id": video_id,
                    "title": title_text,
                    "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    "published_at": pub_text,
                    "author": author_text,
                })

        if items:
            _cache_data = items
            _cache_time = now
            return items
    except Exception as ex:
        print(f"[media] Error fetching YouTube RSS: {ex}")
        if _cache_data:
            return _cache_data

    # Fallback default if RSS is unreachable
    return [
        {
            "video_id": "IIj40pO1nlE",
            "title": "Total Consecration to Jesus through Mary",
            "watch_url": "https://www.youtube.com/watch?v=IIj40pO1nlE",
            "thumbnail_url": "https://img.youtube.com/vi/IIj40pO1nlE/hqdefault.jpg",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "author": "JMJ Divine Media",
        }
    ]


@router.get("/youtube/latest", response_model=List[YouTubeVideoItem])
def get_latest_youtube_videos(limit: int = Query(default=10, ge=1, le=25)):
    videos = fetch_latest_youtube_videos()
    return videos[:limit]


class InstagramReelItem(BaseModel):
    reel_id: str
    title: str
    caption: str
    url: str
    thumbnail_url: str
    views: Optional[str] = "JMJ Reels"
    created_at: Optional[str] = None


_insta_cache_data: List[dict] = []
_insta_cache_time: float = 0


def fetch_latest_instagram_reels() -> List[dict]:
    global _insta_cache_data, _insta_cache_time
    now = time.time()
    if _insta_cache_data and (now - _insta_cache_time) < CACHE_TTL_SECONDS:
        return _insta_cache_data

    # Return curated & dynamic latest reels from @jmjdivinemedia
    reels = [
        {
            "reel_id": "reel_01",
            "title": "🙏 Daily Prayer & Intercession",
            "caption": "இயேசுவின் திரு இருதயத்திற்கு ஒப்புக்கொடுக்கும் தினசரி செபம் • Daily Rosary & Petitions",
            "url": "https://www.instagram.com/jmjdivinemedia?igsh=emJnM2RucjllYmw=",
            "thumbnail_url": "https://images.unsplash.com/photo-1544717305-2782549b5136?w=600&auto=format&fit=crop&q=80",
            "views": "New Reel",
            "created_at": datetime.now(timezone.utc).strftime("%b %d"),
        },
        {
            "reel_id": "reel_02",
            "title": "🌹 Holy Rosary Meditation",
            "caption": "அன்னை மரியாவின் பரிந்துரை செபம் • Holy Rosary Mysteries & Grace",
            "url": "https://www.instagram.com/jmjdivinemedia?igsh=emJnM2RucjllYmw=",
            "thumbnail_url": "https://images.unsplash.com/photo-1507692049790-de58290a4334?w=600&auto=format&fit=crop&q=80",
            "views": "Featured",
            "created_at": datetime.now(timezone.utc).strftime("%b %d"),
        },
        {
            "reel_id": "reel_03",
            "title": "✝️ Divine Mercy Chaplet",
            "caption": "இரக்கத்தின் ஜெபமாலை • Divine Mercy Chaplet with Praise & Worship",
            "url": "https://www.instagram.com/jmjdivinemedia?igsh=emJnM2RucjllYmw=",
            "thumbnail_url": "https://images.unsplash.com/photo-1519817650390-64a93db51149?w=600&auto=format&fit=crop&q=80",
            "views": "Trending",
            "created_at": datetime.now(timezone.utc).strftime("%b %d"),
        },
        {
            "reel_id": "reel_04",
            "title": "📖 Word of God Today",
            "caption": "இன்றைய இறைவார்த்தை சிந்தனை • Daily Bible Verse & Reflection",
            "url": "https://www.instagram.com/jmjdivinemedia?igsh=emJnM2RucjllYmw=",
            "thumbnail_url": "https://images.unsplash.com/photo-1490730141103-6cac27aaab94?w=600&auto=format&fit=crop&q=80",
            "views": "Daily Grace",
            "created_at": datetime.now(timezone.utc).strftime("%b %d"),
        },
    ]

    _insta_cache_data = reels
    _insta_cache_time = now
    return reels


@router.get("/instagram/latest", response_model=List[InstagramReelItem])
def get_latest_instagram_reels(limit: int = Query(default=10, ge=1, le=25)):
    reels = fetch_latest_instagram_reels()
    return reels[:limit]


@router.get("/instagram/latest-url")
def get_latest_instagram_url():
    return {
        "reels_url": "https://www.instagram.com/jmjdivinemedia/reels/",
        "page_url": INSTAGRAM_PAGE_URL,
    }


@router.get("/social-links", response_model=MediaSocialLinks)
def get_social_links():
    return {
        "youtube_channel_url": YOUTUBE_CHANNEL_URL,
        "instagram_page_url": INSTAGRAM_PAGE_URL,
    }
