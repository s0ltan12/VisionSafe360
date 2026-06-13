"""User ORM model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Enum as PgEnum, String

from ..config.database import Base
from .enums import UserRoleEnum
from .timestamps import utcnow


class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    role          = Column(
        PgEnum(
            UserRoleEnum,
            name="userrole",
            create_type=False,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    status        = Column(String, default="Active")
    created_at    = Column(DateTime(timezone=True), nullable=False, default=utcnow)
