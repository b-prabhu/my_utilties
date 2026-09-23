"""Render source/target snapshots and their comparison as a self-contained HTML page."""

from __future__ import annotations

import datetime as dt
import json
from importlib import resources
from pathlib import Path

from .compare import compare

DEFAULT_SCHEMA_MAPS = {
    ("mssql", "postgresql"): {"dbo": "public"},
    ("mysql", "postgresql"): {},
}


def default_schema_map(source: dict, target: dict) -> dict[str, str]:
    mapping = dict(DEFAULT_SCHEMA_MAPS.get((source.get("dialect"), target.get("dialect")), {}))
    s_def, t_def = source.get("default_schema"), target.get("default_schema")
    if s_def and t_def and s_def not in mapping:
        mapping[s_def] = t_def
    return mapping


def build_report(source: dict, target: dict, schema_map: dict[str, str] | None = None) -> str:
    if schema_map is None:
        schema_map = default_schema_map(source, target)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "target": target,
        "comparison": compare(source, target, schema_map),
    }
    # Keep the embedded JSON from terminating the <script> element early.
    blob = json.dumps(payload, default=str).replace("</", "<\\/")
    template = resources.files(__package__).joinpath("report_template.html").read_text()
    return template.replace("__REPORT_DATA__", blob)


def write_report(path: str | Path, source: dict, target: dict, schema_map: dict[str, str] | None = None) -> Path:
    path = Path(path)
    path.write_text(build_report(source, target, schema_map))
    return path
