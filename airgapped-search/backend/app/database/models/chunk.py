"""Chunk model for document segments."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.document import Document


class Chunk(Base):
    """Chunk model for storing document segments with embeddings."""

    __tablename__ = "chunk"

    # Parent document
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Chunk content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Vector database reference
    vector_id: Mapped[str] = mapped_column(String, nullable=True, index=True)  # Qdrant point ID

    # Chunk metadata
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Access Control (denormalized from document for efficient filtering)
    access_type: Mapped[str] = mapped_column(String, default="private", nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    access_domains: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
        lazy="noload"
    )
