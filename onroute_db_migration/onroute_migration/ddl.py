"""Pure functions that turn the introspected SQL Server schema into PostgreSQL DDL.

Nothing in this module talks to a database, so it is fully unit-testable.
"""

from __future__ import annotations

import re

from .models import Column, ForeignKey, Index, Table

# Types whose values pyodbc cannot read natively; they are converted to text
# in the SELECT issued against SQL Server (see source.select_expression).
TEXT_CAST_TYPES = {"geography", "geometry", "hierarchyid", "sql_variant"}

_SIMPLE_TYPES = {
    "bigint": "bigint",
    "int": "integer",
    "smallint": "smallint",
    "tinyint": "smallint",
    "bit": "boolean",
    "money": "numeric(19,4)",
    "smallmoney": "numeric(10,4)",
    "real": "real",
    "date": "date",
    "smalldatetime": "timestamp(0)",
    "datetime": "timestamp(3)",
    "text": "text",
    "ntext": "text",
    "image": "bytea",
    "uniqueidentifier": "uuid",
    "xml": "xml",
    "timestamp": "bytea",  # rowversion
    "rowversion": "bytea",
    "sql_variant": "text",
    "hierarchyid": "text",
    "geography": "text",  # switch to PostGIS geography if the extension is available
    "geometry": "text",
}


class NameMapper:
    """Maps SQL Server identifiers to PostgreSQL identifiers."""

    def __init__(self, lowercase: bool = True, schema_map: dict[str, str] | None = None):
        self.lowercase = lowercase
        self.schema_map = {k.lower(): v for k, v in (schema_map or {}).items()}

    def ident(self, name: str) -> str:
        return name.lower() if self.lowercase else name

    def schema(self, name: str) -> str:
        mapped = self.schema_map.get(name.lower())
        return mapped if mapped is not None else self.ident(name)

    def table(self, table: Table) -> str:
        return f"{quote(self.schema(table.schema))}.{quote(self.ident(table.name))}"

    def ref_table(self, schema: str, name: str) -> str:
        return f"{quote(self.schema(schema))}.{quote(self.ident(name))}"


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def map_type(col: Column) -> str:
    """Return the PostgreSQL type for a SQL Server column."""
    t = col.data_type.lower()

    if t in _SIMPLE_TYPES:
        return _SIMPLE_TYPES[t]

    if t in ("decimal", "numeric"):
        if col.precision is not None:
            return f"numeric({col.precision},{col.scale or 0})"
        return "numeric"

    if t == "float":
        # SQL Server float(n): n <= 24 is 4-byte, otherwise 8-byte.
        if col.precision is not None and col.precision <= 24:
            return "real"
        return "double precision"

    if t in ("datetime2", "time", "datetimeoffset"):
        # SQL Server allows up to 7 fractional digits; PostgreSQL allows 6.
        p = col.datetime_precision
        suffix = f"({min(p, 6)})" if p is not None else ""
        base = {"datetime2": "timestamp", "time": "time", "datetimeoffset": "timestamptz"}[t]
        return f"{base}{suffix}"

    if t in ("char", "nchar"):
        return f"char({col.max_length})" if col.max_length and col.max_length > 0 else "char(1)"

    if t in ("varchar", "nvarchar"):
        if col.max_length is None or col.max_length < 0:
            return "text"
        return f"varchar({col.max_length})"

    if t in ("binary", "varbinary"):
        return "bytea"

    raise ValueError(f"Unsupported SQL Server type {col.data_type!r} for column {col.name!r}")


_PAREN_WRAPPED = re.compile(r"^\((.*)\)$", re.S)
_FUNC_DEFAULTS = {
    "getdate()": "CURRENT_TIMESTAMP",
    "sysdatetime()": "CURRENT_TIMESTAMP",
    "current_timestamp": "CURRENT_TIMESTAMP",
    "getutcdate()": "(now() AT TIME ZONE 'utc')",
    "sysutcdatetime()": "(now() AT TIME ZONE 'utc')",
    "sysdatetimeoffset()": "CURRENT_TIMESTAMP",
    "newid()": "gen_random_uuid()",
    "newsequentialid()": "gen_random_uuid()",
    "suser_sname()": "CURRENT_USER",
    "user_name()": "CURRENT_USER",
}


def _strip_parens(expr: str) -> str:
    expr = expr.strip()
    while True:
        m = _PAREN_WRAPPED.match(expr)
        if not m or not _balanced(m.group(1)):
            return expr
        expr = m.group(1).strip()


def _balanced(s: str) -> bool:
    depth = 0
    in_str = False
    for ch in s:
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return False
    return depth == 0 and not in_str


def translate_default(col: Column) -> str | None:
    """Translate a SQL Server default expression.

    Returns None when there is no default or it cannot be translated safely;
    untranslatable defaults are reported by ``untranslatable_defaults``.
    """
    if not col.default:
        return None
    expr = _strip_parens(col.default)
    low = expr.lower()

    if low in _FUNC_DEFAULTS:
        return _FUNC_DEFAULTS[low]

    if col.data_type.lower() == "bit" and low in ("0", "1"):
        return "false" if low == "0" else "true"

    if re.fullmatch(r"-?\d+(\.\d+)?", expr):
        return expr

    # String literals, optionally N-prefixed: N'abc' -> 'abc'
    m = re.fullmatch(r"N?('(?:[^']|'')*')", expr, re.S)
    if m:
        return m.group(1)

    if low == "null":
        return "NULL"

    return None


def untranslatable_defaults(table: Table) -> list[tuple[str, str]]:
    return [
        (c.name, c.default)
        for c in table.columns
        if c.default and not c.is_computed and translate_default(c) is None
    ]


def column_ddl(col: Column, names: NameMapper) -> str:
    pg_type = map_type(col)
    if col.is_identity and pg_type.startswith("numeric"):
        pg_type = "bigint"  # SQL Server allows decimal(p,0) identities; PostgreSQL does not
    parts = [quote(names.ident(col.name)), pg_type]
    if col.is_identity:
        parts.append("GENERATED BY DEFAULT AS IDENTITY")
    else:
        default = translate_default(col)
        if default is not None:
            parts.append(f"DEFAULT {default}")
    if not col.nullable:
        parts.append("NOT NULL")
    return " ".join(parts)


def create_table_ddl(table: Table, names: NameMapper) -> str:
    """CREATE TABLE including the primary key, but not FKs or secondary indexes.

    Computed columns are emitted as regular columns: their values are copied
    from SQL Server. Recreate them as generated columns or views afterwards if
    needed (they are listed in the migration report).
    """
    lines = [column_ddl(c, names) for c in table.columns]
    if table.primary_key:
        pk_cols = ", ".join(quote(names.ident(c)) for c in table.primary_key)
        constraint = (
            f"CONSTRAINT {quote(names.ident(table.primary_key_name))} "
            if table.primary_key_name
            else ""
        )
        lines.append(f"{constraint}PRIMARY KEY ({pk_cols})")
    body = ",\n    ".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {names.table(table)} (\n    {body}\n);"


def index_ddl(table: Table, index: Index, names: NameMapper) -> str | None:
    if index.filter:
        return None  # filtered index predicates need manual translation
    cols = ", ".join(quote(names.ident(c)) for c in index.columns)
    unique = "UNIQUE " if index.unique else ""
    return (
        f"CREATE {unique}INDEX IF NOT EXISTS {quote(names.ident(index.name))} "
        f"ON {names.table(table)} ({cols});"
    )


def foreign_key_ddl(table: Table, fk: ForeignKey, names: NameMapper) -> str:
    cols = ", ".join(quote(names.ident(c)) for c in fk.columns)
    ref_cols = ", ".join(quote(names.ident(c)) for c in fk.ref_columns)
    return (
        f"ALTER TABLE {names.table(table)} ADD CONSTRAINT {quote(names.ident(fk.name))} "
        f"FOREIGN KEY ({cols}) REFERENCES {names.ref_table(fk.ref_schema, fk.ref_table)} "
        f"({ref_cols}) ON DELETE {_fk_action(fk.on_delete)} ON UPDATE {_fk_action(fk.on_update)};"
    )


def _fk_action(action: str) -> str:
    return action.replace("_", " ").upper()


def identity_reset_sql(table: Table, names: NameMapper) -> list[str]:
    """Statements that move identity sequences past the migrated max value."""
    stmts = []
    for c in table.columns:
        if not c.is_identity:
            continue
        col = quote(names.ident(c.name))
        tbl = names.table(table)
        # pg_get_serial_sequence wants the table as a text literal.
        tbl_literal = "'" + tbl.replace("'", "''") + "'"
        col_literal = "'" + names.ident(c.name).replace("'", "''") + "'"
        stmts.append(
            f"SELECT setval(pg_get_serial_sequence({tbl_literal}, {col_literal}), "
            f"COALESCE((SELECT MAX({col}) FROM {tbl}), 0) + 1, false);"
        )
    return stmts


def build_schema_script(tables: list[Table], names: NameMapper) -> dict[str, list[str]]:
    """Return DDL grouped by phase: pre-data (schemas, tables) and post-data
    (indexes, foreign keys). FKs are added after the load so table order and
    circular references don't matter."""
    schemas = sorted({names.schema(t.schema) for t in tables})
    pre = ["CREATE EXTENSION IF NOT EXISTS pgcrypto;"]  # gen_random_uuid on PG < 13
    pre += [f"CREATE SCHEMA IF NOT EXISTS {quote(s)};" for s in schemas]
    pre += [create_table_ddl(t, names) for t in tables]

    post: list[str] = []
    for t in tables:
        for ix in t.indexes:
            stmt = index_ddl(t, ix, names)
            if stmt:
                post.append(stmt)
    for t in tables:
        post += [foreign_key_ddl(t, fk, names) for fk in t.foreign_keys]
    return {"pre_data": pre, "post_data": post}
