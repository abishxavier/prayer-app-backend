import os
import json
import base64

def get_firebase_service_account():
    """
    Safely retrieves Firebase Service Account from environment variables.
    No credentials are ever hardcoded in the codebase.
    """
    # 1. Try base64 encoded environment variable
    b64_data = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "").strip()
    if b64_data:
        try:
            raw_json = base64.b64decode(b64_data).decode("utf-8")
            return json.loads(raw_json)
        except Exception:
            pass

    # 2. Try raw JSON string environment variable
    json_data = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_data:
        try:
            return json.loads(json_data)
        except Exception:
            pass

    return None
