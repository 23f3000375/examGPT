"""
ExamGPT — Application Configuration

Loads environment variables via Pydantic BaseSettings.
A .env file in the backend root is read automatically.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    # ── API Keys ──────────────────────────────────────────────
    GROQ_API_KEY: str = "your_api_key_here"

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/examgpt"

    # ── App Metadata ──────────────────────────────────────────
    APP_NAME: str = "ExamGPT"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton – import this instance everywhere
settings = Settings()
