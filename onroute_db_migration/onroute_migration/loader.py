"""Load one chunk: delete the target slice, COPY the source rows, validate, and
mark the chunk done, all in one PostgreSQL transaction.

Because the checkpoint commits with the data, a chunk is either fully loaded and
marked done, or not loaded at all. Re-running a chunk replaces its slice, so a
rerun never duplicates rows (the uuid surrogate keys on the target are
regenerated, the business data is identical).
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from . import target as tgt
from .chunks import Chunk
from .config import Settings, TableSpec
from .control import Control
from .mapping import TEXT_TGT, Reject, TablePlan, build_plan


class ChunkFailed(Exception):
    pass


class LeaseLost(ChunkFailed):
    pass


def chunk_from_row(row: dict) -> Chunk:
    ctx = row.get("context") or {}
    return Chunk(row["table_key"], row["chunk_key"], row["kind"], row["lo"], row["hi"], row["source_table"],
                 tuple(sorted(ctx.items())))


class Planner:
    """Builds and caches TablePlans (column mapping + converters)."""

    def __init__(self, settings: Settings, source, target_conn: psycopg.Connection):
        self.settings = settings
        self.source = source
        self.conn = target_conn
        self._plans: dict = {}
        self._target_cols: dict = {}

    def target_columns(self, spec: TableSpec):
        if spec.key not in self._target_cols:
            cols = tgt.columns(self.conn, spec.target)
            if not cols:
                raise ChunkFailed(f"target table {spec.target} not found")
            self._target_cols[spec.key] = cols
        return self._target_cols[spec.key]

    def plan(self, spec: TableSpec, source_table: str, context: dict | None = None) -> TablePlan:
        key = (spec.key, source_table, tuple(sorted((context or {}).items())))
        if key not in self._plans:
            src_cols = self.source.columns(source_table)
            if not src_cols:
                raise ChunkFailed(f"source table {source_table} not found")
            plan = build_plan(spec, source_table, src_cols, self.target_columns(spec), context,
                              timezone=self.settings.source.get("timezone", "UTC"))
            chunk_target(plan)  # validates the chunk column mapping early
            self._plans[key] = plan
        return self._plans[key]


def chunk_target(plan: TablePlan):
    """(target column, kind) that the chunk predicate applies to on the target side."""
    spec = plan.spec
    if spec.strategy == "per_source_table":
        for s in plan.steps:
            if s.target.name == spec.chunk_target_column:
                return s
        raise ValueError(f"{spec.key}: chunk_target_column {spec.chunk_target_column!r} is not loaded")
    if spec.strategy in ("date_range", "int_range"):
        for s in plan.steps:
            if s.source_index is not None and plan.source_columns[s.source_index].name == spec.chunk_column:
                if s.target.data_type in TEXT_TGT and spec.strategy == "date_range" and not spec.datetime_text_format.startswith("%Y-%m-%d"):
                    raise ValueError(f"{spec.key}: chunk column is stored as text; datetime_text_format must start with %Y-%m-%d so ranges sort correctly")
                return s
        raise ValueError(f"{spec.key}: chunk_column {spec.chunk_column!r} is not a loaded column")
    return None


def target_predicate(plan: TablePlan, chunk: Chunk) -> tuple[sql.Composable, list]:
    if chunk.kind == "full":
        return sql.SQL("TRUE"), []
    step = chunk_target(plan)
    col = sql.Identifier(step.target.name)
    if chunk.kind == "source_table":
        return sql.SQL("{} = %s").format(col), [step.convert(step.constant)]
    if chunk.kind == "null":
        return sql.SQL("{} IS NULL").format(col), []
    if chunk.kind == "date":
        if step.target.data_type in TEXT_TGT:
            lo, hi = chunk.lo, chunk.hi
        else:
            lo, hi = date.fromisoformat(chunk.lo), date.fromisoformat(chunk.hi)
        return sql.SQL("{c} >= %s AND {c} < %s").format(c=col), [lo, hi]
    if chunk.kind == "int":
        return sql.SQL("{c} >= %s AND {c} < %s").format(c=col), [int(chunk.lo), int(chunk.hi)]
    raise ValueError(chunk.kind)


def _jsonable(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


class Loader:
    """data_conn must be an autocommit connection: each chunk opens its own transaction."""

    def __init__(self, settings: Settings, source, control: Control, data_conn: psycopg.Connection,
                 planner: Planner, worker: str, dry_run: bool = False, log=print):
        self.settings = settings
        self.source = source
        self.control = control
        if not data_conn.autocommit:
            raise ValueError("Loader needs an autocommit connection")
        self.conn = data_conn
        self.planner = planner
        self.worker = worker
        self.dry_run = dry_run
        self.log = log

    def process(self, row: dict) -> dict:
        """Load one claimed chunk. Returns a result dict; raises nothing for data problems."""
        spec = self.settings.table(row["table_key"])
        chunk = chunk_from_row(row)
        started = time.monotonic()
        progress = {"rows_read": 0}
        try:
            plan = self.planner.plan(spec, chunk.source_table or spec.source, chunk.context_dict)
            result = self._load(spec, plan, chunk, row, progress, started)
            return result
        except Exception as e:  # any failure leaves the chunk retryable
            if not self.conn.closed and self.conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                self.conn.rollback()
            msg = f"{type(e).__name__}: {e}"
            if not self.dry_run:
                self.control.fail_chunk(row, msg, progress["rows_read"], time.monotonic() - started,
                                        int(self.settings.run.get("retry_backoff_seconds", 30)))
            self.control.event(row["run_id"], "error", f"chunk failed: {msg}", spec.key, chunk.chunk_key)
            return {"status": "failed", "error": msg, "rows_read": progress["rows_read"]}

    def _load(self, spec: TableSpec, plan: TablePlan, chunk: Chunk, row: dict, progress: dict, started: float) -> dict:
        plan.stats.clear()
        table = tgt.table_ident(spec.target)
        where, params = target_predicate(plan, chunk)
        cols = sql.SQL(", ").join(sql.Identifier(c) for c in plan.target_columns)
        src_cols = [c.name for c in plan.source_columns]
        token = row["lease_token"]
        rejects: list[tuple] = []
        loaded = 0
        loaded_sum = Decimal(0) if plan.checksum_index is not None else None
        rejected_sum = Decimal(0) if plan.checksum_index is not None else None
        checksum_src = None
        if plan.checksum_index is not None:
            checksum_src = plan.steps[plan.checksum_index].source_index
        seen: set | None = set() if plan.dedupe_indexes else None
        last_beat = time.monotonic()
        max_rejects = spec.max_reject_rows

        conn = self.conn
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(sql.SQL("SET LOCAL synchronous_commit = {}").format(sql.Literal(self.settings.target.get("synchronous_commit", "on"))))
            cur.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(str(self.settings.target.get("statement_timeout", "0")))))
            needs_delete = row["needs_delete"]
            if not self.dry_run:
                # Re-read under the transaction: the lease may have been taken over while this worker was stalled.
                cur.execute(self.control.q("SELECT needs_delete FROM {s}.chunk WHERE chunk_id = %s AND lease_token = %s"),
                            (row["chunk_id"], token))
                fresh = cur.fetchone()
                if fresh is None:
                    raise LeaseLost("another worker took over this chunk (lease expired); nothing was written")
                needs_delete = fresh[0]
            deleted = 0
            if needs_delete or chunk.kind == "full":
                cur.execute(sql.SQL("DELETE FROM {} WHERE ").format(table) + where, params)
                deleted = cur.rowcount
            cur.execute(self.control.q("DELETE FROM {s}.rejected_row WHERE chunk_id = %s"), (row["chunk_id"],))

            copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(table, cols)
            with cur.copy(copy_sql) as copy:
                for batch in self.source.read(plan.source_table, src_cols, chunk, spec.chunk_column, spec.batch_size):
                    for src_row in batch:
                        progress["rows_read"] += 1
                        try:
                            out = plan.transform(src_row)
                            if seen is not None:
                                k = tuple(out[i] for i in plan.dedupe_indexes)
                                if k in seen:
                                    raise Reject("duplicate_key", ",".join(spec.dedupe_on), k, "duplicate of a row already loaded in this chunk")
                                seen.add(k)
                        except Reject as r:
                            rejects.append((r, src_row))
                            if rejected_sum is not None and checksum_src is not None:
                                v = src_row[checksum_src]
                                if v is not None:
                                    rejected_sum += Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
                            if len(rejects) > max_rejects:
                                raise ChunkFailed(f"more than {max_rejects} rejected rows (last: {r}); fix the data or raise max_reject_rows")
                            continue
                        copy.write_row(out)
                        loaded += 1
                        if loaded_sum is not None:
                            v = out[plan.checksum_index]
                            if v is not None:
                                loaded_sum += Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
                    now = time.monotonic()
                    if now - last_beat > 15 and not self.dry_run:
                        self.control.heartbeat_chunk(row["chunk_id"], token, progress["rows_read"])
                        last_beat = now

            read = progress["rows_read"]
            if rejects and read >= 1000 and len(rejects) * 100.0 / read > spec.max_reject_pct:
                raise ChunkFailed(f"{len(rejects)} of {read} rows rejected ({len(rejects) * 100.0 / read:.2f}%), "
                                  f"above max_reject_pct {spec.max_reject_pct}")

            if rejects:
                with conn.cursor() as rc:
                    rc.executemany(self.control.q(
                        """INSERT INTO {s}.rejected_row (chunk_id, run_id, table_key, reason, column_name, value, detail, row_data)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""),
                        [(row["chunk_id"], row["run_id"], spec.key, r.reason, r.column, None if r.value is None else str(r.value)[:1000],
                          r.detail, Jsonb({c: _jsonable(v) for c, v in zip(src_cols, src)})) for r, src in rejects])

            # Validate what landed in the target slice against what was sent.
            agg_col = sql.SQL("sum({})").format(sql.Identifier(plan.target_columns[plan.checksum_index])) if plan.checksum_index is not None else sql.SQL("NULL")
            cur.execute(sql.SQL("SELECT count(*), {} FROM {} WHERE ").format(agg_col, table) + where, params)
            t_count, t_sum = cur.fetchone()
            if t_count != loaded:
                raise ChunkFailed(f"target slice has {t_count} rows after load, expected {loaded}"
                                  + ("" if needs_delete else " (target had rows the plan did not expect; rerun with --force)"))
            if loaded_sum is not None and not _sums_match(t_sum, loaded_sum, plan):
                raise ChunkFailed(f"target checksum {t_sum} != loaded checksum {loaded_sum}")

            duration = time.monotonic() - started
            stats = {**plan.stats, "deleted_before_load": deleted}
            if self.dry_run:
                raise _DryRunRollback({"status": "dry_run", "rows_read": read, "rows_loaded": loaded,
                                       "rows_rejected": len(rejects), "stats": stats,
                                       "reject_reasons": _reasons(rejects)})
            cur.execute(self.control.q(
                """UPDATE {s}.chunk SET status = 'done', finished_at = now(), heartbeat_at = now(), rows_read = %s,
                       rows_loaded = %s, rows_rejected = %s, loaded_checksum = %s, rejected_checksum = %s,
                       duration_s = %s, stats = %s, error = NULL, loaded_at = now(), needs_delete = true,
                       lease_token = NULL, next_attempt_at = NULL, verified_at = NULL, verify_result = NULL
                   WHERE chunk_id = %s AND lease_token = %s"""),
                (read, loaded, len(rejects), loaded_sum, rejected_sum, round(duration, 3), Jsonb(stats), row["chunk_id"], token))
            if cur.rowcount != 1:
                raise LeaseLost("another worker took over this chunk (lease expired); this attempt was rolled back")
            cur.execute(self.control.q(
                """INSERT INTO {s}.chunk_attempt (chunk_id, run_id, table_key, chunk_key, worker, status, started_at,
                                                 rows_read, rows_loaded, rows_rejected, duration_s, stats)
                   VALUES (%s, %s, %s, %s, %s, 'done', %s, %s, %s, %s, %s, %s)"""),
                (row["chunk_id"], row["run_id"], spec.key, chunk.chunk_key, self.worker, row["started_at"],
                 read, loaded, len(rejects), round(duration, 3), Jsonb(stats)))
        msg = f"loaded {loaded:,} rows" + (f", rejected {len(rejects):,}" if rejects else "") + f" in {duration:.1f}s"
        if rejects:
            msg += " (" + ", ".join(f"{k}: {v}" for k, v in _reasons(rejects).items()) + ")"
        self.control.event(row["run_id"], "warning" if rejects else "info", msg, spec.key, chunk.chunk_key)
        return {"status": "done", "rows_read": read, "rows_loaded": loaded, "rows_rejected": len(rejects), "duration": duration}


class _DryRunRollback(Exception):
    def __init__(self, result):
        super().__init__("dry run")
        self.result = result


def _reasons(rejects) -> dict:
    out: dict = {}
    for r, _ in rejects:
        k = f"{r.reason}:{r.column}"
        out[k] = out.get(k, 0) + 1
    return out


def _sums_match(t_sum, loaded_sum: Decimal, plan: TablePlan) -> bool:
    if t_sum is None:
        return loaded_sum == 0
    t = Decimal(t_sum) if not isinstance(t_sum, float) else Decimal(repr(t_sum))
    if plan.steps[plan.checksum_index].target.data_type == "numeric":
        return t == loaded_sum
    return abs(t - loaded_sum) <= max(Decimal("1e-6") * abs(loaded_sum), Decimal("1e-6"))


def dry_run_chunk(loader: Loader, row: dict) -> dict:
    """Run the full load for a chunk inside a transaction that is always rolled back."""
    spec = loader.settings.table(row["table_key"])
    chunk = chunk_from_row(row)
    plan = loader.planner.plan(spec, chunk.source_table or spec.source, chunk.context_dict)
    progress = {"rows_read": 0}
    try:
        loader._load(spec, plan, chunk, {**row, "lease_token": None}, progress, time.monotonic())
    except _DryRunRollback as d:
        return d.result
    except Exception as e:
        return {"status": "failed", "error": f"{type(e).__name__}: {e}", "rows_read": progress["rows_read"]}
    return {"status": "unexpected"}
