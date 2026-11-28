"""The plain-SQL statements the workshop guide has participants paste into psql.

The guide (Workshop Studio, Tasks 1A, 2A and 4B) carries these statements as text. This
module is the one place in this repository that holds them, so a schema rename that would
break the pasted statement fails here, in the backend-postgres job, instead of at an event.
Change a statement here and in the guide together.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]

# Task 1A starts with PostgreSQL full-text search. The optional pgvector example
# uses the same visible catalog and the product found by the word search.
WORD_MATCH = """
SELECT p.name AS product
FROM pellier.product_catalog p
WHERE NULLIF(btrim(p."imgUrl"), '') IS NOT NULL
  AND p.description_tsv @@ to_tsquery('english', 'pour-over')
ORDER BY p.name;
"""

NEAREST_BY_MEANING = """
SELECT p.name AS product,
       round((p.embedding <=> q.emb)::numeric, 3) AS distance,
       round((1 - (p.embedding <=> q.emb))::numeric, 3) AS similarity
FROM pellier.product_catalog p,
     (SELECT embedding AS emb FROM pellier.product_catalog
      WHERE name = 'Stoneware Pour-Over Set') q
WHERE NULLIF(btrim(p."imgUrl"), '') IS NOT NULL
ORDER BY p.embedding <=> q.emb
LIMIT 5;
"""

# Task 2A: the warehouse rows behind Marco's answer. Plain SQL, no backslash commands.
WAREHOUSE_ROWS = """
SELECT warehouse_name AS warehouse,
       quantity AS units,
       ship_window_min || ' to ' || ship_window_max || ' days' AS ships_in
FROM pellier.warehouse_inventory
WHERE product_id = (SELECT product_id FROM pellier.product_catalog
                    WHERE name = 'Hadley Linen Shirt')
ORDER BY ship_window_min;
"""

# Task 2B, before and after the fix: the stock function called directly. A piece Pellier does
# not carry returns one row of 0 units until the fix, and no row after it, where a sold-out
# piece still returns its row of 0.
STOCK_FUNCTION_ROWS = """
SELECT q.asked, count(f.total_units) AS rows_returned, max(f.total_units) AS units
FROM (VALUES ('Velvet Opera Cape'), ('Quilted Silk Vest'), ('Hadley Linen Shirt')) AS q(asked)
LEFT JOIN LATERAL pellier.check_stock(q.asked) AS f ON true
GROUP BY q.asked
ORDER BY q.asked;
"""

# Task 3A: who the server binds each sign-in name to. Read-only.
SIGN_IN_TO_CUSTOMER = """
SELECT cognito_username AS signs_in_as, id AS customer_id
FROM pellier.customers
WHERE cognito_username IN ('theo', 'jessica')
ORDER BY cognito_username;
"""

# Task 3B: tickets as Theo, under the role the agent uses. A transaction that ends in ROLLBACK,
# no backslash commands, so it pastes as a heredoc. Run it with psql -q so the tags stay out.
TICKETS_AS_THEO = """
BEGIN;
SET LOCAL ROLE pellier_agent;
SET LOCAL pellier.principal_username = 'theo';
SELECT ticket_id, customer_id, subject FROM pellier.support_tickets ORDER BY ticket_id;
ROLLBACK;
"""

# Task 4B step 1: who may do what on pellier.store_credits, in words, one row per role.
# It reads the table's access list from pg_class, which every login may read. Column-level
# grants are left out: pellier_credit_writer holds none either way, and the table-level
# list is what the task changes.
STORE_CREDITS_ACCESS = """
SELECT CASE a.grantee WHEN 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS role,
       string_agg(lower(a.privilege_type), ', ' ORDER BY a.privilege_type) AS can
FROM pg_class c, aclexplode(c.relacl) a
WHERE c.oid = 'pellier.store_credits'::regclass
GROUP BY 1
ORDER BY 1;
"""


def test_the_2a_warehouse_query_returns_the_three_seeded_rows(fresh_db) -> None:  # noqa: F811
    rows = fresh_db.psql(WAREHOUSE_ROWS).splitlines()
    assert rows == ["Brooklyn|0|1 to 2 days", "Austin|6|2 to 4 days", "Portland|14|3 to 5 days"]


def test_the_4b_access_query_lists_roles_and_not_the_credit_writer(fresh_db) -> None:  # noqa: F811
    rows = dict(line.split("|", 1) for line in fresh_db.psql(STORE_CREDITS_ACCESS).splitlines())
    assert rows["pellier_credit_owner"] == "select"
    assert rows["pellier_operator_tools"] == "select"
    assert "insert" in rows["rds_pgaudit"] and "update" in rows["rds_pgaudit"]
    assert "pellier_credit_writer" not in rows and "PUBLIC" not in rows


def test_the_1a_extension_line_has_a_vector_extension_to_show(fresh_db) -> None:  # noqa: F811
    version = fresh_db.psql("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    assert version[:1].isdigit(), version


def test_the_1a_word_search_finds_the_pour_over_set(fresh_db) -> None:  # noqa: F811
    assert fresh_db.psql(WORD_MATCH).splitlines() == ["Stoneware Pour-Over Set"]


def test_the_1a_nearest_query_starts_at_the_product_itself(fresh_db) -> None:  # noqa: F811
    rows = [line.split("|") for line in fresh_db.psql(NEAREST_BY_MEANING).splitlines()]
    assert rows[0] == ["Stoneware Pour-Over Set", "0.000", "1.000"]
    assert [row[0] for row in rows[1:]] == [
        "Ceramic Tumblers",
        "Stoneware Mugs, Set of 2",
        "Ceramic Pitcher, Slate, 750 ml",
        "Ceramic Pitcher, Slate, 1500 ml",
    ]
    distances = [float(row[1]) for row in rows]
    assert len(rows) == 5 and distances == sorted(distances)
    assert all(abs(float(row[1]) + float(row[2]) - 1) < 0.002 for row in rows)


def test_the_2b_stock_function_query_shows_not_carried_before_and_after_the_fix(  # noqa: F811
        fresh_db) -> None:
    before = fresh_db.psql(STOCK_FUNCTION_ROWS).splitlines()
    assert before == ["Hadley Linen Shirt|1|20", "Quilted Silk Vest|1|0", "Velvet Opera Cape|1|0"]
    solution = REPO / "solutions" / "lab-2-ground" / "sql" / "lab-2-check-stock-solution.sql"
    done = subprocess.run(
        [str(fresh_db.bin / "psql"), "-X", "-h", str(fresh_db.socket), "-U", "postgres",
         "-d", "postgres", "-f", str(solution)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    after = fresh_db.psql(STOCK_FUNCTION_ROWS).splitlines()
    assert after == ["Hadley Linen Shirt|1|20", "Quilted Silk Vest|1|0", "Velvet Opera Cape|0|"]


def test_the_3a_sign_in_query_maps_names_to_customer_ids(fresh_db) -> None:  # noqa: F811
    assert fresh_db.psql(SIGN_IN_TO_CUSTOMER).splitlines() == [
        "jessica|CUST-JESSICA", "theo|CUST-THEO"]


def test_the_3b_ticket_query_returns_only_theos_tickets_and_changes_nothing(  # noqa: F811
        fresh_db) -> None:
    done = subprocess.run(
        [str(fresh_db.bin / "psql"), "-X", "-q", "-At", "-h", str(fresh_db.socket), "-U",
         "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1"],
        input=TICKETS_AS_THEO, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    rows = [line.split("|") for line in done.stdout.splitlines()]
    assert [row[:2] for row in rows] == [["TKT-2026-1874", "CUST-THEO"],
                                         ["TKT-2026-5021", "CUST-THEO"]]
    assert fresh_db.psql("SELECT count(DISTINCT customer_id) > 1 FROM pellier.support_tickets") == "t"
