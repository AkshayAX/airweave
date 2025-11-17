"""Enhanced hybrid search service combining multiple search strategies.

Combines 5 search methods:
1. Vector search on chunk text (semantic)
2. Vector search on headers (semantic)
3. Sparse search on chunk text (BM25-like via SPLADE)
4. Fuzzy matching on headers
5. Exact matching on headers (part of fuzzy matcher)

Uses Reciprocal Rank Fusion (RRF) to combine results.
"""

from typing import List, Dict, Optional
from collections import defaultdict
from uuid import UUID
import asyncio
import logging

from app.search.vector_store import VectorStore
from app.search.qdrant_service import QdrantService
from app.search.embedding_service import EmbeddingService
from app.search.sparse_embedding_service import SparseEmbeddingService
from app.search.fuzzy_matcher import HeaderFuzzyMatcher
from app.core.config import settings

logger = logging.getLogger(__name__)


class EnhancedHybridSearch:
    """
    Enhanced hybrid search combining multiple search strategies.

    Uses Reciprocal Rank Fusion (RRF) to combine results from:
    - Semantic search on chunk text
    - Semantic search on headers
    - Keyword search (SPLADE)
    - Fuzzy matching on headers
    """

    def __init__(self):
        """Initialize enhanced hybrid search service."""
        self.qdrant = QdrantService()
        self.embedding_service = EmbeddingService()
        self.sparse_embedding_service = SparseEmbeddingService()
        self.fuzzy_matcher = HeaderFuzzyMatcher(min_score=settings.FUZZY_MATCH_MIN_SCORE)

        # RRF parameter (k=60 is standard)
        self.rrf_k = settings.RRF_K

        logger.info("EnhancedHybridSearch initialized")

    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        document_filter: Optional[UUID] = None,
        metadata_filters: Optional[Dict[str, any]] = None,
        user_email: Optional[str] = None,
        user_domains: Optional[List[str]] = None,
        enable_spell_correction: bool = True,
    ) -> List[Dict]:
        """
        Perform enhanced hybrid search.

        Args:
            query: Search query string
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            document_filter: Optional document UUID to filter by
            metadata_filters: Optional dict of metadata filters
            user_email: User email for access control
            user_domains: List of domains user has access to
            enable_spell_correction: Whether to correct spelling

        Returns:
            List of search results with scores and metadata
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        logger.info(f"Enhanced hybrid search: '{query[:50]}...' (user={user_email})")

        # Step 1: Spell correction (if enabled)
        corrected_query = query
        if enable_spell_correction and settings.ENABLE_SPELL_CORRECTION and settings.ENABLE_LLM:
            try:
                from app.llm import LLMProviderFactory, LLMService
                from app.llm.spell_corrector import SpellCorrector

                llm_provider = LLMProviderFactory.create(
                    provider_type=settings.LLM_PROVIDER,
                    base_url=settings.LLM_BASE_URL,
                    model_name=settings.LLM_MODEL,
                    timeout=settings.LLM_TIMEOUT,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )

                llm_service = LLMService(primary=llm_provider)
                spell_corrector = SpellCorrector(
                    llm_service,
                    min_query_length=settings.SPELL_CORRECTION_MIN_QUERY_LENGTH
                )

                corrected_query = await spell_corrector.correct(query)

                if corrected_query != query:
                    logger.info(f"Query corrected: '{query}' → '{corrected_query}'")

            except Exception as e:
                logger.warning(f"Spell correction failed: {e}, using original query")
                corrected_query = query

        # Step 2: Generate embeddings for corrected query
        logger.debug("Generating query embeddings...")
        query_dense_emb = await self.embedding_service.embed_query(corrected_query)
        query_sparse_emb = await self.sparse_embedding_service.embed_query(corrected_query)

        # Step 3: Parallel search with all methods
        logger.debug("Executing parallel searches...")

        # Increase limit for individual searches to get better candidates for fusion
        search_limit = limit * 3

        results = await asyncio.gather(
            # Method 1: Vector search on chunk text
            self._search_chunk_vectors(
                query_dense_emb,
                search_limit,
                score_threshold,
                document_filter,
                metadata_filters,
                user_email,
                user_domains
            ),

            # Method 2: Vector search on headers
            self._search_header_vectors(
                query_dense_emb,
                search_limit,
                score_threshold,
                document_filter,
                metadata_filters,
                user_email,
                user_domains
            ),

            # Method 3: Sparse search (BM25-like)
            self._search_sparse(
                query_sparse_emb,
                search_limit,
                score_threshold,
                document_filter,
                metadata_filters,
                user_email,
                user_domains
            ),

            # Method 4: Fuzzy match on headers
            self._fuzzy_search_headers(
                corrected_query,
                search_limit,
                document_filter,
                metadata_filters,
                user_email,
                user_domains
            ),

            return_exceptions=True
        )

        # Handle exceptions
        chunk_vector_results = results[0] if not isinstance(results[0], Exception) else []
        header_vector_results = results[1] if not isinstance(results[1], Exception) else []
        sparse_results = results[2] if not isinstance(results[2], Exception) else []
        fuzzy_results = results[3] if not isinstance(results[3], Exception) else []

        logger.info(
            f"Search results: chunk_vector={len(chunk_vector_results)}, "
            f"header_vector={len(header_vector_results)}, "
            f"sparse={len(sparse_results)}, fuzzy={len(fuzzy_results)}"
        )

        # Step 4: Rank fusion (RRF)
        fused_results = self._reciprocal_rank_fusion({
            "chunk_vector": chunk_vector_results,
            "header_vector": header_vector_results,
            "sparse": sparse_results,
            "fuzzy": fuzzy_results,
        })

        logger.info(f"RRF produced {len(fused_results)} fused results")

        return fused_results[:limit]

    async def _search_chunk_vectors(
        self,
        query_vector: List[float],
        limit: int,
        score_threshold: Optional[float],
        document_filter: Optional[UUID],
        metadata_filters: Optional[Dict],
        user_email: Optional[str],
        user_domains: Optional[List[str]]
    ) -> List[Dict]:
        """Search using chunk text vectors (semantic)."""
        try:
            results = await self.qdrant.search_vectors(
                query_vector=query_vector,
                sparse_query_vector=None,
                search_type="semantic",
                limit=limit,
                score_threshold=score_threshold,
                document_filter=document_filter,
                metadata_filters=metadata_filters,
                user_email=user_email,
                user_domains=user_domains
            )

            return [
                {
                    "id": r["payload"].get("document_id", "") + "_" + str(r["payload"].get("chunk_index", 0)),
                    "score": r["score"],
                    "method": "chunk_vector",
                    "payload": r["payload"]
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Chunk vector search failed: {e}")
            return []

    async def _search_header_vectors(
        self,
        query_vector: List[float],
        limit: int,
        score_threshold: Optional[float],
        document_filter: Optional[UUID],
        metadata_filters: Optional[Dict],
        user_email: Optional[str],
        user_domains: Optional[List[str]]
    ) -> List[Dict]:
        """Search using header vectors (semantic)."""
        try:
            from qdrant_client.models import NamedVector, Filter, FieldCondition, MatchValue, MatchAny

            # Build filters
            filter_conditions = []
            if document_filter:
                filter_conditions.append(
                    FieldCondition(key="document_id", match=MatchValue(value=str(document_filter)))
                )

            if metadata_filters:
                for field, value in metadata_filters.items():
                    filter_conditions.append(
                        FieldCondition(key=field, match=MatchValue(value=value))
                    )

            # Access control
            access_conditions = []
            access_conditions.append(FieldCondition(key="access_type", match=MatchValue(value="public")))

            if user_email:
                access_conditions.append(FieldCondition(key="owner_email", match=MatchValue(value=user_email)))

            if user_domains:
                for domain in user_domains:
                    access_conditions.append(FieldCondition(key="access_domains", match=MatchAny(any=[domain])))

            query_filter = None
            if access_conditions:
                if filter_conditions:
                    query_filter = Filter(must=filter_conditions, should=access_conditions)
                else:
                    query_filter = Filter(should=access_conditions)
            elif filter_conditions:
                query_filter = Filter(must=filter_conditions)

            # Search using header_dense vector
            search_result = self.qdrant.client.search(
                collection_name=self.qdrant.COLLECTION_NAME,
                query_vector=NamedVector(name="header_dense", vector=query_vector),
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter
            )

            return [
                {
                    "id": r.payload.get("document_id", "") + "_" + str(r.payload.get("chunk_index", 0)),
                    "score": r.score,
                    "method": "header_vector",
                    "payload": r.payload
                }
                for r in search_result
            ]
        except Exception as e:
            logger.error(f"Header vector search failed: {e}")
            return []

    async def _search_sparse(
        self,
        sparse_query_vector: Dict,
        limit: int,
        score_threshold: Optional[float],
        document_filter: Optional[UUID],
        metadata_filters: Optional[Dict],
        user_email: Optional[str],
        user_domains: Optional[List[str]]
    ) -> List[Dict]:
        """Search using sparse vectors (BM25-like)."""
        try:
            results = await self.qdrant.search_vectors(
                query_vector=None,
                sparse_query_vector=sparse_query_vector,
                search_type="keyword",
                limit=limit,
                score_threshold=score_threshold,
                document_filter=document_filter,
                metadata_filters=metadata_filters,
                user_email=user_email,
                user_domains=user_domains
            )

            return [
                {
                    "id": r["payload"].get("document_id", "") + "_" + str(r["payload"].get("chunk_index", 0)),
                    "score": r["score"],
                    "method": "sparse",
                    "payload": r["payload"]
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Sparse search failed: {e}")
            return []

    async def _fuzzy_search_headers(
        self,
        query: str,
        limit: int,
        document_filter: Optional[UUID],
        metadata_filters: Optional[Dict],
        user_email: Optional[str],
        user_domains: Optional[List[str]]
    ) -> List[Dict]:
        """Search using fuzzy matching on headers."""
        if not settings.ENABLE_FUZZY_MATCHING:
            return []

        try:
            # Fetch all headers from Qdrant (with filters)
            # For efficiency, we'll scroll through collection with filters
            from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

            # Build filters
            filter_conditions = []
            if document_filter:
                filter_conditions.append(
                    FieldCondition(key="document_id", match=MatchValue(value=str(document_filter)))
                )

            if metadata_filters:
                for field, value in metadata_filters.items():
                    filter_conditions.append(
                        FieldCondition(key=field, match=MatchValue(value=value))
                    )

            # Access control
            access_conditions = []
            access_conditions.append(FieldCondition(key="access_type", match=MatchValue(value="public")))

            if user_email:
                access_conditions.append(FieldCondition(key="owner_email", match=MatchValue(value=user_email)))

            if user_domains:
                for domain in user_domains:
                    access_conditions.append(FieldCondition(key="access_domains", match=MatchAny(any=[domain])))

            query_filter = None
            if access_conditions:
                if filter_conditions:
                    query_filter = Filter(must=filter_conditions, should=access_conditions)
                else:
                    query_filter = Filter(should=access_conditions)
            elif filter_conditions:
                query_filter = Filter(must=filter_conditions)

            # Scroll to get headers (limit to reasonable number for fuzzy matching)
            scroll_result = self.qdrant.client.scroll(
                collection_name=self.qdrant.COLLECTION_NAME,
                scroll_filter=query_filter,
                limit=1000,  # Reasonable limit for fuzzy matching
                with_payload=True,
                with_vectors=False
            )

            points = scroll_result[0] if scroll_result else []

            # Extract headers
            headers = []
            for point in points:
                header = point.payload.get("header", "")
                if header:
                    headers.append({
                        "id": point.payload.get("document_id", "") + "_" + str(point.payload.get("chunk_index", 0)),
                        "header": header,
                        "payload": point.payload
                    })

            # Fuzzy match
            fuzzy_results = self.fuzzy_matcher.search(query, headers, top_k=limit)

            return [
                {
                    "id": metadata["id"],
                    "score": score / 100.0,  # Normalize to 0-1
                    "method": "fuzzy",
                    "payload": metadata["payload"]
                }
                for header, score, metadata in fuzzy_results
            ]

        except Exception as e:
            logger.error(f"Fuzzy search failed: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        search_results: Dict[str, List[Dict]],
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) algorithm.

        Formula: score = Σ(1 / (k + rank))
        k=60 is standard (prevents high ranks from dominating)

        Args:
            search_results: Dict mapping method name to list of results

        Returns:
            List of fused results sorted by combined score
        """
        scores = defaultdict(float)
        metadata = {}
        method_ranks = defaultdict(dict)  # Track which methods contributed

        for method, results in search_results.items():
            for rank, result in enumerate(results, start=1):
                result_id = result["id"]

                # RRF score
                rrf_score = 1.0 / (self.rrf_k + rank)
                scores[result_id] += rrf_score

                # Store metadata (from first occurrence)
                if result_id not in metadata:
                    metadata[result_id] = result

                # Track method contribution
                method_ranks[result_id][method] = {
                    "rank": rank,
                    "score": result.get("score", 0),
                    "rrf_contribution": rrf_score
                }

        # Sort by fused score
        sorted_results = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Build final results
        final = []
        for result_id, fused_score in sorted_results:
            result = metadata[result_id].copy()
            result["fused_score"] = fused_score
            result["methods"] = method_ranks[result_id]
            final.append(result)

        return final
