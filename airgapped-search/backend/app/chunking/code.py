"""Code chunker using AST-based parsing for logical code boundaries.

Adapted from Airweave for air-gapped operation.
Uses chonkie library with tree-sitter for AST parsing - completely local.
"""

import asyncio
from typing import Any, Dict, List, Optional
import logging

from .base import BaseChunker

logger = logging.getLogger(__name__)


class CodeChunker(BaseChunker):
    """Singleton code chunker with AST-based parsing (no API calls).

    Two-stage approach:
    1. CodeChunker: Chunks at logical code boundaries (functions, classes, methods)
    2. TokenChunker fallback: Force-splits any oversized chunks at token boundaries

    The chunker is shared to avoid reloading language detection model multiple times.
    """

    # Configuration constants
    MAX_TOKENS_PER_CHUNK = 8192  # OpenAI hard limit
    CHUNK_SIZE = 2048  # Target chunk size
    TOKENIZER = "cl100k_base"  # OpenAI-compatible tokenizer

    # Singleton instance
    _instance: Optional["CodeChunker"] = None

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

        self._code_chunker = None  # Lazy init
        self._token_chunker = None  # Lazy init
        self._tiktoken_tokenizer = None  # Lazy init
        self._initialized = True

        logger.debug(
            f"CodeChunker initialized "
            f"(target: {self.CHUNK_SIZE}, max: {self.MAX_TOKENS_PER_CHUNK})"
        )

    def _ensure_chunkers(self):
        """Lazy initialization of chunker models."""
        if self._code_chunker is not None:
            return

        try:
            import tiktoken
            from chonkie import CodeChunker as ChonkieCodeChunker
            from chonkie import TokenChunker
        except ImportError as e:
            raise Exception(
                f"Chunking dependencies not installed: {e}. "
                "Install with: pip install chonkie tiktoken"
            )

        try:
            # Initialize tiktoken tokenizer
            self._tiktoken_tokenizer = tiktoken.get_encoding(self.TOKENIZER)

            # Initialize code chunker with auto language detection
            # Uses Magika (Google's ML-based language detector) + tree-sitter
            self._code_chunker = ChonkieCodeChunker(
                language="auto",  # Auto-detect using Magika
                tokenizer=self._tiktoken_tokenizer,
                chunk_size=self.CHUNK_SIZE,
                include_nodes=False,  # Don't include AST node types in output
            )

            # Initialize token chunker for fallback
            self._token_chunker = TokenChunker(
                tokenizer=self._tiktoken_tokenizer,
                chunk_size=self.MAX_TOKENS_PER_CHUNK,
                chunk_overlap=0,
            )

            logger.info(
                f"Loaded CodeChunker (auto-detect, target: {self.CHUNK_SIZE}, "
                f"max: {self.MAX_TOKENS_PER_CHUNK})"
            )

        except Exception as e:
            raise Exception(f"Failed to initialize code chunker: {e}")

    async def chunk_batch(self, texts: List[str]) -> List[List[Dict[str, Any]]]:
        """Chunk a batch of code texts with AST-based chunking.

        Args:
            texts: List of code textual representations to chunk

        Returns:
            List of chunk lists (one per input text)
        """
        self._ensure_chunkers()

        # Stage 1: AST-based code chunking
        try:
            code_results = await asyncio.to_thread(
                self._code_chunker.chunk_batch, texts
            )
        except Exception as e:
            raise Exception(f"Code chunking failed: {e}")

        # Stage 2: Safety net for oversized chunks
        final_results = await asyncio.to_thread(
            self._apply_safety_net_batched, code_results
        )

        # Validation
        for doc_chunks in final_results:
            for chunk in doc_chunks:
                if not chunk["text"] or not chunk["text"].strip():
                    raise Exception("Empty chunk produced")
                if chunk["token_count"] > self.MAX_TOKENS_PER_CHUNK:
                    raise Exception(f"Chunk exceeds max tokens: {chunk['token_count']}")

        return final_results

    def _apply_safety_net_batched(self, code_results: List[List[Any]]) -> List[List[Dict[str, Any]]]:
        """Split oversized chunks using TokenChunker fallback."""
        final_results = []

        for doc_chunks in code_results:
            new_doc_chunks = []
            for chunk in doc_chunks:
                # Get token count
                tokens = self._tiktoken_tokenizer.encode(chunk.text)
                token_count = len(tokens)

                if token_count <= self.MAX_TOKENS_PER_CHUNK:
                    # Chunk is fine
                    new_doc_chunks.append({
                        "text": chunk.text,
                        "start_index": chunk.start_index,
                        "end_index": chunk.end_index,
                        "token_count": token_count,
                    })
                else:
                    # Split oversized chunk
                    logger.warning(
                        f"Code chunk exceeded {self.MAX_TOKENS_PER_CHUNK} tokens "
                        f"({token_count}), splitting with TokenChunker"
                    )
                    split_chunks = self._token_chunker.chunk(chunk.text)

                    for split_chunk in split_chunks:
                        split_tokens = self._tiktoken_tokenizer.encode(split_chunk.text)
                        new_doc_chunks.append({
                            "text": split_chunk.text,
                            "start_index": split_chunk.start_index + chunk.start_index,
                            "end_index": split_chunk.end_index + chunk.start_index,
                            "token_count": len(split_tokens),
                        })

            final_results.append(new_doc_chunks)

        return final_results
