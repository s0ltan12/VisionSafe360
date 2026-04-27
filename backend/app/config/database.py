"""SQLAlchemy engine/session configuration for VisionSafe backend."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .settings import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # Detect stale connections automatically
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,    # Recycle connections every 30 minutes
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Yield a DB session and close it after request processing."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
