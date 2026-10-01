"""Commands: check, plan, run, verify, profile, status, reset."""

from __future__ import annotations

import importlib
import multiprocessing as mp
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from psycopg import sql

from . import target as tgt
from .chunks import plan_chunks
from .config import Settings, TableSpec, load
from .control import Control, Scope
from .loader import Loader, Planner, chunk_from_row, chunk_target, dry_run_chunk, target_predicate
from .mapping import MappingError, profile_checks, snake

DEFAULT_SOURCE_FACTORY = "onroute_migration.sqlserver:from_settings"


def log(msg: str, prefix: str = "main"):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{prefix}] {msg}", flush=True)


def load_factory(path: str):
    module, _, fn = path.partition(":")
    return getattr(importlib.import_module(module), fn)


@dataclass
class Context:
    config_path: str
    tables_path: str | None = None
    source_factory: str = field(default_factory=lambda: os.environ.get("ONROUTE_SOURCE_FACTORY", DEFAULT_SOURCE_FACTORY))
    _settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = load(self.config_path, self.tables_path)
        return self._settings

    def source(self):
        return load_factory(self.source_factory)(self.settings)

    def control(self) -> Control:
        return Control(tgt.connect(self.settings.target, autocommit=True, application_name="onroute-migration-control"),
                       self.settings.control_schema)


# ------------------------------------------------------------------ preflight

@dataclass
class TablePrep:
    spec: TableSpec
    source_tables: list[str]
    chunks: list
    plans: dict            # source_table -> TablePlan
    source_rows: int | None
    warnings: list[str]


def prepare(settings: Settings, source, conn, specs: list[TableSpec], with_chunks: bool = True) -> tuple[list[TablePrep], list[str]]:
    """Validate mappings for every source table and (optionally) work out chunks."""
    preps, problems = [], []
    planner = Planner(settings, source, conn)
    for spec in specs:
        warnings: list[str] = []
        try:
            if not tgt.columns(conn, spec.target):
                problems.append(f"{spec.key}: target table {spec.target} does not exist")
                continue
            chunks = plan_chunks(spec, source) if with_chunks or spec.strategy == "per_source_table" else []
            if spec.strategy == "per_source_table":
                src_tables = [c.source_table for c in chunks]
                contexts = {c.source_table: c.context_dict for c in chunks}
                if not src_tables:
                    warnings.append(f"no source table matches {spec.source_like}")
            else:
                src_tables, contexts = [spec.source], {spec.source: {}}
            plans = {}
            for st in src_tables:
                try:
                    plans[st] = planner.plan(spec, st, contexts[st])
                except MappingError as e:
                    problems += [f"{spec.key} ({st}): {p}" for p in e.problems]
                except ValueError as e:
                    problems.append(f"{spec.key} ({st}): {e}")
            if spec.strategy in ("date_range", "int_range"):
                if not source.has_index_on(spec.source, spec.chunk_column):
                    warnings.append(f"source has no index leading on {spec.chunk_column}: every chunk scans all of {spec.source}. "
                                    f"Create one before loading (CREATE INDEX ... ON {spec.source} ({spec.chunk_column})).")
                if plans:
                    step = chunk_target(next(iter(plans.values())))
                    if not tgt.has_leading_index(conn, spec.target, step.target.name):
                        warnings.append(f"target has no index on {step.target.name}: reloading or validating a chunk scans all of "
                                        f"{spec.target}. Create one: CREATE INDEX ON {spec.target} ({step.target.name});")
            rows = None
            try:
                rows = sum(source.row_count(st) for st in src_tables)
            except Exception as e:  # row counts are informational
                warnings.append(f"could not read source row count: {e}")
            preps.append(TablePrep(spec, src_tables, chunks, plans, rows, warnings))
        except Exception as e:
            problems.append(f"{spec.key}: {type(e).__name__}: {e}")
    return preps, problems


# ------------------------------------------------------------------ check / plan

def cmd_check(ctx: Context, tables: list[str] | None) -> int:
    s = ctx.settings
    source = ctx.source()
    conn = tgt.connect(s.target, autocommit=True)
    preps, problems = prepare(s, source, conn, s.select(tables), with_chunks=False)
    for p in preps:
        print(f"\n== {p.spec.key}: {', '.join(p.source_tables) or '(no source tables)'} -> {p.spec.target} [{p.spec.strategy}]")
        if p.source_rows is not None:
            print(f"   source rows: {p.source_rows:,}")
        for plan in list(p.plans.values())[:1]:
            for d in plan.describe():
                if d["conversion"] != "as is" or snake(d["source"]) != d["target"].lower():
                    print(f"   {d['source']:<32} -> {d['target']:<34} {d['conversion']}")
        for w in p.warnings:
            print(f"   WARNING: {w}")
    if problems:
        print("\nPROBLEMS (fix before loading):")
        for pr in problems:
            print(f"  - {pr}")
        return 2
    print("\nAll mappings resolved.")
    return 0


def plan_tables(control: Control, conn, run_id: int, preps: list[TablePrep]) -> dict:
    out = {}
    for p in preps:
        existing = control.chunk_count(p.spec.key)
        needs_delete = True
        if existing == 0:
            needs_delete = not tgt.is_empty(conn, p.spec.target)
            if needs_delete:
                control.event(run_id, "warning", f"target {p.spec.target} already has rows; each chunk will delete its slice before loading",
                              p.spec.key)
        new = control.upsert_chunks(p.chunks, p.spec.priority, needs_delete)
        gone = control.mark_missing(p.spec.key, [c.chunk_key for c in p.chunks]) if p.spec.strategy == "per_source_table" else 0
        first_plan = next(iter(p.plans.values()), None)
        control.save_table_state(p.spec, ", ".join(p.source_tables), p.source_rows,
                                 first_plan.describe() if first_plan else [], p.warnings)
        for w in p.warnings:
            control.event(run_id, "warning", w, p.spec.key)
        if new or gone:
            control.event(run_id, "info", f"planned {len(p.chunks)} chunks ({new} new" + (f", {gone} no longer in source" if gone else "") + ")", p.spec.key)
        out[p.spec.key] = {"chunks": len(p.chunks), "new": new}
    return out


def cmd_plan(ctx: Context, tables: list[str] | None) -> int:
    s = ctx.settings
    control = ctx.control()
    control.ensure_schema()
    run_id = control.start_run("plan", [t.key for t in s.select(tables)], {}, 0)
    conn = tgt.connect(s.target, autocommit=True)
    preps, problems = prepare(s, ctx.source(), conn, s.select(tables))
    if problems:
        for pr in problems:
            control.event(run_id, "error", pr)
            log(f"PROBLEM: {pr}")
        control.finish_run(run_id, "failed", error=f"{len(problems)} mapping problems")
        return 2
    result = plan_tables(control, conn, run_id, preps)
    for k, v in result.items():
        log(f"{k}: {v['chunks']} chunks ({v['new']} new)")
    control.finish_run(run_id, "succeeded", summary={"planned": result})
    return 0


# ------------------------------------------------------------------ run

def worker_loop(ctx: Context, run_id: int, scope: Scope, name: str, stop_after: int | None = None) -> dict:
    s = ctx.settings
    source = ctx.source()
    control = ctx.control()
    data_conn = tgt.connect(s.target, autocommit=True, application_name=f"onroute-migration-{name}")
    planner = Planner(s, source, data_conn)
    loader = Loader(s, source, control, data_conn, planner, name)
    max_attempts = int(s.run["max_attempts"])
    lease = int(s.run["lease_minutes"])
    done = failed = 0
    try:
        while stop_after is None or done + failed < stop_after:
            row = control.claim(scope, run_id, name, max_attempts, lease)
            if row is None:
                if control.has_waiting(scope, max_attempts):
                    time.sleep(5)
                    continue
                break
            label = f"{row['table_key']} {row['chunk_key']} (attempt {row['attempts']})"
            log(f"start {label}", name)
            res = loader.process(row)
            if res["status"] == "done":
                done += 1
                log(f"done  {label}: {res['rows_loaded']:,} rows" + (f", {res['rows_rejected']:,} rejected" if res['rows_rejected'] else "")
                    + f", {res['duration']:.1f}s", name)
            else:
                failed += 1
                log(f"FAIL  {label}: {res['error']}", name)
    finally:
        for c in (data_conn, control.conn):
            try:
                c.close()
            except Exception:
                pass
        close = getattr(source, "close", None)
        if close:
            close()
    return {"done": done, "failed": failed}


def _worker_entry(config_path, tables_path, factory, run_id, scope_dict, name):
    ctx = Context(config_path, tables_path, factory)
    try:
        worker_loop(ctx, run_id, Scope.from_dict(scope_dict), name)
    except KeyboardInterrupt:
        pass
    except Exception:
        log("worker crashed:\n" + traceback.format_exc(), name)
        sys.exit(1)


def requeue_for_refresh(control: Control, scope: Scope, reopen_days: int) -> int:
    cutoff = (date.today() - timedelta(days=reopen_days)).isoformat()
    return control.requeue(scope, where=(
        "c.kind IN ('full', 'source_table', 'null') "
        "OR (c.kind = 'date' AND c.hi > %(cutoff)s) "
        "OR (c.kind = 'int' AND c.chunk_key = (SELECT max(m.chunk_key) FROM {s}.chunk m WHERE m.table_key = c.table_key AND m.kind = 'int'))"),
        reason=f"refresh: reloading chunks that can still change (last {reopen_days} days)", params={"cutoff": cutoff})


def cmd_run(ctx: Context, tables: list[str] | None, *, date_from: date | None = None, date_to: date | None = None,
            chunk_keys: list[str] | None = None, force: bool = False, refresh: bool = False, reopen_days: int = 7,
            workers: int | None = None, retry_failed: bool = True, dry_run: bool = False, sample: int | None = None,
            skip_table_counts: bool = False) -> int:
    s = ctx.settings
    specs = s.select(tables)
    workers = int(workers or s.run["workers"])
    control = ctx.control()
    control.ensure_schema()
    abandoned = control.abandon_dead_runs(int(s.run["lease_minutes"]))
    options = {"date_from": date_from and date_from.isoformat(), "date_to": date_to and date_to.isoformat(),
               "chunk_keys": chunk_keys, "force": force, "refresh": refresh, "reopen_days": reopen_days,
               "retry_failed": retry_failed, "dry_run": dry_run, "sample": sample}
    run_id = control.start_run("dry-run" if dry_run else "run", [t.key for t in specs], options, 0 if dry_run else workers)
    log(f"run {run_id} started for {len(specs)} tables with {workers} workers" + (" (DRY RUN: every chunk is rolled back)" if dry_run else ""))
    if abandoned:
        control.event(run_id, "warning", f"marked {abandoned} earlier run(s) as abandoned (no heartbeat)")
    procs: list = []
    try:
        conn = tgt.connect(s.target, autocommit=True)
        source = ctx.source()
        preps, problems = prepare(s, source, conn, specs)
        if problems:
            for pr in problems:
                control.event(run_id, "error", pr)
                log(f"PROBLEM: {pr}")
            control.finish_run(run_id, "failed", error=f"{len(problems)} mapping problems; run `check` for details")
            return 2
        plan_tables(control, conn, run_id, preps)

        scope = Scope([t.key for t in specs], date_from, date_to, chunk_keys)
        if force:
            n = control.requeue(scope, reason="forced reload")
            control.event(run_id, "info", f"--force: {n} chunks queued for reload")
        elif refresh:
            n = requeue_for_refresh(control, scope, reopen_days)
            control.event(run_id, "info", f"--refresh: {n} chunks queued for reload")
        if retry_failed:
            n = control.reset_failed_attempts(scope)
            if n:
                control.event(run_id, "info", f"retrying {n} failed chunks")

        if dry_run:
            return _dry_run(ctx, control, run_id, scope, sample)

        before = control.scope_counts(scope)
        control.event(run_id, "info", "chunks before run: " + ", ".join(f"{k} {v}" for k, v in sorted(before.items())))
        if workers <= 1:
            worker_loop(ctx, run_id, scope, "w1")
        else:
            mpctx = mp.get_context("spawn")
            for i in range(workers):
                p = mpctx.Process(target=_worker_entry, args=(ctx.config_path, ctx.tables_path, ctx.source_factory,
                                                              run_id, scope.as_dict(), f"w{i + 1}"), daemon=False)
                p.start()
                procs.append(p)
            last = 0.0
            while any(p.is_alive() for p in procs):
                time.sleep(2)
                if time.monotonic() - last > 30:
                    control.heartbeat_run(run_id)
                    counts = control.scope_counts(scope)
                    log("progress: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
                    last = time.monotonic()
            crashed = [p for p in procs if p.exitcode not in (0, None)]
            if crashed:
                control.event(run_id, "error", f"{len(crashed)} worker process(es) exited with an error")
                control.release_running(run_id)

        post_load(ctx, control, conn, run_id, specs, skip_table_counts)
        counts = control.scope_counts(scope)
        failed = counts.get("failed", 0)
        status = "succeeded" if not failed and not counts.get("running") else "completed_with_errors"
        summary = {"chunks": counts, **_run_totals(control, run_id)}
        control.finish_run(run_id, status, summary=summary,
                           error=f"{failed} chunks failed; see the dashboard or `status`" if failed else None)
        log(f"run {run_id} {status}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        return 0 if status == "succeeded" else 1
    except KeyboardInterrupt:
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(10)
        n = control.release_running(run_id)
        control.event(run_id, "warning", f"interrupted; {n} in-flight chunks rolled back and returned to the queue")
        control.finish_run(run_id, "interrupted", summary=_run_totals(control, run_id))
        log("interrupted; rerun the same command to resume")
        return 130
    except Exception as e:
        for p in procs:
            if p.is_alive():
                p.terminate()
        control.release_running(run_id)
        control.event(run_id, "error", f"run failed: {type(e).__name__}: {e}")
        control.finish_run(run_id, "failed", error=f"{type(e).__name__}: {e}")
        log(traceback.format_exc())
        return 1


def _run_totals(control: Control, run_id: int) -> dict:
    r = control.x("""SELECT count(*) FILTER (WHERE status = 'done'), count(*) FILTER (WHERE status = 'failed'),
                            COALESCE(sum(rows_loaded), 0), COALESCE(sum(rows_rejected), 0)
                     FROM {s}.chunk_attempt WHERE run_id = %s""", (run_id,)).fetchone()
    return {"chunks_loaded": r[0], "chunk_failures": r[1], "rows_loaded": int(r[2]), "rows_rejected": int(r[3])}


def _dry_run(ctx: Context, control: Control, run_id: int, scope: Scope, sample: int | None) -> int:
    s = ctx.settings
    s_sql, s_params = scope.sql()
    rows = control.rows(f"""SELECT c.* FROM {{s}}.chunk c WHERE {s_sql} AND c.status IN ('pending', 'failed', 'stale')
                            ORDER BY c.priority, c.table_key, c.chunk_key""", s_params)
    if sample:
        picked, per_table = [], {}
        for r in rows:
            if per_table.get(r["table_key"], 0) < sample:
                picked.append(r)
                per_table[r["table_key"]] = per_table.get(r["table_key"], 0) + 1
        rows = picked
    source = ctx.source()
    conn = tgt.connect(s.target, autocommit=True)
    loader = Loader(s, source, control, conn, Planner(s, source, conn), "dry-run", dry_run=True)
    bad = 0
    results = {}
    for r in rows:
        res = dry_run_chunk(loader, {**r, "run_id": run_id})
        results[f"{r['table_key']}/{r['chunk_key']}"] = res
        line = f"{r['table_key']} {r['chunk_key']}: {res['status']}"
        if res["status"] == "dry_run":
            line += f", {res['rows_loaded']:,} would load, {res['rows_rejected']:,} rejected"
            if res.get("reject_reasons"):
                line += " (" + ", ".join(f"{k} {v}" for k, v in res["reject_reasons"].items()) + ")"
            level = "warning" if res["rows_rejected"] else "info"
        else:
            bad += 1
            line += f" - {res.get('error')}"
            level = "error"
        control.event(run_id, level, "dry run: " + line, r["table_key"], r["chunk_key"])
        log(line, "dry-run")
    control.finish_run(run_id, "succeeded" if not bad else "completed_with_errors",
                       summary={"dry_run_chunks": len(rows), "would_fail": bad})
    return 0 if not bad else 1


def post_load(ctx: Context, control: Control, conn, run_id: int, specs: list[TableSpec], skip_counts: bool):
    for spec in specs:
        counts = control.scope_counts(Scope([spec.key]))
        complete = not any(counts.get(k) for k in ("pending", "running", "failed", "stale"))
        if spec.reset_sequence and counts.get("done"):
            try:
                seq = _sequence_for(conn, spec.target, spec.reset_sequence)
                if seq:
                    conn.execute(sql.SQL("SELECT setval({}, GREATEST(COALESCE((SELECT max({}) FROM {}), 0), 1))").format(
                        sql.Literal(seq), sql.Identifier(spec.reset_sequence), tgt.table_ident(spec.target)))
                    control.event(run_id, "info", f"sequence {seq} moved past the highest {spec.reset_sequence}", spec.key)
            except Exception as e:
                control.event(run_id, "error", f"could not reset sequence: {e}", spec.key)
        if not complete or skip_counts:
            continue
        loaded = control.x("SELECT COALESCE(sum(rows_loaded), 0), COALESCE(sum(rows_read), 0) FROM {s}.chunk WHERE table_key = %s AND status = 'done'",
                           (spec.key,)).fetchone()
        actual = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(tgt.table_ident(spec.target))).fetchone()[0]
        control.save_target_rows(spec.key, actual)
        ok = actual == loaded[0]
        control.validation(run_id, spec.key, "target_rows_equal_loaded", loaded[0], actual, ok,
                           "" if ok else "target table has rows the migration did not load, or is missing rows")
        state = control.x("SELECT source_rows FROM {s}.table_state WHERE table_key = %s", (spec.key,)).fetchone()
        if state and state[0] is not None:
            same = int(state[0]) == int(loaded[1])
            control.validation(run_id, spec.key, "source_rows_equal_read", state[0], loaded[1], same,
                               "" if same else "source row count changed since those chunks were read; run verify or --refresh")
        control.event(run_id, "info" if ok else "error", f"table complete: {actual:,} rows in target", spec.key)


def _sequence_for(conn, qualified: str, column: str) -> str | None:
    row = conn.execute("SELECT pg_get_serial_sequence(%s, %s)", (qualified, column)).fetchone()
    if row and row[0]:
        return row[0]
    schema, name = qualified.split(".", 1)
    row = conn.execute("SELECT column_default FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s",
                       (schema, name, column)).fetchone()
    if row and row[0]:
        m = re.search(r"nextval\('([^']+)'", row[0])
        if m:
            seq = m.group(1)
            return seq if "." in seq else f"{schema}.{seq}"
    return None


# ------------------------------------------------------------------ verify

def cmd_verify(ctx: Context, tables: list[str] | None, *, date_from=None, date_to=None, chunk_keys=None, limit: int | None = None) -> int:
    s = ctx.settings
    specs = s.select(tables)
    control = ctx.control()
    control.ensure_schema()
    run_id = control.start_run("verify", [t.key for t in specs], {"limit": limit}, 1)
    source = ctx.source()
    conn = tgt.connect(s.target, autocommit=True)
    planner = Planner(s, source, conn)
    scope = Scope([t.key for t in specs], date_from, date_to, chunk_keys)
    rows = control.done_chunks(scope)
    if limit:
        rows = rows[-limit:]
    ok = bad = 0
    try:
        for r in rows:
            spec = s.table(r["table_key"])
            chunk = chunk_from_row(r)
            plan = planner.plan(spec, chunk.source_table or spec.source, chunk.context_dict)
            src_count, src_sum = source.aggregate(plan.source_table, chunk, spec.chunk_column, spec.checksum_column)
            where, params = target_predicate(plan, chunk)
            agg = sql.SQL("sum({})").format(sql.Identifier(plan.target_columns[plan.checksum_index])) if plan.checksum_index is not None else sql.SQL("NULL")
            t_count, t_sum = conn.execute(sql.SQL("SELECT count(*), {} FROM {} WHERE ").format(agg, tgt.table_ident(spec.target)) + where, params).fetchone()
            expected = src_count - int(r["rows_rejected"] or 0)
            problems = []
            if t_count != expected:
                problems.append(f"rows: source {src_count:,} - rejected {r['rows_rejected'] or 0:,} = {expected:,}, target {t_count:,}")
            if plan.checksum_index is not None and src_sum is not None:
                exp_sum = src_sum - Decimal(r["rejected_checksum"] or 0)
                tol = Decimal(0) if not plan.steps[plan.checksum_index].note else Decimal("0.0001") * max(t_count, 1)
                if t_sum is None or abs(Decimal(str(t_sum)) - exp_sum) > tol:
                    problems.append(f"{spec.checksum_column} total: source {exp_sum}, target {t_sum}")
            if problems:
                bad += 1
                msg = "; ".join(problems)
                control.x("UPDATE {s}.chunk SET status = 'stale', attempts = 0, verified_at = now(), verify_result = %s WHERE chunk_id = %s AND status = 'done'",
                          (msg, r["chunk_id"]))
                control.event(run_id, "warning", f"verify mismatch, queued for reload: {msg}", spec.key, chunk.chunk_key)
                log(f"MISMATCH {spec.key} {chunk.chunk_key}: {msg}")
            else:
                ok += 1
                control.x("UPDATE {s}.chunk SET verified_at = now(), verify_result = 'ok' WHERE chunk_id = %s", (r["chunk_id"],))
            src_text = f"{src_count:,}" + (f" - {int(r['rows_rejected']):,} rejected" if r["rows_rejected"] else "")
            control.validation(run_id, spec.key, "chunk_matches_source", src_text, f"{t_count:,}", not problems, "; ".join(problems), chunk.chunk_key)
            control.heartbeat_run(run_id)
        control.finish_run(run_id, "succeeded" if not bad else "completed_with_errors", summary={"verified": ok, "mismatched": bad})
        log(f"verify: {ok} chunks match, {bad} mismatched (marked stale; the next run reloads them)")
        return 0 if not bad else 1
    except KeyboardInterrupt:
        control.finish_run(run_id, "interrupted", summary={"verified": ok, "mismatched": bad})
        return 130
    except Exception as e:
        control.finish_run(run_id, "failed", error=f"{type(e).__name__}: {e}")
        raise


# ------------------------------------------------------------------ profile

def _flag(check: dict, res: dict, spec: TableSpec) -> bool:
    if check["check"] == "distinct":
        allowed = check.get("allowed") or []
        norm = {str(a).strip().upper() for a in allowed}
        flag_column = set(allowed) == set(spec.true_values) | set(spec.false_values)
        unmapped = []
        for v, n in res.get("values", []):
            if v is None:
                continue
            if flag_column:
                key = v.strip().upper()
                if key in norm or (key == "" and spec.empty_flag_is_null):
                    continue
            elif v in allowed or v.strip() in allowed or v.strip() == "":
                continue
            unmapped.append([v, n])
        res["unmapped"] = unmapped
        return bool(unmapped)
    return bool(res.get("count"))


def cmd_profile(ctx: Context, tables: list[str] | None, sample_pct: float | None = None) -> int:
    s = ctx.settings
    specs = s.select(tables)
    control = ctx.control()
    control.ensure_schema()
    run_id = control.start_run("profile", [t.key for t in specs], {"sample_pct": sample_pct}, 1)
    source = ctx.source()
    conn = tgt.connect(s.target, autocommit=True)
    preps, problems = prepare(s, source, conn, specs, with_chunks=False)
    flagged = 0
    for p in preps:
        for st, plan in p.plans.items():
            checks = profile_checks(plan)
            if not checks:
                continue
            log(f"profiling {p.spec.key} ({st}): {len(checks)} checks" + (f" on a {sample_pct}% sample" if sample_pct else ""))
            res = source.profile(st, checks, sample_pct)
            for i, c in enumerate(checks):
                r = {**res.get(i, {}), "rows": res.get("rows")}
                f = _flag(c, r, p.spec)
                flagged += f
                control.profile_result(run_id, p.spec.key, st, c, r, f)
                if f:
                    detail = r.get("unmapped") or r.get("count")
                    log(f"  FLAG {c['check']} {c.get('column') or c.get('columns')} -> {c.get('target')}: {detail}")
            control.heartbeat_run(run_id)
    for pr in problems:
        control.event(run_id, "error", pr)
    control.finish_run(run_id, "succeeded" if not problems else "completed_with_errors",
                       summary={"flagged_checks": flagged, "problems": len(problems)})
    log(f"profile finished: {flagged} checks flagged")
    return 0 if not problems else 2


# ------------------------------------------------------------------ status / reset

def cmd_status(ctx: Context, tables: list[str] | None) -> int:
    s = ctx.settings
    control = ctx.control()
    control.ensure_schema()
    keys = [t.key for t in s.select(tables)]
    rows = control.rows("""
        SELECT c.table_key, count(*) AS chunks,
               count(*) FILTER (WHERE c.status = 'done') AS done,
               count(*) FILTER (WHERE c.status = 'running') AS running,
               count(*) FILTER (WHERE c.status = 'failed') AS failed,
               count(*) FILTER (WHERE c.status IN ('pending', 'stale')) AS waiting,
               COALESCE(sum(c.rows_loaded) FILTER (WHERE c.status = 'done'), 0) AS rows_loaded,
               COALESCE(sum(c.rows_rejected) FILTER (WHERE c.status = 'done'), 0) AS rows_rejected,
               max(ts.source_rows) AS source_rows
        FROM {s}.chunk c LEFT JOIN {s}.table_state ts USING (table_key)
        WHERE c.table_key = ANY(%s) AND c.status <> 'skipped'
        GROUP BY c.table_key ORDER BY min(c.priority)""", (keys,))
    print(f"{'table':<28}{'chunks':>8}{'done':>7}{'run':>5}{'fail':>6}{'wait':>6}{'rows loaded':>16}{'source rows':>16}{'rejected':>10}")
    for r in rows:
        print(f"{r['table_key']:<28}{r['chunks']:>8}{r['done']:>7}{r['running']:>5}{r['failed']:>6}{r['waiting']:>6}"
              f"{r['rows_loaded']:>16,}{(r['source_rows'] or 0):>16,}{r['rows_rejected']:>10,}")
    fails = control.rows("""SELECT table_key, chunk_key, attempts, error FROM {s}.chunk
                            WHERE table_key = ANY(%s) AND status = 'failed' ORDER BY priority, chunk_key LIMIT 20""", (keys,))
    if fails:
        print("\nFailed chunks:")
        for f in fails:
            print(f"  {f['table_key']} {f['chunk_key']} (attempts {f['attempts']}): {f['error']}")
    return 0


def cmd_reset(ctx: Context, tables: list[str], truncate_target: bool, yes: bool) -> int:
    if not tables:
        print("reset needs --tables (it never resets everything implicitly)")
        return 2
    s = ctx.settings
    specs = s.select(tables)
    if not yes:
        print("This forgets all checkpoints for: " + ", ".join(t.key for t in specs)
              + (" and TRUNCATES their target tables" if truncate_target else "") + ". Re-run with --yes to confirm.")
        return 2
    control = ctx.control()
    control.ensure_schema()
    run_id = control.start_run("reset", [t.key for t in specs], {"truncate_target": truncate_target}, 0)
    conn = tgt.connect(s.target, autocommit=True)
    for spec in specs:
        busy = control.x("SELECT count(*) FROM {s}.chunk WHERE table_key = %s AND status = 'running' AND heartbeat_at > now() - %s::interval",
                         (spec.key, f"{s.run['lease_minutes']} minutes")).fetchone()[0]
        if busy:
            control.finish_run(run_id, "failed", error=f"{spec.key} has {busy} chunks loading right now")
            print(f"{spec.key} has {busy} chunks loading right now; stop that run first")
            return 2
        if truncate_target:
            conn.execute(sql.SQL("TRUNCATE {}").format(tgt.table_ident(spec.target)))
        control.x("DELETE FROM {s}.chunk WHERE table_key = %s", (spec.key,))
        control.x("DELETE FROM {s}.table_state WHERE table_key = %s", (spec.key,))
        control.event(run_id, "warning", "checkpoints cleared" + (" and target truncated" if truncate_target else ""), spec.key)
        log(f"reset {spec.key}")
    control.finish_run(run_id, "succeeded")
    return 0
