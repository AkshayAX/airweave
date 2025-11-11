"""Qdrant vector database service for managing collections and search.

Handles connection, collection management, and vector operations.
"""

from typing import Dict, List, Optional
from uuid import UUID
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for interacting with Qdrant vector database.

    Manages collections per organization for multi-tenant isolation.
    """

    def __init__(self):
        """Initialize Qdrant client."""
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=60,  # Increased timeout for large batches
        )
        self.embedding_dimension = settings.EMBEDDING_DIMENSION
        logger.info(f"Qdrant client initialized: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")

    def get_collection_name(self, organization_id: UUID) -> str:
        """Get collection name for an organization.

        Args:
            organization_id: Organization UUID

        Returns:
            Collection name string
        """
        return f"org_{str(organization_id).replace('-', '_')}"

    async def ensure_collection_exists(self, organization_id: UUID) -> str:
        """Ensure a collection exists for the organization.

        Creates the collection if it doesn't exist.

        Args:
            organization_id: Organization UUID

        Returns:
            Collection name
        """
        collection_name = self.get_collection_name(organization_id)

        # Check if collection exists
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            raise

        if not exists:
            # Create collection
            try:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {collection_name}")
            except Exception as e:
                logger.error(f"Failed to create collection {collection_name}: {e}")
                raise

        return collection_name

    async def upsert_vectors(
        self,
        organization_id: UUID,
        points: List[PointStruct],
    ) -> Dict[str, int]:
        """Insert or update vectors in the collection.

        Args:
            organization_id: Organization UUID
            points: List of PointStruct objects with vectors and payloads

        Returns:
            Dict with operation statistics
        """
        collection_name = await self.ensure_collection_exists(organization_id)

        try:
            # Upsert points
            operation_info = self.client.upsert(
                collection_name=collection_name,
                points=points,
            )

            logger.info(
                f"Upserted {len(points)} vectors to {collection_name}. "
                f"Status: {operation_info.status}"
            )

            return {
                "collection": collection_name,
                "upserted": len(points),
                "status": operation_info.status,
            }

        except Exception as e:
            logger.error(f"Failed to upsert vectors to {collection_name}: {e}")
            raise

    async def search_vectors(
        self,
        organization_id: UUID,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict]:
        """Search for similar vectors in the collection.

        Args:
            organization_id: Organization UUID
            query_vector: Query embedding vector
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            filter_conditions: Optional metadata filters

        Returns:
            List of search results with scores and payloads
        """
        collection_name = self.get_collection_name(organization_id)

        # Check if collection exists
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)
            if not exists:
                logger.warning(f"Collection {collection_name} does not exist")
                return []
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            raise

        # Build filter
        search_filter = None
        if filter_conditions:
            # Build Qdrant filter from conditions
            field_conditions = []
            for field, value in filter_conditions.items():
                field_conditions.append(
                    FieldCondition(key=field, match=MatchValue(value=value))
                )
            if field_conditions:
                search_filter = Filter(must=field_conditions)

        try:
            # Perform search
            search_results = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter,
            )

            results = []
            for hit in search_results:
                results.append({
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                })

            logger.debug(f"Vector search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Vector search failed in {collection_name}: {e}")
            raise

    async def delete_vectors(
        self,
        organization_id: UUID,
        point_ids: List[str],
    ) -> Dict[str, int]:
        """Delete vectors from the collection.

        Args:
            organization_id: Organization UUID
            point_ids: List of point IDs to delete

        Returns:
            Dict with operation statistics
        """
        collection_name = self.get_collection_name(organization_id)

        try:
            operation_info = self.client.delete(
                collection_name=collection_name,
                points_selector=point_ids,
            )

            logger.info(f"Deleted {len(point_ids)} vectors from {collection_name}")

            return {
                "collection": collection_name,
                "deleted": len(point_ids),
                "status": operation_info.status,
            }

        except Exception as e:
            logger.error(f"Failed to delete vectors from {collection_name}: {e}")
            raise

    async def delete_document_vectors(
        self,
        organization_id: UUID,
        document_id: UUID,
    ) -> Dict[str, int]:
        """Delete all vectors for a document.

        Args:
            organization_id: Organization UUID
            document_id: Document UUID

        Returns:
            Dict with operation statistics
        """
        collection_name = self.get_collection_name(organization_id)

        try:
            # Delete by filter
            operation_info = self.client.delete(
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

            logger.info(f"Deleted vectors for document {document_id} from {collection_name}")

            return {
                "collection": collection_name,
                "document_id": str(document_id),
                "status": operation_info.status,
            }

        except Exception as e:
            logger.error(f"Failed to delete document vectors: {e}")
            raise

    async def get_collection_info(self, organization_id: UUID) -> Dict:
        """Get collection information and statistics.

        Args:
            organization_id: Organization UUID

        Returns:
            Dict with collection information
        """
        collection_name = self.get_collection_name(organization_id)

        try:
            info = self.client.get_collection(collection_name=collection_name)

            return {
                "name": collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
            }

        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {
                "name": collection_name,
                "error": str(e),
            }
