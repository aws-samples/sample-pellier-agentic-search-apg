"""Each cluster copy must isolate cluster-wide roles and database-local tables."""

import pytest

from tests import fresh_cluster


def test_cluster_copies_isolate_roles_and_tables(request: pytest.FixtureRequest) -> None:
    objects_exist = (
        "SELECT to_regrole('copy_probe_role') IS NOT NULL, "
        "to_regclass('public.copy_probe_table') IS NOT NULL"
    )
    with fresh_cluster.fresh_db_copy(request.session) as first:
        first.psql("CREATE ROLE copy_probe_role; CREATE TABLE public.copy_probe_table (id integer)")
        assert first.psql(objects_exist) == "t|t"
        with fresh_cluster.fresh_db_copy(request.session) as second:
            assert second.psql(objects_exist) == "f|f"
