"""Vector store service for document indexing and search.

Orchestrates chunking, embedding, and vector storage.
"""

from typing import List, Dict, Optional
from uuid import UUID, uuid4
import logging

from qdrant_client.models import PointStruct

from app.search.qdrant_service import QdrantService
from app.search.embedding_service import EmbeddingService
from app.chunking import SemanticChunker

logger = logging.getLogger(__name__)


class VectorStore:
    """High-level service for document indexing and vector search.

    Combines chunking, embedding, and vector storage.
    """

    def __init__(self):
        """Initialize vector store with required services."""
        self.qdrant = QdrantService()
        self.embedding_service = EmbeddingService()
        self.chunker = SemanticChunker()

        logger.info("VectorStore initialized")

    async def index_document(
        self,
        organization_id: UUID,
        document_id: UUID,
        text: str,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Index a document for search.

        Process flow:
        1. Chunk the document text
        2. Generate embeddings for each chunk
        3. Store vectors in Qdrant with metadata

        Args:
            organization_id: Organization UUID
            document_id: Document UUID
            text: Document text content
            metadata: Optional metadata (filename, file_type, etc.)

        Returns:
            Dict with indexing statistics
        """
        if not text or not text.strip():
            raise ValueError("Document text cannot be empty")

        logger.info(f"Indexing document {document_id} for org {organization_id}")

        # Step 1: Chunk the document
        logger.debug("Chunking document...")
        chunk_results = await self.chunker.chunk_batch([text])

        if not chunk_results or not chunk_results[0]:
            raise Exception("Chunking produced no results")

        chunks = chunk_results[0]
        logger.info(f"Document chunked into {len(chunks)} chunks")

        # Step 2: Extract chunk texts
        chunk_texts = [chunk["text"] for chunk in chunks]

        # Step 3: Generate embeddings
        logger.debug("Generating embeddings...")
        embeddings = await self.embedding_service.embed_documents(
            chunk_texts, batch_size=32
        )

        if len(embeddings) != len(chunks):
            raise Exception(
                f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}"
            )

        logger.info(f"Generated {len(embeddings)} embeddings")

        # Step 4: Prepare points for Qdrant
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Create unique point ID
            point_id = str(uuid4())

            # Prepare payload
            payload = {
                "document_id": str(document_id),
                "organization_id": str(organization_id),
                "chunk_index": i,
                "text": chunk["text"],
                "start_index": chunk["start_index"],
                "end_index": chunk["end_index"],
                "token_count": chunk["token_count"],
            }

            # Add custom metadata
            if metadata:
                payload.update(metadata)

            # Create point
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            )
            points.append(point)

        # Step 5: Upsert to Qdrant
        logger.debug("Storing vectors in Qdrant...")
        result = await self.qdrant.upsert_vectors(
            organization_id=organization_id,
            points=points,
        )

        logger.info(
            f"✓ Document {document_id} indexed: {len(chunks)} chunks, "
            f"{len(embeddings)} vectors"
        )

        return {
            "document_id": str(document_id),
            "chunks_count": len(chunks),
            "vectors_stored": result["upserted"],
            "collection": result["collection"],
        }

    async def search(
        self,
        organization_id: UUID,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        metadata_filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """Search for documents using semantic search.

        Args:
            organization_id: Organization UUID
            query: Search query string
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            metadata_filters: Optional filters (e.g., {"file_type": "pdf"})

        Returns:
            List of search results with scores, text, and metadata
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        logger.info(f"Searching for: '{query[:50]}...' in org {organization_id}")

        # Step 1: Generate query embedding
        logger.debug("Generating query embedding...")
        query_vector = await self.embedding_service.embed_query(query)

        # Step 2: Search in Qdrant
        logger.debug("Searching vectors...")
        results = await self.qdrant.search_vectors(
            organization_id=organization_id,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=metadata_filters,
        )

        logger.info(f"Found {len(results)} results")

        # Step 3: Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "score": result["score"],
                "document_id": result["payload"].get("document_id"),
                "chunk_index": result["payload"].get("chunk_index"),
                "text": result["payload"].get("text"),
                "metadata": {
                    k: v for k, v in result["payload"].items()
                    if k not in ["text", "document_id", "chunk_index", "organization_id"]
                },
            })

        return formatted_results

    async def delete_document(
        self,
        organization_id: UUID,
        document_id: UUID,
    ) -> Dict:
        """Delete all vectors for a document.

        Args:
            organization_id: Organization UUID
            document_id: Document UUID

        Returns:
            Dict with deletion statistics
        """
        logger.info(f"Deleting vectors for document {document_id}")

        result = await self.qdrant.delete_document_vectors(
            organization_id=organization_id,
            document_id=document_id,
        )

        logger.info(f"✓ Vectors deleted for document {document_id}")

        return result

    async def get_collection_stats(self, organization_id: UUID) -> Dict:
        """Get statistics for an organization's collection.

        Args:
            organization_id: Organization UUID

        Returns:
            Dict with collection statistics
        """
        return await self.qdrant.get_collection_info(organization_id)
