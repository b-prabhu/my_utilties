"""Unit tests: no database needed."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from onroute_migration.chunks import Chunk, date_chunks, int_chunks, source_table_chunks
from onroute_migration.config import TableSpec, load_tables
from onroute_migration.mapping import (MappingError, Reject, SourceColumn, TargetColumn, build_plan,
                                       make_converter, snake)
from onroute_migration.sqlserver import chunk_predicate, qname

TABLES = Path(__file__).parent.parent / "config" / "tables.toml"


def spec(**kw):
    base = dict(key="t", target="master.t", strategy="full", source="dbo.T")
    base.update(kw)
    return TableSpec(**base)


def conv(src, tgt, **kw):
    f, _ = make_converter(src, tgt, spec(**kw), {}, "America/Toronto")
    return f


def test_tables_toml_loads_all_15():
    specs = load_tables(TABLES)
    assert len(specs) == 15
    assert {s.strategy for s in specs} == {"full", "date_range", "int_range", "per_source_table"}
    pos = next(s for s in specs if s.key == "pos_orders")
    assert pos.columns["Endday"] == "end_day"           # global rename merged in


@pytest.mark.parametrize("src,expected", [
    ("OrderDetailID", "order_detail_id"), ("Third_Party_OrderID", "third_party_order_id"),
    ("ALCMaxPrice", "alc_max_price"), ("Day of_Week", "day_of_week"), ("brand_w_DT", "brand_w_dt"),
    ("NSDeptID", "ns_dept_id"), ("ComboPercentBasedDiscountPrice", "combo_percent_based_discount_price"),
])
def test_snake(src, expected):
    assert snake(src) == expected


def test_flag_to_boolean():
    f = conv(SourceColumn("IsRefund", "varchar", 10), TargetColumn("is_refund", "boolean"))
    assert f("Y") is True and f(" true ") is True and f("0") is False and f("") is None and f(None) is None
    with pytest.raises(Reject) as e:
        f("MAYBE")
    assert e.value.reason == "bad_flag_value"


def test_uuid_validation_and_braces():
    f = conv(SourceColumn("GUID", "varchar", 100), TargetColumn("guid", "uuid"))
    u = "6f1c2b9e-1a2b-4c3d-8e9f-0a1b2c3d4e5f"
    assert f("{" + u.upper() + "}") == uuid.UUID(u)
    with pytest.raises(Reject):
        f("not-a-guid")


def test_enum_values():
    f = conv(SourceColumn("OrderTypeName", "varchar", 100), TargetColumn("order_type_name", "USER-DEFINED", enum_labels=["Dine In", "Take Out"]))
    assert f("Dine In") == "Dine In" and f("Take Out ") == "Take Out"
    with pytest.raises(Reject) as e:
        f("Pickup")
    assert e.value.reason == "not_in_enum"


def test_float_to_numeric_rounds_and_checks_overflow():
    stats = {}
    f, _ = make_converter(SourceColumn("cogs", "float"), TargetColumn("cogs", "numeric", precision=15, scale=2), spec(), stats, "UTC")
    assert f(1.005) == Decimal("1.01") or f(1.005) == Decimal("1.00")  # binary float; either way exactly 2 places
    assert f(12.345678) == Decimal("12.35")
    assert stats["rounded:cogs"] >= 1
    with pytest.raises(Reject) as e:
        f(1e13)
    assert e.value.reason == "numeric_overflow"


def test_same_numeric_passes_through():
    f = conv(SourceColumn("Price", "numeric", precision=9, scale=2), TargetColumn("price", "numeric", precision=9, scale=2))
    v = Decimal("12.34")
    assert f(v) is v


def test_length_reject_and_truncate():
    src, tgt = SourceColumn("EmployeeName", "nvarchar", 255), TargetColumn("employee_name", "character varying", max_length=5)
    with pytest.raises(Reject) as e:
        conv(src, tgt)("abcdefg")
    assert e.value.reason == "too_long"
    assert conv(src, tgt, string_overflow="truncate")("abcdefg") == "abcde"


def test_nul_characters_removed():
    f = conv(SourceColumn("x", "varchar", 10), TargetColumn("x", "character varying", max_length=10))
    assert f("a\x00b") == "ab"


def test_datetime_to_text_and_date():
    f = conv(SourceColumn("PayDate", "datetime"), TargetColumn("pay_date", "character varying", max_length=20))
    assert f(datetime(2024, 3, 5, 7, 8, 9)) == "2024-03-05 07:08:09"
    stats = {}
    g, _ = make_converter(SourceColumn("period", "datetime"), TargetColumn("period", "date"), spec(), stats, "UTC")
    assert g(datetime(2024, 3, 5, 13, 0)) == date(2024, 3, 5)
    assert stats["time_dropped:period"] == 1


def test_not_null_reject_and_default():
    tgt = TargetColumn("category", "character varying", max_length=255, nullable=False, has_default=True)
    with pytest.raises(Reject):
        conv(SourceColumn("category", "nvarchar", 100), tgt)(None)
    assert conv(SourceColumn("category", "nvarchar", 100), tgt, null_defaults={"category": ""})(None) == ""


def test_plan_requires_every_source_column_mapped_or_ignored():
    src = [SourceColumn("A", "int"), SourceColumn("Mystery", "int")]
    tgt = [TargetColumn("a", "integer")]
    with pytest.raises(MappingError) as e:
        build_plan(spec(), "dbo.T", src, tgt)
    assert "Mystery" in str(e.value)
    plan = build_plan(spec(ignore=["Mystery"]), "dbo.T", src, tgt)
    assert plan.target_columns == ["a"]


def test_plan_requires_not_null_targets_to_be_fed():
    src = [SourceColumn("A", "int")]
    tgt = [TargetColumn("a", "integer"), TargetColumn("budget_year", "integer", nullable=False)]
    with pytest.raises(MappingError):
        build_plan(spec(), "dbo.T", src, tgt)
    plan = build_plan(spec(constants={"budget_year": "{year}"}), "dbo.T", src, tgt, {"year": "2026"})
    assert plan.transform((1,)) == (1, 2026)


def test_month_week_day_chunks():
    s = spec(strategy="date_range", chunk_column="Endday", granularity="month")
    ch = date_chunks(s, "dbo.T", datetime(2024, 1, 15), datetime(2024, 3, 2), 5)
    assert [c.chunk_key for c in ch] == ["m:2024-01", "m:2024-02", "m:2024-03", "null"]
    assert (ch[0].lo, ch[0].hi) == ("2024-01-01", "2024-02-01")
    s.granularity = "week"
    wk = date_chunks(s, "dbo.T", date(2024, 1, 3), date(2024, 1, 15), 0)
    assert [c.lo for c in wk] == ["2024-01-01", "2024-01-08", "2024-01-15"]
    s.granularity = "day"
    assert len(date_chunks(s, "dbo.T", date(2024, 2, 27), date(2024, 3, 1), 0)) == 4   # leap year


def test_int_chunks_cover_bounds():
    s = spec(strategy="int_range", chunk_column="ID", chunk_size=1000)
    ch = int_chunks(s, "dbo.T", 1, 2500, 0)
    assert [(c.lo, c.hi) for c in ch] == [("0", "1000"), ("1000", "2000"), ("2000", "3000")]


def test_source_table_chunks_capture_year():
    s = spec(strategy="per_source_table", source=None, source_like="dbo.Sales_20%_UnPivot_New",
             source_regex=r"Sales_(?P<year>\d{4})_UnPivot_New", chunk_target_column="budget_year")
    ch = source_table_chunks(s, ["dbo.Sales_2026_UnPivot_New", "dbo.Sales_2025_UnPivot_New", "dbo.Sales_Old"])
    assert [c.chunk_key for c in ch] == ["src:2025", "src:2026"]
    assert ch[0].context_dict == {"year": "2025"}


def test_sqlserver_predicates():
    assert qname("dbo.POS_ORDERS") == "[dbo].[POS_ORDERS]"
    where, params = chunk_predicate(Chunk("t", "m:2024-01", "date", "2024-01-01", "2024-02-01"), "Endday")
    assert where == "[Endday] >= ? AND [Endday] < ?" and params[0] == datetime(2024, 1, 1)
    assert chunk_predicate(Chunk("t", "null", "null"), "Endday")[0] == "[Endday] IS NULL"
