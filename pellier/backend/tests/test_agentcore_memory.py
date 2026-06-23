"""Tests for ``services.agentcore_memory.AgentCoreMemory`` (Challenge 6).

Validates Requirements 2.5.2, 4.3.2, 4.3.3, 4.4.1, and 6.2.1 from
``.kiro/specs/pellier-storefront/requirements.md``:

  2.5.2 ``agentcore_memory`` implements session history + persistent
        user preferences via the ``AgentCoreMemory`` class.
  4.3.2 Agent calls SHALL be scoped so no cross-user bleed is
        possible (``user-{user_id}-...`` keyspace).
  4.3.3 Anonymous ``anon-{session_id}`` namespace SHALL NOT be
        merged into the user namespace on sign-in.
  4.4.1 Preferences persist via ``agentcore_memory`` at
        ``user:{user_id}:preferences`` — never in localStorage, never
        in the product DB.
  6.2.1 Session history and user preferences use
        ``pellier/backend/services/agentcore_memory.py``.

Tests run without ``AGENTCORE_MEMORY_ID`` so the in-memory fallback
path exercises — identical surface to the SDK path. Async methods are
dispatched via ``asyncio.run`` per the repo convention in
``test_runtime_switch.py`` and ``test_vector_search.py`` (no async
plugin is installed in the backend venv).

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_agentcore_memory.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from models import Preferences
from services.agentcore_memory import AgentCoreMemory


def _run(coro: Any) -> Any:
    """Run an async coroutine from a sync test without needing a plugin."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level fallback dicts between tests and force the
    SDK-unavailable path so every test runs deterministically against
    the in-memory fallback.
    """
    import services.agentcore_memory as mem

    monkeypatch.setattr(mem, "_SESSION_STORE", {})
    monkeypatch.setattr(mem, "_PREFS_STORE", {})
    # Force the fallback path regardless of whether AGENTCORE_MEMORY_ID
    # is set in the dev env that runs the suite.
    monkeypatch.setattr(mem.settings, "AGENTCORE_MEMORY_ID", None)


@pytest.fixture
def memory():
    from services.agentcore_memory import AgentCoreMemory

    return AgentCoreMemory()


# ---------------------------------------------------------------------------
# Preference round-trip (Req 4.4.1)
# ---------------------------------------------------------------------------


def test_set_then_get_user_preferences_round_trip(memory) -> None:
    """Writing preferences and reading them back SHALL return the
    identical payload (Req 4.4.1)."""
    prefs = Preferences(
        vibe=["minimal", "serene"],
        colors=["warm", "neutral"],
        occasions=["everyday", "slow"],
        categories=["linen"],
    )

    saved = _run(memory.set_user_preferences("user-abc", prefs))
    assert isinstance(saved, Preferences)
    assert saved == prefs

    loaded = _run(memory.get_user_preferences("user-abc"))
    assert loaded == prefs


def test_get_user_preferences_returns_none_when_unset(memory) -> None:
    """A user with no saved prefs SHALL return ``None``, not an empty
    ``Preferences`` — the frontend distinguishes null from empty to
    decide whether to auto-open the onboarding modal."""
    assert _run(memory.get_user_preferences("user-unseen")) is None


def test_set_user_preferences_accepts_plain_dict(memory) -> None:
    """Route handlers can pass a validated payload; the class SHALL
    coerce it into a ``Preferences`` before persisting."""
    payload = {
        "vibe": ["bold"],
        "colors": ["moody"],
        "occasions": ["evening"],
        "categories": ["dresses"],
    }

    saved = _run(memory.set_user_preferences("user-xyz", payload))
    assert isinstance(saved, Preferences)
    assert saved.vibe == ["bold"]

    loaded = _run(memory.get_user_preferences("user-xyz"))
    assert loaded is not None
    assert loaded.model_dump() == saved.model_dump()


def test_preferences_scoped_per_user_id(memory) -> None:
    """Req 4.3.2: two users SHALL NOT see each other's preferences."""
    alice_prefs = Preferences(vibe=["minimal"])
    bob_prefs = Preferences(vibe=["bold"])

    _run(memory.set_user_preferences("alice", alice_prefs))
    _run(memory.set_user_preferences("bob", bob_prefs))

    assert _run(memory.get_user_preferences("alice")) == alice_prefs
    assert _run(memory.get_user_preferences("bob")) == bob_prefs


# ---------------------------------------------------------------------------
# Session history append + read (Req 2.5.2, 4.3.2)
# ---------------------------------------------------------------------------


def test_session_history_append_and_read_preserves_order(memory) -> None:
    """Turns appended in order SHALL read back in the same order."""
    ns = "user-alice-session-s1"
    turns = [
        {"role": "user", "content": "show me linen"},
        {"role": "assistant", "content": "here are four linen pieces"},
        {"role": "user", "content": "only under $100"},
    ]

    for turn in turns:
        _run(memory.append_session_turn(ns, turn))

    history = _run(memory.get_session_history(ns))
    assert history == turns


def test_session_history_returns_empty_list_for_unknown_ns(memory) -> None:
    """A namespace with no writes SHALL return ``[]`` (not ``None``)."""
    assert _run(memory.get_session_history("user-ghost-session-nope")) == []


# ---------------------------------------------------------------------------
# SDK turn normalization (the /api/agent/session/{id} 500 regression)
# ---------------------------------------------------------------------------
#
# The in-memory fallback above already returns plain ``{role, content}``
# dicts, so the route serialized fine in dev. On a provisioned account the
# SDK path runs instead, and ``get_last_k_turns`` returns grouped turns of
# uppercase-role messages with nested ``content.text`` and ``datetime``
# fields — NOT JSON serializable, so ``JSONResponse`` 500'd at render time.
# These tests pin the normalizer that closes that gap.


def test_normalize_sdk_turns_flattens_grouped_messages() -> None:
    """SDK groups messages into turns (list-of-lists); the normalizer
    SHALL flatten them into the route's ``{role, content, timestamp}``
    shape with lowercased roles and unwrapped ``content.text``.
    """
    import datetime as _dt

    raw = [
        [{"role": "USER", "content": {"text": "a milestone gift"}}],
        [{"role": "ASSISTANT", "content": {"text": "Here are three pieces"},
          "timestamp": _dt.datetime(2026, 6, 23, 12, 0, 0)}],
    ]

    out = AgentCoreMemory._normalize_sdk_turns(raw)

    assert out == [
        {"role": "user", "content": "a milestone gift", "timestamp": ""},
        {"role": "assistant", "content": "Here are three pieces",
         "timestamp": "2026-06-23 12:00:00"},
    ]


def test_normalize_sdk_turns_output_is_json_serializable() -> None:
    """Whatever the SDK hands back, the normalized result SHALL survive
    ``json.dumps`` — this is the exact property whose absence produced
    the 500 (a datetime in the payload).
    """
    import datetime as _dt
    import json

    raw = [
        [{"role": "USER", "content": {"text": "hi"},
          "createdAt": _dt.datetime(2026, 6, 23, 9, 30, 0)}],
    ]

    out = AgentCoreMemory._normalize_sdk_turns(raw)
    # Would raise TypeError on a datetime / SDK object; must not.
    json.dumps(out)


def test_normalize_sdk_turns_tolerates_string_content_and_bare_turn() -> None:
    """A bare message dict (not wrapped in a turn list) and a string
    ``content`` SHALL both normalize cleanly rather than crash."""
    raw = [
        {"role": "user", "content": "bare string content"},
        [{"role": "system", "content": {"text": "context"}}],
    ]

    out = AgentCoreMemory._normalize_sdk_turns(raw)

    assert out == [
        {"role": "user", "content": "bare string content", "timestamp": ""},
        # non user/assistant roles collapse to assistant
        {"role": "assistant", "content": "context", "timestamp": ""},
    ]


def test_normalize_sdk_turns_handles_none_and_empty() -> None:
    """``None`` (SDK returned nothing) and ``[]`` SHALL both yield ``[]``."""
    assert AgentCoreMemory._normalize_sdk_turns(None) == []
    assert AgentCoreMemory._normalize_sdk_turns([]) == []


def test_append_session_turn_copies_input(memory) -> None:
    """Mutating the caller's turn dict after appending SHALL NOT
    mutate the stored history — callers often reuse dicts."""
    ns = "user-alice-session-s1"
    turn = {"role": "user", "content": "hello"}
    _run(memory.append_session_turn(ns, turn))

    turn["content"] = "tampered"
    history = _run(memory.get_session_history(ns))
    assert history == [{"role": "user", "content": "hello"}]


# ---------------------------------------------------------------------------
# Namespace isolation (Req 4.3.3)
# ---------------------------------------------------------------------------


def test_anon_namespace_not_accessible_via_user_key(memory) -> None:
    """Req 4.3.3: turns written to ``anon-{sid}`` SHALL NOT be readable
    via ``user-{uid}-session-{sid}``.
    """
    from services.agentcore_identity import AgentCoreIdentityService

    session_id = "s-shared"
    anon_ns = AgentCoreIdentityService.build_namespace(None, session_id)
    user_ns = AgentCoreIdentityService.build_namespace("alice", session_id)
    assert anon_ns == f"anon-{session_id}"
    assert user_ns == f"user-alice-session-{session_id}"

    _run(memory.append_session_turn(anon_ns, {"role": "user", "content": "anon turn"}))

    # The user's namespace SHALL be empty — no silent merge on sign-in.
    assert _run(memory.get_session_history(user_ns)) == []
    # The anon namespace still carries its own data.
    assert _run(memory.get_session_history(anon_ns)) == [
        {"role": "user", "content": "anon turn"}
    ]


def test_user_namespace_not_accessible_via_anon_key(memory) -> None:
    """The reverse direction: authenticated turns SHALL NOT leak to a
    request that lands on the anon namespace with the same session id.
    """
    from services.agentcore_identity import AgentCoreIdentityService

    session_id = "s-shared"
    anon_ns = AgentCoreIdentityService.build_namespace(None, session_id)
    user_ns = AgentCoreIdentityService.build_namespace("alice", session_id)

    _run(memory.append_session_turn(user_ns, {"role": "user", "content": "signed-in turn"}))

    assert _run(memory.get_session_history(anon_ns)) == []
    assert _run(memory.get_session_history(user_ns)) == [
        {"role": "user", "content": "signed-in turn"}
    ]


def test_session_history_scoped_per_user(memory) -> None:
    """Two users sharing nothing but a session-id SHALL see disjoint
    histories (Req 4.3.2).
    """
    from services.agentcore_identity import AgentCoreIdentityService

    shared_sid = "s1"
    alice_ns = AgentCoreIdentityService.build_namespace("alice", shared_sid)
    bob_ns = AgentCoreIdentityService.build_namespace("bob", shared_sid)

    _run(memory.append_session_turn(alice_ns, {"role": "user", "content": "alice hi"}))
    _run(memory.append_session_turn(bob_ns, {"role": "user", "content": "bob hi"}))

    assert _run(memory.get_session_history(alice_ns)) == [
        {"role": "user", "content": "alice hi"}
    ]
    assert _run(memory.get_session_history(bob_ns)) == [
        {"role": "user", "content": "bob hi"}
    ]


# ---------------------------------------------------------------------------
# SDK signature pinning (Batch 3 — list_long_term_memory_records drift)
# ---------------------------------------------------------------------------


def test_get_user_preferences_sdk_path_uses_correct_signature() -> None:
    """Pin the REAL installed-SDK contract for
    ``MemorySessionManager.list_long_term_memory_records``:
      * kwarg is ``namespace_prefix`` (NOT ``namespace``) + ``max_results``;
      * returns a ``List[MemoryRecord]`` whose ``content`` is ``{"text": "<json>"}``.

    This test previously asserted the OPPOSITE (``namespace=``, and that
    ``namespace_prefix`` was "deprecated") — which was wrong and let the real
    bug (a ``TypeError`` that silently fell back to the in-process dict) pass CI.
    Verified against bedrock-agentcore 1.6.3 (session.py:929) and dat403's
    working 1.8.0 usage. A future SDK bump that changes the signature should
    trip THIS test, not warn silently in prod.
    """
    import json
    from services.agentcore_memory import AgentCoreMemory

    captured: dict = {}

    class _FakeRecord:
        """Mirrors MemoryRecord: .get('content') -> {'text': '<json string>'}."""
        def __init__(self, prefs: dict) -> None:
            self._content = {"text": json.dumps(prefs)}

        def get(self, key: str, default=None):
            return {"content": self._content}.get(key, default)

    class _FakeManager:
        def list_long_term_memory_records(self, **kwargs):
            captured.update(kwargs)
            # Reject the wrong kwargs so a regression to them is loud.
            assert "namespace" not in kwargs, "wrong SDK kwarg 'namespace' (use namespace_prefix)"
            assert "memoryId" not in kwargs, "wrong SDK kwarg 'memoryId'"
            assert "maxResults" not in kwargs, "wrong SDK kwarg 'maxResults' (use max_results)"
            return [_FakeRecord({"vibe": ["minimal"], "colors": ["warm"]})]

    mem = AgentCoreMemory(memory_id="mem-test")
    mem._sdk_manager = _FakeManager()

    loaded = _run(mem.get_user_preferences("alice"))

    assert loaded is not None
    assert loaded.vibe == ["minimal"]
    assert captured["namespace_prefix"] == "user:alice:preferences"
    assert captured["max_results"] == 1


# ---------------------------------------------------------------------------
# Semantic memory (USER_PREFERENCE extraction) — get_semantic_memories
# ---------------------------------------------------------------------------
#
# These pin the LIVE semantic substrate the Atelier panel flips to. The
# USER_PREFERENCE strategy writes long-term records whose ``content.text`` is
# a JSON string ``{"context","preference","categories"[]}`` — LEARNED prose,
# distinct from the typed onboarding ``Preferences`` blob that
# ``get_user_preferences`` serves. get_semantic_memories returns the bare
# ``preference`` strings, reads via ``namespace_prefix`` against
# ``/pellier/preferences/{actor_id}/``, and degrades to ``[]`` (never raises,
# never fabricates) so the route can fall back to the honest fixture.


class _SemRecord:
    """Mirrors MemoryRecord: .get('content') -> {'text': '<json string>'}."""

    def __init__(self, text: str) -> None:
        self._content = {"text": text}

    def get(self, key: str, default=None):
        return {"content": self._content}.get(key, default)


def test_get_semantic_memories_returns_empty_without_sdk(memory) -> None:
    """With no ``AGENTCORE_MEMORY_ID`` (autouse fixture nulls it), the
    method SHALL return ``[]`` so the route falls back to the fixture —
    never a fabricated ``live`` panel."""
    assert _run(memory.get_semantic_memories("CUST-MARCO")) == []


def test_get_semantic_memories_extracts_preference_strings_and_namespace() -> None:
    """SDK path: each record's ``content.text`` JSON SHALL be parsed and
    its ``preference`` field collected; the read SHALL use
    ``namespace_prefix='/pellier/preferences/{actor}/'`` + ``max_results``."""
    import json

    captured: dict = {}

    class _FakeManager:
        def list_long_term_memory_records(self, **kwargs):
            captured.update(kwargs)
            assert "namespace" not in kwargs, "use namespace_prefix, not namespace"
            assert "maxResults" not in kwargs, "use max_results, not maxResults"
            return [
                _SemRecord(json.dumps({
                    "context": "Goa trip planning",
                    "preference": "Prefers lightweight linen in warm neutrals",
                    "categories": ["linen", "travel"],
                })),
                _SemRecord(json.dumps({
                    "context": "fabric talk",
                    "preference": "Favors natural fibers over synthetics",
                    "categories": ["fabric"],
                })),
            ]

    mem = AgentCoreMemory(memory_id="mem-test")
    mem._sdk_manager = _FakeManager()

    prefs = _run(mem.get_semantic_memories("CUST-MARCO"))

    assert prefs == [
        "Prefers lightweight linen in warm neutrals",
        "Favors natural fibers over synthetics",
    ]
    assert captured["namespace_prefix"] == "/pellier/preferences/CUST-MARCO/"
    assert captured["max_results"] == 20


def test_get_semantic_memories_skips_malformed_and_empty_records() -> None:
    """Malformed JSON, missing ``preference``, and blank text SHALL be
    skipped silently — a single bad record never breaks the panel."""
    import json

    class _FakeManager:
        def list_long_term_memory_records(self, **kwargs):
            return [
                _SemRecord("not valid json {{{"),
                _SemRecord(json.dumps({"context": "x", "categories": []})),  # no preference
                _SemRecord(json.dumps({"preference": ""})),  # empty preference
                _SemRecord(json.dumps({"preference": "Keeps it minimal"})),  # the one good one
            ]

    mem = AgentCoreMemory(memory_id="mem-test")
    mem._sdk_manager = _FakeManager()

    assert _run(mem.get_semantic_memories("CUST-THEO")) == ["Keeps it minimal"]


def test_get_semantic_memories_returns_empty_on_sdk_error() -> None:
    """An SDK exception SHALL be swallowed into ``[]`` (honest fallback),
    never propagated — the route must not 500 because extraction is flaky."""

    class _BoomManager:
        def list_long_term_memory_records(self, **kwargs):
            raise RuntimeError("data plane unavailable")

    mem = AgentCoreMemory(memory_id="mem-test")
    mem._sdk_manager = _BoomManager()

    assert _run(mem.get_semantic_memories("CUST-ANNA")) == []
