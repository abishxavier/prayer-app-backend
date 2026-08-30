import firebase_admin
from firebase_admin import credentials, messaging
import os
import json
import logging

logger = logging.getLogger(__name__)

def _init_firebase():
    """
    Initialises Firebase Admin SDK.
    Tries multiple credential sources in priority order:
    1. FIREBASE_SERVICE_ACCOUNT_JSON env var (full JSON string — useful for Render secret env vars)
    2. FIREBASE_CREDENTIALS_PATH env var (path to the JSON file)
    3. GOOGLE_APPLICATION_CREDENTIALS env var (standard GCP path)
    4. Default file locations (app/core/ or root)
    """
    if firebase_admin._apps:
        return  # Already initialised

    # 1. Try JSON string from environment variable (most reliable on Render)
    json_str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_str:
        try:
            service_account_info = json.loads(json_str)
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialised from FIREBASE_SERVICE_ACCOUNT_JSON env var.")
            return
        except Exception as e:
            logger.error(f"Failed to init Firebase from FIREBASE_SERVICE_ACCOUNT_JSON: {e}")

    # 2. Try file paths
    candidate_paths = [
        os.getenv("FIREBASE_CREDENTIALS_PATH", ""),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        "/etc/secrets/firebase-service-account.json",   # Render secret file standard path
        "app/core/firebase-service-account.json",
        "firebase-service-account.json",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "firebase-service-account.json"),
    ]

    for path in candidate_paths:
        if path and os.path.exists(path):
            try:
                cred = credentials.Certificate(path)
                firebase_admin.initialize_app(cred)
                logger.info(f"Firebase Admin initialised from file: {path}")
                return
            except Exception as e:
                logger.error(f"Failed to init Firebase from {path}: {e}")

    # 3. Try embedded default service account (guarantees Render push notifications work out of the box)
    try:
        from app.core.firebase_credentials import get_firebase_service_account
        sa = get_firebase_service_account()
        if sa:
            cred = credentials.Certificate(sa)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialised from fallback service account.")
            return
    except Exception as e:
        logger.error(f"Failed to init Firebase from fallback service account: {e}")

    logger.warning(
        "Firebase Admin NOT initialised. Push notifications will be skipped.\n"
        "Set FIREBASE_SERVICE_ACCOUNT_JSON (JSON string) or FIREBASE_CREDENTIALS_PATH "
        "(file path) environment variable on Render."
    )

# Initialise once at module load time
_init_firebase()


def send_push_notification(token: str, title: str, body: str, data: dict = None, image: str = None):
    if not firebase_admin._apps:
        _init_firebase()
    if not firebase_admin._apps:
        logger.warning("Firebase not initialised — skipping push notification.")
        return False

    if not token:
        return False

    try:
        fcm_data = {str(k): str(v) for k, v in (data or {}).items()}
        notif_type = fcm_data.get("type") or fcm_data.get("notification_type") or "message"
        
        # Valid http/https image url for FCM rich notifications
        image_url = None
        if image and isinstance(image, str) and (image.startswith("http://") or image.startswith("https://")):
            image_url = image
            fcm_data["image"] = image_url

        # Channel selection: Calls use high priority call channel with ringtone
        is_call = (notif_type in ["video_call", "incoming_call", "call"])
        channel_id = 'video_call_channel' if is_call else 'high_importance_channel'
        tag = fcm_data.get("chat_id") or ("call_" + fcm_data.get("room_name", "")) if not is_call else None
        call_sound = 'ringtone' if is_call else 'default'
        apns_sound = 'ringtone.wav' if is_call else 'default'

        android_config = messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound=call_sound,
                click_action='FLUTTER_NOTIFICATION_CLICK',
                channel_id=channel_id,
                notification_count=1,
                image=image_url,
                tag=tag,
            )
        )

        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    badge=1,
                    sound=apns_sound,
                    mutable_content=True if image_url else False,
                )
            ),
            fcm_options=messaging.APNSFCMOptions(image=image_url) if image_url else None,
        )

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
                image=image_url,
            ),
            data=fcm_data,
            token=token,
            android=android_config,
            apns=apns_config,
        )
        response = messaging.send(message)
        logger.info(f"Push notification sent [{notif_type}]: {response}")
        return True
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return False

