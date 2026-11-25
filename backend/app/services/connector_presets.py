"""Guided connection presets: turn a few user-facing answers into connector config.

The regular source API accepts raw connector JSON. That exposes protocol details
(IMAP host/port/SSL, database ports, SSL modes) that users should not have to
know. This module owns the provider defaults and builds a validated config +
credential pair from a short, provider-aware form.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.services.connectors.base import ConnectorContext, ConnectorError, get_connector


class GuidedConfigError(ConnectorError):
    """A user-facing guided-form field is missing or invalid."""


EMAIL_PROVIDERS: list[dict[str, Any]] = [
    {
        "value": "gmail",
        "label": "Gmail / Google Workspace",
        "host": "imap.gmail.com",
        "port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "smtp_ssl": True,
        "help": "Use a 16-character Google App Password, not your normal password.",
    },
    {
        "value": "outlook",
        "label": "Outlook / Microsoft 365",
        "host": "outlook.office365.com",
        "port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "help": "Microsoft 365 often requires OAuth2 or an app password from your administrator.",
    },
    {
        "value": "custom",
        "label": "Other IMAP provider",
        "host": "",
        "port": 993,
        "smtp_host": "",
        "smtp_port": 465,
        "smtp_ssl": True,
        "help": "Enter the provider IMAP server; technical defaults are filled in.",
    },
]


def _field(
    key: str,
    label: str,
    *,
    type: str = "text",
    required: bool = False,
    placeholder: str = "",
    help: str = "",
    default: str = "",
    options: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": key,
        "label": label,
        "type": type,
        "required": required,
        "placeholder": placeholder,
        "help": help,
        "default": default,
    }
    if options:
        payload["options"] = options
    return payload


GUIDED_PRESETS: list[dict[str, Any]] = [
    {
        "type": "email",
        "label": "Email mailbox",
        "description": "Index recent messages from Gmail, Outlook or another IMAP mailbox.",
        "fields": [
            _field(
                "provider",
                "Email provider",
                type="select",
                required=True,
                default="gmail",
                options=[{"value": item["value"], "label": item["label"]} for item in EMAIL_PROVIDERS],
                help="We fill in the correct server, port, SSL and folder settings.",
            ),
            _field("email", "Email address", type="email", required=True, placeholder="you@example.com"),
            _field(
                "password",
                "App password",
                type="password",
                required=True,
                placeholder="16-character app password",
                help="Gmail/Outlook normal passwords are rejected. Create an app-specific password.",
            ),
            _field("folder", "Folder", placeholder="INBOX", default="INBOX"),
        ],
        "advanced_fields": [
            _field("imap_host", "IMAP server", placeholder="required only for Other"),
            _field("max_messages", "Messages to sync", type="number", default="50"),
        ],
    },
    {
        "type": "website",
        "label": "Website / intranet",
        "description": "Crawl a public documentation site or intranet and index readable pages.",
        "fields": [
            _field("url", "Starting URL", type="url", required=True, placeholder="https://docs.example.com"),
        ],
        "advanced_fields": [
            _field("max_pages", "Maximum pages", type="number", default="25"),
        ],
    },
    {
        "type": "github",
        "label": "GitHub repository",
        "description": "Index markdown, text and documentation files from a repository.",
        "fields": [
            _field("repo", "Repository", required=True, placeholder="owner/repository or GitHub URL"),
            _field("branch", "Branch", placeholder="main", default="main"),
        ],
        "advanced_fields": [
            _field("token", "Access token (private repos)", type="password", help="Optional; encrypted at rest."),
        ],
    },
    {
        "type": "rest",
        "label": "REST / JSON API",
        "description": "Pull text records from a JSON endpoint. Most APIs need only a URL.",
        "fields": [
            _field("url", "API endpoint URL", type="url", required=True, placeholder="https://api.example.com/v1/articles"),
        ],
        "advanced_fields": [
            _field("token", "Bearer token", type="password"),
            _field("item_path", "Records path", placeholder="data", help="Dot path to the array, when it is nested."),
            _field("title_field", "Title field", default="title"),
            _field("text_fields", "Text fields (comma separated)", default="content,text,body,description"),
        ],
    },
    {
        "type": "postgres",
        "label": "PostgreSQL database",
        "description": "Read rows from one table with a read-only account.",
        "fields": [
            _field("host", "Database host", required=True, placeholder="db.example.com"),
            _field("database", "Database name", required=True),
            _field("username", "Username", required=True),
            _field("password", "Password", type="password", required=True),
            _field("table", "Table name", required=True, placeholder="articles"),
            _field("text_column", "Text column", required=True, default="content", help="Column containing the text to index."),
        ],
        "advanced_fields": [
            _field("port", "Port", type="number", default="5432"),
            _field("schema", "Schema", placeholder="public"),
            _field("ssl", "SSL mode", type="select", default="prefer", options=[
                {"value": "prefer", "label": "Prefer SSL (recommended)"},
                {"value": "require", "label": "Require SSL"},
                {"value": "disable", "label": "Disable SSL"},
            ]),
        ],
    },
    {
        "type": "mysql",
        "label": "MySQL database",
        "description": "Read rows from one table with a read-only account.",
        "fields": [
            _field("host", "Database host", required=True, placeholder="db.example.com"),
            _field("database", "Database name", required=True),
            _field("username", "Username", required=True),
            _field("password", "Password", type="password", required=True),
            _field("table", "Table name", required=True, placeholder="articles"),
            _field("text_column", "Text column", required=True, default="content", help="Column containing the text to index."),
        ],
        "advanced_fields": [
            _field("port", "Port", type="number", default="3306"),
            _field("schema", "Database/schema", placeholder="optional"),
        ],
    },
    {
        "type": "gdrive",
        "label": "Google Drive folder",
        "description": "Sync documents from a shared Drive folder using OAuth credentials.",
        "fields": [
            _field("folder_link", "Folder link or ID", placeholder="https://drive.google.com/drive/folders/..."),
            _field("client_id", "OAuth client ID", required=True),
            _field("client_secret", "OAuth client secret", type="password", required=True),
            _field("refresh_token", "OAuth refresh token", type="password", required=True),
        ],
        "advanced_fields": [
            _field("max_files", "Maximum files", type="number", default="25"),
        ],
    },
]


def guided_schema() -> dict[str, Any]:
    """Return the form definition. Never includes secrets or server defaults."""
    return {
        "presets": GUIDED_PRESETS,
        "email_providers": [
            {"value": item["value"], "label": item["label"], "help": item["help"]}
            for item in EMAIL_PROVIDERS
        ],
        "note": (
            "Only user-facing choices are collected. Server ports, SSL, folders and "
            "chunking settings are selected automatically."
        ),
    }


def _text(values: dict[str, Any], key: str, *, required: bool = False, default: str = "") -> str:
    raw = values.get(key)
    value = str(raw).strip() if raw is not None else ""
    if not value:
        if required:
            raise GuidedConfigError(f"Please fill in {key.replace('_', ' ')}.")
        return default
    return value


def _int(values: dict[str, Any], key: str, default: int, *, low: int = 1, high: int = 100000) -> int:
    raw = values.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise GuidedConfigError(f"{key.replace('_', ' ')} must be a number.") from exc
    if not low <= value <= high:
        raise GuidedConfigError(f"{key.replace('_', ' ')} must be between {low} and {high}.")
    return value


def _database_identifier(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", value):
        raise GuidedConfigError(f"{label} contains unsupported characters.")
    return value


def _build_email(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    provider_name = _text(values, "provider", required=True, default="gmail").lower()
    provider = next((item for item in EMAIL_PROVIDERS if item["value"] == provider_name), None)
    if provider is None:
        raise GuidedConfigError("Choose Gmail, Outlook or Other as the email provider.")
    email = _text(values, "email", required=True)
    password = _text(values, "password", required=True)
    host = str(provider["host"])
    if provider_name == "custom":
        host = _text(values, "imap_host", required=True)
    folder = _text(values, "folder", default="INBOX")
    max_messages = _int(values, "max_messages", 50, low=1, high=500)
    config = {
        "host": host,
        "port": int(provider["port"]),
        "folder": folder,
        "use_ssl": True,
        "max_messages": max_messages,
        "from_address": email,
        "provider": provider_name,
    }
    if provider.get("smtp_host"):
        config.update(
            {
                "smtp_host": provider["smtp_host"],
                "smtp_port": int(provider["smtp_port"]),
                "smtp_ssl": bool(provider["smtp_ssl"]),
            }
        )
    return config, {"username": email, "password": password}


def _build_website(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    url = _text(values, "url", required=True)
    if not url.startswith(("http://", "https://")):
        raise GuidedConfigError("Website URL must start with http:// or https://.")
    return {"base_url": url, "max_pages": _int(values, "max_pages", 25, high=100), "timeout_seconds": 15}, {}


def _build_github(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _text(values, "repo", required=True)
    match = re.search(r"github\.com[/:]([^/]+)/([^/#?]+)", raw)
    repo = f"{match.group(1)}/{match.group(2).removesuffix('.git')}" if match else raw
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise GuidedConfigError("Repository must look like owner/name.")
    config = {"repo": repo, "branch": _text(values, "branch", default="main"), "max_files": 100}
    credentials = {}
    token = _text(values, "token")
    if token:
        credentials["token"] = token
    return config, credentials


def _build_rest(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    url = _text(values, "url", required=True)
    if not url.startswith(("http://", "https://")):
        raise GuidedConfigError("API endpoint must start with http:// or https://.")
    config: dict[str, Any] = {"url": url, "page_size": 50, "max_pages": 10, "timeout_seconds": 20}
    for key in ("item_path", "title_field"):
        value = _text(values, key)
        if value:
            config[key] = value
    fields = _text(values, "text_fields")
    if fields:
        config["text_fields"] = [part.strip() for part in fields.split(",") if part.strip()]
    credentials = {}
    token = _text(values, "token")
    if token:
        credentials["token"] = token
    return config, credentials


def _build_database(values: dict[str, Any], driver: str) -> tuple[dict[str, Any], dict[str, Any]]:
    host = _text(values, "host", required=True)
    database = _database_identifier(_text(values, "database", required=True), "Database name")
    table = _database_identifier(_text(values, "table", required=True), "Table name")
    text_column = _database_identifier(_text(values, "text_column", required=True, default="content"), "Text column")
    username = _text(values, "username", required=True)
    password = _text(values, "password", required=True)
    schema = _text(values, "schema")
    if schema:
        schema = _database_identifier(schema, "Schema")
    port = _int(values, "port", 5432 if driver == "postgres" else 3306, high=65535)
    if driver == "postgres":
        ssl_mode = _text(values, "ssl", default="prefer")
        if ssl_mode not in {"prefer", "require", "disable"}:
            ssl_mode = "prefer"
        query = (
            f'SELECT * FROM "{schema}"."{table}"' if schema else f'SELECT * FROM "{table}"'
        )
        connection_url = f"postgresql://{quote(username)}@{host}:{port}/{database}?sslmode={ssl_mode}"
        type_name = "postgres"
    else:
        query = f"SELECT * FROM `{schema}`.`{table}`" if schema else f"SELECT * FROM `{table}`"
        connection_url = f"mysql://{quote(username)}@{host}:{port}/{database}"
        type_name = "mysql"
    config = {
        "connection_url": connection_url,
        "query": query,
        "content_field": text_column,
        "max_rows": 500,
    }
    return type_name, config, {"username": username, "password": password}


def _build_gdrive(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _text(values, "folder_link")
    folder_id = raw
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", raw)
    if match:
        folder_id = match.group(1)
    config: dict[str, Any] = {"max_files": _int(values, "max_files", 25, high=200)}
    if folder_id:
        config["folder_id"] = folder_id
    credentials = {
        "client_id": _text(values, "client_id", required=True),
        "client_secret": _text(values, "client_secret", required=True),
        "refresh_token": _text(values, "refresh_token", required=True),
    }
    return config, credentials


def build_guided_connection(kind: str, values: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return ``(connector_type, config, credentials)`` for a guided form submission."""
    kind = (kind or "").strip().lower()
    if kind == "email":
        config, credentials = _build_email(values)
    elif kind == "website":
        config, credentials = _build_website(values)
    elif kind == "github":
        config, credentials = _build_github(values)
    elif kind == "rest":
        config, credentials = _build_rest(values)
    elif kind == "gdrive":
        config, credentials = _build_gdrive(values)
    elif kind == "postgres":
        kind, config, credentials = _build_database(values, "postgres")
    elif kind == "mysql":
        kind, config, credentials = _build_database(values, "mysql")
    else:
        raise GuidedConfigError(f"Unsupported guided connector type: {kind}")
    get_connector(kind).validate(ConnectorContext(config=config, credentials=credentials))
    return kind, config, credentials
