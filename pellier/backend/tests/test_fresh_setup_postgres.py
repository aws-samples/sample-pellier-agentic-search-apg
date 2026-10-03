"""Fresh setup and reset on real PostgreSQL produce the workshop dataset."""
from tests.fresh_cluster import fresh_db, run_reset  # noqa: F401  (fixture import)


def test_fresh_setup_completes_and_seeds_the_catalog(fresh_db):
    assert int(fresh_db.psql("SELECT count(*) FROM pellier.product_catalog")) > 0


def test_reset_runs_on_a_set_up_database(fresh_db):
    run_reset(fresh_db)
    assert int(fresh_db.psql("SELECT count(*) FROM pellier.product_catalog")) > 0


def test_no_archive_rows_after_setup(fresh_db):
    assert fresh_db.psql("SELECT count(*) FROM pellier.product_catalog WHERE tags @> '[\"archive\"]'") == "0"
    assert fresh_db.psql("SELECT count(*) FROM pellier.product_catalog") == "100"
