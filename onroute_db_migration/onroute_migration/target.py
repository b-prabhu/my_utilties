"""PostgreSQL target: connections and column metadata."""

from __future__ import annotations

import psycopg
from psycopg import sql

from .mapping import TargetColumn


def connect(settings: dict, autocommit: bool = False, application_name: str = "onroute-migration") -> psycopg.Connection:
    conn = psycopg.connect(settings["dsn"], autocommit=autocommit, application_name=application_name)
    return conn


def table_ident(qualified: str) -> sql.Composed:
    schema, name = qualified.split(".", 1)
    return sql.SQL(".").join([sql.Identifier(schema), sql.Identifier(name)])


def columns(conn: psycopg.Connection, qualified: str) -> list[TargetColumn]:
    schema, name = qualified.split(".", 1)
    rows = conn.execute(
        """SELECT c.column_name, c.data_type, c.character_maximum_length, c.numeric_precision,
                  c.numeric_scale, c.is_nullable = 'YES', c.column_default IS NOT NULL,
                  c.is_identity = 'YES', c.udt_schema, c.udt_name
           FROM information_schema.columns c
           WHERE c.table_schema = %s AND c.table_name = %s
           ORDER BY c.ordinal_position""", (schema, name)).fetchall()
    out = []
    for r in rows:
        labels = None
        if r[1] == "USER-DEFINED":
            enum = conn.execute(
                """SELECT e.enumlabel FROM pg_enum e
                   JOIN pg_type t ON t.oid = e.enumtypid
                   JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = %s AND t.typname = %s ORDER BY e.enumsortorder""", (r[8], r[9])).fetchall()
            labels = [e[0] for e in enum] if enum else None
        out.append(TargetColumn(
            name=r[0], data_type=r[1], max_length=r[2],
            precision=r[3] if r[1] == "numeric" else None,
            scale=r[4] if r[1] == "numeric" else None,
            nullable=r[5], has_default=r[6] or r[7], is_identity=r[7], enum_labels=labels))
    return out


def has_leading_index(conn: psycopg.Connection, qualified: str, column: str) -> bool:
    schema, name = qualified.split(".", 1)
    row = conn.execute(
        """SELECT 1 FROM pg_index i
           JOIN pg_class t ON t.oid = i.indrelid
           JOIN pg_namespace n ON n.oid = t.relnamespace
           JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0]
           WHERE n.nspname = %s AND t.relname = %s AND a.attname = %s LIMIT 1""", (schema, name, column)).fetchone()
    return row is not None


def is_empty(conn: psycopg.Connection, qualified: str) -> bool:
    return conn.execute(sql.SQL("SELECT NOT EXISTS (SELECT 1 FROM {})").format(table_ident(qualified))).fetchone()[0]


def estimated_rows(conn: psycopg.Connection, qualified: str) -> int | None:
    schema, name = qualified.split(".", 1)
    row = conn.execute(
        """SELECT c.reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = %s AND c.relname = %s""", (schema, name)).fetchone()
    return None if row is None or row[0] < 0 else int(row[0])
