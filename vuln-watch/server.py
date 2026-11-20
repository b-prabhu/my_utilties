"""VulnWatch server: periodic scheduler + JSON API + static control-centre UI.

    python server.py                 # http://127.0.0.1:8085
    python server.py --port 9000 --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import collector as c

STATIC_DIR = Path(__file__).resolve().parent / "static"
SECRET_MASK = "••••••••"
SECRET_PATHS = [("sources", "nvd", "api_key"), ("sources", "github", "token"), ("notifications", "webhook_url")]

log = logging.getLogger("vulnwatch.server")


# --------------------------------------------------------------------------- scheduler
class Scheduler:
    def __init__(self):
        self.wake = threading.Event()
        self.stop_scan = threading.Event()
        self.shutdown = threading.Event()
        self.run_now = False
        self.running = False
        self.progress = ""
        self.next_run: datetime | None = None
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)

    def start(self):
        self.thread.start()

    def trigger(self) -> bool:
        with self.lock:
            if self.running:
                return False
            self.run_now = True
        self.wake.set()
        return True

    def cancel(self):
        self.stop_scan.set()

    def reschedule(self):
        """Config changed - recompute next run without starting a scan."""
        self.wake.set()

    def _compute_next(self, cfg) -> datetime | None:
        if not cfg.get("schedule", {}).get("enabled", True):
            return None
        last = c.parse_dt(c.load_state().get("last_run"))
        if last is None:
            return c.utcnow() if cfg["schedule"].get("run_on_startup", True) else c.utcnow() + timedelta(seconds=c.interval_seconds(cfg))
        return last + timedelta(seconds=c.interval_seconds(cfg))

    def _loop(self):
        while not self.shutdown.is_set():
            cfg = c.load_config()
            nxt = self._compute_next(cfg)
            self.next_run = nxt
            due = self.run_now or (nxt is not None and nxt <= c.utcnow())
            if not due:
                timeout = 3600 if nxt is None else max(1.0, min(3600, (nxt - c.utcnow()).total_seconds()))
                self.wake.wait(timeout)
                self.wake.clear()
                continue
            with self.lock:
                self.run_now = False
                self.running = True
            self.stop_scan.clear()
            try:
                log.info("Scan starting")
                result = c.run_scan(cfg, self.stop_scan, self._set_progress)
                log.info("Scan finished: %s new, %s updated, %s errors",
                         result["new"], result["updated"], len(result["errors"]))
            except Exception:  # noqa: BLE001
                log.error("Scan crashed:\n%s", traceback.format_exc())
                state = c.load_state()
                state["last_run"] = c.iso(c.utcnow())
                state["runs"] = ([{"started": c.iso(c.utcnow()), "finished": c.iso(c.utcnow()), "status": "failed",
                                   "errors": [traceback.format_exc(limit=2)], "new": 0, "updated": 0, "fetched": 0,
                                   "per_tech": {}}] + state.get("runs", []))[:50]
                c.save_state(state)
            finally:
                with self.lock:
                    self.running = False
                self.progress = ""

    def _set_progress(self, msg: str):
        self.progress = msg
        log.info(msg)

    def status(self) -> dict:
        state = c.load_state()
        cfg = c.load_config()
        return {
            "running": self.running,
            "progress": self.progress,
            "next_run": c.iso(self.next_run) if self.next_run else None,
            "last_run": state.get("last_run"),
            "kev_checked": state.get("kev_checked"),
            "interval_seconds": c.interval_seconds(cfg),
            "schedule_enabled": cfg.get("schedule", {}).get("enabled", True),
            "scheduler_active": self.thread.is_alive(),
            "runs": state.get("runs", [])[:20],
            "now": c.iso(c.utcnow()),
        }


SCHED = Scheduler()


# --------------------------------------------------------------------------- helpers
def _get(d, path):
    for p in path:
        d = (d or {}).get(p)
    return d


def _set(d, path, value):
    for p in path[:-1]:
        d = d.setdefault(p, {})
    d[path[-1]] = value


def mask_config(cfg: dict) -> dict:
    out = json.loads(json.dumps(cfg))
    for path in SECRET_PATHS:
        if _get(out, path):
            _set(out, path, SECRET_MASK)
    return out


def unmask_config(new: dict, old: dict) -> dict:
    for path in SECRET_PATHS:
        if _get(new, path) == SECRET_MASK:
            _set(new, path, _get(old, path) or "")
    return new


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "VulnWatch/1.0"

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)

    # -- responses
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status, msg):
        self._json({"error": msg}, status)

    def _body(self):
        # JSON-only mutations: a cross-site form post cannot send this content type
        # without a CORS pre-flight, which this server never approves.
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("Content-Type must be application/json")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(n) or b"{}")

    # -- routing
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path == "/api/vulns":
                store = c.load_store()
                self._json({"updated": store.get("updated"), "vulns": list(store.get("vulns", {}).values())})
            elif path == "/api/status":
                self._json(SCHED.status())
            elif path == "/api/config":
                self._json(mask_config(c.load_config()))
            elif path == "/api/config/default":
                self._json(c.read_json(c.DEFAULT_CONFIG_PATH, {}))
            elif path.startswith("/api/"):
                self._err(404, "not found")
            else:
                self._static(path)
        except Exception as e:  # noqa: BLE001
            log.error(traceback.format_exc())
            self._err(500, str(e))

    def do_PUT(self):
        try:
            if urlparse(self.path).path != "/api/config":
                return self._err(404, "not found")
            old = c.load_config()
            new = unmask_config(self._body(), old)
            errors = c.validate_config(new)
            if errors:
                return self._json({"error": "invalid configuration", "details": errors}, 400)
            c.write_json(c.CONFIG_PATH, new)
            SCHED.reschedule()
            self._json({"ok": True, "config": mask_config(new)})
        except (ValueError, json.JSONDecodeError) as e:
            self._err(400, str(e))

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            self._body()
            if path == "/api/scan":
                ok = SCHED.trigger()
                return self._json({"ok": ok, "message": "scan started" if ok else "a scan is already running"}, 202 if ok else 409)
            if path == "/api/scan/cancel":
                SCHED.cancel()
                return self._json({"ok": True})
            self._err(404, "not found")
        except (ValueError, json.JSONDecodeError) as e:
            self._err(400, str(e))

    def do_PATCH(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/vulns/"):
                vid = unquote(path[len("/api/vulns/"):])
                body = self._body()
                with c._store_lock:
                    store = c.load_store()
                    rec = store.get("vulns", {}).get(vid)
                    if not rec:
                        return self._err(404, "unknown vulnerability")
                    if "status" in body:
                        if body["status"] not in c.TRIAGE_STATES:
                            return self._err(400, f"status must be one of {c.TRIAGE_STATES}")
                        rec["status"] = body["status"]
                    if "notes" in body:
                        rec["notes"] = str(body["notes"])[:5000]
                    if "owner" in body:
                        rec["owner"] = str(body["owner"])[:120]
                    rec["status_updated"] = c.iso(c.utcnow())
                    c.save_store(store)
                return self._json({"ok": True, "vuln": rec})
            if path == "/api/vulns":  # bulk status update
                body = self._body()
                status = body.get("status")
                if status not in c.TRIAGE_STATES:
                    return self._err(400, "invalid status")
                with c._store_lock:
                    store = c.load_store()
                    n = 0
                    for vid in body.get("ids", []):
                        rec = store.get("vulns", {}).get(vid)
                        if rec:
                            rec["status"], rec["status_updated"] = status, c.iso(c.utcnow())
                            n += 1
                    c.save_store(store)
                return self._json({"ok": True, "updated": n})
            self._err(404, "not found")
        except (ValueError, json.JSONDecodeError) as e:
            self._err(400, str(e))

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        elif path == "/config":
            path = "/config.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            return self._err(404, "not found")
        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)


def main():
    cfg = c.load_config()
    ap = argparse.ArgumentParser(description="VulnWatch control centre")
    ap.add_argument("--host", default=cfg.get("server", {}).get("host", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(cfg.get("server", {}).get("port", 8085)))
    ap.add_argument("--no-scheduler", action="store_true", help="serve the UI only (e.g. when cron runs collector.py)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    c.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not args.no_scheduler:
        SCHED.start()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("VulnWatch control centre on http://%s:%s", args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        SCHED.shutdown.set()
        SCHED.stop_scan.set()
        SCHED.wake.set()


if __name__ == "__main__":
    main()
