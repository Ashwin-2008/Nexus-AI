"""Loader registry: resolve a filename/content type to one loader."""
from __future__ import annotations

from app.rag.exceptions import UnsupportedDocumentError
from app.rag.loaders.base import BaseLoader, LoaderContext
from app.rag.loaders.csv_loader import CsvLoader
from app.rag.loaders.database_loader import DatabaseRowsLoader
from app.rag.loaders.docx_loader import DocxLoader
from app.rag.loaders.email_loader import EmailFileLoader
from app.rag.loaders.excel_loader import ExcelLoader
from app.rag.loaders.html_loader import HtmlLoader
from app.rag.loaders.image_loader import ImageLoader
from app.rag.loaders.json_loader import JsonLoader
from app.rag.loaders.markdown_loader import MarkdownLoader
from app.rag.loaders.pdf_loader import PdfLoader
from app.rag.loaders.pptx_loader import PptxLoader
from app.rag.loaders.text_loader import TextLoader
from app.rag.loaders.web_loader import WebLoader

_LOADERS: tuple[type[BaseLoader], ...] = (
    PdfLoader,
    DocxLoader,
    MarkdownLoader,
    CsvLoader,
    ExcelLoader,
    PptxLoader,
    HtmlLoader,
    ImageLoader,
    JsonLoader,
    EmailFileLoader,
    TextLoader,
)

_BY_EXTENSION = {extension: loader for loader in _LOADERS for extension in loader.extensions}
_BY_CONTENT_TYPE = {content_type: loader for loader in _LOADERS for content_type in loader.content_types}


def loader_for(filename: str, content_type: str | None = None) -> type[BaseLoader]:
    lowered = (filename or "").lower()
    for extension, loader in _BY_EXTENSION.items():
        if lowered.endswith(extension):
            return loader
    if content_type:
        normalized = content_type.split(";")[0].strip().lower()
        if normalized in _BY_CONTENT_TYPE:
            return _BY_CONTENT_TYPE[normalized]
    raise UnsupportedDocumentError(f"No RAG loader for '{filename}' ({content_type or 'unknown type'})")


def get_loader(filename: str, content_type: str | None = None) -> BaseLoader:
    return loader_for(filename, content_type)()


def supported_extensions() -> tuple[str, ...]:
    return tuple(sorted(_BY_EXTENSION))


def load_document(data: bytes, ctx: LoaderContext, content_type: str | None = None) -> "object":
    loader = get_loader(ctx.filename, content_type or ctx.content_type)
    return loader.load(data, ctx)


__all__ = [
    "BaseLoader",
    "DatabaseRowsLoader",
    "LoaderContext",
    "WebLoader",
    "get_loader",
    "load_document",
    "loader_for",
    "supported_extensions",
]
