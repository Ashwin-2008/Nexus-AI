"""Cleaning and prompt-safety helpers.

Retrieved documents are untrusted data. Cleaning removes control characters
and obvious prompt-injection directives *for prompt construction only*; stored
chunk text remains verbatim so citations point at real source material.
"""
from __future__ import annotations

import re
from typing import Any

from app.rag.constants import PROMPT_INJECTION_MARKERS

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*[^\s,;]{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control_characters(text: str) -> str:
    return _CONTROL_RE.sub("", text or "")


def redact_secrets(text: str) -> str:
    """Redact credential-looking values for logs and diagnostics."""
    redacted = text or ""
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def neutralize_prompt_injection(text: str) -> tuple[str, list[str]]:
    """Return prompt-safe text plus the injection markers that were found.

    Markers are replaced with a bracketed notice so the model can see that the
    source contained a directive, without following it.
    """
    found: list[str] = []
    safe = text or ""
    lowered = safe.lower()
    for marker in PROMPT_INJECTION_MARKERS:
        if marker in lowered:
            found.append(marker)
            safe = re.sub(re.escape(marker), "[untrusted instruction removed]", safe, flags=re.IGNORECASE)
            lowered = safe.lower()
    return safe, found


def wrap_untrusted_content(text: str, *, source: str) -> str:
    """Delimit untrusted evidence so injected text cannot masquerade as system text."""
    return (
        f'<untrusted_evidence source="{source}">\n'
        f"{text}\n"
        "</untrusted_evidence>"
    )


def summarize_metadata(metadata: dict[str, Any], max_keys: int = 20) -> dict[str, Any]:
    """Keep metadata JSON-safe and bounded for logs/API responses."""
    result: dict[str, Any] = {}
    for key, value in list(metadata.items())[:max_keys]:
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
        elif isinstance(value, (list, tuple)):
            result[key] = [item for item in list(value)[:10] if isinstance(item, (str, int, float, bool))]
        elif isinstance(value, dict):
            result[key] = {
                sub_key: sub_value
                for sub_key, sub_value in list(value.items())[:10]
                if isinstance(sub_value, (str, int, float, bool)) or sub_value is None
            }
        else:
            result[key] = str(value)[:200]
    return result
