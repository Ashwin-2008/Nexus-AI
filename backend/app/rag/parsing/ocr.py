"""Tesseract OCR for scans and images embedded in documents.

OCR is optional: when Tesseract is not installed the engine reports
``available() == False`` and callers degrade explicitly instead of indexing
empty text. Set ``OCR_ENABLED=false`` to disable it, or ``OCR_TESSERACT_CMD``
to point at a non-standard binary.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.rag.exceptions import OcrUnavailableError

_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


class OcrEngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def extract_text(self, image_bytes: bytes, language: str = "eng") -> str: ...


@lru_cache(maxsize=4)
def _resolve_binary(configured: str) -> str | None:
    candidates = [configured] if configured else []
    found = shutil.which("tesseract")
    if found:
        candidates.append(found)
    candidates.extend(_WINDOWS_CANDIDATES)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


class TesseractOcrEngine:
    name = "tesseract"

    def __init__(self, binary: str | None = None, language: str | None = None) -> None:
        self.binary = binary or _resolve_binary(settings.ocr_tesseract_cmd or "")
        self.language = language or settings.ocr_language or "eng"

    def available(self) -> bool:
        return bool(self.binary)

    def extract_text(self, image_bytes: bytes, language: str = "eng") -> str:
        if not self.binary:
            raise OcrUnavailableError(
                "OCR is not available: install Tesseract or set OCR_TESSERACT_CMD."
            )
        if not image_bytes:
            return ""
        suffix = ".png"
        try:
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(image_bytes)) as image:
                normalized = ImageOps.autocontrast(ImageOps.grayscale(image))
                # Screenshots and small scans often carry ~10px text that Tesseract
                # misreads (5 vs 6, 0 vs O). Upscale those before recognition.
                if normalized.width < 1800 or normalized.height < 1000:
                    scale = 2
                    normalized = normalized.resize(
                        (normalized.width * scale, normalized.height * scale),
                        Image.Resampling.LANCZOS,
                    )
                buffer = io.BytesIO()
                normalized.save(buffer, format="PNG")
                payload = buffer.getvalue()
        except Exception:  # noqa: BLE001 - Tesseract may still read the original
            suffix = ".img"
            payload = image_bytes
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(payload)
                temp_path = handle.name
            command = [self.binary, temp_path, "stdout", "--psm", "3"]
            lang = language or self.language
            if lang:
                command.extend(["-l", lang])
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=max(5, int(settings.ocr_timeout_seconds or 45)),
                check=False,
            )
            text = completed.stdout.decode("utf-8", errors="replace").strip()
            if completed.returncode != 0 and not text:
                detail = completed.stderr.decode("utf-8", errors="replace").strip()[:240]
                raise OcrUnavailableError(f"Tesseract OCR failed: {detail or 'unknown error'}")
            return text
        except subprocess.TimeoutExpired as exc:
            raise OcrUnavailableError("Tesseract OCR timed out") from exc
        except OcrUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OcrUnavailableError(f"Tesseract OCR failed: {exc}") from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


class UnavailableOcrEngine:
    name = "unavailable"

    def available(self) -> bool:
        return False

    def extract_text(self, image_bytes: bytes, language: str = "eng") -> str:  # noqa: ARG002
        raise OcrUnavailableError(
            "OCR is not available. Install Tesseract OCR (or set OCR_TESSERACT_CMD), "
            "restart the API, then retry the document."
        )


def get_ocr_engine() -> OcrEngine:
    """Return the configured OCR engine; never claim OCR when unavailable."""
    if not settings.ocr_enabled:
        return UnavailableOcrEngine()
    engine = TesseractOcrEngine()
    return engine if engine.available() else UnavailableOcrEngine()