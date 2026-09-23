"""Compare a source and target snapshot: which tables line up and how their columns differ."""

from __future__ import annotations

import re
from typing import Any

# Generic SQLAlchemy type names grouped into families that migrate without data loss in practice.
FAMILIES = {
    "int": {"INTEGER", "SMALLINTEGER", "BIGINTEGER", "TINYINT", "SMALLINT", "BIGINT", "INT"},
    "decimal": {"NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "MONEY", "SMALLMONEY", "DOUBLE_PRECISION"},
    "text": {"STRING", "VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "TEXT", "NTEXT", "UNICODE", "UNICODETEXT", "CLOB"},
    "bool": {"BOOLEAN", "BIT"},
    "datetime": {"DATETIME", "TIMESTAMP", "DATETIME2", "SMALLDATETIME", "DATETIMEOFFSET"},
    "date": {"DATE"},
    "time": {"TIME"},
    "binary": {"LARGEBINARY", "BINARY", "VARBINARY", "BLOB", "BYTEA", "IMAGE"},
    "uuid": {"UUID", "UNIQUEIDENTIFIER", "UUIDTYPE"},
    "json": {"JSON", "JSONB"},
}
_FAMILY_OF = {t: fam for fam, types in FAMILIES.items() for t in types}
_LENGTH = re.compile(r"\((\d+)")
_INT_RANK = {"TINYINT": 1, "SMALLINTEGER": 2, "SMALLINT": 2, "INTEGER": 3, "INT": 3, "BIGINTEGER": 4, "BIGINT": 4}


def _base(type_str: str) -> str:
    return re.split(r"[\s(]", type_str.strip().upper(), maxsplit=1)[0]


def family(col: dict) -> str | None:
    return _FAMILY_OF.get(_base(col["type"])) or _FAMILY_OF.get(col["generic"])


def _length(type_str: str) -> int | None:
    if "MAX" in type_str.upper():
        return None
    m = _LENGTH.search(type_str)
    return int(m.group(1)) if m else None


def type_verdict(src: dict, tgt: dict) -> tuple[str, str | None]:
    """Return (verdict, note) where verdict is 'same', 'compatible', 'narrowing' or 'mismatch'."""
    fs, ft = family(src), family(tgt)
    if fs is None or ft is None or fs != ft:
        if src["generic"] == tgt["generic"]:
            return "same", None
        return "mismatch", f"{src['type']} → {tgt['type']}"
    if fs == "text":
        ls, lt = _length(src["type"]), _length(tgt["type"])
        if lt is not None and (ls is None or ls > lt):
            return "narrowing", f"length {ls or 'unbounded'} → {lt}"
    if fs == "int":
        rs = _INT_RANK.get(src["generic"], _INT_RANK.get(_base(src["type"]), 3))
        rt = _INT_RANK.get(tgt["generic"], _INT_RANK.get(_base(tgt["type"]), 3))
        if rt < rs:
            return "narrowing", f"{src['type']} → {tgt['type']}"
    if src["generic"] == tgt["generic"]:
        return "same", None
    return "compatible", f"{src['type']} → {tgt['type']}"


def compare_columns(src_cols: list[dict], tgt_cols: list[dict]) -> list[dict]:
    tgt_by_name = {c["name"].lower(): c for c in tgt_cols}
    rows, seen = [], set()
    for s in src_cols:
        key = s["name"].lower()
        t = tgt_by_name.get(key)
        if t is None:
            rows.append({"name": s["name"], "source": s, "target": None, "status": "missing", "notes": ["not in target"]})
            continue
        seen.add(key)
        verdict, note = type_verdict(s, t)
        notes = [note] if note else []
        status = {"same": "ok", "compatible": "ok", "narrowing": "warn"}.get(verdict, "error")
        if s["nullable"] and not t["nullable"]:
            notes.append("target is NOT NULL but source allows NULL")
            status = "warn" if status == "ok" else status
        if s["pk"] != t["pk"]:
            notes.append("primary key differs")
            status = "warn" if status == "ok" else status
        rows.append({"name": s["name"], "source": s, "target": t, "status": status, "type_verdict": verdict, "notes": notes})
    for t in tgt_cols:
        if t["name"].lower() not in seen:
            notes = ["only in target"]
            status = "extra"
            if not t["nullable"] and t["default"] is None and not t["autoincrement"]:
                notes.append("NOT NULL with no default — inserts will fail")
                status = "error"
            rows.append({"name": t["name"], "source": None, "target": t, "status": status, "notes": notes})
    return rows


def _index(snap: dict) -> dict[tuple[str, str], dict]:
    return {(s["name"], t["name"]): t for s in snap.get("schemas", []) for t in s["tables"]}


def compare(source: dict, target: dict, schema_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Pair tables by (mapped schema, name) case-insensitively, falling back to name alone."""
    schema_map = {k.lower(): v for k, v in (schema_map or {}).items()}
    src_tables, tgt_tables = _index(source), _index(target)

    tgt_exact = {(s.lower(), n.lower()): (s, n) for s, n in tgt_tables}
    tgt_by_name: dict[str, list[tuple[str, str]]] = {}
    for s, n in tgt_tables:
        tgt_by_name.setdefault(n.lower(), []).append((s, n))
    tgt_default = (target.get("default_schema") or "").lower()

    pairs, used = [], set()
    for (s_schema, s_name), s_table in sorted(src_tables.items()):
        mapped = schema_map.get(s_schema.lower(), s_schema).lower()
        key = tgt_exact.get((mapped, s_name.lower()))
        if key is None or key in used:
            candidates = [k for k in tgt_by_name.get(s_name.lower(), []) if k not in used]
            preferred = [k for k in candidates if k[0].lower() == tgt_default]
            key = (preferred or candidates or [None])[0]
        entry = {"source_schema": s_schema, "source_table": s_name, "source": s_table}
        if key is None:
            entry.update(status="source_only", target_schema=None, target_table=None, target=None, columns=[])
        else:
            used.add(key)
            t_table = tgt_tables[key]
            cols = compare_columns(s_table["columns"], t_table["columns"])
            worst = "ok"
            for c in cols:
                if c["status"] in ("error", "missing"):
                    worst = "error"
                    break
                if c["status"] in ("warn", "extra"):
                    worst = "warn"
            sc, tc = s_table.get("row_count"), t_table.get("row_count")
            entry.update(
                status={"ok": "matched", "warn": "matched_warn", "error": "matched_error"}[worst],
                target_schema=key[0], target_table=key[1], target=t_table, columns=cols,
                row_diff=None if sc is None or tc is None else tc - sc,
            )
        pairs.append(entry)

    for key, t_table in sorted(tgt_tables.items()):
        if key not in used:
            pairs.append({
                "status": "target_only", "source_schema": None, "source_table": None, "source": None,
                "target_schema": key[0], "target_table": key[1], "target": t_table, "columns": [],
            })

    counts: dict[str, int] = {}
    for p in pairs:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    return {"pairs": pairs, "counts": counts, "schema_map": schema_map}
