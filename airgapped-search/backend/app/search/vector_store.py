"""Vector store service for document indexing and search.

Orchestrates chunking, embedding, and vector storage.
"""

from typing import List, Dict, Optional
from uuid import UUID, uuid4
import logging

from app.search.qdrant_service import QdrantService
from app.search.embedding_service import EmbeddingService
from app.search.sparse_embedding_service import SparseEmbeddingService
from app.chunking import SemanticChunker

logger = logging.getLogger(__name__)


class VectorStore:
    """High-level service for document indexing and vector search.

    Combines chunking, embedding, and vector storage in a single collection.
    """

    def __init__(self):
        """Initialize vector store with required services."""
        self.qdrant = QdrantService()
        self.embedding_service = EmbeddingService()
        self.sparse_embedding_service = SparseEmbeddingService()
        self.chunker = SemanticChunker()

        logger.info("VectorStore initialized with hybrid search support")

    async def index_document(
        self,
        document_id: UUID,
        text: str,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Index a document for hybrid search.

        Process flow:
        1. Chunk the document text
        2. Generate dense embeddings (semantic) for each chunk
        3. Generate sparse embeddings (keyword/BM25) for each chunk
        4. Store both vectors in Qdrant with metadata

        Args:
            document_id: Document UUID
            text: Document text content
            metadata: Optional metadata (filename, file_type, etc.)

        Returns:
            Dict with indexing statistics
        """
        if not text or not text.strip():
            raise ValueError("Document text cannot be empty")

        logger.info(f"Indexing document {document_id}")

        # Step 1: Chunk the document
        logger.debug("Chunking document...")
        chunk_results = await self.chunker.chunk_batch([text])

        if not chunk_results or not chunk_results[0]:
            raise Exception("Chunking produced no results")

        chunks = chunk_results[0]
        logger.info(f"Document chunked into {len(chunks)} chunks")

        # Step 2: Extract chunk texts
        chunk_texts = [chunk["text"] for chunk in chunks]

        # Step 3: Generate dense embeddings (semantic)
        logger.debug("Generating dense embeddings (semantic)...")
        dense_embeddings = await self.embedding_service.embed_documents(
            chunk_texts, batch_size=32
        )

        if len(dense_embeddings) != len(chunks):
            raise Exception(
                f"Dense embedding count mismatch: {len(dense_embeddings)} != {len(chunks)}"
            )

        logger.info(f"Generated {len(dense_embeddings)} dense embeddings")

        # Step 4: Generate sparse embeddings (keyword/BM25)
        logger.debug("Generating sparse embeddings (keyword)...")
        sparse_embeddings = await self.sparse_embedding_service.embed_documents(
            chunk_texts, batch_size=32
        )

        if len(sparse_embeddings) != len(chunks):
            raise Exception(
                f"Sparse embedding count mismatch: {len(sparse_embeddings)} != {len(chunks)}"
            )

        logger.info(f"Generated {len(sparse_embeddings)} sparse embeddings")

        # Step 5: Prepare points for Qdrant (hybrid format)
        points = []
        for i, (chunk, dense_emb, sparse_emb) in enumerate(zip(chunks, dense_embeddings, sparse_embeddings)):
            # Create unique point ID
            point_id = str(uuid4())

            # Prepare payload
            payload = {
                "document_id": str(document_id),
                "chunk_index": i,
                "text": chunk["text"],
                "start_index": chunk["start_index"],
                "end_index": chunk["end_index"],
                "token_count": chunk["token_count"],
            }

            # Add custom metadata
            if metadata:
                payload.update(metadata)

            # Create point with both dense and sparse vectors
            point = {
                "id": point_id,
                "dense_vector": dense_emb,
                "sparse_vector": sparse_emb,
                "payload": payload,
            }
            points.append(point)

        # Step 6: Upsert to Qdrant
        logger.debug("Storing vectors in Qdrant...")
        result = await self.qdrant.upsert_vectors(points=points)

        logger.info(
            f"✓ Document {document_id} indexed: {len(chunks)} chunks, "
            f"{len(points)} vectors"
        )

        return {
            "document_id": str(document_id),
            "chunks_count": len(chunks),
            "vectors_stored": result["points_count"],
            "collection": result["collection"],
        }

    async def search(
        self,
        query: str,
        search_type: str = "hybrid",
        limit: int = 10,
        score_threshold: Optional[float] = None,
        document_filter: Optional[UUID] = None,
        metadata_filters: Optional[Dict[str, any]] = None,
        user_email: Optional[str] = None,
        user_domains: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Search for documents using hybrid search with access control and metadata filtering.

        Args:
            query: Search query string
            search_type: Type of search - "semantic", "keyword", or "hybrid" (default: "hybrid")
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            document_filter: Optional document UUID to filter by
            metadata_filters: Optional dict of metadata field->value pairs to filter by (e.g., {"file_type": "pdf"})
            user_email: User email for access control filtering
            user_domains: List of domains user has access to

        Returns:
            List of search results with scores, text, and metadata
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        logger.info(
            f"Searching for: '{query[:50]}...' (type={search_type}, "
            f"user_email={user_email}, domains={user_domains})"
        )

        # Step 1: Generate query embeddings based on search type
        query_vector = None
        sparse_query_vector = None

        if search_type in ["semantic", "hybrid"]:
            logger.debug("Generating dense query embedding (semantic)...")
            query_vector = await self.embedding_service.embed_query(query)

        if search_type in ["keyword", "hybrid"]:
            logger.debug("Generating sparse query embedding (keyword)...")
            sparse_query_vector = await self.sparse_embedding_service.embed_query(query)

        # Step 2: Search in Qdrant with access control and metadata filtering
        logger.debug(f"Searching vectors with access control (type={search_type})...")
        results = await self.qdrant.search_vectors(
            query_vector=query_vector,
            sparse_query_vector=sparse_query_vector,
            search_type=search_type,
            limit=limit,
            score_threshold=score_threshold,
            document_filter=document_filter,
            metadata_filters=metadata_filters,
            user_email=user_email,
            user_domains=user_domains,
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
                    if k not in ["text", "document_id", "chunk_index"]
                },
            })

        return formatted_results

    async def delete_document(self, document_id: UUID) -> Dict:
        """Delete all vectors for a document.

        Args:
            document_id: Document UUID

        Returns:
            Dict with deletion statistics
        """
        logger.info(f"Deleting vectors for document {document_id}")

        result = await self.qdrant.delete_document_vectors(document_id=document_id)

        logger.info(f"✓ Vectors deleted for document {document_id}")

        return result

    async def get_collection_stats(self) -> Dict:
        """Get statistics for the collection.

        Returns:
            Dict with collection statistics
        """
        return await self.qdrant.get_collection_info()
