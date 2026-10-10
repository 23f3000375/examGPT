"""
ExamGPT — Application Configuration

Loads environment variables via Pydantic BaseSettings.
A .env file in the backend root is read automatically.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    # ── API Keys ──────────────────────────────────────────────
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    CEREBRAS_API_KEY: str | None = None
    CEREBRAS_MODEL: str = "llama3.1-70b"
    
    APP_URL: str = "http://localhost:5173"
    LLM_TIMEOUT_SECONDS: float = 30.0
    CHUNK_SIZE: int = 5

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
