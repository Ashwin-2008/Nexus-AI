"""Upload/ingestion validation.

Defence in depth: extension allow-list, size limit, magic-byte consistency, and
bounded OOXML archive inspection (zip-bomb protection). Validation failures are
explicit ``ValidationError`` subclasses, never silent skips.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.rag.config import RagConfig
from app.rag.exceptions import UnsupportedDocumentError, ValidationError

ZIP_EXTENSIONS = {".docx", ".xlsx", ".pptx"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".html", ".htm", ".json", ".eml"}
MAGIC_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
}
EXECUTABLE_SIGNATURES = (b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")
MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_UNCOMPRESSED = 200 * 1024 * 1024
MAX_FILENAME_LENGTH = 512


def validate_document(
    filename: str,
    content_type: str | None,
    data: bytes,
    config: RagConfig | None = None,
) -> str:
    """Validate an upload and return its normalized extension."""
    config = config or RagConfig()
    name = Path(filename or "").name
    if not name or len(name) > MAX_FILENAME_LENGTH:
        raise ValidationError("Filename is empty or too long")
    extension = Path(name).suffix.lower()
    if extension not in config.allowed_extensions:
        raise UnsupportedDocumentError(
            f"Unsupported file type: {extension or 'unknown'}. "
            f"Supported: {', '.join(sorted(config.allowed_extensions))}"
        )
    if not data:
        raise ValidationError("Empty file")
    if len(data) > config.max_document_bytes:
        raise ValidationError(
            f"File exceeds the {config.max_document_bytes // (1024 * 1024)} MB ingestion limit"
        )
    _reject_executables(data)
    _check_magic(extension, data)
    if extension in ZIP_EXTENSIONS:
        _inspect_archive(data, extension)
    if extension in TEXT_EXTENSIONS:
        _check_text_like(data, extension)
    return extension


def _reject_executables(data: bytes) -> None:
    for signature in EXECUTABLE_SIGNATURES:
        if data.startswith(signature):
            raise ValidationError("Executable content is not accepted")


def _check_magic(extension: str, data: bytes) -> None:
    signatures = MAGIC_SIGNATURES.get(extension)
    if not signatures:
        return
    if not any(data.startswith(signature) for signature in signatures):
        raise ValidationError(f"File content does not match its {extension} extension")


def _inspect_archive(data: bytes, extension: str) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"Malformed {extension} archive: {exc}") from exc
    try:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValidationError("Archive contains too many entries")
        total_uncompressed = sum(entry.file_size for entry in entries)
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED:
            raise ValidationError("Archive expands beyond the safe ingestion limit")
        for entry in entries:
            if entry.compress_size and entry.file_size / max(1, entry.compress_size) > 1000 and entry.file_size > 10 * 1024 * 1024:
                raise ValidationError("Archive contains a suspiciously compressed entry")
    finally:
        archive.close()


def _check_text_like(data: bytes, extension: str) -> None:
    sample = data[:8192]
    if not sample:
        raise ValidationError("Empty file")
    # UTF-16 BOM is legitimate for text exports.
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return
    printable = sum(1 for byte in sample if byte in b"\n\r\t" or 32 <= byte <= 126 or byte >= 128)
    if printable / len(sample) < 0.85:
        raise ValidationError(f"{extension} file does not look like text content")
