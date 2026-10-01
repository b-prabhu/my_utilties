"""Build schema_review.html from the same mapping used for schema_comparison.xlsx.

Usage:  python build_review_page.py  ->  writes schema_review.html
"""

from __future__ import annotations

import json
from pathlib import Path

from compare_schemas import (
    ROWCOUNT_FILE, SOURCE_FILE, TARGET_FILE, TABLE_MAP, _worst_status,
    build_mapping, is_nullable, load_rows,
)

HERE = Path(__file__).parent
TEMPLATE = HERE / "review_page_template.html"
OUTPUT = HERE / "schema_review.html"

PURPOSE = {
    "POS_ORDERS": "sales, transactions, HST",
    "POS_ORDERDETAILS": "items, gift cards, donations, lottery",
    "POS_ORDERPAYMENTS": "tender",
    "POS_ORDERPAIDOUTS": "tender, financial",
    "NetSuiteLocation_Mapping": "plaza, brand, ROLLOUT (all reports)",
    "District_Directors": "District Director filter",
    "date_table": "retail calendar",
    "EmployeePaySummaryV2": "labour hours",
    "Temp_DLH": "temp labour hours",
    "WeeklyCogs": "COGS, stock, waste",
    "WeeklyCogsProdNum": "product categories",
    "Sales_2026_UnPivot_New": "sales budget",
    "GM_2026_UnPivot_New": "margin budget",
    "Transactions_2026_UnPivot_v2": "transactions budget",
    "DLH_2026_UnPivot_New": "labour budget",
}


def main():
    mapping = build_mapping(load_rows(SOURCE_FILE), load_rows(TARGET_FILE))
    counts = {str(r["table_name"]).lower(): r["row_count"] for r in load_rows(ROWCOUNT_FILE)}

    def fmt(col):
        if not col:
            return None
        lp = col.get("length_precision") or ""
        default = col.get("default_value")
        return {
            "name": col["column_name"],
            "type": col["data_type"] + (f"({lp})" if lp and col["data_type"] not in ("timestamp without time zone", "timestamp with time zone") else ""),
            "null": is_nullable(col["is_nullable"]),
            "default": None if default in (None, "", "(null)") else default,
        }

    rows = [{
        "s_table": m["src_table"], "t_table": m["tgt_table"],
        "src": fmt(m["src"]), "tgt": fmt(m["tgt"]),
        "status": m["status"], "worst": _worst_status(m["status"]),
        "detail": m["detail"], "note": m["note"],
    } for m in mapping]
    tables = [{
        "source": s, "target": t, "rows": counts.get(s.lower()), "purpose": PURPOSE.get(s, ""),
    } for s, t in TABLE_MAP.items()]

    data = json.dumps({"tables": tables, "rows": rows}, ensure_ascii=False)
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", data)
    OUTPUT.write_text(html)
    print(f"Wrote {OUTPUT} ({len(rows)} column rows)")


if __name__ == "__main__":
    main()
