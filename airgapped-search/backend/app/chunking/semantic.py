"""Semantic chunker using local embedding model for boundary detection.

Adapted from Airweave for air-gapped operation.
Uses chonkie library with local Model2Vec embeddings - no API calls required.
"""

import asyncio
from typing import Any, Dict, List, Optional
import logging

from .base import BaseChunker

logger = logging.getLogger(__name__)


class SemanticChunker(BaseChunker):
    """Singleton semantic chunker with local inference (no API calls).

    Two-stage chunking approach:
    1. SemanticChunker: Detects semantic boundaries via embedding similarity
    2. TokenChunker fallback: Force-splits any oversized chunks at token boundaries

    The chunker is shared to avoid reloading the embedding model multiple times.
    """

    # Configuration constants
    MAX_TOKENS_PER_CHUNK = 8192  # Hard limit (OpenAI compatibility)
    SEMANTIC_CHUNK_SIZE = 2048  # Soft target for semantic groups
    OVERLAP_TOKENS = 128  # Token overlap between chunks

    # SemanticChunker configuration
    EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # Same model as vector search for consistency
    SIMILARITY_THRESHOLD = 0.3  # 0-1: Lower=larger chunks, Higher=smaller chunks
    SIMILARITY_WINDOW = 10  # Number of sentences to compare
    MIN_SENTENCES_PER_CHUNK = 1
    MIN_CHARACTERS_PER_SENTENCE = 24

    # Advanced features
    SKIP_WINDOW = 0  # Merge non-consecutive similar groups
    FILTER_WINDOW = 5  # Savitzky-Golay filter window
    FILTER_POLYORDER = 3
    FILTER_TOLERANCE = 0.2

    # Sentence splitting
    SENTENCE_DELIMITERS = [". ", "! ", "? ", "\n"]
    INCLUDE_DELIMITER = "prev"

    # Tokenizer
    TOKENIZER = "cl100k_base"  # OpenAI-compatible tokenizer

    # Singleton instance
    _instance: Optional["SemanticChunker"] = None

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize once (models load lazily on first use)."""
        if self._initialized:
            return

        self._semantic_chunker = None  # Lazy init
        self._token_chunker = None  # Lazy init
        self._tiktoken_tokenizer = None  # Lazy init
        self._initialized = True

        logger.debug(
            f"SemanticChunker initialized "
            f"(model: {self.EMBEDDING_MODEL}, max_tokens: {self.MAX_TOKENS_PER_CHUNK})"
        )

    def _ensure_chunkers(self):
        """Lazy initialization of chunker models."""
        if self._semantic_chunker is not None:
            return

        try:
            import tiktoken
            from chonkie import SemanticChunker as ChonkieSemanticChunker
            from chonkie import TokenChunker
        except ImportError as e:
            raise Exception(
                f"Chunking dependencies not installed: {e}. "
                "Install with: pip install chonkie tiktoken"
            )

        try:
            # Initialize tiktoken tokenizer
            self._tiktoken_tokenizer = tiktoken.get_encoding(self.TOKENIZER)

            # Initialize semantic chunker (uses local Model2Vec model)
            self._semantic_chunker = ChonkieSemanticChunker(
                embedding_model=self.EMBEDDING_MODEL,
                chunk_size=self.SEMANTIC_CHUNK_SIZE,
                threshold=self.SIMILARITY_THRESHOLD,
                similarity_window=self.SIMILARITY_WINDOW,
                min_sentences_per_chunk=self.MIN_SENTENCES_PER_CHUNK,
                min_characters_per_sentence=self.MIN_CHARACTERS_PER_SENTENCE,
                delim=self.SENTENCE_DELIMITERS,
                include_delim=self.INCLUDE_DELIMITER,
                skip_window=self.SKIP_WINDOW,
                filter_window=self.FILTER_WINDOW,
                filter_polyorder=self.FILTER_POLYORDER,
                filter_tolerance=self.FILTER_TOLERANCE,
            )

            # Initialize token chunker for fallback
            self._token_chunker = TokenChunker(
                tokenizer=self._tiktoken_tokenizer,
                chunk_size=self.MAX_TOKENS_PER_CHUNK,
                chunk_overlap=0,
            )

            logger.info(
                f"Loaded SemanticChunker (model: {self.EMBEDDING_MODEL}, "
                f"target: {self.SEMANTIC_CHUNK_SIZE}, max: {self.MAX_TOKENS_PER_CHUNK})"
            )

        except Exception as e:
            raise Exception(f"Failed to initialize semantic chunker: {e}")

    async def chunk_batch(self, texts: List[str]) -> List[List[Dict[str, Any]]]:
        """Chunk a batch of texts with semantic chunking + token fallback.

        Args:
            texts: List of textual representations to chunk

        Returns:
            List of chunk lists (one per input text)
        """
        self._ensure_chunkers()

        # Stage 1: Semantic chunking (finds topic boundaries)
        try:
            semantic_results = await asyncio.to_thread(
                self._semantic_chunker.chunk_batch, texts
            )
        except Exception as e:
            raise Exception(f"Semantic chunking failed: {e}")

        # Stage 2: Recount tokens with tiktoken
        semantic_results_with_tiktoken = await asyncio.to_thread(
            self._recount_tokens_with_tiktoken, semantic_results
        )

        # Stage 3: Safety net for oversized chunks
        final_results = await asyncio.to_thread(
            self._apply_safety_net_batched, semantic_results_with_tiktoken
        )

        # Validation
        for doc_chunks in final_results:
            for chunk in doc_chunks:
                if not chunk["text"] or not chunk["text"].strip():
                    raise Exception("Empty chunk produced")
                if chunk["token_count"] > self.MAX_TOKENS_PER_CHUNK:
                    raise Exception(f"Chunk exceeds max tokens: {chunk['token_count']}")

        return final_results

    def _recount_tokens_with_tiktoken(self, results: List[List[Any]]) -> List[List[Dict[str, Any]]]:
        """Recount tokens using tiktoken for OpenAI compatibility."""
        new_results = []
        for doc_chunks in results:
            new_doc_chunks = []
            for chunk in doc_chunks:
                # Recount tokens with tiktoken
                tokens = self._tiktoken_tokenizer.encode(chunk.text)
                token_count = len(tokens)

                new_doc_chunks.append({
                    "text": chunk.text,
                    "start_index": chunk.start_index,
                    "end_index": chunk.end_index,
                    "token_count": token_count,
                })
            new_results.append(new_doc_chunks)
        return new_results

    def _apply_safety_net_batched(self, results: List[List[Dict[str, Any]]]) -> List[List[Dict[str, Any]]]:
        """Split oversized chunks using TokenChunker fallback."""
        final_results = []

        for doc_chunks in results:
            new_doc_chunks = []
            for chunk in doc_chunks:
                if chunk["token_count"] <= self.MAX_TOKENS_PER_CHUNK:
                    # Chunk is fine
                    new_doc_chunks.append(chunk)
                else:
                    # Split oversized chunk
                    logger.warning(
                        f"Chunk exceeded {self.MAX_TOKENS_PER_CHUNK} tokens "
                        f"({chunk['token_count']}), splitting with TokenChunker"
                    )
                    split_chunks = self._token_chunker.chunk(chunk["text"])

                    for split_chunk in split_chunks:
                        tokens = self._tiktoken_tokenizer.encode(split_chunk.text)
                        new_doc_chunks.append({
                            "text": split_chunk.text,
                            "start_index": split_chunk.start_index + chunk["start_index"],
                            "end_index": split_chunk.end_index + chunk["start_index"],
                            "token_count": len(tokens),
                        })

            final_results.append(new_doc_chunks)

        return final_results
