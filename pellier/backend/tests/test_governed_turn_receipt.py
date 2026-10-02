"""Tests for the immutable, participant-facing governed turn receipt."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

import pytest

from services.governed_turn_receipt import (
    _receipt_citations,
    _trace_metadata,
    get_turn_receipt,
    get_visible_tool_audit,
    map_answer_claims,
    persist_turn_receipt,
)
from services.managed_policy import recent_decisions
from services.retrieval_receipt import citation_snapshot_hash


@pytest.mark.parametrize("value", [True, False])
def test_durable_trace_preserves_observed_transport_flags(value: bool) -> None:
    trace = _trace_metadata({
        "jwtPassthrough": value, "gatewayPassthrough": value,
        "authorization": "private-token", "spans": [{"prompt": "private-text"}],
    })
    assert trace == {"jwtPassthrough": value, "gatewayPassthrough": value}


def test_durable_trace_keeps_customer_bindings_without_customer_ids() -> None:
    trace = _trace_metadata({
        "runtime": "agentcore-managed",
        "customerBindings": [
            {"tool": "get_ticket_history", "status": "success", "customerScope": "server",
             "requestedOtherCustomer": True, "customer_id": "CUST-JESSICA"},
            {"tool": "get_ticket_history", "customerScope": "invented"},
            "not-a-binding",
        ],
    })
    assert trace["customerBindings"] == [
        {"tool": "get_ticket_history", "status": "success",
         "customerScope": "server", "requestedOtherCustomer": True},
    ]


def test_durable_trace_omits_customer_bindings_when_none_were_observed() -> None:
    assert "customerBindings" not in _trace_metadata({"runtime": "agentcore-managed"})


def test_durable_trace_does_not_infer_missing_transport_flags() -> None:
    trace = _trace_metadata({"runtime": "agentcore-managed", "rail": "gateway-mcp"})
    assert "jwtPassthrough" not in trace
    assert "gatewayPassthrough" not in trace


def _model_execution(*models: tuple[str, str]) -> dict[str, Any]:
    return {"spans": [
        {"name": f"invoke_agent {agent}", "attributes": {
            "gen_ai.agent.name": agent,
            "gen_ai.request.model": model,
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 5,
            "gen_ai.input.messages": "private prompt",
        }}
        for agent, model in models
    ]}


@pytest.mark.parametrize("models,route,managed,expected", [
    ([("router", "sonnet"), ("search", "opus")], "search", None, "opus"),
    ([("inventory", "sonnet")], "inventory", None, "sonnet"),
    ([("search", "fast-model")], "search", None, "fast-model"),
    ([("router", "sonnet")], "search", None, None),
    ([("search", "first"), ("search", "second")], "search", None, None),
    ([], "search", None, None),
    ([], "Search Agent", "managed-specialist", "managed-specialist"),
])
def test_receipt_attributes_the_observed_specialist_model(
    models, route, managed, expected,
) -> None:
    db = _ReceiptDB()
    receipt = asyncio.run(persist_turn_receipt(
        db, turn_id="turn-persisted", session_id="session-1", principal_sub=None,
        rail="in-process", terminal_status="complete", latency_ms=32,
        agent_execution=_model_execution(*models), specialist_route=route,
        managed_model_id=managed,
    ))
    assert receipt is not None
    config = json.loads(db.calls[-1][6])
    assert config["agent_model"] == expected
    assert "private prompt" not in json.dumps(config)
    assert [(r["purpose"], r["model_id"]) for r in config["model_invocations"]] == [
        (f"agent:{agent}", model) for agent, model in models
    ]


def test_terminal_receipt_forwards_execution_instead_of_legacy_router_model(monkeypatch):
    import app

    db = _ReceiptDB()
    monkeypatch.setattr(app, "db_service", db)
    result = asyncio.run(app._persist_terminal_turn_receipt(
        turn_id="turn-persisted", session_id="session-1", user=None,
        rail="in-process", terminal_status="complete", started_at=time.perf_counter(),
        skip_handoff_lookup=True, specialist_route="search", model_id="sonnet",
        agent_execution=_model_execution(("router", "sonnet"), ("search", "opus")),
    ))
    assert result is not None
    inserted = next(c for c in db.calls if "INSERT INTO pellier.governed_turn_receipts" in c[0])
    assert json.loads(inserted[6])["agent_model"] == "opus"


def _citation_snapshots() -> list[dict[str, Any]]:
    return [
        {
            "entity_id": "P-2",
            "source_uri": "aurora://pellier/product_catalog/P-2",
            "revision": "2026-08-02T00:00:00+00:00",
            "quote": "Linen Camp Shirt: Breathable resort shirt",
        },
        {
            "entity_id": "P-1",
            "source_uri": "aurora://pellier/product_catalog/P-1",
            "revision": "2026-08-01T00:00:00+00:00",
            "quote": "Linen Trouser: Lightweight travel layer",
        },
    ]


class _ReceiptDB:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def fetch_one(self, query: str, *params: Any) -> dict[str, Any] | None:
        self.calls.append((query, *params))
        if "FROM pellier.retrieval_receipts" in query:
            return {
                "receipt_id": 42,
                "embedding_model": "us.cohere.embed-v4:0",
                "rerank_model": "cohere.rerank-v3-5:0",
                "retrieval_config": {"rrf_k": 60},
                "citation_ids": ["P-2", "P-1"],
                "citation_snapshots": _citation_snapshots(),
                "citation_snapshot_hash": citation_snapshot_hash(
                    _citation_snapshots()
                ),
            }
        if "FROM pellier.governed_turn_receipts" in query:
            assert params == ("turn-persisted", "principal-1")
            return {
                "turn_id": "turn-persisted",
                "session_id": "session-1",
                "principal_sub": "principal-1",
                "principal_verified": True,
                "rail": "gateway-mcp",
                "model_config": '{"agent_model":"model-1"}',
                "retrieval_receipt_id": 42,
                "citations": '[{"entity_id":"P-1"}]',
                "tool_audit_ids": "[]",
                "policy_events": '[{"decision":"NOT_EVALUATED"}]',
                "trace": "{}",
                "terminal_outcome": "{}",
                "terminal_status": "complete",
                "latency_ms": 32,
                "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
            }
        return None

    async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, *params))
        if "FROM pellier.tool_audit" in query:
            assert params == ("turn-persisted",)
            return [
                {
                    "audit_id": 9,
                    "tool": "search_products_hybrid",
                    "caller": "gateway",
                    "latency_ms": 18,
                    "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
                }
            ]
        if "FROM pellier.governed_receipts" in query:
            assert params == ("turn-persisted",)
            return []
        if "FROM pellier.product_catalog" in query:
            raise AssertionError("turn receipts must not reread mutable catalog rows")
        return []

    async def execute_query(self, *args: Any) -> None:
        self.calls.append(args)


def test_persisted_receipt_uses_captured_catalog_evidence_not_live_catalog() -> None:
    db = _ReceiptDB()

    receipt = asyncio.run(
        persist_turn_receipt(
            db,
            turn_id="turn-persisted",
            session_id="session-1",
            principal_sub="principal-1",
            rail="gateway-mcp",
            terminal_status="complete",
            latency_ms=32,
            trace={
                "traceKind": "managed-runtime-receipt",
                "traceId": "trace-1",
                "spans": [{"invented": "must not persist"}],
            },
        )
    )

    assert receipt == {
        "turn_id": "turn-persisted",
        "rail": "gateway-mcp",
        "terminal_status": "complete",
        "citation_count": 2,
        "tool_count": 1,
        "policy_decision": "NOT_EVALUATED",
        "latency_ms": 32,
    }
    insert = db.calls[-1]
    assert "INSERT INTO pellier.governed_turn_receipts" in insert[0]
    citations = json.loads(insert[8])
    assert [citation["entity_id"] for citation in citations] == ["P-2", "P-1"]
    assert citations[0] == {
        "evidence_id": "retrieval-42-catalog-P-2",
        "source_uri": "aurora://pellier/product_catalog/P-2",
        "revision": "2026-08-02T00:00:00+00:00",
        "quote": "Linen Camp Shirt: Breathable resort shirt",
        "entity_id": "P-2",
    }
    policy_events = json.loads(insert[10])
    assert policy_events[0]["decision"] == "NOT_EVALUATED"
    trace = json.loads(insert[11])
    assert trace["traceId"] == "trace-1"
    assert "spans" not in trace


def test_answer_sentences_map_to_the_cited_products_they_name() -> None:
    citations = _receipt_citations(
        retrieval_receipt_id=42,
        citation_snapshots=_citation_snapshots(),
        expected_snapshot_hash=citation_snapshot_hash(_citation_snapshots()),
    )

    claims, unsupported = map_answer_claims(
        "The Linen Camp Shirt breathes well in Goa heat. "
        "You will also want a good sunscreen!",
        citations,
    )

    assert claims == [
        {
            "text": "The Linen Camp Shirt breathes well in Goa heat.",
            "evidence_ids": ["retrieval-42-catalog-P-2"],
        }
    ]
    assert unsupported == ["You will also want a good sunscreen!"]


def test_claim_mapping_is_case_insensitive_and_handles_empty_input() -> None:
    citations = _receipt_citations(
        retrieval_receipt_id=42,
        citation_snapshots=_citation_snapshots(),
        expected_snapshot_hash=citation_snapshot_hash(_citation_snapshots()),
    )

    claims, unsupported = map_answer_claims(
        "Pair the linen trouser with the LINEN CAMP SHIRT? Yes.", citations
    )

    assert claims[0]["evidence_ids"] == [
        "retrieval-42-catalog-P-2",
        "retrieval-42-catalog-P-1",
    ]
    assert unsupported == ["Yes."]
    assert map_answer_claims("", citations) == ([], [])
    assert map_answer_claims("Nothing cited here.", []) == ([], ["Nothing cited here."])


def test_persisted_receipt_records_claims_inside_the_terminal_outcome() -> None:
    db = _ReceiptDB()

    receipt = asyncio.run(
        persist_turn_receipt(
            db,
            turn_id="turn-persisted",
            session_id="session-1",
            principal_sub="principal-1",
            rail="gateway-mcp",
            terminal_status="complete",
            latency_ms=32,
            answer_text="Start with the Linen Trouser. Pack light.",
        )
    )

    assert receipt is not None
    insert = db.calls[-1]
    outcome = json.loads(insert[13])
    assert outcome["claims"] == [
        {
            "text": "Start with the Linen Trouser.",
            "evidence_ids": ["retrieval-42-catalog-P-1"],
        }
    ]
    assert outcome["unsupported"] == ["Pack light."]


def test_invalid_citation_snapshot_hash_suppresses_citations() -> None:
    citations = _receipt_citations(
        retrieval_receipt_id=42,
        citation_snapshots=_citation_snapshots(),
        expected_snapshot_hash="not-the-captured-hash",
    )

    assert citations == []


def test_explicit_governed_policy_event_wins_over_absence() -> None:
    db = _ReceiptDB()

    async def policy_rows(query: str, *params: Any) -> list[dict[str, Any]]:
        if "FROM pellier.tool_audit" in query:
            return []
        if "FROM pellier.governed_receipts" in query:
            return [
                {
                    "receipt_id": 7,
                    "audit_id": None,
                    "tool": "initiate_return",
                    "caller": "gateway",
                    "decision": "DENY",
                    "policy_engine_id": "policy-1",
                    "policy_name": "deny-return",
                    "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
                }
            ]
        if "FROM pellier.product_catalog" in query:
            return []
        return []

    db.fetch_all = policy_rows  # type: ignore[method-assign]
    receipt = asyncio.run(
        persist_turn_receipt(
            db,
            turn_id="turn-persisted",
            session_id="session-1",
            principal_sub="principal-1",
            rail="gateway-mcp",
            terminal_status="denied-before-execution",
            latency_ms=5,
            terminal_error_code="policy_denied",
        )
    )

    assert receipt is not None
    assert receipt["policy_decision"] == "DENY"


def test_receipt_read_is_scoped_to_the_verified_principal() -> None:
    receipt = asyncio.run(
        get_turn_receipt(
            _ReceiptDB(), turn_id="turn-persisted", principal_sub="principal-1"
        )
    )

    assert receipt is not None
    assert receipt["principal_sub"] == "principal-1"
    assert receipt["citations"] == [{"entity_id": "P-1"}]
    assert receipt["created_at"] == "2026-08-12T00:00:00+00:00"


def test_receipt_persistence_failure_returns_no_ui_receipt() -> None:
    class _BrokenDB:
        async def fetch_one(self, *_: Any) -> None:
            raise RuntimeError("database unavailable")

    result = asyncio.run(
        persist_turn_receipt(
            _BrokenDB(),
            turn_id="turn-broken",
            session_id="session-1",
            principal_sub="principal-1",
            rail="in-process",
            terminal_status="failed",
            latency_ms=1,
        )
    )

    assert result is None


def test_visible_tool_audit_uses_receipt_principal_scope() -> None:
    class _AuditDB:
        seen: tuple[Any, ...] | None = None

        async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
            self.seen = (query, *params)
            return [
                {
                    "audit_id": 11,
                    "session_id": "session-1",
                    "tool": "initiate_return",
                    "caller": "gateway",
                    "args": {"turn_id": "turn-persisted"},
                    "result": {"status": "success"},
                    "latency_ms": 12,
                    "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
                }
            ]

    db = _AuditDB()
    rows = asyncio.run(
        get_visible_tool_audit(db, principal_sub="principal-1", limit=10)
    )

    assert rows[0]["audit_id"] == 11
    assert rows[0]["created_at"] == "2026-08-12T00:00:00+00:00"
    assert db.seen is not None
    assert db.seen[1:] == ("principal-1", "principal-1", 10)
    assert "governed_turn_receipts" in db.seen[0]
    assert "jsonb_build_object('audit_id', ta.audit_id)" in db.seen[0]


def test_recent_policy_decisions_include_explicit_allow_and_deny() -> None:
    class _PolicyDB:
        seen: tuple[Any, ...] | None = None

        async def fetch_all(self, query: str, *params: Any) -> list[dict[str, Any]]:
            self.seen = (query, *params)
            return [
                {
                    "receipt_id": 1,
                    "audit_id": 2,
                    "session_id": "session-1",
                    "tool": "initiate_return",
                    "caller": "gateway",
                    "decision": "ALLOW",
                    "args": {"turn_id": "turn-1"},
                    "policy_engine_id": "engine-1",
                    "policy_name": "allow-return",
                    "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
                },
                {
                    "receipt_id": 3,
                    "audit_id": None,
                    "session_id": "session-1",
                    "tool": "initiate_return",
                    "caller": "gateway",
                    "decision": "DENY",
                    "args": {"turn_id": "turn-2"},
                    "policy_engine_id": "engine-1",
                    "policy_name": "deny-return",
                    "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
                },
            ]

    db = _PolicyDB()
    result = asyncio.run(
        recent_decisions(
            db, principal_sub="principal-1", session_id="session-1", limit=10
        )
    )

    assert result["source"] == "governed-receipts"
    assert [decision["decision"] for decision in result["decisions"]] == [
        "ALLOW",
        "DENY",
    ]
    assert db.seen is not None
    assert db.seen[1:] == ("principal-1", "session-1", 10)
    assert "principal_id = %s" in db.seen[0]


def _short_name_snapshots() -> list[dict[str, Any]]:
    """A cited product whose name is a common substring of ordinary words."""
    return [
        {
            "entity_id": "P-9",
            "source_uri": "aurora://pellier/product_catalog/P-9",
            "revision": "2026-08-09T00:00:00+00:00",
            "quote": "Ash: Hand-turned ash serving bowl",
        }
    ]


def test_a_short_product_name_does_not_match_inside_a_longer_word() -> None:
    """Substring matching attached evidence to sentences it did not support."""
    citations = _receipt_citations(
        retrieval_receipt_id=42,
        citation_snapshots=_short_name_snapshots(),
        expected_snapshot_hash=citation_snapshot_hash(_short_name_snapshots()),
    )

    claims, unsupported = map_answer_claims(
        "Wash the cashmere separately. The Ash bowl anchors the table.",
        citations,
    )

    assert claims == [
        {
            "text": "The Ash bowl anchors the table.",
            "evidence_ids": ["retrieval-42-catalog-P-9"],
        }
    ]
    assert unsupported == ["Wash the cashmere separately."]


def test_a_multi_word_name_only_counts_as_a_whole_phrase() -> None:
    """Every word present is not the same claim as the product being named."""
    citations = _receipt_citations(
        retrieval_receipt_id=42,
        citation_snapshots=_citation_snapshots(),
        expected_snapshot_hash=citation_snapshot_hash(_citation_snapshots()),
    )

    claims, unsupported = map_answer_claims(
        "Linen wears well, and a camp collar shirt travels flat.", citations
    )

    assert claims == []
    assert unsupported == [
        "Linen wears well, and a camp collar shirt travels flat."
    ]


def _no_separator_snapshots() -> list[dict[str, Any]]:
    """Quotes the writer produces when a catalog row has no description."""
    return [
        {
            "entity_id": "P-7",
            "source_uri": "aurora://pellier/product_catalog/P-7",
            "revision": "2026-08-07T00:00:00+00:00",
            "quote": "Ceramic Vase",
        },
        {
            "entity_id": "P-8",
            "source_uri": "aurora://pellier/product_catalog/P-8",
            "revision": "2026-08-08T00:00:00+00:00",
            "quote": "Rope Basket:A woven floor basket",
        },
    ]


def test_a_citation_quote_without_the_separator_still_yields_its_name() -> None:
    """A description-free product is captured as a bare name, not ``Name: ...``."""
    citations = _receipt_citations(
        retrieval_receipt_id=42,
        citation_snapshots=_no_separator_snapshots(),
        expected_snapshot_hash=citation_snapshot_hash(_no_separator_snapshots()),
    )

    claims, unsupported = map_answer_claims(
        "The Ceramic Vase reads quiet. The Rope Basket hides the rest. Done.",
        citations,
    )

    assert claims == [
        {
            "text": "The Ceramic Vase reads quiet.",
            "evidence_ids": ["retrieval-42-catalog-P-7"],
        },
        {
            "text": "The Rope Basket hides the rest.",
            "evidence_ids": ["retrieval-42-catalog-P-8"],
        },
    ]
    assert unsupported == ["Done."]
