"""Tests for ``RerankService.rerank`` — Cohere Rerank v3.5 via Bedrock.

We mock boto3 so the tests run offline; the real Bedrock invocation is
exercised in the live verification phase.

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_rerank.py -v
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from services.rerank import RerankService, get_rerank_service
import services.rerank as rerank_module


@pytest.fixture
def mock_bedrock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub boto3.client('bedrock-runtime') so .invoke_model is observable."""
    client = MagicMock()
    # Default: well-formed Cohere response, top_n results in input order.
    body = {
        "results": [
            {"index": 0, "relevance_score": 0.95},
            {"index": 2, "relevance_score": 0.71},
            {"index": 1, "relevance_score": 0.34},
        ]
    }
    client.invoke_model.return_value = {
        "body": MagicMock(read=MagicMock(return_value=json.dumps(body).encode())),
    }
    monkeypatch.setattr(rerank_module.boto3, "client", lambda *_, **__: client)
    return client


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a fresh RerankService for each test."""
    monkeypatch.setattr(rerank_module, "_rerank_service", None)


class TestRerankRequestShape:
    """The Bedrock invoke_model body must match the Cohere v2 schema."""

    def test_request_body_includes_required_fields(
        self, mock_bedrock: MagicMock,
    ) -> None:
        svc = RerankService()
        docs = ["doc one", "doc two", "doc three"]
        svc.rerank(query="my query", documents=docs, top_n=2)

        # invoke_model called once with the right shape.
        assert mock_bedrock.invoke_model.call_count == 1
        kwargs = mock_bedrock.invoke_model.call_args.kwargs
        # The body is a JSON string — parse it back.
        body = json.loads(kwargs["body"])
        assert body["query"] == "my query"
        assert body["documents"] == docs
        # top_n was 2 and we had 3 docs, so it should pass through 2.
        assert body["top_n"] == 2
        assert body["api_version"] == 2

    def test_top_n_clamped_to_document_count(
        self, mock_bedrock: MagicMock,
    ) -> None:
        svc = RerankService()
        docs = ["only doc"]
        svc.rerank(query="q", documents=docs, top_n=10)
        body = json.loads(mock_bedrock.invoke_model.call_args.kwargs["body"])
        # min(top_n=10, len(docs)=1) → 1
        assert body["top_n"] == 1

    def test_uses_configured_model_id(
        self, mock_bedrock: MagicMock,
    ) -> None:
        svc = RerankService()
        svc.rerank(query="q", documents=["doc"], top_n=1)
        kwargs = mock_bedrock.invoke_model.call_args.kwargs
        assert kwargs["modelId"] == svc.model_id
        # Verify it actually points to the rerank model, not something else.
        assert "rerank" in svc.model_id.lower()


class TestRerankResults:

    def test_returns_results_list_verbatim(
        self, mock_bedrock: MagicMock,
    ) -> None:
        svc = RerankService()
        results = svc.rerank("q", ["a", "b", "c"], top_n=3)
        # Mock returned 3 results — passed through unchanged.
        assert len(results) == 3
        assert results[0] == {"index": 0, "relevance_score": 0.95}
        assert results[2]["relevance_score"] == 0.34

    def test_empty_documents_returns_empty_without_calling_bedrock(
        self, mock_bedrock: MagicMock,
    ) -> None:
        svc = RerankService()
        results = svc.rerank(query="q", documents=[], top_n=5)
        assert results == []
        assert mock_bedrock.invoke_model.call_count == 0

    def test_zero_top_n_returns_empty_without_calling_bedrock(
        self, mock_bedrock: MagicMock,
    ) -> None:
        svc = RerankService()
        results = svc.rerank(query="q", documents=["doc"], top_n=0)
        assert results == []
        assert mock_bedrock.invoke_model.call_count == 0


class TestRerankFailureMode:

    def test_bedrock_exception_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = MagicMock()
        client.invoke_model.side_effect = RuntimeError("Bedrock down")
        monkeypatch.setattr(rerank_module.boto3, "client", lambda *_, **__: client)
        svc = RerankService()
        # No exception — caller is responsible for falling back to RRF order.
        result = svc.rerank("q", ["a", "b"], top_n=2)
        assert result == []


class TestSingleton:

    def test_get_rerank_service_returns_same_instance(
        self, mock_bedrock: MagicMock,
    ) -> None:
        a = get_rerank_service()
        b = get_rerank_service()
        assert a is b
