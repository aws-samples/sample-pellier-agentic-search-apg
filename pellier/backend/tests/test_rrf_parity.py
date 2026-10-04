"""RRF: one fusion implementation, one constant, both rails.

Fusion used to be implemented twice, in Python for the in-process path and as a
single CTE for the Lambda. Both rails now call ``store_tools.rrf_merge``, so
there is nothing left to transcribe-and-compare. What remains worth pinning:

1. The k constant is one number: the in-process default, the Settings default
   and ``DEFAULT_RETRIEVAL_CONFIG`` (what the Lambda runs on) agree.
2. ``rrf_merge`` implements ``sum 1 / (k + rank)`` over both branches, checked
   against an independent transcription of the formula on shared fixtures,
   including overlap, one-branch-only and tie cases.
3. The Lambda passes no config of its own, so it cannot fuse with another k.
"""

import math
from typing import Any, Dict, List

from config import Settings
from services import store_tools
from services.search_plan import build_plan
from services.hybrid_search import _RRF_K_DEFAULT
from services.store_tools import DEFAULT_RETRIEVAL_CONFIG, rrf_merge


def _row(product_id: int) -> Dict[str, Any]:
    return {"product_id": product_id}


def _reference_scores(vector_pids: List[int], fts_pids: List[int], k: int) -> Dict[int, float]:
    """Reciprocal Rank Fusion, transcribed from the definition.

    Each branch ranks from 1 in list order; a product absent from a branch
    contributes nothing from it.
    """
    vrank = {pid: i + 1 for i, pid in enumerate(vector_pids)}
    frank = {pid: i + 1 for i, pid in enumerate(fts_pids)}
    scores: Dict[int, float] = {}
    for pid in set(vector_pids) | set(fts_pids):
        v_term = 1.0 / (k + vrank[pid]) if pid in vrank else 0.0
        f_term = 1.0 / (k + frank[pid]) if pid in frank else 0.0
        scores[pid] = v_term + f_term
    return scores


class TestRRFConstantParity:
    """One k across the in-process default, Settings, and the Lambda's defaults."""

    def test_settings_default_matches_in_process_default(self) -> None:
        assert Settings.model_fields["HYBRID_RRF_K"].default == _RRF_K_DEFAULT

    def test_the_lambdas_default_config_fuses_with_the_same_constant(self) -> None:
        assert DEFAULT_RETRIEVAL_CONFIG["rrf_k"] == _RRF_K_DEFAULT

    def test_the_lambdas_default_config_matches_the_settings_defaults(self) -> None:
        fields = Settings.model_fields
        assert DEFAULT_RETRIEVAL_CONFIG == {
            "k_vector": fields["HYBRID_VECTOR_K"].default,
            "k_fts": fields["HYBRID_FTS_K"].default,
            "rrf_k": fields["HYBRID_RRF_K"].default,
            "top_n": fields["HYBRID_TOP_N"].default,
            "rerank_max_documents": fields["RERANK_MAX_DOCUMENTS"].default,
        }

    def test_the_lambda_passes_no_config_of_its_own(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "scripts" / "deploy" / "pellier_store_tools.py"
        ).read_text(encoding="utf-8")
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "search_products"
        ]
        assert len(calls) == 1
        assert "config" not in {keyword.arg for keyword in calls[0].keywords}


class TestFusionMath:
    """Same fixtures through the implementation and the definition."""

    FIXTURES = [
        # (label, vector pids, fts pids)
        ("overlap-at-head", [1, 2, 3], [1, 4, 5]),
        ("disjoint", [10, 11], [20, 21]),
        ("fts-empty", [1, 2, 3], []),
        ("vector-empty", [], [7, 8]),
        # Symmetric ranks: pid 1 and pid 2 tie exactly.
        ("exact-tie", [1, 2], [2, 1]),
        ("full-depth", list(range(1, 21)), list(range(15, 35))),
    ]

    def test_scores_match_the_reference_formula(self) -> None:
        for label, v_pids, f_pids in self.FIXTURES:
            merged = rrf_merge(
                [_row(p) for p in v_pids], [_row(p) for p in f_pids], _RRF_K_DEFAULT
            )
            got = {r["product_id"]: r["rrf_score"] for r in merged}
            expected = _reference_scores(v_pids, f_pids, _RRF_K_DEFAULT)
            assert got.keys() == expected.keys(), label
            for pid in expected:
                assert math.isclose(got[pid], expected[pid], rel_tol=0, abs_tol=1e-12), (
                    f"{label}: pid {pid} scored differently from the formula"
                )

    def test_ordering_is_score_descending(self) -> None:
        for label, v_pids, f_pids in self.FIXTURES:
            merged = rrf_merge(
                [_row(p) for p in v_pids], [_row(p) for p in f_pids], _RRF_K_DEFAULT
            )
            scores = [r["rrf_score"] for r in merged]
            assert scores == sorted(scores, reverse=True), label
            expected_order = sorted(
                _reference_scores(v_pids, f_pids, _RRF_K_DEFAULT).values(), reverse=True
            )
            for got, expected in zip(scores, expected_order):
                assert math.isclose(got, expected, rel_tol=0, abs_tol=1e-12), label

    def test_the_search_pipeline_fuses_with_the_default_constant(self) -> None:
        """End to end: a product ranked first by both branches scores 2 / (k + 1)."""
        shared = {"product_id": "1", "name": "A", "price": 10, "category": "Home"}

        def run(sql: str, params: Any) -> List[Dict[str, Any]]:
            if "to_tsquery" in sql or "query_embedding" in sql:
                return [dict(shared)]
            return []

        execution = store_tools.run_search_plan(
            run,
            plan=build_plan("linen shirt"),
            query="linen shirt",
            limit=1,
            embed=lambda _q: [0.1],
            rerank=lambda **_kw: [],
            config=dict(DEFAULT_RETRIEVAL_CONFIG),
        )

        assert math.isclose(
            execution.candidates[0]["rrf_score"], 2.0 / (_RRF_K_DEFAULT + 1), abs_tol=1e-12
        )
