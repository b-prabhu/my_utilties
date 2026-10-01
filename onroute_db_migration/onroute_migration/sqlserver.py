"""SQL Server source (read only), via pyodbc."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .chunks import Chunk
from .mapping import SourceColumn


def qname(table: str) -> str:
    """dbo.POS_ORDERS -> [dbo].[POS_ORDERS]"""
    schema, _, name = table.partition(".")
    if not name:
        schema, name = "dbo", schema
    return f"{qident(schema)}.{qident(name)}"


def qident(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def split(table: str) -> tuple[str, str]:
    schema, _, name = table.partition(".")
    return (schema, name) if name else ("dbo", schema)


def chunk_predicate(chunk: Chunk, column: str | None) -> tuple[str, list]:
    if chunk.kind in ("full", "source_table"):
        return "1=1", []
    col = qident(column)
    if chunk.kind == "null":
        return f"{col} IS NULL", []
    if chunk.kind == "date":
        return f"{col} >= ? AND {col} < ?", [datetime.fromisoformat(chunk.lo), datetime.fromisoformat(chunk.hi)]
    if chunk.kind == "int":
        return f"{col} >= ? AND {col} < ?", [int(chunk.lo), int(chunk.hi)]
    raise ValueError(f"unknown chunk kind {chunk.kind}")


class SqlServerSource:
    def __init__(self, settings: dict):
        self.settings = settings
        self._conn = None

    # -- connection
    @property
    def conn(self):
        if self._conn is None:
            import pyodbc  # imported lazily so the rest of the tool works without the driver
            self._conn = pyodbc.connect(self.settings["dsn"], autocommit=True)
            iso = self.settings.get("isolation", "READ COMMITTED").upper()
            self._conn.execute(f"SET TRANSACTION ISOLATION LEVEL {iso}")
            self._conn.execute("SET ARITHABORT ON")
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _rows(self, sql: str, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, *params) if params else cur.execute(sql)
        return cur.fetchall()

    # -- metadata
    def columns(self, table: str) -> list[SourceColumn]:
        schema, name = split(table)
        rows = self._rows(
            """SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION,
                      NUMERIC_SCALE, IS_NULLABLE
               FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
               ORDER BY ORDINAL_POSITION""", (schema, name))
        cols = []
        for r in rows:
            dt = r[1].lower()
            cols.append(SourceColumn(
                name=r[0], data_type=dt, max_length=r[2],
                precision=r[3] if dt in ("decimal", "numeric") else None,
                scale=r[4] if dt in ("decimal", "numeric") else None,
                nullable=r[5] == "YES"))
        return cols

    def find_tables(self, like: str) -> list[str]:
        schema, pattern = split(like)
        rows = self._rows(
            "SELECT TABLE_SCHEMA + '.' + TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = ? AND TABLE_NAME LIKE ?", (schema, pattern))
        return [r[0] for r in rows]

    def row_count(self, table: str) -> int:
        """Fast committed row count from partition stats (no table scan)."""
        rows = self._rows(
            "SELECT SUM(p.row_count) FROM sys.dm_db_partition_stats p "
            "WHERE p.object_id = OBJECT_ID(?) AND p.index_id IN (0, 1)", (qname(table),))
        if rows and rows[0][0] is not None:
            return int(rows[0][0])
        return int(self._rows(f"SELECT COUNT_BIG(*) FROM {qname(table)}")[0][0])

    def has_index_on(self, table: str, column: str) -> bool:
        rows = self._rows(
            """SELECT 1 FROM sys.index_columns ic
               JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
               WHERE ic.object_id = OBJECT_ID(?) AND ic.key_ordinal = 1 AND c.name = ?""",
            (qname(table), column))
        return bool(rows)

    def bounds(self, table: str, column: str):
        col = qident(column)
        r = self._rows(
            f"SELECT MIN({col}), MAX({col}), SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) FROM {qname(table)}")[0]
        return r[0], r[1], int(r[2] or 0)

    # -- data
    def read(self, table: str, columns: list[str], chunk: Chunk, chunk_column: str | None, batch_size: int):
        where, params = chunk_predicate(chunk, chunk_column)
        cols = ", ".join(qident(c) for c in columns)
        cur = self.conn.cursor()
        cur.arraysize = batch_size
        cur.execute(f"SELECT {cols} FROM {qname(table)} WHERE {where}", *params)
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            yield rows
        cur.close()

    def aggregate(self, table: str, chunk: Chunk, chunk_column: str | None, checksum_column: str | None):
        where, params = chunk_predicate(chunk, chunk_column)
        total = f"SUM(CAST({qident(checksum_column)} AS decimal(38,6)))" if checksum_column else "NULL"
        r = self._rows(f"SELECT COUNT_BIG(*), {total} FROM {qname(table)} WHERE {where}", params)[0]
        return int(r[0]), (Decimal(r[1]) if r[1] is not None else None)

    # -- profiling
    def profile(self, table: str, checks: list[dict], sample_pct: float | None = None) -> dict:
        src = qname(table) + (f" TABLESAMPLE ({float(sample_pct)} PERCENT)" if sample_pct else "")
        aggs, keys = ["COUNT_BIG(*)"], ["rows"]
        out: dict = {}
        for i, c in enumerate(checks):
            col = qident(c["column"]) if "column" in c else None
            k = c["check"]
            if k == "too_long":
                aggs += [f"SUM(CASE WHEN LEN({col} + 'x') - 1 > {int(c['limit'])} THEN 1 ELSE 0 END)", f"MAX(LEN({col} + 'x') - 1)"]
                keys += [f"{i}:count", f"{i}:max"]
            elif k == "nulls":
                aggs.append(f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END)")
                keys.append(f"{i}:count")
            elif k == "bad_uuid":
                aggs.append(f"SUM(CASE WHEN {col} IS NOT NULL AND LTRIM(RTRIM({col})) <> '' "
                            f"AND TRY_CONVERT(uniqueidentifier, {col}) IS NULL THEN 1 ELSE 0 END)")
                keys.append(f"{i}:count")
            elif k == "numeric_overflow":
                aggs += [f"SUM(CASE WHEN ABS(CAST({col} AS float)) >= {float(c['limit'])} THEN 1 ELSE 0 END)",
                         f"MAX(ABS(CAST({col} AS float)))"]
                keys += [f"{i}:count", f"{i}:max"]
            elif k == "time_part":
                aggs.append(f"SUM(CASE WHEN CAST({col} AS time) <> '00:00:00' THEN 1 ELSE 0 END)")
                keys.append(f"{i}:count")
        r = self._rows(f"SELECT {', '.join(aggs)} FROM {src}")[0]
        values = dict(zip(keys, r))
        out["rows"] = int(values["rows"])
        for i, c in enumerate(checks):
            res = {}
            if f"{i}:count" in values:
                res["count"] = int(values[f"{i}:count"] or 0)
            if f"{i}:max" in values and values[f"{i}:max"] is not None:
                res["max"] = float(values[f"{i}:max"])
            if c["check"] == "distinct":
                col = qident(c["column"])
                top = self._rows(f"SELECT TOP 50 {col}, COUNT_BIG(*) FROM {src} GROUP BY {col} ORDER BY COUNT_BIG(*) DESC")
                res["values"] = [[None if v is None else str(v), int(n)] for v, n in top]
                res["distinct"] = int(self._rows(f"SELECT COUNT(DISTINCT {col}) FROM {src}")[0][0])
            if c["check"] == "duplicates":
                cols = ", ".join(qident(x) for x in c["columns"])
                res["count"] = int(self._rows(
                    f"SELECT COUNT_BIG(*) FROM (SELECT {cols} FROM {src} GROUP BY {cols} HAVING COUNT_BIG(*) > 1) d")[0][0])
            out[i] = res
        return out


def from_settings(settings) -> SqlServerSource:
    return SqlServerSource(settings.source)
