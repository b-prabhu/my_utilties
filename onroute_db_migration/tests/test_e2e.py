"""End-to-end rerun scenarios against a real PostgreSQL (set ONROUTE_TEST_PG_DSN).

The source is the in-memory fake in fake_source.py; the target is the real
master schema generated from the target export.
"""

from datetime import datetime

import psycopg
import pytest

import fake_source
from onroute_migration import runner
from onroute_migration.control import Control, Scope
from onroute_migration.loader import Loader, Planner


def ctx(env):
    return runner.Context(env["config"])


def q(env, sql, params=None):
    with psycopg.connect(env["dsn"], autocommit=True) as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if cur.description else []


def count(env, table):
    return q(env, f"SELECT count(*) FROM master.{table}")[0][0]


def chunk_states(env, table):
    return dict(q(env, "SELECT chunk_key, status FROM migration_test.chunk WHERE table_key = %s", (table,)))


EXPECTED = {"pos_orders": 2396, "pos_order_details": 7200, "pos_order_payments": 2400, "employee_pay_summary": 898,
            "weekly_cogs_prod_num": 119, "weekly_cogs": 2500, "vena_sales": 120, "date_table": 400}


def test_full_load_then_rerun_is_a_no_op(pg_env):
    assert runner.cmd_run(ctx(pg_env), None) == 0
    for t, n in EXPECTED.items():
        assert count(pg_env, t) == n, t
    reasons = dict(q(pg_env, "SELECT reason || ':' || column_name, count(*) FROM migration_test.rejected_row GROUP BY 1"))
    assert reasons == {"bad_flag_value:is_refund": 1, "bad_uuid:guid": 1, "not_in_enum:order_type_name": 1,
                       "null_not_allowed:store_id": 1, "too_long:employee_name": 1, "null_not_allowed:pay_date": 1,
                       "duplicate_key:product_num": 1}
    assert q(pg_env, "SELECT bool_and(passed) FROM migration_test.validation")[0][0] is True
    assert q(pg_env, "SELECT last_value FROM master.weekly_cogs_id_seq")[0][0] == 2500

    attempts_before = q(pg_env, "SELECT count(*) FROM migration_test.chunk_attempt")[0][0]
    assert runner.cmd_run(ctx(pg_env), None) == 0
    assert q(pg_env, "SELECT count(*) FROM migration_test.chunk_attempt")[0][0] == attempts_before   # nothing reloaded
    for t, n in EXPECTED.items():
        assert count(pg_env, t) == n, t


def test_force_reload_never_duplicates(pg_env):
    runner.cmd_run(ctx(pg_env), ["pos_orders", "vena_sales"])
    ids_before = q(pg_env, "SELECT count(DISTINCT id) FROM master.pos_orders")[0][0]
    assert runner.cmd_run(ctx(pg_env), ["pos_orders", "vena_sales"], force=True) == 0
    assert runner.cmd_run(ctx(pg_env), ["pos_orders"], chunk_keys=["m:2024-02"], force=True) == 0
    assert count(pg_env, "pos_orders") == ids_before == 2396
    assert count(pg_env, "vena_sales") == 120


def test_failed_chunk_is_retried_and_succeeds(pg_env):
    (pg_env["dir"] / "fail.txt").write_text("pos_orders:m:2024-03")
    assert runner.cmd_run(ctx(pg_env), ["pos_orders"]) == 0
    hist = q(pg_env, "SELECT status FROM migration_test.chunk_attempt WHERE chunk_key = 'm:2024-03' ORDER BY attempt_id")
    assert [h[0] for h in hist] == ["failed", "done"]
    assert count(pg_env, "pos_orders") == 2396


def test_chunk_that_keeps_failing_is_left_failed_and_retried_next_run(pg_env, monkeypatch):
    import onroute_migration.loader as L
    real = L.Loader._load

    def broken(self, spec, plan, chunk, row, progress, started):
        if chunk.chunk_key == "m:2024-02":
            raise RuntimeError("target disk full")
        return real(self, spec, plan, chunk, row, progress, started)
    monkeypatch.setattr(L.Loader, "_load", broken)
    assert runner.cmd_run(ctx(pg_env), ["pos_orders"]) == 1          # completed_with_errors
    assert chunk_states(pg_env, "pos_orders")["m:2024-02"] == "failed"
    assert q(pg_env, "SELECT attempts FROM migration_test.chunk WHERE chunk_key = 'm:2024-02' AND table_key = 'pos_orders'")[0][0] == 3
    monkeypatch.setattr(L.Loader, "_load", real)
    assert runner.cmd_run(ctx(pg_env), ["pos_orders"]) == 0          # next run retries it
    assert set(chunk_states(pg_env, "pos_orders").values()) == {"done"}
    assert count(pg_env, "pos_orders") == 2396


def test_dead_worker_lease_is_taken_over_and_zombie_cannot_commit(pg_env):
    c = ctx(pg_env)
    s = c.settings
    runner.cmd_plan(c, ["pos_orders"])
    control = c.control()
    run_id = control.start_run("test", ["pos_orders"], {}, 1)
    scope = Scope(["pos_orders"], chunk_keys=["m:2024-01"])
    zombie = control.claim(scope, run_id, "zombie", 3, 1)
    assert zombie is not None
    # The zombie stops heartbeating; after the lease expires another worker takes the chunk over.
    q(pg_env, "UPDATE migration_test.chunk SET heartbeat_at = now() - interval '5 minutes' WHERE chunk_id = %s", (zombie["chunk_id"],))
    assert runner.cmd_run(c, ["pos_orders"]) == 0
    assert chunk_states(pg_env, "pos_orders")["m:2024-01"] == "done"
    # The zombie wakes up and tries to finish with its old lease: its transaction is rolled back.
    conn = psycopg.connect(s.target["dsn"], autocommit=True)
    source = c.source()
    loader = Loader(s, source, control, conn, Planner(s, source, conn), "zombie")
    res = loader.process(zombie)
    assert res["status"] == "failed" and "LeaseLost" in res["error"]
    assert count(pg_env, "pos_orders") == 2396
    assert chunk_states(pg_env, "pos_orders")["m:2024-01"] == "done"


def test_interrupted_run_releases_chunks(pg_env):
    c = ctx(pg_env)
    runner.cmd_plan(c, ["pos_orders"])
    control = c.control()
    run_id = control.start_run("test", ["pos_orders"], {}, 1)
    control.claim(Scope(["pos_orders"]), run_id, "w1", 3, 20)
    assert control.release_running(run_id) == 1
    assert "running" not in chunk_states(pg_env, "pos_orders").values()
    assert runner.cmd_run(c, ["pos_orders"]) == 0
    assert count(pg_env, "pos_orders") == 2396


def test_verify_detects_late_source_rows_and_next_run_reloads_only_that_chunk(pg_env):
    c = ctx(pg_env)
    runner.cmd_run(c, ["pos_orders"])
    data = pg_env["data"]
    t = data["dbo.POS_ORDERS"]
    names = [col.name for col in t["columns"]]
    row = list(t["rows"][100])
    row[names.index("OrderID")] = 999999
    row[names.index("Endday")] = datetime(2024, 3, 15)
    t["rows"].append(tuple(row))
    fake_source.save(data, str(pg_env["dir"] / "source.pkl"))

    assert runner.cmd_verify(c, ["pos_orders"]) == 1
    states = chunk_states(pg_env, "pos_orders")
    assert states["m:2024-03"] == "stale" and states["m:2024-02"] == "done"
    before = q(pg_env, "SELECT count(*) FROM migration_test.chunk_attempt")[0][0]
    assert runner.cmd_run(c, ["pos_orders"]) == 0
    assert q(pg_env, "SELECT count(*) FROM migration_test.chunk_attempt")[0][0] == before + 1
    assert q(pg_env, "SELECT count(*) FROM master.pos_orders WHERE order_id = 999999")[0][0] == 1
    assert runner.cmd_verify(c, ["pos_orders"]) == 0


def test_refresh_reloads_full_tables_and_recent_chunks_only(pg_env):
    c = ctx(pg_env)
    runner.cmd_run(c, ["pos_orders", "date_table"])
    before = dict(q(pg_env, "SELECT chunk_key || '@' || table_key, loaded_at FROM migration_test.chunk"))
    assert runner.cmd_run(c, ["pos_orders", "date_table"], refresh=True, reopen_days=7) == 0
    after = dict(q(pg_env, "SELECT chunk_key || '@' || table_key, loaded_at FROM migration_test.chunk"))
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"all@date_table", "null@pos_orders"}   # 2024 months are older than 7 days
    assert count(pg_env, "pos_orders") == 2396


def test_date_range_scope(pg_env):
    c = ctx(pg_env)
    runner.cmd_run(c, ["pos_orders"])
    before = dict(q(pg_env, "SELECT chunk_key, loaded_at FROM migration_test.chunk WHERE table_key = 'pos_orders'"))
    from datetime import date
    assert runner.cmd_run(c, ["pos_orders"], date_from=date(2024, 2, 1), date_to=date(2024, 4, 1), force=True) == 0
    after = dict(q(pg_env, "SELECT chunk_key, loaded_at FROM migration_test.chunk WHERE table_key = 'pos_orders'"))
    assert {k for k in before if before[k] != after[k]} == {"m:2024-02", "m:2024-03"}


def test_dry_run_changes_nothing(pg_env):
    assert runner.cmd_run(ctx(pg_env), ["pos_orders", "employee_pay_summary"], dry_run=True) == 0
    assert count(pg_env, "pos_orders") == 0
    assert set(chunk_states(pg_env, "pos_orders").values()) == {"pending"}
    msgs = [m[0] for m in q(pg_env, "SELECT message FROM migration_test.event WHERE message LIKE 'dry run:%%'")]
    assert any("would load" in m for m in msgs)


def test_existing_target_rows_are_replaced_not_duplicated(pg_env):
    # Someone loaded part of the data by hand before the migration tool was used.
    q(pg_env, """INSERT INTO master.vena_sales (budget_year, "Region", "Location", "Brand", "TimePeriod_Date", "HostLocationID")
                 VALUES (2026, 'East', 'L0', 'B', '2026-01-01', 1)""")
    assert runner.cmd_run(ctx(pg_env), ["vena_sales"]) == 0
    assert count(pg_env, "vena_sales") == 120


def test_parallel_workers(pg_env):
    assert runner.cmd_run(ctx(pg_env), None, workers=3) == 0
    for t, n in EXPECTED.items():
        assert count(pg_env, t) == n, t
    workers = {w[0] for w in q(pg_env, "SELECT DISTINCT worker FROM migration_test.chunk_attempt")}
    assert len(workers) >= 2


def test_reset_requires_confirmation(pg_env):
    c = ctx(pg_env)
    runner.cmd_run(c, ["date_table"])
    assert runner.cmd_reset(c, ["date_table"], truncate_target=True, yes=False) == 2
    assert count(pg_env, "date_table") == 400
    assert runner.cmd_reset(c, ["date_table"], truncate_target=True, yes=True) == 0
    assert count(pg_env, "date_table") == 0
    assert chunk_states(pg_env, "date_table") == {}


def test_profile_predicts_rejects(pg_env):
    assert runner.cmd_profile(ctx(pg_env), ["pos_orders", "weekly_cogs_prod_num"]) == 0
    flagged = {(r[0], r[1]) for r in q(pg_env, "SELECT column_name, check_name FROM migration_test.profile WHERE flagged")}
    assert flagged == {("OrderTypeName", "distinct"), ("IsRefund", "distinct"), ("GUID", "bad_uuid"),
                       ("StoreId", "nulls"), ("product_num", "duplicates")}


def test_dashboard_api(pg_env):
    from onroute_migration.dashboard.server import Api
    runner.cmd_run(ctx(pg_env), ["pos_orders"])
    api = Api(pg_env["dsn"], "migration_test")
    ov = api.overview()
    assert ov["ready"] and ov["totals"]["rows_loaded"] == 2396
    assert api.runs()["runs"][0]["status"] == "succeeded"
    t = api.table("pos_orders")
    assert len(t["chunks"]) == 5 and len(t["reject_reasons"]) == 4
