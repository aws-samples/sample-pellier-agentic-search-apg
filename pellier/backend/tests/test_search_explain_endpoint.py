"""Tests for ``GET /api/atelier/search/explain`` — the Atelier "Search"
mechanism surface (``app.explain_search``).

This endpoint is the *mechanism* counterpart to
``/search-strategies/compare`` (the outcome view). It runs one hybrid
query and returns every intermediate stage —
EMBED → VECTOR → LEXICAL → FUSION → RERANK — each shaped as a telemetry
panel (tag / title / sql / columns / rows / meta / tagClass).

We exercise the handler directly (like ``test_atelier_working_panel``
calls ``_load_live_working`` directly) so the suite runs offline without
Aurora, Bedrock, or the app lifespan. The two hybrid branches
(``_vector_search`` / ``_bm25_search``) are patched at the class level,
``EmbeddingService.embed_query`` returns a deterministic 1024-dim vector,
and the rerank service is faked so we can test both the live-reorder path
and the honest-degrade path.

Runnable from ``pellier/backend/``:

    .venv/bin/python -m pytest tests/test_search_explain_endpoint.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

import services.embeddings as embeddings_module
import services.hybrid_search as hybrid_module
import services.rerank as rerank_module


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Synthetic branch rows — a deliberate partial overlap so RRF has something
# to fuse: products 1 & 2 appear in both branches, 3 vector-only, 9 fts-only.
# ---------------------------------------------------------------------------


def _vector_rows() -> List[Dict[str, Any]]:
    return [
        {"product_id": 1, "name": "Linen Camp Shirt", "brand": "Hadley",
         "description": "Breezy Italian linen", "category": "Shirts",
         "similarity": 0.91},
        {"product_id": 2, "name": "Wide-Leg Trousers", "brand": "Hadley",
         "description": "Relaxed linen trouser", "category": "Bottoms",
         "similarity": 0.84},
        {"product_id": 3, "name": "Oxford Shirt", "brand": "Pellier",
         "description": "Cotton oxford", "category": "Shirts",
         "similarity": 0.77},
    ]


def _bm25_rows() -> List[Dict[str, Any]]:
    return [
        {"product_id": 2, "name": "Wide-Leg Trousers", "brand": "Hadley",
         "description": "Relaxed linen trouser", "category": "Bottoms",
         "bm25_score": 0.61},
        {"product_id": 1, "name": "Linen Camp Shirt", "brand": "Hadley",
         "description": "Breezy Italian linen", "category": "Shirts",
         "bm25_score": 0.55},
        {"product_id": 9, "name": "Linen Sundress", "brand": "Pellier",
         "description": "Washed linen dress", "category": "Dresses",
         "bm25_score": 0.40},
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _StubDB:
    """Placeholder DB — the branch methods are patched, so psycopg is
    never touched. It only needs to be non-None so the route passes its
    ``db_service is None`` guard and ``HybridSearch(db)`` has a handle."""

    pass


class _FakeRerank:
    """Stand-in for ``RerankService``. ``results`` is returned verbatim
    from ``rerank(...)``; an empty list exercises the degrade path."""

    def __init__(self, results: List[Dict[str, Any]]) -> None:
        self.results = results
        self.last_query: Optional[str] = None
        self.last_top_n: Optional[int] = None

    def rerank(self, query: str, documents: List[str], top_n: int = 5):
        self.last_query = query
        self.last_top_n = top_n
        return self.results


@pytest.fixture(autouse=True)
def patch_pipeline(monkeypatch):
    """Patch embeddings + both hybrid branches for every test. Rerank is
    installed per-test so each case picks its own reorder/degrade outcome."""
    monkeypatch.setattr(
        embeddings_module.EmbeddingService,
        "embed_query",
        lambda self, q: [0.01] * 1024,
    )

    async def _fake_vector(self, embedding, k):
        return _vector_rows()

    async def _fake_bm25(self, query, k):
        return _bm25_rows()

    monkeypatch.setattr(hybrid_module.HybridSearch, "_vector_search", _fake_vector)
    monkeypatch.setattr(hybrid_module.HybridSearch, "_bm25_search", _fake_bm25)

    import app
    monkeypatch.setattr(app, "db_service", _StubDB(), raising=False)


def _install_rerank(monkeypatch, results: List[Dict[str, Any]]) -> _FakeRerank:
    fake = _FakeRerank(results)
    monkeypatch.setattr(rerank_module, "get_rerank_service", lambda: fake)
    return fake


def _stages_by_name(body: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {s["stage"]: s for s in body["stages"]}


# ---------------------------------------------------------------------------
# Shape + ordering
# ---------------------------------------------------------------------------


def test_returns_five_stages_in_pipeline_order(monkeypatch) -> None:
    _install_rerank(monkeypatch, [{"index": 0, "relevance_score": 0.9}])
    import app

    body = _run(app.explain_search(query="linen shirt"))

    assert body["query"] == "linen shirt"
    assert [s["stage"] for s in body["stages"]] == [
        "embed", "vector", "lexical", "fusion", "rerank",
    ]
    # Every stage carries the panel contract keys.
    for s in body["stages"]:
        for key in ("tag", "title", "sql", "columns", "rows", "meta", "tagClass"):
            assert key in s, f"{s['stage']} missing {key}"


def test_embed_stage_reports_model_and_dims(monkeypatch) -> None:
    _install_rerank(monkeypatch, [{"index": 0, "relevance_score": 0.9}])
    import app
    from config import settings

    stages = _stages_by_name(_run(app.explain_search(query="linen shirt")))
    embed = stages["embed"]
    flat = {r[0]: r[1] for r in embed["rows"]}
    assert flat["model"] == settings.BEDROCK_EMBEDDING_MODEL
    assert flat["input_type"] == "search_query"
    assert flat["output_dimension"] == "1024"
    assert embed["tagClass"] == "amber"
    assert embed["sql"] == ""  # embed is not a SQL stage


# ---------------------------------------------------------------------------
# VECTOR / LEXICAL carry the real branch SQL
# ---------------------------------------------------------------------------


def test_vector_and_lexical_carry_real_branch_sql(monkeypatch) -> None:
    _install_rerank(monkeypatch, [{"index": 0, "relevance_score": 0.9}])
    import app

    stages = _stages_by_name(_run(app.explain_search(query="linen shirt")))

    # The SQL shown is the SAME constant the live path executes.
    assert stages["vector"]["sql"] == hybrid_module._VECTOR_BRANCH_SQL.strip()
    assert stages["lexical"]["sql"] == hybrid_module._FTS_BRANCH_SQL.strip()
    assert "<=>" in stages["vector"]["sql"]
    assert "ts_rank_cd" in stages["lexical"]["sql"]
    assert stages["vector"]["tagClass"] == "cyan"
    assert stages["lexical"]["tagClass"] == "cyan"

    # Branch rows are ranked 1..N with the right score columns.
    assert stages["vector"]["columns"] == ["rank", "product", "similarity"]
    assert stages["vector"]["rows"][0][0] == "1"
    assert "Linen Camp Shirt" in stages["vector"]["rows"][0][1]
    assert stages["lexical"]["columns"] == ["rank", "product", "ts_rank_cd"]


# ---------------------------------------------------------------------------
# FUSION shows per-branch ranks side by side
# ---------------------------------------------------------------------------


def test_fusion_shows_per_branch_ranks(monkeypatch) -> None:
    _install_rerank(monkeypatch, [{"index": 0, "relevance_score": 0.9}])
    import app

    stages = _stages_by_name(_run(app.explain_search(query="linen shirt")))
    fusion = stages["fusion"]
    assert fusion["columns"] == ["product", "vec_rank", "fts_rank", "rrf_score"]

    by_product = {r[0]: r for r in fusion["rows"]}
    # Product 1: vector rank 1, fts rank 2 (both branches).
    shirt = next(r for k, r in by_product.items() if "Linen Camp Shirt" in k)
    assert shirt[1] == "1" and shirt[2] == "2"
    # Oxford Shirt is vector-only → fts_rank shown as em-dash sentinel.
    oxford = next(r for k, r in by_product.items() if "Oxford Shirt" in k)
    assert oxford[1] == "3" and oxford[2] == "—"
    # Sundress is fts-only → vec_rank em-dash.
    dress = next(r for k, r in by_product.items() if "Sundress" in k)
    assert dress[1] == "—" and dress[2] == "3"


# ---------------------------------------------------------------------------
# RERANK reordering delta (live) + honest degrade (Bedrock down)
# ---------------------------------------------------------------------------


def test_rerank_shows_reordering_delta(monkeypatch) -> None:
    # Cohere returns index 2 (RRF pos 3) as the new #1 — a clear climb.
    _install_rerank(
        monkeypatch,
        [
            {"index": 2, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.80},
            {"index": 1, "relevance_score": 0.40},
        ],
    )
    import app

    stages = _stages_by_name(_run(app.explain_search(query="linen shirt")))
    rerank = stages["rerank"]
    assert rerank["columns"] == [
        "product", "rrf_pos", "reranked_pos", "relevance_score",
    ]
    assert rerank["tagClass"] == "amber"
    # First reranked row was RRF pos 3, now pos 1 → climbed (▲).
    first = rerank["rows"][0]
    assert first[1] == "3"
    assert first[2].startswith("1")
    assert "▲" in first[2]
    assert first[3] == "0.9500"


def test_rerank_degrades_honestly_when_bedrock_returns_empty(monkeypatch) -> None:
    # Empty rerank result = Bedrock outage / fallback path.
    _install_rerank(monkeypatch, [])
    import app

    stages = _stages_by_name(_run(app.explain_search(query="linen shirt")))
    rerank = stages["rerank"]
    # Positions unchanged (rrf_pos == reranked_pos), scores n/a — no fabrication.
    for i, row in enumerate(rerank["rows"], start=1):
        assert row[1] == str(i)
        assert row[2].startswith(str(i))
        assert row[3] == "n/a"
    assert "unavailable" in rerank["meta"].lower() or "fall" in rerank["meta"].lower()


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_empty_query_raises_400(monkeypatch) -> None:
    _install_rerank(monkeypatch, [])
    import app
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _run(app.explain_search(query="   "))
    assert exc.value.status_code == 400


def test_db_uninitialized_raises_503(monkeypatch) -> None:
    _install_rerank(monkeypatch, [])
    import app

    monkeypatch.setattr(app, "db_service", None, raising=False)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _run(app.explain_search(query="linen shirt"))
    assert exc.value.status_code == 503
