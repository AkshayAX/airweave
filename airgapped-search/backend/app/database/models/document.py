"""Document model."""

from datetime import datetime
from typing import TYPE_CHECKING, List
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.organization import Organization
    from app.database.models.chunk import Chunk


class Document(Base):
    """Document model for storing uploaded files."""

    __tablename__ = "document"

    # Multi-tenant isolation
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Document metadata
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)  # pdf, docx, etc.
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=True)  # Storage path

    # Content
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Extracted text

    # Upload tracking
    uploaded_by: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True
    )
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Processing status
    status: Mapped[str] = mapped_column(
        String,
        default="pending",
        nullable=False
    )  # pending, processing, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="documents",
        lazy="noload"
    )
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="noload"
    )
