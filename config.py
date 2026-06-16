from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "PharmaVision AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite+aiosqlite:///./pharmavision.db"

    REDIS_URL: str = "redis://localhost:6379/0"
    USE_REDIS: bool = False

    DEFAULT_CAMERA_INDEX: int = 0
    CAMERA_SCAN_MAX: int = 10

    YOLO_MODEL_PATH: str = "ai_models/yolo_pharma.pt"
    YOLO_CONFIDENCE: float = 0.5
    PATCHCORE_MODEL_PATH: str = "ai_models/patchcore_model.pt"
    ANOMALY_THRESHOLD_CONFORME: float = 0.30
    ANOMALY_THRESHOLD_SUSPECT: float = 0.60

    ALERT_NONCONFORMITY_RATE: float = 0.20
    ALERT_CONSECUTIVE_INSPECTIONS: int = 5

    COMPANY_NAME: str = "PharmaVision"
    REPORT_LANGUAGE: str = "fr"
    EXPORTS_DIR: str = "exports"

    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    ALERT_EMAIL: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
