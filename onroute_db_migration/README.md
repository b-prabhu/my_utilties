# ONroute database migration (SQL Server → PostgreSQL)

Moves the 15 ONroute tables (~689 million rows) from SQL Server `dbo` into the
existing PostgreSQL `master` schema. The migration can be stopped and re-run at any
point, and every run is recorded and visible in a monitoring dashboard.

```
onroute_db_migration/
  config/tables.toml          table definitions: strategy, chunking, renames, ignores, constants
  config/config.example.toml  connections and run settings (copy to config.toml)
  onroute_migration/          the tool  (python -m onroute_migration ...)
  onroute_migration/dashboard monitoring dashboard (served by the tool)
  analysis/                   source vs target schema comparison
  tests/                      unit + end-to-end tests (real PostgreSQL, fake SQL Server)
```

## Strategy, and why

The data is very lopsided: three POS tables hold 97% of the rows.

| Table | Rows | Strategy | Chunk |
|---|---:|---|---|
| pos_order_details | 441.9M | date_range on `Endday` | month (~4–5M rows) |
| pos_order_payments | 115.1M | date_range on `Endday` | month |
| pos_orders | 113.7M | date_range on `Endday` | month |
| weekly_cogs | 8.9M | int_range on `WeeklyCogs_ID` | 1M IDs |
| employee_pay_summary | 8.8M | date_range on `PayDate` | month |
| vena_* (4) | 37k–736k | per_source_table (one table per budget year) | one year |
| 7 small tables | ≤ 119k | full | whole table |

* **Chunks are the unit of work.** Each table is split into chunks that partition
  the source, and each chunk maps to an exact slice of the target (for example
  `end_day >= '2024-03-01' AND end_day < '2024-04-01'`). Rows with no chunk value
  (a NULL `Endday`) get their own `null` chunk, so nothing falls between chunks.
* **One chunk = one PostgreSQL transaction.** It clears the target slice, bulk-loads
  with `COPY`, writes rejected rows, checks the slice's row count and checksum
  against what was sent, and marks the chunk done, all in one transaction. A chunk
  is either fully loaded and recorded, or not loaded at all. That is what makes
  re-running safe: a reload replaces its slice, so rows are never duplicated, even
  though the target's `uuid` keys are regenerated.
* **Parallel and resumable.** Workers claim chunks with `FOR UPDATE SKIP LOCKED`, so
  several processes (or machines) can share one run. Every chunk has a lease with a
  heartbeat. If a worker dies, its chunk is taken over once the lease expires, and
  the dead worker can no longer commit.
* **Fast first load.** When a table's target is empty at first planning, chunks skip
  the delete step until they have been loaded once. Every reload after that deletes
  its slice first.
* **Conversions come from the schemas.** Each column's conversion is derived from
  the live source and target types:
  * text flags become `boolean`
  * GUID text is validated and becomes `uuid`
  * order type names are checked against the enum's allowed values
  * floats are rounded to the target's `numeric` precision, with an overflow check
  * datetimes become dates (counting any time of day that is dropped) or ISO-formatted text
  * text gets a length check and has NUL characters removed
  * columns that become NOT NULL get a NULL check, or the configured default (`null_defaults`)
  * `budget_year` is set from the Vena table name

  A column that maps to nothing stops the run unless it is listed in `ignore`.
* **Bad rows are kept, not lost.** A row that can't be converted goes to
  `migration.rejected_row`, together with its source values and the reason. A chunk
  fails, and is rolled back, if it rejects more than `max_reject_rows` rows or more
  than `max_reject_pct` percent of its rows.

### Throughput and sizing

Measured on the 40-column `POS_ORDERDETAILS` shape, one worker converted and loaded
**about 25–40k rows per second**. The loop is CPU-bound in Python, so throughput
scales with workers until SQL Server reads, the network or PostgreSQL WAL become the
limit. A planning estimate for the full 689M rows:

| Workers | Rows/s (estimate) | Initial load |
|---:|---:|---|
| 4 | 100–150k | 1.5–2 h of pure load time |
| 8 | 180–250k | 45–65 min |

Expect 2–4× that in practice once source I/O and index maintenance are included.
The dashboard shows the real rate and estimated time left within minutes of
starting. A load that doesn't fit one maintenance window can be stopped with Ctrl-C
and resumed the next night.

## Setup

```bash
cd onroute_db_migration
python -m pip install -r requirements.txt          # psycopg 3, pyodbc (+ Microsoft ODBC Driver 18)
cp config/config.example.toml config/config.toml   # set hosts; passwords come from env vars
export MSSQL_PASSWORD=... PG_PASSWORD=...
```

The SQL Server login needs read access only. The PostgreSQL login needs
INSERT/DELETE/SELECT on `master.*` and CREATE on the database (for the `migration`
control schema).

**Indexes (do this first).** Every chunk reads its slice from SQL Server and, on a
reload, deletes and recounts its slice in PostgreSQL. Without an index that starts
with the chunk column, each chunk scans the whole table. `check` and `run` warn about
any missing index. For example:

```sql
-- SQL Server (or confirm an existing index already leads with Endday)
CREATE INDEX ix_mig_endday ON dbo.POS_ORDERDETAILS (Endday) WITH (ONLINE = ON);   -- also POS_ORDERS, POS_ORDERPAYMENTS
CREATE INDEX ix_mig_paydate ON dbo.EmployeePaySummaryV2 (PayDate);
-- PostgreSQL
CREATE INDEX ON master.pos_order_details (end_day);   -- also pos_orders, pos_order_payments
CREATE INDEX ON master.employee_pay_summary (pay_date);
```

## Commands

All commands take `-c config/config.toml` and `-t table1,table2` (default: all tables).

| Command | What it does |
|---|---|
| `check` | Resolves every column mapping against the live source and target and prints each conversion. Writes nothing. |
| `profile [--sample-pct 5]` | Scans the source for values that would be rejected: too long, NULL into NOT NULL, unmapped flag/enum values, bad GUIDs, numeric overflow, dropped time of day, duplicate keys. Results appear in the dashboard. |
| `run --only-failed` | Retries only the chunks that failed. |
| `run --dry-run [--sample 2]` | Loads chunks inside transactions that are always rolled back, so the real constraints are tested without changing anything. |
| `run` | Loads every chunk that isn't done yet. **Always safe to re-run**: finished chunks are skipped and failed ones are retried. |
| `verify` | Re-counts done chunks in both databases (rows and checksum column). Mismatches are marked *needs reload*, and the next `run` reloads only those chunks. |
| `stop [--now] [--run-id N]` | Asks a running command to stop. By default workers finish the chunk they're on, then stop. With `--now`, in-flight chunks are rolled back within a few seconds. This works on runs started anywhere: a terminal, the dashboard or another machine. |
| `status` | Progress per table, plus failed chunks with their errors. |
| `dashboard` | Serves the monitoring dashboard on http://127.0.0.1:8765. |
| `reset -t X --yes [--truncate-target]` | Forgets the checkpoints for a table (optionally truncating its target) so it starts from scratch. |

## Re-run scenarios

| Situation | What to do | What happens |
|---|---|---|
| First load | `run -w 8` | Plans chunks, then loads them in parallel. |
| Need to pause (end of a maintenance window) | Dashboard **Stop after current chunks**, or `stop` | The run ends as *stopped* once in-flight chunks finish. **Resume** carries on later. |
| Ctrl-C, reboot, network drop, killed process | `run` again, or **Resume** in the dashboard | In-flight chunk transactions were rolled back. Ctrl-C returns those chunks to the queue immediately; after a hard kill they're taken over once their lease expires (`lease_minutes`). Done chunks are skipped. |
| One chunk keeps failing | Read the error in the dashboard or `status`, fix the cause, then `run` | A failure is retried up to `max_attempts` times, with backoff. The next run resets the attempt count and tries again. |
| Rows rejected | Look up the reason on the table's dashboard page, then fix the source data or the config, then `run -t X --chunk m:2024-03 --force` | That chunk's slice and its rejected-row list are replaced. |
| The source still receives data (before cutover) | `run --refresh --reopen-days 7` | Reloads full tables, Vena years, NULL chunks, the last ID range, and date chunks ending in the last 7 days. |
| Old data corrected in the source | `verify --from 2024-01 --to 2024-07`, then `run` | Chunks that no longer match are reloaded; nothing else is touched. |
| Reload a date range | `run -t pos_orders --from 2023-01 --to 2023-07 --force` | Only date chunks overlapping that range are reloaded. |
| New month, or a new Vena year table (e.g. `Sales_2027_UnPivot_New`) | `run` | Re-planning adds the new chunks automatically. |
| Target already had rows before the tool ran | `run` | Detected at first planning, so every chunk deletes its slice before loading. |
| Mapping or schema changed | `check`, edit `tables.toml`, then `run --force -t X` | The run stops before loading anything if a column no longer maps. |
| Start a table over | `reset -t X --truncate-target --yes`, then `run -t X` | |

## Suggested cutover plan

1. Create the indexes above, then run `check` and `profile --sample-pct 5`. Resolve the
   flagged values (see `analysis/schema_review.html`), or decide to accept them as rejects.
2. Run `run --dry-run --sample 2`.
3. Do the initial load (`run -w 8`) over one or more nights, followed by `verify`.
4. Run `run --refresh` daily until cutover.
5. At cutover:
   - Stop writes to SQL Server (POS feed and ETL jobs).
   - Run `run --refresh --reopen-days 3`.
   - Run `verify --from <last month>` and check that the dashboard shows all counts matching.
   - Switch reporting over to PostgreSQL.

   SQL Server is never modified, so rolling back means pointing reports at it again.
6. After the load, run `ANALYZE` on the `master` tables.

## Dashboard: monitor and control

`python -m onroute_migration dashboard` serves a page that refreshes every 5 seconds.

**Controls.** Everything the command line can do is also available from buttons:

* **Overview:**
  * *Resume* (loads what isn't done) or *Start loading*
  * *Retry N failed chunks*
  * *Catch up recent data* (`--refresh`)
  * *Verify against source*
  * *Stop after current chunks* or *Stop now* while a run is going
* **Control tab:** a form for any command (load, dry run, verify, profile, check
  mapping). You choose which chunks (resume, catch up, only failed, or reload
  everything), the tables, the date range, workers, sample size and so on. It shows the
  equivalent command line before you start. A list of commands started from the
  dashboard follows, each with its live log.
* **Table page:** *Load remaining chunks*, *Retry failed*, *Reload whole table*,
  *Verify*, *Profile source*. Select any chunk to *Reload this chunk* or *Verify* it.
* **Run page:** *Resume run N* for a stopped, interrupted or failed run (same tables and
  filters, finished chunks skipped), or stop buttons if it is still going.

Destructive actions (stop now, reloading a whole table or every table) need a second
click to confirm. Each command runs as its own process with its own log, so it keeps
going if the dashboard is closed or restarted.

**Safety:**
* Only one writing command (run, verify, reset, plan) can run at a time, enforced by a
  database lock, so a second start is refused instead of colliding.
* Buttons are enabled when the dashboard listens on localhost. On a network address
  they need `[dashboard] admin_token`. Set `allow_actions = false` for a view-only
  dashboard.
* Every request must carry a dashboard-only header and be same-origin, so other
  websites can't trigger actions.

**Monitoring.** The page shows:

* overall progress, throughput and estimated time left
* every table: rows read against source rows, a strip of its chunks coloured by
  status, rejects, and failed checks
* chunks loading right now, with each worker's heartbeat (a stuck worker stands out)
* rows loaded per minute over the last hour, recent failures, and a live activity feed
* **Run history:** every `run`, `verify`, `profile`, `dry-run` and `reset`, with
  who started it and from where, its options, duration, results, full log and
  validation results
* **Table pages:** every chunk (select one for its details and the command to reload
  it), rejected rows by reason with samples, source profile findings, the resolved
  column mapping, and load history

Monitoring queries use `[dashboard] dsn` (a read-only login is enough). Stop requests
and launched commands use the normal migration login. History is ordinary tables in the `migration` schema (`run`,
`chunk`, `chunk_attempt`, `rejected_row`, `event`, `validation`, `profile`,
`table_state`), so it can also be queried directly.

## Decisions still open (from the schema review)

These are configured with a sensible default, and each one is easy to change in
`tables.toml`:

* `WeeklyCogs.createdate` is loaded into `created_at`.
* `AuthorizedManager` and `AuthorizedEmployee` are ignored, because the target has no columns for them.
* `pay_date` and `retrieve_date` are written as `YYYY-MM-DD HH:MM:SS` text, because the target columns are varchar.
* Values longer than the target column are rejected (`string_overflow = "reject"`). Set it to `"truncate"` to cut them to fit instead.
* The `order_type_name` enum's allowed values are read from PostgreSQL. Run `profile` to see any source values outside that list.
* `netsuite_location_mapping.location_id_src` has no source column, so it is left NULL.

## Tests

```bash
pip install pytest openpyxl
python -m pytest tests                                    # unit tests
ONROUTE_TEST_PG_DSN="postgresql://...test-db" python -m pytest tests   # + end-to-end scenarios
```

The end-to-end tests run against a real PostgreSQL database with the target schema
(`tests/target_schema.sql`, generated from the target export), using an in-memory
SQL Server stand-in seeded with deliberately bad rows. They cover:

* a full load, with the expected rejects
* an idempotent rerun, and forced reloads without duplicates
* retry after a failure, and a chunk that keeps failing
* takeover of a dead worker's lease, with the stale worker refused at commit
* an interrupted run
* late source data caught by verify, and reloading only the affected chunk
* refresh, date-range scope and dry run
* pre-existing target rows
* parallel workers, reset and profile
* the dashboard API
* stopping after current chunks, then resuming
* stopping now, which rolls back the chunk in flight
* refusing a second writer while one is running
* retrying only failed chunks
* starting runs from the dashboard (with its access checks)

**Use a throwaway database for these tests.** They drop and recreate the `master`
schema.
