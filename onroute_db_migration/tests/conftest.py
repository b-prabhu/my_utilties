import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

PG_DSN = os.environ.get("ONROUTE_TEST_PG_DSN")


@pytest.fixture
def pg_env(tmp_path, monkeypatch):
    """A clean target database (master schema from the export, no control schema) and a config pointing at it."""
    if not PG_DSN:
        pytest.skip("set ONROUTE_TEST_PG_DSN to run end-to-end tests against PostgreSQL")
    import psycopg
    with psycopg.connect(PG_DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS migration_test CASCADE")
        c.execute((HERE / "target_schema.sql").read_text())
    cfg = tmp_path / "config.toml"
    cfg.write_text(f"""
[source]
dsn = "unused"
[target]
dsn = "{PG_DSN}"
control_schema = "migration_test"
synchronous_commit = "off"
[run]
workers = 1
max_attempts = 3
retry_backoff_seconds = 0
lease_minutes = 1
""")
    (tmp_path / "tables.toml").write_text((HERE.parent / "config" / "tables.toml").read_text())
    monkeypatch.setenv("ONROUTE_SOURCE_FACTORY", "fake_source:factory")
    monkeypatch.setenv("FAKE_SOURCE_PATH", str(tmp_path / "source.pkl"))
    monkeypatch.setenv("FAKE_FAIL_FILE", str(tmp_path / "fail.txt"))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(HERE.parent), str(HERE)]))
    import fake_source
    data = fake_source.build_dataset()
    fake_source.save(data, str(tmp_path / "source.pkl"))
    return {"dir": tmp_path, "config": str(cfg), "dsn": PG_DSN, "data": data}
