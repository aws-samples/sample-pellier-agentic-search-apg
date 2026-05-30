"""Tests for ``routes.search`` — the ``POST /api/search`` surface (Task 3.7).

Validates Requirements 3.3.6 and 5.1.1 without live Aurora or Bedrock
traffic. The ``EmbeddingService`` is stubbed to return a deterministic
1024-dim vector and ``HybridSearchService._vector_search`` is
monkey-patched to return a handful of synthetic rows so the test
exercises the full route: request validation, embedding call, search
call, row projection, and the ``StorefrontSearchResponse`` wire shape.

Headline acceptance (Task 3.7 "Test verification"):

    "timing fields are populated; p95 < 500ms smoke test against
     seeded catalog."

Against mocked services the p95 is effectively the overhead of the
FastAPI TestClient stack — always well under 500ms — so the assertion
is that a warm single request stays inside budget. The real
perf-against-seeded-catalog measurement lives in Task 7.1.

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_search_endpoint.py -v
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.vector_search as vector_search_module
from routes.search import (
    get_db_service,
    get_embedding_service,
    router as search_router,
)


# ---------------------------------------------------------------------------
# Synthetic catalog — 5 rows in the legacy vector-search shape
# ---------------------------------------------------------------------------
#
# These mimic what ``HybridSearchService._vector_search`` returns: rows
# aliased for the legacy search explorer (``product_id``,
# ``product_description``, ``img_url``, ``category_name``, ``rating``,
# etc.) with a trailing ``similarity`` column. The route projects them
# onto ``StorefrontProduct`` before the response; the test asserts the
# projection is lossless for id/price/rating/imageUrl and falls back
# safely for brand/color/tags which aren't carried on the vector row.


def _synthetic_vector_rows() -> List[Dict[str, Any]]:
    return [
        {
            "product_id": 1,
            "product_description": "Italian Linen Camp Shirt\nMade in Portugal",
            "img_url": "https://example.com/linen-shirt-01.jpg",
            "product_url": "https://example.com/p/linen-shirt-01",
            "category_name": "Linen Shirts",
            "price": 128.0,
            "reviews": 142,
            "rating": 4.7,
            "isbestseller": False,
            "boughtinlastmonth": 34,
            "quantity": 10,
            "similarity": 0.91,
        },
        {
            "product_id": 2,
            "product_description": "Wide-Leg Linen Trousers",
            "img_url": "https://example.com/linen-trousers-02.jpg",
            "product_url": "https://example.com/p/linen-trousers-02",
            "category_name": "Linen Bottoms",
            "price": 98.0,
            "reviews": 87,
            "rating": 4.5,
            "isbestseller": False,
            "boughtinlastmonth": 21,
            "quantity": 8,
            "similarity": 0.85,
        },
        {
            "product_id": 4,
            "product_description": "Relaxed Oxford Shirt",
            "img_url": "https://example.com/oxford-shirt-03.jpg",
            "product_url": "https://example.com/p/oxford-shirt-03",
            "category_name": "Linen Shirts",
            "price": 88.0,
            "reviews": 54,
            "rating": 4.4,
            "isbestseller": False,
            "boughtinlastmonth": 12,
            "quantity": 6,
            "similarity": 0.78,
        },
        {
            "product_id": 7,
            "product_description": "Cashmere-Blend Cardigan",
            "img_url": "https://example.com/cardigan-04.jpg",
            "product_url": "https://example.com/p/cardigan-04",
            "category_name": "Outerwear",
            "price": 158.0,
            "reviews": 31,
            "rating": 4.8,
            "isbestseller": True,
            "boughtinlastmonth": 9,
            "quantity": 4,
            "similarity": 0.74,
        },
        {
            "product_id": 5,
            "product_description": "Sundress in Washed Linen",
            "img_url": "https://example.com/sundress-05.jpg",
            "product_url": "https://example.com/p/sundress-05",
            "category_name": "Dresses",
            "price": 148.0,
            "reviews": 66,
            "rating": 4.6,
            "isbestseller": False,
            "boughtinlastmonth": 18,
            "quantity": 5,
            "similarity": 0.70,
        },
    ]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmbeddingService:
    """Minimal stand-in for ``EmbeddingService``.

    Returns a deterministic 1024-dim vector so the route can hand it
    off to ``_vector_search`` without exercising Bedrock. Records the
    most recent query so tests can assert the route called
    ``embed_query`` with the request payload.
    """

    def __init__(self) -> None:
        self.last_query: str | None = None
        self.calls = 0

    def embed_query(self, query: str) -> List[float]:
        self.last_query = query
        self.calls += 1
        # 1024 floats matches Cohere Embed English v3's output dimension. The
        # specific values don't matter — the fake ``_vector_search``
        # below ignores them.
        return [0.0] * 1024


class FakeDatabaseService:
    """Placeholder DB service. ``_vector_search`` is monkey-patched at
    the class level in the fixture so this instance is never actually
    called by psycopg — it just needs to exist so
    ``HybridSearchService(db)`` has something to hold onto.
    """

    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_rows() -> List[Dict[str, Any]]:
    return _synthetic_vector_rows()


@pytest.fixture
def embedding_service() -> FakeEmbeddingService:
    return FakeEmbeddingService()


@pytest.fixture
def db_service() -> FakeDatabaseService:
    return FakeDatabaseService()


@pytest.fixture
def patch_vector_search(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Replace ``HybridSearchService._vector_search`` with a fake that
    returns the synthetic catalog. Returns the captured-calls dict so
    tests can assert how the route invoked the underlying method.

    Patching at the class level means every instance inside the route
    handler picks up the stub automatically, without threading a
    service dependency override through the router.
    """
    captured: Dict[str, Any] = {}

    async def fake_vector_search(
        self: Any,
        embedding: List[float],
        limit: int,
        ef_search: int,
        iterative_scan: bool = True,
    ) -> List[Dict[str, Any]]:
        # Record the call so tests can assert the embedding size + limit
        # were forwarded intact. The route passes ef_search=40.
        captured.update(
            embedding_len=len(embedding),
            limit=limit,
            ef_search=ef_search,
            iterative_scan=iterative_scan,
        )
        return synthetic_rows[:limit]

    monkeypatch.setattr(
        vector_search_module.VectorSearch,
        "vector_search",
        fake_vector_search,
    )
    return captured


@pytest.fixture
def client(
    embedding_service: FakeEmbeddingService,
    db_service: FakeDatabaseService,
    patch_vector_search: Dict[str, Any],
) -> TestClient:
    """FastAPI test app with only the search router mounted.

    Isolates the router from ``app.py`` so tests don't need the full
    lifespan (database, Bedrock pool, agent graph). The embedding
    service and DB service are injected via FastAPI dependency
    overrides; ``_vector_search`` is patched at the class level by
    ``patch_vector_search``.
    """
    app = FastAPI()
    app.include_router(search_router)
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_db_service] = lambda: db_service
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy path — wire shape + timing fields
# ---------------------------------------------------------------------------


def test_returns_storefront_search_response_shape(client: TestClient) -> None:
    """Req 3.3.6 / Task 1.3 contract: the response matches the
    ``StorefrontSearchResponse`` wire shape — a ``products`` list and
    three camelCase timing fields (``queryEmbeddingMs``, ``searchMs``,
    ``totalMs``)."""
    resp = client.post("/api/search", json={"query": "linen shirt"})
    assert resp.status_code == 200
    body = resp.json()

    # Exactly these four top-level keys, no legacy snake_case leaks.
    assert set(body.keys()) == {
        "products", "queryEmbeddingMs", "searchMs", "totalMs",
    }
    assert "query_embedding_ms" not in body
    assert "search_ms" not in body
    assert "total_ms" not in body


def test_products_list_is_projected_onto_storefront_shape(
    client: TestClient,
) -> None:
    """Each product in the response uses the camelCase
    ``StorefrontProduct`` shape (``id``, ``reviewCount``, ``imageUrl``,
    etc.) regardless of the snake_case columns the vector row carried."""
    resp = client.post("/api/search", json={"query": "linen shirt"})
    body = resp.json()

    assert isinstance(body["products"], list)
    assert len(body["products"]) == 5
    sample = body["products"][0]

    # camelCase wire shape (Task 1.3).
    assert "reviewCount" in sample
    assert "imageUrl" in sample
    assert "review_count" not in sample
    assert "image_url" not in sample

    # First row projection: id + price + rating + imageUrl survive
    # intact; name is the first line of product_description.
    assert sample["id"] == 1
    assert sample["price"] == 128.0
    assert sample["rating"] == 4.7
    assert sample["reviewCount"] == 142
    assert sample["imageUrl"] == "https://example.com/linen-shirt-01.jpg"
    assert sample["name"] == "Italian Linen Camp Shirt"


def test_timing_fields_are_populated(client: TestClient) -> None:
    """Task 3.7 headline assertion: all three timing fields are
    populated on every response so the frontend can render the
    latency stamp in the hero card (Req 1.3.4).

    Under mocked services the embed + search steps are near-zero ms,
    so the fields may be 0 — the invariant we care about is that they
    are present, integer, non-negative, and that ``totalMs`` upper-bounds
    the two components within a millisecond of floor() rounding noise.
    """
    resp = client.post("/api/search", json={"query": "linen shirt"})
    body = resp.json()

    for field in ("queryEmbeddingMs", "searchMs", "totalMs"):
        assert field in body, f"missing timing field: {field}"
        assert isinstance(body[field], int), f"{field} must be int"
        assert body[field] >= 0, f"{field} must be non-negative"

    # total_ms is a superset of embed + search. Allow 1ms slack for
    # independent time.perf_counter() samples rounding in opposite
    # directions.
    assert body["totalMs"] >= body["queryEmbeddingMs"] + body["searchMs"] - 1


def test_request_forwards_to_embed_and_vector_search(
    client: TestClient,
    embedding_service: FakeEmbeddingService,
    patch_vector_search: Dict[str, Any],
) -> None:
    """The route embeds the query exactly once and forwards the
    resulting vector (1024-dim) to ``_vector_search`` with the
    requested limit and the route's fixed ``ef_search=40``."""
    resp = client.post("/api/search", json={"query": "linen shirt", "limit": 3})
    assert resp.status_code == 200

    assert embedding_service.calls == 1
    assert embedding_service.last_query == "linen shirt"

    captured = patch_vector_search
    assert captured["embedding_len"] == 1024
    assert captured["limit"] == 3
    assert captured["ef_search"] == 40
    assert captured["iterative_scan"] is True

    # The search honoured the caller's limit.
    assert len(resp.json()["products"]) == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_query_rejected_by_pydantic(client: TestClient) -> None:
    """``StorefrontSearchRequest`` has ``min_length=1`` on ``query`` so
    an empty string surfaces as a 422 before the handler runs."""
    resp = client.post("/api/search", json={"query": ""})
    assert resp.status_code == 422


def test_oversize_limit_rejected(client: TestClient) -> None:
    """``limit`` is bounded at 100 to match the legacy SearchRequest."""
    resp = client.post("/api/search", json={"query": "shirt", "limit": 500})
    assert resp.status_code == 422


def test_zero_result_search_returns_empty_products_list(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """When ``_vector_search`` returns no rows (e.g. a catalog with no
    in-stock matches), the route returns a 200 with an empty products
    list — not an error envelope. The frontend renders the editorial
    "Nothing yet" card in that case (Design Error Handling row)."""

    async def empty_vector_search(
        self: Any,
        embedding: List[float],
        limit: int,
        ef_search: int,
        iterative_scan: bool = True,
    ) -> List[Dict[str, Any]]:
        return []

    monkeypatch.setattr(
        vector_search_module.VectorSearch,
        "vector_search",
        empty_vector_search,
    )

    resp = client.post("/api/search", json={"query": "no-results-expected"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["products"] == []
    # Timing fields are still populated on empty results.
    assert "queryEmbeddingMs" in body
    assert "searchMs" in body
    assert "totalMs" in body


# ---------------------------------------------------------------------------
# Perf smoke (Req 5.1.1 — p95 < 500ms)
# ---------------------------------------------------------------------------


def test_p95_latency_under_500ms_smoke(client: TestClient) -> None:
    """Req 5.1.1: ``POST /api/search`` SHALL stay under 500ms p95.

    Against mocked services this is effectively a smoke test — the
    FastAPI TestClient stack adds a few ms of overhead and the fake
    embed + search steps are near-zero. Running 20 requests and taking
    the 95th percentile captures any runaway overhead the route
    introduces (e.g. accidental blocking I/O, giant response
    serialisation) while keeping the test deterministic.

    The real perf measurement against the seeded Aurora catalog lives
    in Task 7.1 — this test only proves the route layer itself is
    inside budget.
    """
    samples_ms: List[float] = []
    for _ in range(20):
        start = time.perf_counter()
        resp = client.post("/api/search", json={"query": "linen shirt"})
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        samples_ms.append(elapsed_ms)

    samples_ms.sort()
    p95 = samples_ms[int(0.95 * len(samples_ms)) - 1]

    assert p95 < 500, (
        f"route-layer p95 latency {p95:.1f}ms exceeds 500ms budget "
        f"(samples={samples_ms})"
    )
