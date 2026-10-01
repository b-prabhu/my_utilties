"""Plain data structures describing the source schema."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    data_type: str  # SQL Server type name, lower case (e.g. "nvarchar")
    nullable: bool = True
    max_length: int | None = None  # characters; -1 means MAX
    precision: int | None = None
    scale: int | None = None
    datetime_precision: int | None = None
    default: str | None = None  # raw SQL Server default expression
    is_identity: bool = False
    is_computed: bool = False
    ordinal: int = 0


@dataclass
class ForeignKey:
    name: str
    columns: list[str]
    ref_schema: str
    ref_table: str
    ref_columns: list[str]
    on_delete: str = "NO ACTION"
    on_update: str = "NO ACTION"


@dataclass
class Index:
    name: str
    columns: list[str]
    unique: bool = False
    filter: str | None = None  # SQL Server filtered indexes are reported, not migrated


@dataclass
class Table:
    schema: str
    name: str
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    primary_key_name: str | None = None
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def data_columns(self) -> list[Column]:
        """Columns that hold stored data (computed columns are excluded)."""
        return [c for c in self.columns if not c.is_computed]
