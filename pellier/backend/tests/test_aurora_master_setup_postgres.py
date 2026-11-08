"""Setup and reset run as Aurora's master user, which is not a superuser.

Every other fresh-cluster test builds the database as ``postgres``, a superuser, so a
statement only a superuser may run passes there and fails on Aurora. The 2026-11-08 test
event stopped that way: ``ALTER ROLE ... NOSUPERUSER`` is refused to a non-superuser even
when it changes nothing.

The stand-in login has what Aurora's master user had on that event (no SUPERUSER,
CREATEROLE, CREATEDB, and the owner of the ``pellier`` database), plus BYPASSRLS. Aurora's
``rds_superuser`` lets the master create a BYPASSRLS role without holding the attribute;
vanilla PostgreSQL requires it. The superuser creates the two untrusted extensions first,
as ``rds_superuser`` may on Aurora.
"""
import dataclasses
import tempfile
from pathlib import Path

from tests.fresh_cluster import run_reset, run_setup, start_cluster

MASTER = "pellier_master"


def test_setup_and_reset_run_as_a_master_user_that_is_not_a_superuser():
    with tempfile.TemporaryDirectory(prefix="pellier-master-") as tmp:
        cluster = start_cluster(Path(tmp))
        try:
            cluster.psql(f"CREATE ROLE {MASTER} LOGIN NOSUPERUSER CREATEROLE CREATEDB "
                         "BYPASSRLS")
            cluster.psql(f"CREATE DATABASE pellier OWNER {MASTER}")
            dataclasses.replace(cluster, database="pellier").psql(
                "CREATE EXTENSION vector; "
                "CREATE EXTENSION pg_stat_statements WITH SCHEMA public")
            master = dataclasses.replace(cluster, user=MASTER, database="pellier")

            run_setup(master)
            # Reset drops the schema but keeps the roles, so the role blocks run again
            # against roles that already exist, as the provisioner's upgrade does.
            run_reset(master)

            assert master.psql(
                "SELECT rolname || ' ' || rolsuper || ' ' || rolbypassrls || ' ' "
                "|| rolcreaterole || ' ' || rolcreatedb || ' ' || rolinherit "
                "FROM pg_roles WHERE rolname = 'pellier_operator_tools'"
            ) == "pellier_operator_tools false false false false false"
            assert master.psql(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'pellier'") == "10"
        finally:
            cluster.stop()
