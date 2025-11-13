"""Qdrant vector database service for managing collections and search.

Handles connection, collection management, and vector operations with hybrid search support.
Supports both dense vectors (semantic) and sparse vectors (keyword/BM25-like).
"""

from typing import Dict, List, Optional
from uuid import UUID
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    SearchRequest,
    NamedVector,
    NamedSparseVector,
    Prefetch,
    Query,
    FusionQuery,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for interacting with Qdrant vector database.

    Uses a single 'documents' collection for all documents.
    """

    COLLECTION_NAME = "documents"

    def __init__(self):
        """Initialize Qdrant client."""
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=60,  # Increased timeout for large batches
        )
        self.embedding_dimension = settings.EMBEDDING_DIMENSION
        logger.info(f"Qdrant client initialized: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")

    async def ensure_collection_exists(self) -> str:
        """Ensure the documents collection exists with hybrid search support.

        Creates the collection if it doesn't exist with both dense and sparse vectors.
        Dense vectors: semantic search (BAAI/bge-small-en-v1.5)
        Sparse vectors: keyword search (SPLADE)

        Returns:
            Collection name
        """
        collection_name = self.COLLECTION_NAME

        # Check if collection exists
        collections = self.client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)

        if not exists:
            logger.info(f"Creating hybrid search collection: {collection_name}")
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    # Dense vectors for semantic search
                    "dense": VectorParams(
                        size=self.embedding_dimension,
                        distance=Distance.COSINE,
                    ),
                    # Sparse vectors for keyword search (SPLADE)
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(),
                    ),
                },
            )
            logger.info(f"✓ Hybrid search collection created: {collection_name}")
        else:
            logger.debug(f"Collection already exists: {collection_name}")

        return collection_name

    async def upsert_vectors(
        self,
        points: List[Dict],
    ) -> Dict:
        """Insert or update vectors in the collection with hybrid search support.

        Args:
            points: List of dicts with:
                - id: Point ID
                - dense_vector: Dense embedding vector
                - sparse_vector: Sparse embedding dict with 'indices' and 'values'
                - payload: Metadata payload

        Returns:
            Dictionary with operation status
        """
        collection_name = await self.ensure_collection_exists()

        logger.debug(f"Upserting {len(points)} hybrid points to {collection_name}")

        # Convert to Qdrant PointStruct format with named vectors
        qdrant_points = []
        for point in points:
            qdrant_point = PointStruct(
                id=point["id"],
                vector={
                    "dense": point["dense_vector"],
                    "sparse": point["sparse_vector"],
                },
                payload=point["payload"],
            )
            qdrant_points.append(qdrant_point)

        # Upsert points
        result = self.client.upsert(
            collection_name=collection_name,
            points=qdrant_points,
        )

        logger.info(f"✓ Upserted {len(points)} hybrid vectors to {collection_name}")

        return {
            "collection": collection_name,
            "points_count": len(points),
            "status": result.status.name if hasattr(result, 'status') else "completed",
        }

    async def search_vectors(
        self,
        query_vector: Optional[List[float]] = None,
        sparse_query_vector: Optional[Dict] = None,
        search_type: str = "semantic",  # semantic, keyword, or hybrid
        limit: int = 10,
        score_threshold: Optional[float] = None,
        document_filter: Optional[UUID] = None,
        metadata_filters: Optional[Dict[str, any]] = None,
        user_email: Optional[str] = None,
        user_domains: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Search for similar vectors in the collection with hybrid search support.

        Args:
            query_vector: Dense query embedding vector (for semantic search)
            sparse_query_vector: Sparse query embedding (for keyword search)
            search_type: Type of search - "semantic", "keyword", or "hybrid"
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0.0 to 1.0)
            document_filter: Optional document UUID to filter by
            metadata_filters: Optional dict of metadata field->value pairs to filter by (e.g., {"file_type": "pdf"})
            user_email: User email for access control filtering
            user_domains: List of domains user has access to

        Returns:
            List of search results with scores and payloads
        """
        collection_name = self.COLLECTION_NAME

        # Build filters
        filter_conditions = []

        # Add document ID filter if provided
        if document_filter:
            filter_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=str(document_filter)),
                )
            )

        # Add metadata filters if provided
        if metadata_filters:
            for field, value in metadata_filters.items():
                filter_conditions.append(
                    FieldCondition(
                        key=field,
                        match=MatchValue(value=value),
                    )
                )

        # Build access control filter (OR conditions)
        access_conditions = []

        # 1. Public documents - everyone can access
        access_conditions.append(
            FieldCondition(
                key="access_type",
                match=MatchValue(value="public"),
            )
        )

        # 2. Private documents - only owner
        if user_email:
            access_conditions.append(
                FieldCondition(
                    key="owner_email",
                    match=MatchValue(value=user_email),
                )
            )

        # 3. Domain-based access - check if user's domains match document's domains
        if user_domains:
            for domain in user_domains:
                access_conditions.append(
                    FieldCondition(
                        key="access_domains",
                        match=MatchAny(any=[domain]),
                    )
                )

        # Combine filters
        query_filter = None
        if access_conditions:
            if filter_conditions:
                # Both document filter AND access control
                query_filter = Filter(
                    must=filter_conditions,
                    should=access_conditions,  # OR for access conditions
                )
            else:
                # Only access control
                query_filter = Filter(should=access_conditions)
        elif filter_conditions:
            # Only document filter
            query_filter = Filter(must=filter_conditions)

        logger.debug(
            f"Searching {collection_name}: type={search_type}, limit={limit}, "
            f"threshold={score_threshold}, document_filter={document_filter}, "
            f"metadata_filters={metadata_filters}, user_email={user_email}, user_domains={user_domains}"
        )

        # Perform search based on search_type
        if search_type == "semantic":
            # Dense vector search only (semantic/embedding-based)
            if not query_vector:
                raise ValueError("query_vector required for semantic search")

            logger.debug("Performing semantic search with dense vectors")
            search_result = self.client.search(
                collection_name=collection_name,
                query_vector=NamedVector(name="dense", vector=query_vector),
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            )

        elif search_type == "keyword":
            # Sparse vector search only (keyword/BM25-like)
            if not sparse_query_vector:
                raise ValueError("sparse_query_vector required for keyword search")

            logger.debug("Performing keyword search with sparse vectors")
            search_result = self.client.search(
                collection_name=collection_name,
                query_vector=NamedSparseVector(
                    name="sparse",
                    vector=sparse_query_vector
                ),
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            )

        elif search_type == "hybrid":
            # Hybrid search: combine dense (semantic) and sparse (keyword)
            if not query_vector or not sparse_query_vector:
                raise ValueError("Both query_vector and sparse_query_vector required for hybrid search")

            logger.debug("Performing hybrid search with dense + sparse vectors")
            # Use query API with Reciprocal Rank Fusion (RRF)
            query_result = self.client.query_points(
                collection_name=collection_name,
                query=FusionQuery(fusion="rrf"),  # Reciprocal Rank Fusion
                prefetch=[
                    # Prefetch from dense vectors (semantic)
                    Prefetch(
                        query=query_vector,
                        using="dense",
                        limit=limit * 2,  # Get more results for better fusion
                        query_filter=query_filter,
                    ),
                    # Prefetch from sparse vectors (keyword)
                    Prefetch(
                        query=sparse_query_vector,
                        using="sparse",
                        limit=limit * 2,
                        query_filter=query_filter,
                    ),
                ],
                limit=limit,
                score_threshold=score_threshold,
            )

            # Extract points from query result
            search_result = query_result.points if hasattr(query_result, 'points') else query_result

        else:
            raise ValueError(f"Invalid search_type: {search_type}. Must be 'semantic', 'keyword', or 'hybrid'")

        # Format results
        results = [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in search_result
        ]

        logger.info(f"Search returned {len(results)} results (type={search_type})")

        return results

    async def delete_document_vectors(self, document_id: UUID) -> Dict:
        """Delete all vectors for a specific document.

        Args:
            document_id: Document UUID

        Returns:
            Dictionary with deletion status
        """
        collection_name = self.COLLECTION_NAME

        logger.debug(f"Deleting vectors for document {document_id}")

        # Delete points by filter
        self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id)),
                    )
                ]
            ),
        )

        logger.info(f"✓ Deleted vectors for document {document_id}")

        return {
            "collection": collection_name,
            "document_id": str(document_id),
            "status": "deleted",
        }

    async def delete_vectors_by_ids(self, vector_ids: List[str]) -> Dict:
        """Delete vectors by their IDs.

        Args:
            vector_ids: List of vector IDs to delete

        Returns:
            Dictionary with deletion status
        """
        collection_name = self.COLLECTION_NAME

        logger.debug(f"Deleting {len(vector_ids)} vectors by ID")

        # Delete points by ID
        self.client.delete(
            collection_name=collection_name,
            points_selector=vector_ids,
        )

        logger.info(f"✓ Deleted {len(vector_ids)} vectors")

        return {
            "collection": collection_name,
            "deleted_count": len(vector_ids),
            "status": "deleted",
        }

    async def get_collection_info(self) -> Dict:
        """Get information about the collection.

        Returns:
            Dictionary with collection information
        """
        collection_name = self.COLLECTION_NAME

        try:
            info = self.client.get_collection(collection_name=collection_name)

            return {
                "name": collection_name,
                "vectors_count": info.vectors_count if hasattr(info, 'vectors_count') else 0,
                "points_count": info.points_count if hasattr(info, 'points_count') else 0,
                "status": info.status.name if hasattr(info, 'status') else "unknown",
            }
        except Exception as e:
            logger.warning(f"Could not get collection info: {e}")
            return {
                "name": collection_name,
                "error": str(e),
            }

    async def collection_exists(self) -> bool:
        """Check if the collection exists.

        Returns:
            True if collection exists, False otherwise
        """
        collections = self.client.get_collections().collections
        return any(c.name == self.COLLECTION_NAME for c in collections)

    async def count_vectors(self, document_filter: Optional[UUID] = None) -> int:
        """Count vectors in the collection, optionally filtered by document.

        Args:
            document_filter: Optional document UUID to filter by

        Returns:
            Number of vectors
        """
        collection_name = self.COLLECTION_NAME

        if document_filter:
            # Count with filter
            result = self.client.count(
                collection_name=collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(document_filter)),
                        )
                    ]
                ),
            )
            return result.count
        else:
            # Count all
            info = await self.get_collection_info()
            return info.get("points_count", 0)
