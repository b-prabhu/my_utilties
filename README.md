# my_utilties

## data_migration — source/target schema review

Inspects a source and a target database and writes a single self-contained HTML page
that shows, side by side:

- connection details (password masked), engine and version, and schemas
- every table, paired by schema and name (case-insensitive; `dbo` maps to `public` for SQL Server → Postgres)
- tables missing from the target and tables that only exist in the target
- per-column differences: missing or extra columns, type mismatches, narrowing (e.g. `NVARCHAR(320)` → `VARCHAR(255)`, `INT` → `SMALLINT`),
  NULL → NOT NULL, PK differences, and target NOT NULL columns with no default that would fail inserts
- primary keys, foreign keys, indexes and row counts (with Δ rows)

### Connection settings (environment variables)

| Variable | Example |
|---|---|
| `src_dbtype` / `tgt_dbtype` | `sqlserver`, `postgres`, `mysql`, `sqlite` |
| `src_host` / `tgt_host` | `myserver.database.windows.net` |
| `src_port` / `tgt_port` | optional (1433 / 5432 / 3306 by default) |
| `src_dbname` / `tgt_dbname` | database name |
| `src_username` / `tgt_username` | |
| `src_password` / `tgt_password` | |
| `src_url` / `tgt_url` | optional full SQLAlchemy URL, overrides the above |

Postgres connections use `sslmode=require` (required by Azure) unless `<prefix>_sslmode` says otherwise.

### Usage

```bash
pip install -r requirements.txt

# Inspect both databases and write the page
python -m data_migration review --out schema_review.html --snapshot-dir snapshots

# Useful options
#   --no-counts             skip COUNT(*) on every table
#   --src-schema dbo        limit what is inspected (repeatable; also --tgt-schema)
#   --schema-map dbo=etl    pair a source schema with a differently named target schema

# Rebuild the page later from saved snapshots, without connecting
python -m data_migration report snapshots/src_snapshot.json snapshots/tgt_snapshot.json --out schema_review.html
```

To try it without real databases:

```bash
python examples/make_demo_dbs.py demo
src_url=sqlite:///demo/source.db tgt_url=sqlite:///demo/target.db python -m data_migration review --out demo_review.html
```

### Tests

```bash
python -m pytest tests
```
