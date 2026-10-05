"""``GET /api/products?page=``: the home grid reads the catalog one page at a time.

A page is one catalog statement (plus the batched stock read every listing
makes) that carries the catalog's size, so the browser never fetches the
whole catalog or orders it. The page size is capped at the most cards one
grid draws, and a page past the last is not found. The order itself is
proved on real PostgreSQL in ``test_catalog_pages_postgres.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.products import PAGE_SIZE_MAX, get_db_service, router as products_router
from routes.user import get_agentcore_memory
from services.agentcore_identity import get_agentcore_identity_service

CATALOG_SIZE = 100


def _row(pid: int, total: int) -> Dict[str, Any]:
    return {
        "id": str(pid), "brand": "Pellier", "name": f"Piece {pid}", "color": "Oat", "price": 40,
        "rating": 4.5, "reviews": "12", "category": "Home", "image_url": f"/products/{pid}.webp",
        "badge": None, "tags": [], "tier": 1, "quantity": 9, "total": total,
    }


class _FakeDB:
    """Answers the page read with ``LIMIT %s OFFSET %s`` over ``size`` rows, and the stock join."""

    def __init__(self, size: int = CATALOG_SIZE) -> None:
        self.size = size
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.calls.append((query, params))
        if "warehouse_inventory" in query:
            return []
        _, limit, offset = params
        return [_row(pid, self.size) for pid in range(1, self.size + 1)][offset:offset + limit]


@pytest.fixture
def db() -> _FakeDB:
    return _FakeDB()


def _client(db: _FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(products_router)
    app.dependency_overrides[get_db_service] = lambda: db
    app.dependency_overrides[get_agentcore_identity_service] = lambda: None
    app.dependency_overrides[get_agentcore_memory] = lambda: None
    return TestClient(app)


def _catalog_reads(db: _FakeDB) -> List[tuple[str, tuple[Any, ...]]]:
    return [call for call in db.calls if "warehouse_inventory" not in call[0]]


def test_a_page_is_one_read_that_carries_the_catalog_size(db: _FakeDB) -> None:
    response = _client(db).get("/api/products", params={"persona": "Anna", "page": 2, "page_size": 12})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {key: body[key] for key in ("page", "pageSize", "total", "pages")} == {
        "page": 2, "pageSize": 12, "total": 100, "pages": 9,
    }
    assert [card["id"] for card in body["products"]] == list(range(13, 25))
    reads = _catalog_reads(db)
    assert len(reads) == 1, "one statement for the page and its total"
    query, params = reads[0]
    assert "COUNT(*) OVER ()" in query and "LIMIT %s OFFSET %s" in query
    assert params == ("anna", 12, 12)


def test_the_last_page_holds_what_is_left(db: _FakeDB) -> None:
    body = _client(db).get("/api/products", params={"persona": "fresh", "page": 9, "page_size": 12}).json()
    assert [card["id"] for card in body["products"]] == [97, 98, 99, 100]
    assert body["pages"] == 9


def test_the_edit_is_a_bound_parameter_never_sql_text(db: _FakeDB) -> None:
    edit = "anna' or '1'='1"
    _client(db).get("/api/products", params={"persona": edit, "page": 1})
    query, params = _catalog_reads(db)[0]
    assert params[0] == edit
    assert "anna" not in query and "'1'" not in query


def test_without_an_edit_every_piece_still_pages(db: _FakeDB) -> None:
    body = _client(db).get("/api/products", params={"page": 1}).json()
    assert len(body["products"]) == 12 and body["pageSize"] == 12
    assert _catalog_reads(db)[0][1] == (None, 12, 0)


@pytest.mark.parametrize("params", [
    {"page": 0},
    {"page": -1},
    {"page": 1001},
    {"page": 1, "page_size": 0},
    {"page": 1, "page_size": PAGE_SIZE_MAX + 1},
    {"page": "two"},
])
def test_a_page_or_size_out_of_bounds_is_refused_before_any_read(db: _FakeDB, params: Dict[str, Any]) -> None:
    assert _client(db).get("/api/products", params=params).status_code == 422
    assert db.calls == []


def test_the_page_size_cap_itself_is_served(db: _FakeDB) -> None:
    body = _client(db).get("/api/products", params={"page": 1, "page_size": PAGE_SIZE_MAX}).json()
    assert len(body["products"]) == PAGE_SIZE_MAX == 30


def test_a_page_past_the_last_is_not_found(db: _FakeDB) -> None:
    response = _client(db).get("/api/products", params={"persona": "fresh", "page": 10, "page_size": 12})
    assert response.status_code == 404
    assert response.json()["detail"] == "page_not_found"


def test_the_first_page_of_an_empty_catalog_is_empty_not_missing() -> None:
    body = _client(_FakeDB(size=0)).get("/api/products", params={"page": 1}).json()
    assert body == {"products": [], "page": 1, "pageSize": 12, "total": 0, "pages": 0}
