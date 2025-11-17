"""High-level LLM service with caching and fallback support."""

from typing import List, Optional
import logging
from app.llm.providers import LLMProvider

logger = logging.getLogger(__name__)


class LLMService:
    """High-level LLM service with fallback and caching."""

    def __init__(self, primary: LLMProvider, fallback: Optional[LLMProvider] = None):
        self.primary = primary
        self.fallback = fallback
        self._cache = {}
        logger.info("LLMService initialized")

    async def generate(self, prompt: str, use_cache: bool = True, **kwargs) -> str:
        cache_key = f"{prompt}:{kwargs.get('temperature', 0.1)}:{kwargs.get('max_tokens', 512)}"
        if use_cache and cache_key in self._cache:
            logger.debug(f"Cache hit for prompt: {prompt[:50]}...")
            return self._cache[cache_key]

        try:
            result = await self.primary.generate(prompt, **kwargs)
            if use_cache:
                self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.warning(f"Primary LLM failed: {e}")
            if self.fallback:
                logger.info("Attempting fallback LLM...")
                try:
                    result = await self.fallback.generate(prompt, **kwargs)
                    if use_cache:
                        self._cache[cache_key] = result
                    return result
                except Exception as fallback_error:
                    logger.error(f"Fallback LLM also failed: {fallback_error}")
                    raise
            else:
                raise

    async def generate_batch(self, prompts: List[str], **kwargs) -> List[str]:
        try:
            return await self.primary.generate_batch(prompts, **kwargs)
        except Exception as e:
            logger.warning(f"Primary LLM batch failed: {e}")
            if self.fallback:
                return await self.fallback.generate_batch(prompts, **kwargs)
            raise

    async def close(self):
        await self.primary.close()
        if self.fallback:
            await self.fallback.close()
