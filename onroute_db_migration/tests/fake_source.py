"""In-memory stand-in for the SQL Server source, used by the tests.

Columns come from the real source export (analysis/inputs); rows are generated,
with a few deliberately bad values so reject handling is exercised. The dataset
is pickled to FAKE_SOURCE_PATH so worker processes see the same data, and tests
can change it between runs to simulate late-arriving or corrected source rows.
"""

from __future__ import annotations

import os
import pickle
import random
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import openpyxl

from onroute_migration.chunks import Chunk
from onroute_migration.mapping import SourceColumn

HERE = Path(__file__).parent
EXPORT = HERE.parent / "analysis" / "inputs" / "source_sqlserver_columns.xlsx"


def source_columns() -> dict[str, list[SourceColumn]]:
    ws = openpyxl.load_workbook(EXPORT, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    head = rows[0]
    out: dict[str, list[SourceColumn]] = {}
    for r in rows[1:]:
        if not r[0]:
            continue
        d = dict(zip(head, r))
        lp = str(d["length_precision"] or "")
        dt = d["data_type"].lower()
        prec = scale = length = None
        if "," in lp:
            prec, scale = (int(x) for x in lp.split(","))
        elif lp:
            length = int(lp)
        out.setdefault(f"{d['schema_name']}.{d['table_name']}", []).append(
            SourceColumn(d["column_name"], dt, length, prec, scale, str(d["is_nullable"]) == "1"))
    return out


def _val(col: SourceColumn, rnd: random.Random, i: int):
    t = col.data_type
    if t in ("int", "bigint"):
        return rnd.randint(1, 50000)
    if t in ("smallint", "tinyint"):
        return rnd.randint(1, 200)
    if t in ("numeric", "decimal"):
        return Decimal(rnd.randint(0, 99999)) / Decimal(10 ** (col.scale or 0))
    if t == "float":
        return round(rnd.uniform(0, 5000), 6)
    if t in ("datetime", "smalldatetime"):
        return datetime(2024, 1, 1) + timedelta(minutes=rnd.randint(0, 150000))
    if t == "date":
        return date(2024, 1, 1) + timedelta(days=rnd.randint(0, 120))
    n = col.max_length if col.max_length and col.max_length > 0 else 30
    return f"{col.name[:6]}{i}"[: min(n, 20)]


def build_dataset(seed: int = 7, orders: int = 2400) -> dict:
    rnd = random.Random(seed)
    cols = source_columns()
    # one Vena table per budget year
    cols["dbo.Sales_2025_UnPivot_New"] = cols["dbo.Sales_2026_UnPivot_New"]
    cols["dbo.EmployeePaySummaryV2"] = cols.pop("dbo.EmployeePaySummaryV2")
    data: dict[str, dict] = {}

    def table(name, n, override=None):
        cs = cols[name]
        rows = []
        for i in range(n):
            row = {c.name: _val(c, rnd, i) for c in cs}
            if override:
                override(row, i)
            rows.append(tuple(row[c.name] for c in cs))
        data[name] = {"columns": cs, "rows": rows}

    flags = ["Y", "N", "True", "False", "1", "0", ""]
    order_types = ["Dine In", "Take Out", "Delivery", "Drive Thru"]
    start = datetime(2024, 1, 1)

    def endday(i):
        if i % 997 == 0:
            return None                       # rows with no business day -> the "null" chunk
        return start + timedelta(days=(i * 107) // orders)

    def order(row, i):
        row.update(OrderID=i + 1, Endday=endday(i), GUID=str(uuid.UUID(int=i + 1)), StoreId=f"S{i % 40:03d}",
                   IsRefund=rnd.choice(flags), OrderTypeName=rnd.choice(order_types))
        if i == 5:
            row["IsRefund"] = "MAYBE"          # bad flag
        if i == 6:
            row["GUID"] = "not-a-guid"         # bad uuid
        if i == 7:
            row["OrderTypeName"] = "Pickup"    # not in enum
        if i == 8:
            row["StoreId"] = None              # NOT NULL in target
    table("dbo.POS_ORDERS", orders, order)

    def detail(row, i):
        o = i // 3
        row.update(OrderID=o + 1, OrderDetailID=i % 3 + 1, Endday=endday(o), GUID=str(uuid.UUID(int=o + 1)),
                   StoreId=f"S{o % 40:03d}", HasMods=rnd.choice(flags), TaxExemption=rnd.choice(flags),
                   Deposit=rnd.choice(flags), OrderTypeName=rnd.choice(order_types), MaxOrderDetailID=3)
    table("dbo.POS_ORDERDETAILS", orders * 3, detail)

    def payment(row, i):
        row.update(OrderID=i + 1, Endday=endday(i), GUID=str(uuid.UUID(int=i + 1)), StoreId=f"S{i % 40:03d}",
                   UsePennyRounding=rnd.choice(flags))
    table("dbo.POS_ORDERPAYMENTS", orders, payment)

    def paidout(row, i):
        row.update(GUID=str(uuid.UUID(int=i + 1)), StoreId=f"S{i % 40:03d}", OrderTypeName=rnd.choice(order_types))
    table("dbo.POS_ORDERPAIDOUTS", 60, paidout)

    def cogs(row, i):
        row.update(WeeklyCogs_ID=i + 1, loc_code=f"L{i % 30}", period=datetime(2024, 1, 1) + timedelta(weeks=i % 20),
                   Start_Date=datetime(2024, 1, 1) + timedelta(weeks=i % 20))
        if i % 50 == 0:
            row["createdate"] = None
        if i == 3:
            row["period"] = datetime(2024, 2, 5, 13, 30)   # time of day is dropped
    table("dbo.WeeklyCogs", 2500, cogs)

    def pay(row, i):
        row.update(PayDate=datetime(2024, 1 + i % 4, 1 + i % 27, 0, 0), Retrieve_Date=datetime(2024, 5, 1, 6, 0),
                   EmployeeNumber=f"E{i:05d}", EmployeeName=f"Employee {i}", Rounded_In_Out="09:00-17:00")
        if i == 11:
            row["EmployeeName"] = "X" * 150    # longer than varchar(100)
        if i == 12:
            row["PayDate"] = None              # NOT NULL in target
    table("dbo.EmployeePaySummaryV2", 900, pay)

    def prod(row, i):
        row.update(WeeklyCogsProdNum_ID=i + 1, product_num=f"P{i:04d}" if i != 40 else "P0039",
                   category=None if i % 25 == 0 else "Food")
    table("dbo.WeeklyCogsProdNum", 120, prod)

    def loc(row, i):
        row.update(LocationID=i + 1, AcquitsionDate=datetime(2020, 1, 1))
    table("dbo.NetSuiteLocation_Mapping", 25, loc)
    table("dbo.District_Directors", 23)

    def dt(row, i):
        d = date(2020, 1, 1) + timedelta(days=i)
        row.update(day_id=i + 1, Date=d, Weekday=d.strftime("%A"))
    table("dbo.date_table", 400, dt)
    table("dbo.Temp_DLH", 80)

    def vena(row, i):
        row.update(TimePeriod_Date=date(2026, 1 + i % 12, 1), Region="East", Location=f"L{i}", Brand="B")
        if isinstance(row.get("TimePeriod"), date) or "TimePeriod" in row and row["TimePeriod"] is None:
            row["TimePeriod"] = date(2026, 1 + i % 12, 1)
    for name in ["dbo.Sales_2026_UnPivot_New", "dbo.Sales_2025_UnPivot_New", "dbo.GM_2026_UnPivot_New",
                 "dbo.Transactions_2026_UnPivot_v2", "dbo.DLH_2026_UnPivot_New"]:
        table(name, 60, vena)
    return data


def _match_chunk(chunk: Chunk, value) -> bool:
    if chunk.kind in ("full", "source_table"):
        return True
    if chunk.kind == "null":
        return value is None
    if value is None:
        return False
    if chunk.kind == "date":
        v = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())
        return datetime.fromisoformat(chunk.lo) <= v < datetime.fromisoformat(chunk.hi)
    return int(chunk.lo) <= int(value) < int(chunk.hi)


class FakeSource:
    def __init__(self, data: dict):
        self.data = {k.lower(): v for k, v in data.items()}
        self.names = {k.lower(): k for k in data}

    def _t(self, table):
        return self.data[table.lower()]

    def columns(self, table):
        t = self.data.get(table.lower())
        return list(t["columns"]) if t else []

    def find_tables(self, like):
        rx = re.compile("^" + re.escape(like).replace("%", ".*").replace("_", ".") + "$", re.I)
        return [self.names[k] for k in self.data if rx.match(k)]

    def row_count(self, table):
        return len(self._t(table)["rows"])

    def has_index_on(self, table, column):
        return True

    def _idx(self, table, column):
        return [c.name for c in self._t(table)["columns"]].index(column)

    def bounds(self, table, column):
        i = self._idx(table, column)
        vals = [r[i] for r in self._t(table)["rows"]]
        present = [v for v in vals if v is not None]
        return (min(present) if present else None, max(present) if present else None, len(vals) - len(present))

    def read(self, table, columns, chunk, chunk_column, batch_size):
        fail = os.environ.get("FAKE_FAIL_FILE")
        if fail and Path(fail).exists() and Path(fail).read_text().strip() == f"{chunk.table_key}:{chunk.chunk_key}":
            Path(fail).unlink()
            raise ConnectionError("simulated network failure while reading the source")
        t = self._t(table)
        names = [c.name for c in t["columns"]]
        idx = [names.index(c) for c in columns]
        ci = names.index(chunk_column) if chunk_column and chunk.kind not in ("full", "source_table") else None
        batch = []
        for r in t["rows"]:
            if ci is not None and not _match_chunk(chunk, r[ci]):
                continue
            batch.append(tuple(r[i] for i in idx))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def aggregate(self, table, chunk, chunk_column, checksum_column):
        t = self._t(table)
        names = [c.name for c in t["columns"]]
        ci = names.index(chunk_column) if chunk_column and chunk.kind not in ("full", "source_table") else None
        si = names.index(checksum_column) if checksum_column else None
        n, total = 0, Decimal(0)
        for r in t["rows"]:
            if ci is not None and not _match_chunk(chunk, r[ci]):
                continue
            n += 1
            if si is not None and r[si] is not None:
                total += Decimal(repr(r[si])) if isinstance(r[si], float) else Decimal(r[si])
        return n, (total if si is not None else None)

    def profile(self, table, checks, sample_pct=None):
        t = self._t(table)
        names = [c.name for c in t["columns"]]
        rows = t["rows"]
        out = {"rows": len(rows)}
        for i, c in enumerate(checks):
            k = c["check"]
            if k == "duplicates":
                idx = [names.index(x) for x in c["columns"]]
                seen, dup = {}, 0
                for r in rows:
                    key = tuple(r[j] for j in idx)
                    seen[key] = seen.get(key, 0) + 1
                out[i] = {"count": sum(1 for v in seen.values() if v > 1)}
                continue
            vals = [r[names.index(c["column"])] for r in rows]
            if k == "nulls":
                out[i] = {"count": sum(v is None for v in vals)}
            elif k == "too_long":
                lens = [len(v) for v in vals if v is not None]
                out[i] = {"count": sum(x > c["limit"] for x in lens), "max": max(lens) if lens else None}
            elif k == "bad_uuid":
                bad = 0
                for v in vals:
                    if v is None or not str(v).strip():
                        continue
                    try:
                        uuid.UUID(str(v).strip("{}"))
                    except ValueError:
                        bad += 1
                out[i] = {"count": bad}
            elif k == "numeric_overflow":
                nums = [abs(float(v)) for v in vals if v is not None]
                out[i] = {"count": sum(x >= c["limit"] for x in nums), "max": max(nums) if nums else None}
            elif k == "time_part":
                out[i] = {"count": sum(1 for v in vals if v is not None and v.time() != datetime.min.time())}
            elif k == "distinct":
                counts: dict = {}
                for v in vals:
                    counts[v] = counts.get(v, 0) + 1
                top = sorted(counts.items(), key=lambda kv: -kv[1])[:50]
                out[i] = {"values": [[None if v is None else str(v), n] for v, n in top], "distinct": len(counts)}
        return out

    def close(self):
        pass


def save(data: dict, path: str):
    with open(path, "wb") as f:
        pickle.dump(data, f)


def factory(settings):
    path = os.environ.get("FAKE_SOURCE_PATH")
    if path and Path(path).exists():
        with open(path, "rb") as f:
            return FakeSource(pickle.load(f))
    return FakeSource(build_dataset())
