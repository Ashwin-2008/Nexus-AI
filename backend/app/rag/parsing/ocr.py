"""OCR interface.

OCR is not configured in this deployment. Scanned PDFs raise an explicit
``OcrUnavailableError`` instead of silently producing empty chunks. A real OCR
engine (Tesseract/PaddleOCR/cloud vision) can be plugged in by implementing
``OcrEngine``; the pipeline treats it as an optional capability.
"""
from __future__ import annotations

from typing import Protocol

from app.rag.exceptions import OcrUnavailableError


class OcrEngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def extract_text(self, image_bytes: bytes, language: str = "eng") -> str: ...


class UnavailableOcrEngine:
    name = "unavailable"

    def available(self) -> bool:
        return False

    def extract_text(self, image_bytes: bytes, language: str = "eng") -> str:  # noqa: ARG002
        raise OcrUnavailableError(
            "OCR is not configured. Install and configure an OCR engine, or upload a "
            "text-based document."
        )


def get_ocr_engine() -> OcrEngine:
    """Return the configured OCR engine.

    The repository ships no OCR dependency; returning the explicit unavailable
    engine keeps the failure mode truthful. Register a real engine here when one
    is provisioned.
    """
    return UnavailableOcrEngine()
