"""
AquaLens AI - Configuration Module
"""

import os
from pathlib import Path
from typing import List
from dotenv import dotenv_values
from pydantic import BaseModel, SecretStr

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def data_gov_key() -> str:
    return os.getenv("DATA_GOV_IN_API_KEY", "").strip() or (
        dotenv_values(BASE_DIR / ".env", encoding="utf-8-sig").get("DATA_GOV_IN_API_KEY") or ""
    ).strip()


class Settings(BaseModel):
    PROJECT_NAME: str = "AquaLens AI"
    VERSION: str = "3.0.0"
    API_V1_STR: str = "/api/v1"
    DATA_GOV_IN_API_KEY: SecretStr = SecretStr(data_gov_key())
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "aqualens-insecure-secret-key-change-in-production-2026")
    ALGORITHM: str = "HS256"
    SESSION_COOKIE: str = "aqualens_session"
    SECURE_COOKIES: bool = os.getenv("AQUALENS_SECURE_COOKIES", "false").lower() == "true"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database: Supports PostgreSQL or local SQLite for development
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'aqualens.db'}")
    
    # Storage
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    
    # Scientific thresholds
    BASELINE_MIN_OBSERVATIONS: int = int(os.getenv("BASELINE_MIN_OBSERVATIONS", "5"))
    ANOMALY_Z_THRESHOLD: float = float(os.getenv("ANOMALY_Z_THRESHOLD", "2.5"))
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*"
    ]


settings = Settings()

# Ensure uploads directory exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
