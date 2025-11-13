"""PPTX to markdown converter using LibreOffice + pdf2image + DeepSeek-OCR.

Uses LibreOffice to convert PPTX to PDF, then DeepSeek-OCR for extraction.
"""

import asyncio
import subprocess
import tempfile
import os
from typing import Dict, List
import logging
from pathlib import Path

from .base import BaseTextConverter
from .pdf_converter import PdfConverter
from .deepseek_ocr_converter import DeepSeekOCRConverter

logger = logging.getLogger(__name__)


class PptxConverter(BaseTextConverter):
    """Converts PPTX files to markdown using LibreOffice + pdf2image + DeepSeek-OCR."""

    def __init__(self, ocr_converter: DeepSeekOCRConverter = None):
        """Initialize PPTX converter.

        Args:
            ocr_converter: Shared DeepSeek-OCR converter instance (reuses loaded model)
        """
        self._ocr_converter = ocr_converter
        self._pdf_converter = PdfConverter(ocr_converter=ocr_converter)

    async def convert_batch(self, file_paths: List[str]) -> Dict[str, str]:
        """Convert PPTX files to markdown text via LibreOffice + OCR.

        Args:
            file_paths: List of PPTX file paths to convert

        Returns:
            Dict mapping file_path -> markdown text content (None if failed)
        """
        logger.info(f"Converting {len(file_paths)} PPTX files to markdown via OCR...")

        results = {}
        semaphore = asyncio.Semaphore(2)  # Limit concurrent PPTX processing

        async def _convert_one(path: str):
            async with semaphore:
                temp_pdf = None
                try:
                    # Step 1: Convert PPTX to PDF using LibreOffice
                    with tempfile.TemporaryDirectory() as tmpdir:
                        def _pptx_to_pdf():
                            # Use soffice (LibreOffice command-line tool) to convert to PDF
                            # --headless: Run without GUI
                            # --convert-to pdf: Output format
                            # --outdir: Output directory
                            result = subprocess.run(
                                [
                                    "soffice",
                                    "--headless",
                                    "--convert-to",
                                    "pdf",
                                    "--outdir",
                                    tmpdir,
                                    path,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=60,  # 60 second timeout
                            )

                            if result.returncode != 0:
                                raise Exception(f"LibreOffice conversion failed: {result.stderr}")

                            # Find the generated PDF
                            pdf_files = list(Path(tmpdir).glob("*.pdf"))
                            if not pdf_files:
                                raise Exception("LibreOffice did not produce a PDF file")

                            return str(pdf_files[0])

                        temp_pdf = await asyncio.to_thread(_pptx_to_pdf)
                        logger.debug(f"Converted PPTX to PDF: {path} -> {temp_pdf}")

                        # Step 2: Convert PDF to markdown using PDF converter (which uses OCR)
                        pdf_results = await self._pdf_converter.convert_batch([temp_pdf])
                        text = pdf_results.get(temp_pdf)

                        if text:
                            results[path] = text
                            logger.debug(f"Converted PPTX file via OCR: {path} ({len(text)} characters)")
                        else:
                            logger.warning(f"PPTX conversion produced no content for {path}")
                            results[path] = None

                except subprocess.TimeoutExpired:
                    logger.error(f"PPTX conversion timed out for {path}")
                    results[path] = None
                except Exception as e:
                    logger.error(f"PPTX conversion failed for {path}: {e}")
                    results[path] = None

        await asyncio.gather(*[_convert_one(p) for p in file_paths], return_exceptions=True)

        successful = sum(1 for r in results.values() if r)
        logger.info(f"PPTX conversion complete: {successful}/{len(file_paths)} files successful")

        return results
