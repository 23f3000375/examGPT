"""
ExamGPT — Database Table Initializer

Run this script once after starting the PostgreSQL container
to create all tables defined in the ORM models.

Usage:
    python init_db.py
"""

from app.core.database import engine, SessionLocal
from app.models.models import Base, User


def init() -> None:
    print("Connecting to database...")
    print(f"  URL: {engine.url}")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    print(f"  Tables: {list(Base.metadata.tables.keys())}")

    # Seed default user with id=1
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            print("Seeding default user (id=1)...")
            default_user = User(id=1, username="student", email="student@examgpt.com")
            db.add(default_user)
            db.commit()
            print("Default user seeded successfully!")
        else:
            print("Default user already exists.")
    except Exception as e:
        print(f"Error seeding user: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init()
