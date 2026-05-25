"""
AgentCore Memory — Short-Term Memory (STM) for session history and
persistent user preferences.

Challenge 6 (Requirements 2.5.2, 4.3.2, 4.4.1, 6.2.1). Exposes a single
``AgentCoreMemory`` class with four async methods:

    append_session_turn(session_ns, turn)
    get_session_history(session_ns)
    get_user_preferences(user_id)
    set_user_preferences(user_id, prefs)

Key schemes (strict — never silently merged, per Requirement 4.3.3):

    user:{user_id}:session:{session_id}   authenticated sessions
    anon:{session_id}                     anonymous sessions
    user:{user_id}:preferences            persistent prefs

The authenticated session namespace is built by
``services.agentcore_identity.AgentCoreIdentityService`` (Challenge 9.2)
and passed verbatim into ``append_session_turn`` /
``get_session_history``. This module never infers a namespace from a
raw ``user_id`` + ``session_id`` pair, so a future change to the
namespace format only touches the identity service.

When ``settings.AGENTCORE_MEMORY_ID`` is set the class routes calls
through the ``bedrock-agentcore`` SDK's ``MemorySessionManager``. When
unset (the workshop default before C9) it falls back to a process-local
``dict`` so ``POST /api/user/preferences`` and ``POST /api/agent/chat``
work end-to-end offline — identical pattern to the Challenge 5 runtime
fallback in ``agentcore_runtime.py``.

The legacy helper functions ``create_agentcore_session_manager``,
``get_user_memories``, and ``search_episodic_memories`` are retained
outside the challenge block because ``app.py`` and ``services/chat.py``
import them directly for the pre-C9 "wire it live" demo surface.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config import settings
from models import Preferences

logger = logging.getLogger(__name__)


# === CHALLENGE 6: AgentCore Memory (STM) — START ===
# Requirements 2.5.2, 4.3.2, 4.4.1, 6.2.1, and Design sequence #3
# (Multi-turn conversation with STM).
#
# Participants delete this block and reimplement ``AgentCoreMemory``
# using the ``bedrock-agentcore`` SDK's ``MemorySessionManager``. The
# in-memory ``dict`` fallback keeps the workshop runnable offline (no
# AgentCore Memory resource provisioned) by mirroring the exact same
# namespace contract in memory.
#
# Key schemes (strict — never silently merged, per Req 4.3.3):
#
#     user:{user_id}:session:{session_id}   authenticated sessions
#     anon:{session_id}                     anonymous sessions
#     user:{user_id}:preferences            persistent prefs
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_memory.py pellier/backend/services/agentcore_memory.py

# Process-local fallback store. Keyed by the raw namespace string so
# ``anon:{sid}`` and ``user:{uid}:session:{sid}`` are physically
# disjoint entries — Req 4.3.3 holds by construction.
_SESSION_STORE: Dict[str, List[Dict[str, Any]]] = {}
_PREFS_STORE: Dict[str, Dict[str, Any]] = {}

# Module-level SDK import status. The Atelier memory route constructs a
# fresh ``AgentCoreMemory`` on every request (see
# ``routes/atelier_observatory.py::_load_live_semantic``), so a per-instance
# cache for the SDK handle is useless — every new instance would retry the
# import and log "bedrock-agentcore not installed" again. Caching the
# success/failure at module level means the warning fires once per process.
#
# ``None``  → not yet probed
# ``False`` → probed and failed (SDK not installed); use in-memory fallback
# ``True``  → probed and succeeded; SDK is importable
_SDK_AVAILABLE: Optional[bool] = None


def _prefs_key(user_id: str) -> str:
    """Return the canonical preferences key for ``user_id``.

    Kept private so the on-disk key scheme never leaks into call sites.
    """
    return f"user:{user_id}:preferences"


class AgentCoreMemory:
    """Short-term memory + persistent preferences backed by AgentCore.

    The class is a thin namespace-scoped facade over the SDK. Every
    read/write uses the namespace string passed in by the caller; no
    cross-namespace merge is ever performed (Req 4.3.3).

    When ``settings.AGENTCORE_MEMORY_ID`` is unset the class transparently
    uses a process-local ``dict``. Tests rely on this path so the suite
    runs without provisioning an AgentCore Memory resource.
    """

    def __init__(self, memory_id: Optional[str] = None, region: Optional[str] = None) -> None:
        self._memory_id = memory_id if memory_id is not None else settings.AGENTCORE_MEMORY_ID
        self._region = region or settings.aws_region_resolved
        self._sdk_manager: Any = None  # lazy — see _get_sdk_manager

    # ------------------------------------------------------------------
    # SDK handle (lazy, optional)
    # ------------------------------------------------------------------

    def _get_sdk_manager(self) -> Any:
        """Return a cached ``MemorySessionManager`` or ``None``.

        Returns ``None`` (not raises) when the SDK is unavailable or
        ``AGENTCORE_MEMORY_ID`` is unset so the in-memory fallback path
        takes over without any try/except gymnastics at call sites.

        The "SDK installed?" probe is cached at module scope (not
        per-instance) because the Atelier memory route builds a fresh
        ``AgentCoreMemory`` per request — without this the warning would
        fire on every page load when ``bedrock-agentcore`` isn't
        importable in the running interpreter (e.g. uvicorn launched
        outside the venv).
        """
        if not self._memory_id:
            return None
        if self._sdk_manager is not None:
            return self._sdk_manager

        global _SDK_AVAILABLE
        if _SDK_AVAILABLE is False:
            return None

        try:
            from bedrock_agentcore.memory import MemorySessionManager

            _SDK_AVAILABLE = True
            self._sdk_manager = MemorySessionManager(
                memory_id=self._memory_id,
                region_name=self._region,
            )
            return self._sdk_manager
        except ImportError:
            if _SDK_AVAILABLE is None:
                logger.warning(
                    "bedrock-agentcore not installed — AgentCoreMemory using "
                    "in-memory fallback. If you provisioned an AgentCore Memory "
                    "resource, make sure uvicorn is launched from the venv where "
                    "``pip install -e .`` ran (e.g. "
                    "``pellier/backend/.venv/bin/uvicorn app:app``)."
                )
            _SDK_AVAILABLE = False
            return None
        except Exception as exc:  # pragma: no cover - SDK init path
            logger.warning("AgentCore MemorySessionManager init failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Session history (STM)
    # ------------------------------------------------------------------

    async def append_session_turn(
        self,
        session_ns: str,
        turn: Dict[str, Any],
    ) -> None:
        """Append one turn to ``session_ns``.

        ``turn`` is ``{"role": "user"|"assistant", "content": str, ...}``.
        The namespace is whatever the identity service computed — the
        method does not derive it from ``user_id``/``session_id`` itself.
        """
        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                # MemorySessionManager.create_memory_session expects
                # actor_id + session_id. We treat the full namespace as
                # actor_id so anon:{sid} and user:{uid}:session:{sid}
                # land in separate AgentCore actors and Req 4.3.3 holds
                # end-to-end.
                session = mgr.create_memory_session(
                    actor_id=session_ns,
                    session_id=session_ns,
                )
                session.add_turns(turns=[turn])
                return
            except Exception as exc:  # pragma: no cover - SDK error path
                logger.warning(
                    "AgentCore append_session_turn failed for %s: %s — "
                    "falling back to in-memory store",
                    session_ns,
                    exc,
                )
        _SESSION_STORE.setdefault(session_ns, []).append(dict(turn))

    async def get_session_history(self, session_ns: str) -> List[Dict[str, Any]]:
        """Return all turns stored under ``session_ns`` in insertion order.

        A namespace with no writes returns ``[]``. Crucially, a
        ``user:{uid}:session:{sid}`` namespace never reads from the
        corresponding ``anon:{sid}`` namespace and vice versa — they
        are different strings keying different entries (Req 4.3.3).
        """
        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                session = mgr.create_memory_session(
                    actor_id=session_ns,
                    session_id=session_ns,
                )
                # get_last_k_turns with a generous k stands in for "all
                # turns" — the workshop sessions are short (<20 turns).
                return list(session.get_last_k_turns(k=100))
            except Exception as exc:  # pragma: no cover - SDK error path
                logger.warning(
                    "AgentCore get_session_history failed for %s: %s — "
                    "falling back to in-memory store",
                    session_ns,
                    exc,
                )
        return list(_SESSION_STORE.get(session_ns, []))

    # ------------------------------------------------------------------
    # User preferences (persistent)
    # ------------------------------------------------------------------

    async def get_user_preferences(self, user_id: str) -> Optional[Preferences]:
        """Return the stored ``Preferences`` for ``user_id`` or ``None``.

        The backing key is ``user:{user_id}:preferences`` (Req 4.4.1).
        Anonymous callers have no ``user_id`` and must not reach this
        method — the route layer enforces that.
        """
        key = _prefs_key(user_id)

        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                records = mgr.list_long_term_memory_records(
                    memoryId=self._memory_id,
                    namespace=key,
                    maxResults=1,
                )
                items = records.get("memoryRecords") or records.get("records") or []
                if items:
                    payload = items[0].get("content", {})
                    if isinstance(payload, dict) and payload:
                        return Preferences.model_validate(payload)
                return None
            except Exception as exc:  # pragma: no cover - SDK error path
                logger.warning(
                    "AgentCore get_user_preferences failed for %s: %s — "
                    "falling back to in-memory store",
                    user_id,
                    exc,
                )

        stored = _PREFS_STORE.get(key)
        if stored is None:
            return None
        return Preferences.model_validate(stored)

    async def set_user_preferences(
        self,
        user_id: str,
        prefs: Preferences,
    ) -> Preferences:
        """Persist ``prefs`` under ``user:{user_id}:preferences`` and
        return the saved object.

        Accepts either a ``Preferences`` instance or any dict-compatible
        payload so route handlers can pass the parsed Pydantic model
        straight through.
        """
        key = _prefs_key(user_id)
        prefs_obj = (
            prefs if isinstance(prefs, Preferences) else Preferences.model_validate(prefs)
        )
        payload = prefs_obj.model_dump(mode="json", by_alias=False)

        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                session = mgr.create_memory_session(
                    actor_id=user_id,
                    session_id="preferences",
                )
                session.add_turns(
                    turns=[{"role": "system", "content": payload, "namespace": key}]
                )
                _PREFS_STORE[key] = payload
                return prefs_obj
            except Exception as exc:  # pragma: no cover - SDK error path
                logger.warning(
                    "AgentCore set_user_preferences failed for %s: %s — "
                    "falling back to in-memory store",
                    user_id,
                    exc,
                )

        _PREFS_STORE[key] = payload
        return prefs_obj
# === CHALLENGE 6: AgentCore Memory (STM) — END ===



# ---------------------------------------------------------------------------
# Legacy helpers (pre-C9 "Wire It Live" surface)
# ---------------------------------------------------------------------------
#
# These are NOT part of Challenge 6. ``app.py`` and ``services/chat.py``
# import them directly for the older AgentCore Memory demo endpoints
# (``/api/user/memories``, episodic memory panel). They stay out of the
# challenge block so participants can reimplement ``AgentCoreMemory``
# without breaking the demo surface.


def create_agentcore_session_manager(
    session_id: str,
    user_id: str = "anonymous",
):
    """Create a Strands-integrated AgentCore Memory session manager.

    Returns ``None`` when the SDK or ``AGENTCORE_MEMORY_ID`` is not
    configured so call sites can treat it as optional.
    """
    if not settings.AGENTCORE_MEMORY_ID:
        logger.info("AGENTCORE_MEMORY_ID not set — memory disabled")
        return None

    try:
        from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )

        config = AgentCoreMemoryConfig(
            memory_id=settings.AGENTCORE_MEMORY_ID,
            session_id=session_id,
            actor_id=user_id,
            batch_size=5,
        )

        session_manager = AgentCoreMemorySessionManager(
            config,
            region_name=settings.AWS_REGION,
        )

        logger.info(
            "✅ AgentCore Memory session created (memory_id=%s, user=%s)",
            settings.AGENTCORE_MEMORY_ID,
            user_id,
        )
        return session_manager

    except ImportError:
        logger.warning("bedrock-agentcore package not installed — pip install bedrock-agentcore")
        return None
    except Exception as e:
        logger.warning("AgentCore Memory setup failed: %s", e)
        return None


def get_user_memories(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve stored memories / preferences for a user via the raw API."""
    if not settings.AGENTCORE_MEMORY_ID:
        return []

    try:
        import boto3

        client = boto3.client("bedrock-agentcore", region_name=settings.AWS_REGION)
        response = client.retrieve_memories(
            memoryId=settings.AGENTCORE_MEMORY_ID,
            actorId=user_id,
            maxResults=20,
        )
        memories = []
        for item in response.get("memories", []):
            memories.append(
                {
                    "id": item.get("memoryId", ""),
                    "type": item.get("memoryType", "unknown"),
                    "content": item.get("content", ""),
                    "created_at": str(item.get("createdAt", "")),
                    "metadata": item.get("metadata", {}),
                }
            )
        return memories

    except ImportError:
        logger.warning("bedrock-agentcore not installed")
        return []
    except Exception as e:
        logger.warning("Failed to retrieve memories: %s", e)
        return []


def search_episodic_memories(
    user_id: str,
    query: str,
    session_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Search episodic memories for relevant past experiences.

    Episodic memory captures structured experiences (Goal, Reasoning,
    Actions, Outcome, Reflection) so agents can learn from past
    interactions and tune decisions over time.
    """
    if not settings.AGENTCORE_MEMORY_ID:
        return []

    try:
        from bedrock_agentcore.memory import MemorySessionManager

        mgr = MemorySessionManager(
            memory_id=settings.AGENTCORE_MEMORY_ID,
            region_name=settings.AWS_REGION,
        )
        memory_session = mgr.create_memory_session(
            actor_id=user_id,
            session_id=session_id or "search",
        )

        records = memory_session.search_long_term_memories(
            query=query,
            namespace_prefix="/",
            top_k=top_k,
        )

        episodes = []
        for record in records:
            content = record.get("content", {})
            episodes.append(
                {
                    "text": content.get("text", ""),
                    "type": record.get("memoryType", "unknown"),
                    "score": record.get("score", 0),
                    "created_at": str(record.get("createdAt", "")),
                }
            )

        logger.info("Found %d episodic memories for query: %s", len(episodes), query[:50])
        return episodes

    except ImportError:
        logger.warning("bedrock-agentcore not installed — episodic memory unavailable")
        return []
    except Exception as e:
        logger.warning("Episodic memory search failed: %s", e)
        return []
