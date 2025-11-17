"""Spell correction service using LLM."""

from typing import Optional
import logging
from app.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class SpellCorrector:
    """Lightweight spell correction using LLM."""

    CORRECTION_PROMPT = """Correct spelling mistakes in this query. Return ONLY the corrected text.
If no mistakes, return the original unchanged.

Query: {query}
Corrected:"""

    def __init__(self, llm_service: Optional[LLMService] = None, min_query_length: int = 4):
        self.llm = llm_service
        self.min_query_length = min_query_length
        self._cache = {}

    async def correct(self, query: str) -> str:
        if not self.llm:
            return query

        if query in self._cache:
            return self._cache[query]

        if len(query) <= self.min_query_length:
            return query

        try:
            prompt = self.CORRECTION_PROMPT.format(query=query)
            corrected = await self.llm.generate(prompt, temperature=0.1, max_tokens=50)
            corrected = corrected.strip().strip('"\'').strip()

            if not corrected or len(corrected) < len(query) * 0.5:
                corrected = query

            self._cache[query] = corrected

            if corrected.lower() != query.lower():
                logger.info(f"Spell corrected: '{query}' → '{corrected}'")

            return corrected
        except Exception as e:
            logger.warning(f"Spell correction failed: {e}")
            return query
