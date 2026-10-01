"""Resolve source -> target columns and build a per-column converter for each.

Converters are derived from the two sides' types, so the checks only run where
they are needed (a varchar(60) -> varchar(60) column is passed straight through;
a varchar(255) -> varchar(100) column gets a length check).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .config import TableSpec

STRING_SRC = {"varchar", "nvarchar", "char", "nchar", "text", "ntext", "sysname"}
DATETIME_SRC = {"datetime", "smalldatetime", "datetime2"}
FLOAT_SRC = {"float", "real"}
NUMERIC_SRC = {"decimal", "numeric", "money", "smallmoney"}
INT_SRC = {"tinyint": (0, 255), "smallint": (-2**15, 2**15 - 1), "int": (-2**31, 2**31 - 1), "bigint": (-2**63, 2**63 - 1)}
INT_TGT = {"smallint": (-2**15, 2**15 - 1), "integer": (-2**31, 2**31 - 1), "bigint": (-2**63, 2**63 - 1)}
TEXT_TGT = {"character varying", "character", "text"}


@dataclass
class SourceColumn:
    name: str
    data_type: str
    max_length: int | None = None   # characters; -1 = MAX
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True


@dataclass
class TargetColumn:
    name: str
    data_type: str                  # information_schema.columns.data_type
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True
    has_default: bool = False
    is_identity: bool = False
    enum_labels: list[str] | None = None


def identity(v):
    return v


class Reject(Exception):
    """A row that cannot be loaded. Collected in migration.rejected_row."""

    def __init__(self, reason: str, column: str, value: Any, detail: str = ""):
        super().__init__(f"{reason} on {column}: {detail or value!r}")
        self.reason = reason
        self.column = column
        self.value = value
        self.detail = detail


class MappingError(ValueError):
    def __init__(self, table: str, problems: list[str]):
        super().__init__(f"{table}: " + "; ".join(problems))
        self.problems = problems


def snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return re.sub(r"[\s_]+", "_", s).strip("_").lower()


@dataclass
class Step:
    target: TargetColumn
    source_index: int | None        # index into the selected source columns; None = constant
    convert: Callable[[Any], Any]
    constant: Any = None
    note: str = ""


@dataclass
class TablePlan:
    spec: TableSpec
    source_table: str
    source_columns: list[SourceColumn]          # columns to SELECT, in order
    steps: list[Step]                           # one per target column loaded, in COPY order
    checksum_index: int | None = None           # position in the output row
    dedupe_indexes: list[int] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def target_columns(self) -> list[str]:
        return [s.target.name for s in self.steps]

    def transform(self, row) -> tuple:
        fn = self.__dict__.get("_compiled")
        if fn is None:
            fn = self._compiled = self._compile()
        return fn(row)

    def _compile(self):
        """Build one function per table: pass-through columns become plain tuple indexing."""
        ns: dict = {}
        parts = []
        for k, step in enumerate(self.steps):
            if step.source_index is None:
                ns[f"c{k}"], ns[f"v{k}"] = step.convert, step.constant
                parts.append(f"c{k}(v{k})")
            elif step.convert is identity:
                parts.append(f"row[{int(step.source_index)}]")
            else:
                ns[f"c{k}"] = step.convert
                parts.append(f"c{k}(row[{int(step.source_index)}])")
        exec("def _transform(row):\n    return (" + ", ".join(parts) + ",)", ns)
        return ns["_transform"]

    def describe(self) -> list[dict]:
        rows = []
        for s in self.steps:
            src = self.source_columns[s.source_index].name if s.source_index is not None else f"constant {s.constant!r}"
            rows.append({"source": src, "target": s.target.name, "conversion": s.note or "as is"})
        return rows


def resolve_target_name(spec: TableSpec, src: str, targets: dict[str, TargetColumn]) -> str | None:
    if src in spec.columns:
        return spec.columns[src]
    if src in targets:
        return src
    s = snake(src)
    if s in targets:
        return s
    lowered = {k.lower(): k for k in targets}
    return lowered.get(src.lower())


def build_plan(spec: TableSpec, source_table: str, source_cols: list[SourceColumn],
               target_cols: list[TargetColumn], context: dict | None = None,
               timezone: str = "UTC") -> TablePlan:
    context = context or {}
    targets = {c.name: c for c in target_cols}
    problems: list[str] = []
    plan = TablePlan(spec=spec, source_table=source_table, source_columns=[], steps=[])
    used: dict[str, str] = {}

    ignore = {c.lower() for c in spec.ignore}
    for sc in source_cols:
        if sc.name.lower() in ignore:
            continue
        tname = resolve_target_name(spec, sc.name, targets)
        if tname is None or tname not in targets:
            problems.append(f"source column {sc.name!r} has no target column (map it in [table.columns] or add it to ignore)")
            continue
        if tname in used:
            problems.append(f"target column {tname!r} is mapped from both {used[tname]!r} and {sc.name!r}")
            continue
        used[tname] = sc.name
        tc = targets[tname]
        try:
            conv, note = make_converter(sc, tc, spec, plan.stats, timezone)
        except ValueError as e:
            problems.append(str(e))
            continue
        plan.source_columns.append(sc)
        plan.steps.append(Step(tc, len(plan.source_columns) - 1, conv, note=note))

    for tname, raw in spec.constants.items():
        if tname not in targets:
            problems.append(f"constant for unknown target column {tname!r}")
            continue
        if tname in used:
            problems.append(f"target column {tname!r} has both a source column and a constant")
            continue
        try:
            value = str(raw).format(**context)
        except KeyError as e:
            problems.append(f"constant {tname!r} uses {e} which this source table does not provide")
            continue
        used[tname] = f"constant {value!r}"
        pseudo = SourceColumn(f"<{tname}>", "varchar", -1)
        conv, note = make_converter(pseudo, targets[tname], spec, plan.stats, timezone)
        plan.steps.append(Step(targets[tname], None, conv, constant=value, note=f"constant {value!r}" + (f"; {note}" if note else "")))

    for tc in target_cols:
        if tc.name in used:
            continue
        if not tc.nullable and not tc.has_default:
            problems.append(f"target column {tc.name!r} is NOT NULL with no default and nothing maps to it")

    for col in spec.null_defaults:
        if col not in used:
            problems.append(f"null_defaults names {col!r}, which is not loaded")

    names = plan.target_columns
    if spec.checksum_column:
        src_names = [plan.source_columns[s.source_index].name if s.source_index is not None else None for s in plan.steps]
        if spec.checksum_column in src_names:
            plan.checksum_index = src_names.index(spec.checksum_column)
        else:
            problems.append(f"checksum_column {spec.checksum_column!r} is not a loaded source column")
    for col in spec.dedupe_on:
        if col in names:
            plan.dedupe_indexes.append(names.index(col))
        else:
            problems.append(f"dedupe_on column {col!r} is not a loaded target column")

    if problems:
        raise MappingError(spec.key, problems)
    return plan


# ---------------------------------------------------------------- converters

def make_converter(src: SourceColumn, tgt: TargetColumn, spec: TableSpec,
                   stats: dict[str, int], timezone: str) -> tuple[Callable, str]:
    base, note = _base_converter(src, tgt, spec, stats, timezone)
    col = tgt.name
    if tgt.nullable:
        return base, note
    if col in spec.null_defaults:
        default = spec.null_defaults[col]

        def with_default(v, base=base, default=default):
            r = base(v)
            if r is None:
                stats[f"null_default:{col}"] = stats.get(f"null_default:{col}", 0) + 1
                return datetime.now() if default == "@now" else default
            return r
        return with_default, _join(note, f"NULL -> {default!r}")

    def not_null(v, base=base):
        r = base(v)
        if r is None:
            raise Reject("null_not_allowed", col, v, "target column is NOT NULL")
        return r
    return not_null, _join(note, "NOT NULL check" if src.nullable else "")


def _join(*parts: str) -> str:
    return "; ".join(p for p in parts if p)


def _bump(stats, key):
    stats[key] = stats.get(key, 0) + 1


def _base_converter(src: SourceColumn, tgt: TargetColumn, spec: TableSpec, stats, timezone):
    st, tt, col = src.data_type.lower(), tgt.data_type, tgt.name

    if tt == "boolean":
        if st == "bit" or st in INT_SRC:
            return (lambda v: None if v is None else bool(v)), "number -> boolean"
        if st in STRING_SRC:
            trues = {s.upper() for s in spec.true_values}
            falses = {s.upper() for s in spec.false_values}

            def flag(v):
                if v is None:
                    return None
                key = str(v).strip().upper()
                if key in trues:
                    return True
                if key in falses:
                    return False
                if key == "" and spec.empty_flag_is_null:
                    return None
                raise Reject("bad_flag_value", col, v, f"{v!r} is not one of the true/false values")
            return flag, "text flag -> boolean"
        raise ValueError(f"{col}: cannot convert {st} to boolean")

    if tt == "uuid":
        if st == "uniqueidentifier":
            return (lambda v: None if v is None else uuid.UUID(str(v))), "uniqueidentifier -> uuid"

        def to_uuid(v):
            if v is None:
                return None
            s = str(v).strip().strip("{}")
            if not s:
                return None
            try:
                return uuid.UUID(s)
            except ValueError:
                raise Reject("bad_uuid", col, v, f"{v!r} is not a UUID") from None
        return to_uuid, "text -> uuid (validated)"

    if tt == "USER-DEFINED":
        if tgt.enum_labels is None:
            raise ValueError(f"{col}: target type is user-defined but not an enum; add a converter")
        labels = set(tgt.enum_labels)

        def to_enum(v):
            if v is None:
                return None
            if v in labels:
                return v
            s = str(v).strip()
            if s in labels:
                return s
            if s == "":
                return None
            raise Reject("not_in_enum", col, v, f"{v!r} is not an allowed value")
        return to_enum, f"text -> enum ({len(labels)} values)"

    if tt == "numeric":
        p, s = tgt.precision, tgt.scale
        if p is None:
            return (lambda v: None if v is None else Decimal(str(v))), "-> numeric"
        quantum = Decimal(1).scaleb(-(s or 0))
        limit = Decimal(10) ** (p - (s or 0))
        src_fits = (st in NUMERIC_SRC and src.precision is not None
                    and (src.scale or 0) <= (s or 0)
                    and src.precision - (src.scale or 0) <= p - (s or 0))
        if src_fits:
            return identity, ""
        if st in INT_SRC and INT_SRC[st][1] < limit:
            return identity, ""

        def to_numeric(v):
            if v is None:
                return None
            try:
                d = Decimal(repr(v)) if isinstance(v, float) else Decimal(str(v).strip())
            except InvalidOperation:
                raise Reject("bad_number", col, v) from None
            if not d.is_finite():
                raise Reject("bad_number", col, v)
            q = d.quantize(quantum, rounding=ROUND_HALF_UP)
            if abs(q) >= limit:
                raise Reject("numeric_overflow", col, v, f"{v!r} does not fit numeric({p},{s})")
            if q != d:
                _bump(stats, f"rounded:{col}")
            return q
        return to_numeric, f"{st} -> numeric({p},{s}) (rounded, overflow check)"

    if tt in ("double precision", "real"):
        if st in FLOAT_SRC:
            return identity, ""
        return (lambda v: None if v is None else float(v)), f"{st} -> {tt}"

    if tt in INT_TGT:
        lo, hi = INT_TGT[tt]
        if st in INT_SRC and INT_SRC[st][0] >= lo and INT_SRC[st][1] <= hi:
            return identity, ""
        if st == "bit":
            return (lambda v: None if v is None else int(v)), "bit -> integer"

        def to_int(v):
            if v is None:
                return None
            try:
                i = int(str(v).strip()) if isinstance(v, str) else int(v)
            except (TypeError, ValueError):
                raise Reject("bad_integer", col, v) from None
            if isinstance(v, (float, Decimal)) and i != v:
                raise Reject("bad_integer", col, v, f"{v!r} has a fractional part")
            if not lo <= i <= hi:
                raise Reject("integer_overflow", col, v, f"{v!r} out of {tt} range")
            return i
        return to_int, f"{st} -> {tt} (range check)"

    if tt in TEXT_TGT:
        n = tgt.max_length
        if st in STRING_SRC:
            fmt = None
        elif st in DATETIME_SRC:
            fmt = spec.datetime_text_format
        elif st in ("date", "time", "uniqueidentifier") or st in INT_SRC or st in NUMERIC_SRC or st in FLOAT_SRC or st == "bit":
            fmt = ""
        else:
            raise ValueError(f"{col}: cannot convert {st} to text")
        check_len = n is not None and (fmt is not None or src.max_length in (None, -1) or src.max_length > n)
        truncate = spec.string_overflow == "truncate"

        def to_text(v):
            if v is None:
                return None
            if fmt:
                s = v.strftime(fmt)
            elif fmt == "":
                s = v.isoformat() if isinstance(v, (date, time)) else str(v)
            else:
                s = v
                if "\x00" in s:
                    s = s.replace("\x00", "")
                    _bump(stats, f"nul_removed:{col}")
            if check_len and len(s) > n:
                if truncate:
                    _bump(stats, f"truncated:{col}")
                    return s[:n]
                raise Reject("too_long", col, v, f"{len(s)} characters, limit {n}")
            return s
        note = []
        if fmt:
            note.append(f"datetime -> text '{fmt}'")
        elif fmt == "":
            note.append(f"{st} -> text")
        if check_len:
            note.append(f"length <= {n} ({'truncate' if truncate else 'reject'})")
        return to_text, "; ".join(note)

    if tt == "date":
        if st == "date":
            return identity, ""
        if st in DATETIME_SRC:
            def to_date(v):
                if v is None:
                    return None
                if v.time() != time(0):
                    _bump(stats, f"time_dropped:{col}")
                return v.date()
            return to_date, "datetime -> date (time of day dropped)"
        if st in STRING_SRC:
            def parse_date(v):
                if v is None or not str(v).strip():
                    return None
                try:
                    return date.fromisoformat(str(v).strip()[:10])
                except ValueError:
                    raise Reject("bad_date", col, v) from None
            return parse_date, "text -> date"
        raise ValueError(f"{col}: cannot convert {st} to date")

    if tt in ("timestamp without time zone", "timestamp with time zone"):
        tz = ZoneInfo(timezone) if tt == "timestamp with time zone" else None
        if st in DATETIME_SRC or st == "date":
            def to_ts(v):
                if v is None:
                    return None
                if not isinstance(v, datetime):
                    v = datetime.combine(v, time(0))
                return v.replace(tzinfo=tz) if tz and v.tzinfo is None else v
            return to_ts, ("" if st in ("datetime", "datetime2", "smalldatetime") and tz is None else f"{st} -> {tt}")
        if st == "datetimeoffset":
            return identity, ""
        raise ValueError(f"{col}: cannot convert {st} to {tt}")

    raise ValueError(f"{col}: no converter for {st} -> {tt}")


# ---------------------------------------------------------------- profiling checks

def profile_checks(plan: TablePlan) -> list[dict]:
    """Source-side checks that predict rejects, one list per table plan."""
    checks = []
    for step in plan.steps:
        if step.source_index is None:
            continue
        sc, tc = plan.source_columns[step.source_index], step.target
        st, tt = sc.data_type, tc.data_type
        if not tc.nullable and sc.nullable and tc.name not in plan.spec.null_defaults:
            checks.append({"check": "nulls", "column": sc.name, "target": tc.name})
        if tt in TEXT_TGT and tc.max_length and st in STRING_SRC and (sc.max_length in (None, -1) or sc.max_length > tc.max_length):
            checks.append({"check": "too_long", "column": sc.name, "target": tc.name, "limit": tc.max_length})
        if tt == "boolean" and st in STRING_SRC:
            checks.append({"check": "distinct", "column": sc.name, "target": tc.name,
                           "allowed": sorted({*plan.spec.true_values, *plan.spec.false_values})})
        if tt == "USER-DEFINED" and tc.enum_labels is not None:
            checks.append({"check": "distinct", "column": sc.name, "target": tc.name, "allowed": tc.enum_labels})
        if tt == "uuid" and st in STRING_SRC:
            checks.append({"check": "bad_uuid", "column": sc.name, "target": tc.name})
        if tt == "numeric" and tc.precision is not None and st in FLOAT_SRC | NUMERIC_SRC and step.note:
            checks.append({"check": "numeric_overflow", "column": sc.name, "target": tc.name,
                           "limit": 10 ** (tc.precision - (tc.scale or 0))})
        if tt == "date" and st in DATETIME_SRC:
            checks.append({"check": "time_part", "column": sc.name, "target": tc.name})
    if plan.dedupe_indexes:
        src_for = {s.target.name: plan.source_columns[s.source_index].name for s in plan.steps if s.source_index is not None}
        cols = [src_for[plan.steps[i].target.name] for i in plan.dedupe_indexes]
        checks.append({"check": "duplicates", "columns": cols, "target": ",".join(plan.steps[i].target.name for i in plan.dedupe_indexes)})
    return checks
