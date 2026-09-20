"""Live Row-Level Security proofs against a real Aurora cluster.

Skipped unless `PELLIER_LIVE_DB_TESTS=1`. These tests connect to the
configured cluster and write fixture rows, so they are opt-in by design — the
default suite stays hermetic and offline.

Run with:

    PELLIER_LIVE_DB_TESTS=1 .venv/bin/python -m pytest tests/test_rls_live_integration.py -v

Why these cannot be unit tests
------------------------------

Three of the properties here are only true of a real server:

* **Owner bypass.** A table owner ignores RLS unless `FORCE ROW LEVEL
  SECURITY` is set. That is server behavior, and it is also the workshop's
  teaching point, so it must be demonstrated rather than asserted in a mock.
* **Pool leakage.** The spec makes this release-blocking: principal state must
  not survive into the next borrower of the same pooled connection. Proving it
  requires an actual connection pool handing back an actual connection, which
  the test confirms by comparing backend PIDs.
* **`WITH CHECK` versus `USING`.** Whether a policy rejects a *new* row is
  decided by the planner, not by application code.

The connection pool is module-scoped and pinned to one event loop. A
per-test pool is not merely slow: psycopg's pool starts background tasks
bound to the loop that opened it, and pytest-asyncio gives each test a
fresh loop, so a function-scoped pool hangs on reuse rather than failing.

Every probe is differential. A count of zero proves nothing on its own — an
empty table also returns zero — so each denial is paired with a permitted
read that returns a specific row.
"""

from __future__ import annotations

import os
import pathlib
import uuid
from typing import Any, AsyncIterator, Dict, List

import pytest
import pytest_asyncio

pytestmark = pytest.mark.skipif(
    os.environ.get("PELLIER_LIVE_DB_TESTS") != "1",
    reason="live Aurora integration; set PELLIER_LIVE_DB_TESTS=1 to run",
)

# Distinct per run so a crashed run cannot collide with the next one.
_RUN = uuid.uuid4().hex[:8]
_SUB_MARCO = f"test-sub-marco-{_RUN}"
_SUB_UNMAPPED = f"test-sub-unmapped-{_RUN}"


def _live_database_url() -> str:
    """Build a connection URL from the real `.env`.

    `tests/conftest.py` deliberately replaces every `DB_*` setting with a
    localhost placeholder so the suite can never reach a real cluster by
    accident. That protection is correct and stays in place — a live test has
    to opt out of it explicitly, which is what this does. `PELLIER_LIVE_DB_URL`
    overrides the `.env` cluster with any reachable PostgreSQL that carries the
    Pellier schema.
    """
    from urllib.parse import quote_plus

    # An explicit URL wins, so the suite can target a local clone of the schema
    # without pointing it at whichever cluster the developer's .env names.
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

    # `database_url` prefers DATABASE_URL when set, so one attribute redirects
    # the pool without touching the individual placeholder settings.
    previous = settings.DATABASE_URL
    previous_min = settings.DB_POOL_MIN_SIZE
    previous_max = settings.DB_POOL_MAX_SIZE
    settings.DATABASE_URL = _live_database_url()
    # A single connection makes the leakage probe deterministic: with a larger
    # pool the second transaction may land on a different backend, and the
    # probe then proves nothing about state surviving reuse.
    settings.DB_POOL_MIN_SIZE = 1
    settings.DB_POOL_MAX_SIZE = 1

    service = DatabaseService()
    try:
        await service.connect()
    except Exception as exc:
        settings.DATABASE_URL = previous
        settings.DB_POOL_MIN_SIZE = previous_min
        settings.DB_POOL_MAX_SIZE = previous_max
        pytest.skip(f"live cluster unreachable: {exc}")

    try:
        yield service
    finally:
        await service.disconnect()
        settings.DATABASE_URL = previous
        settings.DB_POOL_MIN_SIZE = previous_min
        settings.DB_POOL_MAX_SIZE = previous_max


@pytest_asyncio.fixture(loop_scope="module")
async def seeded(db) -> AsyncIterator[Dict[str, Any]]:
    """Two orders for two customers, plus one principal mapping.

    Seeded as the owner (which bypasses RLS) and removed afterwards. Product
    ids come from the committed catalog so any foreign key holds.
    """
    await db.execute_query(
        "INSERT INTO pellier.principal_customers (principal_sub, customer_id)"
        " VALUES (%s, %s) ON CONFLICT DO NOTHING",
        _SUB_MARCO,
        "CUST-MARCO",
    )
    rows = await db.fetch_all(
        "INSERT INTO pellier.orders (customer_id, product_id, quantity)"
        " VALUES (%s, %s, %s), (%s, %s, %s) RETURNING id, customer_id",
        "CUST-MARCO", "11", 1,
        "CUST-ANNA", "21", 1,
    )
    try:
        yield {"order_ids": [r["id"] for r in rows]}
    finally:
        await db.execute_query(
            "DELETE FROM pellier.orders WHERE id = ANY(%s)",
            [r["id"] for r in rows],
        )
        await db.execute_query(
            "DELETE FROM pellier.principal_customers WHERE principal_sub = %s",
            _SUB_MARCO,
        )


async def _scalar(conn: Any, sql: str, params: tuple = ()) -> Any:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()
    return None if row is None else list(row.values())[0]


# ---------------------------------------------------------------------------
# Owner bypass versus bound role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_owner_sees_rows_that_the_bound_role_cannot(db, seeded):
    """The differential that makes the exercise legible.

    Same rows, same instant, two effective roles: the owner bypasses RLS, the
    runtime role is bound by it.
    """
    owner_visible = await db.fetch_one(
        "SELECT count(*) AS n FROM pellier.orders WHERE customer_id IN"
        " ('CUST-MARCO','CUST-ANNA')"
    )
    assert owner_visible["n"] >= 2, "owner must see both seeded rows"

    async with db.principal_session(_SUB_MARCO) as conn:
        scoped = await _scalar(
            conn,
            "SELECT count(*) FROM pellier.orders WHERE customer_id IN"
            " ('CUST-MARCO','CUST-ANNA')",
        )
        customers = await _scalar(
            conn,
            "SELECT string_agg(DISTINCT customer_id, ',') FROM pellier.orders",
        )

    # Marco's principal sees Marco's rows and not Anna's — a specific claim,
    # not merely "fewer rows".
    assert scoped >= 1
    assert customers == "CUST-MARCO"


@pytest.mark.asyncio(loop_scope="module")
async def test_unmapped_principal_is_denied_while_mapped_one_is_not(db, seeded):
    async with db.principal_session(_SUB_MARCO) as conn:
        mapped = await _scalar(conn, "SELECT count(*) FROM pellier.orders")
    async with db.principal_session(_SUB_UNMAPPED) as conn:
        unmapped = await _scalar(conn, "SELECT count(*) FROM pellier.orders")

    assert mapped >= 1, "a mapped principal must see its own rows"
    assert unmapped == 0, "an unmapped principal must see nothing"


@pytest.mark.asyncio(loop_scope="module")
async def test_anonymous_turn_fails_closed(db, seeded):
    """A missing principal denies access; it must not widen it."""
    async with db.principal_session(None) as conn:
        visible = await _scalar(conn, "SELECT count(*) FROM pellier.orders")

    assert visible == 0


# ---------------------------------------------------------------------------
# Pool leakage — release-blocking (spec section 11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_principal_cannot_leak_between_pooled_transactions(db, seeded):
    """Transaction B must not inherit transaction A's principal.

    The test is only meaningful if the pool actually hands back the same
    physical connection, so it asserts the backend PID matches. If a future
    pool configuration stops reusing connections, this fails loudly rather
    than passing vacuously.
    """
    async with db.principal_session(_SUB_MARCO) as conn:
        pid_a = await _scalar(conn, "SELECT pg_backend_pid()")
        visible_a = await _scalar(conn, "SELECT count(*) FROM pellier.orders")

    assert visible_a >= 1, "transaction A must be the permitted case"

    # Same connection, no principal bound this time.
    async with db.principal_session(None) as conn:
        pid_b = await _scalar(conn, "SELECT pg_backend_pid()")
        visible_b = await _scalar(conn, "SELECT count(*) FROM pellier.orders")
        leaked = await _scalar(
            conn, "SELECT current_setting('pellier.principal_sub', true)"
        )

    assert pid_b == pid_a, (
        "the pool did not reuse the connection, so this run proved nothing "
        "about leakage"
    )
    assert visible_b == 0, "principal state leaked across pooled transactions"
    assert not leaked, f"stale principal survived the transaction: {leaked!r}"


# ---------------------------------------------------------------------------
# WITH CHECK versus USING
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_authorized_principal_cannot_write_another_customers_row(db, seeded):
    """A read-shaped policy would allow this; `WITH CHECK` must reject it."""
    import psycopg

    with pytest.raises(psycopg.errors.Error) as caught:
        async with db.principal_session(_SUB_MARCO) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO pellier.orders (customer_id, product_id, quantity)"
                    " VALUES ('CUST-ANNA', '21', 1)"
                )

    assert "row-level security" in str(caught.value).lower()


@pytest.mark.asyncio(loop_scope="module")
async def test_authorized_principal_can_write_its_own_row(db, seeded):
    """The permitted half, so the rejection above is not a blanket failure."""
    async with db.principal_session(_SUB_MARCO) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO pellier.orders (customer_id, product_id, quantity)"
                " VALUES ('CUST-MARCO', '11', 1) RETURNING id"
            )
            row = await cur.fetchone()
    inserted = row["id"]

    try:
        assert inserted is not None
    finally:
        await db.execute_query("DELETE FROM pellier.orders WHERE id = %s", inserted)


# ---------------------------------------------------------------------------
# Evidence-ledger grants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_agent_can_complete_its_own_receipt_but_not_falsify_one(db):
    """The grants must fit the shipped two-phase writer, and no further.

    `tool_audit_writer` INSERTs with `RETURNING audit_id`, then UPDATEs
    `result` and `latency_ms`. A literal INSERT-only grant breaks both, and
    the writer swallows its own exceptions, so the failure would be silent
    evidence loss. These probes pin the exact privilege surface.
    """
    import psycopg

    async with db.principal_session("irrelevant-for-grants") as conn:
        async with conn.cursor() as cur:
            # Phase 1, exactly as the writer issues it.
            await cur.execute(
                "INSERT INTO pellier.tool_audit (session_id, tool, caller, args)"
                " VALUES (%s, 'grant_probe', 'test', '{}'::jsonb)"
                " RETURNING audit_id",
                (f"grant-probe-{_RUN}",),
            )
            appended = (await cur.fetchone())["audit_id"]
            # Phase 2, likewise.
            await cur.execute(
                "UPDATE pellier.tool_audit SET result = %s::jsonb, latency_ms = %s"
                " WHERE audit_id = %s",
                ("{}", 5, appended),
            )
    assert appended is not None

    # What the agent must NOT be able to do.
    forbidden = [
        ("read another row's arguments", "SELECT args FROM pellier.tool_audit"),
        ("read results", "SELECT result FROM pellier.tool_audit"),
        ("rewrite which tool ran", f"UPDATE pellier.tool_audit SET tool = 'x' WHERE audit_id = {appended}"),
        ("rewrite the caller", f"UPDATE pellier.tool_audit SET caller = 'x' WHERE audit_id = {appended}"),
        ("rewrite the arguments", f"UPDATE pellier.tool_audit SET args = '{{}}'::jsonb WHERE audit_id = {appended}"),
        ("delete evidence", f"DELETE FROM pellier.tool_audit WHERE audit_id = {appended}"),
    ]
    for label, statement in forbidden:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, ):
            async with db.principal_session("irrelevant-for-grants") as conn:
                async with conn.cursor() as cur:
                    await cur.execute(statement)

    # Nobody cleans this up. Since migration 047 the owner cannot delete an audit
    # row either: the receipt is evidence, and the probe row stays as one.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await db.execute_query(
            "DELETE FROM pellier.tool_audit WHERE audit_id = %s", appended
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_generated_sql_role_is_blind_to_the_ledger(db):
    """`pellier_query` must not read, write, or infer the evidence ledger."""
    import psycopg

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with db.principal_session(None, role="pellier_query") as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM pellier.tool_audit")

    # ...while still being able to read the catalog it exists to query.
    async with db.principal_session(None, role="pellier_query") as conn:
        catalog = await _scalar(conn, "SELECT count(*) FROM pellier.product_catalog")
    assert catalog > 0

# ---------------------------------------------------------------------------
# Deployment state: every named shopper must be mapped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_every_named_persona_has_a_seeded_mapping(db):
    """An unmapped signed-in shopper is denied their own data.

    This is deployment state rather than code behavior, and it is exactly the
    question a participant asks first: "I signed in as marco — why can't I see
    my order?" An empty or partial `principal_customers` table does not read
    as governance, it reads as a broken application. `scripts/
    seed_principal_mappings.py` populates it after Cognito provisioning.
    """
    from services.turn_identity import USERNAME_TO_CUSTOMER_ID

    rows = await db.fetch_all(
        "SELECT customer_id, count(*) AS subjects FROM pellier.principal_customers"
        " GROUP BY customer_id"
    )
    mapped = {row["customer_id"]: row["subjects"] for row in rows}
    expected = set(USERNAME_TO_CUSTOMER_ID.values())

    unmapped = sorted(expected - set(mapped))
    assert not unmapped, (
        f"no principal mapping for {', '.join(unmapped)} — RLS denies those "
        "shoppers their own orders. Run scripts/seed_principal_mappings.py."
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_database_scope_agrees_with_the_application_scope(db, seeded):
    """The app and the database must resolve a principal to the same customer.

    If they disagree the application believes a turn is scoped to a customer
    while the database refuses every row — a failure with no error message to
    explain it. This walks each seeded subject through RLS and checks the
    customer it can actually see is the one `turn_identity` would assign.
    """
    from services.turn_identity import USERNAME_TO_CUSTOMER_ID

    mappings = await db.fetch_all(
        "SELECT principal_sub, customer_id FROM pellier.principal_customers"
    )
    by_customer = {row["customer_id"]: row["principal_sub"] for row in mappings}

    for username, customer in sorted(USERNAME_TO_CUSTOMER_ID.items()):
        subject = by_customer.get(customer)
        if subject is None:
            pytest.fail(f"{username} ({customer}) has no seeded subject")
        async with db.principal_session(subject) as conn:
            scope = await _scalar(
                conn,
                "SELECT string_agg(DISTINCT customer_id, ',') FROM"
                " pellier.current_principal_customers()",
            )
        assert scope == customer, (
            f"{username}: application scopes to {customer}, database resolves "
            f"to {scope!r}"
        )

# ---------------------------------------------------------------------------
# The write path: two rails, and the audit-survival invariant (spec 13)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="module")
async def ordered(db) -> AsyncIterator[Dict[str, Any]]:
    """One real order per customer, so an ownership lookup can succeed."""
    await db.execute_query(
        "INSERT INTO pellier.orders (customer_id, product_id, quantity)"
        " VALUES ('CUST-MARCO','11',2), ('CUST-ANNA','21',2)"
    )
    rows = await db.fetch_all(
        "SELECT id FROM pellier.orders ORDER BY id DESC LIMIT 2"
    )
    ids = [r["id"] for r in rows]
    subjects = {
        r["customer_id"]: r["principal_sub"]
        for r in await db.fetch_all(
            "SELECT customer_id, principal_sub FROM pellier.principal_customers"
        )
    }
    try:
        yield {"order_ids": ids, "subjects": subjects}
    finally:
        await db.execute_query(
            "DELETE FROM pellier.returns WHERE customer_id IN ('CUST-MARCO','CUST-ANNA')"
        )
        await db.execute_query("DELETE FROM pellier.orders WHERE id = ANY(%s)", ids)
        # Only unfilled claims can be released. A completed write_operations row
        # is frozen evidence since migration 047, so the successful probes stay.
        await db.execute_query(
            "DELETE FROM pellier.write_operations"
            " WHERE idempotency_key LIKE %s AND completed_at IS NULL",
            f"live-{_RUN}-%",
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_owner_rail_can_process_another_customers_return(db, ordered):
    """The ungoverned baseline, stated plainly because it is the contrast.

    On the owner connection the only gate is the `customer_id` argument, which
    the caller supplies. This is what the governed rail exists to close, and a
    participant should see it succeed here before seeing it refused there.
    """
    from services.business_logic import BusinessLogic

    result = await BusinessLogic(db).initiate_return(
        "CUST-ANNA", 21, "damaged", f"live-{_RUN}-owner"
    )

    assert result["status"] == "success", result


@pytest.mark.asyncio(loop_scope="module")
async def test_governed_rail_refuses_another_customers_return(db, ordered):
    """Same request, verified principal bound: the database refuses it."""
    from services.business_logic import BusinessLogic

    marco = ordered["subjects"].get("CUST-MARCO")
    assert marco, "Marco has no seeded principal mapping"

    result = await BusinessLogic(db).initiate_return(
        "CUST-ANNA", 21, "damaged", f"live-{_RUN}-cross", principal_sub=marco
    )

    assert result["status"] == "policy_blocked", result
    assert result.get("denied_by") == "database_row_level_security"
    # The message must not claim Anna never ordered it. She did.
    assert "did not order" not in result["message"]


@pytest.mark.asyncio(loop_scope="module")
async def test_governed_rail_allows_a_principal_its_own_return(db, ordered):
    """The permitted half, so the refusal above is not a blanket failure."""
    from services.business_logic import BusinessLogic

    marco = ordered["subjects"].get("CUST-MARCO")
    result = await BusinessLogic(db).initiate_return(
        "CUST-MARCO", 11, "damaged", f"live-{_RUN}-own", principal_sub=marco
    )

    assert result["status"] == "success", result
    assert result.get("return_id")


@pytest.mark.asyncio(loop_scope="module")
async def test_denied_write_commits_no_business_change_but_leaves_a_receipt(
    db, ordered
):
    """Spec 13: 0 committed business changes plus exactly 1 attempt receipt.

    The receipt has to survive the transaction the database rejected, or the
    exercise has no evidence that the attempt happened at all.
    """
    from services.business_logic import BusinessLogic

    marco = ordered["subjects"].get("CUST-MARCO")
    key = f"live-{_RUN}-survive"

    before_returns = (
        await db.fetch_one(
            "SELECT count(*) AS n FROM pellier.returns WHERE customer_id='CUST-ANNA'"
        )
    )["n"]
    before_ledger = (
        await db.fetch_one("SELECT count(*) AS n FROM pellier.inventory_ledger")
    )["n"]

    result = await BusinessLogic(db).initiate_return(
        "CUST-ANNA", 21, "damaged", key, principal_sub=marco
    )
    assert result["status"] == "policy_blocked"

    after_returns = (
        await db.fetch_one(
            "SELECT count(*) AS n FROM pellier.returns WHERE customer_id='CUST-ANNA'"
        )
    )["n"]
    after_ledger = (
        await db.fetch_one("SELECT count(*) AS n FROM pellier.inventory_ledger")
    )["n"]

    assert after_returns == before_returns, "a denied return committed a row"
    assert after_ledger == before_ledger, "a denied return moved inventory"

    receipts = await db.fetch_all(
        "SELECT operation FROM pellier.write_operations WHERE idempotency_key = %s",
        key,
    )
    assert len(receipts) == 1, "expected exactly one attempt receipt"
    assert receipts[0]["operation"] == "initiate_return"


@pytest.mark.asyncio(loop_scope="module")
async def test_retrying_a_denied_write_does_not_duplicate_evidence(db, ordered):
    """Spec 13: retries must not make the exercise ambiguous."""
    from services.business_logic import BusinessLogic

    marco = ordered["subjects"].get("CUST-MARCO")
    key = f"live-{_RUN}-retry"
    logic = BusinessLogic(db)

    first = await logic.initiate_return(
        "CUST-ANNA", 21, "damaged", key, principal_sub=marco
    )
    second = await logic.initiate_return(
        "CUST-ANNA", 21, "damaged", key, principal_sub=marco
    )

    assert first["status"] == "policy_blocked"
    assert second["status"] in {"policy_blocked", "error"}

    receipts = await db.fetch_all(
        "SELECT count(*) AS n FROM pellier.write_operations WHERE idempotency_key = %s",
        key,
    )
    assert receipts[0]["n"] == 1, "a retry duplicated the attempt receipt"


# ---------------------------------------------------------------------------
# Migration 047: evidence immutability, proved against the live triggers
# ---------------------------------------------------------------------------
#
# Every probe below runs on one owner connection and rolls it back at the end.
# That is not tidiness: after 047 nothing can delete these rows, so a probe that
# committed would leave permanent residue on every run.


async def _expect_refused(conn: Any, statement: str, params: tuple = ()) -> None:
    """The statement must raise insufficient_privilege from the trigger.

    A savepoint around the statement keeps the surrounding probe transaction
    usable after the expected failure.
    """
    import psycopg

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(statement, params)


@pytest.mark.asyncio(loop_scope="module")
async def test_governed_and_execution_receipts_are_append_only(db):
    """UPDATE and DELETE raise on both receipt tables, even for the owner."""
    session = f"immutability-probe-{_RUN}"
    async with db.get_connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO pellier.governed_receipts"
                    " (session_id, principal_id, principal_label, tool, caller, decision)"
                    " VALUES (%s, 'probe', 'probe', 'probe', 'gateway', 'ALLOW')"
                    " RETURNING receipt_id",
                    (session,),
                )
                receipt_id = (await cur.fetchone())["receipt_id"]
            await _expect_refused(
                conn,
                "UPDATE pellier.governed_receipts SET decision = 'DENY'"
                " WHERE receipt_id = %s",
                (receipt_id,),
            )
            await _expect_refused(
                conn,
                "DELETE FROM pellier.governed_receipts WHERE receipt_id = %s",
                (receipt_id,),
            )

            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM pellier.customers ORDER BY id LIMIT 1")
                customer = (await cur.fetchone())["id"]
                await cur.execute(
                    "INSERT INTO pellier.approvals"
                    " (customer_id, tool, args, status, source_turn_id, issue,"
                    "  action_hash, decided_at, decided_by, execution_turn_id)"
                    " VALUES (%s, 'initiate_return', '{}'::jsonb, 'approved', %s,"
                    "  'probe', %s, now(), 'probe', %s) RETURNING id",
                    (customer, session, "e" * 64, "turn-" + "e" * 32),
                )
                review_id = (await cur.fetchone())["id"]
                await cur.execute(
                    "INSERT INTO pellier.execution_receipts"
                    " (execution_turn_id, review_id, tool, rail, actor_principal,"
                    "  policy_outcome, aurora_outcome, evidence_outcome, idempotency_key)"
                    " VALUES (%s, %s, 'initiate_return', 'gateway-mcp', 'probe',"
                    "  'DENY', 'NOT_REACHED', 'POLICY_PROOF', %s) RETURNING receipt_id",
                    ("turn-" + "e" * 32, review_id, session),
                )
                exec_receipt = (await cur.fetchone())["receipt_id"]
            await _expect_refused(
                conn,
                "UPDATE pellier.execution_receipts SET policy_outcome = 'ALLOW'"
                " WHERE receipt_id = %s",
                (exec_receipt,),
            )
            await _expect_refused(
                conn,
                "DELETE FROM pellier.execution_receipts WHERE receipt_id = %s",
                (exec_receipt,),
            )
        finally:
            await conn.rollback()


@pytest.mark.asyncio(loop_scope="module")
async def test_tool_audit_completes_once_and_is_then_frozen(db):
    """The writer's INSERT then UPDATE pair stays legal; anything after it raises."""
    async with db.get_connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO pellier.tool_audit (session_id, tool, caller, args)"
                    " VALUES (%s, 'probe', 'probe', '{}'::jsonb) RETURNING audit_id",
                    (f"fill-once-probe-{_RUN}",),
                )
                audit_id = (await cur.fetchone())["audit_id"]
                # The one permitted completion, exactly as tool_audit_writer issues it.
                await cur.execute(
                    "UPDATE pellier.tool_audit SET result = %s::jsonb, latency_ms = %s"
                    " WHERE audit_id = %s",
                    ('{"status":"probe"}', 7, audit_id),
                )
            await _expect_refused(
                conn,
                "UPDATE pellier.tool_audit SET result = '{}'::jsonb WHERE audit_id = %s",
                (audit_id,),
            )
            await _expect_refused(
                conn,
                "DELETE FROM pellier.tool_audit WHERE audit_id = %s",
                (audit_id,),
            )
        finally:
            await conn.rollback()


@pytest.mark.asyncio(loop_scope="module")
async def test_write_operations_moves_from_claim_to_completed_exactly_once(db):
    """Claim -> completed succeeds; a completed row refuses UPDATE and DELETE.

    An UNFILLED claim can still be released by DELETE, which is the path
    migration 023 relies on for a failed attempt.
    """
    key = f"fill-once-probe-{_RUN}"
    async with db.get_connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO pellier.write_operations"
                    " (idempotency_key, operation, request_hash)"
                    " VALUES (%s, 'initiate_return', %s)",
                    (key, "f" * 64),
                )
                await cur.execute(
                    "UPDATE pellier.write_operations"
                    " SET result = '{\"status\":\"success\"}'::jsonb, completed_at = now()"
                    " WHERE idempotency_key = %s",
                    (key,),
                )
                await cur.execute(
                    "SELECT completed_at FROM pellier.write_operations"
                    " WHERE idempotency_key = %s",
                    (key,),
                )
                assert (await cur.fetchone())["completed_at"] is not None
            await _expect_refused(
                conn,
                "UPDATE pellier.write_operations SET result = '{}'::jsonb"
                " WHERE idempotency_key = %s",
                (key,),
            )
            await _expect_refused(
                conn,
                "DELETE FROM pellier.write_operations WHERE idempotency_key = %s",
                (key,),
            )

            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO pellier.write_operations"
                    " (idempotency_key, operation, request_hash)"
                    " VALUES (%s, 'initiate_return', %s)",
                    (key + "-unfilled", "f" * 64),
                )
            await _expect_refused(
                conn,
                "UPDATE pellier.write_operations SET request_hash = %s"
                " WHERE idempotency_key = %s",
                ("0" * 64, key + "-unfilled"),
            )
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM pellier.write_operations WHERE idempotency_key = %s",
                    (key + "-unfilled",),
                )
                assert cur.rowcount == 1, "an unfilled claim must remain releasable"
        finally:
            await conn.rollback()


@pytest.mark.asyncio(loop_scope="module")
async def test_agent_role_can_complete_a_claim_but_not_rewrite_its_identity(db):
    """The narrowed grant fits the write functions and nothing more.

    `process_return_idempotent` runs as pellier_agent and finalises a claim with
    `UPDATE ... SET result, completed_at`. That must still work under the column
    grant; touching any other column is refused by the grant before the trigger
    is consulted.
    """
    import psycopg

    key = f"agent-grant-probe-{_RUN}"
    await db.execute_query(
        "INSERT INTO pellier.write_operations (idempotency_key, operation, request_hash)"
        " VALUES (%s, 'initiate_return', %s)",
        key, "a" * 64,
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with db.principal_session("irrelevant-for-grants") as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE pellier.write_operations SET request_hash = %s"
                    " WHERE idempotency_key = %s",
                    ("b" * 64, key),
                )
    async with db.principal_session("irrelevant-for-grants") as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE pellier.write_operations"
                " SET result = '{\"status\":\"success\"}'::jsonb, completed_at = now()"
                " WHERE idempotency_key = %s",
                (key,),
            )
            assert cur.rowcount == 1
    # The completed row is evidence now and stays; there is no cleanup by design.
