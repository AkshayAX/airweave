"""Document model."""

from datetime import datetime
from typing import TYPE_CHECKING, List
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.database.models.chunk import Chunk


class Document(Base):
    """Document model for storing uploaded files."""

    __tablename__ = "document"

    # Document metadata
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)  # pdf, docx, etc.
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    file_path: Mapped[str] = mapped_column(String, nullable=True)  # Storage path

    # Content
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Extracted text

    # Upload tracking
    uploaded_by: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True
    )
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    # Processing status
    status: Mapped[str] = mapped_column(
        String,
        default="pending",
        nullable=False
    )  # pending, processing, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Access Control
    access_type: Mapped[str] = mapped_column(
        String,
        default="private",
        nullable=False
    )  # private, domain, public
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True
    )  # For private documents (emails)
    access_domains: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True
    )  # ["finance", "legal", "engineering"] for domain-based access

    # Relationships
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="noload"
    )
