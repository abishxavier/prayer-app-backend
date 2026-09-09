import os
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

router = APIRouter(prefix="/api/app", tags=["App Update"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERSION_CONFIG_PATH = os.path.join(BASE_DIR, "app_version.json")
STATIC_APK_DIR = os.path.join(BASE_DIR, "static", "apk")

# Ensure static/apk directory exists
os.makedirs(STATIC_APK_DIR, exist_ok=True)


def _load_version_config():
    default_config = {
        "latest_version": "1.0.0",
        "build_number": 1,
        "release_notes": "Initial release with live prayer audio meetings and auto-update support.",
        "download_url": "/api/app/download",
        "force_update": False
    }
    if os.path.exists(VERSION_CONFIG_PATH):
        try:
            with open(VERSION_CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**default_config, **json.load(f)}
        except Exception as e:
            print(f"Error reading app_version.json: {e}")
    return default_config


@router.get("/version")
def get_app_version(request: Request):
    """
    Returns the latest available version, build number, and download link for the app.
    Used by Flutter client to detect if an in-app update is needed.
    """
    config = _load_version_config()
    download_url = config.get("download_url", "/api/app/download")

    # If it's a relative URL, construct the full external URL
    if download_url.startswith("/"):
        base_url = str(request.base_url).rstrip("/")
        # Handle reverse proxies or Cloud Run forwarded protos
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto and base_url.startswith("http://") and forwarded_proto == "https":
            base_url = "https://" + base_url[7:]
        download_url = f"{base_url}{download_url}"

    return {
        "latest_version": config.get("latest_version", "1.0.0"),
        "build_number": int(config.get("build_number", 1)),
        "release_notes": config.get("release_notes", "Bug fixes and improvements."),
        "download_url": download_url,
        "force_update": bool(config.get("force_update", False))
    }


@router.get("/download")
def download_latest_apk():
    """
    Directly serves the latest Android APK for Over-The-Air app update installation.
    Looks for prayer_app.apk or app-release.apk in static/apk/.
    If an external download URL is configured, redirects directly to it.
    """
    config = _load_version_config()
    external_url = config.get("download_url", "")
    if external_url and external_url.startswith("http"):
        return RedirectResponse(url=external_url, status_code=302)
    candidates = [
        os.path.join(STATIC_APK_DIR, "prayer_app.apk"),
        os.path.join(STATIC_APK_DIR, "app-release.apk"),
    ]

    for apk_path in candidates:
        if os.path.isfile(apk_path):
            return FileResponse(
                path=apk_path,
                filename="prayer_app.apk",
                media_type="application/vnd.android.package-archive",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )

    raise HTTPException(
        status_code=404,
        detail="No APK found in static/apk/. Please place prayer_app.apk or app-release.apk in that directory."
    )
