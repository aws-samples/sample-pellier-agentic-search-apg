"""Tests for the shared execution-rail dispatcher.

The governed-workshop audit's B1 finding: ``USE_AGENTCORE_RUNTIME`` only
affected ``/api/agent/chat``, while Pellier posts to
``/api/chat/stream``. The storefront could therefore serve every shopper
turn in-process while the operator believed the managed Runtime, Gateway,
and Policy chain was carrying them.

The fix is one resolver both endpoints call, plus a rail label on every
completed turn. These tests pin three properties:

  1. Rail selection is identical regardless of which endpoint asks.
  2. A requested-but-unusable managed rail is reported as unavailable with
     a reason — it never silently resolves to in-process.
  3. A degraded turn names the capabilities that were withheld, and is
     never described as a Cedar DENY.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from config import settings
from services.execution_rail import (
    RAIL_IN_PROCESS,
    RAIL_RUNTIME,
    REASON_NO_TOKEN,
    REASON_NOT_CONFIGURED,
    degraded_notice,
    resolve_rail,
)

_ENDPOINT = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier"


def _managed(monkeypatch: pytest.MonkeyPatch, *, endpoint: str | None = _ENDPOINT) -> None:
    monkeypatch.setattr(settings, "USE_AGENTCORE_RUNTIME", True, raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_RUNTIME_ENDPOINT", endpoint, raising=False)


# ---------------------------------------------------------------------------
# Rail selection
# ---------------------------------------------------------------------------
def test_flag_off_resolves_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "USE_AGENTCORE_RUNTIME", False, raising=False)

    decision = resolve_rail(auth_token="jwt-123")

    assert decision.rail == RAIL_IN_PROCESS
    assert decision.managed_requested is False
    assert decision.available is True
    assert decision.reason is None


def test_flag_on_with_token_and_endpoint_resolves_managed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)

    decision = resolve_rail(auth_token="jwt-123")

    assert decision.rail == RAIL_RUNTIME
    assert decision.is_managed is True
    assert decision.available is True


def test_missing_token_is_unavailable_not_a_silent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The managed authorizer rejects anonymous callers, so say so."""
    _managed(monkeypatch)

    decision = resolve_rail(auth_token=None)

    assert decision.managed_requested is True
    assert decision.available is False
    assert decision.reason == REASON_NO_TOKEN
    assert decision.is_managed is False


def test_missing_endpoint_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch, endpoint=None)

    decision = resolve_rail(auth_token="jwt-123")

    assert decision.available is False
    assert decision.reason == REASON_NOT_CONFIGURED


def test_empty_token_string_counts_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)

    assert resolve_rail(auth_token="").available is False


def test_both_endpoints_resolve_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One resolver, so the storefront and managed route cannot disagree.

    This is the whole point of B1: two call sites, one decision function,
    identical results for identical inputs.
    """
    _managed(monkeypatch)

    storefront = resolve_rail(auth_token="jwt-123")
    managed_route = resolve_rail(auth_token="jwt-123")

    assert storefront == managed_route
    assert storefront.to_dict() == managed_route.to_dict()


# ---------------------------------------------------------------------------
# Serialization onto the turn
# ---------------------------------------------------------------------------
def test_decision_serializes_for_the_completion_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)

    payload = resolve_rail(auth_token="jwt-123").to_dict()

    assert payload == {
        "rail": RAIL_RUNTIME,
        "managedRequested": True,
        "available": True,
        "reason": None,
    }


# ---------------------------------------------------------------------------
# Mutation tools must not run off the managed rail in governed format
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Degradation disclosure
# ---------------------------------------------------------------------------
def test_degraded_notice_names_the_withheld_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)
    decision = resolve_rail(auth_token=None)

    notice = degraded_notice(decision)

    assert notice["degraded"] is True
    assert notice["reason"] == REASON_NO_TOKEN
    assert notice["capabilitiesRemoved"] == ["give_store_credit"]


def test_degraded_notice_is_not_described_as_a_policy_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing rail is an availability problem, not an authorization one.

    Calling it a DENY would break the workshop's core distinction between
    "Cedar refused this" and "the rail was not there".
    """
    _managed(monkeypatch)
    decision = resolve_rail(auth_token=None)

    explanation = degraded_notice(decision)["explanation"]

    assert "not a Cedar DENY" in explanation


# ---------------------------------------------------------------------------
# Storefront annotation
# ---------------------------------------------------------------------------
def test_storefront_complete_event_carries_the_rail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as app_module

    _managed(monkeypatch)
    decision = resolve_rail(auth_token="jwt-123")
    event = {"type": "complete", "response": {"response": "hi", "success": True}}

    annotated = app_module._annotate_rail(event, decision, degraded_notice)

    assert annotated["response"]["rail"] == RAIL_RUNTIME
    assert annotated["response"]["railDecision"]["rail"] == RAIL_RUNTIME
    assert annotated["response"]["railDecision"]["available"] is True
    assert "degradation" not in annotated["response"]


def test_storefront_degraded_turn_is_labelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as app_module

    _managed(monkeypatch)
    decision = resolve_rail(auth_token=None)
    event = {"type": "complete", "response": {"response": "hi", "success": True}}

    annotated = app_module._annotate_rail(event, decision, degraded_notice)

    assert annotated["response"]["rail"] == RAIL_IN_PROCESS
    assert annotated["response"]["degradation"]["degraded"] is True
    assert annotated["response"]["degradation"]["reason"] == REASON_NO_TOKEN


def test_annotation_leaves_a_malformed_event_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as app_module

    monkeypatch.setattr(settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    decision = resolve_rail()
    event = {"type": "complete", "response": "not a dict"}

    assert app_module._annotate_rail(event, decision, degraded_notice) == event


# ---------------------------------------------------------------------------
# Gateway capability tiers (audit finding B3)
# ---------------------------------------------------------------------------
def test_every_published_tool_has_a_tier() -> None:
    """A flat catalog makes least-privilege unverifiable; classify all nine."""
    from services.agentcore_gateway import GATEWAY_TOOL_TIERS

    assert len(GATEWAY_TOOL_TIERS) == 9
    assert set(GATEWAY_TOOL_TIERS) == {
        "search_products", "browse_department", "compare_products", "check_stock",
        "get_orders", "get_return_policy", "get_tickets", "give_store_credit",
        "ask_a_person",
    }


def test_an_unknown_tool_defaults_to_the_most_restrictive_tier() -> None:
    """An unclassified tool is more likely a forgotten mutation than a read."""
    from services.agentcore_gateway import TIER_OPERATOR_MUTATION, tool_tier

    assert tool_tier("some_new_tool") == TIER_OPERATOR_MUTATION


def test_mutation_tiers_capture_exactly_the_write_tools() -> None:
    from services.agentcore_gateway import mutation_tool_names

    assert sorted(mutation_tool_names()) == ["give_store_credit"]


def test_search_tools_are_in_the_read_tier() -> None:
    from services.agentcore_gateway import TIER_READ, tools_in_tier

    read_tools = tools_in_tier(TIER_READ)

    assert "search_products" in read_tools
    assert "check_stock" in read_tools
    assert "give_store_credit" not in read_tools


def test_fail_closed_rule_derives_from_the_tier_map() -> None:
    """The rail guard and the tier map must be one source of truth.

    If these two lists could drift, a tool promoted to a mutation tier
    would keep being servable in-process — exactly the gap B3 describes.
    """
    from services.agentcore_gateway import mutation_tool_names
    from services.execution_rail import mutation_tools

    assert mutation_tools() == frozenset(mutation_tool_names())


def test_fallback_list_matches_the_tier_map() -> None:
    """The optional-import fallback must not encode a stale set."""
    from services.agentcore_gateway import mutation_tool_names
    from services.execution_rail import _MUTATION_TOOLS_FALLBACK

    assert _MUTATION_TOOLS_FALLBACK == frozenset(mutation_tool_names())


def test_startup_warns_loudly_when_the_boundary_is_off() -> None:
    """A silent fail-open is the thing that cost a live business mutation.

    `WORKSHOP_FORMAT` now decides only the Operator's write rail
    (`governed_execution.select_rail`); the warning says that, and nothing
    about a shopper-rail credit, because no agent binds one.
    """
    import pathlib

    app_source = pathlib.Path("app.py").read_text()
    block = app_source.split("WORKSHOP_FORMAT=governed —")[1][:1200]
    assert "The managed-rail boundary is OFF" in block
    assert "the Operator executes a confirmed credit in process" in block
    assert "logger.warning(" in block
    assert "requires_managed_rail" not in app_source
    # And the positive case is stated too, so a correct box confirms itself.
    assert "governed writes are managed-rail only" in app_source


def test_give_store_credit_is_the_only_mutation_tool() -> None:
    from services.execution_rail import _MUTATION_TOOLS_FALLBACK, mutation_tools

    assert mutation_tools() == frozenset({"give_store_credit"})
    assert _MUTATION_TOOLS_FALLBACK == frozenset({"give_store_credit"})
