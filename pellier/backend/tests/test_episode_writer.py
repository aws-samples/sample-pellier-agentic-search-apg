"""The production episode writer: a derived memory of one reviewed execution.

What was wrong
--------------

``pellier.operator_episodes`` shipped in migration 024 with a module, 24 tests and no
production reader or writer. The only rows it ever held were written by a capture script
during the Phase 6B proof, which is precisely what the module's own docstring warns
against: a seeded "successful past resolution" is a story, not a record.

What this file asserts
----------------------

  * an episode is written only for a TERMINAL outcome, and the three that qualify are
    the three the live cluster produced;
  * every field is derived from durable artifacts, never from model prose;
  * one reviewed outcome yields one episode however many times the tool is replayed;
  * a failure to remember never fails the execution being remembered.

Measured live on 2026-08-27, after the writer was wired: three executions produced
episodes 36, 37 and 38 (deny/not_attempted, allow/applied, allow/refused), each with a
Bedrock embedding, and two further replays of review 40 added two execution receipts and
zero episodes.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

import pytest

from services import governed_execution as GE
from services import operator_episodes as EP

MIGRATION = pathlib.Path("../../scripts/migrations/026_episode_outcome_lineage.sql")
DATABASE_SETUP = pathlib.Path("../../scripts/setup/database-setup.sh")


def _module_source(name: str) -> str:
    """A function's source read from the FILE, not through `inspect`.

    The autouse `no_bedrock` fixture replaces `EP._embed_situation`, so `inspect` would
    return the stub and a scan of it would pass vacuously.
    """
    body = pathlib.Path("services/operator_episodes.py").read_text()
    key = f"async def {name}("
    start = body.index(key) if key in body else body.index(f"def {name}(")
    rest = body[start:]
    ends = [i for i in (rest.find(chr(10) * 3 + "async def "),
                        rest.find(chr(10) * 3 + "def ")) if i != -1]
    return rest[: min(ends)] if ends else rest


def _code_only(source: str) -> str:
    """Strip docstrings and comments, so prose cannot satisfy or break a scan."""
    out, in_doc = [], False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # A one-line docstring opens and closes on the same line.
            if len(stripped) > 3 and stripped.endswith(stripped[:3]):
                continue
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        out.append(line.split("#", 1)[0])
    return chr(10).join(out)


def _review(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "review_id": 40,
        "customer_id": "CUST-THEO",
        "status": "approved",
        "action": "initiate_return",
        "source_turn_id": "turn-" + "b" * 32,
        "args": {"reason": "damaged", "product_id": 37, "customer_id": "CUST-THEO"},
    }
    base.update(over)
    return base


def _receipt(**over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "receipt_id": 10,
        "policy_outcome": "ALLOW",
        "aurora_outcome": "PERMITTED",
        "tool": "initiate_return",
        "execution_turn_id": "turn-" + "a" * 32,
        "idempotency_key": "operator-review:40:abc",
        "gateway_action_id": "pellier-concierge-experience-target___initiate_return",
        "gateway_mode": "ENFORCE",
        "rail": "gateway-mcp",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Eligibility: only a terminal outcome is worth remembering
# ---------------------------------------------------------------------------


def test_the_three_terminal_shapes_are_the_live_ones() -> None:
    assert EP.is_terminal_outcome("ALLOW", "PERMITTED") is True
    assert EP.is_terminal_outcome("DENY", "NOT_REACHED") is True
    assert EP.is_terminal_outcome("ALLOW", "DENIED") is True


@pytest.mark.parametrize(
    ("policy", "aurora"),
    [
        ("PENDING", "NOT_EVALUATED"),   # confirmed, nothing attempted
        ("NOT_EVALUATED", "PERMITTED"),  # in-process rail, no verdict
        ("WOULD_DENY", "PERMITTED"),     # observed under LOG_ONLY, not enforced
        ("ALLOW", "NOT_REACHED"),        # permitted and never reached the database
        ("DENY", "DENIED"),              # incoherent; refuse rather than guess
    ],
)
def test_a_non_terminal_shape_writes_nothing(policy: str, aurora: str) -> None:
    """No episode, and that is a decision rather than a failure.

    A proposal, a pending review, a confirmation on its own and all four read workflows
    land here. None of them has ended, and remembering one would be inventing history.
    """
    assert EP.is_terminal_outcome(policy, aurora) is False
    assert EP.derive_episode(
        review=_review(), receipt=_receipt(policy_outcome=policy, aurora_outcome=aurora)
    ) is None


def test_a_tool_with_no_episode_kind_writes_nothing() -> None:
    """Refuse rather than file it under a kind that does not describe it."""
    assert EP.derive_episode(
        review=_review(action="some_future_tool"),
        receipt=_receipt(tool="some_future_tool"),
    ) is None


# ---------------------------------------------------------------------------
# Derivation: from artifacts, never from prose
# ---------------------------------------------------------------------------


def test_the_success_episode_matches_the_live_row() -> None:
    episode = EP.derive_episode(
        review=_review(), receipt=_receipt(), result={"return_id": 37}
    )
    assert episode is not None
    assert episode.episode_type == EP.EPISODE_RETURN_RESOLUTION
    assert (episode.human_outcome, episode.policy_outcome, episode.aurora_outcome) == (
        "confirmed", "allow", "applied",
    )
    assert episode.review_id == 40
    assert episode.execution_turn_id == "turn-" + "a" * 32
    assert episode.situation == "CUST-THEO asked for a damaged return on product 37."
    assert "Return 37 was created" in episode.resolution


def test_the_policy_denial_episode_names_the_layer_that_refused() -> None:
    episode = EP.derive_episode(
        review=_review(customer_id="CUST-RACHEL", args={
            "reason": "not_as_described", "product_id": 47,
        }),
        receipt=_receipt(policy_outcome="DENY", aurora_outcome="NOT_REACHED"),
        result={"status": "policy_denied"},
    )
    assert episode is not None
    assert (episode.policy_outcome, episode.aurora_outcome) == ("deny", "not_attempted")
    assert "AgentCore Policy refused" in episode.resolution
    assert "never entered" in episode.resolution


def test_the_database_denial_episode_keeps_the_allow() -> None:
    """The most instructive row this table can hold, and it must not be flattened."""
    episode = EP.derive_episode(
        review=_review(customer_id="CUST-AMARA", args={
            "reason": "damaged", "product_id": 46,
        }),
        receipt=_receipt(aurora_outcome="DENIED"),
        result={"status": "error", "denied_by": "database_row_level_security"},
    )
    assert episode is not None
    assert (episode.policy_outcome, episode.aurora_outcome) == ("allow", "refused")
    assert "permitted the action" in episode.resolution
    assert "row-level security refused" in episode.resolution


def test_the_human_axis_comes_from_the_approval() -> None:
    """`pellier.approvals.status` is the human axis and nothing else."""
    for status, expected in (("approved", "confirmed"), ("rejected", "declined")):
        episode = EP.derive_episode(
            review=_review(status=status), receipt=_receipt(), result={}
        )
        assert episode is not None and episode.human_outcome == expected


def test_the_evidence_summary_holds_pointers_not_business_truth() -> None:
    """Membership, stock and order state are read live from the tables that own them.

    An episode that copied them would decay silently, which is the argument migration
    021 makes about the review row and it applies here for the same reason.
    """
    episode = EP.derive_episode(
        review=_review(), receipt=_receipt(), result={"return_id": 37}
    )
    assert episode is not None
    assert set(episode.evidence_summary) == {
        "reviewId", "sourceTurnId", "executionTurnId", "receiptId",
        "idempotencyKey", "gatewayActionId", "gatewayMode", "rail",
    }
    blob = str(episode.evidence_summary) + str(episode.action_summary)
    for business in ("membership", "spend", "quantity", "price", "warehouse"):
        assert business not in blob.lower(), business


def test_a_replay_is_recorded_as_such() -> None:
    episode = EP.derive_episode(
        review=_review(),
        receipt=_receipt(),
        result={"return_id": 37, "idempotent_replay": True},
    )
    assert episode is not None
    assert episode.action_summary["idempotentReplay"] is True
    assert "replayed a write that had already applied" in episode.resolution


def test_the_situation_is_composed_not_generated() -> None:
    """No model output reaches this field.

    An episode that remembers what a model said rather than what happened is worse than
    no episode: it is a plausible sentence with the authority of a record.
    """
    import inspect

    source = _code_only(
        inspect.getsource(EP.derive_episode) + inspect.getsource(EP._situation)
    )
    for model_ish in ("bedrock", "converse", "invoke_model", "synthesize", "prompt"):
        assert model_ish not in source.lower(), model_ish


# ---------------------------------------------------------------------------
# The writer, and what it must never break
# ---------------------------------------------------------------------------


class FakeDb:
    def __init__(self, *, fail: bool = False, conflict: bool = False) -> None:
        self.fail = fail
        self.conflict = conflict
        self.statements: List[str] = []
        self.params: List[Any] = []

    def get_connection(self):
        return _Conn(self)


class _Cur:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self._one: Optional[Dict[str, Any]] = None

    async def execute(self, sql: str, params: Any = ()) -> None:
        self.db.statements.append(" ".join(sql.split()))
        self.db.params.append(params)
        if self.db.fail:
            raise RuntimeError("insert refused")
        self._one = None if self.db.conflict else {"episode_id": 42, "created_at": None}

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


@pytest.fixture(autouse=True)
def no_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding is best effort, so the unit tests must not reach Bedrock."""
    async def _none(_situation: str):
        return None

    monkeypatch.setattr(EP, "_embed_situation", _none)


@pytest.mark.asyncio
async def test_a_terminal_outcome_is_recorded() -> None:
    db = FakeDb()
    got = await EP.record_outcome_episode(
        db, review=_review(), receipt=_receipt(), result={"return_id": 37}
    )
    assert got == {"episodeId": 42, "createdAt": None, "replayed": False,
                   "recorded": True}
    insert = next(s for s in db.statements if s.startswith("INSERT"))
    assert "pellier.operator_episodes" in insert
    # The LOGICAL OUTCOME key, not the shopper turn.
    assert "ON CONFLICT (review_id, episode_type)" in insert


@pytest.mark.asyncio
async def test_a_non_terminal_outcome_is_not_recorded_and_is_not_an_error() -> None:
    db = FakeDb()
    got = await EP.record_outcome_episode(
        db, review=_review(), receipt=_receipt(policy_outcome="PENDING",
                                               aurora_outcome="NOT_EVALUATED")
    )
    assert got["recorded"] is False
    assert db.statements == []


@pytest.mark.asyncio
async def test_a_replay_reports_itself_rather_than_appending() -> None:
    """`ON CONFLICT DO NOTHING` returns no row, and that is a success."""
    got = await EP.record_outcome_episode(
        FakeDb(conflict=True), review=_review(), receipt=_receipt(),
        result={"return_id": 37},
    )
    assert got["replayed"] is True
    assert got["recorded"] is True
    assert got["episodeId"] is None


@pytest.mark.asyncio
async def test_a_write_failure_never_raises() -> None:
    """An episode is a derived memory. Losing one costs recall; raising costs a write.

    By the time this runs the approval, the receipt, `tool_audit`, `write_operations`
    and the domain rows are all durable. Reporting a completed governed mutation as a
    500 because its memory failed would invite an operator to retry it.
    """
    got = await EP.record_outcome_episode(
        FakeDb(fail=True), review=_review(), receipt=_receipt(),
        result={"return_id": 37},
    )
    assert got == {"episodeId": None, "replayed": False, "recorded": False}


@pytest.mark.asyncio
async def test_an_episode_with_no_review_uses_the_other_conflict_target() -> None:
    """Postgres resolves `ON CONFLICT` against one index, so there are two statements."""
    db = FakeDb()
    await EP.store_episode(db, EP.Episode(
        customer_id="CUST-THEO", episode_type=EP.EPISODE_INVENTORY_CORRECTION,
        situation="a background reconciliation", source_turn_id="turn-x",
    ))
    insert = next(s for s in db.statements if s.startswith("INSERT"))
    assert "ON CONFLICT (source_turn_id, episode_type)" in insert


# ---------------------------------------------------------------------------
# Embedding: best effort, and asymmetric
# ---------------------------------------------------------------------------


def test_the_stored_side_is_embedded_as_a_document() -> None:
    """Cohere Embed v4 is asymmetric.

    Embedding the stored situation with `embed_query` would measure every recall against
    the wrong half of the model, and the failure would be silent: recall would simply be
    worse than it looks.
    """
    source = _module_source("_embed_situation")
    assert "embed_document" in source
    assert "embed_query" not in _code_only(source)


def test_an_embedding_failure_leaves_the_episode_durable() -> None:
    source = _module_source("_embed_situation")
    assert "return None" in source
    # In a thread: the Bedrock call is blocking and this runs on the request loop
    # directly after a governed write.
    assert "to_thread" in source


def test_the_dimension_matches_the_schema() -> None:
    """1024, the same as the catalog and the semantic cache. One configuration."""
    body = (pathlib.Path("../../scripts/migrations/024_operator_episodes.sql")
            .read_text())
    assert "vector(1024)" in body


# ---------------------------------------------------------------------------
# The execution path calls it, and cannot be broken by it
# ---------------------------------------------------------------------------


class _OrderRecordingDb:
    """The database an execution actually talks to, in call order.

    Enough of the real surface for one in-process execution: the principal
    lookup, the execution-turn claim, and a log of every call the execution made
    through it. The receipt and the episode append their own names, so the test
    reads the sequence rather than the source text.
    """

    def __init__(self) -> None:
        self.calls: List[str] = []
        self._claimed: Optional[str] = None

    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        if "FROM pellier.principal_customers" in query:
            self.calls.append("resolve_customer_subject")
            return {"principal_sub": "sub-theo-cognito"}
        if query.strip().startswith("UPDATE pellier.approvals"):
            self.calls.append("claim_execution_turn")
            self._claimed = params[0]
            return {"execution_turn_id": params[0]}
        if "SELECT execution_turn_id" in query:
            return {"execution_turn_id": self._claimed}
        return None

    async def fetch_all(self, _query: str, *_params: Any) -> List[Dict[str, Any]]:
        return []


class _NoOpLogic:
    def __init__(self, _db: Any) -> None:
        pass

    async def initiate_return(self, **_kwargs: Any) -> Dict[str, Any]:
        return {"status": "success", "return_id": 9}


@pytest.mark.asyncio
async def test_the_execution_path_records_the_episode_after_the_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Derived from the durable row, so the memory and the evidence cannot disagree.

    Asserted by running an execution and reading the order of the calls it made,
    not by comparing the position of two identifiers in the source: that scan
    passes on a rename in a comment and fails on a rename in the code.
    """
    from services.business_logic import write_request_hash

    args = {"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"}
    review = {
        "review_id": 12, "customer_id": "CUST-THEO", "action": "initiate_return",
        "args": dict(args), "status": "approved",
        "action_hash": write_request_hash("initiate_return", **args),
        "source_turn_id": "turn-" + ("a" * 32), "order_id": 305,
        "execution_turn_id": None, "decided_by": "operator-1",
    }
    db = _OrderRecordingDb()

    async def _receipt(recorded_db: Any, *_args: Any, **_kwargs: Any) -> int:
        recorded_db.calls.append("record_receipt")
        return 77

    async def _remember(recorded_db: Any, *_args: Any, **_kwargs: Any) -> None:
        recorded_db.calls.append("_remember_outcome")

    import services.business_logic as bl
    from config import settings

    monkeypatch.setattr(bl, "BusinessLogic", _NoOpLogic)
    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "", raising=False)
    monkeypatch.setattr(GE, "record_receipt", _receipt)
    monkeypatch.setattr(GE, "_remember_outcome", _remember)

    await GE.execute_confirmed_review(db, review, operator_sub="sub-operator")

    assert db.calls == [
        "resolve_customer_subject", "claim_execution_turn",
        "record_receipt", "_remember_outcome",
    ]


@pytest.mark.asyncio
async def test_no_episode_is_remembered_when_the_receipt_could_not_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A memory derived from a receipt that does not exist would be invented."""
    from services.business_logic import write_request_hash

    args = {"customer_id": "CUST-THEO", "product_id": 37, "reason": "damaged"}
    review = {
        "review_id": 12, "customer_id": "CUST-THEO", "action": "initiate_return",
        "args": dict(args), "status": "approved",
        "action_hash": write_request_hash("initiate_return", **args),
        "source_turn_id": "turn-" + ("a" * 32), "order_id": 305,
        "execution_turn_id": None, "decided_by": "operator-1",
    }
    db = _OrderRecordingDb()

    async def _no_receipt(*_args: Any, **_kwargs: Any) -> Optional[int]:
        return None

    async def _remember(recorded_db: Any, *_args: Any, **_kwargs: Any) -> None:
        recorded_db.calls.append("_remember_outcome")

    import services.business_logic as bl
    from config import settings

    monkeypatch.setattr(bl, "BusinessLogic", _NoOpLogic)
    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "", raising=False)
    monkeypatch.setattr(GE, "record_receipt", _no_receipt)
    monkeypatch.setattr(GE, "_remember_outcome", _remember)

    outcome = await GE.execute_confirmed_review(db, review, operator_sub="sub-operator")

    assert "_remember_outcome" not in db.calls
    assert outcome.evidence == GE.EVIDENCE_PENDING


def test_the_episode_is_derived_from_the_receipt_that_was_just_written() -> None:
    """The contract of the step itself: read back, never reuse the in-flight object."""
    import inspect

    remember = inspect.getsource(GE._remember_outcome)
    assert "record_outcome_episode" in remember
    assert "latest_receipt" in remember


def test_the_execution_path_swallows_a_memory_failure() -> None:
    import inspect

    remember = _code_only(inspect.getsource(GE._remember_outcome))
    assert "except Exception" in remember
    assert "logger.warning" in remember
    # No re-raise in the body. The docstring says "Never raises", which is why this
    # scan has to look at code rather than at the whole function text.
    assert "raise" not in remember


# ---------------------------------------------------------------------------
# Migration 026
# ---------------------------------------------------------------------------


def _sql() -> str:
    """The migration with `--` comments stripped, so prose cannot satisfy a scan."""
    return "\n".join(
        line.split("--", 1)[0] for line in MIGRATION.read_text().splitlines()
    )


def test_the_migration_is_registered() -> None:
    assert "026_episode_outcome_lineage.sql" in DATABASE_SETUP.read_text()


def test_the_outcome_index_is_the_idempotency_contract() -> None:
    sql = _sql()
    assert "operator_episodes_outcome_idx" in sql
    assert "(review_id, episode_type)" in sql
    assert "WHERE review_id IS NOT NULL" in sql


def test_the_old_turn_index_gives_up_the_reviewed_rows() -> None:
    """The defect the live run found.

    With 024's index covering every row, all three governed executions raised
    `duplicate key value violates unique constraint "operator_episodes_turn_idx"` and
    the best-effort handler swallowed it: three executions, three warnings, no memories.
    """
    sql = _sql()
    assert "DROP INDEX IF EXISTS pellier.operator_episodes_turn_idx" in sql
    assert "WHERE source_turn_id IS NOT NULL AND review_id IS NULL" in sql


def test_the_review_reference_cascades() -> None:
    assert "REFERENCES pellier.approvals(id) ON DELETE CASCADE" in _sql()


def test_the_execution_turn_keeps_the_turn_id_format() -> None:
    assert "'^turn-[0-9a-f]{32}$'" in _sql()


def test_the_self_probe_covers_the_cases_that_broke() -> None:
    sql = MIGRATION.read_text()
    assert "a replayed execution appended a second episode" in sql
    assert "two review-less episodes shared a shopper turn and kind" in sql
    assert "episode(s) survived their review" in sql
    assert "accepted a malformed execution turn id" in sql


def test_the_migration_seeds_nothing() -> None:
    body = MIGRATION.read_text()
    probe = body.index("Self-probe")
    assert "INSERT INTO pellier.operator_episodes" not in body[:probe]
