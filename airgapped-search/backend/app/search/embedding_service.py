"""FastEmbed service for generating local embeddings.

Uses FastEmbed library for fast, local embedding generation without API calls.
"""

from typing import List, Optional
import logging
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using FastEmbed (local, no API calls).

    Singleton pattern to avoid reloading the model multiple times.
    """

    _instance: Optional["EmbeddingService"] = None

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
        self._model_name = settings.EMBEDDING_MODEL
        self._embedding_dimension = settings.EMBEDDING_DIMENSION
        self._initialized = True

        logger.debug(f"EmbeddingService initialized (model: {self._model_name})")

    def _ensure_model_loaded(self):
        """Lazy load the FastEmbed model."""
        if self._model is not None:
            return

        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise Exception(
                "FastEmbed not installed. Install with: pip install fastembed"
            )

        logger.info(f"Loading FastEmbed model: {self._model_name}")

        try:
            # Initialize FastEmbed model
            # This downloads the model on first use (~50-100MB, cached locally)
            self._model = TextEmbedding(
                model_name=self._model_name,
                max_length=512,  # Maximum sequence length
            )

            logger.info(f"✓ FastEmbed model loaded: {self._model_name}")

        except Exception as e:
            logger.error(f"Failed to load FastEmbed model: {e}")
            raise Exception(f"FastEmbed model loading failed: {e}")

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (floats)
        """
        if not texts:
            return []

        self._ensure_model_loaded()

        try:
            # Generate embeddings (run in thread pool to avoid blocking)
            def _generate():
                # FastEmbed returns a generator, convert to list
                embeddings = list(self._model.embed(texts))
                # Convert numpy arrays to lists
                return [embedding.tolist() for embedding in embeddings]

            embeddings = await asyncio.to_thread(_generate)

            logger.debug(f"Generated {len(embeddings)} embeddings")

            # Validate dimensions
            for i, emb in enumerate(embeddings):
                if len(emb) != self._embedding_dimension:
                    raise Exception(
                        f"Embedding {i} has wrong dimension: "
                        f"{len(emb)} != {self._embedding_dimension}"
                    )

            return embeddings

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a single query.

        Args:
            query: Query text string

        Returns:
            Embedding vector (floats)
        """
        embeddings = await self.embed_texts([query])
        return embeddings[0] if embeddings else []

    async def embed_documents(self, documents: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for documents in batches.

        Args:
            documents: List of document texts
            batch_size: Number of documents per batch

        Returns:
            List of embedding vectors
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
        """Get information about the current embedding model.

        Returns:
            Dict with model information
        """
        return {
            "model_name": self._model_name,
            "embedding_dimension": self._embedding_dimension,
            "loaded": self._model is not None,
        }
