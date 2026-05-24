"""
ExamGPT — SQLAlchemy 2.0 ORM Models

Defines the three core tables:
  • User            – registered learners
  • Question        – the question bank
  • UserPerformance – per-question attempt records
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import ForeignKey, JSON, String, Text, Boolean, Float, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# ── DeclarativeBase ───────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── User ──────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    performances: Mapped[List["UserPerformance"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"


# ── Question ──────────────────────────────────────────────────
class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sub_topic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    performances: Mapped[List["UserPerformance"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, topic='{self.topic}', difficulty='{self.difficulty}')>"


# ── UserPerformance ───────────────────────────────────────────
class UserPerformance(Base):
    __tablename__ = "user_performances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chosen_option: Mapped[str] = mapped_column(String(1), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    time_taken_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="performances")
    question: Mapped["Question"] = relationship(back_populates="performances")

    def __repr__(self) -> str:
        return (
            f"<UserPerformance(user_id={self.user_id}, "
            f"question_id={self.question_id}, correct={self.is_correct})>"
        )
