"""Split each table into chunks: the unit of loading, checkpointing and retry.

Chunks partition the source table, and each chunk maps to a matching slice of
the target table, so a chunk can be reloaded on its own (delete the slice, copy
it again) without touching the rest of the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .config import TableSpec


@dataclass(frozen=True)
class Chunk:
    table_key: str
    chunk_key: str
    kind: str              # full | date | int | null | source_table
    lo: str | None = None  # inclusive bound (ISO date or integer as text)
    hi: str | None = None  # exclusive bound
    source_table: str | None = None
    context: tuple = ()    # (name, value) pairs for constants, e.g. (("year", "2026"),)

    @property
    def context_dict(self) -> dict:
        return dict(self.context)

    @property
    def label(self) -> str:
        if self.kind == "date":
            return f"{self.lo} .. {self.hi}"
        if self.kind == "int":
            return f"{int(self.lo):,} .. {int(self.hi):,}"
        if self.kind == "null":
            return "rows with no value"
        if self.kind == "source_table":
            return self.source_table or self.chunk_key
        return "whole table"


def _as_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


def period_start(d: date, granularity: str) -> date:
    if granularity == "day":
        return d
    if granularity == "week":
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def next_period(d: date, granularity: str) -> date:
    if granularity == "day":
        return d + timedelta(days=1)
    if granularity == "week":
        return d + timedelta(days=7)
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def date_chunks(spec: TableSpec, source_table: str, lo, hi, null_count: int) -> list[Chunk]:
    out = []
    prefix = spec.granularity[0]
    if lo is not None:
        start = period_start(_as_date(lo), spec.granularity)
        last = _as_date(hi)
        while start <= last:
            end = next_period(start, spec.granularity)
            key = start.strftime("%Y-%m") if spec.granularity == "month" else start.isoformat()
            out.append(Chunk(spec.key, f"{prefix}:{key}", "date", start.isoformat(), end.isoformat(), source_table))
            start = end
    if null_count:
        out.append(Chunk(spec.key, "null", "null", source_table=source_table))
    return out


def int_chunks(spec: TableSpec, source_table: str, lo, hi, null_count: int) -> list[Chunk]:
    out = []
    size = spec.chunk_size
    if lo is not None:
        start = (int(lo) // size) * size
        while start <= int(hi):
            end = start + size
            out.append(Chunk(spec.key, f"i:{start:015d}", "int", str(start), str(end), source_table))
            start = end
    if null_count:
        out.append(Chunk(spec.key, "null", "null", source_table=source_table))
    return out


def source_table_chunks(spec: TableSpec, tables: list[str]) -> list[Chunk]:
    rx = re.compile(spec.source_regex)
    out = []
    for name in sorted(tables):
        m = rx.search(name)
        if not m:
            continue
        ctx = tuple(sorted(m.groupdict().items())) or (("match", m.group(0)),)
        key = "src:" + "-".join(v for _, v in ctx)
        out.append(Chunk(spec.key, key, "source_table", source_table=name, context=ctx))
    return out


def plan_chunks(spec: TableSpec, source) -> list[Chunk]:
    """Ask the source for bounds and return every chunk the table needs now."""
    if spec.strategy == "full":
        return [Chunk(spec.key, "all", "full", source_table=spec.source)]
    if spec.strategy == "per_source_table":
        return source_table_chunks(spec, source.find_tables(spec.source_like))
    lo, hi, nulls = source.bounds(spec.source, spec.chunk_column)
    if spec.strategy == "date_range":
        return date_chunks(spec, spec.source, lo, hi, nulls)
    return int_chunks(spec, spec.source, lo, hi, nulls)
