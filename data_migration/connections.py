"""Build SQLAlchemy URLs from ``src_*`` / ``tgt_*`` environment variables.

Recognised variables per side (prefix ``src`` or ``tgt``):

    <p>_dbtype    sqlserver | postgres | mysql | sqlite
    <p>_host      server hostname
    <p>_port      optional, defaults per dbtype
    <p>_dbname    database name (file path for sqlite)
    <p>_username
    <p>_password
    <p>_url       optional full SQLAlchemy URL, overrides everything above
"""

from __future__ import annotations

import os

from sqlalchemy.engine import URL

DRIVERS = {
    "sqlserver": ("mssql+pymssql", 1433),
    "mssql": ("mssql+pymssql", 1433),
    "postgres": ("postgresql+psycopg2", 5432),
    "postgresql": ("postgresql+psycopg2", 5432),
    "mysql": ("mysql+pymysql", 3306),
}


def _env(prefix: str, key: str) -> str | None:
    value = os.environ.get(f"{prefix}_{key}") or os.environ.get(f"{prefix}_{key}".upper())
    return value or None


def url_from_env(prefix: str) -> URL | str:
    """Return a connection URL for ``prefix`` ('src' or 'tgt')."""
    if full := _env(prefix, "url"):
        return full

    dbtype = (_env(prefix, "dbtype") or "").lower()
    if not dbtype:
        raise KeyError(f"{prefix}_dbtype is not set")
    if dbtype == "sqlite":
        return URL.create("sqlite", database=_env(prefix, "dbname"))
    if dbtype not in DRIVERS:
        raise ValueError(f"{prefix}_dbtype={dbtype!r} is not supported; use one of {sorted(DRIVERS)} or sqlite")

    driver, default_port = DRIVERS[dbtype]
    query = {}
    if driver.startswith("postgresql"):
        # Azure Database for PostgreSQL requires TLS.
        query["sslmode"] = _env(prefix, "sslmode") or "require"
    return URL.create(
        driver,
        username=_env(prefix, "username"),
        password=_env(prefix, "password"),
        host=_env(prefix, "host"),
        port=int(_env(prefix, "port") or default_port),
        database=_env(prefix, "dbname"),
        query=query,
    )


def describe(url: URL | str) -> str:
    """URL string with the password masked, safe to print or embed in a report."""
    if isinstance(url, str):
        from sqlalchemy.engine import make_url

        url = make_url(url)
    return url.render_as_string(hide_password=True)
