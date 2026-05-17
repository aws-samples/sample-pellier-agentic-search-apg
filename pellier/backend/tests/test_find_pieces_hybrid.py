"""Tests for ``services.agent_tools.find_pieces_hybrid`` — Anna's tool.

Mocks the EmbeddingService, HybridSearch, and RerankService so the
tests run offline. The pipeline order matters: embed → hybrid →
rerank → filter → return.

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_find_pieces_hybrid.py -v
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

import services.agent_tools as agent_tools
import services.embeddings as embeddings_module
import services.hybrid_search as hybrid_search_module
import services.rerank as rerank_module


class _SentinelDB:
    """Opaque placeholder — the mocked HybridSearch ignores it."""


@pytest.fixture
def candidates() -> List[Dict[str, Any]]:
    """Five fake candidates from the hybrid search step."""
    return [
        {
            "product_id": i,
            "name": f"Product {i}",
            "brand": "Pellier Editions",
            "color": "Sand",
            "description": f"Description for product {i}",
            "img_url": f"https://example.com/{i}.jpg",
            "category": "Apparel",
            "price": 50.0 + i * 10,  # 60, 70, 80, 90, 100
            "rating": 4.7,
            "reviews": "50",
            "badge": None,
            "tags": [],
            "rrf_score": 0.05 - i * 0.005,
        }
        for i in range(1, 6)
    ]


@pytest.fixture(autouse=True)
def patch_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make _db_service truthy so the tool doesn't early-return."""
    monkeypatch.setattr(agent_tools, "_db_service", _SentinelDB())


@pytest.fixture(autouse=True)
def patch_run_async(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make _run_async pass through coroutines synchronously via asyncio.run.

    The production helper bridges sync @tool calls to the main uvicorn
    loop; in tests we just want to await the coroutine directly.
    """
    import asyncio

    def _run(coro: Any) -> Any:
        return asyncio.run(coro)

    monkeypatch.setattr(agent_tools, "_run_async", _run)


@pytest.fixture
def patch_embedding(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub EmbeddingService.embed_query → fixed 1024-dim vector."""
    embed_service = MagicMock()
    embed_service.embed_query.return_value = [0.01] * 1024
    monkeypatch.setattr(
        embeddings_module, "EmbeddingService",
        lambda *_, **__: embed_service,
    )
    return embed_service


@pytest.fixture
def patch_hybrid(
    monkeypatch: pytest.MonkeyPatch,
    candidates: List[Dict[str, Any]],
) -> MagicMock:
    """Stub HybridSearch.search → fixed candidate list."""
    hs = MagicMock()

    async def _search(*_args: Any, **_kwargs: Any) -> List[Dict[str, Any]]:
        return list(candidates)

    hs.search = _search
    monkeypatch.setattr(
        hybrid_search_module, "HybridSearch",
        lambda *_, **__: hs,
    )
    return hs


@pytest.fixture
def patch_rerank(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub get_rerank_service → reranker that reverses input order."""
    svc = MagicMock()
    # Reverse the order so we can verify the rerank step actually
    # influenced the final ranking. Without this, the test couldn't
    # tell hybrid order from reranked order.
    svc.rerank.return_value = [
        {"index": 4, "relevance_score": 0.95},
        {"index": 3, "relevance_score": 0.88},
        {"index": 2, "relevance_score": 0.71},
        {"index": 1, "relevance_score": 0.55},
        {"index": 0, "relevance_score": 0.40},
    ]
    monkeypatch.setattr(
        rerank_module, "get_rerank_service", lambda: svc,
    )
    return svc


# ---------------------------------------------------------------------------
# Pipeline order
# ---------------------------------------------------------------------------


class TestPipelineOrder:

    def test_embed_then_hybrid_then_rerank_then_return(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="something beautiful", limit=3)
        )
        assert result["status"] == "success"
        # Embedding called once.
        assert patch_embedding.embed_query.call_count == 1
        # Reranker called with the candidates derived from hybrid output.
        assert patch_rerank.rerank.call_count == 1
        rerank_kwargs = patch_rerank.rerank.call_args.kwargs
        assert rerank_kwargs["query"] == "something beautiful"
        # Five candidates → five documents passed to rerank.
        assert len(rerank_kwargs["documents"]) == 5

    def test_search_method_says_hybrid_plus_rerank_when_rerank_succeeds(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", limit=5)
        )
        assert result["search_method"] == "hybrid+rerank"

    def test_pool_size_reflects_hybrid_output(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", limit=2)
        )
        assert result["pool_size"] == 5  # five candidates from hybrid


# ---------------------------------------------------------------------------
# Rerank actually reorders results
# ---------------------------------------------------------------------------


class TestReranking:

    def test_rerank_order_overrides_hybrid_order(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        # Mocked reranker reversed the order, so the first result should
        # be product_id 5 (originally last), not product_id 1 (originally
        # first by RRF).
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", limit=5)
        )
        names = [p["name"] for p in result["products"]]
        assert names[0] == "Product 5"
        assert names[-1] == "Product 1"

    def test_milestone_home_query_promotes_olive_branch_when_rerank_found_it(
        self,
        candidates: List[Dict[str, Any]],
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        candidates[1]["name"] = "Olive Branch Vessel"
        result = json.loads(
            agent_tools.find_pieces_hybrid(
                query="A milestone gift for a new homeowner",
                limit=5,
            )
        )
        names = [p["name"] for p in result["products"]]
        assert names[0] == "Olive Branch Vessel"

    def test_non_home_milestone_queries_keep_rerank_order(
        self,
        candidates: List[Dict[str, Any]],
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        candidates[1]["name"] = "Olive Branch Vessel"
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="something beautiful", limit=5)
        )
        names = [p["name"] for p in result["products"]]
        assert names[0] == "Product 5"
        assert names[3] == "Olive Branch Vessel"

    def test_each_product_has_rerank_score(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", limit=3)
        )
        for product in result["products"]:
            assert "rerank_score" in product
            assert isinstance(product["rerank_score"], float)


# ---------------------------------------------------------------------------
# Failure mode: rerank returns []
# ---------------------------------------------------------------------------


class TestRerankFailureFallback:

    def test_empty_rerank_falls_back_to_rrf_order(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        broken = MagicMock()
        broken.rerank.return_value = []  # rerank failed
        monkeypatch.setattr(
            rerank_module, "get_rerank_service", lambda: broken,
        )
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", limit=5)
        )
        assert "rerank fallback" in result["search_method"]
        # All candidates kept in original RRF order.
        names = [p["name"] for p in result["products"]]
        assert names == [f"Product {i}" for i in range(1, 6)]


# ---------------------------------------------------------------------------
# Filters apply post-rerank
# ---------------------------------------------------------------------------


class TestFilters:

    def test_max_price_filters_after_rerank(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        # Candidate prices: 60, 70, 80, 90, 100. Rerank reverses order
        # so product_id 5 ($100) is first. max_price=80 should drop
        # 5 and 4.
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", max_price=80, limit=5)
        )
        prices = [p["price"] for p in result["products"]]
        assert all(p <= 80 for p in prices)
        assert len(prices) == 3  # 60, 70, 80

    def test_min_rating_filter_passes_through(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        # All fixture candidates have rating 4.7; min_rating=4.8 drops all.
        result = json.loads(
            agent_tools.find_pieces_hybrid(query="q", min_rating=4.8, limit=5)
        )
        assert result["count"] == 0

    def test_explicit_category_filters_but_auto_does_not(
        self,
        patch_embedding: MagicMock,
        patch_hybrid: MagicMock,
        patch_rerank: MagicMock,
    ) -> None:
        # Explicit category that doesn't match → drops all results.
        result_explicit = json.loads(
            agent_tools.find_pieces_hybrid(
                query="q", category="Footwear", limit=5,
            )
        )
        assert result_explicit["count"] == 0
        # No category passed → no filtering.
        result_default = json.loads(
            agent_tools.find_pieces_hybrid(query="q", limit=5)
        )
        assert result_default["count"] == 5
