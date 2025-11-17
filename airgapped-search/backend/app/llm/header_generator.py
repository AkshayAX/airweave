"""Header generation service using LLM."""

from typing import List, Optional
import logging
from app.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class HeaderGenerator:
    """Generates headers for text chunks using LLM."""

    HEADER_GENERATION_PROMPT = """Generate a concise, descriptive header for this text chunk.
Requirements:
- 5-10 words maximum
- Capture the main topic and key information
- Use searchable keywords
- Be specific and clear
- Do not use quotes or punctuation at the end

Text chunk:
{chunk_text}

Header (5-10 words):"""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service
        self._cache = {}

    async def generate_header(self, chunk_text: str) -> str:
        if not self.llm:
            return self._fallback_header(chunk_text)

        if chunk_text in self._cache:
            return self._cache[chunk_text]

        truncated_text = chunk_text[:2000] if len(chunk_text) > 2000 else chunk_text

        try:
            prompt = self.HEADER_GENERATION_PROMPT.format(chunk_text=truncated_text)
            header = await self.llm.generate(prompt, use_cache=True, temperature=0.1, max_tokens=50)
            header = header.strip().strip('"\'').strip()

            if not header or len(header.split()) < 2:
                header = self._fallback_header(chunk_text)
            elif len(header.split()) > 15:
                header = " ".join(header.split()[:10])

            self._cache[chunk_text] = header
            return header
        except Exception as e:
            logger.error(f"Header generation failed: {e}")
            return self._fallback_header(chunk_text)

    async def generate_headers_batch(self, chunk_texts: List[str]) -> List[str]:
        if not self.llm:
            return [self._fallback_header(text) for text in chunk_texts]

        try:
            prompts = [self.HEADER_GENERATION_PROMPT.format(
                chunk_text=text[:2000] if len(text) > 2000 else text) for text in chunk_texts]
            headers = await self.llm.generate_batch(prompts, temperature=0.1, max_tokens=50)

            cleaned_headers = []
            for i, header in enumerate(headers):
                header = header.strip().strip('"\'').strip()
                if not header or len(header.split()) < 2:
                    header = self._fallback_header(chunk_texts[i])
                elif len(header.split()) > 15:
                    header = " ".join(header.split()[:10])
                cleaned_headers.append(header)
                self._cache[chunk_texts[i]] = header

            logger.info(f"Generated {len(cleaned_headers)} headers in batch")
            return cleaned_headers
        except Exception as e:
            logger.error(f"Batch header generation failed: {e}")
            return [self._fallback_header(text) for text in chunk_texts]

    def _fallback_header(self, chunk_text: str) -> str:
        first_line = chunk_text.split('\n')[0].strip()
        if not first_line:
            first_line = chunk_text.strip()
        if len(first_line) > 50:
            words = first_line[:50].split()
            first_line = " ".join(words[:-1]) + "..."
        return first_line if first_line else "Document Chunk"
