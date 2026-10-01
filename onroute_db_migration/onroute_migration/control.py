"""Control tables in the target database: runs, chunk checkpoints, attempts,
rejected rows, events, validations and profiles.

Chunk state machine:
    pending -> running -> done
                       -> failed  (retried with backoff up to run.max_attempts)
    done    -> stale   (verify found the source changed) -> running ...
A running chunk whose heartbeat is older than run.lease_minutes is taken over by
another worker; its owner can no longer commit because the lease token changed.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import socket
import uuid
from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .chunks import Chunk

SCHEMA_VERSION = 2
WRITER_LOCK = "hashtext('onroute-migration-writer')"

DDL = """
CREATE SCHEMA IF NOT EXISTS {s};

CREATE TABLE IF NOT EXISTS {s}.schema_version (version int PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS {s}.run (
    run_id        bigserial PRIMARY KEY,
    command       text NOT NULL,
    status        text NOT NULL,          -- running | succeeded | completed_with_errors | failed | stopped | interrupted | abandoned
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    heartbeat_at  timestamptz NOT NULL DEFAULT now(),
    host          text,
    os_user       text,
    pid           int,
    workers       int,
    tables        text[],
    options       jsonb NOT NULL DEFAULT '{{}}',
    summary       jsonb,
    error         text
);

ALTER TABLE {s}.run ADD COLUMN IF NOT EXISTS stop_requested text;      -- graceful | now
ALTER TABLE {s}.run ADD COLUMN IF NOT EXISTS stop_requested_at timestamptz;
ALTER TABLE {s}.run ADD COLUMN IF NOT EXISTS stop_requested_by text;
ALTER TABLE {s}.run ADD COLUMN IF NOT EXISTS launched_by text;

CREATE TABLE IF NOT EXISTS {s}.chunk (
    chunk_id          bigserial PRIMARY KEY,
    table_key         text NOT NULL,
    chunk_key         text NOT NULL,
    kind              text NOT NULL,      -- full | date | int | null | source_table
    lo                text,
    hi                text,
    source_table      text,
    context           jsonb NOT NULL DEFAULT '{{}}',
    priority          int NOT NULL DEFAULT 100,
    status            text NOT NULL DEFAULT 'pending',
    needs_delete      boolean NOT NULL DEFAULT true,
    attempts          int NOT NULL DEFAULT 0,
    next_attempt_at   timestamptz,
    lease_token       uuid,
    worker            text,
    run_id            bigint,
    started_at        timestamptz,
    heartbeat_at      timestamptz,
    finished_at       timestamptz,
    rows_read         bigint NOT NULL DEFAULT 0,
    rows_loaded       bigint,
    rows_rejected     bigint,
    loaded_checksum   numeric,
    rejected_checksum numeric,
    duration_s        numeric,
    stats             jsonb,
    error             text,
    loaded_at         timestamptz,
    verified_at       timestamptz,
    verify_result     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (table_key, chunk_key)
);
CREATE INDEX IF NOT EXISTS chunk_claim_idx ON {s}.chunk (status, priority, table_key, chunk_key);
CREATE INDEX IF NOT EXISTS chunk_finished_idx ON {s}.chunk (finished_at);

CREATE TABLE IF NOT EXISTS {s}.chunk_attempt (
    attempt_id     bigserial PRIMARY KEY,
    chunk_id       bigint NOT NULL REFERENCES {s}.chunk ON DELETE CASCADE,
    run_id         bigint,
    table_key      text NOT NULL,
    chunk_key      text NOT NULL,
    worker         text,
    status         text NOT NULL,          -- done | failed
    started_at     timestamptz,
    finished_at    timestamptz NOT NULL DEFAULT now(),
    rows_read      bigint,
    rows_loaded    bigint,
    rows_rejected  bigint,
    duration_s     numeric,
    error          text,
    stats          jsonb
);
CREATE INDEX IF NOT EXISTS chunk_attempt_run_idx ON {s}.chunk_attempt (run_id);
CREATE INDEX IF NOT EXISTS chunk_attempt_finished_idx ON {s}.chunk_attempt (finished_at);

CREATE TABLE IF NOT EXISTS {s}.rejected_row (
    reject_id    bigserial PRIMARY KEY,
    chunk_id     bigint NOT NULL REFERENCES {s}.chunk ON DELETE CASCADE,
    run_id       bigint,
    table_key    text NOT NULL,
    reason       text NOT NULL,
    column_name  text,
    value        text,
    detail       text,
    row_data     jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rejected_row_table_idx ON {s}.rejected_row (table_key, reason);
CREATE INDEX IF NOT EXISTS rejected_row_chunk_idx ON {s}.rejected_row (chunk_id);

CREATE TABLE IF NOT EXISTS {s}.event (
    event_id   bigserial PRIMARY KEY,
    run_id     bigint,
    ts         timestamptz NOT NULL DEFAULT now(),
    level      text NOT NULL,
    table_key  text,
    chunk_key  text,
    message    text NOT NULL
);
CREATE INDEX IF NOT EXISTS event_run_idx ON {s}.event (run_id, event_id);

CREATE TABLE IF NOT EXISTS {s}.table_state (
    table_key       text PRIMARY KEY,
    source_table    text,
    target_table    text,
    strategy        text,
    priority        int,
    source_rows     bigint,
    source_rows_at  timestamptz,
    target_rows     bigint,
    target_rows_at  timestamptz,
    planned_at      timestamptz,
    mapping         jsonb,
    warnings        jsonb
);

CREATE TABLE IF NOT EXISTS {s}.validation (
    validation_id  bigserial PRIMARY KEY,
    run_id         bigint,
    table_key      text NOT NULL,
    chunk_key      text,
    check_name     text NOT NULL,
    source_value   text,
    target_value   text,
    passed         boolean NOT NULL,
    detail         text,
    checked_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS validation_table_idx ON {s}.validation (table_key, checked_at);

CREATE TABLE IF NOT EXISTS {s}.profile (
    profile_id   bigserial PRIMARY KEY,
    run_id       bigint,
    table_key    text NOT NULL,
    source_table text,
    column_name  text,
    target_column text,
    check_name   text NOT NULL,
    result       jsonb NOT NULL,
    flagged      boolean NOT NULL,
    checked_at   timestamptz NOT NULL DEFAULT now()
);

INSERT INTO {s}.schema_version (version) VALUES ({version}) ON CONFLICT DO NOTHING;
"""

RUNNABLE = "(c.status IN ('pending', 'stale') OR (c.status = 'failed' AND c.attempts < %(max_attempts)s AND COALESCE(c.next_attempt_at, now()) <= now()) OR (c.status = 'running' AND c.heartbeat_at < now() - %(lease)s::interval))"


@dataclass
class Scope:
    """Which chunks a command acts on."""
    tables: list[str]
    date_from: date | None = None   # date chunks overlapping [date_from, date_to) only
    date_to: date | None = None
    chunk_keys: list[str] | None = None
    statuses: list[str] | None = None   # e.g. ["failed"] to retry only failed chunks

    def sql(self, alias: str = "c") -> tuple[str, dict]:
        parts = [f"{alias}.table_key = ANY(%(scope_tables)s)"]
        params: dict = {"scope_tables": list(self.tables)}
        if self.date_from or self.date_to:
            parts.append(f"{alias}.kind = 'date'")
            if self.date_from:
                parts.append(f"{alias}.hi > %(scope_from)s")
                params["scope_from"] = self.date_from.isoformat()
            if self.date_to:
                parts.append(f"{alias}.lo < %(scope_to)s")
                params["scope_to"] = self.date_to.isoformat()
        if self.chunk_keys:
            parts.append(f"{alias}.chunk_key = ANY(%(scope_chunks)s)")
            params["scope_chunks"] = list(self.chunk_keys)
        if self.statuses:
            parts.append(f"({alias}.status = ANY(%(scope_statuses)s) OR {alias}.status = 'running')")
            params["scope_statuses"] = list(self.statuses)
        return " AND ".join(parts), params

    def as_dict(self) -> dict:
        return {"tables": self.tables, "date_from": self.date_from and self.date_from.isoformat(),
                "date_to": self.date_to and self.date_to.isoformat(), "chunk_keys": self.chunk_keys, "statuses": self.statuses}

    @classmethod
    def from_dict(cls, d: dict) -> "Scope":
        return cls(d["tables"], d.get("date_from") and date.fromisoformat(d["date_from"]),
                   d.get("date_to") and date.fromisoformat(d["date_to"]), d.get("chunk_keys"), d.get("statuses"))


class Control:
    def __init__(self, conn: psycopg.Connection, schema: str = "migration"):
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
            raise ValueError(f"control schema name {schema!r} must be a plain lower-case identifier")
        self.conn = conn          # autocommit connection
        self.s = schema

    def q(self, text: str) -> str:
        return text.replace("{s}", f'"{self.s}"')

    def x(self, text: str, params=None):
        return self.conn.execute(self.q(text), params)

    def rows(self, text: str, params=None) -> list[dict]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(self.q(text), params)
            return cur.fetchall()

    # ------------------------------------------------------------ schema
    def ensure_schema(self):
        with self.conn.transaction():
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtext('onroute-migration-ddl'))")
            self.conn.execute(DDL.replace("{s}", f'"{self.s}"').replace("{version}", str(SCHEMA_VERSION)).replace("{{", "{").replace("}}", "}"))

    # ------------------------------------------------------------ runs
    def start_run(self, command: str, tables: list[str], options: dict, workers: int) -> int:
        row = self.x("""INSERT INTO {s}.run (command, status, host, os_user, pid, workers, tables, options, launched_by)
                        VALUES (%s, 'running', %s, %s, %s, %s, %s, %s, %s) RETURNING run_id""",
                     (command, socket.gethostname(), _user(), os.getpid(), workers, tables, Jsonb(options),
                      os.environ.get("ONROUTE_LAUNCHED_BY", "command line"))).fetchone()
        return row[0]

    # ------------------------------------------------------------ one writer at a time
    def acquire_writer_lock(self) -> bool:
        """Session-level lock held for the life of this process: only one run/verify/reset at a time."""
        return self.x(f"SELECT pg_try_advisory_lock({WRITER_LOCK})").fetchone()[0]

    def active_runs(self) -> list[dict]:
        return self.rows("""SELECT run_id, command, host, pid, started_at, heartbeat_at, stop_requested
                             FROM {s}.run WHERE status = 'running' ORDER BY run_id DESC""")

    def request_stop(self, run_id: int | None, mode: str, by: str) -> list[int]:
        if mode not in ("graceful", "now"):
            raise ValueError("mode must be graceful or now")
        rows = self.x("""UPDATE {s}.run SET stop_requested = %s, stop_requested_at = now(), stop_requested_by = %s
                          WHERE status = 'running' AND (%s::bigint IS NULL OR run_id = %s)
                            AND command IN ('run', 'dry-run', 'verify', 'profile')
                          RETURNING run_id""", (mode, by, run_id, run_id)).fetchall()
        for r in rows:
            self.event(r[0], "warning", f"stop requested ({'finish current chunks' if mode == 'graceful' else 'now: roll back in-flight chunks'}) by {by}")
        return [r[0] for r in rows]

    def stop_mode(self, run_id: int) -> str | None:
        row = self.x("SELECT stop_requested FROM {s}.run WHERE run_id = %s", (run_id,)).fetchone()
        return row[0] if row else None

    def heartbeat_run(self, run_id: int):
        self.x("UPDATE {s}.run SET heartbeat_at = now() WHERE run_id = %s", (run_id,))

    def finish_run(self, run_id: int, status: str, summary: dict | None = None, error: str | None = None):
        self.x("UPDATE {s}.run SET status = %s, finished_at = now(), heartbeat_at = now(), summary = %s, error = %s WHERE run_id = %s",
               (status, Jsonb(summary) if summary is not None else None, error, run_id))

    def abandon_dead_runs(self, lease_minutes: int) -> int:
        cur = self.x("""UPDATE {s}.run SET status = 'abandoned', finished_at = heartbeat_at,
                               error = COALESCE(error, 'process stopped without finishing (no heartbeat)')
                        WHERE status = 'running' AND heartbeat_at < now() - %s::interval""", (f"{lease_minutes} minutes",))
        return cur.rowcount

    def event(self, run_id: int | None, level: str, message: str, table_key: str | None = None, chunk_key: str | None = None):
        self.x("INSERT INTO {s}.event (run_id, level, table_key, chunk_key, message) VALUES (%s, %s, %s, %s, %s)",
               (run_id, level, table_key, chunk_key, message[:4000]))

    # ------------------------------------------------------------ planning
    def chunk_count(self, table_key: str) -> int:
        return self.x("SELECT count(*) FROM {s}.chunk WHERE table_key = %s", (table_key,)).fetchone()[0]

    def upsert_chunks(self, chunks: list[Chunk], priority: int, needs_delete: bool) -> int:
        if not chunks:
            return 0
        with self.conn.cursor() as cur:
            cur.executemany(self.q(
                """INSERT INTO {s}.chunk (table_key, chunk_key, kind, lo, hi, source_table, context, priority, needs_delete)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (table_key, chunk_key) DO UPDATE SET priority = EXCLUDED.priority,
                       source_table = EXCLUDED.source_table, context = EXCLUDED.context
                   RETURNING (xmax = 0)"""),
                [(c.table_key, c.chunk_key, c.kind, c.lo, c.hi, c.source_table, Jsonb(c.context_dict), priority, needs_delete)
                 for c in chunks], returning=True)
            new = 0
            while True:
                row = cur.fetchone()
                if row and row[0]:
                    new += 1
                if not cur.nextset():
                    break
        return new

    def mark_missing(self, table_key: str, present_keys: list[str]) -> int:
        """Chunks that no longer exist in the source (e.g. a dropped Vena year)."""
        cur = self.x("""UPDATE {s}.chunk SET status = 'skipped', error = 'no longer present in source'
                        WHERE table_key = %s AND NOT (chunk_key = ANY(%s)) AND status <> 'skipped'""", (table_key, present_keys))
        return cur.rowcount

    def requeue(self, scope: Scope, where: str = "TRUE", reason: str = "requeued", params: dict | None = None) -> int:
        s_sql, s_params = scope.sql()
        cur = self.x(f"""UPDATE {{s}}.chunk c SET status = 'pending', attempts = 0, next_attempt_at = NULL, error = %(reason)s
                         WHERE {s_sql} AND c.status IN ('done', 'failed', 'stale', 'skipped') AND ({where})""",
                     {**s_params, **(params or {}), "reason": reason})
        return cur.rowcount

    def reset_failed_attempts(self, scope: Scope) -> int:
        s_sql, s_params = scope.sql()
        cur = self.x(f"UPDATE {{s}}.chunk c SET attempts = 0, next_attempt_at = NULL WHERE {s_sql} AND c.status = 'failed'", s_params)
        return cur.rowcount

    def save_table_state(self, spec, source_table: str, source_rows: int | None, mapping: list[dict], warnings: list[str]):
        self.x("""INSERT INTO {s}.table_state (table_key, source_table, target_table, strategy, priority, source_rows,
                                              source_rows_at, planned_at, mapping, warnings)
                  VALUES (%s, %s, %s, %s, %s, %s, now(), now(), %s, %s)
                  ON CONFLICT (table_key) DO UPDATE SET source_table = EXCLUDED.source_table, target_table = EXCLUDED.target_table,
                      strategy = EXCLUDED.strategy, priority = EXCLUDED.priority,
                      source_rows = COALESCE(EXCLUDED.source_rows, {s}.table_state.source_rows),
                      source_rows_at = CASE WHEN EXCLUDED.source_rows IS NULL THEN {s}.table_state.source_rows_at ELSE now() END,
                      planned_at = now(), mapping = EXCLUDED.mapping, warnings = EXCLUDED.warnings""",
               (spec.key, source_table, spec.target, spec.strategy, spec.priority, source_rows, Jsonb(mapping), Jsonb(warnings)))

    def save_target_rows(self, table_key: str, rows: int):
        self.x("UPDATE {s}.table_state SET target_rows = %s, target_rows_at = now() WHERE table_key = %s", (rows, table_key))

    # ------------------------------------------------------------ claiming
    def claim(self, scope: Scope, run_id: int, worker: str, max_attempts: int, lease_minutes: int) -> dict | None:
        s_sql, s_params = scope.sql()
        token = uuid.uuid4()
        rows = self.rows(f"""
            UPDATE {{s}}.chunk t SET status = 'running', lease_token = %(token)s, worker = %(worker)s, run_id = %(run_id)s,
                   attempts = t.attempts + 1,
                   started_at = now(), heartbeat_at = now(), rows_read = 0, error = NULL
            WHERE t.chunk_id = (
                SELECT c.chunk_id FROM {{s}}.chunk c
                WHERE {s_sql} AND {RUNNABLE}
                ORDER BY c.priority, c.table_key, c.chunk_key
                FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING t.*""",
            {**s_params, "token": token, "worker": worker, "run_id": run_id,
             "max_attempts": max_attempts, "lease": f"{lease_minutes} minutes"})
        return rows[0] if rows else None

    def has_waiting(self, scope: Scope, max_attempts: int) -> bool:
        """True while some chunk in scope will become runnable later (retry backoff or another worker's lease)."""
        s_sql, s_params = scope.sql()
        return self.x(f"""SELECT EXISTS (SELECT 1 FROM {{s}}.chunk c WHERE {s_sql}
                          AND ((c.status = 'failed' AND c.attempts < %(max_attempts)s) OR c.status = 'running'))""",
                      {**s_params, "max_attempts": max_attempts}).fetchone()[0]

    def heartbeat_chunk(self, chunk_id: int, token, rows_read: int, run_id: int | None = None) -> str | None:
        """Record progress; returns the run's stop request, if any."""
        row = self.x("""WITH u AS (UPDATE {s}.chunk SET heartbeat_at = now(), rows_read = %s WHERE chunk_id = %s AND lease_token = %s)
                         SELECT stop_requested FROM {s}.run WHERE run_id = %s""", (rows_read, chunk_id, token, run_id)).fetchone()
        return row[0] if row else None

    def release_chunk(self, chunk: dict, reason: str):
        """Give a claimed chunk back to the queue without counting a failed attempt."""
        self.x("""UPDATE {s}.chunk SET status = CASE WHEN loaded_at IS NULL THEN 'pending' ELSE 'stale' END,
                         lease_token = NULL, attempts = GREATEST(attempts - 1, 0), error = %s
                  WHERE chunk_id = %s AND lease_token = %s""", (reason, chunk["chunk_id"], chunk["lease_token"]))

    def fail_chunk(self, chunk: dict, error: str, rows_read: int, duration: float, backoff_seconds: int, stats: dict | None = None):
        cur = self.x("""UPDATE {s}.chunk SET status = 'failed', error = %s, finished_at = now(), rows_read = %s,
                               duration_s = %s, next_attempt_at = now() + make_interval(secs => %s * attempts), lease_token = NULL
                        WHERE chunk_id = %s AND lease_token = %s""",
                     (error[:4000], rows_read, round(duration, 3), backoff_seconds, chunk["chunk_id"], chunk["lease_token"]))
        if cur.rowcount:
            self.x("""INSERT INTO {s}.chunk_attempt (chunk_id, run_id, table_key, chunk_key, worker, status, started_at,
                                                     rows_read, duration_s, error, stats)
                      VALUES (%s, %s, %s, %s, %s, 'failed', %s, %s, %s, %s, %s)""",
                   (chunk["chunk_id"], chunk["run_id"], chunk["table_key"], chunk["chunk_key"], chunk["worker"],
                    chunk["started_at"], rows_read, round(duration, 3), error[:4000], Jsonb(stats or {})))

    def release_running(self, run_id: int) -> int:
        """Return this run's in-flight chunks to the queue (their transactions were rolled back)."""
        cur = self.x("""UPDATE {s}.chunk SET status = CASE WHEN loaded_at IS NULL THEN 'pending' ELSE 'stale' END,
                               lease_token = NULL, attempts = GREATEST(attempts - 1, 0), error = 'interrupted'
                        WHERE run_id = %s AND status = 'running'""", (run_id,))
        return cur.rowcount

    # ------------------------------------------------------------ reporting helpers
    def scope_counts(self, scope: Scope) -> dict:
        s_sql, s_params = scope.sql()
        rows = self.x(f"SELECT c.status, count(*) FROM {{s}}.chunk c WHERE {s_sql} GROUP BY c.status", s_params).fetchall()
        return {r[0]: r[1] for r in rows}

    def done_chunks(self, scope: Scope) -> list[dict]:
        s_sql, s_params = scope.sql()
        return self.rows(f"SELECT c.* FROM {{s}}.chunk c WHERE {s_sql} AND c.status = 'done' ORDER BY c.priority, c.table_key, c.chunk_key", s_params)

    def validation(self, run_id, table_key, check, source_value, target_value, passed, detail="", chunk_key=None):
        self.x("""INSERT INTO {s}.validation (run_id, table_key, chunk_key, check_name, source_value, target_value, passed, detail)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
               (run_id, table_key, chunk_key, check, _s(source_value), _s(target_value), passed, detail))

    def profile_result(self, run_id, table_key, source_table, check: dict, result: dict, flagged: bool):
        self.x("""INSERT INTO {s}.profile (run_id, table_key, source_table, column_name, target_column, check_name, result, flagged)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
               (run_id, table_key, source_table, check.get("column") or ",".join(check.get("columns", [])),
                check.get("target"), check["check"], Jsonb(result), flagged))


def _s(v):
    return None if v is None else str(v)


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def dumps(obj) -> str:
    return json.dumps(obj, default=str)
