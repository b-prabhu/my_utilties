"""python -m onroute_migration <command> [options]

Commands
  check      validate every column mapping against the live source and target (no writes)
  profile    scan the source for values that would be rejected (lengths, NULLs, flags, GUIDs, ...)
  plan       work out chunks and record them, without loading
  run        load everything not yet loaded; safe to re-run at any time (resumes)
  verify     re-count loaded chunks against the source; mismatches are queued for reload
  status     print progress per table
  reset      forget checkpoints for tables (optionally truncate their targets)
  dashboard  serve the monitoring dashboard
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from . import runner


def _date(s: str) -> date:
    return date.fromisoformat(s if len(s) > 7 else s + "-01")


def _tables(s: str | None):
    return [t.strip() for t in s.split(",") if t.strip()] if s else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="onroute_migration", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", default="config/config.toml", help="connection and run settings (default config/config.toml)")
    p.add_argument("--tables-file", default=None, help="table definitions (default: tables.toml next to the config)")
    p.add_argument("--source-factory", default=None, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command", required=True)

    def with_tables(sp, required=False):
        sp.add_argument("-t", "--tables", required=required, help="comma-separated table keys (default: all)")
        return sp

    with_tables(sub.add_parser("check", help="validate mappings (no writes)"))
    sp = with_tables(sub.add_parser("profile", help="scan the source for values that would be rejected"))
    sp.add_argument("--sample-pct", type=float, default=None, help="profile a TABLESAMPLE percentage instead of every row")
    with_tables(sub.add_parser("plan", help="record chunks without loading"))

    sp = with_tables(sub.add_parser("run", help="load (resumes; safe to re-run)"))
    sp.add_argument("--from", dest="date_from", type=_date, help="only date chunks overlapping this date (YYYY-MM or YYYY-MM-DD) or later")
    sp.add_argument("--to", dest="date_to", type=_date, help="only date chunks before this date")
    sp.add_argument("--chunk", action="append", dest="chunks", help="only this chunk key (repeatable), e.g. m:2024-03")
    mode = sp.add_mutually_exclusive_group()
    mode.add_argument("--force", action="store_true", help="reload every chunk in scope, even ones already done")
    mode.add_argument("--refresh", action="store_true", help="also reload chunks that can still change: full tables, "
                                                              "Vena years, NULL chunks, recent date chunks, the last ID range")
    sp.add_argument("--reopen-days", type=int, default=7, help="with --refresh: reload date chunks ending within this many days (default 7)")
    sp.add_argument("-w", "--workers", type=int, help="parallel loaders (default from config)")
    sp.add_argument("--no-retry-failed", action="store_true", help="leave chunks that failed in an earlier run alone")
    sp.add_argument("--dry-run", action="store_true", help="load each chunk inside a transaction that is rolled back")
    sp.add_argument("--sample", type=int, help="with --dry-run: only this many chunks per table")
    sp.add_argument("--skip-table-counts", action="store_true", help="skip the final count(*) of completed target tables")

    sp = with_tables(sub.add_parser("verify", help="compare loaded chunks with the source"))
    sp.add_argument("--from", dest="date_from", type=_date)
    sp.add_argument("--to", dest="date_to", type=_date)
    sp.add_argument("--chunk", action="append", dest="chunks")
    sp.add_argument("--limit", type=int, help="only the most recent N done chunks")

    with_tables(sub.add_parser("status", help="progress per table"))
    sp = with_tables(sub.add_parser("reset", help="forget checkpoints"), required=True)
    sp.add_argument("--truncate-target", action="store_true", help="also TRUNCATE the target tables")
    sp.add_argument("--yes", action="store_true", help="confirm")

    sp = sub.add_parser("dashboard", help="serve the monitoring dashboard")
    sp.add_argument("--host", default=None)
    sp.add_argument("--port", type=int, default=None)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ctx = runner.Context(args.config, args.tables_file)
    if args.source_factory:
        ctx.source_factory = args.source_factory
    c = args.command
    tables = _tables(getattr(args, "tables", None))
    if c == "check":
        return runner.cmd_check(ctx, tables)
    if c == "profile":
        return runner.cmd_profile(ctx, tables, args.sample_pct)
    if c == "plan":
        return runner.cmd_plan(ctx, tables)
    if c == "run":
        return runner.cmd_run(ctx, tables, date_from=args.date_from, date_to=args.date_to, chunk_keys=args.chunks,
                              force=args.force, refresh=args.refresh, reopen_days=args.reopen_days, workers=args.workers,
                              retry_failed=not args.no_retry_failed, dry_run=args.dry_run, sample=args.sample,
                              skip_table_counts=args.skip_table_counts)
    if c == "verify":
        return runner.cmd_verify(ctx, tables, date_from=args.date_from, date_to=args.date_to, chunk_keys=args.chunks, limit=args.limit)
    if c == "status":
        return runner.cmd_status(ctx, tables)
    if c == "reset":
        return runner.cmd_reset(ctx, tables, args.truncate_target, args.yes)
    if c == "dashboard":
        from .dashboard.server import serve
        return serve(ctx, args.host, args.port)
    return 2


if __name__ == "__main__":
    sys.exit(main())
