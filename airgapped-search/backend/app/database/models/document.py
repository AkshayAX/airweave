"""Document model."""

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import BigInteger, DateTime, String, Text
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

    # Upload tracking (no foreign key - accepts email from external auth)
    uploaded_by_email: Mapped[str | None] = mapped_column(String, nullable=True)
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    # Processing status
    status: Mapped[str] = mapped_column(
        String,
        default="pending",
        nullable=False
    )  # pending, processing, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Access Control (no foreign keys - accepts info from external auth)
    access_type: Mapped[str] = mapped_column(
        String,
        default="private",
        nullable=False
    )  # private, domain, public
    owner_email: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )  # For private documents (emails) - email of the owner
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
