"""Document converters for air-gapped system."""

from .converters.base import BaseTextConverter
from .converters.txt_converter import TxtConverter
from .converters.html_converter import HtmlConverter
from .converters.xlsx_converter import XlsxConverter
from .converters.code_converter import CodeConverter
from .converters.pdf_converter import PdfConverter
from .converters.docx_converter import DocxConverter

# Singleton instances
txt_converter = TxtConverter()
html_converter = HtmlConverter()
xlsx_converter = XlsxConverter()
code_converter = CodeConverter()
pdf_converter = PdfConverter()
docx_converter = DocxConverter()

__all__ = [
    "BaseTextConverter",
    "TxtConverter",
    "HtmlConverter",
    "XlsxConverter",
    "CodeConverter",
    "PdfConverter",
    "DocxConverter",
    "txt_converter",
    "html_converter",
    "xlsx_converter",
    "code_converter",
    "pdf_converter",
    "docx_converter",
]
