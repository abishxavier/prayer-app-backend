from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./fallback.db"
    jwt_secret: str = "default_jwt_secret_dev"
    firebase_credentials_path: Optional[str] = "app/core/firebase-service-account.json"
    agora_app_id: Optional[str] = ""
    agora_app_certificate: Optional[str] = ""

settings = Settings()