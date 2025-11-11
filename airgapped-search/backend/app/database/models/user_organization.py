"""User Organization relationship model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.organization import Organization
    from app.database.models.user import User


class UserOrganization(Base):
    """Many-to-many relationship between users and organizations with roles."""

    __tablename__ = "user_organization"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role: Mapped[str] = mapped_column(
        String,
        default="member",
        nullable=False
    )  # owner, admin, member
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_organizations",
        lazy="noload"
    )
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="user_organizations",
        lazy="noload"
    )
