"""User model."""

from datetime import datetime
from typing import TYPE_CHECKING, List
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user_organization import UserOrganization


class User(Base):
    """User model with RBAC support."""

    __tablename__ = "user"

    full_name: Mapped[str] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Many-to-many relationship with organizations
    user_organizations: Mapped[List["UserOrganization"]] = relationship(
        "UserOrganization",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    @property
    def primary_organization_id(self) -> UUID | None:
        """Get the primary organization ID."""
        for user_org in self.user_organizations:
            if user_org.is_primary:
                return user_org.organization_id
        return None

    def has_role_in_org(self, organization_id: UUID, required_role: str) -> bool:
        """Check if user has required role in organization."""
        role_hierarchy = {
            "member": ["member", "admin", "owner"],
            "admin": ["admin", "owner"],
            "owner": ["owner"]
        }

        for user_org in self.user_organizations:
            if user_org.organization_id == organization_id:
                return user_org.role in role_hierarchy.get(required_role, [])
        return False
