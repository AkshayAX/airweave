"""Sparse embedding service using SPLADE for keyword/BM25-like search.

Uses FastEmbed's SPLADE model for local sparse embedding generation.
"""

from typing import List, Optional
import logging
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)


class SparseEmbeddingService:
    """Service for generating sparse embeddings using SPLADE (local, no API calls).

    SPLADE generates sparse vectors similar to BM25 but with better semantic understanding.
    Singleton pattern to avoid reloading the model multiple times.
    """

    _instance: Optional["SparseEmbeddingService"] = None

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize (model loads lazily on first use)."""
        if self._initialized:
            return

        self._model = None
        # SPLADE model for sparse vectors (keyword-based search)
        self._model_name = "prithivida/Splade_PP_en_v1"
        self._initialized = True

        logger.debug(f"SparseEmbeddingService initialized (model: {self._model_name})")

    def _ensure_model_loaded(self):
        """Lazy load the FastEmbed SPLADE model."""
        if self._model is not None:
            return

        try:
            from fastembed import SparseTextEmbedding
        except ImportError:
            raise Exception(
                "FastEmbed not installed. Install with: pip install fastembed"
            )

        logger.info(f"Loading FastEmbed SPLADE model: {self._model_name}")

        try:
            # Initialize SPLADE model
            # This downloads the model on first use (~300MB, cached locally)
            self._model = SparseTextEmbedding(
                model_name=self._model_name,
            )

            logger.info(f"✓ SPLADE model loaded: {self._model_name}")

        except Exception as e:
            logger.error(f"Failed to load SPLADE model: {e}")
            raise Exception(f"SPLADE model loading failed: {e}")

    async def embed_texts(self, texts: List[str]) -> List[dict]:
        """Generate sparse embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of sparse embeddings (dict with 'indices' and 'values')
        """
        if not texts:
            return []

        self._ensure_model_loaded()

        try:
            # Generate sparse embeddings (run in thread pool to avoid blocking)
            def _generate():
                # FastEmbed SPLADE returns SparseEmbedding objects
                embeddings_gen = self._model.embed(texts)

                # Convert to list of dicts with indices and values
                embeddings = []
                for emb in embeddings_gen:
                    embeddings.append({
                        "indices": emb.indices.tolist(),
                        "values": emb.values.tolist(),
                    })

                return embeddings

            embeddings = await asyncio.to_thread(_generate)

            logger.debug(f"Generated {len(embeddings)} sparse embeddings")

            return embeddings

        except Exception as e:
            logger.error(f"Sparse embedding generation failed: {e}")
            raise

    async def embed_query(self, query: str) -> dict:
        """Generate sparse embedding for a single query.

        Args:
            query: Query text string

        Returns:
            Sparse embedding dict with 'indices' and 'values'
        """
        embeddings = await self.embed_texts([query])
        return embeddings[0] if embeddings else {"indices": [], "values": []}

    async def embed_documents(self, documents: List[str], batch_size: int = 32) -> List[dict]:
        """Generate sparse embeddings for documents in batches.

        Args:
            documents: List of document texts
            batch_size: Number of documents per batch

        Returns:
            List of sparse embedding dicts
        """
        if not documents:
            return []

        self._ensure_model_loaded()

        all_embeddings = []

        # Process in batches for better performance
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            batch_embeddings = await self.embed_texts(batch)
            all_embeddings.extend(batch_embeddings)

            logger.debug(
                f"Processed batch {i // batch_size + 1}/{(len(documents) + batch_size - 1) // batch_size}"
            )

        return all_embeddings

    def get_model_info(self) -> dict:
        """Get information about the current sparse embedding model.

        Returns:
            Dict with model information
        """
        return {
            "model_name": self._model_name,
            "model_type": "SPLADE (sparse)",
            "loaded": self._model is not None,
        }
