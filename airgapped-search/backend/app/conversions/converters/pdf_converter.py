"""PDF to markdown converter using pdf2image + DeepSeek-OCR.

Uses DeepSeek-OCR for high-quality extraction of text, tables, and layout.
"""

import asyncio
from typing import Dict, List
import logging
from PIL import Image

from .base import BaseTextConverter
from .deepseek_ocr_converter import DeepSeekOCRConverter

logger = logging.getLogger(__name__)


class PdfConverter(BaseTextConverter):
    """Converts PDF files to markdown using pdf2image + DeepSeek-OCR."""

    def __init__(self, ocr_converter: DeepSeekOCRConverter = None):
        """Initialize PDF converter.

        Args:
            ocr_converter: Shared DeepSeek-OCR converter instance (reuses loaded model)
        """
        self._ocr_converter = ocr_converter

    async def convert_batch(self, file_paths: List[str]) -> Dict[str, str]:
        """Convert PDF files to markdown text via OCR.

        Args:
            file_paths: List of PDF file paths to convert

        Returns:
            Dict mapping file_path -> markdown text content (None if failed)
        """
        try:
            from pdf2image import convert_from_path
        except ImportError:
            logger.error("pdf2image package not installed for PDF conversion")
            return {path: None for path in file_paths}

        if not self._ocr_converter:
            logger.error("DeepSeek-OCR converter not provided for PDF conversion")
            return {path: None for path in file_paths}

        logger.info(f"Converting {len(file_paths)} PDF files to markdown via OCR...")

        results = {}
        semaphore = asyncio.Semaphore(2)  # Limit concurrent PDF processing (OCR is heavy)

        async def _convert_one(path: str):
            async with semaphore:
                try:
                    def _pdf_to_images():
                        # Convert PDF pages to images
                        # Use lower DPI for faster processing, DeepSeek-OCR handles it well
                        images = convert_from_path(path, dpi=150)
                        return images

                    images = await asyncio.to_thread(_pdf_to_images)

                    if not images:
                        logger.warning(f"PDF conversion produced no images for {path}")
                        results[path] = None
                        return

                    logger.debug(f"PDF {path} converted to {len(images)} page images")

                    # Run OCR on all pages
                    page_texts = []
                    for i, image in enumerate(images):
                        page_text = await self._ocr_converter._ocr_single_image(
                            image,
                            f"{path}_page{i+1}"
                        )
                        if page_text:
                            page_texts.append(f"# Page {i+1}\n\n{page_text}")

                    if page_texts:
                        full_text = "\n\n---\n\n".join(page_texts)
                        results[path] = full_text
                        logger.debug(f"Converted PDF file via OCR: {path} ({len(full_text)} characters)")
                    else:
                        logger.warning(f"PDF OCR produced no content for {path}")
                        results[path] = None

                except Exception as e:
                    logger.error(f"PDF conversion failed for {path}: {e}")
                    results[path] = None

        await asyncio.gather(*[_convert_one(p) for p in file_paths], return_exceptions=True)

        successful = sum(1 for r in results.values() if r)
        logger.info(f"PDF conversion complete: {successful}/{len(file_paths)} files successful")

        return results
