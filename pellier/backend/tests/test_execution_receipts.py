"""The policy artifact: a Cedar verdict that survives the response body.

The defect this file exists to prevent
-------------------------------------

Migration 021 deferred governance state to "its own artifacts: the policy decision, the
``tool_audit`` receipt, ``write_operations``, and the domain rows". Three of those were
real. Nothing persisted the policy decision, so:

  * a Cedar DENY left no durable trace of ANY kind — correctly no ``tool_audit`` row,
    correctly no idempotency claim, and no verdict either;
  * ``GET /api/operator/reviews/{id}`` derived all four assurance axes from the human
    state alone, so three live executions with materially different outcomes (a written
    return, a policy denial, and an RLS refusal) all reported an identical
    ``policy: PENDING, aurora: NOT_EVALUATED`` on the surface built to show them apart.

So the assertions here are mostly about a row existing and a surface reading it, which
is unglamorous and is exactly what was missing.

Measured against the live cluster on 2026-08-27, and these are the three shapes:

    review 36  CUST-RACHEL  DENY  / NOT_REACHED / POLICY_PROOF     no subject
    review 40  CUST-THEO    ALLOW / PERMITTED   / RECEIPTED        subject bound
    review 41  CUST-AMARA   ALLOW / DENIED      / ATTEMPT_RECEIPT  no subject
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional

import pytest

from routes import operator as OP
from services import governed_execution as GE

MIGRATION = pathlib.Path("../../scripts/migrations/025_execution_receipts.sql")
DATABASE_SETUP = pathlib.Path("../../scripts/setup/database-setup.sh")


# ---------------------------------------------------------------------------
# Fakes. Mappings, not tuples: the pool configures `dict_row`.
# ---------------------------------------------------------------------------


class FakeDb:
    def __init__(
        self,
        *,
        insert_id: Optional[int] = 7,
        rows: Optional[List[Dict[str, Any]]] = None,
        fail: bool = False,
        violation: Optional[BaseException] = None,
    ) -> None:
        self.insert_id = insert_id
        self.rows = rows or []
        self.fail = fail
        self.violation = violation
        self.statements: List[str] = []
        self.params: List[Any] = []

    def get_connection(self):
        return _Conn(self)

    async def fetch_one(self, sql: str, *params: Any):
        self.statements.append(" ".join(sql.split()))
        self.params.append(params)
        if self.fail:
            raise RuntimeError('relation "pellier.execution_receipts" does not exist')
        return self.rows[0] if self.rows else None

    async def fetch_all(self, sql: str, *params: Any):
        self.statements.append(" ".join(sql.split()))
        self.params.append(params)
        if self.fail:
            raise RuntimeError('relation "pellier.execution_receipts" does not exist')
        return list(self.rows)


class _Cur:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self._one: Optional[Dict[str, Any]] = None

    async def execute(self, sql: str, params: Any = ()) -> None:
        flat = " ".join(sql.split())
        self.db.statements.append(flat)
        self.db.params.append(params)
        if self.db.fail:
            raise RuntimeError("insert refused")
        if self.db.violation is not None:
            raise self.db.violation
        # Mimic psycopg's arity check. The first version of `record_receipt` called
        # `db.fetch_one(sql, params)`, which forwards `*params` as a one-tuple, and the
        # driver raised "the query has 15 placeholders but 1 parameters were passed" —
        # swallowed by the best-effort handler, so no receipt was ever written and
        # nothing failed. A fake that accepts any params reproduces none of that.
        if "%(" in flat and not isinstance(params, dict):
            raise TypeError(
                f"named placeholders need a mapping, got {type(params).__name__}"
            )
        self._one = (
            {"receipt_id": self.db.insert_id} if self.db.insert_id is not None else None
        )

    async def fetchone(self):
        return self._one

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Conn:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    def cursor(self):
        return _Cur(self.db)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _outcome(**over: Any) -> GE.ExecutionOutcome:
    base: Dict[str, Any] = {
        "rail": GE.RAIL_GATEWAY,
        "execution_turn_id": "turn-" + "a" * 32,
        "idempotency_key": "operator-review:36:" + "b" * 32,
        "operator_sub": "04184458-d0e1-7066-7498-a60aa5a02bc4",
        "customer_subject": None,
        "policy": GE.POLICY_DENY,
        "aurora": GE.AURORA_NOT_REACHED,
        "evidence": GE.EVIDENCE_POLICY_PROOF,
        "tool": "give_store_credit",
        "result": {"status": "policy_denied"},
        "notes": {"policy": "Cedar denied the action; the tool was never entered."},
    }
    base.update(over)
    return GE.ExecutionOutcome(**base)


class _Engine:
    gateway_mode = "ENFORCE"
    matching_forbids = ("process_return_damaged_only",)


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_denial_is_recorded() -> None:
    """The whole point. Before this, a DENY was provable only from a live response."""
    db = FakeDb()
    receipt_id = await GE.record_receipt(
        db, _outcome(), review_id=36, engine_state=_Engine()
    )
    assert receipt_id == 7
    insert = next(s for s in db.statements if s.startswith("INSERT"))
    assert "pellier.execution_receipts" in insert
    params = next(p for p in db.params if isinstance(p, dict))
    assert params["policy_outcome"] == "DENY"
    assert params["aurora_outcome"] == "NOT_REACHED"
    assert params["evidence_outcome"] == "POLICY_PROOF"
    assert params["review_id"] == 36
    assert params["rail"] == "gateway-mcp"


@pytest.mark.asyncio
async def test_the_insert_is_passed_a_mapping_not_a_tuple() -> None:
    """The bug that made the first version silently write nothing.

    `db.fetch_one(sql, params)` forwards `*params`, so a dict became a one-tuple and
    psycopg reported 15 placeholders against 1 parameter — logged at warning and
    swallowed. This asserts the cursor form, which is the only one that binds named
    placeholders.
    """
    db = FakeDb()
    assert await GE.record_receipt(db, _outcome(), review_id=36) == 7
    assert any(isinstance(p, dict) for p in db.params)


@pytest.mark.asyncio
async def test_the_verdict_names_the_engine_and_the_mode() -> None:
    """An ALLOW without them is unattributable.

    The same word means "permitted" under ENFORCE and "observed, not enforced" under
    LOG_ONLY, and the two scopes use different enums.
    """
    db = FakeDb()
    await GE.record_receipt(
        db, _outcome(policy=GE.POLICY_ALLOW), review_id=40, engine_state=_Engine()
    )
    params = next(p for p in db.params if isinstance(p, dict))
    assert params["gateway_mode"] == "ENFORCE"
    assert params["matching_forbids"] == ["process_return_damaged_only"]
    assert params["policy_engine_id"] is not None


@pytest.mark.asyncio
async def test_the_in_process_rail_claims_no_policy_engine() -> None:
    """It consults none, so naming one would attribute a verdict that never happened."""
    db = FakeDb()
    await GE.record_receipt(
        db,
        _outcome(rail=GE.RAIL_IN_PROCESS, policy=GE.POLICY_NOT_EVALUATED),
        review_id=40,
    )
    params = next(p for p in db.params if isinstance(p, dict))
    assert params["policy_engine_id"] is None
    assert params["rail"] == "in-process"


@pytest.mark.asyncio
async def test_a_receipt_failure_never_fails_the_execution() -> None:
    """Evidence ABOUT a completed write must not turn it into an error.

    The write has already applied by the time this runs. Raising here would report a
    successful governed mutation as a 500 and invite the operator to retry it.
    """
    db = FakeDb(fail=True)
    assert await GE.record_receipt(db, _outcome(), review_id=36) is None


@pytest.mark.asyncio
async def test_a_receipt_the_table_refuses_is_a_defect_that_raises(caplog) -> None:
    """A CHECK that disagrees with the service must not lose receipts quietly.

    An outage is logged and swallowed (above). A constraint violation means the
    vocabulary written here and the table disagree, which once dropped every
    refused-rail receipt with only a warning. It raises, and says why.
    """
    import psycopg

    violation = psycopg.errors.CheckViolation(
        'new row for relation "execution_receipts" violates check constraint'
    )
    db = FakeDb(violation=violation)
    with pytest.raises(GE.ExecutionError) as raised:
        await GE.record_receipt(db, _outcome(rail=GE.RAIL_REFUSED), review_id=36)
    assert raised.value.code == "execution_receipt_rejected"
    assert raised.value.status_code == 500
    assert any("REJECTED by a constraint" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_the_notes_are_stored_as_json() -> None:
    db = FakeDb()
    await GE.record_receipt(db, _outcome(), review_id=36)
    params = next(p for p in db.params if isinstance(p, dict))
    assert json.loads(params["notes"])["policy"].startswith("Cedar denied")


# ---------------------------------------------------------------------------
# The readers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_execution_reads_as_none_not_as_a_verdict() -> None:
    """Most reviews have never executed, and that is not a DENY."""
    assert await GE.latest_receipt(FakeDb(rows=[]), 36) is None
    assert await GE.latest_receipts(FakeDb(rows=[]), [36, 40]) == {}


@pytest.mark.asyncio
async def test_an_unreadable_receipt_table_keeps_the_review_viewable() -> None:
    assert await GE.latest_receipt(FakeDb(fail=True), 36) is None
    assert await GE.latest_receipts(FakeDb(fail=True), [36]) == {}


@pytest.mark.asyncio
async def test_the_batch_read_is_one_round_trip() -> None:
    """A per-row read would scale the queue's cost with its length."""
    db = FakeDb(rows=[{"review_id": 36, "policy_outcome": "DENY"}])
    got = await GE.latest_receipts(db, [36, 40, 41])
    assert got == {36: {"review_id": 36, "policy_outcome": "DENY"}}
    assert len([s for s in db.statements if "execution_receipts" in s]) == 1


@pytest.mark.asyncio
async def test_the_batch_read_skips_the_query_for_an_empty_queue() -> None:
    db = FakeDb()
    assert await GE.latest_receipts(db, []) == {}
    assert db.statements == []


@pytest.mark.asyncio
async def test_the_reads_take_the_newest_attempt() -> None:
    """Append-only, so ordering is the whole selection logic."""
    for sql in (GE._LATEST_RECEIPT, GE._LATEST_RECEIPTS_BATCH):
        flat = " ".join(sql.split())
        assert "receipt_id DESC" in flat, flat


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------


def _receipt(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "receipt_id": 9,
        "execution_turn_id": "turn-" + "c" * 32,
        "review_id": 36,
        "tool": "give_store_credit",
        "gateway_action_id": "pellier-store-tools___give_store_credit",
        "rail": "gateway-mcp",
        "actor_principal": "operator-sub",
        "customer_subject": None,
        "policy_outcome": "DENY",
        "aurora_outcome": "NOT_REACHED",
        "evidence_outcome": "POLICY_PROOF",
        "policy_engine_id": "pellier_policy_engine-usqc5dbiek",
        "gateway_mode": "ENFORCE",
        "matching_forbids": ["process_return_damaged_only"],
        "idempotency_key": "operator-review:36:x",
        "notes": {"policy": "Cedar denied the action; the tool was never entered."},
        "created_at": None,
    }
    base.update(over)
    return base


def test_the_receipt_supersedes_the_pre_execution_reading() -> None:
    """The defect, stated as an assertion.

    `_assurance("confirmed")` is PENDING / NOT_EVALUATED, which is right before an
    execution and wrong after one. All three live outcomes read identically until this
    handoff existed.
    """
    before = OP._assurance("confirmed")
    assert before["policy"] == "PENDING"
    after = OP._assurance_from_receipt("confirmed", _receipt())
    assert after == {
        "human": "CONFIRMED",
        "policy": "DENY",
        "aurora": "NOT_REACHED",
        "evidence": "POLICY_PROOF",
    }


def test_the_human_axis_is_never_revised_by_the_receipt() -> None:
    """A confirmation is not undone by what the governance layers then decided."""
    got = OP._assurance_from_receipt(
        "confirmed", _receipt(policy_outcome="DENY")
    )
    assert got["human"] == "CONFIRMED"
    # And a declined review has no execution to read.
    assert OP._assurance_from_receipt("declined", None)["human"] == "DECLINED"


def test_no_receipt_leaves_the_pre_execution_reading_intact() -> None:
    for state in ("confirmation_required", "confirmed", "declined"):
        assert OP._assurance_from_receipt(state, None) == OP._assurance(state)


def test_the_three_live_outcomes_round_trip() -> None:
    """Exactly the rows the live cluster holds for reviews 36, 40 and 41."""
    cases = [
        ("DENY", "NOT_REACHED", "POLICY_PROOF"),
        ("ALLOW", "PERMITTED", "RECEIPTED"),
        ("ALLOW", "DENIED", "ATTEMPT_RECEIPT"),
    ]
    for policy, aurora, evidence in cases:
        got = OP._assurance_from_receipt(
            "confirmed",
            _receipt(
                policy_outcome=policy,
                aurora_outcome=aurora,
                evidence_outcome=evidence,
            ),
        )
        assert (got["policy"], got["aurora"], got["evidence"]) == (
            policy, aurora, evidence,
        )


def test_an_allow_and_an_aurora_denial_coexist() -> None:
    """Amara's row, and the reason the axes are separate columns.

    A surface that folded these into one status would have to pick a winner, and
    either choice states something false: the action WAS authorized and the database
    DID refuse it.
    """
    got = OP._assurance_from_receipt(
        "confirmed",
        _receipt(policy_outcome="ALLOW", aurora_outcome="DENIED",
                 evidence_outcome="ATTEMPT_RECEIPT"),
    )
    assert got["policy"] == "ALLOW" and got["aurora"] == "DENIED"


def test_the_payload_carries_the_attribution() -> None:
    payload = OP._receipt_payload(_receipt())
    assert payload["gatewayMode"] == "ENFORCE"
    assert payload["policyEngineId"] == "pellier_policy_engine-usqc5dbiek"
    assert payload["matchingForbids"] == ["process_return_damaged_only"]
    assert payload["rail"] == "gateway-mcp"
    assert payload["notes"]["policy"].startswith("Cedar denied")


def test_the_payload_parses_notes_that_arrive_as_text() -> None:
    payload = OP._receipt_payload(_receipt(notes='{"policy": "denied"}'))
    assert payload["notes"] == {"policy": "denied"}
    assert OP._receipt_payload(_receipt(notes="not json"))["notes"] == {}


def test_no_receipt_is_no_payload() -> None:
    assert OP._receipt_payload(None) is None


def test_the_review_payload_reports_execution_separately_from_the_axes() -> None:
    """The axes are the verdicts; `execution` is what produced them.

    A surface can render ALLOW without the attribution, but it cannot defend it.
    """
    row = {
        "review_id": 36, "customer_id": "CUST-RACHEL", "action": "give_store_credit",
        "args": {"reason": "not_as_described"}, "status": "approved",
        "action_hash": "h" * 64, "source_turn_id": "turn-src",
        "execution_turn_id": "turn-" + "c" * 32,
    }
    payload = OP._review_payload(row, _receipt())
    assert payload["assurance"]["policy"] == "DENY"
    assert payload["execution"]["gatewayMode"] == "ENFORCE"
    assert payload["executionTurnId"] == "turn-" + "c" * 32


def test_an_execution_turn_without_a_receipt_is_its_own_state() -> None:
    """An attempt began and produced no verdict. Not the same as never attempting."""
    row = {
        "review_id": 36, "customer_id": "CUST-RACHEL", "action": "give_store_credit",
        "args": {}, "status": "approved", "action_hash": "h" * 64,
        "execution_turn_id": "turn-" + "d" * 32,
    }
    payload = OP._review_payload(row, None)
    assert payload["executionTurnId"] == "turn-" + "d" * 32
    assert payload["execution"] is None
    assert payload["assurance"]["policy"] == "PENDING"


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------


def _migration() -> str:
    return MIGRATION.read_text()


def _migration_sql() -> str:
    """The migration with `--` comments stripped.

    Scanning the raw text matches this file's own prose: the note explaining why the
    turn id is NOT unique contains the word UNIQUE, so a naive search found it.
    """
    return "\n".join(
        line.split("--", 1)[0] for line in MIGRATION.read_text().splitlines()
    )


def test_the_migration_is_registered() -> None:
    assert "025_execution_receipts.sql" in DATABASE_SETUP.read_text()


def test_the_vocabularies_match_the_service() -> None:
    """A CHECK constraint that disagrees with the code fails at write time only."""
    sql = _migration_sql()
    for value in (GE.POLICY_ALLOW, GE.POLICY_DENY, GE.POLICY_NOT_EVALUATED):
        assert f"'{value}'" in sql, value
    for value in (GE.AURORA_PERMITTED, GE.AURORA_DENIED, GE.AURORA_NOT_REACHED):
        assert f"'{value}'" in sql, value
    for value in (GE.EVIDENCE_RECEIPTED, GE.EVIDENCE_POLICY_PROOF,
                  GE.EVIDENCE_ATTEMPT_RECEIPT, GE.EVIDENCE_NO_EXECUTION,
                  GE.EVIDENCE_PENDING):
        assert f"'{value}'" in sql, value
    for value in (GE.RAIL_GATEWAY, GE.RAIL_IN_PROCESS):
        assert f"'{value}'" in sql, value


def _check_values(sql: str, constraint_start: str) -> set[str]:
    """The quoted values of the first CHECK list after ``constraint_start``."""
    body = sql[sql.index(constraint_start):]
    opened = body.index("(", body.index(" IN", body.index("CHECK")))
    values = body[opened + 1 : body.index(")", opened)]
    return {part.strip().strip("'") for part in values.split(",")}


# Every value the service writes, per column. A value missing from a CHECK is a
# receipt the table refuses: refused-rail receipts carry RAIL_REFUSED and
# EVALUATION_INCOMPLETE, an output-suppressed Gateway response OUTCOME_UNKNOWN.
_WRITTEN = {
    "rail": {GE.RAIL_GATEWAY, GE.RAIL_IN_PROCESS, GE.RAIL_REFUSED},
    "policy_outcome": {GE.POLICY_ALLOW, GE.POLICY_DENY, GE.POLICY_NOT_EVALUATED,
                       GE.POLICY_EVALUATION_INCOMPLETE},
    "aurora_outcome": {GE.AURORA_PERMITTED, GE.AURORA_DENIED, GE.AURORA_NOT_REACHED,
                       GE.AURORA_OUTCOME_UNKNOWN},
    "evidence_outcome": {GE.EVIDENCE_RECEIPTED, GE.EVIDENCE_POLICY_PROOF,
                         GE.EVIDENCE_ATTEMPT_RECEIPT, GE.EVIDENCE_NO_EXECUTION,
                         GE.EVIDENCE_PENDING},
}


@pytest.mark.parametrize("column", sorted(_WRITTEN))
def test_migration_025_admits_every_value_the_service_writes(column: str) -> None:
    """The table this migration creates accepts every receipt the service writes."""
    sql = _migration_sql()
    declared = _check_values(sql, f"CHECK ({column} IN")
    assert _WRITTEN[column] <= declared, _WRITTEN[column] - declared


def test_the_later_migrations_that_redefine_the_checks_admit_them_too() -> None:
    """048 and 052 drop and re-add three of these CHECKs; the last definition wins."""
    migrations = MIGRATION.parent
    later = {
        "rail": "048_policy_decisions.sql",
        "policy_outcome": "048_policy_decisions.sql",
        "aurora_outcome": "052_replacement_recovery.sql",
    }
    for column, name in later.items():
        text = (migrations / name).read_text()
        sql = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
        declared = _check_values(sql, f"ADD CONSTRAINT execution_receipts_{column}_check")
        assert _WRITTEN[column] <= declared, (name, _WRITTEN[column] - declared)


def test_the_execution_turn_is_not_unique() -> None:
    """One row per ATTEMPT, and a retry reuses the turn.

    Theo's first attempt reported NOT_EVALUATED because the engine was unreadable and
    his replay reported ALLOW. A unique index would have forced one of those facts to
    be discarded.
    """
    sql = _migration_sql()
    assert "execution_turn_id   TEXT NOT NULL" in sql
    assert "UNIQUE" not in sql.upper()
    assert "receipt_id          BIGSERIAL PRIMARY KEY" in sql


def test_the_review_reference_cascades() -> None:
    """So the deterministic reset stays one delete instead of an ordered pair."""
    sql = _migration_sql()
    assert "REFERENCES pellier.approvals(id) ON DELETE CASCADE" in sql


def test_the_migration_seeds_nothing() -> None:
    """A receipt exists only where an execution was attempted."""
    body = _migration()
    probe = body.index("Self-probe")
    assert "INSERT INTO pellier.execution_receipts" not in body[:probe]


def test_the_self_probe_proves_both_attempts_survive() -> None:
    sql = _migration()
    assert "expected 2 retained attempts on one execution turn" in sql
    assert "accepted a malformed execution turn id" in sql
    assert "accepted a policy outcome outside the vocabulary" in sql
    # The cascade used to be proved by deleting the review. Migration 047 makes
    # execution_receipts append-only and a cascaded DELETE fires that trigger,
    # so the probe now asserts the declaration from pg_constraint instead.
    assert "does not CASCADE from" in sql
    assert "confdeltype = 'c'" in sql


def test_the_migration_does_not_widen_the_human_axis() -> None:
    """Migration 021's argument still stands: `status` is the human axis alone."""
    sql = _migration_sql()
    assert "ALTER TABLE pellier.approvals" not in sql
    for folded in ("'executed'", "'policy_denied'", "'rls_denied'"):
        assert folded not in sql, folded


# ---------------------------------------------------------------------------
# The attempt receipt across a rolled-back business transaction
#
# Closure item: the workshop guide may only claim that a refused attempt leaves
# durable evidence if that is actually true. These tests establish WHICH of the
# two possible truths the implementation has, so the wording can follow the code
# instead of the code being trusted to match the wording.
#
# The answer is A: the receipt is written on its own connection, after the
# business transaction has already resolved, and independently of whether that
# transaction committed. An RLS refusal rolls the write back and the attempt is
# still provable afterwards.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_receipt_uses_its_own_connection_not_the_business_transaction() -> None:
    """Structural guarantee behind rollback survival.

    `record_receipt` acquires a connection from the pool and inserts on it. It
    does not join, and cannot be enlisted in, whatever transaction performed the
    domain write — so a rollback there cannot take the receipt with it. If a
    future refactor threads the business connection in, this fails and the
    workshop claim has to be revisited.
    """
    db = FakeDb()
    await GE.record_receipt(db, _outcome(), review_id=41)
    insert = next(s for s in db.statements if s.startswith("INSERT"))
    assert "pellier.execution_receipts" in insert
    # The insert went through get_connection()/cursor, which is the pool's own
    # connection, rather than through a caller-supplied transaction handle.
    assert GE.record_receipt.__doc__ is not None
    source = pathlib.Path("services/governed_execution.py").read_text()
    writer = source[source.index("async def record_receipt("):]
    writer = writer[: writer.index("\n_LATEST_RECEIPT")]
    assert "db.get_connection()" in writer, (
        "record_receipt must own its connection; sharing the business "
        "transaction would let a rollback erase the attempt receipt."
    )
    assert "conn.rollback" not in writer and "conn.commit" not in writer, (
        "the pool's connection is autocommit for this insert; explicit "
        "transaction control here would couple the receipt to the write."
    )


@pytest.mark.asyncio
async def test_an_aurora_refusal_still_records_the_attempt() -> None:
    """The row that makes "two independent layers" provable.

    Cedar permitted the invocation and PostgreSQL refused the write, so the
    domain tables hold nothing and `tool_audit` may hold nothing for this key.
    The attempt receipt is the only artifact that can distinguish this from a
    call that never happened, so it must exist and must say both things.
    """
    db = FakeDb()
    receipt_id = await GE.record_receipt(
        db,
        _outcome(policy=GE.POLICY_ALLOW, aurora=GE.AURORA_DENIED),
        review_id=41,
        engine_state=_Engine(),
    )
    assert receipt_id == 7
    params = next(p for p in db.params if isinstance(p, dict))
    assert params["policy_outcome"] == "ALLOW"
    assert params["aurora_outcome"] == "DENIED"
    # Not RECEIPTED: nothing durable was written, so the evidence class must not
    # imply that it was.
    assert params["evidence_outcome"] != GE.EVIDENCE_RECEIPTED


@pytest.mark.asyncio
async def test_the_receipt_write_is_ordered_after_the_business_outcome() -> None:
    """The receipt describes a resolved attempt, never predicts one.

    `execute_governed_action` classifies the Aurora result and only then records.
    Recording first would produce a receipt whose `aurora_outcome` was a guess,
    and a crash between the two would leave a confident row about a write that
    never landed.
    """
    source = pathlib.Path("services/governed_execution.py").read_text()
    classify_at = source.index("evidence = classify_evidence_for(")
    record_at = source.index("receipt_id = await record_receipt(")
    assert classify_at < record_at, (
        "classification must precede the receipt insert so the stored axes and "
        "the returned payload cannot disagree."
    )


def test_the_receipt_is_append_only_per_attempt() -> None:
    """A retry must not overwrite the attempt it followed.

    Rollback survival is worth nothing if the next attempt silently replaces the
    refused one: the pair is the evidence.
    """
    migration = MIGRATION.read_text()
    assert "ON CONFLICT" not in migration.upper() or "DO NOTHING" in migration.upper(), (
        "an upsert on this table would let a later attempt erase an earlier "
        "refusal; migration 025 keeps one row per attempt."
    )
