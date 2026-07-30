from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import Base


class Plugin(Base):
    __tablename__ = "plugin"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    capability_types: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
