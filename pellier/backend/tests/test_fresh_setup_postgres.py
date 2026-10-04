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


def test_every_order_has_an_explicit_amount(fresh_db):
    assert fresh_db.psql("SELECT count(*) FROM pellier.orders WHERE amount_paid_cents IS NULL") == "0"
    assert fresh_db.psql(
        "SELECT amount_paid_cents FROM pellier.orders WHERE customer_id='CUST-JESSICA' AND product_id='42'"
    ) == "6400"


def test_repricing_never_rewrites_history(fresh_db):
    before = fresh_db.psql("SELECT amount_paid_cents FROM pellier.orders WHERE customer_id='CUST-JESSICA' AND product_id='42'")
    fresh_db.psql("""BEGIN; UPDATE pellier.product_catalog SET price = 99 WHERE "productId" = '42'; COMMIT;""")
    after = fresh_db.psql("SELECT amount_paid_cents FROM pellier.orders WHERE customer_id='CUST-JESSICA' AND product_id='42'")
    fresh_db.psql("""UPDATE pellier.product_catalog SET price = 64 WHERE "productId" = '42'""")
    assert before == after == "6400"
