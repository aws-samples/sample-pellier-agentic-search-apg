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
def lake(fresh_db, tmp_path: Path):  # noqa: F811  (fixture)
    with _owner(fresh_db) as conn:
        conn.execute("CREATE FOREIGN DATA WRAPPER lake_stand_in")
        conn.execute("CREATE SERVER aurora_analytics_server FOREIGN DATA WRAPPER lake_stand_in")
        conn.execute("CREATE SCHEMA lake")
        conn.execute("CREATE FOREIGN TABLE lake.daily_sales (product_id text, warehouse_code text,"
                     " sale_date date, units_sold int) SERVER aurora_analytics_server")
        conn.execute("CREATE FOREIGN TABLE lake.deliveries (product_id text, warehouse_code text,"
                     " arrives_in_days int, units int) SERVER aurora_analytics_server")
        connection = {"host": str(fresh_db.socket), "dbname": fresh_db.database}
        analytics.prepare_reader(conn, tmp_path, connection)
    yield fresh_db
    # A test may have granted the reader more, which DROP ROLE rightly refuses; the local
    # superuser can drop whatever is left, so the next test starts clean.
    with _owner(fresh_db) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                        (analytics.ROLE,)).fetchone():
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(analytics.ROLE)))
        analytics.drop_lake_objects(conn)
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


def test_dropping_the_lake_objects_removes_the_login_and_runs_again(lake) -> None:
    with _owner(lake) as conn:
        analytics.drop_lake_objects(conn)
        analytics.drop_lake_objects(conn)
        assert conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                            (analytics.ROLE,)).fetchone() is None
        assert conn.execute("SELECT to_regnamespace('lake')").fetchone() == (None,)
