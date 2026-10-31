"""The baseline schema and seed, built from nothing on real PostgreSQL.

`tests/fresh_cluster.py` runs `scripts/setup/database-setup.sh` (schema, catalog,
seed) and `database-reset.sh` (drop and rebuild) against a throwaway PostgreSQL
18 cluster with pgvector, so these tests prove the commands bootstrap and reset
run.
"""
import re
import subprocess
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.conftest import SEED_CUSTOMER_USERNAMES
from tests.fresh_cluster import fresh_db, run_reset  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]

TEN_TABLES = [
    "approvals", "customers", "orders", "product_catalog", "retrieval_receipts",
    "return_policies", "store_credits", "support_tickets", "tool_audit", "warehouse_inventory",
]


def _rows(cluster, sql: str) -> list[str]:
    out = cluster.psql(sql)
    return out.split("\n") if out else []


def _connect(cluster) -> psycopg.Connection:
    return psycopg.connect(host=str(cluster.socket), port=5432, user="postgres",
                           dbname="postgres", autocommit=True, row_factory=dict_row)


# ---------------------------------------------------------------------------
# The shape: ten tables and nothing else
# ---------------------------------------------------------------------------


def test_the_schema_is_exactly_the_ten_tables(fresh_db):
    assert _rows(fresh_db, "SELECT tablename FROM pg_tables WHERE schemaname = 'pellier' "
                           "ORDER BY tablename") == TEN_TABLES
    assert fresh_db.psql("SELECT count(*) FROM pg_views WHERE schemaname = 'pellier'") == "0"


def test_the_objects_beside_the_tables_are_few_and_named(fresh_db):
    assert _rows(fresh_db, "SELECT p.proname FROM pg_proc p JOIN pg_namespace n "
                           "ON n.oid = p.pronamespace WHERE n.nspname = 'pellier' "
                           "ORDER BY 1") == [
        "check_stock", "give_store_credit", "retrieval_receipts_append_only",
        "set_updated_at",
        "store_credits_require_approval", "tool_audit_fill_once",
    ]
    assert _rows(fresh_db, "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                           "JOIN pg_namespace n ON n.oid = c.relnamespace "
                           "WHERE n.nspname = 'pellier' AND NOT t.tgisinternal ORDER BY 1") == [
        "product_catalog_set_updated_at", "retrieval_receipts_append_only",
        "store_credits_require_approval", "tool_audit_fill_once",
    ]
    assert _rows(fresh_db, "SELECT tablename || '.' || policyname FROM pg_policies "
                           "WHERE schemaname = 'pellier' ORDER BY 1") == [
        "orders.orders_own_rows", "support_tickets.support_tickets_own_rows",
    ]
    assert _rows(fresh_db, "SELECT rolname FROM pg_roles WHERE rolname LIKE 'pellier%' "
                           "ORDER BY 1") == ["pellier_agent", "pellier_credit_writer"]
    # This cluster has no pgAudit library, so the schema built without the extension.
    assert _rows(fresh_db, "SELECT extname FROM pg_extension ORDER BY 1") == [
        "pg_stat_statements", "pg_trgm", "plpgsql", "vector",
    ]


def test_there_are_two_migration_files(fresh_db):
    names = sorted(p.name for p in (REPO / "scripts" / "migrations").glob("*.sql"))
    assert names == ["001_schema.sql", "002_seed.sql"]


def test_the_seed_runs_after_the_schema_and_the_catalog():
    """A seed that ran before the schema once broke a fresh deploy; the order is fixed."""
    setup = (REPO / "scripts" / "setup" / "database-setup.sh").read_text()
    schema = setup.index("apply 001_schema.sql")
    catalog = setup.index("scripts/seed_pellier_catalog.py --from-cache")
    seed = setup.index("apply 002_seed.sql")
    assert schema < catalog < seed


# ---------------------------------------------------------------------------
# The seed
# ---------------------------------------------------------------------------


def test_a_product_without_a_photograph_stores_no_image_url(fresh_db):
    """The column's own IS NOT NULL test and the storefront rule keep the same 1,000 rows."""
    assert fresh_db.psql('SELECT count(*) FROM pellier.product_catalog '
                         'WHERE "imgUrl" = \'\'') == "0"
    assert fresh_db.psql('SELECT count(*) FROM pellier.product_catalog '
                         'WHERE "imgUrl" IS NOT NULL') == "1000"
    assert fresh_db.psql("SELECT count(*) FROM pellier.product_catalog "
                         "WHERE NULLIF(btrim(\"imgUrl\"), '') IS NOT NULL") == "1000"


def test_the_catalog_is_fifty_thousand_products_with_embeddings(fresh_db):
    assert fresh_db.psql("SELECT count(*) FROM pellier.product_catalog") == "50000"
    assert fresh_db.psql("SELECT count(*) FROM pellier.product_catalog "
                         "WHERE embedding IS NULL OR description_tsv IS NULL") == "0"
    assert fresh_db.psql("SELECT count(*) FROM pellier.product_catalog "
                         "WHERE tags @> '[\"archive\"]'") == "0"


def test_the_customers_are_the_four_shoppers_exactly(fresh_db):
    rows = _rows(fresh_db, "SELECT id || '|' || cognito_username FROM pellier.customers ORDER BY id")
    assert rows == sorted(f"{customer}|{name}" for name, customer in SEED_CUSTOMER_USERNAMES.items())
    for row in rows:
        assert re.fullmatch(r"CUST-[A-Z]+\|[a-z]+", row), row


def test_no_customer_id_outside_the_pattern_can_be_written(fresh_db):
    with pytest.raises(AssertionError, match="customers_id_check"):
        fresh_db.psql("INSERT INTO pellier.customers (id, name, cognito_username) "
                      "VALUES ('theo', 'Theo', 'theo-alias')")


@pytest.mark.parametrize("username", ["", "Theo", "theo smith"])
def test_a_sign_in_name_is_lowercase_and_never_empty(fresh_db, username):
    """An unbound session names '' and the binding lowercases, so neither can match a row."""
    with pytest.raises(AssertionError, match="customers_cognito_username_check"):
        fresh_db.psql("INSERT INTO pellier.customers (id, name, cognito_username) "
                      f"VALUES ('CUST-ZED', 'Zed', '{username}')")


def test_jessicas_case_is_exactly_one_hundred_dollars_and_nothing_is_credited(fresh_db):
    returned = _rows(fresh_db, """
        SELECT p.name || '|' || o.amount_paid_cents FROM pellier.orders o
          JOIN pellier.product_catalog p ON p."productId" = o.product_id
         WHERE o.customer_id = 'CUST-JESSICA' AND o.return_status = 'received'
         ORDER BY o.id""")
    assert returned == ["Waffle Bath Robe, Sage|6400", "Reed Diffuser|3600"]
    assert fresh_db.psql("SELECT count(*) FROM pellier.store_credits") == "0"
    assert fresh_db.psql("SELECT count(*) FROM pellier.approvals") == "0"
    assert fresh_db.psql("SELECT count(*) FROM pellier.orders WHERE store_credit_id IS NOT NULL") == "0"
    ticket = fresh_db.psql("SELECT last_note FROM pellier.support_tickets "
                           "WHERE ticket_id = 'TKT-2026-3015'")
    assert "Waffle Bath Robe, Sage" in ticket and "Reed Diffuser" in ticket


def test_theo_and_jessica_ship_to_one_home(fresh_db):
    homes = _rows(fresh_db, "SELECT customer_id || '|' || string_agg(DISTINCT ship_to, ';') "
                            "FROM pellier.orders GROUP BY customer_id ORDER BY customer_id")
    by_customer = dict(row.split("|") for row in homes)
    assert by_customer["CUST-THEO"] == by_customer["CUST-JESSICA"]
    assert ";" not in by_customer["CUST-THEO"]
    assert by_customer["CUST-MARCO"] != by_customer["CUST-THEO"]


def test_the_tickets_tell_theo_and_jessicas_stories(fresh_db):
    assert _rows(fresh_db, "SELECT ticket_id || '|' || customer_id || '|' || status "
                           "FROM pellier.support_tickets ORDER BY ticket_id") == [
        "TKT-2026-1874|CUST-THEO|resolved",
        "TKT-2026-3015|CUST-JESSICA|open",
        "TKT-2026-5021|CUST-THEO|open",
    ]
    assert "Wabi-Sabi Bowl" in fresh_db.psql(
        "SELECT p.name FROM pellier.orders o JOIN pellier.product_catalog p "
        "ON p.\"productId\" = o.product_id WHERE o.customer_id = 'CUST-THEO' AND o.product_id = '37'")


def test_repricing_never_rewrites_what_an_order_paid(fresh_db):
    paid = ("SELECT amount_paid_cents FROM pellier.orders "
            "WHERE customer_id = 'CUST-JESSICA' AND product_id = '42'")
    original = fresh_db.psql("""SELECT price FROM pellier.product_catalog WHERE "productId" = '42'""")
    try:
        fresh_db.psql("""UPDATE pellier.product_catalog SET price = 99 WHERE "productId" = '42'""")
        assert fresh_db.psql(paid) == "6400"
    finally:
        fresh_db.psql(f"""UPDATE pellier.product_catalog SET price = {original} WHERE "productId" = '42'""")


WAREHOUSE_FIXTURES = {
    "2": {"BK-01": 0, "ATX-02": 6, "PDX-01": 14},
    "14": {"BK-01": 3, "ATX-02": 2, "PDX-01": 0},
    "43": {"BK-01": 0, "ATX-02": 0, "PDX-01": 0},
    "79": {"BK-01": 0, "ATX-02": 0, "PDX-01": 0},
}


def test_three_rows_per_product_and_the_catalog_agrees(fresh_db):
    assert fresh_db.psql("SELECT count(*) FROM pellier.warehouse_inventory") == "150000"
    assert fresh_db.psql("""
        SELECT count(*) FROM pellier.product_catalog pc
         WHERE pc.quantity <> (SELECT COALESCE(sum(quantity), 0) FROM pellier.warehouse_inventory wi
                                WHERE wi.product_id = pc."productId")""") == "0"
    assert _rows(fresh_db, "SELECT DISTINCT warehouse_code || '|' || warehouse_name || '|' || city "
                           "|| '|' || ship_window_min || '-' || ship_window_max "
                           "FROM pellier.warehouse_inventory ORDER BY 1") == [
        "ATX-02|Austin|Austin, TX|2-4",
        "BK-01|Brooklyn|Brooklyn, NY|1-2",
        "PDX-01|Portland|Portland, OR|3-5",
    ]


def test_teaching_products_have_exact_stock(fresh_db):
    for pid, expected in WAREHOUSE_FIXTURES.items():
        rows = fresh_db.psql("SELECT warehouse_code, quantity FROM pellier.warehouse_inventory "
                             f"WHERE product_id = '{pid}'")
        actual = dict(line.split("|") for line in rows.split("\n"))
        assert actual == {k: str(v) for k, v in expected.items()}, pid


def test_low_stock_list_is_real(fresh_db):
    assert fresh_db.psql("""SELECT string_agg("productId", ',' ORDER BY "productId"::int)
                              FROM pellier.product_catalog
                             WHERE quantity <= 10 AND "productId"::int <= 100""") == "12,14,20,43,79"
    # The larger assortment also contains low-stock and sold-out pieces.
    assert int(fresh_db.psql("""SELECT count(*) FROM pellier.product_catalog
                               WHERE quantity BETWEEN 1 AND 10
                                 AND "productId"::int > 100""")) > 0


# ---------------------------------------------------------------------------
# The guarantees the database itself keeps
# ---------------------------------------------------------------------------


def _as_agent(conn: psycopg.Connection, username: str, sql: str) -> list[dict]:
    with conn.transaction(force_rollback=True):
        conn.execute("SET LOCAL ROLE pellier_agent")
        conn.execute("SELECT set_config('pellier.principal_username', %s, true)", (username,))
        return conn.execute(sql).fetchall()


def test_row_level_security_hides_another_customers_orders_and_tickets(fresh_db):
    with _connect(fresh_db) as conn:
        for table in ("orders", "support_tickets"):
            own = _as_agent(conn, "jessica", f"SELECT DISTINCT customer_id FROM pellier.{table}")
            assert own == [{"customer_id": "CUST-JESSICA"}], table
            theos = _as_agent(conn, "jessica",
                              f"SELECT count(*) AS n FROM pellier.{table} WHERE customer_id = 'CUST-THEO'")
            assert theos == [{"n": 0}], table
            nobody = _as_agent(conn, "", f"SELECT count(*) AS n FROM pellier.{table}")
            assert nobody == [{"n": 0}], f"{table}: an unnamed session must see nothing"
        # The owner, which staff paths use, is not bound by the policies.
        assert conn.execute("SELECT count(DISTINCT customer_id) AS n FROM pellier.orders").fetchone()["n"] == 4


def test_a_cross_customer_write_is_refused_by_row_level_security(fresh_db):
    with _connect(fresh_db) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"):
            _as_agent(conn, "theo", "INSERT INTO pellier.support_tickets "
                                    "(ticket_id, customer_id, subject, status) "
                                    "VALUES ('TKT-X', 'CUST-JESSICA', 'For Jessica', 'open') "
                                    "RETURNING ticket_id")
        assert _as_agent(conn, "theo", "INSERT INTO pellier.support_tickets "
                                       "(ticket_id, customer_id, subject, status) "
                                       "VALUES ('TKT-Y', 'CUST-THEO', 'Mine', 'open') "
                                       "RETURNING ticket_id") == [{"ticket_id": "TKT-Y"}]


def test_store_credits_keep_one_row_per_key_under_a_retry(fresh_db):
    with _connect(fresh_db) as conn:
        with conn.transaction(force_rollback=True):
            review = conn.execute(
                "INSERT INTO pellier.approvals (customer_id, tool, status, args, action_hash, "
                "order_ids, decided_by, decided_at) VALUES ('CUST-JESSICA', 'give_store_credit', "
                "'approved', '{\"customer_id\": \"CUST-JESSICA\", \"amount_cents\": 10000, "
                "\"reason\": \"Two returns.\"}', repeat('c', 64), '{20,21}', 'sub-nadia', now()) "
                "RETURNING id").fetchone()["id"]
            key = f"operator-review:{review}:{'c' * 32}"
            call = "SELECT pellier.give_store_credit(%s, 'CUST-JESSICA', 10000, 'Two returns.') AS r"
            first = conn.execute(call, (key,)).fetchone()["r"]
            second = conn.execute(call, (key,)).fetchone()["r"]
            assert first["status"] == second["status"] == "success"
            assert first["idempotent_replay"] is False and second["idempotent_replay"] is True
            assert first["credit_id"] == second["credit_id"]
            assert conn.execute("SELECT count(*) AS n FROM pellier.store_credits "
                                "WHERE idempotency_key = %s", (key,)).fetchone()["n"] == 1
            # A second row for the same approval, even with its exact terms and key,
            # is refused by the owner's own table: the orders it covers are paid.
            with pytest.raises(psycopg.errors.CheckViolation) as again:
                with conn.transaction():
                    conn.execute("INSERT INTO pellier.store_credits (approval_id, customer_id, "
                                 "amount_cents, reason, idempotency_key) VALUES "
                                 "(%s, 'CUST-JESSICA', 10000, 'Two returns.', %s)", (review, key))
            assert again.value.diag.constraint_name == "store_credits_require_approval"


def test_tool_audit_refuses_a_second_fill_and_any_delete(fresh_db):
    with _connect(fresh_db) as conn:
        with conn.transaction(force_rollback=True):
            audit = conn.execute(
                "INSERT INTO pellier.tool_audit (session_id, tool, caller, args, build_fingerprint) "
                "VALUES ('turn-x', 'get_tickets', 'gateway', '{}', repeat('b', 64)) "
                "RETURNING audit_id").fetchone()["audit_id"]
            conn.execute("UPDATE pellier.tool_audit SET result = '{}', latency_ms = 5 "
                         "WHERE audit_id = %s", (audit,))
            for statement in (
                "UPDATE pellier.tool_audit SET result = '{\"forged\": true}' WHERE audit_id = %s",
                "UPDATE pellier.tool_audit SET build_fingerprint = 'other' WHERE audit_id = %s",
                "DELETE FROM pellier.tool_audit WHERE audit_id = %s",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(statement, (audit,))


def test_retrieval_receipts_are_append_only(fresh_db):
    with _connect(fresh_db) as conn:
        with conn.transaction(force_rollback=True):
            receipt = conn.execute(
                "INSERT INTO pellier.retrieval_receipts (query_hash, search_plan) "
                "VALUES ('h', '{}') RETURNING receipt_id").fetchone()["receipt_id"]
            with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
                with conn.transaction():
                    conn.execute("UPDATE pellier.retrieval_receipts SET query_hash = 'x' "
                                 "WHERE receipt_id = %s", (receipt,))


# ---------------------------------------------------------------------------
# Filtered vector search: strict-order iterative scan, and the Lab 1 index check
# ---------------------------------------------------------------------------


def _iterative_scan_block() -> str:
    schema = (REPO / "scripts/migrations/001_schema.sql").read_text()
    block = re.search(r"DO \$iterative_scan\$.*?\$iterative_scan\$;", schema, re.S)
    assert block, "001_schema.sql no longer sets hnsw.iterative_scan"
    return block.group(0)


def test_new_sessions_default_to_strict_order_iterative_scan(fresh_db):
    """The Gateway Lambda's Data API calls hold no pooled session; the default reaches them."""
    assert fresh_db.psql("SHOW hnsw.iterative_scan") == "strict_order"


def test_a_user_that_does_not_own_the_database_sets_it_for_itself(fresh_db):
    fresh_db.psql("CREATE ROLE lab_reader LOGIN")
    try:
        fresh_db.psql("SET client_min_messages TO error;\nSET ROLE lab_reader;\n"
                      + _iterative_scan_block())
        assert fresh_db.psql(
            "SELECT array_to_string(setconfig, ',') FROM pg_db_role_setting "
            "WHERE setrole = 'lab_reader'::regrole") == "hnsw.iterative_scan=strict_order"
    finally:
        fresh_db.psql("ALTER ROLE lab_reader RESET ALL; DROP ROLE lab_reader")


def _lab1_index(cluster, *extra: str) -> str:
    done = subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-P", "pager=off", *extra,
         "-f", str(REPO / "workshop/lab-1-index.sql")],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr + done.stdout
    return done.stdout


def test_the_lab1_index_check_measures_the_full_catalog(fresh_db):
    out = _lab1_index(fresh_db)
    choice, forced = out.split("1. The planner's own choice")[1].split(
        "3. Forced onto the HNSW index, iterative scan off")
    # Costs and statistics choose the initial plan; at 50,000 rows either plan is legitimate.
    assert "product_catalog" in choice and "Limit" in choice
    assert "Index Scan using product_catalog_embedding_hnsw" in forced
    eligible = int(re.search(r"2\. exact scan: 20 of 20 \((\d+) products are \$35 or less "
                             r"and not candles\)", out).group(1))
    assert eligible > 10_000
    assert re.search(r"3\. HNSW, iterative scan off: \d+ of 20; recall@20 [\d.]+%", out)
    assert re.search(r"4\. HNSW, strict_order: 20 of 20; recall@20 [\d.]+%", out)
    assert "5. The storefront" not in out
    assert out.rstrip().endswith("Lab 1 index check passed")
    # Read-only: the forced plan and the scan setting end with the transaction.
    assert fresh_db.psql("SHOW enable_seqscan") == "on"


def test_the_photographed_run_comes_back_short_until_the_partial_index(fresh_db):
    """1% of the full graph qualifies: one pass comes back short; the partial index fills it."""
    out = _lab1_index(fresh_db, "-v", "storefront_only=on")
    steps = out.split("3. Forced onto the HNSW index, iterative scan off")[1]
    full_graph, partial = steps.split("5. The storefront's own predicate")
    assert "Index Scan using product_catalog_embedding_hnsw" in full_graph
    assert "product_catalog_visible_hnsw" not in full_graph
    assert "Index Scan using product_catalog_visible_hnsw" in partial
    short = int(re.search(r"3\. HNSW, iterative scan off: (\d+) of 20", out).group(1))
    assert short < 20
    assert re.search(r"4\. HNSW, strict_order: 20 of 20;", out)
    assert re.search(r"5\. photographed-only index, iterative scan off: 20 of 20;", out)
    assert "select different rows" not in out
    assert out.rstrip().endswith("Lab 1 index check passed")


# ---------------------------------------------------------------------------
# Reset is a rebuild
# ---------------------------------------------------------------------------


def test_reset_rebuilds_the_same_dataset(fresh_db):
    fresh_db.psql("INSERT INTO pellier.approvals (customer_id, tool, status) "
                  "VALUES ('CUST-JESSICA', 'store_credit_request', 'open')")
    done = run_reset(fresh_db)
    assert fresh_db.psql("SELECT count(*) FROM pellier.approvals") == "0"
    assert "WARNING:  pgAudit is off (" in done.stderr
    test_pgaudit_audits_the_credit_table_writes_and_nothing_else(fresh_db)
    test_the_schema_is_exactly_the_ten_tables(fresh_db)
    test_the_customers_are_the_four_shoppers_exactly(fresh_db)
    test_jessicas_case_is_exactly_one_hundred_dollars_and_nothing_is_credited(fresh_db)
    test_three_rows_per_product_and_the_catalog_agrees(fresh_db)
    test_teaching_products_have_exact_stock(fresh_db)


# ---------------------------------------------------------------------------
# pgAudit: the database's record of what reached the credits table
# ---------------------------------------------------------------------------

PGAUDIT_PRIVILEGES = (
    "SELECT c.oid::regclass || ' ' || e.privilege_type FROM pg_class c, aclexplode(c.relacl) e "
    "WHERE e.grantee = 'rds_pgaudit'::regrole "
    "UNION ALL SELECT 'column ' || a.attrelid::regclass || '.' || a.attname "
    "FROM pg_attribute a, aclexplode(a.attacl) e WHERE e.grantee = 'rds_pgaudit'::regrole "
    "UNION ALL SELECT 'function ' || p.oid::regprocedure FROM pg_proc p, aclexplode(p.proacl) e "
    "WHERE e.grantee = 'rds_pgaudit'::regrole "
    "UNION ALL SELECT 'member of ' || roleid::regrole FROM pg_auth_members "
    "WHERE member = 'rds_pgaudit'::regrole "
    "UNION ALL SELECT 'granted to ' || member::regrole FROM pg_auth_members "
    "WHERE roleid = 'rds_pgaudit'::regrole ORDER BY 1"
)


def test_pgaudit_audits_the_credit_table_writes_and_nothing_else(fresh_db):  # noqa: F811
    """pgaudit.role's privileges choose what object auditing logs, so they are pinned here.

    rds_pgaudit is Aurora's one allowed pgaudit.role. It cannot log in and nobody holds it:
    its two privileges only mark INSERT and UPDATE on the credits table as audited.
    """
    assert _rows(fresh_db, "SELECT rolcanlogin || ' ' || rolsuper || ' ' || rolbypassrls "
                           "FROM pg_roles WHERE rolname = 'rds_pgaudit'") == ["false false false"]
    assert _rows(fresh_db, PGAUDIT_PRIVILEGES) == [
        "pellier.store_credits INSERT", "pellier.store_credits UPDATE",
    ]


def test_the_schema_builds_without_pgaudit_and_says_so(fresh_db, tmp_path):  # noqa: F811
    # The extension's block alone, as the schema runs it, on a cluster with no pgAudit library.
    schema = (REPO / "scripts" / "migrations" / "001_schema.sql").read_text(encoding="utf-8")
    block = re.search(r"DO \$pgaudit\$.*?END \$pgaudit\$;", schema, re.S)
    assert block is not None
    script = tmp_path / "pgaudit.sql"
    script.write_text(block.group(0), encoding="utf-8")
    done = subprocess.run(
        [str(fresh_db.bin / "psql"), "-X", "-h", str(fresh_db.socket), "-U", "postgres",
         "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-f", str(script)],
        capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "WARNING:  pgAudit is off (" in done.stderr
    assert "Writes to pellier.store_credits are not audited" in done.stderr
    assert fresh_db.psql("SELECT count(*) FROM pg_extension WHERE extname = 'pgaudit'") == "0"


def test_the_credit_function_is_the_money_roles_only_way_in(fresh_db):  # noqa: F811
    """Definer rights make EXECUTE the whole key, so who holds it is pinned here."""
    assert _rows(fresh_db, "SELECT prosecdef::text || ' ' || array_to_string(proconfig, ',') "
                           "FROM pg_proc WHERE proname = 'give_store_credit'") == [
        "true search_path=pg_catalog, pg_temp"
    ]
    signature = "'pellier.give_store_credit(text, text, integer, text, text)'"
    assert _rows(fresh_db, f"SELECT r || ' ' || has_function_privilege(r, {signature}, 'EXECUTE') "
                           "FROM unnest(ARRAY['pellier_credit_writer', 'pellier_agent', 'public']) "
                           "AS r") == [
        "pellier_credit_writer true", "pellier_agent false", "public false",
    ]
    assert _rows(fresh_db, "SELECT count(*) FROM information_schema.role_table_grants "
                           "WHERE grantee = 'pellier_credit_writer'") == ["0"]
    assert _rows(fresh_db, "SELECT count(*) FROM information_schema.role_column_grants "
                           "WHERE grantee = 'pellier_credit_writer'") == ["0"]


# ---------------------------------------------------------------------------
# get_return_policy: a department is matched as the shopper writes it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("asked", "answered", "fallback"), [
    ("Kitchen and table", "Kitchen and table", False),
    ("kitchen AND Table", "Kitchen and table", False),
    ("home", "Home", False),
    ("Garden", "default", True),
    ("", "default", False),
])
def test_return_policy_matches_a_department_in_any_case(fresh_db, asked, answered, fallback):
    from services import store_tools

    with _connect(fresh_db) as conn:
        def run(sql, params=()):
            return conn.execute(sql, params).fetchall()

        policy = store_tools.get_return_policy(run, department=asked)

    assert policy["status"] == "success"
    assert policy["department"] == answered
    assert policy.get("fallback", False) is fallback
