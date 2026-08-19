import firebase_admin
from firebase_admin import credentials, messaging
import os
import logging

logger = logging.getLogger(__name__)

# Search candidate paths for firebase service account json
candidate_paths = [
    os.getenv("FIREBASE_CREDENTIALS_PATH", ""),
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
    "app/core/firebase-service-account.json",
    "firebase-service-account.json",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "firebase-service-account.json"),
]

if not firebase_admin._apps:
    for path in candidate_paths:
        if path and os.path.exists(path):
            try:
                cred = credentials.Certificate(path)
                firebase_admin.initialize_app(cred)
                logger.info(f"Firebase Admin initialized successfully using {path}.")
                break
            except Exception as e:
                logger.error(f"Failed to initialize Firebase Admin with {path}: {e}")

def send_push_notification(token: str, title: str, body: str, data: dict = None):
    if not firebase_admin._apps:
        logger.warning("Firebase Admin is not initialized. Skipping push notification.")
        return False
        
    if not token:
        return False

    try:
        fcm_data = {str(k): str(v) for k, v in (data or {}).items()}
        
        android_config = messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound='default',
                click_action='FLUTTER_NOTIFICATION_CLICK',
                channel_id='high_importance_channel',
                notification_count=1,
            )
        )
        
        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    badge=1,
                    sound='default',
                )
            )
        )

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=fcm_data,
            token=token,
            android=android_config,
            apns=apns_config,
        )
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return True
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return False
