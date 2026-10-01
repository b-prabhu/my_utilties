"""Load config.toml (connections, run settings) and tables.toml (table definitions)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

STRATEGIES = {"full", "date_range", "int_range", "per_source_table"}
GRANULARITIES = {"day", "week", "month"}


class ConfigError(ValueError):
    pass


@dataclass
class TableSpec:
    key: str
    target: str
    strategy: str
    source: str | None = None
    source_like: str | None = None
    source_regex: str | None = None
    chunk_column: str | None = None
    chunk_target_column: str | None = None
    granularity: str = "month"
    chunk_size: int = 1_000_000
    checksum_column: str | None = None
    priority: int = 100
    columns: dict[str, str] = field(default_factory=dict)
    ignore: list[str] = field(default_factory=list)
    constants: dict[str, str] = field(default_factory=dict)
    null_defaults: dict[str, object] = field(default_factory=dict)
    dedupe_on: list[str] = field(default_factory=list)
    reset_sequence: str | None = None
    datetime_text_format: str = "%Y-%m-%d %H:%M:%S"
    # filled from [defaults]
    batch_size: int = 20000
    max_reject_rows: int = 1000
    max_reject_pct: float = 0.5
    string_overflow: str = "reject"
    true_values: list[str] = field(default_factory=lambda: ["Y", "YES", "T", "TRUE", "1"])
    false_values: list[str] = field(default_factory=lambda: ["N", "NO", "F", "FALSE", "0"])
    empty_flag_is_null: bool = True

    @property
    def target_schema(self) -> str:
        return self.target.split(".", 1)[0]

    @property
    def target_table(self) -> str:
        return self.target.split(".", 1)[1]

    def validate(self) -> None:
        if self.strategy not in STRATEGIES:
            raise ConfigError(f"{self.key}: unknown strategy {self.strategy!r}")
        if "." not in self.target:
            raise ConfigError(f"{self.key}: target must be schema.table")
        if self.strategy == "per_source_table":
            if not (self.source_like and self.source_regex and self.chunk_target_column):
                raise ConfigError(f"{self.key}: per_source_table needs source_like, source_regex and chunk_target_column")
            re.compile(self.source_regex)
        elif not self.source:
            raise ConfigError(f"{self.key}: source is required")
        if self.strategy in ("date_range", "int_range") and not self.chunk_column:
            raise ConfigError(f"{self.key}: {self.strategy} needs chunk_column")
        if self.strategy == "date_range" and self.granularity not in GRANULARITIES:
            raise ConfigError(f"{self.key}: granularity must be one of {sorted(GRANULARITIES)}")
        if self.string_overflow not in ("reject", "truncate"):
            raise ConfigError(f"{self.key}: string_overflow must be reject or truncate")


@dataclass
class Settings:
    source: dict
    target: dict
    run: dict
    dashboard: dict
    tables: list[TableSpec]

    @property
    def control_schema(self) -> str:
        return self.target.get("control_schema", "migration")

    def table(self, key: str) -> TableSpec:
        for t in self.tables:
            if t.key == key:
                return t
        raise ConfigError(f"unknown table {key!r}; known: {', '.join(t.key for t in self.tables)}")

    def select(self, keys: list[str] | None) -> list[TableSpec]:
        if not keys:
            return sorted(self.tables, key=lambda t: t.priority)
        return sorted((self.table(k) for k in keys), key=lambda t: t.priority)


_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand(value):
    if isinstance(value, str):
        def repl(m):
            name = m.group(1)
            if name not in os.environ:
                raise ConfigError(f"environment variable {name} is not set")
            return os.environ[name]
        return _ENV.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def load_tables(path: Path) -> list[TableSpec]:
    data = tomllib.loads(Path(path).read_text())
    defaults = data.get("defaults", {})
    rename = data.get("rename", {})
    specs = []
    seen = set()
    for raw in data.get("table", []):
        merged = {**defaults, **raw}
        merged["columns"] = {**rename, **raw.get("columns", {})}
        known = TableSpec.__dataclass_fields__.keys()
        unknown = set(merged) - set(known)
        if unknown:
            raise ConfigError(f"{raw.get('key')}: unknown settings {sorted(unknown)}")
        spec = TableSpec(**merged)
        spec.validate()
        if spec.key in seen:
            raise ConfigError(f"duplicate table key {spec.key}")
        seen.add(spec.key)
        specs.append(spec)
    return specs


def load(config_path: Path, tables_path: Path | None = None) -> Settings:
    config_path = Path(config_path)
    data = _expand(tomllib.loads(config_path.read_text()))
    tables_path = Path(tables_path) if tables_path else config_path.parent / "tables.toml"
    return Settings(
        source=data.get("source", {}),
        target=data.get("target", {}),
        run={"workers": 4, "max_attempts": 3, "retry_backoff_seconds": 30, "lease_minutes": 20, **data.get("run", {})},
        dashboard={"host": "127.0.0.1", "port": 8765, **data.get("dashboard", {})},
        tables=load_tables(tables_path),
    )
