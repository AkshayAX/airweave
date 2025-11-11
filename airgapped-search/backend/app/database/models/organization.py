"""Organization model."""

from typing import TYPE_CHECKING, List

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user_organization import UserOrganization
    from app.database.models.document import Document


class Organization(Base):
    """Organization model for multi-tenancy."""

    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Many-to-many relationship with users
    user_organizations: Mapped[List["UserOrganization"]] = relationship(
        "UserOrganization",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # One-to-many relationship with documents
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="noload"
    )
