"""Episodic memory: one row per durable outcome, and an honest empty state.

The temptation this file guards against is seeding plausible history. An empty
episode store is the correct state until a governed resolution actually completes, and
a surface that shows "3 similar situations resolved successfully" from fixture rows is
demonstrating something the system has never done.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, List, Optional

import pytest

from services import operator_episodes as EP

MIGRATION = pathlib.Path("../../scripts/migrations/024_operator_episodes.sql")


class FakeDb:
    """Mappings, not tuples: the pool configures `dict_row`."""

    def __init__(self, *, rows: Optional[List[Dict[str, Any]]] = None,
                 conflict: bool = False, fail: bool = False) -> None:
        self.rows = rows or []
        self.conflict = conflict
        self.fail = fail
        self.statements: List[str] = []
        self.params: List[Any] = []

    def get_connection(self):
        return _Conn(self)


class _Cur:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self._rows: List[Dict[str, Any]] = []
        self._one: Optional[Dict[str, Any]] = None

    async def execute(self, sql: str, params: Any = ()) -> None:
        flat = " ".join(sql.split())
        self.db.statements.append(flat)
        self.db.params.append(params)
        if self.db.fail:
            raise RuntimeError("relation does not exist")
        if flat.startswith("INSERT"):
            self._one = None if self.db.conflict else {
                "episode_id": 1, "created_at": None,
            }
        else:
            self._rows = list(self.db.rows)

    async def fetchone(self):
        return self._one

    async def fetchall(self):
        return self._rows

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


def _episode(**overrides: Any) -> EP.Episode:
    base: Dict[str, Any] = {
        "customer_id": "CUST-THEO",
        "episode_type": EP.EPISODE_RETURN_RESOLUTION,
        "situation": "Damaged item returned; refund disputed.",
        "source_turn_id": "turn-1",
        "human_outcome": "confirmed",
        "policy_outcome": "allow",
        "aurora_outcome": "applied",
        "resolution": "Return applied exactly once.",
    }
    base.update(overrides)
    return EP.Episode(**base)


# ---------------------------------------------------------------------------
# Schema agreement
# ---------------------------------------------------------------------------

def test_episode_types_match_the_migration() -> None:
    """A Python-side list that drifts from the CHECK constraint fails at write time."""
    text = MIGRATION.read_text()
    block = text[text.index("CHECK (episode_type IN"):]
    block = block[: block.index("))")]
    in_sql = set(re.findall(r"'([a-z_]+)'", block))
    assert in_sql == set(EP.EPISODE_TYPES)


def test_the_three_outcome_vocabularies_match_the_migration() -> None:
    text = MIGRATION.read_text()
    for column, values in (
        ("human_outcome", EP.HUMAN_OUTCOMES),
        ("policy_outcome", EP.POLICY_OUTCOMES),
        ("aurora_outcome", EP.AURORA_OUTCOMES),
    ):
        block = text[text.index(f"CHECK ({column} IN"):]
        block = block[: block.index("))")]
        assert set(re.findall(r"'([a-z_]+)'", block)) == set(values), column


def test_the_migration_is_forward_only_and_additive() -> None:
    text = MIGRATION.read_text()
    assert "CREATE TABLE IF NOT EXISTS pellier.operator_episodes" in text
    for destructive in ("DROP TABLE", "ALTER TABLE pellier.messages",
                        "DELETE FROM", "TRUNCATE"):
        assert destructive not in text, f"migration 024 is not additive: {destructive}"
    # No seed rows: an empty store is the honest state.
    assert "INSERT INTO pellier.operator_episodes" not in text


def test_the_embedding_matches_the_repository_convention() -> None:
    text = MIGRATION.read_text()
    assert "vector(1024)" in text
    # One embedding configuration for the whole application: same dimension as the
    # catalog (migration 001) and the semantic cache (migration 019).
    catalog = pathlib.Path("../../scripts/migrations/001_schema.sql").read_text()
    assert "vector(1024)" in catalog


def test_a_replay_cannot_append_a_second_episode() -> None:
    text = MIGRATION.read_text()
    assert "CREATE UNIQUE INDEX IF NOT EXISTS operator_episodes_turn_idx" in text
    assert "(source_turn_id, episode_type)" in text


def test_hnsw_is_deferred_with_a_stated_threshold() -> None:
    """An index on an empty table buys nothing; the reason is recorded, not implied."""
    text = MIGRATION.read_text()
    assert "USING hnsw" not in text.split("-- No HNSW index yet")[0]
    assert "thousand rows" in text
    # Lexical retrieval IS indexed, because hybrid recall should be possible from day
    # one and a GIN index over a small table costs nothing.
    assert "USING gin (to_tsvector('english', situation))" in text


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_episode_is_stored_with_its_three_outcomes_apart() -> None:
    db = FakeDb()
    result = await EP.store_episode(db, _episode(
        human_outcome="confirmed", policy_outcome="allow", aurora_outcome="rolled_back",
    ))
    assert result["episodeId"] == 1 and result["replayed"] is False
    params = db.params[0]
    # A Cedar ALLOW beside an Aurora rollback is the most instructive row here, and it
    # survives only because the three are separate columns.
    assert params["human_outcome"] == "confirmed"
    assert params["policy_outcome"] == "allow"
    assert params["aurora_outcome"] == "rolled_back"


@pytest.mark.asyncio
async def test_a_replayed_write_is_a_success_not_a_failure() -> None:
    db = FakeDb(conflict=True)
    result = await EP.store_episode(db, _episode())
    assert result["replayed"] is True
    assert result["episodeId"] is None


@pytest.mark.asyncio
async def test_an_unknown_episode_type_is_refused_before_the_database() -> None:
    db = FakeDb()
    with pytest.raises(EP.EpisodeError) as exc:
        await EP.store_episode(db, _episode(episode_type="vibes"))
    assert exc.value.code == "unknown_episode_type:vibes"
    assert db.statements == [], "a refused episode still reached Aurora"


@pytest.mark.asyncio
async def test_the_required_fields_are_refused_when_missing() -> None:
    for overrides, code in (
        ({"customer_id": " "}, "customer_required"),
        ({"situation": ""}, "situation_required"),
        ({"human_outcome": "maybe"}, "unknown_human_outcome:maybe"),
        ({"policy_outcome": "sort_of"}, "unknown_policy_outcome:sort_of"),
        ({"aurora_outcome": "probably"}, "unknown_aurora_outcome:probably"),
    ):
        with pytest.raises(EP.EpisodeError) as exc:
            await EP.store_episode(FakeDb(), _episode(**overrides))
        assert exc.value.code == code


@pytest.mark.asyncio
async def test_an_episode_is_durable_without_an_embedding() -> None:
    """An embedding call that fails must not be able to lose the outcome."""
    db = FakeDb()
    await EP.store_episode(db, _episode())
    assert db.params[0]["embedding"] is None
    db2 = FakeDb()
    await EP.store_episode(db2, _episode(), embedding=[0.1] * 1024)
    assert len(db2.params[0]["embedding"]) == 1024


@pytest.mark.asyncio
async def test_json_columns_are_serialized_not_passed_as_dicts() -> None:
    db = FakeDb()
    await EP.store_episode(db, _episode(
        evidence_summary={"ticket": "TKT-1"}, action_summary={"tool": "give_store_credit"},
    ))
    assert json.loads(db.params[0]["evidence_summary"]) == {"ticket": "TKT-1"}
    assert json.loads(db.params[0]["action_summary"]) == {"tool": "give_store_credit"}


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------

def _row(**overrides: Any) -> Dict[str, Any]:
    base = {
        "episode_id": 7, "customer_id": "CUST-THEO", "source_turn_id": "turn-1",
        "session_id": "sess-1", "episode_type": EP.EPISODE_RETURN_RESOLUTION,
        "situation": "Damaged item returned.", "evidence_summary": {},
        "action_summary": {}, "human_outcome": "confirmed", "policy_outcome": "allow",
        "aurora_outcome": "applied", "resolution": "Applied once.",
        "created_at": None, "similarity": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_an_empty_store_recalls_nothing() -> None:
    """The correct answer today, and the caller must render it as such."""
    assert await EP.retrieve_episodes(FakeDb(rows=[]), customer_id="CUST-THEO") == []


@pytest.mark.asyncio
async def test_recall_is_scoped_to_one_client() -> None:
    db = FakeDb(rows=[_row()])
    await EP.retrieve_episodes(db, customer_id="CUST-THEO")
    assert db.params[0]["customer_id"] == "CUST-THEO"
    assert "customer_id = %(customer_id)s" in db.statements[0]


@pytest.mark.asyncio
async def test_the_optional_type_filter_is_cast_so_the_query_plans() -> None:
    """Regression: an untyped NULL parameter made every recall raise.

    PostgreSQL cannot infer a type for a parameter used only in `IS NULL`, so the read
    failed with "could not determine data type of parameter $2" — and the best-effort
    handler turned that into an empty list, indistinguishable from "no episodes".
    """
    db = FakeDb(rows=[_row()])
    await EP.retrieve_episodes(db, customer_id="CUST-THEO")
    assert "%(episode_type)s::text IS NULL" in db.statements[0]

    embedded = FakeDb(rows=[_row(similarity=0.82)])
    await EP.retrieve_episodes(embedded, customer_id="CUST-THEO",
                               embedding=[0.0] * 1024)
    assert "%(episode_type)s::text IS NULL" in embedded.statements[0]


@pytest.mark.asyncio
async def test_semantic_recall_uses_cosine_over_pgvector() -> None:
    db = FakeDb(rows=[_row(similarity=0.82)])
    episodes = await EP.retrieve_episodes(
        db, customer_id="CUST-THEO", embedding=[0.0] * 1024
    )
    sql = db.statements[0]
    assert "embedding <=> %(embedding)s::vector" in sql
    # Rows with no embedding are excluded, not treated as maximally distant.
    assert "embedding IS NOT NULL" in sql
    assert episodes[0].similarity == 0.82


@pytest.mark.asyncio
async def test_recall_is_bounded() -> None:
    db = FakeDb(rows=[_row()])
    await EP.retrieve_episodes(db, customer_id="CUST-THEO", limit=500)
    assert db.params[0]["limit"] == 25, "unbounded history is a cost, not a feature"


@pytest.mark.asyncio
async def test_a_read_failure_recalls_nothing_rather_than_raising() -> None:
    assert await EP.retrieve_episodes(FakeDb(fail=True), customer_id="X") == []


def test_a_broken_recall_query_is_logged_loudly() -> None:
    """The handler also swallows a malformed query, so it must not whisper."""
    import inspect

    source = inspect.getsource(EP.retrieve_episodes)
    assert "logger.warning" in source
    assert "logger.info" not in source


# ---------------------------------------------------------------------------
# Not a per-turn log, and not the narrative seed
# ---------------------------------------------------------------------------

def test_no_read_workflow_writes_an_episode() -> None:
    """The Concierge is read-only: three workflows, zero episodes."""
    import inspect

    from services import operator_concierge as ORCH

    source = inspect.getsource(ORCH)
    assert "store_episode" not in source, (
        f"{ORCH.__name__} writes an episode from a read workflow"
    )


def test_the_narrative_seed_is_not_the_episode_store() -> None:
    import inspect

    source = inspect.getsource(EP)
    # Named in the docstring to keep the distinction, never read or written.
    assert "customer_episodic_seed" in source
    assert "FROM pellier.customer_episodic_seed" not in source
    assert "INSERT INTO pellier.customer_episodic_seed" not in source


# ---------------------------------------------------------------------------
# Episodes come from outcomes, not from proposals
# ---------------------------------------------------------------------------

def test_the_three_governance_outcomes_map_to_distinct_episode_tuples() -> None:
    """Proven live 2026-08-27. Each boundary produces a different tuple."""
    tuples = {
        "theo":   ("confirmed", "allow", "applied"),
        "rachel": ("confirmed", "deny", "not_attempted"),
        "amara":  ("confirmed", "allow", "refused"),
    }
    assert len(set(tuples.values())) == 3, "two outcomes share a tuple"
    for human, policy, aurora in tuples.values():
        assert human in EP.HUMAN_OUTCOMES
        assert policy in EP.POLICY_OUTCOMES
        assert aurora in EP.AURORA_OUTCOMES


def test_a_policy_denied_outcome_records_no_aurora_attempt() -> None:
    """Rachel: the tool never ran, so the database was never asked."""
    episode = _episode(human_outcome="confirmed", policy_outcome="deny",
                       aurora_outcome="not_attempted",
                       resolution="Action not authorized.")
    payload = episode.to_payload()
    assert payload["policyOutcome"] == "deny"
    assert payload["auroraOutcome"] == "not_attempted"
    # And it must not be phrased as a business failure.
    assert "failed" not in payload["resolution"].lower()


def test_an_rls_denied_outcome_records_policy_allow_and_aurora_refused() -> None:
    """Amara: the two boundaries disagreed, and both are on the record."""
    episode = _episode(
        human_outcome="confirmed", policy_outcome="allow", aurora_outcome="refused",
        resolution="No business mutation. The order relationship exists; it was not "
                   "visible to the database session.",
    )
    payload = episode.to_payload()
    assert (payload["policyOutcome"], payload["auroraOutcome"]) == ("allow", "refused")
    # The episode describes what happened, never rewriting the underlying business truth.
    assert "order relationship exists" in payload["resolution"]
    assert "did not order" not in payload["resolution"]
