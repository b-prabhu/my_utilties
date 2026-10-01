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


# ---------------------------------------------------------------- start / stop / resume / rerun controls

def test_graceful_stop_then_resume(pg_env, monkeypatch):
    c = ctx(pg_env)
    import onroute_migration.runner as R
    real = R.Loader.process
    calls = {"n": 0}

    def process_then_stop(self, row):
        res = real(self, row)
        calls["n"] += 1
        if calls["n"] == 2:   # someone presses "Stop after current chunks"
            self.control.request_stop(row["run_id"], "graceful", "test")
        return res
    monkeypatch.setattr(R.Loader, "process", process_then_stop)
    assert runner.cmd_run(c, ["pos_orders"]) == 4
    assert q(pg_env, "SELECT status FROM migration_test.run ORDER BY run_id DESC LIMIT 1")[0][0] == "stopped"
    states = list(chunk_states(pg_env, "pos_orders").values())
    assert states.count("done") == 2 and states.count("pending") == 3
    monkeypatch.setattr(R.Loader, "process", real)
    assert runner.cmd_run(c, ["pos_orders"]) == 0          # resume
    assert set(chunk_states(pg_env, "pos_orders").values()) == {"done"}
    assert count(pg_env, "pos_orders") == 2396


def test_stop_now_rolls_back_the_chunk_in_flight(pg_env, monkeypatch):
    import onroute_migration.loader as L
    monkeypatch.setattr(L, "HEARTBEAT_SECONDS", 0)
    c = ctx(pg_env)
    for spec in c.settings.tables:
        spec.batch_size = 100
    real = L.Control.heartbeat_chunk

    def beat(self, chunk_id, token, rows_read, run_id=None):
        mode = real(self, chunk_id, token, rows_read, run_id)
        if rows_read >= 300 and not mode:
            self.request_stop(run_id, "now", "test")
            return "now"
        return mode
    monkeypatch.setattr(L.Control, "heartbeat_chunk", beat)
    assert runner.cmd_run(c, ["pos_orders"]) == 4
    assert count(pg_env, "pos_orders") == 0                    # first chunk rolled back
    assert set(chunk_states(pg_env, "pos_orders").values()) == {"pending"}
    assert q(pg_env, "SELECT count(*) FROM migration_test.chunk_attempt")[0][0] == 0   # not counted as a failure
    monkeypatch.setattr(L.Control, "heartbeat_chunk", real)
    assert runner.cmd_run(c, ["pos_orders"]) == 0
    assert count(pg_env, "pos_orders") == 2396


def test_only_one_writer_at_a_time(pg_env):
    c = ctx(pg_env)
    holder = c.control()
    holder.ensure_schema()
    assert holder.acquire_writer_lock()
    assert runner.cmd_run(c, ["date_table"]) == 3
    assert runner.cmd_verify(c, ["date_table"]) == 3
    assert runner.cmd_run(c, ["date_table"], dry_run=True) == 0     # dry runs never write, so they may run alongside
    holder.conn.close()
    assert runner.cmd_run(c, ["date_table"]) == 0


def test_only_failed_retries_just_the_failed_chunks(pg_env):
    c = ctx(pg_env)
    runner.cmd_run(c, ["pos_orders"])
    q(pg_env, "UPDATE migration_test.chunk SET status = 'failed', attempts = 3 WHERE table_key = 'pos_orders' AND chunk_key = 'm:2024-02'")
    q(pg_env, "UPDATE migration_test.chunk SET status = 'pending' WHERE table_key = 'pos_orders' AND chunk_key = 'm:2024-03'")
    assert runner.cmd_run(c, ["pos_orders"], only_failed=True) == 0
    states = chunk_states(pg_env, "pos_orders")
    assert states["m:2024-02"] == "done" and states["m:2024-03"] == "pending"


def test_stop_command_with_nothing_running(pg_env):
    assert runner.cmd_stop(ctx(pg_env), None, now=False) == 1


def _serve(pg_env, tmp_path):
    import threading
    from http.server import ThreadingHTTPServer
    from onroute_migration.dashboard import server as S
    c = ctx(pg_env)
    c.settings.dashboard["log_dir"] = str(tmp_path / "logs")
    api = S.Api(pg_env["dsn"], "migration_test")
    S.Handler.api = api
    S.Handler.controls = S.Controls(c, api, True, "", None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, S.Handler.controls


def _post(port, path, body, headers=None):
    import json as _j
    import urllib.request
    import urllib.error
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=_j.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers if headers is not None else {"X-Requested-By": "onroute-dashboard"})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, _j.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _j.loads(e.read())


def test_dashboard_starts_and_resumes_runs(pg_env, tmp_path):
    import time as _t
    httpd, controls = _serve(pg_env, tmp_path)
    port = httpd.server_address[1]
    try:
        assert _post(port, "/api/actions", {"action": "run"}, headers={})[0] == 403          # no CSRF header
        assert _post(port, "/api/actions", {"action": "run", "tables": ["bogus"]})[0] == 400
        code, res = _post(port, "/api/actions", {"action": "run", "tables": ["date_table", "district_directors"]})
        assert code == 200 and res["job"]["display"].endswith("run -t date_table,district_directors")
        job_id = res["job"]["job_id"]
        deadline = _t.time() + 120
        while _t.time() < deadline and controls.jobs.list()[0]["status"] == "running":
            _t.sleep(0.5)
        job = controls.jobs.list()[0]
        assert job["exit_code"] == 0, controls.jobs.log_tail(job_id)["log"]
        run = q(pg_env, "SELECT status, launched_by, tables FROM migration_test.run WHERE command = 'run' ORDER BY run_id DESC LIMIT 1")[0]
        assert run[0] == "succeeded" and run[1].startswith("dashboard")
        assert count(pg_env, "date_table") == 400
        # Resume repeats the last run's scope.
        assert set(controls.resume_action({})["tables"]) == {"date_table", "district_directors"}
        assert "run 1" in controls.jobs.log_tail(job_id)["log"] or "succeeded" in controls.jobs.log_tail(job_id)["log"]
    finally:
        httpd.shutdown()
