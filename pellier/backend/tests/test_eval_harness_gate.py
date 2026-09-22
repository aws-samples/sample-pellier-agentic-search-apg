"""Tests for the retrieval harness's CI gate and scoring layers.

The harness itself needs Aurora and Bedrock, so these tests exercise the
pure functions: threshold evaluation, planner scoring, and hard-constraint
compliance. Those are the parts that decide whether CI passes, and before
this suite existed the harness returned exit code 0 unconditionally — a
relevance regression was invisible to CI by construction.
"""

from __future__ import annotations

import contextlib
import importlib.util
from pathlib import Path
from typing import Any

import pytest

_HARNESS_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "eval_retrieval_harness.py"
)


def _load_harness() -> Any:
    """Import the standalone harness script as a module.

    The module must be registered in ``sys.modules`` before execution:
    its dataclasses are defined under ``from __future__ import
    annotations``, and ``dataclasses`` resolves a class's module by name
    at decoration time.
    """
    import sys

    spec = importlib.util.spec_from_file_location(
        "eval_retrieval_harness", _HARNESS_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness() -> Any:
    return _load_harness()


def _saved_comparison(harness: Any, comparison_id: str, candidates: list[str], products: list[str]) -> dict[str, Any]:
    return {
        "query": harness._ANNA_QUERY,
        "receipt": {"persisted": True, "comparisonId": comparison_id},
        "strategies": [{
            "shares_storefront_executor": True,
            "searchPlan": {"hard_constraints": {"price_max_usd": 100, "in_stock_only": True}},
            "rerank": {"status": "applied", "model": "test-reranker", "candidateIds": candidates, "poolK": len(candidates)},
            "products": [{"productId": pid} for pid in products],
            "observedMs": 100,
        }],
    }


def test_saved_quality_can_decline_while_candidate_coverage_improves(harness: Any) -> None:
    first, second = harness._ANNA_EXPECTED[:2]
    before = _saved_comparison(harness, "before", [first, "unlabelled"], [first])
    after = _saved_comparison(harness, "after", [first, second, "unlabelled"], ["unlabelled"])
    report = harness.compare_saved_runs(before, after)
    assert report["delta"]["candidate_coverage"] > 0
    assert report["delta"]["recall_at_5"] < 0
    assert report["quality_change"] == "declined"
    assert report["status"] == "measured"
    assert "passed" not in report


def test_saved_quality_preserves_an_unchanged_recommendation(harness: Any) -> None:
    first, second = harness._ANNA_EXPECTED[:2]
    before = _saved_comparison(harness, "before", [first], [first])
    after = _saved_comparison(harness, "after", [first, second], [first])
    report = harness.compare_saved_runs(before, after)
    assert report["quality_change"] == "unchanged"
    assert report["delta"]["candidate_coverage"] > 0
    assert report["delta"]["recall_at_5"] == 0


def test_soft_relaxation_changes_retain_scores_but_qualify_the_comparison(harness: Any) -> None:
    first, second = harness._ANNA_EXPECTED[:2]
    before = _saved_comparison(harness, "before", [first], [first])
    after = _saved_comparison(harness, "after", [first, second], [first, second])
    before["strategies"][0]["searchPlan"]["relaxations"] = [{"step": "drop_tags"}]
    after["strategies"][0]["searchPlan"]["relaxations"] = []
    report = harness.compare_saved_runs(before, after)
    assert report["quality_change"] == "improved"
    assert report["comparison_context"]["same_executed_plan"] is False
    assert "do not attribute" in report["comparison_context"]["interpretation"]


@pytest.mark.parametrize("defect", [
    "same_receipt", "unpersisted", "different_query", "changed_plan", "fallback",
    "duplicate_id", "missing_id", "outside_pool", "missing_plan", "missing_products",
    "ambiguous_executor", "malformed_capture", "changed_model", "missing_model",
])
def test_saved_quality_refuses_missing_or_incomparable_evidence(harness: Any, defect: str) -> None:
    first = harness._ANNA_EXPECTED[0]
    before = _saved_comparison(harness, "before", [first], [first])
    after = _saved_comparison(harness, "after", [first], [first])
    row = after["strategies"][0]
    if defect == "same_receipt": after["receipt"]["comparisonId"] = "before"
    elif defect == "unpersisted": after["receipt"]["persisted"] = False
    elif defect == "different_query": after["query"] = "different request"
    elif defect == "changed_plan": row["searchPlan"]["hard_constraints"]["price_max_usd"] = 70
    elif defect == "fallback": row["rerank"]["status"] = "fallback"
    elif defect == "duplicate_id": row["products"].append({"productId": first})
    elif defect == "missing_id": row["products"][0]["productId"] = None
    elif defect == "outside_pool": row["products"][0]["productId"] = "outside"
    elif defect == "missing_plan": row.pop("searchPlan")
    elif defect == "missing_products": row.pop("products")
    elif defect == "ambiguous_executor": after["strategies"].append(row)
    elif defect == "malformed_capture": after = []
    elif defect == "changed_model": row["rerank"]["model"] = "different-reranker"
    elif defect == "missing_model": row["rerank"].pop("model")
    with pytest.raises(ValueError):
        harness.compare_saved_runs(before, after)


def test_saved_mode_does_not_load_credentials_or_call_services(harness: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    import json
    import sys
    first = harness._ANNA_EXPECTED[0]
    paths = [tmp_path / "before.json", tmp_path / "after.json"]
    for path in paths:
        path.write_text(json.dumps(_saved_comparison(harness, path.stem, [first], [first])))
    def forbidden():
        pytest.fail("Saved scoring must not initialize the live backend or credentials")
    monkeypatch.setattr(harness, "_load_env", forbidden)
    monkeypatch.setattr(harness, "_import_backend", forbidden)
    monkeypatch.setattr(sys, "argv", ["eval_retrieval_harness.py", "--compare-saved", *map(str, paths)])
    assert harness.main() == 0
    assert json.loads(capsys.readouterr().out)["quality_change"] == "unchanged"


# ---------------------------------------------------------------------------
# Fakes for the two behavioral tests below. They stand in for Aurora and
# Bedrock only; the harness code under test is the shipped code.
# ---------------------------------------------------------------------------


def _catalog_row(product_id: int) -> dict[str, Any]:
    return {
        "product_id": str(product_id),
        "name": f"Product {product_id}",
        "description": f"Description {product_id}",
        "category": "Home Decor",
        "price": 40.0 + product_id,
        "tags": ["home", "gift"],
        "quantity": 12,
    }


class _RecordingCursor:
    """Answers both branch queries and records the LIMIT each one bound."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.limits: list[Any] = []

    async def __aenter__(self) -> "_RecordingCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(self, sql: str, params: Any = None) -> None:
        # Both branch queries bind their pool size last.
        self.limits.append(list(params)[-1] if params else None)

    async def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _RecordingCursor:
        return self._cursor


class _RecordingDB:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor = _RecordingCursor(rows)

    @contextlib.asynccontextmanager
    async def get_connection(self) -> Any:
        yield _RecordingConnection(self.cursor)


class _RecordingReranker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, query: str, documents: list[str], top_n: int) -> list[dict]:
        self.calls.append({"query": query, "documents": list(documents), "top_n": top_n})
        return [
            {"index": index, "relevance_score": 1.0 - index * 0.1}
            for index in range(min(top_n, len(documents)))
        ]


class _StubExecution:
    """The subset of ``SearchExecution`` the harness's scoring layer reads."""

    def __init__(
        self,
        plan: Any,
        *,
        rerank_pool_k: int = 20,
        returned: list[dict[str, Any]] | None = None,
        pool: list[dict[str, Any]] | None = None,
    ) -> None:
        self.plan = plan
        self.rerank_pool_k = rerank_pool_k
        self.returned = returned if returned is not None else []
        self.rerank_pool = pool if pool is not None else []

    def latency_breakdown(self) -> dict[str, int]:
        return {"embed": 1, "hybrid": 2, "rerank": 3, "eligibility": 0}


class _StubExtractor:
    def extract(self, query: str) -> dict[str, Any]:
        return {
            "categories": ["Home Decor"],
            "tags": ["gift"],
            "price_max_usd": 100,
            "in_stock_only": True,
            "exclusions": [],
            "soft_signal": "housewarming gift",
        }


def _healthy_totals() -> dict[str, dict[str, float]]:
    return {
        "vector": {"recall_at_5": 0.60, "mrr_at_5": 0.50},
        "hybrid": {"recall_at_5": 0.75, "mrr_at_5": 0.60},
        "rerank": {"recall_at_5": 0.85, "mrr_at_5": 0.70},
        "agentic": {"recall_at_5": 0.80, "mrr_at_5": 0.68},
    }


def _clean_planner() -> dict[str, float]:
    return {
        "constraints_expected": 10,
        "constraints_recovered": 8,
        "constraint_recall": 0.80,
        "hallucinated_constraints": 0,
        "hallucinated_constraint_rate": 0.0,
    }


def _clean_compliance() -> dict[str, float]:
    return {
        "rows_scored": 75,
        "hard_violations": 0,
        "hard_constraint_violation_rate": 0.0,
        "exclusion_violations": 0,
        "exclusion_violation_rate": 0.0,
    }


def _gate(harness: Any, **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "totals": _healthy_totals(),
        "coverage": 0.90,
        "planner": _clean_planner(),
        "compliance": _clean_compliance(),
        "requested": _clean_compliance(),
        "strict_planner": False,
    }
    kwargs.update(overrides)
    return harness._evaluate_gate(**kwargs)


# ---------------------------------------------------------------------------
# Gate: healthy run
# ---------------------------------------------------------------------------
def test_healthy_run_passes(harness: Any) -> None:
    verdict = _gate(harness)

    assert verdict["passed"] is True
    assert verdict["failures"] == []


# ---------------------------------------------------------------------------
# Gate: quality regressions
# ---------------------------------------------------------------------------
def test_recall_regression_fails_the_gate(harness: Any) -> None:
    totals = _healthy_totals()
    totals["rerank"]["recall_at_5"] = 0.40

    verdict = _gate(harness, totals=totals)

    assert verdict["passed"] is False
    assert any("recall@5" in failure for failure in verdict["failures"])


def test_mrr_regression_fails_the_gate(harness: Any) -> None:
    totals = _healthy_totals()
    totals["rerank"]["mrr_at_5"] = 0.10

    verdict = _gate(harness, totals=totals)

    assert verdict["passed"] is False
    assert any("mrr@5" in failure for failure in verdict["failures"])


def test_candidate_coverage_regression_fails_the_gate(harness: Any) -> None:
    verdict = _gate(harness, coverage=0.10)

    assert verdict["passed"] is False
    assert any("coverage" in failure for failure in verdict["failures"])


# ---------------------------------------------------------------------------
# Gate: correctness budgets are zero-tolerance
# ---------------------------------------------------------------------------
def test_a_single_hard_constraint_violation_fails_the_gate(harness: Any) -> None:
    """One violated hard constraint is a bug, not an averageable metric."""
    compliance = _clean_compliance()
    compliance["hard_violations"] = 1
    compliance["hard_constraint_violation_rate"] = 0.013

    verdict = _gate(harness, compliance=compliance)

    assert verdict["passed"] is False
    assert any("hard-constraint" in failure for failure in verdict["failures"])


def test_a_single_exclusion_violation_fails_the_gate(harness: Any) -> None:
    compliance = _clean_compliance()
    compliance["exclusion_violations"] = 1
    compliance["exclusion_violation_rate"] = 0.013

    verdict = _gate(harness, compliance=compliance)

    assert verdict["passed"] is False
    assert any("exclusion" in failure for failure in verdict["failures"])


def test_a_constraint_the_planner_dropped_fails_the_gate(harness: Any) -> None:
    """The oracle must not be the thing under test.

    A requirement the planner silently drops disappears from the plan, so
    plan-scored compliance reports a clean run. Scoring the same returned rows
    against the pinned golden filters is what turns that silence into a failure.
    """
    requested = _clean_compliance()
    requested["hard_violations"] = 1
    requested["hard_constraint_violation_rate"] = 0.013

    verdict = _gate(harness, compliance=_clean_compliance(), requested=requested)

    assert verdict["passed"] is False
    assert any("requested-constraint" in failure for failure in verdict["failures"])


def test_a_dropped_exclusion_fails_the_gate(harness: Any) -> None:
    requested = _clean_compliance()
    requested["exclusion_violations"] = 1
    requested["exclusion_violation_rate"] = 0.013

    verdict = _gate(harness, compliance=_clean_compliance(), requested=requested)

    assert verdict["passed"] is False
    assert any("requested-exclusion" in failure for failure in verdict["failures"])


def test_hallucinated_constraint_fails_the_gate(harness: Any) -> None:
    """An invented hard constraint silently removes valid results."""
    planner = _clean_planner()
    planner["hallucinated_constraints"] = 1
    planner["hallucinated_constraint_rate"] = 0.067

    verdict = _gate(harness, planner=planner)

    assert verdict["passed"] is False
    assert any("hallucinated" in failure for failure in verdict["failures"])


# ---------------------------------------------------------------------------
# Gate: planner recall is opt-in
# ---------------------------------------------------------------------------
def test_low_planner_recall_passes_unless_strict(harness: Any) -> None:
    planner = _clean_planner()
    planner["constraint_recall"] = 0.20

    assert _gate(harness, planner=planner)["passed"] is True
    strict = _gate(harness, planner=planner, strict_planner=True)
    assert strict["passed"] is False
    assert any("constraint recall" in f for f in strict["failures"])


def test_gate_reports_its_thresholds(harness: Any) -> None:
    verdict = _gate(harness)

    assert verdict["thresholds"]["hard_constraint_violation_rate_max"] == 0.0
    assert verdict["thresholds"]["rerank_recall_at_5_min"] > 0


# ---------------------------------------------------------------------------
# Planner scoring
# ---------------------------------------------------------------------------
def test_planner_score_credits_a_recovered_constraint(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan(
        "linen under $200",
        {"categories": ["Apparel"], "price_max_usd": 200, "in_stock_only": True},
    )
    expected = harness.Filters(categories=("Apparel",), price_max=200.0)

    score = harness._score_plan(plan, expected)

    # Three: category, price, and stock. `Filters.in_stock` defaults to True
    # because every golden id is labeled against the sellable catalog.
    assert score["constraints_recovered"] == 3
    assert score["constraints_expected"] == 3
    assert score["hallucinated_constraints"] == 0


def test_planner_score_flags_a_dropped_stock_requirement(harness: Any) -> None:
    """The quietest planner failure: nothing looks wrong until it cannot ship."""
    from services.search_plan import build_plan

    plan = build_plan(
        "linen under $200",
        {"categories": ["Apparel"], "price_max_usd": 200},  # no in_stock_only
    )
    expected = harness.Filters(categories=("Apparel",), price_max=200.0)

    score = harness._score_plan(plan, expected)

    assert score["constraints_recovered"] == 2
    assert score["constraints_expected"] == 3
    assert score["expected_in_stock"] is True
    assert score["planned_in_stock_only"] is False


def test_planner_score_counts_each_requested_exclusion(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan(
        "a gift, nothing in leather",
        {"in_stock_only": True, "exclusions": ["leather"]},
    )
    expected = harness.Filters(exclusions=("leather", "candle"))

    score = harness._score_plan(plan, expected)

    # Two negatives requested, one recovered: a partial miss, not a pass.
    assert score["expected_exclusions"] == ["candle", "leather"]
    assert score["constraints_recovered"] == 2  # stock + leather
    assert score["constraints_expected"] == 3   # stock + leather + candle


def test_planner_score_flags_a_missed_constraint(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan("linen shirts", {})
    expected = harness.Filters(categories=("Apparel",), price_max=200.0)

    score = harness._score_plan(plan, expected)

    assert score["constraints_recovered"] == 0
    assert score["constraints_expected"] == 3


def test_planner_score_flags_an_invented_price_ceiling(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan("linen shirts", {"price_max_usd": 50})
    expected = harness.Filters()

    score = harness._score_plan(plan, expected)

    assert score["hallucinated_constraints"] == 1


# ---------------------------------------------------------------------------
# Compliance scoring
# ---------------------------------------------------------------------------
def test_compliance_counts_an_over_budget_row(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan("gift under $100", {"price_max_usd": 100})
    rows = [
        {"price": 90.0, "category": "Gifts", "tags": []},
        {"price": 250.0, "category": "Gifts", "tags": []},
    ]

    score = harness._score_compliance(rows, plan)

    assert score["rows"] == 2
    assert score["hard_violations"] == 1


def test_compliance_counts_an_out_of_stock_row(harness: Any) -> None:
    """A returned row the warehouse cannot ship, under an in-stock plan.

    This scored zero violations before stock was counted here, which is exactly
    the failure a hard-constraint compliance metric exists to catch.
    """
    from services.search_plan import build_plan

    plan = build_plan("gift, ready to ship", {"in_stock_only": True})
    rows = [
        {"price": 40.0, "category": "Gifts", "tags": [], "quantity": 4},
        {"price": 40.0, "category": "Gifts", "tags": [], "quantity": 0},
    ]

    score = harness._score_compliance(rows, plan)

    assert score["rows"] == 2
    assert score["hard_violations"] == 1


def test_compliance_counts_an_excluded_tag(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan("gift, no candles", {"exclusions": ["candle"]})
    rows = [
        {"price": 20.0, "category": "Gifts", "tags": ["candle"]},
        {"price": 20.0, "category": "Gifts", "tags": ["home"]},
    ]

    score = harness._score_compliance(rows, plan)

    assert score["exclusion_violations"] == 1


def test_compliance_is_clean_when_every_row_is_valid(harness: Any) -> None:
    from services.search_plan import build_plan

    plan = build_plan(
        "in-stock gift under $100, no candles",
        {"price_max_usd": 100, "in_stock_only": True, "exclusions": ["candle"]},
    )
    rows = [{"price": 40.0, "category": "Gifts", "tags": ["home"]}]

    score = harness._score_compliance(rows, plan)

    assert score["hard_violations"] == 0
    assert score["exclusion_violations"] == 0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def test_planner_totals_aggregate_rates(harness: Any) -> None:
    totals = harness._planner_totals(
        [
            {
                "constraints_expected": 2,
                "constraints_recovered": 2,
                "hallucinated_constraints": 0,
            },
            {
                "constraints_expected": 2,
                "constraints_recovered": 1,
                "hallucinated_constraints": 1,
            },
        ]
    )

    assert totals["constraint_recall"] == 0.75
    assert totals["hallucinated_constraint_rate"] == 0.5


def test_compliance_totals_aggregate_rates(harness: Any) -> None:
    totals = harness._compliance_totals(
        [
            {"rows": 5, "hard_violations": 1, "exclusion_violations": 0},
            {"rows": 5, "hard_violations": 0, "exclusion_violations": 1},
        ]
    )

    assert totals["rows_scored"] == 10
    assert totals["hard_constraint_violation_rate"] == 0.1
    assert totals["exclusion_violation_rate"] == 0.1


def test_baseline_rows_run_a_strict_unextracted_plan(harness: Any) -> None:
    """Only the agentic row may carry model-proposed filters or widen.

    The three baseline rows exist to isolate what retrieval mechanics buy.
    Giving them the extractor's constraints would make every row agentic;
    letting them widen would hide a short result behind a relaxed pass.
    """
    from services import search_plan

    backend = {
        "build_plan": search_plan.build_plan,
        "strategies": {
            "vector": search_plan.STRATEGY_VECTOR,
            "hybrid": search_plan.STRATEGY_HYBRID,
            "rerank": search_plan.STRATEGY_HYBRID_RERANK,
        },
        "strict_policy": search_plan.RELAXATION_POLICY_STRICT,
    }

    plan = harness._baseline_plan(backend, "gift under $100", "rerank", 5)

    assert plan.hard.price_max_usd is None
    assert plan.hard.categories == ()
    assert plan.soft.tags == ()
    assert plan.hard.in_stock_only is True
    assert plan.retrieval_strategy == search_plan.STRATEGY_HYBRID_RERANK
    assert len(plan.relaxation_ladder()) == 1


def test_pool_k_bounds_both_branches_and_the_rerank_pool(harness: Any) -> None:
    """``--pool-k`` is the one knob the harness varies to show pool effects.

    The config dict is a request. What the branches receive is the contract,
    and ``HybridSearch`` raises each branch to a floor of five, so a config
    assertion alone would have reported a pool of three where the vector and
    lexical branches actually asked Postgres for five rows each.
    """
    import argparse
    import asyncio

    from services.planned_hybrid_retrieval import execute_search_plan
    from services.search_plan import build_plan

    args = argparse.Namespace(pool_k=3, rrf_k=60, top_k=5)
    config = harness._executor_config(args)
    assert config == {
        "k_vector": 3,
        "k_fts": 3,
        "rrf_k": 60,
        "top_n": 5,
        "rerank_pool_k": 3,
    }

    db = _RecordingDB([_catalog_row(index) for index in range(1, 9)])
    reranker = _RecordingReranker()
    execution = asyncio.run(
        execute_search_plan(
            db,
            plan=build_plan("a housewarming gift", {"in_stock_only": True}, top_k=5),
            query="a housewarming gift",
            limit=5,
            embed=lambda _query: [0.01] * 1024,
            rerank=reranker,
            config=config,
            relax=False,
        )
    )

    # Both branch queries ran, and each bound a LIMIT of five, not three.
    assert len(db.cursor.limits) == 2
    assert db.cursor.limits == [5, 5]
    # The reranker, in contrast, honors the requested three exactly.
    assert execution.rerank_pool_k == 3
    assert len(reranker.calls[0]["documents"]) == 3


def test_the_harness_runs_the_shipped_executor(harness: Any) -> None:
    """An eval that scores its own private pipeline cannot detect a regression.

    Behavioral rather than textual: the harness is handed a recording
    executor and must route every strategy through it, with the widening
    policy each strategy is supposed to carry.
    """
    import argparse
    import asyncio

    from services import search_plan

    calls: list[dict[str, Any]] = []

    async def _recording_executor(db: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return _StubExecution(kwargs["plan"])

    backend = {
        "build_plan": search_plan.build_plan,
        "strategies": {
            "vector": search_plan.STRATEGY_VECTOR,
            "hybrid": search_plan.STRATEGY_HYBRID,
            "rerank": search_plan.STRATEGY_HYBRID_RERANK,
        },
        "strict_policy": search_plan.RELAXATION_POLICY_STRICT,
        "execute_search_plan": _recording_executor,
        "rerank": lambda **_kwargs: [],
        "extractor": _StubExtractor(),
    }
    # Not GOLDEN_QUERIES[0]: that entry's labels are Lab 2b's artifact and are
    # empty until a participant builds it. These tests exercise the harness's
    # coverage arithmetic, which needs a labeled entry to divide by.
    golden = next(g for g in harness.GOLDEN_QUERIES if g.expected)
    args = argparse.Namespace(pool_k=20, rrf_k=60, top_k=5)

    outcomes = asyncio.run(
        harness._run_strategies(
            object(), golden, [0.01] * 1024, backend=backend, args=args
        )
    )

    assert harness.STRATEGIES == ("vector", "hybrid", "rerank", "agentic")
    assert tuple(outcomes) == harness.STRATEGIES
    assert len(calls) == 4
    # Every strategy went through the injected executor with the harness config.
    for call in calls:
        assert call["config"]["rerank_pool_k"] == 20
        assert call["query"] == golden.query
        assert call["limit"] == 5
    # Only the agentic row is allowed to widen.
    assert [call["relax"] for call in calls] == [False, False, False, True]
    assert calls[3]["plan"].hard.price_max_usd == 100.0


def test_the_harness_reports_the_pool_the_executor_resolved(harness: Any) -> None:
    """``--pool-k 50`` cannot label coverage at 50 over a pool of thirty."""
    from services.search_plan import build_plan

    # Not GOLDEN_QUERIES[0]: that entry's labels are Lab 2b's artifact and are
    # empty until a participant builds it. These tests exercise the harness's
    # coverage arithmetic, which needs a labeled entry to divide by.
    golden = next(g for g in harness.GOLDEN_QUERIES if g.expected)
    plan = build_plan(golden.query, {"in_stock_only": True}, top_k=5)
    resolved = 30
    rows = [{"product_id": str(expected)} for expected in golden.expected]
    outcomes = {
        strategy: {
            "execution": _StubExecution(
                plan, rerank_pool_k=resolved, returned=rows, pool=rows
            ),
            "elapsed_s": 0.01,
        }
        for strategy in harness.STRATEGIES
    }

    detail = harness._detail_for(golden, outcomes, top_k=5)

    assert detail["hybrid_candidate_coverage"]["pool_k"] == resolved
    assert detail["hybrid_candidate_coverage"]["coverage"] == 1.0
