"""Focused tests for the participant-facing Builders' Session client."""

from __future__ import annotations

import argparse
import importlib.util
import io
import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO = Path(__file__).resolve().parents[3]
CLIENT = REPO / "scripts" / "builders_lab.py"


def _load_client():
    spec = importlib.util.spec_from_file_location("builders_lab_client", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retrieval_rejects_wrong_math_ineligible_and_missing_results():
    client = _load_client()
    row = {"productId": "4", "price": 20, "quantity": 8,
           "vectorRank": 1, "keywordRank": 2, "rrfScore": 1 / 61 + 1 / 62}
    assert client.retrieval_errors({"eligibleCount": 1, "rows": [row]}, 100) == []
    assert client.retrieval_errors({"eligibleCount": 0, "rows": []}, 0) == []
    assert client.retrieval_errors({"eligibleCount": 1, "rows": []}, 100)
    for changes in ({"rrfScore": 0}, {"price": 101}, {"quantity": 0}):
        assert client.retrieval_errors({"eligibleCount": 1, "rows": [row | changes]}, 100)


def test_agent_check_scopes_receipt_to_its_own_turn(monkeypatch, tmp_path):
    client = _load_client()
    seen = {}

    def stream(_base, payload, **kwargs):
        seen["session"] = payload["session_id"]
        return [{"type": "complete", "response": {"message": "Inventory result"}}]

    def check(args):
        assert args.session == seen["session"]
        assert args.within_minutes == 5
        return 0

    monkeypatch.setattr(client, "_stream_chat", stream)
    monkeypatch.setattr(client, "receipt", check)
    assert client.agent_check(argparse.Namespace(
        base_url="http://example", output=tmp_path / "turn.sse",
    )) == 0


def test_inventory_sql_binds_hostile_input_and_keeps_zero_stock():
    from services.inventory_sql import warehouse_inventory_query

    hostile = "4' OR 1=1 --"
    query, parameters = warehouse_inventory_query(hostile)
    assert hostile not in query
    assert parameters == (hostile,)
    assert "wi.product_id = %s" in query
    assert "quantity >" not in query
    assert "JOIN pellier.warehouses" in query


@pytest.mark.parametrize("status,expected", [(401, 0), (403, 0), (404, 1), (500, 1)])
def test_runtime_negative_auth_check_rejects_unrelated_errors(monkeypatch, status, expected):
    client = _load_client()
    monkeypatch.setattr(client, "_repo_env", lambda: {"AGENTCORE_RUNTIME_ENDPOINT": "test-runtime"})

    def refuse(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://example.invalid", status, "test", {}, io.BytesIO(b"test"))

    monkeypatch.setattr(client.urllib.request, "urlopen", refuse)
    assert client.runtime(argparse.Namespace(
        without_token=True, timeout=5, query="test", user_id="test",
    )) == expected


def test_retrieval_uses_read_only_sql_and_rejects_bad_embedding(monkeypatch, tmp_path):
    client = _load_client()
    comparison = tmp_path / "comparison.json"
    comparison.write_text(client.json.dumps({
        "query": client.DEFAULT_QUERY, "queryEmbedding": [0.5] * 1024,
    }))
    args = argparse.Namespace(
        max_price=0, reference_vector=False, comparison=comparison,
        sql=tmp_path / "retrieval.sql", terms="housewarming | gift",
        output=tmp_path / "result.json",
    )
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert "default_transaction_read_only=on" in kwargs["env"]["PGOPTIONS"]
        assert "statement_timeout=15000" in kwargs["env"]["PGOPTIONS"]
        assert command[-2:] == ["-f", str(args.sql)]
        return subprocess.CompletedProcess(command, 0, '{"eligibleCount":0,"rows":[]}', "")

    monkeypatch.setattr(client.subprocess, "run", run)
    assert client.retrieval(args) == 0
    comparison.write_text('{"queryEmbedding":[0.5]}')
    with pytest.raises(RuntimeError):
        client.retrieval(args)
    assert len(calls) == 1


def _comparison_payload(rerank_executed: bool = True) -> dict[str, Any]:
    return {
        "sharedQueryEmbeddingObservedMs": 8,
        "strategies": [
            {
                "strategy": name,
                "observedMs": index * 10,
                "modeledCostPerThousandUsd": index / 100,
                "costComponents": ["queryEmbedding"],
                "products": [{"name": f"Product {index}"}],
                **(
                    {
                        "rerankExecuted": rerank_executed,
                        "productOrderSource": (
                            "rerank" if rerank_executed else "hybrid RRF (rerank degraded)"
                        ),
                        "degradedReason": (
                            None
                            if rerank_executed
                            else "ThrottlingException: rate exceeded"
                        ),
                    }
                    if "rerank" in name
                    else {}
                ),
                **(
                    {
                        "extractedFilters": {
                            "priceMaxUsd": 100,
                            "inStockOnly": True,
                            "hardConstraintsEnforced": True,
                        }
                    }
                    if index == 4
                    else {}
                ),
            }
            for index, name in enumerate(
                ("vector only", "hybrid", "hybrid + rerank", "agentic rerank"),
                start=1,
            )
        ],
        "costModel": {
            "pricingReviewedOn": "2026-08-16",
            "pricingSource": "https://aws.amazon.com/bedrock/pricing/",
            "components": {"queryEmbedding": {"formula": "requests * rate"}},
        },
    }


def test_readiness_requires_database_claude_and_starter_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _load_client()
    responses = {
        "/api/health": {"status": "healthy", "database": "connected"},
        "/api/agent-trace/build-state": {
            "agents": {"Stock Keeper": "exercise"},
            "tools": {"floor_check": "exercise"},
        },
    }
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda _base, path, **_kwargs: responses[path],
    )
    monkeypatch.setattr(
        client.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["claude", "--version"],
            0,
            stdout="2.1.233 (Claude Code)\n",
            stderr="",
        ),
    )
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv(
        "ANTHROPIC_MODEL", "global.anthropic.claude-sonnet-4-6"
    )

    assert client.readiness(argparse.Namespace(base_url="http://example")) == 0

    responses["/api/health"]["database"] = "disconnected"
    assert client.readiness(argparse.Namespace(base_url="http://example")) == 1


def test_build_state_enforces_expected_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _load_client()
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda *_args, **_kwargs: {
            "agents": {"Stock Keeper": "shipped"},
            "tools": {"floor_check": "shipped"},
        },
    )
    args = argparse.Namespace(
        base_url="http://example",
        expect="shipped",
        expect_agent=None,
        expect_tool=None,
    )

    assert client.build_state(args) == 0

    args.expect = "exercise"
    assert client.build_state(args) == 1

    args.expect = None
    args.expect_agent = "shipped"
    args.expect_tool = "shipped"
    assert client.build_state(args) == 0

    args.expect_agent = "exercise"
    assert client.build_state(args) == 1


def test_tool_check_requires_brooklyn_quantity_and_ship_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _load_client()
    seen: dict[str, Any] = {}

    def fake_request(
        _base_url: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        seen["path"] = path
        seen["query"] = kwargs["query"]
        return {
            "status": "success",
            "warehouses": [
                {
                    "warehouse_id": "BK-01",
                    "city": "Brooklyn",
                    "quantity": 8,
                    "ship_window_min": 1,
                    "ship_window_max": 2,
                }
            ],
        }

    monkeypatch.setattr(client, "_request_json", fake_request)
    args = argparse.Namespace(
        base_url="http://example",
        query="Hadley shirt",
    )

    assert client.tool_check(args) == 0
    assert seen == {
        "path": "/api/agent-trace/tools/floor-check/run",
        "query": {"product_query": "Hadley shirt"},
    }


def test_compare_writes_full_response_and_checks_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _load_client()
    seen: dict[str, Any] = {}

    def fake_request(
        _base_url: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        seen["path"] = path
        seen["query"] = kwargs["query"]
        return _comparison_payload()

    monkeypatch.setattr(client, "_request_json", fake_request)
    output = tmp_path / "comparison.json"
    args = argparse.Namespace(
        base_url="http://example",
        query=client.DEFAULT_QUERY,
        output=output,
    )

    assert client.compare(args) == 0
    assert seen == {
        "path": "/api/agent-trace/search-strategies/compare",
        "query": {"query": client.DEFAULT_QUERY},
    }
    assert '"priceMaxUsd": 100' in output.read_text(encoding="utf-8")


def test_compare_fails_when_rerank_silently_degraded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A rerank-labelled row that fell back to fusion order fails the gate.

    Without this, a Bedrock rerank outage still produced a green Lab 2
    checkpoint: four strategies, correct filters, and fusion rows
    presented as reranked results.
    """
    client = _load_client()
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda *_a, **_k: _comparison_payload(rerank_executed=False),
    )
    args = argparse.Namespace(
        base_url="http://example",
        query=client.DEFAULT_QUERY,
        output=tmp_path / "comparison.json",
    )

    assert client.compare(args) == 1


def test_receipt_requires_agent_floor_check_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _load_client()
    seen: dict[str, Any] = {}

    def fake_request(
        _base_url: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        seen["path"] = path
        seen["query"] = kwargs["query"]
        return {
            "source": "pellier.tool_audit",
            "count": 1,
            "rows": [
                {
                    "audit_id": 81,
                    "session_id": "marco-session",
                    "tool": "floor_check",
                    "caller": "agent",
                    "args": {"product_query": "Hadley shirt"},
                    "result": {
                        "status": "success",
                        "warehouses": [
                            {
                                "warehouse_id": "BK-01",
                                "city": "Brooklyn",
                                "quantity": 8,
                                "ship_window_min": 1,
                                "ship_window_max": 2,
                            }
                        ],
                    },
                    "latency_ms": 19,
                    "created_at": "2026-08-24T12:00:00+00:00",
                }
            ],
        }

    monkeypatch.setattr(client, "_request_json", fake_request)

    args = argparse.Namespace(
        base_url="http://example", within_minutes=30, session=None
    )
    assert client.receipt(args) == 0
    # The request must carry the freshness window: an unscoped "latest row"
    # would let a rehearsal or a neighbour's turn satisfy the proof.
    assert seen == {
        "path": "/api/agent-trace/tool-audit/recent",
        "query": {
            "tool": "floor_check",
            "limit": "1",
            "within_minutes": "30",
        },
    }


def test_receipt_scopes_to_an_explicit_session_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _load_client()
    seen: dict[str, Any] = {}

    def fake_request(_base_url: str, path: str, **kwargs: Any) -> dict[str, Any]:
        seen["query"] = kwargs["query"]
        return {"source": "pellier.tool_audit", "count": 0, "rows": []}

    monkeypatch.setattr(client, "_request_json", fake_request)
    args = argparse.Namespace(
        base_url="http://example", within_minutes=5, session="marco-session"
    )

    assert client.receipt(args) == 1
    assert seen["query"]["session_id"] == "marco-session"
    assert seen["query"]["within_minutes"] == "5"


def test_receipt_rejects_missing_audit_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _load_client()
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda *_args, **_kwargs: {
            "source": "pellier.tool_audit",
            "count": 0,
            "rows": [],
        },
    )

    args = argparse.Namespace(
        base_url="http://example", within_minutes=30, session=None
    )
    assert client.receipt(args) == 1


def test_ledger_reuses_one_ownership_token_and_writes_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _load_client()
    calls: list[dict[str, Any]] = []

    def fake_stream(
        _base_url: str,
        payload: dict[str, Any],
        *,
        session_token: str,
        output_path: Path,
        timeout: int = 75,
    ) -> list[dict[str, Any]]:
        calls.append(
            {
                "payload": payload,
                "token": session_token,
                "output": output_path,
                "timeout": timeout,
            }
        )
        if len(calls) == 2:
            return [
                {
                    "type": "complete",
                    "response": {
                        "memory": {
                            "source": "agentcore-memory",
                            "loaded_messages": 2,
                            "persisted": True,
                        }
                    },
                }
            ]
        return []

    monkeypatch.setattr(client, "_stream_chat", fake_stream)
    args = SimpleNamespace(
        base_url="http://example",
        session="builders-ledger-test",
        token="a" * 64,
        session_file=tmp_path / "session.txt",
        ledger_output=tmp_path / "ledger.sse",
        memory_output=tmp_path / "memory.sse",
    )

    assert client.ledger(args) == 0
    assert args.session_file.read_text(encoding="utf-8") == "builders-ledger-test\n"
    assert len(calls) == 2
    assert {call["payload"]["session_id"] for call in calls} == {
        "builders-ledger-test"
    }
    assert {call["token"] for call in calls} == {"a" * 64}
    assert "Without calling a tool" in calls[1]["payload"]["message"]


def test_ledger_does_not_publish_session_before_recall_is_proven(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _load_client()
    monkeypatch.setattr(
        client,
        "_stream_chat",
        lambda *_args, **_kwargs: [
            {
                "type": "complete",
                "response": {
                    "memory": {
                        "source": "agentcore-memory",
                        "loaded_messages": 0,
                        "persisted": True,
                    }
                },
            }
        ],
    )
    session_file = tmp_path / "session.txt"
    args = SimpleNamespace(
        base_url="http://example",
        session="builders-ledger-failed",
        token="a" * 64,
        session_file=session_file,
        ledger_output=tmp_path / "ledger.sse",
        memory_output=tmp_path / "memory.sse",
    )

    assert client.ledger(args) == 1
    assert not session_file.exists()
