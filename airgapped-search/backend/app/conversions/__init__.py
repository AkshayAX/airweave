"""Document converters for air-gapped system."""

from .converters.base import BaseTextConverter
from .converters.txt_converter import TxtConverter
from .converters.html_converter import HtmlConverter
from .converters.xlsx_converter import XlsxConverter
from .converters.code_converter import CodeConverter
from .converters.pdf_converter import PdfConverter
from .converters.docx_converter import DocxConverter
from .converters.deepseek_ocr_converter import DeepSeekOCRConverter

# Singleton instances
txt_converter = TxtConverter()
html_converter = HtmlConverter()
xlsx_converter = XlsxConverter()
code_converter = CodeConverter()
pdf_converter = PdfConverter()
docx_converter = DocxConverter()

# OCR converter (lazy initialization - only load if enabled)
_ocr_converter = None

def get_ocr_converter(device: str = "auto", batch_size: int = 4) -> DeepSeekOCRConverter:
    """Get or create OCR converter singleton.

    Args:
        device: Device to run on - "auto", "cuda", "cpu", "mps"
        batch_size: Number of images to process in parallel

    Returns:
        DeepSeekOCRConverter instance
    """
    global _ocr_converter
    if _ocr_converter is None:
        _ocr_converter = DeepSeekOCRConverter(device=device, batch_size=batch_size)
    return _ocr_converter

__all__ = [
    "BaseTextConverter",
    "TxtConverter",
    "HtmlConverter",
    "XlsxConverter",
    "CodeConverter",
    "PdfConverter",
    "DocxConverter",
    "DeepSeekOCRConverter",
    "txt_converter",
    "html_converter",
    "xlsx_converter",
    "code_converter",
    "pdf_converter",
    "docx_converter",
    "get_ocr_converter",
]
