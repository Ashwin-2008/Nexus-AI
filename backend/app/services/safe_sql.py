"""Controlled read-only SQL execution for configured database connectors."""
from __future__ import annotations

import re
from typing import Any

from app.services.connectors import ConnectorError, ConnectorContext
from app.services.connectors.base import _require

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge|call|execute|copy|vacuum|attach|detach|pragma)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--|/\*|\*/)")


def validate_read_only_sql(query: str, max_rows: int = 100) -> str:
    """Validate and bound one read-only SQL statement before execution."""
    statement = query.strip()
    if not statement:
        raise ConnectorError("SQL query must not be empty")
    if len(statement) > 10_000:
        raise ConnectorError("SQL query exceeds the 10000 character limit")
    if _COMMENT.search(statement):
        raise ConnectorError("SQL comments are not allowed")
    if ";" in statement:
        raise ConnectorError("Only one SQL statement is permitted")
    first = statement.split(None, 1)[0].lower()
    if first not in {"select", "with"}:
        raise ConnectorError("Only SELECT or WITH queries are permitted")
    if _FORBIDDEN.search(statement):
        raise ConnectorError("SQL contains a prohibited operation")
    if not 1 <= max_rows <= 1000:
        raise ConnectorError("max_rows must be between 1 and 1000")
    if not re.search(r"\blimit\s+\d+\b", statement, re.IGNORECASE):
        statement = f"SELECT * FROM ({statement}) AS nexus_read_only LIMIT {max_rows}"
    return statement


def _connection_url(ctx: ConnectorContext, driver: str) -> str:
    url = str(_require(ctx, "connection_url"))
    if driver == "postgres":
        if not url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
            raise ConnectorError("postgres connection_url must start with postgresql:// or postgres://")
        return url.replace("postgres://", "postgresql://", 1)
    if driver == "mysql":
        if not url.startswith(("mysql://", "mysql+pymysql://")):
            raise ConnectorError("mysql connection_url must start with mysql:// or mysql+pymysql://")
        return url.replace("mysql://", "mysql+pymysql://", 1)
    raise ConnectorError("Unsupported database connector")


def execute_read_only_sql(ctx: ConnectorContext, query: str, max_rows: int = 100) -> dict[str, Any]:
    """Execute a validated query and return JSON-safe columns, rows, and count."""
    import sqlalchemy as sa
    from sqlalchemy import text as sql_text

    driver = str(ctx.config.get("driver") or ctx.config.get("type") or "")
    if driver not in {"postgres", "mysql"}:
        driver = "mysql" if str(ctx.config.get("connection_url", "")).startswith("mysql") else "postgres"
    statement = validate_read_only_sql(query, max_rows)
    url = _connection_url(ctx, driver)
    engine = None
    try:
        engine = sa.create_engine(
            url,
            connect_args={"connect_timeout": 10} if driver == "postgres" else {},
            pool_pre_ping=True,
        )
        with engine.connect() as connection:
            result = connection.execute(sql_text(statement))
            columns = list(result.keys())
            rows = [dict(row._mapping) for row in result.fetchmany(max_rows)]
    except ConnectorError:
        raise
    except Exception as exc:
        raise ConnectorError(f"{driver} read-only query failed: {exc}") from exc
    finally:
        if engine is not None:
            engine.dispose()
    return {
        "driver": driver,
        "columns": columns,
        "rows": [[_json_value(row.get(column)) for column in columns] for row in rows],
        "row_count": len(rows),
        "truncated": len(rows) >= max_rows,
    }


def discover_schema(ctx: ConnectorContext, max_tables: int = 100) -> dict[str, Any]:
    """Return non-secret table/column metadata for an authorized source."""
    import sqlalchemy as sa

    driver = str(ctx.config.get("type") or ctx.config.get("driver") or "")
    if driver not in {"postgres", "mysql"}:
        driver = "mysql" if str(ctx.config.get("connection_url", "")).startswith("mysql") else "postgres"
    engine = None
    try:
        engine = sa.create_engine(_connection_url(ctx, driver), pool_pre_ping=True)
        inspector = sa.inspect(engine)
        schema_allowlist = ctx.config.get("schemas")
        schemas = schema_allowlist if isinstance(schema_allowlist, list) and schema_allowlist else inspector.get_schema_names()
        tables: list[dict[str, Any]] = []
        for schema in schemas:
            for table in inspector.get_table_names(schema=schema):
                if len(tables) >= max_tables:
                    break
                columns = inspector.get_columns(table, schema=schema)
                tables.append(
                    {
                        "schema": schema,
                        "table": table,
                        "columns": [
                            {"name": column["name"], "type": str(column["type"]), "nullable": bool(column.get("nullable", True))}
                            for column in columns
                        ],
                        "primary_key": inspector.get_pk_constraint(table, schema=schema).get("constrained_columns", []),
                    }
                )
        return {"driver": driver, "tables": tables, "truncated": len(tables) >= max_tables}
    except ConnectorError:
        raise
    except Exception as exc:
        raise ConnectorError(f"{driver} schema discovery failed: {exc}") from exc
    finally:
        if engine is not None:
            engine.dispose()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
