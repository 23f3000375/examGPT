"""
ExamGPT — Database Engine & Session

Sets up the synchronous SQLAlchemy 2.0 engine and a session factory.
Use the `get_db` dependency in FastAPI routes to obtain a session.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,       # log SQL when DEBUG=True
    pool_pre_ping=True,        # verify connections before checkout
)

# ── Session Factory ───────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI Dependency ────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
