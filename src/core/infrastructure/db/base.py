import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Uuid
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class HasId(Base):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class UTCDateTime(TypeDecorator[datetime]):
    """A tz-aware UTC datetime that round-trips correctly through SQLite.

    SQLite has no native tz-aware storage; SQLAlchemy's plain DateTime(timezone=True)
    silently returns a naive datetime on read even when written as UTC-aware, which
    breaks any later comparison against a fresh tz-aware value. This type always
    stores naive-UTC and always returns UTC-aware.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: UP017
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)  # noqa: UP017
        return value
