"""Gateway retrieval receipts: the Lambda writes the one ``store_tools`` receipt.

The receipt is built and inserted by ``store_tools.search_products`` through the
runner it is given. On the Gateway rail that runner is ``run_store_sql``, so
these tests drive ``lambda_handler`` with a fake Data API and read the INSERT
back out of its named parameters. The execution receipt (``tool_audit``) is a
separate write through ``execute_write``; it is faked at the Data API client.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

_DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(_DEPLOY) not in sys.path:
    sys.path.insert(0, str(_DEPLOY))

import common.dataapi as dataapi  # noqa: E402
import pellier_store_tools as lambda_tools  # noqa: E402
from services.retrieval_receipt import _COLUMN_ORDER  # noqa: E402

TURN_ID = "turn-0123456789abcdef0123456789abcdef"
RECEIPT_TABLE = "INSERT INTO pellier.retrieval_receipts"


def _branch_row(product_id: str, name: str, price: str, rating: str, **ranks: Any) -> Dict[str, Any]:
    """A catalog row as the Data API returns it: numbers and JSON arrive as text."""
    return {
        "product_id": product_id,
        "name": name,
        "brand": "Pellier",
        "color": "Sand",
        "description": name,
        "img_url": "https://example.com/p.jpg",
        "category": "Resort",
        "price": price,
        "rating": rating,
        "reviews": "20",
        "badge": None,
        "tags": '["linen"]',
        "materials": '["linen"]',
        "quantity": 4,
        "updated_at": f"2026-08-0{product_id[-1]}T00:00:00+00:00",
        **ranks,
    }


def _vector_rows() -> List[Dict[str, Any]]:
    return [
        _branch_row("P-1", "Linen Camp Shirt", "128.0", "4.8", similarity=0.9),
        _branch_row("P-2", "Linen Trouser", "148.0", "4.9", similarity=0.8),
    ]


def _fts_rows() -> List[Dict[str, Any]]:
    return [
        _branch_row("P-2", "Linen Trouser", "148.0", "4.9", fts_rank_score=0.6),
        _branch_row("P-1", "Linen Camp Shirt", "128.0", "4.8", fts_rank_score=0.5),
    ]


class _Transport:
    """The Data API behind ``run_store_sql`` (reads) and ``execute_write`` (audit)."""

    def __init__(self, vector_rows: List[Dict[str, Any]], fts_rows: List[Dict[str, Any]]) -> None:
        self.vector_rows = vector_rows
        self.fts_rows = fts_rows
        self.statements: List[tuple[str, Dict[str, Any]]] = []
        self.audit_calls: List[Dict[str, Any]] = []

    def execute_sql(self, sql: str, parameters: list | None = None) -> List[Dict[str, Any]]:
        bound = {item["name"]: item["value"] for item in parameters or []}
        self.statements.append((sql, bound))
        if "to_tsquery" in sql:
            return [dict(row) for row in self.fts_rows]
        if "query_embedding" in sql:
            return [dict(row) for row in self.vector_rows]
        return []

    def execute_statement(self, **kwargs: Any) -> Dict[str, Any]:
        self.audit_calls.append(kwargs)
        return {"numberOfRecordsUpdated": 1}

    @property
    def branches(self) -> List[tuple[str, Dict[str, Any]]]:
        return [(s, b) for s, b in self.statements if "FROM pellier.product_catalog" in s]

    @property
    def receipts(self) -> List[Dict[str, Any]]:
        """Each receipt INSERT as ``{column: bound string value}``."""
        found = []
        for sql, bound in self.statements:
            if RECEIPT_TABLE in sql:
                found.append(
                    {
                        column: next(iter(bound[f"p{index}"].values()), None)
                        for index, column in enumerate(_COLUMN_ORDER)
                    }
                )
        return found


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> _Transport:
    fake = _Transport(_vector_rows(), _fts_rows())
    monkeypatch.setattr(dataapi, "execute_sql", fake.execute_sql)
    monkeypatch.setattr(dataapi, "rds_client", fake)
    monkeypatch.setattr(lambda_tools, "query_embedding", lambda _query: [0.1, 0.2])
    monkeypatch.setattr(
        lambda_tools,
        "rerank_documents",
        lambda *, query, documents, top_n: [
            {"index": 1, "relevance_score": 0.92},
            {"index": 0, "relevance_score": 0.81},
        ],
    )
    return fake


def _search(arguments: Dict[str, Any]) -> Dict[str, Any]:
    response = lambda_tools.lambda_handler(
        {"name": "search_products", "arguments": arguments}, SimpleNamespace(client_context=None)
    )
    assert response.get("isError") is not True
    return json.loads(response["content"][0]["text"])


def test_gateway_search_persists_actual_ranking_evidence(transport: _Transport) -> None:
    payload = _search({"query": "linen for a resort", "turn_id": TURN_ID, "limit": 2, "max_price": 175})

    assert [product["productId"] for product in payload["products"]] == ["P-2", "P-1"]
    assert "_receipt_evidence" not in payload

    assert len(transport.receipts) == 1
    values = transport.receipts[0]
    assert values["turn_id"] == TURN_ID
    assert values["query_preview"] == "linen for a resort"
    assert values["rail"] == "gateway-mcp"
    assert values["embedding_model"] == dataapi.EMBED_MODEL_ID
    assert values["rerank_model"] == dataapi.RERANK_MODEL_ID
    assert json.loads(values["candidate_product_ids"]) == ["P-1", "P-2"]
    assert json.loads(values["citation_ids"]) == ["P-2", "P-1"]
    assert json.loads(values["vector_ranks"]) == {"P-1": 1, "P-2": 2}
    assert json.loads(values["lexical_ranks"]) == {"P-1": 2, "P-2": 1}
    assert json.loads(values["rerank_scores"]) == {"P-2": 0.92, "P-1": 0.81}
    rrf = json.loads(values["rrf_scores"])
    assert rrf["P-1"] == pytest.approx(1 / 61 + 1 / 62)
    assert rrf["P-2"] == pytest.approx(1 / 62 + 1 / 61)
    snapshots = json.loads(values["citation_snapshots"])
    assert [snapshot["entity_id"] for snapshot in snapshots] == ["P-2", "P-1"]
    assert snapshots[0]["quote"] == "Linen Trouser: Linen Trouser"
    assert len(values["citation_snapshot_hash"]) == 64
    hard = json.loads(values["hard_constraints"])
    assert hard["price_max_usd"] == 175
    config = json.loads(values["retrieval_config"])
    assert config["search_method"] == "hybrid+rerank"
    assert config["rerank_pool_k"] >= 3


def test_gateway_search_also_writes_the_execution_receipt_for_the_same_turn(
    transport: _Transport,
) -> None:
    _search({"query": "linen for a resort", "turn_id": TURN_ID, "limit": 2})

    assert len(transport.audit_calls) == 1
    audit = transport.audit_calls[0]
    assert "INSERT INTO pellier.tool_audit" in audit["sql"]
    bound = {item["name"]: item["value"] for item in audit["parameters"]}
    assert json.loads(bound["args"]["stringValue"])["turn_id"] == TURN_ID
    assert bound["tool"] == {"stringValue": "search_products"}


def test_gateway_receipt_cites_only_rows_that_survive_min_rating(transport: _Transport) -> None:
    transport.vector_rows.append(_branch_row("P-3", "Linen Scarf", "60.0", "3.9"))

    payload = _search({"query": "linen for a resort", "turn_id": TURN_ID, "limit": 5, "min_rating": 4.5})

    shown = [product["productId"] for product in payload["products"]]
    assert "P-3" not in shown
    cited = json.loads(transport.receipts[0]["citation_ids"])
    assert cited == shown


def test_gateway_search_applies_hard_filters_in_both_branches_before_fusion(
    transport: _Transport,
) -> None:
    payload = _search(
        {"query": "linen for a resort", "turn_id": TURN_ID, "limit": 2, "max_price": 175}
    )

    assert payload["constraints_applied_before_rerank"] is True
    assert len(transport.branches) == 2
    for sql, bound in transport.branches:
        assert "price <= :p1" in sql
        assert bound["p1"] == {"doubleValue": 175.0}
    assert payload["search_method"] == "hybrid+rerank"


def test_gateway_search_binds_no_filter_predicates_when_none_are_given(
    transport: _Transport,
) -> None:
    _search({"query": "linen", "limit": 2})

    assert len(transport.branches) == 2
    for sql, _bound in transport.branches:
        assert "price <=" not in sql
        assert "category = ANY" not in sql
        assert "quantity > 0" not in sql


@pytest.mark.parametrize("turn_id", ["not-a-server-minted-turn", "turn-x", "turn-abc"])
def test_gateway_search_never_persists_an_untrusted_turn_id(
    transport: _Transport, turn_id: str
) -> None:
    payload = _search({"query": "linen", "turn_id": turn_id, "limit": 1})

    assert payload["status"] == "success"
    assert transport.receipts == []


def test_gateway_search_without_a_turn_id_writes_no_evidence_at_all(
    transport: _Transport,
) -> None:
    _search({"query": "linen", "limit": 1})

    assert transport.receipts == []
    assert transport.audit_calls == []


def test_gateway_rerank_outage_falls_back_to_rrf_order_and_says_so(
    transport: _Transport, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lambda_tools, "rerank_documents", lambda **_kwargs: [])

    payload = _search({"query": "linen for a resort", "turn_id": TURN_ID, "limit": 2})

    assert payload["search_method"] == "hybrid (rerank fallback to RRF order)"
    assert [product["productId"] for product in payload["products"]] == ["P-1", "P-2"]
    values = transport.receipts[0]
    assert json.loads(values["rerank_scores"]) == {}
    assert json.loads(values["retrieval_config"])["search_method"] == payload["search_method"]
