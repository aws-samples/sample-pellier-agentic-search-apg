"""Pattern III (Dispatcher) contract test — Phase 2 verification.

Asserts three things, in order of importance:

1. **The workarounds are gone.** The three band-aids that used to
   compensate for Haiku's paraphrase in Pattern I are structurally
   absent from the chat path:

     - No ``[ROUTING DIRECTIVE:]`` prefix injection
     - No "Preferring specialist prose" promotion branch
     - No aggressive empty-response recovery ladder
       (``last_specialist_text`` capture, ``pre_reset_buffer`` walk)

   A single minimal empty-response fallback is retained (in case
   Bedrock itself returns nothing) — that's not a workaround, it's
   defensive hygiene.

2. **The dispatcher path is wired.** The chat request accepts a
   ``pattern`` field with value ``'dispatcher'``; ``chat_stream()``
   branches on it; all five specialist factories are reachable via
   the intent classifier.

3. **Atelier behavior is unchanged at the wire level.** The default
   pattern (absent / None) is ``'agents_as_tools'`` so existing
   Atelier clients keep hitting the Haiku orchestrator.

End-to-end behavior (real Bedrock calls, persona-aware responses)
is verified manually via the four storefront scenarios in Phase 2's
verification output — not here. This test is a structural gate.
"""
from __future__ import annotations

import ast
import inspect

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
        "messages — this was a workaround for Haiku's paraphrase in "
        "Pattern I. The Dispatcher (Pattern III) doesn't need it, and "
        "Pattern I runs without it now."
    )


def test_no_specialist_prose_promotion(chat_module_source: str) -> None:
    """Workaround #2: the specialist-over-orchestrator promotion
    branch must be gone from executable code.
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
            f"specialist's prose when Haiku's paraphrase was short. "
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


def test_chat_request_accepts_pattern_field() -> None:
    """The Pydantic ChatRequest model must accept a ``pattern`` field
    with the three valid values (and default to None)."""
    from models.search import ChatRequest

    # Default (None) — backwards compatible
    default = ChatRequest(message="hello")
    assert default.pattern is None

    # All three valid values
    for val in ("dispatcher", "agents_as_tools", "graph"):
        req = ChatRequest(message="hello", pattern=val)
        assert req.pattern == val


def test_chat_stream_signature_accepts_pattern() -> None:
    """chat_service.chat_stream must accept a ``pattern`` kwarg so the
    /api/chat/stream endpoint can thread the request field through.
    """
    from services.chat import EnhancedChatService

    sig = inspect.signature(EnhancedChatService.chat_stream)
    assert "pattern" in sig.parameters, (
        "chat_stream does not accept 'pattern' — Phase 2 wiring missed it"
    )


def test_chat_stream_branches_on_dispatcher_pattern(chat_module_source: str) -> None:
    """chat_stream must have a `pattern == "dispatcher"` branch that
    imports specialist factories and dispatches to the classifier's
    selection.
    """
    # ast.unparse normalizes string literals to single-quote form.
    assert "pattern == 'dispatcher'" in chat_module_source, (
        "chat_stream is missing the `if pattern == 'dispatcher':` branch"
    )
    # The branch imports the five specialist factories
    for factory_import in (
        "build_search_agent",
        "build_recommendation_agent",
        "build_pricing_agent",
        "build_inventory_agent",
        "build_support_agent",
    ):
        assert factory_import in chat_module_source, (
            f"dispatcher branch missing import of {factory_import}"
        )


def test_dispatcher_log_line_present(chat_module_source: str) -> None:
    """The dispatcher branch emits a `🎯 Dispatcher` log line so
    runtime trace differentiates dispatcher turns from orchestrator turns.
    """
    assert "🎯 Dispatcher" in chat_module_source, (
        "dispatcher branch must emit a distinguishing log line"
    )


# ---------------------------------------------------------------------------
# Pattern I byte-compatibility — Atelier is unchanged at the wire level
# ---------------------------------------------------------------------------


def test_default_pattern_is_agents_as_tools() -> None:
    """When no pattern is supplied (pre-Phase-2 clients), the service
    must default to agents_as_tools so Atelier behavior is preserved.
    """
    import textwrap

    from services import chat as chat_mod

    src = inspect.getsource(chat_mod.EnhancedChatService.chat_stream)
    # ast.unparse is NOT applied here — this reads the literal source —
    # so the double-quoted form in the module is what we check.
    assert 'pattern or "agents_as_tools"' in textwrap.dedent(src), (
        "chat_stream does not default pattern to 'agents_as_tools' — "
        "pre-Phase-2 clients (Atelier) would break"
    )


def test_orchestrator_constructed_only_for_agents_as_tools() -> None:
    """The legacy ``orchestrator = create_orchestrator()`` construction
    inside ``chat_stream()`` must sit inside the ``agents_as_tools``
    branch, not run unconditionally. Otherwise dispatcher turns pay for
    a Haiku instance they never use.

    Scoped to ``chat_stream()`` specifically — the non-streaming
    ``_strands_enhanced_chat()`` legacy path has its own separate
    orchestrator construction that doesn't need the pattern branch
    (it's only reachable via the older non-streaming /api/chat endpoint).
    """
    import textwrap

    from services import chat as chat_mod

    # inspect.getsource returns the method source with its class-level
    # indentation intact; dedent before parsing.
    src = textwrap.dedent(inspect.getsource(chat_mod.EnhancedChatService.chat_stream))
    tree = ast.parse(src)
    # Strip the method docstring for clean checking.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
    body = ast.unparse(tree)

    assert "pattern == 'agents_as_tools'" in body
    normalize_idx = body.find("pattern or 'agents_as_tools'")
    create_idx = body.find("orchestrator = create_orchestrator()")
    assert normalize_idx > 0, "pattern normalization missing from chat_stream"
    assert create_idx > 0, "create_orchestrator() not found in chat_stream"
    assert normalize_idx < create_idx, (
        "create_orchestrator() is called before pattern normalization — "
        "dispatcher turns would construct an unused orchestrator"
    )
