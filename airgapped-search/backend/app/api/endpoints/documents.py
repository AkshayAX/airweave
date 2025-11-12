"""Document management and upload endpoints."""

import os
import tempfile
from pathlib import Path
from typing import List, Optional
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.models import Document, User
from app.api.deps import get_db, get_current_user, require_admin
from app.conversions.converter_factory import ConverterFactory
from app.search.vector_store import VectorStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# Pydantic models for request/response
class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""

    document_id: str
    filename: str
    file_type: str
    status: str
    message: str


class DocumentResponse(BaseModel):
    """Response model for document details."""

    id: str
    filename: str
    file_type: str
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Response model for document list."""

    documents: List[DocumentResponse]
    total: int


class SearchRequest(BaseModel):
    """Request model for document search."""

    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    score_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Minimum similarity score"
    )


class SearchResult(BaseModel):
    """Individual search result."""

    score: float
    document_id: str
    chunk_index: int
    text: str
    metadata: dict


class SearchResponse(BaseModel):
    """Response model for search results."""

    results: List[SearchResult]
    total: int


# File type detection
SUPPORTED_EXTENSIONS = {
    # Documents
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".txt": "txt",
    ".md": "txt",
    # Spreadsheets
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".csv": "xlsx",
    # Code
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".java": "code",
    ".cpp": "code",
    ".c": "code",
    ".go": "code",
    ".rs": "code",
    ".rb": "code",
    ".php": "code",
    # Web
    ".html": "html",
    ".htm": "html",
    # Images (for OCR)
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".tif": "image",
}


def detect_file_type(filename: str) -> str:
    """Detect file type from filename extension.

    Args:
        filename: Name of the file

    Returns:
        File type string

    Raises:
        HTTPException: If file type is not supported
    """
    ext = Path(filename).suffix.lower()
    file_type = SUPPORTED_EXTENSIONS.get(ext)

    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}. Supported types: {', '.join(SUPPORTED_EXTENSIONS.keys())}",
        )

    return file_type


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and process a document for search.

    Processing pipeline:
    1. Save uploaded file temporarily
    2. Detect file type and convert to text
    3. Chunk the text
    4. Generate embeddings and store in vector database
    5. Save document metadata to database

    Args:
        file: Uploaded file
        current_user: Authenticated user
        db: Database session

    Returns:
        DocumentUploadResponse with document ID and status
    """
    logger.info(
        f"📁 UPLOAD ENDPOINT REACHED - Document upload started: {file.filename} by user {current_user.email} (ID: {current_user.id})"
    )

    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    # Detect file type
    file_type = detect_file_type(file.filename)

    # Create document record
    document = Document(
        filename=file.filename,
        file_type=file_type,
        status="processing",
        uploaded_by=current_user.id,
    )
    db.add(document)
    await db.flush()  # Get document ID
    await db.commit()

    temp_file_path = None
    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
            document.file_size = len(content)

        logger.debug(f"File saved to temp: {temp_file_path}")

        # Step 1: Convert document to text
        logger.debug(f"Converting {file_type} document...")
        converter = ConverterFactory.get_converter(file_type)
        conversion_result = await converter.convert_batch([temp_file_path])

        if temp_file_path not in conversion_result:
            raise Exception("Conversion failed: no result returned")

        text_content = conversion_result[temp_file_path]

        if not text_content or not text_content.strip():
            raise Exception("Conversion produced empty text")

        logger.info(f"Document converted: {len(text_content)} characters")

        # Update document with content
        document.content = text_content
        await db.commit()

        # Step 2: Index document (chunk + embed + store in Qdrant)
        logger.debug("Indexing document in vector store...")
        vector_store = VectorStore()
        index_result = await vector_store.index_document(
            document_id=document.id,
            text=text_content,
            metadata={
                "filename": file.filename,
                "file_type": file_type,
            },
        )

        logger.info(
            f"✓ Document indexed: {index_result['chunks_count']} chunks, "
            f"{index_result['vectors_stored']} vectors"
        )

        # Update document status
        document.status = "completed"
        await db.commit()

        return DocumentUploadResponse(
            document_id=str(document.id),
            filename=file.filename,
            file_type=file_type,
            status="completed",
            message=f"Document processed successfully: {index_result['chunks_count']} chunks indexed",
        )

    except Exception as e:
        logger.error(f"Document processing failed: {e}", exc_info=True)

        # Update document status to failed
        document.status = "failed"
        document.error_message = str(e)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(e)}",
        )

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"Temp file cleaned up: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents.

    Args:
        skip: Number of documents to skip (pagination)
        limit: Maximum number of documents to return
        current_user: Authenticated user
        db: Database session

    Returns:
        DocumentListResponse with list of documents
    """
    # Get documents
    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    documents = result.scalars().all()

    # Get total count
    count_result = await db.execute(select(Document))
    total = len(count_result.scalars().all())

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=str(doc.id),
                filename=doc.filename,
                file_type=doc.file_type,
                status=doc.status,
                created_at=doc.created_at.isoformat(),
                updated_at=doc.modified_at.isoformat(),
            )
            for doc in documents
        ],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific document.

    Args:
        document_id: Document UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        DocumentResponse with document details
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentResponse(
        id=str(document.id),
        filename=document.filename,
        file_type=document.file_type,
        status=document.status,
        created_at=document.created_at.isoformat(),
        updated_at=document.modified_at.isoformat(),
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its vectors.

    Requires admin access.

    Args:
        document_id: Document UUID
        current_user: Authenticated admin user
        db: Database session
    """
    # Get document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Delete vectors from Qdrant
    try:
        vector_store = VectorStore()
        await vector_store.delete_document(document_id=document_id)
        logger.info(f"Vectors deleted for document {document_id}")
    except Exception as e:
        logger.error(f"Failed to delete vectors: {e}", exc_info=True)
        # Continue with database deletion even if vector deletion fails

    # Delete document from database (will cascade to chunks)
    await db.delete(document)
    await db.commit()

    logger.info(f"Document deleted: {document_id}")


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    search_request: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search documents using semantic search.

    Args:
        search_request: Search parameters
        current_user: Authenticated user
        db: Database session

    Returns:
        SearchResponse with matching document chunks
    """
    logger.info(
        f"Search request: '{search_request.query[:50]}...' by user {current_user.id}"
    )

    # Perform vector search
    vector_store = VectorStore()
    results = await vector_store.search(
        query=search_request.query,
        limit=search_request.limit,
        score_threshold=search_request.score_threshold,
    )

    logger.info(f"Search returned {len(results)} results")

    return SearchResponse(
        results=[
            SearchResult(
                score=result["score"],
                document_id=result["document_id"],
                chunk_index=result["chunk_index"],
                text=result["text"],
                metadata=result["metadata"],
            )
            for result in results
        ],
        total=len(results),
    )
