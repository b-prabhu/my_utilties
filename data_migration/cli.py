"""Command line entry point: ``python -m data_migration <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .connections import describe, url_from_env
from .inspect_db import snapshot
from .report import write_report


def _parse_map(pairs: list[str]) -> dict[str, str] | None:
    if not pairs:
        return None
    out = {}
    for pair in pairs:
        src, sep, tgt = pair.partition("=")
        if not sep:
            raise SystemExit(f"--schema-map expects SRC=TGT, got {pair!r}")
        out[src] = tgt
    return out


def cmd_review(args) -> int:
    snaps = {}
    for prefix, label in (("src", "Source"), ("tgt", "Target")):
        url = url_from_env(prefix)
        print(f"Inspecting {label.lower()}: {describe(url)}", file=sys.stderr)
        snaps[prefix] = snapshot(url, label=label, count_rows=not args.no_counts, schemas=args.schemas.get(prefix))
        if snaps[prefix]["error"]:
            print(f"  ! {snaps[prefix]['error']}", file=sys.stderr)
        else:
            n = sum(len(s["tables"]) for s in snaps[prefix]["schemas"])
            print(f"  {len(snaps[prefix]['schemas'])} schemas, {n} tables", file=sys.stderr)

    if args.snapshot_dir:
        d = Path(args.snapshot_dir)
        d.mkdir(parents=True, exist_ok=True)
        for prefix, snap in snaps.items():
            (d / f"{prefix}_snapshot.json").write_text(json.dumps(snap, indent=2, default=str))

    out = write_report(args.out, snaps["src"], snaps["tgt"], _parse_map(args.schema_map))
    print(f"Report written to {out}", file=sys.stderr)
    return 1 if any(s["error"] for s in snaps.values()) else 0


def cmd_report(args) -> int:
    source = json.loads(Path(args.source).read_text())
    target = json.loads(Path(args.target).read_text())
    out = write_report(args.out, source, target, _parse_map(args.schema_map))
    print(f"Report written to {out}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="data_migration", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("review", help="inspect src_*/tgt_* databases from env vars and write an HTML review page")
    r.add_argument("--out", default="schema_review.html")
    r.add_argument("--snapshot-dir", help="also save the raw JSON snapshots here")
    r.add_argument("--no-counts", action="store_true", help="skip COUNT(*) per table (faster on big tables)")
    r.add_argument("--src-schema", action="append", default=[], help="limit source to this schema (repeatable)")
    r.add_argument("--tgt-schema", action="append", default=[], help="limit target to this schema (repeatable)")
    r.add_argument("--schema-map", action="append", default=[], metavar="SRC=TGT",
                   help="pair source schema SRC with target schema TGT (default for SQL Server→Postgres: dbo=public)")
    r.set_defaults(func=cmd_review)

    rep = sub.add_parser("report", help="build the HTML page from previously saved JSON snapshots")
    rep.add_argument("source")
    rep.add_argument("target")
    rep.add_argument("--out", default="schema_review.html")
    rep.add_argument("--schema-map", action="append", default=[], metavar="SRC=TGT")
    rep.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review":
        args.schemas = {"src": args.src_schema or None, "tgt": args.tgt_schema or None}
    return args.func(args)
