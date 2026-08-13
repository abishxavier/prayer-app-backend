import firebase_admin
from firebase_admin import credentials, messaging
import os
import logging

logger = logging.getLogger(__name__)

# Only initialize if credentials exist to prevent crashing
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "firebase-service-account.json")

try:
    if os.path.exists(CREDENTIALS_PATH):
        cred = credentials.Certificate(CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin initialized successfully.")
    else:
        logger.warning(f"Firebase credentials not found at {CREDENTIALS_PATH}. Push notifications will not be sent.")
except Exception as e:
    logger.error(f"Failed to initialize Firebase Admin: {e}")

def send_push_notification(token: str, title: str, body: str, data: dict = None):
    if not firebase_admin._apps:
        logger.warning("Firebase Admin is not initialized. Skipping push notification.")
        return False
        
    if not token:
        return False

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
        )
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return True
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return False
