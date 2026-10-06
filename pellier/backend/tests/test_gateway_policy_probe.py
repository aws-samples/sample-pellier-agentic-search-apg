"""``scripts/deploy/gateway_policy_probe.classify_call``: only Cedar's denial reads ``deny``.

The Lab 3 and Lab 4 checks prove a DENY with this classifier, so a tool error
must never pose as a policy decision, and a Cedar denial must read ``deny``
whether the Gateway raises it or returns it as an ``isError`` result.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
probe = importlib.import_module("gateway_policy_probe")

DENIAL = ("Tool call not allowed due to policy enforcement [Policy evaluation denied due to "
          "get_tickets_owner_only-abc]")


def _result(text: str, *, is_error: bool) -> SimpleNamespace:
    return SimpleNamespace(isError=is_error, content=[{"type": "text", "text": text}])


def test_a_raised_denial_is_deny() -> None:
    outcome = probe.classify_call(None, RuntimeError(DENIAL))
    assert (outcome["outcome"], outcome["tool_executed"]) == ("deny", False)


def test_a_denial_returned_as_an_error_result_is_deny() -> None:
    outcome = probe.classify_call(_result(DENIAL, is_error=True), None)
    assert (outcome["outcome"], outcome["cedar_denial"], outcome["tool_executed"]) == (
        "deny", True, False)


def test_a_tool_error_result_is_an_error_with_the_tool_entered() -> None:
    outcome = probe.classify_call(_result('{"status": "error"}', is_error=True), None)
    assert (outcome["outcome"], outcome["tool_executed"]) == ("error", True)


def test_a_401_is_an_error_not_a_denial() -> None:
    outcome = probe.classify_call(None, RuntimeError("401 Unauthorized"))
    assert (outcome["outcome"], outcome["cedar_denial"]) == ("error", False)
