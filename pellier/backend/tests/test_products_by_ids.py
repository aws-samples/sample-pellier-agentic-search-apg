"""``GET /api/products?ids=``: the cards for one search result, in its order.

The storefront grid draws the agent's own search result from the product ids
the turn's evidence carried. This read returns exactly those cards, in the
requested order, from one catalog statement plus the one batched stock read
every listing makes; it skips an unknown id and refuses more ids than one
result can hold.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.products import get_db_service, router as products_router
from routes.user import get_agentcore_memory
from services.agentcore_identity import get_agentcore_identity_service
from services.store_tools import RESULT_IDS_MAX


def _row(pid: int, name: str) -> Dict[str, Any]:
    return {
        "id": str(pid), "brand": "Pellier", "name": name, "color": "Ash gray", "price": 58,
        "rating": 4.9, "reviews": "134", "category": "Kitchen and table",
        "image_url": f"/products/{pid}.webp", "badge": None, "tags": ["ceramic"], "tier": 1,
        "quantity": 24,
    }


CATALOG = {
    "22": _row(22, "Linen Napkins, Set of 4"),
    "31": _row(31, "Stoneware Pour-Over Set"),
    "36": _row(36, "Ceramic Tumblers"),
}


class _FakeDB:
    """Answers the catalog read by ``= ANY(%s)``, in table order, and the stock join."""

    def __init__(self) -> None:
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.calls.append((query, params))
        if "warehouse_inventory" in query:
            return [
                {"product_id": pid, "warehouse_id": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY",
                 "quantity": 12, "ship_window_min": 1, "ship_window_max": 2}
                for pid in params[0]
            ]
        if '"productId" = ANY(%s)' not in query:
            return []  # the editorial listing
        wanted = set(params[0])
        # Postgres returns ANY() matches in table order, not the order asked.
        return [dict(row) for key, row in sorted(CATALOG.items()) if key in wanted]


@pytest.fixture
def db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture
def client(db: _FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(products_router)
    app.dependency_overrides[get_db_service] = lambda: db
    app.dependency_overrides[get_agentcore_identity_service] = lambda: None
    app.dependency_overrides[get_agentcore_memory] = lambda: None
    return TestClient(app)


def _ids(response: Any) -> List[int]:
    assert response.status_code == 200, response.text
    return [card["id"] for card in response.json()]


def test_cards_come_back_in_the_requested_order(client: TestClient, db: _FakeDB) -> None:
    response = client.get("/api/products", params={"ids": "36,22,31"})
    assert _ids(response) == [36, 22, 31]
    cards = response.json()
    assert cards[0]["name"] == "Ceramic Tumblers"
    # Each card carries the stock line the grid draws, from the batched read.
    assert cards[0]["warehouses"][0]["city"] == "Brooklyn, NY"
    catalog_reads = [query for query, _ in db.calls if "warehouse_inventory" not in query]
    assert len(catalog_reads) == 1, "one read for every id, never one per card"
    assert '"productId" = ANY(%s)' in catalog_reads[0]


def test_an_unknown_id_is_skipped_and_a_repeat_is_read_once(client: TestClient, db: _FakeDB) -> None:
    assert _ids(client.get("/api/products", params={"ids": "31,999,31,22"})) == [31, 22]
    _, params = db.calls[0]
    assert params == (["31", "999", "22"],)


def test_more_ids_than_one_result_holds_is_refused(client: TestClient, db: _FakeDB) -> None:
    too_many = ",".join(str(pid) for pid in range(1, RESULT_IDS_MAX + 2))
    response = client.get("/api/products", params={"ids": too_many})
    assert response.status_code == 422
    assert db.calls == []
    exactly = ",".join(str(pid) for pid in range(1, RESULT_IDS_MAX + 1))
    assert client.get("/api/products", params={"ids": exactly}).status_code == 200


# Only ASCII digits are ids. "²" passes str.isdigit() and int() refuses it,
# which was a 500; "٣" is a digit int() reads as 3. Both are a 422.
@pytest.mark.parametrize("raw", ["31,abc", "-4", "31;DROP", "0", "1234567", "²", "31,٣"])
def test_a_malformed_id_is_refused_before_any_read(client: TestClient, db: _FakeDB, raw: str) -> None:
    assert client.get("/api/products", params={"ids": raw}).status_code == 422
    assert db.calls == []


def test_an_empty_list_reads_nothing(client: TestClient, db: _FakeDB) -> None:
    assert _ids(client.get("/api/products", params={"ids": ""})) == []
    assert db.calls == []


def test_without_ids_the_listing_is_unchanged(client: TestClient, db: _FakeDB) -> None:
    """The editorial listing still answers; ``ids`` is a separate, bounded read."""
    response = client.get("/api/products")
    assert response.status_code == 200
    query, _ = db.calls[0]
    assert "ANY(%s)" not in query and "ORDER BY" in query
