"""Website loader with SSRF protections.

Used when a configured website/URL source is registered for RAG ingestion.
Only absolute HTTP(S) URLs pointing at public addresses are fetched; response
size and content type are bounded. HTML is parsed with the same stdlib parser
the file loaders use. Network failures are explicit errors — never silent
empty documents.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import ClassVar
from urllib.parse import urlparse

import httpx

from app.rag.exceptions import ValidationError
from app.rag.loaders.base import BaseLoader, LoaderContext
from app.rag.types import LoadedDocument

MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def validate_public_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValidationError("URL credentials are not allowed")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise ValidationError(f"URL host cannot be resolved: {exc}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValidationError("URL resolves to a non-public address")
    return url


class WebLoader(BaseLoader):
    name: ClassVar[str] = "web"
    extensions: ClassVar[tuple[str, ...]] = ()
    content_types: ClassVar[tuple[str, ...]] = ("text/html", "text/plain")

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def load_url(self, url: str, ctx: LoaderContext) -> LoadedDocument:
        safe_url = validate_public_http_url(url)
        try:
            with httpx.Client(follow_redirects=True, timeout=self.timeout_seconds) as client:
                with client.stream("GET", safe_url) as response:
                    if response.status_code >= 400:
                        raise ValidationError(f"website fetch failed with HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "")
                    if "html" not in content_type and "text" not in content_type:
                        raise ValidationError(f"unsupported website content type: {content_type or 'unknown'}")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise ValidationError("website response exceeds the 5 MB ingestion limit")
                        chunks.append(chunk)
                    body = b"".join(chunks)
        except httpx.HTTPError as exc:
            raise ValidationError(f"website fetch failed: {exc}") from exc

        filename = "page.html" if "html" in content_type else "page.txt"
        child = LoaderContext(
            document_id=ctx.document_id,
            organization_id=ctx.organization_id,
            filename=filename,
            content_type="text/html" if filename.endswith(".html") else "text/plain",
            storage_path=safe_url,
            storage_backend="url",
            max_bytes=MAX_RESPONSE_BYTES,
        )
        if filename.endswith(".html"):
            from app.rag.loaders.html_loader import HtmlLoader

            loaded = HtmlLoader().load(body, child)
        else:
            from app.rag.loaders.text_loader import TextLoader

            loaded = TextLoader().load(body, child)
        loaded.metadata.update({"uri": safe_url, "source": "website", "loaded_from": "url"})
        loaded.loader = "web"
        return loaded

    def load(self, data: bytes, ctx: LoaderContext) -> LoadedDocument:
        """Treat bytes as a URL when a plain-text body is supplied."""
        url = data.decode("utf-8", errors="ignore").strip()
        if not url:
            raise ValidationError("web loader requires a URL")
        return self.load_url(url, ctx)
