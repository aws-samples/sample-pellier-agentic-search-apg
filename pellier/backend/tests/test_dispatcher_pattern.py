"""Pattern III (Dispatcher) contract tests.

Asserts three things, in order of importance:

1. **The broad workarounds are gone.** The three band-aids that used to
   compensate for any short Pattern I paraphrase are structurally absent
   from the chat path:

     - No ``[ROUTING DIRECTIVE:]`` prefix injection
     - No "Preferring specialist prose" promotion branch
     - No aggressive empty-response recovery ladder
       (``last_specialist_text`` capture, ``pre_reset_buffer`` walk)

   A minimal empty-response fallback remains, plus one bounded Pattern I
   guard for a short trailing-colon preface after grounded products return.

2. **The dispatcher path is wired.** The chat request accepts a
   ``pattern`` field with value ``'dispatcher'``; ``chat_stream()``
   branches on it; all three agent factories are reachable via
   the Router.

3. **The public default is Dispatcher.** An absent / ``None`` pattern
   resolves to ``'dispatcher'`` so every Pellier surface shares one routing
   contract.

End-to-end behavior with real Bedrock calls and persona-aware responses
is covered by the live dispatcher smoke script, not here. This test is a
structural gate.
"""
from __future__ import annotations

import ast
import inspect
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Workaround absence — the three band-aids must be gone
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def chat_module_source() -> str:
    """Return the source text of services.chat, docstring-stripped.

    Comments and docstrings are stripped because we intentionally
    mention the deleted workarounds in NOTE-style comments ("NOTE: the
    three-pattern refactor deleted the ...") — those references are
    documentation of the removal, not the removal itself.
    """
    from services import chat as chat_mod

    src = inspect.getsource(chat_mod)
    tree = ast.parse(src)
    # Remove module-level docstring
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body = tree.body[1:]
    # Strip all comments by round-tripping through ast.unparse (which
    # drops comments and preserves docstrings). Then strip docstrings
    # from every function + class body.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
    return ast.unparse(tree)


def test_no_routing_directive_injection(chat_module_source: str) -> None:
    """Workaround #1: the ``[ROUTING DIRECTIVE: call the X tool]``
    prefix injection must be gone from executable code.
    """
    assert "ROUTING DIRECTIVE" not in chat_module_source, (
        "chat.py still injects a [ROUTING DIRECTIVE:] prefix into user "
        "messages — this was a workaround for the Pattern I paraphrase in "
        "Pattern I. The Dispatcher (Pattern III) doesn't need it, and "
        "Pattern I runs without it now."
    )


def test_no_broad_specialist_prose_promotion(chat_module_source: str) -> None:
    """Workaround #2's broad short-paraphrase promotion must stay gone.

    A bounded trailing-colon check is allowed for Pattern I because that
    output is syntactically incomplete; complete router replies remain
    canonical.
    """
    forbidden_phrases = [
        "Preferring specialist prose",
        "last_specialist_text",
        "flat_paraphrase",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in chat_module_source, (
            f"chat.py still references {phrase!r} — this was part of "
            f"the workaround #2 promotion branch that substituted the "
            f"specialist's prose when the Pattern I paraphrase was short. "
            f"Not needed in the three-pattern model."
        )


def test_no_aggressive_recovery_ladder(chat_module_source: str) -> None:
    """Workaround #3: the aggressive empty-response recovery ladder
    (streamed_text_buffer / pre_reset_buffer walk) must be gone from
    executable code.
    """
    forbidden_phrases = [
        "streamed_text_buffer",
        "pre_reset_buffer",
        "chat_stream recovered",
        "specialist_tool_result",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in chat_module_source, (
            f"chat.py still references {phrase!r} — this was part of "
            f"the recovery ladder. The three-pattern model replaced it "
            f"with a single minimal empty-response fallback."
        )


def test_minimal_empty_fallback_retained(chat_module_source: str) -> None:
    """Sanity check: we kept exactly one minimal empty-response
    fallback so a pathological Bedrock response doesn't strand the
    user on a blank bubble.
    """
    assert "I couldn't land on a clear answer" in chat_module_source, (
        "The minimal empty-response fallback was deleted accidentally "
        "alongside the recovery ladder. Restore the single graceful "
        "line — that's defensive hygiene, not a workaround."
    )


# ---------------------------------------------------------------------------
# Dispatcher wiring — the new code path exists
# ---------------------------------------------------------------------------


def test_dispatcher_is_the_only_routing_mode(chat_module_source: str) -> None:
    """The storefront has one Router. No request field or service argument can
    select an alternative orchestration pattern."""
    from models.search import ChatRequest
    from services.chat import EnhancedChatService

    assert "pattern" not in ChatRequest.model_fields
    assert "pattern" not in inspect.signature(EnhancedChatService.chat_stream).parameters
    for retired in ("create_orchestrator", "agents_as_tools", "graph_pattern"):
        assert retired not in chat_module_source, f"chat.py still references {retired}"


def test_dispatcher_imports_every_specialist_factory(chat_module_source: str) -> None:
    """The dispatcher builds each agent from its own factory."""
    for factory_import in (
        "build_shopping_agent",
        "build_stock_agent",
        "build_support_agent",
    ):
        assert factory_import in chat_module_source, (
            f"dispatcher missing import of {factory_import}"
        )


def test_dispatcher_log_line_present(chat_module_source: str) -> None:
    """The dispatcher branch emits a `🎯 Router` log line so runtime trace
    shows which agent each turn reached.
    """
    assert "🎯 Router" in chat_module_source, (
        "dispatcher branch must emit a distinguishing log line"
    )


def test_each_dispatcher_intent_constructs_a_distinct_specialist() -> None:
    """Production dispatch invokes one different agent factory per intent."""
    from services.chat import _build_dispatcher_specialist

    sentinels = {
        "shopping": object(),
        "stock": object(),
        "support": object(),
    }
    factories = {
        intent: MagicMock(return_value=sentinel)
        for intent, sentinel in sentinels.items()
    }
    modules = {
        "agents.shopping_agent": SimpleNamespace(
            build_shopping_agent=factories["shopping"]
        ),
        "agents.stock_agent": SimpleNamespace(
            build_stock_agent=factories["stock"]
        ),
        "agents.support_agent": SimpleNamespace(
            build_support_agent=factories["support"]
        ),
    }

    with patch.dict(sys.modules, modules):
        built = {
            intent: _build_dispatcher_specialist(intent, allow_handoff=False)
            for intent in sentinels
        }

    assert len({id(agent) for agent in built.values()}) == 3
    for intent, agent in built.items():
        assert agent is sentinels[intent]
        factories[intent].assert_called_once()
    factories["shopping"].assert_called_once_with(allow_handoff=False, skill_mode="fixed")


# ---------------------------------------------------------------------------
# In-process Aurora tool_audit wiring - the decoupled Lab 4 evidence proof
# ---------------------------------------------------------------------------
#
# The mandatory Lab 4 proof ("Aurora as agent system-of-record") reads a
# pellier.tool_audit row. That row must populate on the ORDINARY in-process
# storefront turn — no token, no Gateway, no managed Policy engine — so the
# proof is robust to the managed path failing to provision. The audit write
# lives in the streaming hook (_attach_streaming_and_hooks). These tests pin
# that wiring so a future hook refactor can't silently re-empty the ledger.
#
# chat_module_source has comments + docstrings STRIPPED, so a match here is a
# real code reference (record_allow/record_after actually invoked), not a
# mention in prose.


def test_inprocess_hook_writes_tool_audit(chat_module_source: str) -> None:
    """The streaming hooks must invoke the tool_audit writer on both the
    Before (INSERT) and After (UPDATE) tool events — this is what makes the
    Lab 4 SQL proof populate on the default storefront rail."""
    assert "tool_audit_writer" in chat_module_source, (
        "chat.py no longer references tool_audit_writer — the in-process "
        "audit write was removed; the Lab 4 tool_audit proof would return "
        "zero rows on the default (non-Gateway) turn."
    )
    assert "record_allow(" in chat_module_source, (
        "BeforeToolCall hook must call tool_audit_writer.record_allow to "
        "INSERT the placeholder audit row before the tool runs."
    )
    assert "record_after(" in chat_module_source, (
        "AfterToolCall hook must call tool_audit_writer.record_after to "
        "UPDATE the audit row with result + latency."
    )


def test_dispatcher_path_attaches_audit_hooks(chat_module_source: str) -> None:
    """The dispatcher attaches the audit-bearing hook helper to the specialist
    it builds, so Marco's check_stock turn writes tool_audit rows."""
    assert "_attach_streaming_and_hooks(orchestrator)" in chat_module_source


def test_nonstreaming_chat_runs_the_streamed_turn() -> None:
    """POST /api/chat and the in-process Runtime fallback reuse the streamed
    turn, so no in-process rail can execute a tool off-ledger."""
    import textwrap

    from services import chat as chat_mod

    src = textwrap.dedent(inspect.getsource(chat_mod.EnhancedChatService.chat))
    assert "self.chat_stream(" in src


def test_make_tool_audit_hooks_two_phase(monkeypatch) -> None:
    """The shared hook factory INSERTs on Before (with session + turn
    correlation in the args JSONB) and UPDATEs on After (with the parsed
    JSON result and an integer latency)."""
    from services import chat as chat_mod
    from services import tool_audit_writer

    calls: list = []
    monkeypatch.setattr(
        tool_audit_writer, "record_allow", lambda **kw: calls.append(("allow", kw))
    )
    monkeypatch.setattr(
        tool_audit_writer, "record_after", lambda **kw: calls.append(("after", kw))
    )

    before, after = chat_mod.make_tool_audit_hooks(
        session_id="sess-1",
        turn_id="turn-abc",
        principal_sub="sub-marco",
        customer_id="CUST-MARCO",
    )
    event = SimpleNamespace(
        tool_use={
            "name": "check_stock",
            "toolUseId": "tu-1",
            "input": {"product_query": "hadley"},
        },
        result={"content": [{"text": '{"quantity": 4}'}]},
    )
    before(event)
    after(event)

    assert [phase for phase, _ in calls] == ["allow", "after"]
    allow_kw = calls[0][1]
    assert allow_kw["tool_use_id"] == "tu-1"
    assert allow_kw["tool_name"] == "check_stock"
    assert allow_kw["caller"] == "agent"
    assert allow_kw["session_id"] == "sess-1"
    assert allow_kw["args"]["product_query"] == "hadley"
    assert allow_kw["args"]["turn_id"] == "turn-abc"
    assert allow_kw["args"]["customer_id"] == "CUST-MARCO"
    assert allow_kw["args"]["principal_sub"] == "sub-marco"
    after_kw = calls[1][1]
    assert after_kw["tool_use_id"] == "tu-1"
    assert after_kw["result"] == {"quantity": 4}
    assert isinstance(after_kw["latency_ms"], int)


def test_make_tool_audit_hooks_uses_the_bound_turn_identity(monkeypatch) -> None:
    """The non-streaming path supplies only its session, so defaults are scoped."""
    from services import chat as chat_mod
    from services import tool_audit_writer
    from services.turn_identity import (
        authorized_customer_id_var,
        principal_sub_var,
        turn_id_var,
    )

    calls: list = []
    monkeypatch.setattr(
        tool_audit_writer, "record_allow", lambda **kw: calls.append(kw)
    )
    customer_token = authorized_customer_id_var.set("CUST-THEO")
    principal_token = principal_sub_var.set("sub-theo")
    turn_token = turn_id_var.set("turn-theo")
    try:
        before, _ = chat_mod.make_tool_audit_hooks(session_id="sess-theo")
        before(
            SimpleNamespace(
                tool_use={
                    "name": "get_orders",
                    "toolUseId": "tu-theo",
                    "input": {"customer_id": "CUST-MARCO"},
                }
            )
        )
    finally:
        turn_id_var.reset(turn_token)
        principal_sub_var.reset(principal_token)
        authorized_customer_id_var.reset(customer_token)

    assert calls[0]["args"] == {
        "customer_id": "CUST-THEO",
        "principal_sub": "sub-theo",
        "turn_id": "turn-theo",
    }
