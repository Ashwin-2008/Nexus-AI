"""Connector framework: a consistent interface for external data sources.

Each connector returns ConnectorItems (title + text/bytes + metadata). The
sync service persists items as Documents through the standard ingestion
pipeline (storage → extraction → chunking → embeddings → indexing), so
connector content lands in the same knowledge base and search/RAG paths as
uploaded files.

Implementations:
- website  — same-host HTML crawl (httpx + stdlib HTMLParser)
- github   — GitHub REST API (repo markdown/code files)
- rest     — paginated JSON API pulling text records
- postgres — SQL query over external PostgreSQL (psycopg)
- mysql    — SQL query over external MySQL (pymysql)
- gdrive   — Google Drive files via OAuth2 refresh token (googleapis REST)
- email    — IMAP mailbox fetch (stdlib imaplib)

All network operations are bounded (timeouts, page/item limits) and errors
propagate as ConnectorError — no silent empty results.
"""
from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

CONNECTOR_TYPES = ("postgres", "mysql", "rest", "website", "github", "gdrive", "email")


class ConnectorError(RuntimeError):
    pass


@dataclass
class ConnectorItem:
    """One fetched unit of external content."""

    external_id: str  # stable identity within the source (dedupe key)
    title: str
    text: str | None = None
    data: bytes | None = None
    mime: str = "text/plain"
    uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """Stable hash used for change detection between syncs."""
        payload = self.data if self.data is not None else (self.text or "").encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass
class ConnectorContext:
    config: dict[str, Any]
    credentials: dict[str, Any]
    since_iso: str | None = None  # last successful sync timestamp for incremental fetch


class BaseConnector(ABC):
    """Interface every connector implements."""

    type_name: str = ""

    @abstractmethod
    def validate(self, ctx: ConnectorContext) -> None:
        """Raise ConnectorError if config/credentials are invalid."""

    @abstractmethod
    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        """Yield items. Raise ConnectorError on failure (never return silently empty on error)."""

    def test_connection(self, ctx: ConnectorContext) -> dict[str, Any]:
        """Optional connectivity probe; default validates config only."""
        self.validate(ctx)
        return {"ok": True}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require(ctx: ConnectorContext, key: str, where: str = "config") -> Any:
    value = ctx.config.get(key) if where == "config" else ctx.credentials.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConnectorError(f"Missing required {where} field: {key}")
    return value


class _TextExtractor(HTMLParser):
    """Minimal HTML→text extraction (stdlib, no extra dependency)."""

    SKIP = {"script", "style", "noscript", "template", "svg", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001
        raise ConnectorError(f"HTML parse failed: {e}") from e
    return parser.text()


def strip_html_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


# ---------------------------------------------------------------------------
# website crawler
# ---------------------------------------------------------------------------


class WebsiteConnector(BaseConnector):
    """Crawl one host starting from a base URL (bounded BFS)."""

    type_name = "website"

    def validate(self, ctx: ConnectorContext) -> None:
        base_url = _require(ctx, "base_url")
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConnectorError("website.base_url must be an absolute http(s) URL")
        max_pages = int(ctx.config.get("max_pages", 10))
        if not 1 <= max_pages <= 100:
            raise ConnectorError("website.max_pages must be between 1 and 100")

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        base_url = str(ctx.config["base_url"]).rstrip("/")
        max_pages = min(int(ctx.config.get("max_pages", 10)), max_items)
        timeout = float(ctx.config.get("timeout_seconds", 15))
        origin = urlparse(base_url)
        host = origin.netloc

        visited: set[str] = set()
        queue = [base_url]
        items: list[ConnectorItem] = []
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            while queue and len(visited) < max_pages:
                url = queue.pop(0)
                normalized = url.split("#")[0]
                if normalized in visited:
                    continue
                visited.add(normalized)
                try:
                    resp = client.get(normalized)
                except httpx.HTTPError as e:
                    raise ConnectorError(f"website fetch failed for {normalized}: {e}") from e
                if resp.status_code >= 400:
                    raise ConnectorError(f"website fetch HTTP {resp.status_code} for {normalized}")
                content_type = resp.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    continue
                text = html_to_text(resp.text)
                if not text.strip():
                    continue
                title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
                title = strip_html_tags(title_match.group(1)).strip() if title_match else normalized
                items.append(
                    ConnectorItem(
                        external_id=normalized,
                        title=title[:255] or normalized,
                        text=text,
                        mime="text/plain",
                        uri=normalized,
                        metadata={"source": "website", "url": normalized},
                    )
                )
                for href in re.findall(r'href=["\']([^"\'#]+)["\']', resp.text):
                    absolute = urljoin(normalized, href)
                    if urlparse(absolute).netloc == host and absolute.startswith(("http://", "https://")):
                        queue.append(absolute.split("#")[0])
        if not items:
            raise ConnectorError(f"website crawl produced no text content from {base_url}")
        return items


# ---------------------------------------------------------------------------
# GitHub repository connector
# ---------------------------------------------------------------------------


class GitHubConnector(BaseConnector):
    """Fetch markdown/text files from a GitHub repository via the REST API."""

    type_name = "github"
    DEFAULT_API = "https://api.github.com"

    def validate(self, ctx: ConnectorContext) -> None:
        repo = _require(ctx, "repo")
        if not re.match(r"^[\w.-]+/[\w.-]+$", str(repo)):
            raise ConnectorError("github.repo must look like 'owner/name'")
        branch = ctx.config.get("branch") or "main"
        if not isinstance(branch, str) or len(branch) > 200:
            raise ConnectorError("github.branch invalid")

    def _headers(self, ctx: ConnectorContext) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        token = ctx.credentials.get("token") or ctx.config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        repo = str(ctx.config["repo"])
        branch = str(ctx.config.get("branch") or "main")
        api_base = str(ctx.config.get("api_base_url", self.DEFAULT_API)).rstrip("/")
        max_items = min(max_items, int(ctx.config.get("max_files", 50)) or 50)
        wanted_exts = {".md", ".txt", ".rst", ".json", ".csv"}
        timeout = float(ctx.config.get("timeout_seconds", 20))
        with httpx.Client(timeout=timeout, headers=self._headers(ctx)) as client:
            tree_url = f"{api_base}/repos/{repo}/git/trees/{branch}?recursive=1"
            try:
                resp = client.get(tree_url)
            except httpx.HTTPError as e:
                raise ConnectorError(f"github request failed: {e}") from e
            if resp.status_code == 404:
                raise ConnectorError(f"github repo/branch not found: {repo}@{branch}")
            if resp.status_code in (401, 403):
                raise ConnectorError(f"github auth failed (HTTP {resp.status_code}): provide a valid token for private repos")
            if resp.status_code >= 400:
                raise ConnectorError(f"github API HTTP {resp.status_code}")
            tree = resp.json().get("tree", [])
            items: list[ConnectorItem] = []
            for entry in tree:
                if entry.get("type") != "blob":
                    continue
                path = entry.get("path", "")
                ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
                if ext not in wanted_exts:
                    continue
                if entry.get("size", 0) > 512 * 1024:
                    continue
                if len(items) >= max_items:
                    break
                try:
                    raw = client.get(f"{api_base}/repos/{repo}/contents/{path}?ref={branch}")
                except httpx.HTTPError as e:
                    raise ConnectorError(f"github content fetch failed for {path}: {e}") from e
                if raw.status_code >= 400:
                    raise ConnectorError(f"github content fetch HTTP {raw.status_code} for {path}")
                content_json = raw.json()
                if content_json.get("encoding") != "base64":
                    raise ConnectorError(f"github unexpected encoding for {path}: {content_json.get('encoding')}")
                import base64 as _b64

                data = _b64.b64decode(content_json["content"])
                items.append(
                    ConnectorItem(
                        external_id=f"{repo}@{branch}:{path}",
                        title=path,
                        data=data,
                        mime="text/plain",
                        uri=f"https://github.com/{repo}/blob/{branch}/{path}",
                        metadata={"source": "github", "repo": repo, "branch": branch, "path": path},
                    )
                )
            if not items:
                raise ConnectorError(f"github: no supported files found in {repo}@{branch}")
            return items


# ---------------------------------------------------------------------------
# REST connector
# ---------------------------------------------------------------------------


class RestConnector(BaseConnector):
    """Pull text records from a JSON API endpoint (supports limit/offset pagination)."""

    type_name = "rest"

    def validate(self, ctx: ConnectorContext) -> None:
        url = _require(ctx, "url")
        parsed = urlparse(str(url))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConnectorError("rest.url must be an absolute http(s) URL")
        item_path = ctx.config.get("item_path")
        if item_path is not None and not isinstance(item_path, str):
            raise ConnectorError("rest.item_path must be a dot-separated string when provided")

    def _extract_items(self, payload: Any, item_path: str | None) -> list[dict[str, Any]]:
        data = payload
        if item_path:
            for part in item_path.split("."):
                if isinstance(data, dict):
                    data = data.get(part)
                else:
                    raise ConnectorError(f"rest.item_path '{item_path}' does not match response shape")
        if not isinstance(data, list):
            raise ConnectorError("rest response items must be a JSON array (check item_path)")
        return [entry for entry in data if isinstance(entry, dict)]

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        url = str(ctx.config["url"])
        limit = min(int(ctx.config.get("page_size", 50)), max_items)
        max_pages = min(int(ctx.config.get("max_pages", 4)), 20)
        title_field = ctx.config.get("title_field", "title")
        text_fields = ctx.config.get("text_fields") or ["content", "text", "body", "description"]
        if isinstance(text_fields, str):
            text_fields = [text_fields]
        timeout = float(ctx.config.get("timeout_seconds", 15))
        headers = {"Accept": "application/json"}
        token = ctx.credentials.get("token") or ctx.config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        items: list[ConnectorItem] = []
        with httpx.Client(timeout=timeout, headers=headers) as client:
            for page in range(max_pages):
                page_url = url + ("&" if "?" in url else "?") + f"limit={limit}&offset={page * limit}"
                try:
                    resp = client.get(page_url)
                except httpx.HTTPError as e:
                    raise ConnectorError(f"rest fetch failed for {page_url}: {e}") from e
                if resp.status_code in (401, 403):
                    raise ConnectorError(f"rest endpoint auth failed (HTTP {resp.status_code})")
                if resp.status_code >= 400:
                    raise ConnectorError(f"rest endpoint HTTP {resp.status_code} for {page_url}")
                try:
                    records = self._extract_items(resp.json(), ctx.config.get("item_path"))
                except ValueError as e:
                    raise ConnectorError(f"rest response is not valid JSON: {e}") from e
                if not records:
                    break
                for record in records:
                    text = "\n".join(str(record.get(field_name)) for field_name in text_fields if record.get(field_name))
                    if not text.strip():
                        continue
                    external_id = str(record.get("id") or record.get("uuid") or hashlib.sha256(text.encode()).hexdigest()[:32])
                    items.append(
                        ConnectorItem(
                            external_id=external_id,
                            title=str(record.get(title_field) or external_id)[:255],
                            text=text,
                            mime="text/plain",
                            uri=page_url,
                            metadata={"source": "rest", "endpoint": page_url},
                        )
                    )
                    if len(items) >= max_items:
                        return items
                if len(records) < limit:
                    break
        if not items:
            raise ConnectorError(f"rest endpoint yielded no text records: {url}")
        return items


# ---------------------------------------------------------------------------
# SQL connectors
# ---------------------------------------------------------------------------


def _fetch_sql_rows(ctx: ConnectorContext, driver: str) -> list[tuple[str, str, str]]:
    """Execute a read-only query and return rows of (id, title, text)."""
    import sqlalchemy as sa
    from sqlalchemy import text as sql_text

    connection_url = _require(ctx, "connection_url" if driver == "postgres" else "connection_url")
    query = _require(ctx, "query")
    id_field = ctx.config.get("id_field", "id")
    title_field = ctx.config.get("title_field", "title")
    content_field = ctx.config.get("content_field", "content")
    max_rows = min(int(ctx.config.get("max_rows", 100)), 1000)

    lowered = str(query).lstrip().lower()
    if not lowered.startswith("select"):
        raise ConnectorError(f"{driver} query must be a SELECT statement")
    if ";" in str(query).rstrip().rstrip(";"):
        raise ConnectorError(f"{driver} query must be a single statement")

    if driver == "postgres":
        if not str(connection_url).startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
            raise ConnectorError("postgres connection_url must start with postgresql:// or postgres://")
    else:
        if not str(connection_url).startswith(("mysql://", "mysql+pymysql://")):
            raise ConnectorError("mysql connection_url must start with mysql:// or mysql+pymysql://")

    url = str(connection_url)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)

    try:
        engine = sa.create_engine(url, connect_args={"connect_timeout": 10} if driver == "postgres" else {})
        with engine.connect() as conn:
            result = conn.execute(sql_text(str(query)))
            columns = list(result.keys())
            rows = result.fetchmany(max_rows)
        engine.dispose()
    except Exception as e:  # noqa: BLE001
        raise ConnectorError(f"{driver} query failed: {e}") from e

    def col_index(name: str) -> int | None:
        lname = name.lower()
        for i, c in enumerate(columns):
            if c.lower() == lname:
                return i
        return None

    id_i, title_i, content_i = col_index(id_field), col_index(title_field), col_index(content_field)
    if content_i is None:
        raise ConnectorError(f"{driver} result must contain '{content_field}' column (got: {columns})")

    out: list[tuple[str, str, str]] = []
    for row in rows:
        row_id = str(row[id_i]) if id_i is not None else hashlib.sha256(str(row[content_i]).encode()).hexdigest()[:32]
        title = str(row[title_i]) if title_i is not None else row_id
        out.append((row_id, title, str(row[content_i])))
    if not out:
        raise ConnectorError(f"{driver} query returned no rows")
    return out


class PostgresConnector(BaseConnector):
    """Sync rows from an external PostgreSQL database."""

    type_name = "postgres"

    def validate(self, ctx: ConnectorContext) -> None:
        url = str(_require(ctx, "connection_url"))
        if not url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            raise ConnectorError("postgres connection_url must start with postgresql:// or postgres://")
        _require(ctx, "query")
        _require(ctx, "query")

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        rows = _fetch_sql_rows(ctx, "postgres")
        return [
            ConnectorItem(
                external_id=f"pg:{row_id}",
                title=title[:255],
                text=content,
                mime="text/plain",
                metadata={"source": "postgres", "external_id": row_id},
            )
            for row_id, title, content in rows
        ]


class MySQLConnector(BaseConnector):
    """Sync rows from an external MySQL database (pymysql driver)."""

    type_name = "mysql"

    def validate(self, ctx: ConnectorContext) -> None:
        url = str(_require(ctx, "connection_url"))
        if not url.startswith(("mysql://", "mysql+pymysql://")):
            raise ConnectorError("mysql connection_url must start with mysql:// or mysql+pymysql://")
        _require(ctx, "query")
        _require(ctx, "query")

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        try:
            import pymysql  # noqa: F401
        except ImportError as e:
            raise ConnectorError(
                "mysql connector requires pymysql (add backend/requirements-mysql.txt dependencies)"
            ) from e
        rows = _fetch_sql_rows(ctx, "mysql")
        return [
            ConnectorItem(
                external_id=f"mysql:{row_id}",
                title=title[:255],
                text=content,
                mime="text/plain",
                metadata={"source": "mysql", "external_id": row_id},
            )
            for row_id, title, content in rows
        ]


# ---------------------------------------------------------------------------
# Google Drive connector (OAuth2 refresh token, no google SDK)
# ---------------------------------------------------------------------------


class GDriveConnector(BaseConnector):
    """List and download files from Google Drive using an OAuth2 refresh token."""

    type_name = "gdrive"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    LIST_URL = "https://www.googleapis.com/drive/v3/files"
    EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"
    DOWNLOAD_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"

    TEXT_MIMES = ("text/plain", "text/markdown", "application/json", "text/csv")
    EXPORT_MIMES = {
        "application/vnd.google-apps.document": "text/markdown",
        "application/vnd.google-apps.spreadsheet": "text/csv",
    }

    def validate(self, ctx: ConnectorContext) -> None:
        for field in ("client_id", "client_secret", "refresh_token"):
            _require(ctx, field, where="credentials")
        folder_id = ctx.config.get("folder_id")
        if folder_id is not None and not isinstance(folder_id, str):
            raise ConnectorError("gdrive.folder_id must be a string")

    def _access_token(self, ctx: ConnectorContext, timeout: float) -> str:
        try:
            resp = httpx.post(
                self.TOKEN_URL,
                data={
                    "client_id": ctx.credentials["client_id"],
                    "client_secret": ctx.credentials["client_secret"],
                    "refresh_token": ctx.credentials["refresh_token"],
                    "grant_type": "refresh_token",
                },
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise ConnectorError(f"gdrive token request failed: {e}") from e
        if resp.status_code != 200:
            raise ConnectorError(f"gdrive token refresh failed (HTTP {resp.status_code}): check client_id/secret/refresh_token")
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("gdrive token refresh returned no access_token")
        return str(token)

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        max_items = min(max_items, int(ctx.config.get("max_files", 25)) or 25)
        timeout = float(ctx.config.get("timeout_seconds", 20))
        access_token = self._access_token(ctx, timeout)
        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, Any] = {"pageSize": min(100, max_items), "fields": "nextPageToken, files(id, name, mimeType, modifiedTime)"}
        folder = ctx.config.get("folder_id")
        if folder:
            params["q"] = f"'{folder}' in parents and trashed = false"
        try:
            resp = httpx.get(self.LIST_URL, headers=headers, params=params, timeout=timeout)
        except httpx.HTTPError as e:
            raise ConnectorError(f"gdrive list request failed: {e}") from e
        if resp.status_code in (401, 403):
            raise ConnectorError(f"gdrive authorization failed (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise ConnectorError(f"gdrive list HTTP {resp.status_code}")
        files = resp.json().get("files", [])
        if not files:
            raise ConnectorError("gdrive: no files found in scope")
        items: list[ConnectorItem] = []
        for f in files[:max_items]:
            file_id = f["id"]
            name = f.get("name") or file_id
            mime = f.get("mimeType", "application/octet-stream")
            if mime in self.EXPORT_MIMES:
                url = self.EXPORT_URL.format(file_id=file_id)
                params_export = {"mimeType": self.EXPORT_MIMES[mime]}
            elif any(mime.startswith(t) for t in self.TEXT_MIMES) or mime == "application/octet-stream":
                url = self.DOWNLOAD_URL.format(file_id=file_id)
                params_export = None
            else:
                continue
            try:
                dl = httpx.get(url, headers=headers, params=params_export, timeout=timeout)
            except httpx.HTTPError as e:
                raise ConnectorError(f"gdrive download failed for {name}: {e}") from e
            if dl.status_code >= 400:
                raise ConnectorError(f"gdrive download HTTP {dl.status_code} for {name}")
            items.append(
                ConnectorItem(
                    external_id=f"gdrive:{file_id}",
                    title=name,
                    data=dl.content,
                    mime=self.EXPORT_MIMES.get(mime, "text/plain"),
                    uri=f"https://drive.google.com/file/d/{file_id}/view",
                    metadata={"source": "gdrive", "file_id": file_id, "modified": f.get("modifiedTime")},
                )
            )
        if not items:
            raise ConnectorError("gdrive: no downloadable text files found")
        return items


# ---------------------------------------------------------------------------
# Email connector (IMAP)
# ---------------------------------------------------------------------------


class EmailConnector(BaseConnector):
    """Fetch recent messages from an IMAP mailbox (stdlib imaplib, no new deps)."""

    type_name = "email"

    def validate(self, ctx: ConnectorContext) -> None:
        _require(ctx, "host")
        _require(ctx, "username", where="credentials")
        _require(ctx, "password", where="credentials")
        port = int(ctx.config.get("port", 993))
        if not 1 <= port <= 65535:
            raise ConnectorError("email.port invalid")
        folder = ctx.config.get("folder", "INBOX")
        if not isinstance(folder, str) or not folder:
            raise ConnectorError("email.folder invalid")

    def fetch(self, ctx: ConnectorContext, max_items: int = 200) -> Iterable[ConnectorItem]:
        import email as email_lib
        import imaplib

        host = str(ctx.config["host"])
        port = int(ctx.config.get("port", 993))
        folder = str(ctx.config.get("folder", "INBOX"))
        max_items = min(max_items, int(ctx.config.get("max_messages", 20)) or 20)
        use_ssl = bool(ctx.config.get("use_ssl", True))

        try:
            imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        except Exception as e:  # noqa: BLE001
            raise ConnectorError(f"email: cannot connect to {host}:{port}: {e}") from e
        try:
            login_result = imap.login(ctx.credentials["username"], ctx.credentials["password"])
            if login_result[0] != "OK":
                raise ConnectorError(f"email: IMAP login failed: {login_result}")
            status, _ = imap.select(folder)
            if status != "OK":
                raise ConnectorError(f"email: cannot select folder {folder}")
            status, data = imap.search(None, "ALL")
            if status != "OK":
                raise ConnectorError("email: IMAP search failed")
            ids = (data[0].split() if data and data[0] else [])[-max_items:]
            items: list[ConnectorItem] = []
            for num in reversed(ids):  # newest first
                status, msg_data = imap.fetch(num, "(RFC822)")
                if status != "OK" or not msg_data or msg_data[0] is None:
                    continue
                message = email_lib.message_from_bytes(msg_data[0][1])
                body_parts: list[str] = []
                if message.is_multipart():
                    for part in message.walk():
                        ctype = part.get_content_type()
                        if ctype in ("text/plain", "text/html") and not part.get_filename():
                            payload = part.get_payload(decode=True)
                            if payload:
                                text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                                if ctype == "text/html":
                                    text = html_to_text(text)
                                body_parts.append(text)
                else:
                    payload = message.get_payload(decode=True)
                    if payload:
                        text = payload.decode(message.get_content_charset() or "utf-8", errors="ignore")
                        if message.get_content_type() == "text/html":
                            text = html_to_text(text)
                        body_parts.append(text)
                body = "\n".join(body_parts).strip()
                if not body:
                    continue
                message_id = message.get("Message-ID") or hashlib.sha256(body.encode()).hexdigest()[:32]
                items.append(
                    ConnectorItem(
                        external_id=f"mail:{message_id}",
                        title=str(message.get("Subject") or "(no subject)")[:255],
                        text=f"From: {message.get('From')}\nDate: {message.get('Date')}\n\n{body}",
                        mime="text/plain",
                        metadata={"source": "email", "folder": folder, "message_id": message_id},
                    )
                )
        finally:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
        if not items:
            raise ConnectorError("email: no readable messages found")
        return items


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

_CONNECTORS: dict[str, type[BaseConnector]] = {
    c.type_name: c
    for c in (WebsiteConnector, GitHubConnector, RestConnector, PostgresConnector, MySQLConnector, GDriveConnector, EmailConnector)
}


def get_connector(type_name: str) -> BaseConnector:
    cls = _CONNECTORS.get(type_name)
    if cls is None:
        raise ConnectorError(f"Unknown connector type '{type_name}' (valid: {', '.join(sorted(_CONNECTORS))})")
    return cls()


def parse_config(raw: str | None) -> dict[str, Any]:
    import json

    if not raw:
        return {}
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConnectorError(f"Stored connector config is corrupt: {e}") from e
    return config if isinstance(config, dict) else {}
