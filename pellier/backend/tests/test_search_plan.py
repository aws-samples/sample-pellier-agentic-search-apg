"""Tests for the typed query planner (``services.search_plan``).

The load-bearing test here is
``test_no_ladder_rung_ever_drops_a_hard_constraint``. The previous
comparison endpoint walked a ladder whose last rung dropped price and
in-stock requirements, so "in-stock housewarming gift under $100" could
answer with a $250 out-of-stock candle. That class of bug is what this
module exists to make impossible, so the ladder is asserted over *every*
rung rather than just the first.
"""

from __future__ import annotations

import pytest

from services.search_plan import (
    RELAXATION_POLICY_SOFT_ONLY,
    RELAXATION_POLICY_STRICT,
    STRATEGY_HYBRID_RERANK,
    HardConstraints,
    SearchPlan,
    build_plan,
)


pytestmark = pytest.mark.usefixtures("completed_search_plan")


def _golden_extract() -> dict:
    """The workshop's golden journey, as the extractor would return it."""
    return {
        "categories": ["Home Decor"],
        "tags": ["home", "artisanal"],
        "price_max_usd": 100,
        "in_stock_only": True,
        "exclusions": ["candle"],
        "soft_signal": "thoughtful housewarming gift",
    }


# ---------------------------------------------------------------------------
# Sorting extracted fields into hard / soft / exclusions
# ---------------------------------------------------------------------------
def test_price_and_availability_are_hard_not_hints() -> None:
    plan = build_plan("in-stock gift under $100", _golden_extract())

    assert plan.hard.price_max_usd == 100.0
    assert plan.hard.in_stock_only is True
    assert plan.hard.categories == ("Home Decor",)


def test_tags_are_soft_preferences() -> None:
    plan = build_plan("housewarming gift", _golden_extract())

    assert plan.soft.tags == ("home", "artisanal")
    assert plan.soft.soft_signal == "thoughtful housewarming gift"


def test_exclusions_are_kept_separate_from_preferences() -> None:
    plan = build_plan("gift but avoid candles", _golden_extract())

    assert plan.exclusions == ("candle",)
    assert "candle" not in plan.soft.tags


def test_a_tag_cannot_be_both_excluded_and_preferred() -> None:
    """An exclusion always wins over the same value as a preference."""
    plan = build_plan(
        "cosy but no candles",
        {"tags": ["candle", "home"], "exclusions": ["candle"]},
    )

    assert plan.exclusions == ("candle",)
    assert plan.soft.tags == ("home",)


# ---------------------------------------------------------------------------
# Hallucinated / malformed model output
# ---------------------------------------------------------------------------
def test_unknown_categories_and_tags_are_dropped() -> None:
    plan = build_plan(
        "something nice",
        {"categories": ["Spacecraft"], "tags": ["nonexistent-tag"]},
    )

    assert plan.hard.categories == ()
    assert plan.soft.tags == ()


def test_malformed_price_becomes_ambiguous_not_a_guess() -> None:
    plan = build_plan("cheap gift", {"price_max_usd": "about a hundred"})

    assert plan.hard.price_max_usd is None
    assert "price_max_usd" in plan.ambiguous


def test_negative_price_is_ambiguous() -> None:
    plan = build_plan("gift", {"price_max_usd": -5})

    assert plan.hard.price_max_usd is None
    assert "price_max_usd" in plan.ambiguous


def test_empty_extraction_degrades_to_unconstrained() -> None:
    plan = build_plan("something nice", None)

    assert plan.hard.is_empty()
    assert plan.exclusions == ()
    assert plan.soft.soft_signal == "something nice"


def test_missing_soft_signal_falls_back_to_the_raw_query() -> None:
    plan = build_plan("a slow Sunday morning", {"soft_signal": "   "})

    assert plan.soft.soft_signal == "a slow Sunday morning"


def test_caller_supplied_price_overrides_the_extracted_one() -> None:
    """An explicit tool argument is authoritative, not a model guess."""
    plan = build_plan(
        "gift", {"price_max_usd": 500}, price_max_usd=75,
    )

    assert plan.hard.price_max_usd == 75.0


def test_explicit_unknown_category_is_surfaced_as_ambiguous() -> None:
    plan = build_plan("gift", {}, category="Spacecraft")

    assert plan.hard.categories == ()
    assert "category" in plan.ambiguous


def test_unknown_strategy_falls_back_to_hybrid_rerank() -> None:
    plan = build_plan("gift", {}, retrieval_strategy="telepathy")

    assert plan.retrieval_strategy == STRATEGY_HYBRID_RERANK


def test_top_k_is_clamped() -> None:
    assert build_plan("gift", {}, top_k=0).top_k == 1
    assert build_plan("gift", {}, top_k=9999).top_k == 50


# ---------------------------------------------------------------------------
# The relaxation ladder — the correctness boundary
# ---------------------------------------------------------------------------
def test_no_ladder_rung_ever_drops_a_hard_constraint() -> None:
    """Every rung must keep price, availability, category, and exclusions.

    This is the regression guard for the audit's A2 finding: the old
    ladder's final rung dropped price and in-stock entirely.
    """
    plan = build_plan("in-stock housewarming gift under $100, no candles",
                      _golden_extract())

    ladder = plan.relaxation_ladder()
    assert len(ladder) >= 2, "soft_only policy should offer a widening rung"

    for rung in ladder:
        assert rung.hard.price_max_usd == 100.0
        assert rung.hard.in_stock_only is True
        assert rung.hard.categories == ("Home Decor",)
        assert rung.exclusions == ("candle",)

        clauses, params = rung.compile_predicates()
        assert "price <= %s" in clauses
        assert "quantity > 0" in clauses
        assert "NOT (tags ?| %s)" in clauses
        assert 100.0 in params


def test_widening_only_drops_soft_tags() -> None:
    plan = build_plan("housewarming gift", _golden_extract())

    strict, widened = plan.relaxation_ladder()

    assert strict.soft.tags == ("home", "artisanal")
    assert widened.soft.tags == ()
    # The taste signal survives — it is what the reranker scores against.
    assert widened.soft.soft_signal == "thoughtful housewarming gift"


def test_every_widening_step_is_recorded() -> None:
    plan = build_plan("housewarming gift", _golden_extract())

    _, widened = plan.relaxation_ladder()

    assert [r.step for r in widened.relaxations] == ["drop_tags"]
    recorded = widened.relaxations[0].to_dict()
    assert recorded["dropped"] == ["home", "artisanal"]
    assert "hard constraints kept" in recorded["reason"]


def test_strict_policy_never_widens() -> None:
    plan = build_plan(
        "housewarming gift",
        _golden_extract(),
        relaxation_policy=RELAXATION_POLICY_STRICT,
    )

    ladder = plan.relaxation_ladder()

    assert len(ladder) == 1
    assert ladder[0].relaxations == []


def test_ladder_has_one_rung_when_there_are_no_soft_tags() -> None:
    """Nothing to widen means no second attempt to make."""
    plan = build_plan("gift under $100", {"price_max_usd": 100})

    assert len(plan.relaxation_ladder()) == 1


def test_default_policy_is_soft_only() -> None:
    assert build_plan("gift", {}).relaxation_policy == RELAXATION_POLICY_SOFT_ONLY


def test_unknown_relaxation_policy_falls_back_to_soft_only() -> None:
    plan = build_plan("gift", {}, relaxation_policy="drop_everything")

    assert plan.relaxation_policy == RELAXATION_POLICY_SOFT_ONLY


# ---------------------------------------------------------------------------
# Predicate compilation
# ---------------------------------------------------------------------------
def test_predicates_are_parameterized_never_interpolated() -> None:
    """Values travel as bound params so a hallucination cannot inject SQL."""
    plan = build_plan(
        "gift",
        {
            "categories": ["Gifts"],
            "tags": ["home"],
            "price_max_usd": 100,
            "in_stock_only": True,
            "exclusions": ["candle"],
        },
    )

    clauses, params = plan.compile_predicates()

    for clause in clauses:
        assert "Gifts" not in clause
        assert "100" not in clause
        assert "candle" not in clause
    assert clauses.count("%s") == 0  # placeholders live inside the fragments
    assert [list(p) if isinstance(p, list) else p for p in params] == [
        ["Gifts"], 100.0, ["candle"], ["home"],
    ]


def test_clause_and_param_counts_line_up() -> None:
    """Every placeholder must have exactly one bound parameter."""
    plan = build_plan(
        "gift",
        {
            "categories": ["Gifts"],
            "tags": ["home"],
            "price_max_usd": 100,
            "in_stock_only": True,
            "exclusions": ["candle"],
        },
    )

    clauses, params = plan.compile_predicates()

    placeholders = sum(clause.count("%s") for clause in clauses)
    assert placeholders == len(params)


def test_in_stock_predicate_takes_no_parameter() -> None:
    plan = build_plan("in stock gift", {"in_stock_only": True})

    clauses, params = plan.compile_predicates()

    assert clauses == ["quantity > 0"]
    assert params == []


def test_include_soft_false_keeps_hard_and_exclusions() -> None:
    plan = build_plan(
        "gift",
        {
            "tags": ["home"],
            "price_max_usd": 100,
            "exclusions": ["candle"],
        },
    )

    clauses, _ = plan.compile_predicates(include_soft=False)

    assert "tags ?| %s" not in clauses
    assert "price <= %s" in clauses
    assert "NOT (tags ?| %s)" in clauses


def test_empty_plan_compiles_to_no_predicates() -> None:
    clauses, params = build_plan("something nice", {}).compile_predicates()

    assert clauses == []
    assert params == []


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def test_to_dict_carries_the_full_plan_for_receipts() -> None:
    plan = build_plan("in-stock gift under $100, no candles", _golden_extract())
    _, widened = plan.relaxation_ladder()

    payload = widened.to_dict()

    assert payload["hard_constraints"]["price_max_usd"] == 100.0
    assert payload["hard_constraints"]["in_stock_only"] is True
    assert payload["exclusions"] == ["candle"]
    assert payload["relaxation_policy"] == RELAXATION_POLICY_SOFT_ONLY
    assert payload["relaxations"][0]["step"] == "drop_tags"
    assert payload["evidence_required"] is True


def test_hard_constraints_describe_reads_cleanly() -> None:
    described = HardConstraints(
        price_max_usd=100.0, in_stock_only=True, categories=("Gifts",)
    ).describe()

    assert described == ["price <= $100", "in stock", "category in Gifts"]


def test_empty_hard_constraints_describe_to_nothing() -> None:
    assert HardConstraints().describe() == []
    assert HardConstraints().is_empty() is True


def test_plan_defaults_require_evidence() -> None:
    """Grounding is the default posture, not an opt-in."""
    assert SearchPlan(intent="gift").evidence_required is True


# ---------------------------------------------------------------------------
# The extractor-to-executor boundary for negative constraints
# ---------------------------------------------------------------------------
# A stated "no candles" used to die at the extractor: the prompt never asked for
# `exclusions` and the sanitizer dropped the field even when the model returned
# it, so `SearchPlan.exclusions` was always empty and the `NOT (tags ?| %s)`
# predicate below was never rendered. Everything downstream already worked,
# which is why a plan-level test passed while the shipped path did not enforce
# anything. These tests cross the whole boundary.
class TestNegativeConstraintsReachSQL:
    @staticmethod
    def _envelope(model_json: dict, query: str) -> dict:
        from services.structured_extract import StructuredExtractor

        return StructuredExtractor._sanitize(StructuredExtractor, model_json, query)

    @pytest.mark.parametrize(
        ("phrase", "term"),
        [
            ("a housewarming gift under $100, in stock, no candles", "candle"),
            ("a weekend bag, nothing in leather", "leather"),
        ],
    )
    def test_a_stated_negative_becomes_a_sql_predicate(
        self, phrase: str, term: str
    ) -> None:
        from services.search_plan import build_plan

        envelope = self._envelope(
            {"categories": [], "tags": [], "price_max_usd": None,
             "in_stock_only": False, "exclusions": [term], "soft_signal": phrase},
            phrase,
        )
        assert envelope["exclusions"] == [term]

        plan = build_plan(phrase, envelope)
        assert plan.exclusions == (term,)

        clauses, params = plan.compile_predicates()
        assert "NOT (tags ?| %s)" in clauses
        assert [term] in params

    def test_every_relaxation_rung_keeps_the_negative(self) -> None:
        """Relaxation may widen taste. It may not restore a refused thing."""
        from services.search_plan import build_plan

        phrase = "a housewarming gift under $100, no candles"
        plan = build_plan(phrase, self._envelope(
            {"categories": [], "tags": ["gift"], "price_max_usd": 100,
             "in_stock_only": True, "exclusions": ["candle"], "soft_signal": phrase},
            phrase,
        ))
        ladder = plan.relaxation_ladder()
        assert ladder, "expected at least one rung"
        for rung in ladder:
            clauses, params = rung.compile_predicates()
            assert rung.exclusions == ("candle",)
            assert "NOT (tags ?| %s)" in clauses
            assert ["candle"] in params

    def test_an_excluded_tag_is_never_also_a_soft_preference(self) -> None:
        """Ranking the refused thing higher is worse than not filtering it."""
        phrase = "a gift, but no candles"
        envelope = self._envelope(
            {"categories": [], "tags": ["gift", "candle"], "price_max_usd": None,
             "in_stock_only": False, "exclusions": ["candle"],
             "soft_signal": phrase},
            phrase,
        )
        assert envelope["exclusions"] == ["candle"]
        assert "candle" not in envelope["tags"]
        assert envelope["tags"] == ["gift"]

    def test_extraction_failure_is_distinguishable_from_no_constraints(self) -> None:
        """Same empty filters, different findings -- only one can erase a stated
        requirement, so the caller is told which one it got."""
        from services.structured_extract import StructuredExtractor

        failed = StructuredExtractor._empty("no candles", status="extraction_failed")
        genuine = StructuredExtractor._empty("something nice")
        assert failed["extraction_status"] == "extraction_failed"
        assert genuine["extraction_status"] == "empty_query"
        assert failed["exclusions"] == [] and genuine["exclusions"] == []
