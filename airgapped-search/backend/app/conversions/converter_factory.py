"""Factory for getting appropriate document converter based on file type."""

from typing import Dict

from app.conversions.converters.base import BaseTextConverter
from app.conversions.converters.pdf_converter import PdfConverter
from app.conversions.converters.docx_converter import DocxConverter
from app.conversions.converters.pptx_converter import PptxConverter
from app.conversions.converters.xlsx_converter import XlsxConverter
from app.conversions.converters.html_converter import HtmlConverter
from app.conversions.converters.txt_converter import TxtConverter
from app.conversions.converters.code_converter import CodeConverter
from app.conversions.converters.deepseek_ocr_converter import DeepSeekOCRConverter
from app.core.config import settings


class ConverterFactory:
    """Factory class to get appropriate converter for a file type.

    This implements a singleton pattern for converters to avoid
    reloading heavy resources (like OCR models) repeatedly.

    PDF, DOCX, and PPTX converters now use DeepSeek-OCR for high-quality
    extraction of text, tables, images, and layout.
    """

    # Singleton converter instances
    _converters: Dict[str, BaseTextConverter] = {}
    _ocr_converter: DeepSeekOCRConverter = None

    @classmethod
    def _get_ocr_converter(cls) -> DeepSeekOCRConverter:
        """Get or create the shared OCR converter instance."""
        if not settings.ENABLE_OCR:
            raise ValueError(
                f"OCR is disabled. Enable it in settings to process documents. "
                f"Set ENABLE_OCR=true in environment."
            )

        if cls._ocr_converter is None:
            cls._ocr_converter = DeepSeekOCRConverter(
                device=settings.OCR_DEVICE,
                batch_size=settings.OCR_BATCH_SIZE,
            )

        return cls._ocr_converter

    @classmethod
    def get_converter(cls, file_type: str) -> BaseTextConverter:
        """Get appropriate converter for file type.

        Args:
            file_type: Type of file (pdf, docx, pptx, xlsx, html, txt, code, image)

        Returns:
            BaseTextConverter: Appropriate converter instance

        Raises:
            ValueError: If file type is not supported
        """
        # Initialize converter if not already created (singleton pattern)
        if file_type not in cls._converters:
            if file_type == "pdf":
                # PDF uses OCR for better table/image extraction
                ocr = cls._get_ocr_converter()
                cls._converters[file_type] = PdfConverter(ocr_converter=ocr)
            elif file_type == "docx":
                # DOCX uses OCR to capture embedded images
                ocr = cls._get_ocr_converter()
                cls._converters[file_type] = DocxConverter(ocr_converter=ocr)
            elif file_type == "pptx":
                # PPTX uses LibreOffice + OCR
                ocr = cls._get_ocr_converter()
                cls._converters[file_type] = PptxConverter(ocr_converter=ocr)
            elif file_type == "xlsx":
                cls._converters[file_type] = XlsxConverter()
            elif file_type == "html":
                cls._converters[file_type] = HtmlConverter()
            elif file_type == "txt":
                cls._converters[file_type] = TxtConverter()
            elif file_type == "code":
                cls._converters[file_type] = CodeConverter()
            elif file_type == "image":
                # Standalone images use OCR directly
                cls._converters[file_type] = cls._get_ocr_converter()
            else:
                raise ValueError(
                    f"Unsupported file type: {file_type}. "
                    f"Supported types: pdf, docx, pptx, xlsx, html, txt, code, image"
                )

        return cls._converters[file_type]

    @classmethod
    def clear_converters(cls):
        """Clear all converter instances.

        Useful for testing or to free up memory.
        """
        cls._converters.clear()
        cls._ocr_converter = None

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported file types.

        Returns:
            List of supported file type strings
        """
        types = ["xlsx", "html", "txt", "code"]
        if settings.ENABLE_OCR:
            # These formats require OCR
            types.extend(["pdf", "docx", "pptx", "image"])
        return types
