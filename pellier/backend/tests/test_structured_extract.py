"""The structured extractor asks for one short JSON reply with thinking off, and
reports a reply cut off at ``max_tokens`` as truncated rather than as "no JSON".

No model: the Bedrock client is a stand-in that records the request body.
"""

from __future__ import annotations

import io
import json
from typing import Any, Dict, List

import pytest

import services.structured_extract as module
from services.structured_extract import StructuredExtractor, request_body

PARSED = {
    "required_categories": [], "categories": ["Kitchen and table"], "tags": ["gift"],
    "price_max_usd": 100, "in_stock_only": True, "exclusions": ["candle"],
    "unsupported_exclusions": [], "soft_signal": "housewarming gift for slow mornings",
    "lifted": [],
}


class _Client:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.bodies: List[Dict[str, Any]] = []

    def invoke_model(self, **kwargs: Any) -> Dict[str, Any]:
        self.bodies.append(json.loads(kwargs["body"]))
        return {"body": io.BytesIO(json.dumps(self.payload).encode("utf-8"))}


def _extractor(monkeypatch: pytest.MonkeyPatch, payload: Dict[str, Any]) -> StructuredExtractor:
    monkeypatch.setattr(module.boto3, "client", lambda *args, **kwargs: _Client(payload))
    return StructuredExtractor(region="us-east-1")


def test_the_request_disables_thinking_and_keeps_the_reply_short(monkeypatch) -> None:
    extractor = _extractor(monkeypatch, {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(PARSED)}],
    })
    out = extractor.extract("a housewarming gift under $100, in stock, no candles")
    body = extractor.client.bodies[0]
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 400
    assert request_body("mugs")["thinking"] == {"type": "disabled"}
    assert out["extraction_status"] == "parsed" and out["extraction_reason"] is None
    assert out["price_max_usd"] == 100.0 and out["exclusions"] == ["candle"]


def test_a_reply_cut_off_at_max_tokens_is_reported_as_truncated(monkeypatch) -> None:
    extractor = _extractor(monkeypatch, {
        "stop_reason": "max_tokens",
        "content": [
            {"type": "thinking", "thinking": "The shopper wants..."},
            {"type": "text", "text": '{"required_categ'},
        ],
    })
    out = extractor.extract("a housewarming gift under $100, in stock, no candles")
    assert out["extraction_status"] == "extraction_failed"
    assert out["extraction_reason"] == "truncated"
    assert out["price_max_usd"] is None and out["exclusions"] == []


def test_a_reply_without_json_is_unreadable_not_truncated(monkeypatch) -> None:
    extractor = _extractor(monkeypatch, {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "Sure, here is what I would look for."}],
    })
    out = extractor.extract("a gift")
    assert out["extraction_status"] == "extraction_failed"
    assert out["extraction_reason"] == "unreadable"


def test_the_prompt_carries_no_em_dash() -> None:
    assert "—" not in module._SYSTEM_PROMPT
    assert "—" not in json.dumps(request_body("a gift"))
