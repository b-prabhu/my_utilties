"""Start, stop, resume and re-run migration commands from the dashboard.

Every action is turned into the same command line an operator would type
(`python -m onroute_migration run ...`) and launched as its own process, so a
run keeps going if the dashboard is closed or restarted. Output goes to a log
file per job. Stop requests are written to the run's row in the control schema,
which also stops runs that were started from a terminal or another machine.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
CHUNK = re.compile(r"^(?:[dwm]:\d{4}-\d{2}(?:-\d{2})?|i:\d{1,20}|null|all|src:[A-Za-z0-9_-]{1,40})$")
RUN_MODES = {"resume", "refresh", "force", "only_failed"}


class ActionError(ValueError):
    pass


def _tables(value, known: list[str]) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",") if v.strip()]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ActionError("tables must be a list of table keys")
    unknown = [v for v in value if v not in known]
    if unknown:
        raise ActionError(f"unknown tables: {', '.join(unknown)}")
    return value


def _int(value, name, lo, hi):
    if value in (None, ""):
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ActionError(f"{name} must be a whole number") from None
    if not lo <= v <= hi:
        raise ActionError(f"{name} must be between {lo} and {hi}")
    return v


def _date(value, name):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not DATE.match(value):
        raise ActionError(f"{name} must look like 2024-03 or 2024-03-15")
    return value


def build_args(action: dict, known_tables: list[str]) -> tuple[str, list[str]]:
    """Validate an action request and return (command, CLI arguments after the global options)."""
    kind = action.get("action")
    tables = _tables(action.get("tables"), known_tables)
    args: list[str] = []
    if tables:
        args += ["-t", ",".join(tables)]

    if kind == "run":
        mode = action.get("mode", "resume")
        if mode not in RUN_MODES:
            raise ActionError(f"mode must be one of {sorted(RUN_MODES)}")
        if mode == "force":
            args.append("--force")
        elif mode == "refresh":
            args.append("--refresh")
            days = _int(action.get("reopen_days"), "reopen days", 0, 3650)
            if days is not None:
                args += ["--reopen-days", str(days)]
        elif mode == "only_failed":
            args.append("--only-failed")
        for key, flag in (("date_from", "--from"), ("date_to", "--to")):
            v = _date(action.get(key), key.replace("_", " "))
            if v:
                args += [flag, v]
        chunks = action.get("chunks") or []
        if isinstance(chunks, str):
            chunks = [chunks]
        for c in chunks:
            if not isinstance(c, str) or not CHUNK.match(c):
                raise ActionError(f"bad chunk key {c!r}")
            args += ["--chunk", c]
        workers = _int(action.get("workers"), "workers", 1, 64)
        if workers:
            args += ["-w", str(workers)]
        if action.get("dry_run"):
            args.append("--dry-run")
            sample = _int(action.get("sample"), "sample", 1, 1000)
            if sample:
                args += ["--sample", str(sample)]
        if action.get("retry_failed") is False:
            args.append("--no-retry-failed")
        if mode == "force" and not (tables or chunks or action.get("date_from") or action.get("date_to")) and not action.get("confirm_all"):
            raise ActionError("a forced reload of every table needs confirm_all")
        return "run", args

    if kind == "verify":
        for key, flag in (("date_from", "--from"), ("date_to", "--to")):
            v = _date(action.get(key), key.replace("_", " "))
            if v:
                args += [flag, v]
        for c in action.get("chunks") or []:
            if not isinstance(c, str) or not CHUNK.match(c):
                raise ActionError(f"bad chunk key {c!r}")
            args += ["--chunk", c]
        limit = _int(action.get("limit"), "limit", 1, 1_000_000)
        if limit:
            args += ["--limit", str(limit)]
        return "verify", args

    if kind == "profile":
        pct = action.get("sample_pct")
        if pct not in (None, ""):
            try:
                pct = float(pct)
            except (TypeError, ValueError):
                raise ActionError("sample percent must be a number") from None
            if not 0 < pct <= 100:
                raise ActionError("sample percent must be between 0 and 100")
            args += ["--sample-pct", f"{pct:g}"]
        return "profile", args

    if kind == "check":
        return "check", args

    raise ActionError(f"unknown action {kind!r}")


class JobManager:
    """Launches migration commands as child processes and remembers them in jobs.json."""

    def __init__(self, ctx, log_dir: Path):
        self.ctx = ctx
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.log_dir / "jobs.json"
        self.lock = threading.Lock()
        self.jobs: list[dict] = []
        self.procs: dict[int, subprocess.Popen] = {}
        if self.state_file.exists():
            try:
                self.jobs = json.loads(self.state_file.read_text())
            except ValueError:
                self.jobs = []
        for j in self.jobs:
            if j.get("status") == "running" and not _alive(j.get("pid")):
                j["status"] = "ended"
                j["note"] = "finished while the dashboard was not running; see the run history for the result"

    def _save(self):
        self.state_file.write_text(json.dumps(self.jobs[-200:], indent=1, default=str))

    def base_argv(self) -> list[str]:
        argv = [sys.executable, "-m", "onroute_migration", "-c", str(Path(self.ctx.config_path).resolve())]
        if self.ctx.tables_path:
            argv += ["--tables-file", str(Path(self.ctx.tables_path).resolve())]
        return argv

    def launch(self, command: str, args: list[str], by: str) -> dict:
        with self.lock:
            job_id = (max((j["job_id"] for j in self.jobs), default=0)) + 1
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_path = self.log_dir / f"job-{job_id:04d}-{stamp}-{command}.log"
            argv = self.base_argv() + [command] + args
            env = {**os.environ, "ONROUTE_LAUNCHED_BY": f"dashboard ({by})", "PYTHONUNBUFFERED": "1"}
            pkg_root = str(Path(__file__).resolve().parents[2])
            env["PYTHONPATH"] = pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            log = open(log_path, "ab")
            log.write(f"$ {' '.join(shlex.quote(a) for a in ['python', '-m', 'onroute_migration'] + [command] + args)}\n".encode())
            log.flush()
            proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    cwd=pkg_root, env=env,
                                    start_new_session=True)
            log.close()
            job = {"job_id": job_id, "command": command, "args": args,
                   "display": "python -m onroute_migration " + " ".join(shlex.quote(a) for a in [command] + args),
                   "pid": proc.pid, "started_at": datetime.now().astimezone().isoformat(), "ended_at": None,
                   "exit_code": None, "status": "running", "log": log_path.name, "by": by}
            self.jobs.append(job)
            self.procs[job_id] = proc
            self._save()
        threading.Thread(target=self._wait, args=(job_id, proc), daemon=True).start()
        return job

    def _wait(self, job_id: int, proc: subprocess.Popen):
        code = proc.wait()
        with self.lock:
            for j in self.jobs:
                if j["job_id"] == job_id:
                    j.update(status="ended", exit_code=code, ended_at=datetime.now().astimezone().isoformat(),
                             note=EXIT_NOTES.get(code, ""))
            self.procs.pop(job_id, None)
            self._save()

    def list(self) -> list[dict]:
        with self.lock:
            return list(reversed(self.jobs[-50:]))

    def running(self) -> list[dict]:
        return [j for j in self.list() if j["status"] == "running"]

    def log_tail(self, job_id: int, max_bytes: int = 60000) -> dict:
        job = next((j for j in self.list() if j["job_id"] == job_id), None)
        if not job:
            raise ActionError(f"job {job_id} not found")
        path = self.log_dir / job["log"]
        data = b""
        if path.exists():
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                data = f.read()
        return {"job": job, "log": data.decode("utf-8", "replace"), "truncated": len(data) >= max_bytes}


EXIT_NOTES = {0: "finished", 1: "finished with errors", 2: "stopped before loading: configuration or mapping problems",
              3: "did not start: another migration command was already running", 4: "stopped on request",
              130: "interrupted"}


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False
