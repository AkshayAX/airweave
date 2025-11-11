"""API Key model for authentication."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.organization import Organization


class APIKey(Base):
    """API Key model for programmatic access."""

    __tablename__ = "api_key"

    # Key details
    key_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)  # First 8 chars for display
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="noload")
    organization: Mapped["Organization"] = relationship("Organization", lazy="noload")
