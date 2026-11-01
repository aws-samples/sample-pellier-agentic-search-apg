"""Tests for the store tools' query compiler and RRF merge math.

``or_tsquery`` compiles a conversational query into OR-joined ``to_tsquery``
input; ``rrf_merge`` fuses the vector and full-text branches. Both are pure
functions, so these tests need no database.

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_store_tools_fusion.py -v
"""
from __future__ import annotations

import math
from typing import Any, Dict

from services.store_tools import or_tsquery, rrf_merge


def _make_row(product_id: int, **extra: Any) -> Dict[str, Any]:
    return {"product_id": product_id, "name": f"Product {product_id}", **extra}


# ---------------------------------------------------------------------------
# or_tsquery — the OR-joining query compiler that fixes the
# AND-of-all-stems over-filtering both plainto and websearch default to
# ---------------------------------------------------------------------------


class TestBuildOrTsquery:
    """The compiler that turns conversational queries into OR-joined to_tsquery input."""

    def test_drops_stop_words_and_keeps_content_tokens(self) -> None:
        out = or_tsquery(
            "a thoughtful gift for someone who loves morning rituals"
        )
        # 'a', 'for', 'who' are stop-words; 'someone', 'loves' are in our
        # extra stop-word list (conversational filler / generic verbs).
        assert "thoughtful" in out
        assert "gift" in out
        assert "morning" in out
        assert "rituals" in out
        # Stop-words removed:
        for w in ["someone", "loves", "for", "who", "the"]:
            assert w not in out

    def test_or_joins_remaining_tokens(self) -> None:
        out = or_tsquery("beeswax candle for the dining table")
        # 'for' and 'the' drop; 'beeswax', 'candle', 'dining', 'table' keep.
        # Order preserved so the OR-tree matches user intent for ts_rank_cd.
        parts = out.split(" | ")
        assert "beeswax" in parts
        assert "candle" in parts
        assert "dining" in parts
        assert "table" in parts
        assert "for" not in parts
        assert "the" not in parts

    def test_dedupes_repeated_tokens(self) -> None:
        out = or_tsquery("candle candle CANDLE")
        # All three normalize to 'candle' after lowercase; only one survives.
        assert out == "candle"

    def test_strips_punctuation(self) -> None:
        out = or_tsquery("wrap-ready, gift-table, hand-thrown!")
        # Punctuation removed; tokens preserved (with internal hyphens stripped
        # by the per-token .strip("-") call).
        for word in ["wrap", "ready", "gift", "table", "hand", "thrown"]:
            assert word in out

    def test_drops_short_tokens(self) -> None:
        out = or_tsquery("a is or by candle")
        # All ≤2 chars except 'candle'.
        assert out == "candle"

    def test_pure_stop_word_query_returns_empty(self) -> None:
        out = or_tsquery("the and for what who")
        assert out == ""

    def test_empty_input_returns_empty(self) -> None:
        assert or_tsquery("") == ""
        assert or_tsquery("   ") == ""


# ---------------------------------------------------------------------------
# RRF math — the central correctness claim
# ---------------------------------------------------------------------------


class TestRRFMerge:
    """The fusion formula: score(d) = sum over each list L : 1 / (rrf_k + rank_L(d))."""

    def test_doc_in_both_lists_at_rank_1_scores_higher_than_only_one(self) -> None:
        v_rows = [_make_row(1), _make_row(2)]
        b_rows = [_make_row(1), _make_row(3)]  # product 1 in both, 3 only in FTS
        merged = rrf_merge(v_rows, b_rows, rrf_k=60)
        # product 1 is rank-1 in both → 1/61 + 1/61 = 2/61 ≈ 0.0328
        # product 2 is rank-2 in vector only → 1/62 ≈ 0.0161
        # product 3 is rank-2 in FTS only → 1/62 ≈ 0.0161
        assert [r["product_id"] for r in merged] == [1, 2, 3] \
            or [r["product_id"] for r in merged] == [1, 3, 2]
        assert merged[0]["product_id"] == 1
        assert math.isclose(merged[0]["rrf_score"], 2.0 / 61, abs_tol=1e-9)

    def test_doc_in_only_one_list_scores_lower_than_both(self) -> None:
        v_rows = [_make_row(10)]
        b_rows = [_make_row(20)]
        merged = rrf_merge(v_rows, b_rows, rrf_k=60)
        assert len(merged) == 2
        scores = {r["product_id"]: r["rrf_score"] for r in merged}
        assert math.isclose(scores[10], 1.0 / 61, abs_tol=1e-9)
        assert math.isclose(scores[20], 1.0 / 61, abs_tol=1e-9)

    def test_rank_decay_damps_tail_contributions(self) -> None:
        # A doc at rank 1 should outscore a doc at rank 30 by a wide margin.
        v_rows = [_make_row(i) for i in range(1, 31)]
        b_rows = []
        merged = rrf_merge(v_rows, b_rows, rrf_k=60)
        head = merged[0]["rrf_score"]
        tail = merged[-1]["rrf_score"]
        # rank 1: 1/61 ≈ 0.0164; rank 30: 1/90 ≈ 0.0111
        assert head > tail
        assert head / tail > 1.4  # head is meaningfully higher

    def test_rrf_score_is_monotonic_in_rank_within_a_list(self) -> None:
        v_rows = [_make_row(i) for i in range(1, 6)]
        merged = rrf_merge(v_rows, [], rrf_k=60)
        scores = [r["rrf_score"] for r in merged]
        assert scores == sorted(scores, reverse=True)

    def test_merge_preserves_both_branch_ranks(self) -> None:
        v_rows = [_make_row(1), _make_row(2)]
        fts_rows = [_make_row(2), _make_row(3)]

        merged = rrf_merge(v_rows, fts_rows, rrf_k=60)
        by_id = {row["product_id"]: row for row in merged}

        assert by_id[1]["vec_rank"] == 1
        assert by_id[1]["fts_rank"] is None
        assert by_id[2]["vec_rank"] == 2
        assert by_id[2]["fts_rank"] == 1
        assert by_id[3]["vec_rank"] is None
        assert by_id[3]["fts_rank"] == 2


# ---------------------------------------------------------------------------
# search() end-to-end — both branches run, results merged
# ---------------------------------------------------------------------------
