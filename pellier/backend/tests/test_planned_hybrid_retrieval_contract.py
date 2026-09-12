"""Contract tests for the shared search executor.

``execute_search_plan`` is the retrieval pipeline the storefront tool, the
Observatory strategies, the Lab 2 receipt, the micro-eval, and the eval harness
all run. These tests pin its stage order, its pool bound, its tolerance for a
row value it cannot read, and its refusal to return a row that breaks a hard
constraint even when the reranker put it first.

Two paths deliberately do not run it and are out of scope here: the Operator
Concierge's ``replacement_search.find_replacements`` and the Observatory's
``app.explain_search``. The module docstring in
``services/planned_hybrid_retrieval.py`` says why.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

import pytest

from services.planned_hybrid_retrieval import (
    SearchExecution,
    SearchStage,
    execute_search_plan,
)
from services.search_plan import (
    RELAXATION_POLICY_STRICT,
    STRATEGY_HYBRID,
    STRATEGY_VECTOR,
    build_plan,
)


def _normalized(sql: str) -> str:
    """Collapse SQL whitespace so a match survives reindentation.

    ``hybrid_search._indent_clauses`` decides how a predicate is laid out in
    the branch SQL. A fixture that matched on its exact newline and padding
    was pinned to that formatting: reflowing the generated SQL, which changes
    nothing a database sees, would silently stop the predicate from being
    recognized and quietly change what these tests assert.
    """
    return " ".join(sql.split())


class _FakeCursor:
    """One cursor shared by both branches; picks rows by the SQL it sees."""

    def __init__(self, rows: List[Dict[str, Any]], *, empty_when: str = "") -> None:
        self._rows = rows
        self._empty_when = _normalized(empty_when)
        self._last: List[Dict[str, Any]] = []
        self.sql_seen: List[str] = []

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> None:
        self.sql_seen.append(sql)
        normalized = _normalized(sql)
        if self._empty_when and self._empty_when in normalized:
            self._last = []
        elif "<=>" in normalized or "to_tsquery" in normalized:
            self._last = list(self._rows)
        else:
            self._last = []

    async def fetchall(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._last]


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakeDB:
    def __init__(self, rows: List[Dict[str, Any]], *, empty_when: str = "") -> None:
        self.cursor = _FakeCursor(rows, empty_when=empty_when)

    @asynccontextmanager
    async def get_connection(self):
        yield _FakeConnection(self.cursor)


class _RecordingReranker:
    """Reverses the pool so rerank order is distinguishable from RRF order."""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.unavailable = unavailable

    def __call__(self, *, query: str, documents: List[str], top_n: int) -> List[Dict]:
        self.calls.append({"query": query, "documents": list(documents), "top_n": top_n})
        if self.unavailable:
            return []
        return [
            {"index": index, "relevance_score": 0.9 - index * 0.1}
            for index in reversed(range(min(top_n, len(documents))))
        ]


def _row(product_id: int, **extra: Any) -> Dict[str, Any]:
    base = {
        "product_id": str(product_id),
        "name": f"Product {product_id}",
        "description": f"Description {product_id}",
        "category": "Home Decor",
        "price": 40.0 + product_id,
        "tags": ["home", "gift"],
        "quantity": 12,
        "updated_at": "2026-09-04T00:00:00+00:00",
    }
    base.update(extra)
    return base


def _embed(_query: str) -> List[float]:
    return [0.01] * 1024


def _plan(**overrides: Any) -> Any:
    extracted = {
        "price_max_usd": 100,
        "in_stock_only": True,
        "soft_signal": "considered housewarming gift",
    }
    extracted.update(overrides.pop("extracted", {}))
    return build_plan("A housewarming gift under $100", extracted, **overrides)


def _run(db: Any, *, plan: Any, limit: int = 5, rerank: Any = None, **kwargs: Any):
    rerank = rerank if rerank is not None else _RecordingReranker()
    return asyncio.run(
        execute_search_plan(
            db,
            plan=plan,
            query="A housewarming gift under $100",
            limit=limit,
            embed=_embed,
            rerank=rerank,
            config=kwargs.pop("config", {}),
            **kwargs,
        )
    )


def test_candidate_budget_edit_changes_what_the_live_reranker_receives(monkeypatch) -> None:
    from services import planned_hybrid_retrieval as retrieval

    db = _FakeDB([_row(i) for i in range(1, 7)])
    before_reranker = _RecordingReranker()
    monkeypatch.setattr(retrieval, "DEFAULT_RERANK_POOL_K", 3)
    before = _run(db, plan=_plan(), rerank=before_reranker)
    after_reranker = _RecordingReranker()
    monkeypatch.setattr(retrieval, "DEFAULT_RERANK_POOL_K", 20)
    after = _run(db, plan=_plan(), rerank=after_reranker)

    assert len(before_reranker.calls[0]["documents"]) == 3
    assert len(after_reranker.calls[0]["documents"]) == 6
    assert "6" not in {row["product_id"] for row in before.returned}
    assert "6" in {row["product_id"] for row in after.returned}
    assert all(row["price"] <= 100 and row["quantity"] > 0 for row in after.returned)
    assert retrieval.resolve_rerank_pool_k({"rerank_pool_k": 3}) == 3


def test_execution_runs_embed_hybrid_rerank_then_eligibility_in_order() -> None:
    db = _FakeDB([_row(1), _row(2), _row(3), _row(4)])

    execution = _run(db, plan=_plan(), limit=3, config={"rerank_pool_k": 20})

    assert isinstance(execution, SearchExecution)
    assert [stage.name for stage in execution.stages] == [
        "embed",
        "hybrid",
        "rerank",
        "eligibility",
    ]
    assert all(isinstance(stage, SearchStage) for stage in execution.stages)
    assert all(stage.latency_ms >= 0 for stage in execution.stages)
    assert execution.search_method == "hybrid+rerank"
    assert len(execution.returned) == 3
    assert len(execution.ordered) == 4
    # Rerank reversed the pool, so the last RRF row leads.
    assert execution.returned[0]["product_id"] == "4"


def test_a_row_breaking_the_price_ceiling_after_rerank_is_dropped() -> None:
    # The fake ignores SQL predicates, so the $150 row reaches the reranker,
    # which puts it first. The eligibility recheck must still refuse it.
    db = _FakeDB([_row(1), _row(2), _row(3, price=150.0)])

    execution = _run(db, plan=_plan(), limit=5)

    assert "3" not in [row["product_id"] for row in execution.ordered]
    assert "3" not in [row["product_id"] for row in execution.returned]
    assert execution.stages[-1].count == 2


def test_out_of_stock_and_excluded_rows_are_dropped_after_rerank() -> None:
    db = _FakeDB(
        [
            _row(1),
            _row(2, quantity=0),
            _row(3, tags=["candle", "home"]),
        ]
    )
    plan = _plan(extracted={"exclusions": ["candle"]})

    execution = _run(db, plan=plan, limit=5)

    assert [row["product_id"] for row in execution.returned] == ["1"]


def test_returned_never_exceeds_limit() -> None:
    db = _FakeDB([_row(index) for index in range(1, 9)])

    execution = _run(db, plan=_plan(), limit=2, config={"rerank_pool_k": 20})

    assert len(execution.returned) == 2
    assert len(execution.ordered) == 8


def test_rerank_pool_k_bounds_the_documents_the_reranker_sees() -> None:
    db = _FakeDB([_row(index) for index in range(1, 9)])
    reranker = _RecordingReranker()

    execution = _run(db, plan=_plan(), limit=5, rerank=reranker, config={"rerank_pool_k": 3})

    assert len(reranker.calls) == 1
    assert len(reranker.calls[0]["documents"]) == 3
    assert execution.rerank_pool_k == 3
    assert [row["product_id"] for row in execution.rerank_pool] == ["1", "2", "3"]
    assert len(execution.candidates) == 8
    # A pool of three can never fill five slots; that shortfall is evidence.
    assert len(execution.returned) == 3


def test_rerank_pool_k_has_a_floor_of_three() -> None:
    db = _FakeDB([_row(index) for index in range(1, 6)])
    reranker = _RecordingReranker()

    execution = _run(db, plan=_plan(), rerank=reranker, config={"rerank_pool_k": 1})

    assert execution.rerank_pool_k == 3
    assert len(reranker.calls[0]["documents"]) == 3


def test_reranker_scores_the_plans_soft_signal_not_the_raw_query() -> None:
    db = _FakeDB([_row(1), _row(2)])
    reranker = _RecordingReranker()

    _run(db, plan=_plan(), rerank=reranker)

    assert reranker.calls[0]["query"] == "considered housewarming gift"


def test_rerank_fallback_keeps_rrf_order_and_says_so() -> None:
    db = _FakeDB([_row(1), _row(2), _row(3)])

    execution = _run(db, plan=_plan(), rerank=_RecordingReranker(unavailable=True))

    assert execution.search_method == "hybrid (rerank fallback to RRF order)"
    assert [row["product_id"] for row in execution.ordered] == ["1", "2", "3"]
    assert all(row["rerank_score"] is None for row in execution.ordered)
    assert execution.stage("rerank").count == 0


def test_relaxation_widens_soft_tags_when_the_strict_pass_is_short() -> None:
    # Rows exist only once the soft ``tags ?| %s`` predicate is gone.
    db = _FakeDB([_row(1), _row(2)], empty_when="AND tags ?| %s")
    plan = _plan(extracted={"tags": ["gift"]})

    execution = _run(db, plan=plan, limit=2)

    assert execution.relaxation_steps == ["drop_tags"]
    assert [r.step for r in execution.plan.relaxations] == ["drop_tags"]
    assert [row["product_id"] for row in execution.returned] == ["2", "1"]
    assert [stage.name for stage in execution.stages].count("hybrid") == 2


def test_relaxation_is_off_when_the_caller_says_so() -> None:
    db = _FakeDB([_row(1), _row(2)], empty_when="AND tags ?| %s")
    plan = _plan(extracted={"tags": ["gift"]})

    execution = _run(db, plan=plan, limit=2, relax=False)

    assert execution.relaxation_steps == []
    assert execution.returned == []
    assert [stage.name for stage in execution.stages].count("hybrid") == 1


def test_strict_policy_never_widens_even_when_short() -> None:
    db = _FakeDB([_row(1)], empty_when="AND tags ?| %s")
    plan = _plan(
        extracted={"tags": ["gift"]}, relaxation_policy=RELAXATION_POLICY_STRICT
    )

    execution = _run(db, plan=plan, limit=5)

    assert execution.relaxation_steps == []
    assert execution.returned == []


def test_hybrid_strategy_skips_the_reranker() -> None:
    db = _FakeDB([_row(1), _row(2), _row(3)])
    reranker = _RecordingReranker()
    plan = _plan(retrieval_strategy=STRATEGY_HYBRID)

    execution = _run(db, plan=plan, rerank=reranker)

    assert reranker.calls == []
    assert execution.search_method == "hybrid"
    assert [stage.name for stage in execution.stages] == ["embed", "hybrid", "eligibility"]
    assert [row["product_id"] for row in execution.returned] == ["1", "2", "3"]


def test_vector_strategy_runs_only_the_vector_branch() -> None:
    db = _FakeDB([_row(1), _row(2)])
    reranker = _RecordingReranker()
    plan = _plan(retrieval_strategy=STRATEGY_VECTOR)

    execution = _run(db, plan=plan, rerank=reranker)

    assert reranker.calls == []
    assert execution.search_method == "vector"
    assert [stage.name for stage in execution.stages] == ["embed", "vector", "eligibility"]
    assert all("<=>" in sql for sql in db.cursor.sql_seen)
    assert [row["vec_rank"] for row in execution.returned] == [1, 2]


def test_hard_predicates_reach_both_branches_before_fusion() -> None:
    db = _FakeDB([_row(1)])

    _run(db, plan=_plan(), limit=1)

    assert len(db.cursor.sql_seen) == 2
    for sql in db.cursor.sql_seen:
        assert "price <= %s" in sql
        assert "quantity > 0" in sql


def test_latency_breakdown_sums_every_stage_by_name() -> None:
    db = _FakeDB([_row(1), _row(2)], empty_when="AND tags ?| %s")
    plan = _plan(extracted={"tags": ["gift"]})

    execution = _run(db, plan=plan, limit=2)

    breakdown = execution.latency_breakdown()
    assert set(breakdown) == {"embed", "hybrid", "rerank", "eligibility"}
    assert all(value >= 0 for value in breakdown.values())


def test_limit_below_one_is_clamped() -> None:
    db = _FakeDB([_row(1), _row(2)])

    execution = _run(db, plan=_plan(), limit=0)

    assert len(execution.returned) == 1


@pytest.mark.parametrize("name", ["retrieve_planned_hybrid", "rerank_hybrid_candidates"])
def test_private_comparison_helpers_are_gone(name: str) -> None:
    """One executor replaces the two half-pipelines the Observatory used."""
    import services.planned_hybrid_retrieval as module

    assert not hasattr(module, name)


@pytest.mark.parametrize("price", ["not a price", "", None, object(), True])
def test_an_uncoercible_price_is_absent_evidence_not_a_violation(price: Any) -> None:
    """A row the recheck cannot judge must not 500 the route it is serving."""
    db = _FakeDB([_row(1), _row(2, price=price)])

    execution = _run(db, plan=_plan(), limit=5)

    assert [row["product_id"] for row in execution.returned] == ["2", "1"]


@pytest.mark.parametrize("quantity", ["plenty", None, object(), 12.0])
def test_an_uncoercible_quantity_is_absent_evidence_not_a_violation(
    quantity: Any,
) -> None:
    db = _FakeDB([_row(1), _row(2, quantity=quantity)])

    execution = _run(db, plan=_plan(), limit=5)

    assert "2" in [row["product_id"] for row in execution.returned]


def test_a_numeric_string_over_the_ceiling_is_still_refused() -> None:
    """Coercion widens what can be judged; it never weakens the judgment."""
    db = _FakeDB([_row(1), _row(2, price="150.00"), _row(3, quantity="0")])

    execution = _run(db, plan=_plan(), limit=5)

    assert [row["product_id"] for row in execution.returned] == ["1"]


@pytest.mark.parametrize(
    "value,expected",
    [
        (100, 100.0),
        (100.5, 100.5),
        (Decimal("99.99"), 99.99),
        ("42", 42.0),
        (" 42 ", 42.0),
        (None, None),
        ("", None),
        ("plenty", None),
        (True, None),
        (False, None),
        ([], None),
        (object(), None),
    ],
)
def test_row_values_coerce_to_a_number_or_to_absent(
    value: Any, expected: Optional[float]
) -> None:
    """Absent, not zero. Zero would invent a violation the evidence lacks."""
    from services.planned_hybrid_retrieval import _as_number

    assert _as_number(value) == expected


def test_the_micro_eval_violation_count_also_survives_an_unreadable_row() -> None:
    """``_breaks_price_or_stock`` scores returned rows and must not raise."""
    from services.planned_hybrid_retrieval import _breaks_price_or_stock

    plan = _plan()

    assert _breaks_price_or_stock(_row(1, price="wildly expensive"), plan) is False
    assert _breaks_price_or_stock(_row(1, quantity="none left"), plan) is False
    assert _breaks_price_or_stock(_row(1, price="150.00"), plan) is True
    assert _breaks_price_or_stock(_row(1, quantity="0"), plan) is True
