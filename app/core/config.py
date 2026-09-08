from pydantic_settings import BaseSettings

from typing import Optional

class Settings(BaseSettings):
    database_url: str = "sqlite:///./fallback.db"
    jwt_secret: str = "default_jwt_secret_dev"
    firebase_credentials_path: Optional[str] = "app/core/firebase-service-account.json"
    agora_app_id: Optional[str] = ""
    agora_app_certificate: Optional[str] = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()