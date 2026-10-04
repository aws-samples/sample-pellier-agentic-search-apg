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
    paid = "SELECT amount_paid_cents FROM pellier.orders WHERE customer_id='CUST-JESSICA' AND product_id='42'"
    original_price = fresh_db.psql("""SELECT price FROM pellier.product_catalog WHERE "productId" = '42'""")
    before = fresh_db.psql(paid)
    try:
        updated = fresh_db.psql(
            """UPDATE pellier.product_catalog SET price = 99 WHERE "productId" = '42' RETURNING "productId" """
        )
        after = fresh_db.psql(paid)
    finally:
        fresh_db.psql(
            f"""UPDATE pellier.product_catalog SET price = {original_price} WHERE "productId" = '42'"""
        )
    assert updated.splitlines() == ["42", "UPDATE 1"]
    assert before == after == "6400"


def test_exactly_four_clients_and_the_anonymous_profile(fresh_db):
    ids = set(fresh_db.psql("SELECT id FROM pellier.customers").split("\n"))
    assert ids == {"CUST-MARCO", "CUST-ANNA", "CUST-THEO", "CUST-JESSICA", "CUST-FRESH", "theo"}


def test_spend_is_computed_not_stored(fresh_db):
    assert fresh_db.psql(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema='pellier' "
        "AND table_name='customers' AND column_name='spend_12mo'") == "0"


def test_tickets_tell_theo_and_jessica_stories(fresh_db):
    rows = fresh_db.psql("SELECT ticket_id, customer_id, status FROM pellier.support_tickets ORDER BY ticket_id")
    assert rows.split("\n") == [
        "TKT-2026-1874|CUST-THEO|resolved",
        "TKT-2026-3015|CUST-JESSICA|open",
        "TKT-2026-5021|CUST-THEO|open",
    ]
    assert fresh_db.psql("SELECT count(*) FROM pellier.store_credits") == "0"


def test_reset_restores_the_same_people_and_tickets(fresh_db):
    run_reset(fresh_db)
    test_exactly_four_clients_and_the_anonymous_profile(fresh_db)
    test_tickets_tell_theo_and_jessica_stories(fresh_db)


WAREHOUSE_FIXTURES = {
    "2": {"BK-01": 0, "ATX-02": 6, "PDX-01": 14},
    "14": {"BK-01": 3, "ATX-02": 2, "PDX-01": 0},
    "43": {"BK-01": 0, "ATX-02": 0, "PDX-01": 0},
    "79": {"BK-01": 0, "ATX-02": 0, "PDX-01": 0},
}


def test_three_rows_per_product_and_no_drift(fresh_db):
    assert fresh_db.psql("SELECT count(*) FROM pellier.warehouse_inventory") == "300"
    assert fresh_db.psql("""
        SELECT count(*) FROM pellier.product_catalog pc
         WHERE pc.quantity <> (SELECT COALESCE(sum(quantity),0) FROM pellier.warehouse_inventory wi
                                WHERE wi.product_id = pc."productId")""") == "0"


def test_teaching_products_have_exact_stock(fresh_db):
    for pid, expected in WAREHOUSE_FIXTURES.items():
        rows = fresh_db.psql(
            f"SELECT warehouse_id, quantity FROM pellier.warehouse_inventory "
            f"WHERE product_id = '{pid}'")
        actual = dict(line.split("|") for line in rows.split("\n"))
        assert actual == {k: str(v) for k, v in expected.items()}, pid


def test_low_stock_list_is_real(fresh_db):
    low = fresh_db.psql("""SELECT string_agg("productId", ',' ORDER BY "productId"::int)
                             FROM pellier.product_catalog WHERE quantity <= 10""")
    assert low == "12,14,20,43,79"


def test_stock_shape_differs_between_warehouses(fresh_db):
    leaders = fresh_db.psql("""
        SELECT count(DISTINCT warehouse_id) FROM (
          SELECT DISTINCT ON (product_id) product_id, warehouse_id
            FROM pellier.warehouse_inventory
           WHERE product_id NOT IN ('2','14','43','79')
           ORDER BY product_id, quantity DESC, warehouse_id) t""")
    assert leaders == "3"


def test_every_seeded_stock_movement_carries_the_seed_reason(fresh_db):
    assert fresh_db.psql(
        "SELECT count(*) FROM pellier.inventory_ledger WHERE reason <> 'seed'") == "0"


def test_reset_keeps_the_warehouse_matrix(fresh_db):
    run_reset(fresh_db)
    test_three_rows_per_product_and_no_drift(fresh_db)
    test_teaching_products_have_exact_stock(fresh_db)
    test_low_stock_list_is_real(fresh_db)
    test_every_seeded_stock_movement_carries_the_seed_reason(fresh_db)
