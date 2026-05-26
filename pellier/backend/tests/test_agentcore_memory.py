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
    """The bedrock-agentcore SDK's ``MemorySessionManager.list_long_term_memory_records``
    takes ``namespace`` (exact-match keyword) + ``max_results`` (keyword)
    and returns a ``List[MemoryRecord]``. The historic ``namespace_prefix``
    kwarg is now deprecated in favor of ``namespace`` (exact-match) /
    ``namespace_path`` (hierarchical prefix); ``memoryId`` and ``maxResults``
    were never the right names. Pin the call shape so a future SDK bump
    that changes the signature trips this test instead of warning silently
    in prod.
    """
    from services.agentcore_memory import AgentCoreMemory

    captured: dict = {}

    class _FakeRecord:
        def __init__(self, content: dict) -> None:
            self._content = content

        def get(self, key: str, default=None):
            return {"content": self._content}.get(key, default)

    class _FakeManager:
        def list_long_term_memory_records(self, **kwargs):
            captured.update(kwargs)
            # Reject the deprecated / historic kwargs so a regression is loud.
            assert "memoryId" not in kwargs, "drifted SDK kwarg memoryId"
            assert "namespace_prefix" not in kwargs, "deprecated SDK kwarg namespace_prefix"
            assert "maxResults" not in kwargs, "drifted SDK kwarg maxResults"
            return [
                _FakeRecord({"vibe": ["minimal"], "colors": ["warm"]}),
            ]

    mem = AgentCoreMemory(memory_id="mem-test")
    mem._sdk_manager = _FakeManager()

    loaded = _run(mem.get_user_preferences("alice"))

    assert loaded is not None
    assert loaded.vibe == ["minimal"]
    assert captured["namespace"] == "user:alice:preferences"
    assert captured["max_results"] == 1
