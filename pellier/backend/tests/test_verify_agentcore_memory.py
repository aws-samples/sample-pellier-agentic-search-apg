"""Tests for the fresh-process AgentCore Memory verifier."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "verify_agentcore_memory.py"
)
SPEC = importlib.util.spec_from_file_location("verify_agentcore_memory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _Memory:
    def __init__(self, turns):
        self.turns = turns

    async def get_session_history(self, namespace, *, customer_id=None):
        assert namespace == "user-marco-session-proof"
        assert customer_id in (None, "CUST-MARCO")
        return self.turns


def test_verify_reports_independent_managed_read() -> None:
    result = asyncio.run(
        MODULE.verify(
            "user-marco-session-proof",
            ["Goa", "linen"],
            timeout=1,
            customer_id="CUST-MARCO",
            memory_factory=lambda: _Memory(
                [{"role": "user", "content": "Remember Goa and linen."}]
            ),
        )
    )

    assert result["source"] == "agentcore-memory"
    assert result["process"] == "fresh"
    assert result["turn_count"] == 1
    assert result["matched"] == ["Goa", "linen"]


def test_verify_fails_when_expected_content_is_absent() -> None:
    with pytest.raises(RuntimeError, match="did not contain"):
        asyncio.run(
            MODULE.verify(
                "user-marco-session-proof",
                ["Goa"],
                timeout=0,
                memory_factory=lambda: _Memory([]),
            )
        )
