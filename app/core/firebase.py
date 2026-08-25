import os
import firebase_admin
from firebase_admin import credentials
from app.core.config import settings

if not firebase_admin._apps:
    path = getattr(settings, 'firebase_credentials_path', '')
    if path and os.path.exists(path):
        try:
            cred = credentials.Certificate(path)
            firebase_admin.initialize_app(cred)
        except Exception:
            pass

    if not firebase_admin._apps:
        try:
            from app.core.firebase_credentials import get_firebase_service_account
            sa = get_firebase_service_account()
            if sa:
                cred = credentials.Certificate(sa)
                firebase_admin.initialize_app(cred)
        except Exception:
            pass