"""The aurora_analytics reader on real PostgreSQL: its grants, its refusals and its removal.

Local PostgreSQL has no aurora_analytics extension, so a do-nothing foreign-data wrapper stands
in for its server, and lake.daily_sales and lake.deliveries are foreign tables on it. Reading
them needs Aurora; everything about who may read, write or change them is PostgreSQL's own and
runs here against the workshop's real schema and roles.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sys

import psycopg
from psycopg import sql
import pytest

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
analytics = importlib.import_module("aurora_analytics")


def _owner(cluster) -> psycopg.Connection:
    return psycopg.connect(host=str(cluster.socket), dbname=cluster.database, user="postgres",
                           autocommit=True)


@pytest.fixture
def state(tmp_path):
    return analytics.SetupRecord(tmp_path / "setup.json", "test-target", "test-run", {})


@pytest.fixture
def lake(fresh_db, tmp_path: Path, state):  # noqa: F811  (fixture)
    with _owner(fresh_db) as conn:
        conn.execute("CREATE FOREIGN DATA WRAPPER lake_stand_in")
        conn.execute("CREATE SERVER aurora_analytics_server FOREIGN DATA WRAPPER lake_stand_in")
        conn.execute("CREATE SCHEMA lake")
        conn.execute("CREATE FOREIGN TABLE lake.daily_sales (product_id text, warehouse_code text,"
                     " sale_date date, units_sold int) SERVER aurora_analytics_server")
        conn.execute("CREATE FOREIGN TABLE lake.deliveries (product_id text, warehouse_code text,"
                     " arrives_in_days int, units int) SERVER aurora_analytics_server")
        connection = {"host": str(fresh_db.socket), "dbname": fresh_db.database}
        for name in ("lake", "lake.daily_sales", "lake.deliveries"):
            state.record(name, analytics._oid(conn, name))
        analytics.prepare_reader(conn, tmp_path, connection, state)
    yield fresh_db
    # A test may have granted the reader more, which DROP ROLE rightly refuses; the local
    # superuser can drop whatever is left, so the next test starts clean.
    with _owner(fresh_db) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                        (analytics.ROLE,)).fetchone():
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(analytics.ROLE)))
        analytics.drop_lake_objects(conn, state)
        conn.execute("DROP SCHEMA IF EXISTS lake CASCADE")  # disposable test database
        conn.execute("DROP SERVER IF EXISTS aurora_analytics_server CASCADE")
        conn.execute("DROP FOREIGN DATA WRAPPER IF EXISTS lake_stand_in")


def _reader(cluster) -> psycopg.Connection:
    return psycopg.connect(host=str(cluster.socket), dbname=cluster.database,
                           user=analytics.ROLE, autocommit=True)


def test_the_reader_reads_only_stock_and_names_and_passes_its_audit(lake) -> None:
    with _reader(lake) as reader:
        analytics.reader_grants(reader)
        assert reader.execute("SELECT quantity FROM pellier.warehouse_inventory "
                              "WHERE product_id = '2' ORDER BY warehouse_code").fetchall() == [
            (6,), (0,), (14,)]
        assert reader.execute("SELECT name FROM pellier.product_catalog "
                              "WHERE \"productId\" = '2'").fetchone() == ("Hadley Linen Shirt",)


@pytest.mark.parametrize("statement", analytics.REFUSALS)
def test_the_reader_is_refused_each_forbidden_operation(lake, statement: str) -> None:
    with _reader(lake) as reader, pytest.raises(psycopg.errors.InsufficientPrivilege):
        reader.execute(statement)


@pytest.mark.parametrize("extra", [
    "GRANT SELECT ON pellier.customers TO {}",
    "GRANT UPDATE (quantity) ON pellier.warehouse_inventory TO {}",
    "GRANT CREATE ON SCHEMA pellier TO {}",
    "GRANT CREATE ON SCHEMA lake TO {}",
    "GRANT CREATE ON DATABASE postgres TO {}",
    "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pellier TO {}",
    "GRANT pellier_credit_writer TO {}",
    "ALTER ROLE {} INHERIT",
    "ALTER ROLE {} SET search_path = pellier",
])
def test_the_audit_refuses_a_reader_with_any_extra_authority(lake, extra: str) -> None:
    with _owner(lake) as conn:
        conn.execute(sql.SQL(extra).format(sql.Identifier(analytics.ROLE)))
        with pytest.raises(analytics.AnalyticsError, match="keep this message and ask a "
                                                           "facilitator"):
            analytics.reader_grants(conn)


def test_dropping_the_lake_objects_removes_the_login_and_runs_again(lake, state) -> None:
    with _owner(lake) as conn:
        analytics.drop_lake_objects(conn, state)
        analytics.drop_lake_objects(conn, state)
        assert conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                            (analytics.ROLE,)).fetchone() is None
        assert conn.execute("SELECT to_regnamespace('lake')").fetchone() == (None,)


def test_cleanup_keeps_an_unrelated_table_in_lake(lake, state) -> None:
    with _owner(lake) as conn:
        conn.execute("CREATE TABLE lake.keep_me (n integer)")
        conn.execute("INSERT INTO lake.keep_me VALUES (42)")
        analytics.drop_lake_objects(conn, state)
        assert conn.execute("SELECT n FROM lake.keep_me").fetchone() == (42,)

def test_a_reused_schema_survives_even_when_empty(lake, state) -> None:
    state.resources.pop("lake")
    with _owner(lake) as conn:
        analytics.drop_lake_objects(conn, state)
        assert conn.execute("SELECT to_regnamespace('lake')::text").fetchone() == ("lake",)


def test_prepare_refuses_to_replace_an_unrelated_foreign_table_or_login(lake, state, tmp_path):
    unrelated = analytics.SetupRecord(tmp_path / "other.json", "another", "other-run", {})
    with _owner(lake) as conn:
        original = analytics._oid(conn, "lake.daily_sales")
        with pytest.raises(analytics.AnalyticsError, match="lake.daily_sales already exists"):
            analytics._create_tables(conn, "bucket", "us-west-2", unrelated)
        assert analytics._oid(conn, "lake.daily_sales") == original
        password = conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s",
                                (analytics.ROLE,)).fetchone()
        with pytest.raises(analytics.AnalyticsError, match="already exists"):
            analytics.prepare_reader(conn, tmp_path, {}, unrelated)
        assert conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s",
                            (analytics.ROLE,)).fetchone() == password
        analytics.drop_lake_objects(conn, unrelated)
        assert analytics._oid(conn, "lake.daily_sales") == original


def test_a_same_name_replacement_is_kept_after_prepare(lake, state):
    with _owner(lake) as conn:
        conn.execute("DROP FOREIGN TABLE lake.deliveries")
        conn.execute("CREATE TABLE lake.deliveries (important text)")
        assert analytics.drop_lake_objects(conn, state)
        assert conn.execute("SELECT important FROM lake.deliveries").fetchall() == []


def test_prepare_rerun_and_cleanup_on_a_shared_target(fresh_db, tmp_path, monkeypatch):
    """Drive the participant entry points twice, against local PostgreSQL and AWS fakes."""
    import boto3
    from tests.test_aurora_analytics import FakeRds, FakeS3, ROLE_ARN

    cfg = {"AWS_REGION": "us-east-1", "DB_CLUSTER_ARN": "test-cluster", "CLUSTER_ID": "test",
           "ACCOUNT": "owner", "BUCKET": "bucket", "AURORA_ANALYTICS_ROLE_ARN": ROLE_ARN,
           "DB_NAME": fresh_db.database}
    connection = {"host": str(fresh_db.socket), "dbname": fresh_db.database}
    s3, rds = FakeS3(exists=True), FakeRds()
    s3.objects["lake/shared/sales.parquet"] = "other-data"
    rds.status = "ACTIVE"
    monkeypatch.setattr(boto3, "client", lambda name, **kwargs: {"s3": s3, "rds": rds}[name])
    monkeypatch.setattr(analytics, "LOCAL", tmp_path)
    monkeypatch.setattr(analytics, "owner_connection", lambda *_: (_owner(fresh_db), connection))
    # Aurora supplies the extension. PostgreSQL supplies every ownership and grant check.
    original_oid = analytics._oid
    monkeypatch.setattr(analytics, "_oid", lambda conn, name: 42 if name == "aurora_analytics"
                        else original_oid(conn, name))
    with _owner(fresh_db) as conn:
        conn.execute("CREATE FOREIGN DATA WRAPPER lake_stand_in")
        conn.execute("CREATE SERVER aurora_analytics_server FOREIGN DATA WRAPPER lake_stand_in")
        conn.execute("CREATE SCHEMA lake")
        conn.execute("CREATE TABLE lake.other_reports (n integer)")
    try:
        analytics.prepare(cfg)
        analytics.prepare(cfg)
        assert len(s3.objects) == 6
        with analytics.reader_connection(tmp_path) as reader:
            analytics.reader_grants(reader)
        assert analytics.cleanup(cfg, tmp_path) == (
            "Cleaned up this analytics run. Shared resources were kept.")
        assert analytics.cleanup(cfg, tmp_path).startswith("No setup record")
        assert s3.objects == {"lake/shared/sales.parquet": "other-data"}
        assert rds.status == "ACTIVE" and rds.removals == 0
        assert not (tmp_path / "reader.pgpass").exists()
        with _owner(fresh_db) as conn:
            assert original_oid(conn, "lake.other_reports")
            assert original_oid(conn, "lake.deliveries") is None
            assert original_oid(conn, analytics.ROLE) is None
    finally:
        with _owner(fresh_db) as conn:
            conn.execute("DROP SCHEMA lake CASCADE")
            conn.execute("DROP SERVER aurora_analytics_server CASCADE")
            conn.execute("DROP FOREIGN DATA WRAPPER lake_stand_in")
            if original_oid(conn, analytics.ROLE):
                conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(analytics.ROLE)))
                conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(analytics.ROLE)))
