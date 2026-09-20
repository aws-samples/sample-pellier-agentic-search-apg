"""Live rejection list for model-generated SQL, against a real planner.

Skipped unless `PELLIER_LIVE_DB_TESTS=1`.

"PostgreSQL refuses this statement" is a claim only PostgreSQL can settle, so
the whole rejection list runs against the cluster. Each case asserts **database
state** rather than error text where state is what matters: a `DELETE` that was
refused must leave the row count unchanged, not merely produce a message.

The control case matters as much as the hostile ones. A boundary that refuses
everything looks perfect and is useless, and that is exactly the bug this
module had during implementation — `SET LOCAL statement_timeout = %s` aborted
every query, so every hostile case "passed".
"""

from __future__ import annotations

import os
import pathlib
import uuid
from typing import Any, AsyncIterator, Dict

import pytest
import pytest_asyncio

pytestmark = pytest.mark.skipif(
    os.environ.get("PELLIER_LIVE_DB_TESTS") != "1",
    reason="live Aurora integration; set PELLIER_LIVE_DB_TESTS=1 to run",
)

_RUN = uuid.uuid4().hex[:8]


def _live_database_url() -> str:
    from urllib.parse import quote_plus

    explicit = os.environ.get("PELLIER_LIVE_DB_URL", "").strip()
    if explicit:
        return explicit
    env_path = pathlib.Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        pytest.skip("no backend .env; cannot reach a live cluster")
    cfg: Dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not cfg.get(k)]
    if missing:
        pytest.skip(f"backend .env missing {', '.join(missing)}")
    return (
        f"postgresql://{cfg['DB_USER']}:{quote_plus(cfg['DB_PASSWORD'])}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT', '5432')}/{cfg['DB_NAME']}"
    )


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def db() -> AsyncIterator[Any]:
    from config import settings
    from services.database import DatabaseService

    previous = settings.DATABASE_URL
    settings.DATABASE_URL = _live_database_url()
    service = DatabaseService()
    try:
        await service.connect()
    except Exception as exc:
        settings.DATABASE_URL = previous
        pytest.skip(f"live cluster unreachable: {exc}")
    try:
        yield service
    finally:
        # Every attempt now receipts itself, so a run of the hostile cases
        # leaves ~30 rows in a shared cluster. Keyed on this run's turn_id so
        # the sweep cannot touch a participant's or another run's evidence.
        try:
            await service.execute_query(
                "DELETE FROM pellier.governed_query_receipts WHERE turn_id = %s",
                f"turn-{_RUN}",
            )
        except Exception:  # pragma: no cover - cleanup must not mask a failure
            pass
        await service.disconnect()
        settings.DATABASE_URL = previous


async def _run(db: Any, sql: str, **kwargs: Any):
    from services.governed_query import run_governed_query

    return await run_governed_query(db, sql, turn_id=f"turn-{_RUN}", **kwargs)


# ---------------------------------------------------------------------------
# The control case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_a_legitimate_question_is_answered(db):
    """Without this, a boundary that refuses everything looks perfect."""
    result = await _run(
        db, "SELECT name, price FROM product_catalog ORDER BY price DESC"
    )

    assert result.accepted, result.rejection_reason
    assert result.validation == "accepted"
    assert result.execution_outcome == "success"
    assert result.row_count and result.row_count > 0
    assert result.rows[0].get("name")
    assert result.schemas_read == ["pellier"]


@pytest.mark.asyncio(loop_scope="module")
async def test_unqualified_names_resolve_through_the_fixed_search_path(db):
    """The session pins search_path, so `product_catalog` resolves in pellier."""
    result = await _run(db, "SELECT count(*) AS n FROM product_catalog")

    assert result.accepted, result.rejection_reason
    assert result.rows[0]["n"] > 0


# ---------------------------------------------------------------------------
# The implementation owns the row cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_an_oversized_limit_is_capped_by_the_implementation(db):
    from services.governed_query import MAX_ROWS

    result = await _run(db, "SELECT name FROM product_catalog LIMIT 100000")

    assert result.accepted
    assert result.row_count == MAX_ROWS
    assert len(result.rows) == MAX_ROWS


@pytest.mark.asyncio(loop_scope="module")
async def test_a_nested_limit_cannot_bypass_the_cap(db):
    from services.governed_query import MAX_ROWS

    result = await _run(
        db,
        "SELECT * FROM (SELECT name FROM product_catalog LIMIT 900) inner_q",
    )

    assert result.accepted
    assert result.row_count == MAX_ROWS


# ---------------------------------------------------------------------------
# Mutation attempts — asserted against database state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,sql",
    [
        ("select then delete", "SELECT 1; DELETE FROM pellier.orders"),
        ("update", "UPDATE pellier.orders SET quantity = 0"),
        ("insert", "INSERT INTO pellier.orders (customer_id) VALUES ('x')"),
        ("delete", "DELETE FROM pellier.orders"),
        ("data-modifying cte",
         "WITH d AS (DELETE FROM pellier.orders RETURNING 1) SELECT * FROM d"),
        ("comment-separated statements",
         "SELECT 1 /* sneak */ ; DELETE FROM pellier.orders"),
        ("comment-hidden second statement",
         "SELECT 1 --\n; DELETE FROM pellier.orders"),
    ],
)
@pytest.mark.asyncio(loop_scope="module")
async def test_mutation_attempts_are_refused_and_change_nothing(db, label, sql):
    """Assert state, not error text: the row count must be untouched."""
    # `orders.customer_id` has a foreign key to `customers.id`, so the row has
    # to belong to a seeded customer; it is removed by id afterwards.
    await db.execute_query(
        "INSERT INTO pellier.orders (customer_id, product_id, quantity)"
        " VALUES ('CUST-MARCO', '11', 1)"
    )
    seeded = (
        await db.fetch_one("SELECT max(id) AS id FROM pellier.orders")
    )["id"]
    before = (
        await db.fetch_one("SELECT count(*) AS n FROM pellier.orders")
    )["n"]
    try:
        result = await _run(db, sql)

        assert not result.accepted, f"{label} was accepted"
        assert result.execution_outcome == "not_executed"
        after = (await db.fetch_one("SELECT count(*) AS n FROM pellier.orders"))["n"]
        assert after == before, f"{label} changed the database"
    finally:
        await db.execute_query("DELETE FROM pellier.orders WHERE id = %s", seeded)


@pytest.mark.parametrize(
    "label,sql",
    [
        ("create", "CREATE TABLE zzz_governed (a int)"),
        ("alter disable rls",
         "ALTER TABLE pellier.orders DISABLE ROW LEVEL SECURITY"),
        ("drop", "DROP TABLE pellier.orders"),
        ("grant", "GRANT ALL ON pellier.orders TO pellier_query"),
        ("set role", "SET ROLE postgres"),
        ("begin", "BEGIN"),
        ("commit", "COMMIT"),
    ],
)
@pytest.mark.asyncio(loop_scope="module")
async def test_utility_statements_are_refused(db, label, sql):
    result = await _run(db, sql)

    assert not result.accepted, f"{label} was accepted"
    assert result.execution_outcome == "not_executed"


@pytest.mark.asyncio(loop_scope="module")
async def test_row_level_security_survives_a_disable_attempt(db):
    """The ALTER above must not have taken effect."""
    row = await db.fetch_one(
        "SELECT rowsecurity FROM pg_tables WHERE schemaname='pellier'"
        " AND tablename='orders'"
    )

    assert row["rowsecurity"] is True


@pytest.mark.asyncio(loop_scope="module")
async def test_the_read_role_gained_no_grant(db):
    """The GRANT attempt above must not have widened pellier_query."""
    row = await db.fetch_one(
        "SELECT count(*) AS n FROM information_schema.role_table_grants"
        " WHERE grantee='pellier_query' AND table_name='orders'"
        "   AND privilege_type <> 'SELECT'"
    )

    assert row["n"] == 0


# ---------------------------------------------------------------------------
# Reach beyond the business schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_system_catalog_reads_are_refused(db):
    """A question about the business does not need the role table."""
    result = await _run(db, "SELECT rolname FROM pg_roles")

    assert not result.accepted
    assert "outside the allowed schemas" in (result.rejection_reason or "")


@pytest.mark.asyncio(loop_scope="module")
async def test_a_join_that_reaches_outside_is_refused_whole(db):
    """One out-of-allowlist relation refuses the statement, not just that leg."""
    result = await _run(
        db,
        "SELECT p.name, r.rolname FROM pellier.product_catalog p, pg_roles r",
    )

    assert not result.accepted
    assert "pg_catalog" in (result.rejection_reason or "")


@pytest.mark.asyncio(loop_scope="module")
async def test_the_evidence_ledger_is_unreadable(db):
    """Generated SQL must not inspect or manufacture evidence."""
    result = await _run(db, "SELECT * FROM pellier.tool_audit")

    assert not result.accepted
    assert "tool_audit" in (result.rejection_reason or "")


@pytest.mark.asyncio(loop_scope="module")
async def test_query_receipts_are_unreadable_by_generated_sql(db):
    result = await _run(db, "SELECT * FROM pellier.governed_query_receipts")

    assert not result.accepted


# ---------------------------------------------------------------------------
# A SELECT can call a function; EXECUTE grants are the boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_a_state_changing_function_cannot_be_invoked(db):
    """Structural validation cannot reason about side effects.

    Migration 017 revokes EXECUTE from `pellier_query`, which is why this is
    refused rather than merely failing inside a read-only transaction.
    """
    before = (await db.fetch_one("SELECT count(*) AS n FROM pellier.returns"))["n"]

    result = await _run(
        db,
        "SELECT pellier.process_return_idempotent("
        "'k','h','CUST-MARCO','11','damaged')",
    )

    assert not result.accepted
    assert "permission denied" in (result.rejection_reason or "").lower()
    after = (await db.fetch_one("SELECT count(*) AS n FROM pellier.returns"))["n"]
    assert after == before


# ---------------------------------------------------------------------------
# Long-running statements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_a_long_running_statement_is_cut_off(db):
    """statement_timeout bounds a generated query's resource use."""
    result = await _run(
        db,
        "SELECT count(*) FROM product_catalog a, product_catalog b,"
        " product_catalog c, product_catalog d",
    )

    # Structurally fine, so it is accepted and then stopped.
    assert result.accepted
    assert result.execution_outcome == "error"
    assert "timeout" in (result.rejection_reason or "").lower()


# ---------------------------------------------------------------------------
# Row-Level Security applies to generated SQL too
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_generated_sql_is_scoped_by_row_level_security(db):
    """Generated SQL gets no wider view of customer data than a curated tool."""
    await db.execute_query(
        "INSERT INTO pellier.orders (customer_id, product_id, quantity)"
        " VALUES ('CUST-MARCO','11',1), ('CUST-ANNA','21',1)"
    )
    ids = [
        r["id"]
        for r in await db.fetch_all(
            "SELECT id FROM pellier.orders ORDER BY id DESC LIMIT 2"
        )
    ]
    mapping = await db.fetch_one(
        "SELECT principal_sub FROM pellier.principal_customers"
        " WHERE customer_id='CUST-MARCO'"
    )
    try:
        assert mapping, "Marco has no seeded principal mapping"

        anonymous = await _run(db, "SELECT count(*) AS n FROM orders")
        scoped = await _run(
            db,
            "SELECT DISTINCT customer_id FROM orders",
            principal_sub=mapping["principal_sub"],
        )

        assert anonymous.accepted and anonymous.rows[0]["n"] == 0
        assert scoped.accepted
        assert [row["customer_id"] for row in scoped.rows] == ["CUST-MARCO"]
    finally:
        await db.execute_query("DELETE FROM pellier.orders WHERE id = ANY(%s)", ids)


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_a_refusal_leaves_a_durable_receipt(db):
    """A refusal that leaves no artifact cannot be inspected.

    Asserts the receipt the *call* wrote, not one the test wrote afterwards.
    The earlier version invoked `persist_receipt` itself and so passed while
    every production lane left the table empty.
    """
    result = await _run(db, "DELETE FROM pellier.orders", session_id=f"sess-{_RUN}")
    assert not result.accepted

    receipt_id = result.receipt_id
    try:
        assert receipt_id, "run_governed_query must receipt its own refusal"
        row = await db.fetch_one(
            "SELECT accepted, validation, execution_outcome, role_used,"
            "       result_limit, generated_sql, turn_id"
            "  FROM pellier.governed_query_receipts WHERE receipt_id = %s",
            receipt_id,
        )
        assert row["accepted"] is False
        assert row["execution_outcome"] == "not_executed"
        assert row["role_used"] == "pellier_query"
        assert "DELETE" in row["generated_sql"]
        assert row["turn_id"] == f"turn-{_RUN}"
    finally:
        await db.execute_query(
            "DELETE FROM pellier.governed_query_receipts WHERE receipt_id = %s",
            receipt_id,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_an_accepted_query_receipt_records_the_row_count(db):
    result = await _run(db, "SELECT name FROM product_catalog")
    receipt_id = result.receipt_id
    try:
        assert receipt_id, "run_governed_query must receipt an accepted query"
        row = await db.fetch_one(
            "SELECT accepted, execution_outcome, row_count, schemas_read"
            "  FROM pellier.governed_query_receipts WHERE receipt_id = %s",
            receipt_id,
        )
        assert row["accepted"] is True
        assert row["execution_outcome"] == "success"
        assert row["row_count"] == result.row_count
        assert row["schemas_read"] == ["pellier"]
    finally:
        await db.execute_query(
            "DELETE FROM pellier.governed_query_receipts WHERE receipt_id = %s",
            receipt_id,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_the_earliest_rejection_is_still_receipted(db):
    """A statement refused before it reaches the planner must still leave one.

    `precheck` returns from the first branch of the attempt, ahead of every
    other exit, and is the only rejection that never opens a connection. If
    the receipt write ever moves back inside that function, this is the case
    that stops getting one — and it is the case with no other trace anywhere,
    since nothing was sent to Aurora at all.

    An oversized statement rather than a stacked one: `precheck` only makes
    the rejections it can make without a parser, so `SELECT 1; DROP ...` is
    the *planner's* to refuse (`rejected_structure`), not this stage's.
    """
    from services.governed_query import MAX_SQL_LENGTH

    result = await _run(db, "SELECT " + "1," * MAX_SQL_LENGTH + "1")

    assert result.validation == "rejected_precheck"
    receipt_id = result.receipt_id
    try:
        assert receipt_id, "a precheck rejection must be receipted"
        row = await db.fetch_one(
            "SELECT validation, execution_outcome, rejection_reason"
            "  FROM pellier.governed_query_receipts WHERE receipt_id = %s",
            receipt_id,
        )
        assert row["validation"] == "rejected_precheck"
        assert row["execution_outcome"] == "not_executed"
        assert row["rejection_reason"]
    finally:
        await db.execute_query(
            "DELETE FROM pellier.governed_query_receipts WHERE receipt_id = %s",
            receipt_id,
        )
