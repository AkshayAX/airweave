"""PDF to markdown converter using pdfminer.

Local PDF extraction for air-gapped operation.
"""

import asyncio
from typing import Dict, List
import logging

from .base import BaseTextConverter

logger = logging.getLogger(__name__)


class PdfConverter(BaseTextConverter):
    """Converts PDF files to markdown using pdfminer-six (local extraction)."""

    async def convert_batch(self, file_paths: List[str]) -> Dict[str, str]:
        """Convert PDF files to markdown text.

        Args:
            file_paths: List of PDF file paths to convert

        Returns:
            Dict mapping file_path -> markdown text content (None if failed)
        """
        try:
            from pdfminer.high_level import extract_text
        except ImportError:
            logger.error("pdfminer-six package not installed for PDF conversion")
            return {path: None for path in file_paths}

        logger.info(f"Converting {len(file_paths)} PDF files to markdown...")

        results = {}
        semaphore = asyncio.Semaphore(5)  # Limit concurrent PDF processing

        async def _convert_one(path: str):
            async with semaphore:
                try:
                    def _extract():
                        # Extract text from PDF
                        text = extract_text(path)
                        return text.strip() if text else None

                    text = await asyncio.to_thread(_extract)

                    if text:
                        results[path] = text
                        logger.debug(f"Converted PDF file: {path} ({len(text)} characters)")
                    else:
                        logger.warning(f"PDF conversion produced no content for {path}")
                        results[path] = None

                except Exception as e:
                    logger.error(f"PDF conversion failed for {path}: {e}")
                    results[path] = None

        await asyncio.gather(*[_convert_one(p) for p in file_paths], return_exceptions=True)

        successful = sum(1 for r in results.values() if r)
        logger.info(f"PDF conversion complete: {successful}/{len(file_paths)} files successful")

        return results
