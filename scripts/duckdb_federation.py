#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["duckdb==2.0.0", "psycopg[binary]==3.3.4"]
# ///
"""Optional Aurora + Parquet example. Never used by the app or required labs.

prepare creates a separate inventory-only PostgreSQL login and private local
connection files. query and check use only that login. cleanup removes it.
No customer data, agent tools, RLS policies or business rows are changed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local" / "duckdb"
ROLE = "pellier_inventory_reader"
QUERY = ROOT / "workshop" / "duckdb-inventory.sql"
FORECAST = ROOT / "workshop" / "duckdb-restock.csv"


def _private_file(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def reader_grants(conn) -> None:
    """Fail if the dedicated role has authority outside this optional example."""
    flags = conn.execute("SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolinherit "
                         "FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone()
    if flags != (False, False, False, False, False):
        raise ValueError("inventory reader has unexpected role flags")
    if conn.execute("SELECT 1 FROM pg_auth_members WHERE member = %s::regrole", (ROLE,)).fetchone():
        raise ValueError("inventory reader must have no role memberships")
    for table in ("product_catalog", "warehouse_inventory", "customers", "orders", "support_tickets",
                  "approvals", "store_credits", "tool_audit", "retrieval_receipts"):
        if conn.execute("SELECT has_table_privilege(%s, %s, %s)",
                        (ROLE, "pellier." + table, "SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER")).fetchone()[0]:
            raise ValueError("inventory reader has unexpected table privileges")
    # Column grants do not appear as table grants. Inspect every column in the
    # application schema so a pre-existing role cannot retain customer access.
    allowed = {("product_catalog", "productId"), ("product_catalog", "name"),
               ("warehouse_inventory", "product_id"), ("warehouse_inventory", "warehouse_code"),
               ("warehouse_inventory", "quantity")}
    columns = conn.execute(
        "SELECT c.relname, a.attname, has_column_privilege(%s, c.oid, a.attnum, 'SELECT'), "
        "has_column_privilege(%s, c.oid, a.attnum, 'INSERT,UPDATE,REFERENCES') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid "
        "WHERE n.nspname = 'pellier' AND c.relkind IN ('r','p','v','m','f') "
        "AND a.attnum > 0 AND NOT a.attisdropped", (ROLE, ROLE)).fetchall()
    if any(writes or (reads and (table, column) not in allowed) for table, column, reads, writes in columns):
        raise ValueError("inventory reader has unexpected column privileges")


def prepare_reader(conn, directory: Path, connection: dict) -> None:
    """Owner-only setup; the password is sent to PostgreSQL only as a SCRAM verifier."""
    from deploy.store_tools_login import scram_verifier
    from psycopg import sql

    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    password = secrets.token_hex(24)
    with conn.transaction():
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT NOBYPASSRLS").format(sql.Identifier(ROLE)))
        reader_grants(conn)
        conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} CONNECTION LIMIT 4").format(
            sql.Identifier(ROLE), sql.Literal(scram_verifier(password))))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA pellier TO {}").format(sql.Identifier(ROLE)))
        conn.execute(sql.SQL('GRANT SELECT ("productId", name) ON pellier.product_catalog TO {}').format(sql.Identifier(ROLE)))
        conn.execute(sql.SQL("GRANT SELECT (product_id, warehouse_code, quantity) "
                             "ON pellier.warehouse_inventory TO {}").format(sql.Identifier(ROLE)))
    # libpq reads a private passfile. Neither ATTACH nor its errors contain a password.
    passfile = directory / "reader.pgpass"
    escape = lambda value: str(value).replace("\\", "\\\\").replace(":", "\\:")
    _private_file(passfile, ":".join(escape(value) for value in (
        connection["host"], connection.get("port", 5432), connection["dbname"], ROLE, password)) + "\n")
    options = {key: value for key, value in connection.items() if key not in {"user", "password"}}
    options.update(user=ROLE, passfile=str(passfile.resolve()), connect_timeout=10)
    _private_file(directory / "reader.json", json.dumps(options))


def connect_duckdb(directory: Path):
    import duckdb
    from psycopg.conninfo import make_conninfo

    options = json.loads((directory / "reader.json").read_text())
    conn = duckdb.connect()
    try:
        conn.execute("INSTALL postgres")
        conn.execute("LOAD postgres")
        conn.execute("SET pg_pool_max_connections = 2")
        conn.execute("SET pg_statement_timeout_millis = 10000")
        dsn = make_conninfo(**options)
        conn.execute(f"ATTACH {_literal(dsn)} AS aurora (TYPE postgres, READ_ONLY, SCHEMA 'pellier')")
        return conn
    except Exception:
        conn.close()
        raise


def create_forecast(conn, directory: Path) -> None:
    # Training data, never inferred stock or a supplier commitment.
    conn.execute(f"COPY (SELECT * FROM read_csv({_literal(str(FORECAST))}, header=true, "
                 "columns={'product_id':'VARCHAR','warehouse_code':'VARCHAR',"
                 "'incoming_quantity':'INTEGER','expected_receipt_date':'DATE',"
                 "'forecast_as_of':'DATE'})) TO "
                 f"{_literal(str(directory / 'restock.parquet'))} (FORMAT PARQUET)")


def query(conn, directory: Path, *, explain: bool = False):
    sql = QUERY.read_text()
    result = conn.execute(("EXPLAIN ANALYZE " if explain else "") + sql,
                          {"restock_file": str(directory / "restock.parquet")})
    return [column[0] for column in result.description], result.fetchall()


def check_reader(directory: Path) -> None:
    """Check positive access and refusals through a direct PostgreSQL session too.

    READ_ONLY on a DuckDB attachment alone cannot establish database privileges.
    Even if a forbidden UPDATE is admitted, WHERE false prevents a data change.
    """
    import psycopg

    options = json.loads((directory / "reader.json").read_text())
    with psycopg.connect(**options, autocommit=True) as reader:
        actual = reader.execute("SELECT current_user").fetchone()[0]
        if actual != ROLE:
            raise ValueError("wrong inventory login")
        reader_grants(reader)
        stock = reader.execute("SELECT quantity FROM pellier.warehouse_inventory "
                               "WHERE product_id = '2' ORDER BY warehouse_code").fetchall()
        if len(stock) != 3:
            raise ValueError("expected three live warehouses for Hadley Linen Shirt")
        for statement in (
            "SELECT id FROM pellier.customers LIMIT 1",
            "SELECT id FROM pellier.orders LIMIT 1",
            "UPDATE pellier.warehouse_inventory SET quantity = quantity WHERE false",
            "SET ROLE pellier_credit_writer",
        ):
            try:
                reader.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                continue
            raise ValueError("inventory reader admitted a forbidden operation")
    with connect_duckdb(directory) as conn:
        _, rows = query(conn, directory)
        if len(rows) != 3 or [row[2] for row in rows] != [row[0] for row in stock]:
            raise ValueError("federated result does not match current PostgreSQL stock")
        if rows[-1][3] is not None:
            raise ValueError("a missing Portland forecast must remain NULL")


def owner_connection(directory: Path):
    """Workshop host or existing SSM tunnel, using the supplied DB configuration."""
    import psycopg
    import workshop_check

    cfg = workshop_check.db_config()
    if not cfg:
        raise ValueError("database settings missing")
    host = cfg.get("DB_TUNNEL_REMOTE_HOST") or cfg["DB_HOST"]
    options = {"host": host, "port": int(cfg.get("DB_PORT") or 5432),
               "dbname": cfg["DB_NAME"], "user": cfg["DB_USER"],
               "password": cfg.get("DB_PASSWORD") or "", "connect_timeout": 10}
    if cfg.get("DB_TUNNEL_REMOTE_HOST"):
        options["hostaddr"] = cfg["DB_HOST"]
    if not host.startswith("/"):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        certificate = directory / "rds-global-bundle.pem"
        if not certificate.is_file():
            with urllib.request.urlopen("https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem",
                                        timeout=20) as response:
                _private_file(certificate, response.read().decode())
        options.update(sslmode="verify-full", sslrootcert=str(certificate.resolve()))
    return psycopg.connect(**options, autocommit=True), options


def cleanup_reader(conn, directory: Path) -> None:
    from psycopg import sql

    with conn.transaction():
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone():
            if conn.execute("SELECT 1 FROM pg_shdepend WHERE refobjid = %s::regrole "
                            "AND deptype = 'o' LIMIT 1", (ROLE,)).fetchone():
                raise ValueError("inventory reader unexpectedly owns objects; cleanup stopped")
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(ROLE)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(ROLE)))
    for name in ("reader.json", "reader.pgpass", "restock.parquet", "rds-global-bundle.pem"):
        (directory / name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("operation", choices=("prepare", "query", "check", "cleanup"))
    parser.add_argument("--explain", action="store_true", help="show where the query runs")
    args = parser.parse_args()
    try:
        if args.operation in {"prepare", "cleanup"}:
            owner, options = owner_connection(LOCAL)
            with owner:
                if args.operation == "cleanup":
                    cleanup_reader(owner, LOCAL)
                    print("Removed the optional inventory login and its local files.")
                    return 0
                prepare_reader(owner, LOCAL, options)
            with connect_duckdb(LOCAL) as conn:
                create_forecast(conn, LOCAL)
            print("Prepared an inventory-only login and a training forecast in .local/duckdb.")
        elif args.operation == "check":
            check_reader(LOCAL)
            print("DuckDB check passed: live stock matches; missing forecast stays NULL; customer reads and writes are denied.")
        else:
            with connect_duckdb(LOCAL) as conn:
                columns, rows = query(conn, LOCAL, explain=args.explain)
                print(" | ".join(columns))
                for row in rows:
                    print(" | ".join("NULL" if value is None else str(value) for value in row))
            print("Forecast values are training data. They do not increase stock or establish a shipping date.")
        return 0
    except Exception as exc:
        # Driver errors can include connection details. Keep them off the terminal.
        print(f"Optional federation could not finish ({type(exc).__name__}). "
              "Run prepare on the workshop host, then retry. Check database access and extension downloads.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
