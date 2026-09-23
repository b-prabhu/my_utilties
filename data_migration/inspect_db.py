"""Snapshot a database's schemas, tables, columns, keys, indexes and row counts."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import create_engine, func, select, table as sa_table
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import URL, Engine

from .connections import describe

SYSTEM_SCHEMAS = {
    "information_schema", "pg_catalog", "pg_toast", "sys", "guest", "INFORMATION_SCHEMA",
    "db_owner", "db_accessadmin", "db_securityadmin", "db_ddladmin", "db_backupoperator",
    "db_datareader", "db_datawriter", "db_denydatareader", "db_denydatawriter",
    "mysql", "performance_schema",
}


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # permissions or dialect gaps shouldn't sink the whole snapshot
        return default


def _type_name(col_type) -> str:
    try:
        return str(col_type)
    except Exception:
        return col_type.__class__.__name__


def _generic_type(col_type) -> str:
    try:
        return col_type.as_generic().__class__.__name__.upper()
    except Exception:
        return col_type.__class__.__name__.upper()


def _row_count(engine: Engine, schema: str | None, name: str) -> int | None:
    t = sa_table(name, schema=schema)
    try:
        with engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(t)).scalar_one()
    except Exception:
        return None


def snapshot_table(engine: Engine, insp, schema: str | None, name: str, count_rows: bool) -> dict[str, Any]:
    pk = _safe(lambda: insp.get_pk_constraint(name, schema=schema), {}) or {}
    pk_cols = pk.get("constrained_columns") or []
    columns = []
    for col in _safe(lambda: insp.get_columns(name, schema=schema), []):
        columns.append({
            "name": col["name"],
            "type": _type_name(col["type"]),
            "generic": _generic_type(col["type"]),
            "nullable": bool(col.get("nullable", True)),
            "default": None if col.get("default") is None else str(col["default"]),
            "pk": col["name"] in pk_cols,
            "autoincrement": col.get("autoincrement") is True,
        })
    fks = [
        {
            "columns": fk.get("constrained_columns", []),
            "ref_schema": fk.get("referred_schema"),
            "ref_table": fk.get("referred_table"),
            "ref_columns": fk.get("referred_columns", []),
            "name": fk.get("name"),
        }
        for fk in _safe(lambda: insp.get_foreign_keys(name, schema=schema), [])
    ]
    indexes = [
        {"name": ix.get("name"), "columns": [c for c in ix.get("column_names", []) if c], "unique": bool(ix.get("unique"))}
        for ix in _safe(lambda: insp.get_indexes(name, schema=schema), [])
    ]
    return {
        "name": name,
        "columns": columns,
        "primary_key": pk_cols,
        "foreign_keys": fks,
        "indexes": indexes,
        "row_count": _row_count(engine, schema, name) if count_rows else None,
    }


def _error_text(exc: Exception) -> str:
    root = getattr(exc, "orig", None) or exc
    text = str(root).replace("\\n", " ").replace("\n", " ")
    return f"{type(root).__name__}: {' '.join(text.split())}"[:600]


def _connect_args(url: URL | str, timeout: int) -> dict[str, Any]:
    name = url.drivername if isinstance(url, URL) else str(url).split(":", 1)[0]
    if "pymssql" in name:
        return {"login_timeout": timeout, "timeout": 0}
    if name.startswith("postgresql") or "pymysql" in name:
        return {"connect_timeout": timeout}
    return {}


def snapshot(url: URL | str, *, label: str, count_rows: bool = True, schemas: list[str] | None = None,
             connect_timeout: int = 15) -> dict[str, Any]:
    """Inspect ``url`` and return a JSON-serialisable description of it."""
    engine = create_engine(url, connect_args=_connect_args(url, connect_timeout))
    try:
        insp = sa_inspect(engine)
        default_schema = _safe(lambda: insp.default_schema_name, None)
        all_schemas = _safe(insp.get_schema_names, []) or [default_schema]
        wanted = schemas or [s for s in all_schemas if s not in SYSTEM_SCHEMAS and not str(s).startswith("pg_")]

        out_schemas = []
        for schema in wanted:
            schema_arg = None if schema == default_schema and engine.dialect.name == "sqlite" else schema
            tables = [
                snapshot_table(engine, insp, schema_arg, name, count_rows)
                for name in sorted(_safe(lambda: insp.get_table_names(schema=schema_arg), []))
            ]
            views = sorted(_safe(lambda: insp.get_view_names(schema=schema_arg), []))
            out_schemas.append({"name": schema, "tables": tables, "views": views})

        version = engine.dialect.server_version_info
        return {
            "label": label,
            "url": describe(url),
            "dialect": engine.dialect.name,
            "server_version": ".".join(map(str, version)) if version else None,
            "default_schema": default_schema,
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "schemas": out_schemas,
            "error": None,
        }
    except Exception as exc:
        return {
            "label": label,
            "url": describe(url),
            "dialect": getattr(engine.dialect, "name", None),
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "schemas": [],
            "error": _error_text(exc),
        }
    finally:
        engine.dispose()
