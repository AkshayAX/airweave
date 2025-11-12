"""Factory for getting appropriate document converter based on file type."""

from typing import Dict

from app.conversions.converters.base import BaseTextConverter
from app.conversions.converters.pdf_converter import PdfConverter
from app.conversions.converters.docx_converter import DocxConverter
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
    """

    # Singleton converter instances
    _converters: Dict[str, BaseTextConverter] = {}

    @classmethod
    def get_converter(cls, file_type: str) -> BaseTextConverter:
        """Get appropriate converter for file type.

        Args:
            file_type: Type of file (pdf, docx, xlsx, html, txt, code, image)

        Returns:
            BaseTextConverter: Appropriate converter instance

        Raises:
            ValueError: If file type is not supported
        """
        # Initialize converter if not already created (singleton pattern)
        if file_type not in cls._converters:
            if file_type == "pdf":
                cls._converters[file_type] = PdfConverter()
            elif file_type == "docx":
                cls._converters[file_type] = DocxConverter()
            elif file_type == "xlsx":
                cls._converters[file_type] = XlsxConverter()
            elif file_type == "html":
                cls._converters[file_type] = HtmlConverter()
            elif file_type == "txt":
                cls._converters[file_type] = TxtConverter()
            elif file_type == "code":
                cls._converters[file_type] = CodeConverter()
            elif file_type == "image":
                # OCR converter is heavier, only initialize if OCR is enabled
                if not settings.ENABLE_OCR:
                    raise ValueError(
                        f"OCR is disabled. Enable it in settings to process images. "
                        f"Set ENABLE_OCR=true in environment."
                    )
                cls._converters[file_type] = DeepSeekOCRConverter(
                    device=settings.OCR_DEVICE,
                    batch_size=settings.OCR_BATCH_SIZE,
                )
            else:
                raise ValueError(
                    f"Unsupported file type: {file_type}. "
                    f"Supported types: pdf, docx, xlsx, html, txt, code, image"
                )

        return cls._converters[file_type]

    @classmethod
    def clear_converters(cls):
        """Clear all converter instances.

        Useful for testing or to free up memory.
        """
        cls._converters.clear()

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported file types.

        Returns:
            List of supported file type strings
        """
        types = ["pdf", "docx", "xlsx", "html", "txt", "code"]
        if settings.ENABLE_OCR:
            types.append("image")
        return types
