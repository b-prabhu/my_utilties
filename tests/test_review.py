import json
import sqlite3

import pytest

from data_migration.cli import main
from data_migration.compare import compare, compare_columns, type_verdict
from data_migration.connections import describe, url_from_env
from data_migration.inspect_db import snapshot


def col(name, type_, generic, nullable=True, pk=False, default=None, autoincrement=False):
    return {"name": name, "type": type_, "generic": generic, "nullable": nullable,
            "pk": pk, "default": default, "autoincrement": autoincrement}


@pytest.mark.parametrize("src,tgt,expected", [
    (col("a", "INTEGER", "INTEGER"), col("a", "BIGINT", "BIGINTEGER"), "compatible"),
    (col("a", "BIGINT", "BIGINTEGER"), col("a", "INTEGER", "INTEGER"), "narrowing"),
    (col("a", "NVARCHAR(320)", "UNICODE"), col("a", "VARCHAR(255)", "STRING"), "narrowing"),
    (col("a", "NVARCHAR(max)", "UNICODE"), col("a", "TEXT", "TEXT"), "compatible"),
    (col("a", "NVARCHAR(max)", "UNICODE"), col("a", "VARCHAR(50)", "STRING"), "narrowing"),
    (col("a", "BIT", "BOOLEAN"), col("a", "BOOLEAN", "BOOLEAN"), "same"),
    (col("a", "UNIQUEIDENTIFIER", "UUID"), col("a", "UUID", "UUID"), "same"),
    (col("a", "DATETIME2", "DATETIME"), col("a", "TIMESTAMP", "DATETIME"), "same"),
    (col("a", "VARCHAR(10)", "STRING"), col("a", "INTEGER", "INTEGER"), "mismatch"),
])
def test_type_verdict(src, tgt, expected):
    assert type_verdict(src, tgt)[0] == expected


def test_compare_columns_flags_missing_extra_and_required():
    rows = {r["name"]: r for r in compare_columns(
        [col("id", "INTEGER", "INTEGER", pk=True), col("Email", "VARCHAR(50)", "STRING"), col("gone", "TEXT", "TEXT")],
        [col("id", "INTEGER", "INTEGER", pk=True), col("email", "VARCHAR(50)", "STRING", nullable=False),
         col("tenant", "INTEGER", "INTEGER", nullable=False), col("note", "TEXT", "TEXT")],
    )}
    assert rows["id"]["status"] == "ok"
    assert rows["Email"]["status"] == "warn"  # case-insensitive match, but target is NOT NULL
    assert rows["gone"]["status"] == "missing"
    assert rows["tenant"]["status"] == "error"
    assert rows["note"]["status"] == "extra"


def _snap(schema, tables, default=None):
    return {"default_schema": default or schema,
            "schemas": [{"name": schema, "views": [], "tables": [
                {"name": n, "columns": cols, "primary_key": [], "foreign_keys": [], "indexes": [], "row_count": rc}
                for n, cols, rc in tables]}]}


def test_compare_maps_dbo_to_public_and_reports_row_diff():
    c = [col("id", "INTEGER", "INTEGER")]
    result = compare(
        _snap("dbo", [("Customers", c, 10), ("Legacy", c, 1)]),
        _snap("public", [("customers", c, 7), ("etl_log", c, 0)]),
        {"dbo": "public"},
    )
    by_status = {p["status"]: p for p in result["pairs"]}
    assert by_status["matched"]["target_table"] == "customers"
    assert by_status["matched"]["row_diff"] == -3
    assert by_status["source_only"]["source_table"] == "Legacy"
    assert by_status["target_only"]["target_table"] == "etl_log"


def test_url_from_env(monkeypatch):
    monkeypatch.delenv("src_url", raising=False)
    monkeypatch.delenv("src_port", raising=False)
    monkeypatch.setenv("src_dbtype", "postgres")
    monkeypatch.setenv("src_host", "db.example.com")
    monkeypatch.setenv("src_dbname", "app")
    monkeypatch.setenv("src_username", "u")
    monkeypatch.setenv("src_password", "s3cret")
    url = url_from_env("src")
    assert url.drivername == "postgresql+psycopg2"
    assert url.port == 5432 and url.query["sslmode"] == "require"
    assert "s3cret" not in describe(url)


def test_review_end_to_end(tmp_path, monkeypatch):
    src, tgt = tmp_path / "s.db", tmp_path / "t.db"
    with sqlite3.connect(src) as conn:
        conn.executescript("CREATE TABLE a (id INTEGER PRIMARY KEY, name VARCHAR(20)); INSERT INTO a VALUES (1,'x'),(2,'y');")
    with sqlite3.connect(tgt) as conn:
        conn.executescript("CREATE TABLE a (id INTEGER PRIMARY KEY, name VARCHAR(10)); INSERT INTO a VALUES (1,'x');")
    monkeypatch.setenv("src_url", f"sqlite:///{src}")
    monkeypatch.setenv("tgt_url", f"sqlite:///{tgt}")
    out = tmp_path / "r.html"
    assert main(["review", "--out", str(out), "--snapshot-dir", str(tmp_path)]) == 0
    html = out.read_text()
    assert "__REPORT_DATA__" not in html and "Migration schema review" in html
    snap = json.loads((tmp_path / "src_snapshot.json").read_text())
    assert snap["schemas"][0]["tables"][0]["row_count"] == 2


def test_snapshot_reports_connection_error():
    snap = snapshot("sqlite:////nonexistent/dir/x.db", label="Source")
    assert snap["error"] and snap["schemas"] == []
