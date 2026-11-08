"""Run with DuckDB's optional dependencies; no workshop account is used.

uv run --no-project --with duckdb==2.0.0 --with 'psycopg[binary]==3.3.4' --with pytest==9.1.1 \
    python -m pytest -q optional-tests/test_duckdb_federation.py
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import duckdb_federation as federation

spec = importlib.util.spec_from_file_location("federation_cluster", ROOT / "pellier/backend/tests/fresh_cluster.py")
cluster_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cluster_module
spec.loader.exec_module(cluster_module)


@pytest.fixture
def database(tmp_path):
    server = tmp_path / "server"
    server.mkdir()
    cluster = cluster_module.start_cluster(server)
    try:
        options = {"host": str(cluster.socket), "dbname": "postgres", "user": "postgres"}
        with psycopg.connect(**options, autocommit=True) as conn:
            conn.execute('CREATE SCHEMA pellier')
            conn.execute('CREATE TABLE pellier.product_catalog ("productId" text PRIMARY KEY, name text)')
            conn.execute("CREATE TABLE pellier.warehouse_inventory (product_id text, warehouse_code text, quantity int)")
            conn.execute("INSERT INTO pellier.product_catalog VALUES ('2', 'Hadley Linen Shirt')")
            conn.execute("INSERT INTO pellier.warehouse_inventory VALUES ('2', 'ATX-02', 6), ('2', 'BK-01', 0), ('2', 'PDX-01', 14)")
            for table in ("customers", "orders", "support_tickets", "approvals", "store_credits", "tool_audit", "retrieval_receipts"):
                conn.execute(f"CREATE TABLE pellier.{table} (id int)")
                conn.execute(f"INSERT INTO pellier.{table} VALUES (1)")
            conn.execute("CREATE ROLE pellier_credit_writer NOLOGIN")
            yield conn, options, tmp_path / "client"
    finally:
        cluster.stop()


def test_live_join_keeps_forecast_separate_and_checks_real_permissions(database):
    owner, options, directory = database
    federation.prepare_reader(owner, directory, options)
    assert (directory / "reader.pgpass").stat().st_mode & 0o777 == 0o600
    with federation.connect_duckdb(directory) as conn:
        federation.create_forecast(conn, directory)
        direct = conn.execute("SELECT * FROM postgres_query('aurora', 'SELECT p.name, w.warehouse_code, w.quantity "
                              'FROM pellier.warehouse_inventory w JOIN pellier.product_catalog p ON p."productId" = w.product_id '
                              "WHERE w.product_id = ''2'' ORDER BY w.warehouse_code')").fetchall()
        assert direct == [("Hadley Linen Shirt", "ATX-02", 6), ("Hadley Linen Shirt", "BK-01", 0),
                          ("Hadley Linen Shirt", "PDX-01", 14)]
        columns, rows = federation.query(conn, directory)
        assert columns[:4] == ["name", "warehouse_code", "current_stock", "forecast_incoming"]
        assert [(row[1], row[2], row[3]) for row in rows] == [
            ("ATX-02", 6, 25), ("BK-01", 0, 12), ("PDX-01", 14, None)]
        _, plan = federation.query(conn, directory, explain=True)
        assert "POSTGRES_QUERY" in str(plan).upper()
        # Current stock is read again, not frozen in the Parquet forecast.
        owner.execute("UPDATE pellier.warehouse_inventory SET quantity = 7 WHERE warehouse_code = 'ATX-02'")
        assert federation.query(conn, directory)[1][0][2] == 7
    federation.check_reader(directory)
    assert owner.execute("SELECT count(*) FROM pellier.orders").fetchone()[0] == 1
    # Prepare is repeatable after an interrupted session and replaces local credentials.
    federation.prepare_reader(owner, directory, options)
    federation.check_reader(directory)
    federation.cleanup_reader(owner, directory)
    federation.cleanup_reader(owner, directory)
    assert owner.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (federation.ROLE,)).fetchone() is None
    assert not (directory / "reader.pgpass").exists()


@pytest.mark.parametrize("grant, expected", [
    ("SELECT ON pellier.orders", "table"),
    ("SELECT ON pellier.product_catalog", "table"),
    ("SELECT (id) ON pellier.customers", "column"),
    ("UPDATE (quantity) ON pellier.warehouse_inventory", "column"),
])
def test_preexisting_role_with_excess_authority_is_refused(database, grant, expected):
    owner, options, directory = database
    owner.execute(f"CREATE ROLE {federation.ROLE} NOINHERIT NOBYPASSRLS")
    owner.execute(f"GRANT {grant} TO {federation.ROLE}")
    with pytest.raises(ValueError, match=f"unexpected {expected} privileges"):
        federation.prepare_reader(owner, directory, options)
    assert not (directory / "reader.pgpass").exists()
