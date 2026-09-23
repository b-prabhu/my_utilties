"""Create two small SQLite databases that show every kind of difference the review page reports.

    python examples/make_demo_dbs.py /tmp/demo
    src_dbtype=sqlite src_dbname=/tmp/demo/source.db \
    tgt_dbtype=sqlite tgt_dbname=/tmp/demo/target.db \
    python -m data_migration review --out demo_review.html
"""

import sqlite3
import sys
from pathlib import Path

SOURCE = """
CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY, email NVARCHAR(320) NOT NULL, full_name NVARCHAR(200),
  phone VARCHAR(40), is_active BIT NOT NULL DEFAULT 1, created_at DATETIME NOT NULL);
CREATE UNIQUE INDEX ux_customers_email ON customers(email);
CREATE TABLE products (
  product_id INTEGER PRIMARY KEY, sku VARCHAR(40) NOT NULL, name NVARCHAR(200) NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL, weight_kg FLOAT);
CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  status VARCHAR(20) NOT NULL, total DECIMAL(12,2), ordered_at DATETIME NOT NULL, notes TEXT);
CREATE INDEX ix_orders_customer ON orders(customer_id);
CREATE TABLE order_items (
  order_id BIGINT NOT NULL REFERENCES orders(order_id), line_no INTEGER NOT NULL,
  product_id INTEGER NOT NULL REFERENCES products(product_id), qty INTEGER NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL, PRIMARY KEY (order_id, line_no));
CREATE TABLE audit_log (log_id INTEGER PRIMARY KEY, table_name VARCHAR(128), action VARCHAR(10), logged_at DATETIME);
CREATE VIEW v_active_customers AS SELECT * FROM customers WHERE is_active = 1;
"""

TARGET = """
CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, full_name VARCHAR(200),
  phone VARCHAR(40), is_active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP NOT NULL,
  tenant_id INTEGER NOT NULL);
CREATE TABLE products (
  product_id INTEGER PRIMARY KEY, sku VARCHAR(40) NOT NULL, name VARCHAR(200) NOT NULL,
  unit_price NUMERIC(12,2) NOT NULL, weight_kg DOUBLE PRECISION);
CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY, customer_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL,
  total NUMERIC(12,2), ordered_at TIMESTAMP NOT NULL, notes TEXT, source_system VARCHAR(20) DEFAULT 'legacy');
CREATE TABLE order_items (
  order_id BIGINT NOT NULL, line_no SMALLINT NOT NULL, product_id INTEGER NOT NULL,
  qty INTEGER NOT NULL, unit_price NUMERIC(12,2) NOT NULL, PRIMARY KEY (order_id, line_no));
CREATE TABLE etl_run_log (run_id INTEGER PRIMARY KEY, started_at TIMESTAMP, status VARCHAR(20));
"""


def fill(conn, rows):
    for table, n, make in rows:
        ph = None
        for i in range(1, n + 1):
            vals = make(i)
            ph = ph or ",".join("?" * len(vals))
            conn.execute(f"INSERT INTO {table} VALUES ({ph})", vals)


def main(out: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, ddl in (("source", SOURCE), ("target", TARGET)):
        path = out_dir / f"{name}.db"
        path.unlink(missing_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(ddl)
        src = name == "source"
        fill(conn, [
            ("customers", 1200 if src else 1200,
             (lambda i: (i, f"c{i}@example.com", f"Customer {i}", None, 1, "2024-01-01")) if src
             else (lambda i: (i, f"c{i}@example.com", f"Customer {i}", None, 1, "2024-01-01", 1))),
            ("products", 85, lambda i: (i, f"SKU{i}", f"Product {i}", 9.99, 1.0)),
            ("orders", 5400 if src else 5312,
             (lambda i: (i, i % 1200 + 1, "shipped", 10.0, "2024-02-01", None)) if src
             else (lambda i: (i, i % 1200 + 1, "shipped", 10.0, "2024-02-01", None, "legacy"))),
            ("order_items", 16200 if src else 15936, lambda i: (i // 3 + 1, i % 3 + 1, i % 85 + 1, 1, 9.99)),
        ] + ([("audit_log", 300, lambda i: (i, "orders", "UPDATE", "2024-03-01"))] if src
             else [("etl_run_log", 12, lambda i: (i, "2024-03-01", "ok"))]))
        conn.commit()
        conn.close()
    print(f"wrote {out_dir}/source.db and {out_dir}/target.db")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo")
