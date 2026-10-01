"""Monitoring dashboard: a read-only JSON API over the control tables plus one HTML page.

    python -m onroute_migration -c config/config.toml dashboard [--host 0.0.0.0] [--port 8765]

Besides monitoring, the dashboard can start, stop, resume and re-run commands
(see actions.py). Controls are on when it listens on localhost, or on any address
when [dashboard] admin_token is set. Uses only the standard library HTTP server. Every request opens a short read-only
transaction, so the dashboard can run next to a migration without blocking it.
"""

from __future__ import annotations

import hmac
import json
import re
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row

from .actions import ActionError, JobManager, build_args

INDEX = Path(__file__).with_name("index.html")


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, timedelta):
        return o.total_seconds()
    return str(o)


class Api:
    def __init__(self, dsn: str, schema: str):
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
            raise ValueError("bad control schema name")
        self.dsn = dsn
        self.s = schema
        self._local = threading.local()

    def _conn(self) -> psycopg.Connection:
        c = getattr(self._local, "conn", None)
        if c is None or c.closed:
            c = psycopg.connect(self.dsn, autocommit=True, application_name="onroute-migration-dashboard", row_factory=dict_row)
            c.execute("SET default_transaction_read_only = on")
            c.execute("SET statement_timeout = '15s'")
            self._local.conn = c
        return c

    def q(self, text: str, params=None) -> list[dict]:
        text = text.replace("{s}", f'"{self.s}"')
        try:
            return self._conn().execute(text, params).fetchall()
        except psycopg.OperationalError:
            self._local.conn = None
            return self._conn().execute(text, params).fetchall()

    def ready(self) -> bool:
        return bool(self.q("SELECT to_regclass(%s) IS NOT NULL AS ok", (f'"{self.s}".chunk',))[0]["ok"])

    # ------------------------------------------------------------ endpoints
    def overview(self) -> dict:
        if not self.ready():
            return {"ready": False}
        tables = self.q("""
            SELECT c.table_key, max(ts.target_table) AS target_table, max(ts.source_table) AS source_table,
                   max(ts.strategy) AS strategy, min(c.priority) AS priority, max(ts.source_rows) AS source_rows,
                   max(ts.source_rows_at) AS source_rows_at, max(ts.target_rows) AS target_rows,
                   count(*) FILTER (WHERE c.status <> 'skipped') AS chunks,
                   count(*) FILTER (WHERE c.status = 'done') AS done,
                   count(*) FILTER (WHERE c.status = 'running') AS running,
                   count(*) FILTER (WHERE c.status = 'failed') AS failed,
                   count(*) FILTER (WHERE c.status = 'pending') AS pending,
                   count(*) FILTER (WHERE c.status = 'stale') AS stale,
                   COALESCE(sum(c.rows_loaded) FILTER (WHERE c.status IN ('done', 'stale')), 0) AS rows_loaded,
                   COALESCE(sum(c.rows_read) FILTER (WHERE c.status IN ('done', 'stale')), 0) AS rows_read_done,
                   COALESCE(sum(c.rows_rejected) FILTER (WHERE c.status IN ('done', 'stale')), 0) AS rows_rejected,
                   COALESCE(sum(c.rows_read) FILTER (WHERE c.status = 'running'), 0) AS rows_in_flight,
                   max(c.loaded_at) AS last_loaded_at,
                   max(jsonb_array_length(COALESCE(ts.warnings, '[]'::jsonb))) AS warnings
            FROM {s}.chunk c LEFT JOIN {s}.table_state ts USING (table_key)
            GROUP BY c.table_key ORDER BY min(c.priority), c.table_key""")
        val = self.q("""SELECT DISTINCT ON (table_key, check_name) table_key, check_name, passed, source_value, target_value, checked_at
                        FROM {s}.validation WHERE chunk_key IS NULL ORDER BY table_key, check_name, checked_at DESC""")
        by_table: dict = {}
        for v in val:
            by_table.setdefault(v["table_key"], []).append(v)
        strips = self.q("""SELECT table_key, json_agg(json_build_array(chunk_key, status, rows_loaded, lo) ORDER BY chunk_key) AS cells
                           FROM {s}.chunk WHERE status <> 'skipped' GROUP BY table_key""")
        strip_by = {r["table_key"]: r["cells"] for r in strips}
        for t in tables:
            t["validations"] = by_table.get(t["table_key"], [])
            t["strip"] = strip_by.get(t["table_key"], [])
        runs = self.q("""SELECT run_id, command, status, started_at, heartbeat_at, workers, tables, options, stop_requested, launched_by,
                                extract(epoch FROM now() - heartbeat_at) AS heartbeat_age_s
                         FROM {s}.run WHERE status = 'running' ORDER BY run_id DESC""")
        running = self.q("""SELECT table_key, chunk_key, kind, lo, hi, source_table, worker, run_id, attempts, rows_read, started_at,
                                   extract(epoch FROM now() - started_at) AS elapsed_s,
                                   extract(epoch FROM now() - heartbeat_at) AS heartbeat_age_s
                            FROM {s}.chunk WHERE status = 'running' ORDER BY started_at""")
        thr = self.q("""SELECT date_trunc('minute', finished_at) AS minute, sum(rows_loaded) AS rows, count(*) AS chunks
                        FROM {s}.chunk_attempt WHERE status = 'done' AND finished_at > now() - interval '60 minutes'
                        GROUP BY 1 ORDER BY 1""")
        rate = self.q("""SELECT COALESCE(sum(rows_loaded), 0) AS rows,
                                extract(epoch FROM (now() - min(started_at))) AS secs
                         FROM {s}.chunk_attempt WHERE status = 'done' AND finished_at > now() - interval '15 minutes'""")[0]
        fails = self.q("""SELECT a.table_key, a.chunk_key, a.run_id, a.worker, a.finished_at, a.error, c.status AS current_status, c.attempts
                          FROM {s}.chunk_attempt a JOIN {s}.chunk c USING (chunk_id)
                          WHERE a.status = 'failed' ORDER BY a.finished_at DESC LIMIT 15""")
        events = self.q("SELECT event_id, run_id, ts, level, table_key, chunk_key, message FROM {s}.event ORDER BY event_id DESC LIMIT 60")
        last = self.q("""SELECT run_id, status, started_at, finished_at, tables, options, workers, error
                         FROM {s}.run WHERE command = 'run' ORDER BY run_id DESC LIMIT 1""")
        now = self.q("SELECT now() AS now")[0]["now"]
        total_src = sum(int(t["source_rows"] or 0) for t in tables)
        total_read = sum(int(t["rows_read_done"] or 0) for t in tables)
        per_sec = (float(rate["rows"]) / float(rate["secs"])) if rate["secs"] and float(rate["secs"]) > 0 else 0.0
        remaining = max(total_src - total_read - sum(int(t["rows_in_flight"] or 0) for t in tables), 0)
        return {
            "ready": True, "now": now, "tables": tables, "active_runs": runs, "running_chunks": running,
            "last_load_run": last[0] if last else None,
            "throughput": thr, "recent_failures": fails, "events": events,
            "totals": {
                "source_rows": total_src, "rows_read": total_read,
                "rows_loaded": sum(int(t["rows_loaded"] or 0) for t in tables),
                "rows_rejected": sum(int(t["rows_rejected"] or 0) for t in tables),
                "rows_in_flight": sum(int(t["rows_in_flight"] or 0) for t in tables),
                "chunks": sum(t["chunks"] for t in tables), "done": sum(t["done"] for t in tables),
                "failed": sum(t["failed"] for t in tables), "running": sum(t["running"] for t in tables),
                "pending": sum(t["pending"] + t["stale"] for t in tables),
                "rows_per_sec_15m": per_sec,
                "eta_s": (remaining / per_sec) if per_sec > 0 and remaining else None,
                "remaining_rows": remaining,
            },
        }

    def runs(self, limit: int = 100) -> dict:
        if not self.ready():
            return {"ready": False, "runs": []}
        rows = self.q("""SELECT r.run_id, r.command, r.status, r.started_at, r.finished_at, r.host, r.os_user, r.workers, r.tables, r.launched_by,
                                r.options, r.summary, r.error,
                                extract(epoch FROM COALESCE(r.finished_at, now()) - r.started_at) AS duration_s,
                                (SELECT count(*) FROM {s}.chunk_attempt a WHERE a.run_id = r.run_id AND a.status = 'done') AS chunks_done,
                                (SELECT count(*) FROM {s}.chunk_attempt a WHERE a.run_id = r.run_id AND a.status = 'failed') AS chunk_failures,
                                (SELECT COALESCE(sum(rows_loaded), 0) FROM {s}.chunk_attempt a WHERE a.run_id = r.run_id) AS rows_loaded,
                                (SELECT COALESCE(sum(rows_rejected), 0) FROM {s}.chunk_attempt a WHERE a.run_id = r.run_id) AS rows_rejected
                         FROM {s}.run r ORDER BY r.run_id DESC LIMIT %s""", (limit,))
        return {"ready": True, "runs": rows}

    def run(self, run_id: int) -> dict:
        r = self.q("""SELECT *, extract(epoch FROM COALESCE(finished_at, now()) - started_at) AS duration_s
                      FROM {s}.run WHERE run_id = %s""", (run_id,))
        if not r:
            return {"error": f"run {run_id} not found"}
        per_table = self.q("""SELECT table_key, count(*) FILTER (WHERE status = 'done') AS done, count(*) FILTER (WHERE status = 'failed') AS failed,
                                     COALESCE(sum(rows_loaded), 0) AS rows_loaded, COALESCE(sum(rows_rejected), 0) AS rows_rejected,
                                     COALESCE(sum(duration_s), 0) AS busy_s
                              FROM {s}.chunk_attempt WHERE run_id = %s GROUP BY table_key ORDER BY table_key""", (run_id,))
        attempts = self.q("""SELECT table_key, chunk_key, worker, status, started_at, finished_at, rows_read, rows_loaded,
                                    rows_rejected, duration_s, error
                             FROM {s}.chunk_attempt WHERE run_id = %s ORDER BY finished_at DESC LIMIT 500""", (run_id,))
        events = self.q("SELECT event_id, ts, level, table_key, chunk_key, message FROM {s}.event WHERE run_id = %s ORDER BY event_id LIMIT 2000", (run_id,))
        vals = self.q("""SELECT table_key, chunk_key, check_name, source_value, target_value, passed, detail
                         FROM {s}.validation WHERE run_id = %s ORDER BY passed, table_key, chunk_key LIMIT 500""", (run_id,))
        return {"run": r[0], "per_table": per_table, "attempts": attempts, "events": events, "validations": vals}

    def table(self, key: str) -> dict:
        state = self.q("SELECT * FROM {s}.table_state WHERE table_key = %s", (key,))
        chunks = self.q("""SELECT chunk_id, chunk_key, kind, lo, hi, source_table, status, attempts, worker, run_id, rows_read, rows_loaded,
                                  rows_rejected, duration_s, started_at, finished_at, loaded_at, verified_at, verify_result, error, stats
                           FROM {s}.chunk WHERE table_key = %s ORDER BY chunk_key""", (key,))
        reasons = self.q("""SELECT reason, column_name, count(*) AS rows, min(value) AS example
                            FROM {s}.rejected_row WHERE table_key = %s GROUP BY reason, column_name ORDER BY count(*) DESC""", (key,))
        samples = self.q("""SELECT r.reason, r.column_name, r.value, r.detail, r.row_data, c.chunk_key
                            FROM {s}.rejected_row r JOIN {s}.chunk c USING (chunk_id)
                            WHERE r.table_key = %s ORDER BY r.reject_id LIMIT 25""", (key,))
        profile = self.q("""SELECT DISTINCT ON (source_table, column_name, check_name) source_table, column_name, target_column,
                                   check_name, result, flagged, checked_at
                            FROM {s}.profile WHERE table_key = %s
                            ORDER BY source_table, column_name, check_name, checked_at DESC""", (key,))
        history = self.q("""SELECT a.run_id, a.chunk_key, a.status, a.worker, a.finished_at, a.rows_loaded, a.rows_rejected, a.duration_s, a.error
                            FROM {s}.chunk_attempt a WHERE a.table_key = %s ORDER BY a.finished_at DESC LIMIT 200""", (key,))
        return {"state": state[0] if state else None, "chunks": chunks, "reject_reasons": reasons,
                "reject_samples": samples, "profile": profile, "history": history}


class Controls:
    """The write side of the dashboard: launching commands and stop requests."""

    def __init__(self, ctx, api: Api, enabled: bool, reason: str, token: str | None):
        self.ctx = ctx
        self.api = api
        self.enabled = enabled
        self.reason = reason
        self.token = token
        self.known = [t.key for t in ctx.settings.select(None)]
        base = Path(ctx.config_path).resolve().parent.parent
        log_dir = Path(ctx.settings.dashboard.get("log_dir") or "logs")
        self.jobs = JobManager(ctx, log_dir if log_dir.is_absolute() else base / log_dir)
        self._control = None

    def control(self):
        if self._control is None or self._control.conn.closed:
            self._control = self.ctx.control()
            self._control.ensure_schema()
        return self._control

    def config(self) -> dict:
        s = self.ctx.settings
        return {"actions_enabled": self.enabled, "actions_reason": self.reason, "token_required": bool(self.token),
                "default_workers": int(s.run["workers"]),
                "tables": [{"key": t.key, "strategy": t.strategy, "priority": t.priority} for t in s.select(None)]}

    def start(self, body: dict, by: str) -> dict:
        if body.get("action") == "resume":
            body = self.resume_action(body)
        if body.get("action") in ("run", "verify") and not body.get("dry_run"):
            active = self.api.q("SELECT run_id, command FROM {s}.run WHERE status = 'running' AND command IN ('run', 'verify', 'reset', 'plan') "
                                "AND heartbeat_at > now() - interval '5 minutes' ORDER BY run_id DESC LIMIT 1") if self.api.ready() else []
            if active:
                raise ActionError(f"run {active[0]['run_id']} ({active[0]['command']}) is still in progress; stop it or wait for it to finish")
        command, args = build_args(body, self.known)
        job = self.jobs.launch(command, args, by)
        return {"job": job, "message": f"Started: {job['display']}"}

    def resume_action(self, body: dict) -> dict:
        """Repeat the scope of the most recent load run, without --force (finished chunks are skipped)."""
        if not self.api.ready():
            raise ActionError("nothing to resume yet")
        rid = body.get("run_id")
        rows = self.api.q("SELECT run_id, tables, options, workers FROM {s}.run WHERE command = 'run' AND (%s::bigint IS NULL OR run_id = %s) "
                          "ORDER BY run_id DESC LIMIT 1", (rid, rid))
        if not rows:
            raise ActionError("no earlier run to resume")
        r = rows[0]
        o = r["options"] or {}
        tables = r["tables"] or []
        return {"action": "run", "mode": "only_failed" if o.get("only_failed") else "resume",
                "tables": [] if set(tables) >= set(self.known) else [t for t in tables if t in self.known],
                "date_from": o.get("date_from"), "date_to": o.get("date_to"), "chunks": o.get("chunk_keys") or [],
                "workers": body.get("workers") or r["workers"]}

    def stop(self, body: dict, by: str) -> dict:
        mode = body.get("mode", "graceful")
        run_id = body.get("run_id")
        if run_id is not None:
            run_id = int(run_id)
        ids = self.control().request_stop(run_id, mode, by)
        if not ids:
            raise ActionError("no run is in progress")
        what = "in-flight chunks roll back within a few seconds" if mode == "now" else "workers finish their current chunks first"
        return {"stopped": ids, "message": f"Stop requested for run {', '.join(map(str, ids))}: {what}."}


class Handler(BaseHTTPRequestHandler):
    api: Api = None        # set by serve()
    controls: Controls = None

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=_json_default).encode(), "application/json")

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/overview":
                return self._json(self.api.overview())
            if url.path == "/api/runs":
                return self._json(self.api.runs(int(qs.get("limit", ["100"])[0])))
            m = re.fullmatch(r"/api/runs/(\d+)", url.path)
            if m:
                return self._json(self.api.run(int(m.group(1))))
            m = re.fullmatch(r"/api/tables/([A-Za-z0-9_]+)", url.path)
            if m:
                return self._json(self.api.table(m.group(1)))
            if url.path == "/api/config":
                return self._json(self.controls.config())
            if url.path == "/api/jobs":
                return self._json({"jobs": self.controls.jobs.list()})
            m = re.fullmatch(r"/api/jobs/(\d+)/log", url.path)
            if m:
                return self._json(self.controls.jobs.log_tail(int(m.group(1))))
            return self._json({"error": "not found"}, 404)
        except ActionError as e:
            return self._json({"error": str(e)}, 404)
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _authorised(self) -> str | None:
        """Returns an error message, or None when the request may change things."""
        c = self.controls
        if not c.enabled:
            return c.reason
        if self.headers.get("X-Requested-By") != "onroute-dashboard":
            return "missing X-Requested-By header"
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return "requests must be JSON"
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return "cross-origin request refused"
        if c.token and not hmac.compare_digest(self.headers.get("X-Admin-Token", ""), c.token):
            return "admin token missing or wrong"
        return None

    def do_POST(self):
        url = urlparse(self.path)
        problem = self._authorised()
        if problem:
            return self._json({"error": problem}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 100_000:
                return self._json({"error": "request too large"}, 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ActionError("request body must be a JSON object")
            by = f"{self.client_address[0]}"
            if url.path == "/api/actions":
                return self._json(self.controls.start(body, by))
            if url.path == "/api/stop":
                return self._json(self.controls.stop(body, by))
            return self._json({"error": "not found"}, 404)
        except (ActionError, ValueError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)


LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def serve(ctx, host: str | None = None, port: int | None = None) -> int:
    s = ctx.settings
    dsn = s.dashboard.get("dsn") or s.target["dsn"]
    api = Api(dsn, s.control_schema)
    host = host or s.dashboard.get("host", "127.0.0.1")
    port = int(port or s.dashboard.get("port", 8765))
    token = s.dashboard.get("admin_token") or None
    enabled, reason = bool(s.dashboard.get("allow_actions", True)), ""
    if not enabled:
        reason = "controls are turned off in the config ([dashboard] allow_actions = false)"
    elif host not in LOOPBACK and not token:
        enabled, reason = False, "controls are off: the dashboard listens on a network address without [dashboard] admin_token set"
    Handler.api = api
    Handler.controls = Controls(ctx, api, enabled, reason, token)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Migration dashboard on http://{host}:{port}  (Ctrl-C to stop; runs started here keep going)", flush=True)
    if not enabled:
        print(f"  {reason}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
