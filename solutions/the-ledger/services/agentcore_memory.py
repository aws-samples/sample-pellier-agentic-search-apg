"""
AgentCore Memory — Short-Term Memory (STM) for session history and
persistent user preferences.

AgentCore Memory (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html)
is the managed memory primitive for AgentCore. We use the short-term
side here (event log per session) plus durable preference records.
Episodic memory comes from Aurora customer events. Procedural knowledge
comes from checked-in runtime skills and MCP tool schemas. Aurora
``pellier.tool_audit`` is operational history, not memory.

AgentCore Memory (Requirements 2.5.2, 4.3.2, 4.4.1, 6.2.1). Exposes a single
``AgentCoreMemory`` class with four async methods:

    append_session_turn(session_ns, turn)
    get_session_history(session_ns)
    get_user_preferences(user_id)
    set_user_preferences(user_id, prefs)

Key schemes (strict — never silently merged, per Requirement 4.3.3):

    user-{user_id}-session-{session_id}   authenticated sessions
    anon-{session_id}                     anonymous sessions
    user:{user_id}:preferences            persistent prefs

Session namespaces use dashes (not colons) because AgentCore session
IDs must match ``[a-zA-Z0-9][a-zA-Z0-9-_]*``. The preferences key has
no session-id component so colons are fine there.

The authenticated session namespace is built by
``services.agentcore_identity.AgentCoreIdentityService`` (AgentCore Identity)
and passed verbatim into ``append_session_turn`` /
``get_session_history``. This module never infers a namespace from a
raw ``user_id`` + ``session_id`` pair, so a future change to the
namespace format only touches the identity service.

When ``settings.AGENTCORE_MEMORY_ID`` is set the class routes calls
through the ``bedrock-agentcore`` SDK's ``MemorySessionManager``. When
unset it falls back to a process-local ``dict`` so
``POST /api/user/preferences`` and ``POST /api/agent/chat`` work
end-to-end offline — the same fail-soft pattern used by the runtime
bridge in ``agentcore_runtime.py``.

The legacy helper functions ``get_user_memories`` and
``search_episodic_memories`` are retained outside the reference class
because ``app.py`` imports them directly for older memory demo endpoints.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from models import Preferences

logger = logging.getLogger(__name__)


# === REFERENCE: AgentCore Memory (STM) — START ===
# Requirements 2.5.2, 4.3.2, 4.4.1, 6.2.1, and Design sequence #3
# (Multi-turn conversation with STM).
#
# Reference implementation for ``AgentCoreMemory`` using the
# ``bedrock-agentcore`` SDK's ``MemorySessionManager``. The in-memory
# ``dict`` fallback keeps the workshop runnable offline by mirroring the
# same namespace contract in memory.
#
# Key schemes (strict — never silently merged, per Req 4.3.3):
#
#     user-{user_id}-session-{session_id}   authenticated sessions
#     anon-{session_id}                     anonymous sessions
#     user:{user_id}:preferences            persistent prefs
#
# Session namespaces use dashes — AgentCore session IDs must match
# ``[a-zA-Z0-9][a-zA-Z0-9-_]*``. The preferences key has no session-id
# component so the legacy colon form is retained there.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_memory.py pellier/backend/services/agentcore_memory.py

def _store_key(actor_id: str, session_id: str) -> str:
    """The fallback-store key for an identity pair.

    When actor and session are the same string this is the historical shopper key,
    so existing shopper entries keep working unchanged. When they differ — the
    operator mapping — the pair is composed. Both the writer and the reader call
    this, because a writer and reader that compose keys independently is exactly how
    the operator read came back empty while its write reported success.
    """
    return actor_id if actor_id == session_id else f"{actor_id}|{session_id}"


# Process-local fallback store. Keyed by the raw namespace string so
# ``anon-{sid}`` and ``user-{uid}-session-{sid}`` are physically
# disjoint entries — Req 4.3.3 holds by construction.
# Which store served a call. A process-local dict is NOT persistence — it dies with
# the worker — so a caller that reports "remembered" without distinguishing the two is
# claiming durability it does not have. Found live: uvicorn launched outside the venv
# has no `bedrock-agentcore`, every operator turn silently used the dict, and the turn
# payload still said `memoryPersisted: true`.
BACKEND_AGENTCORE = "agentcore"
BACKEND_PROCESS_LOCAL = "process_local"

_SESSION_STORE: Dict[str, List[Dict[str, Any]]] = {}
_PREFS_STORE: Dict[str, Dict[str, Any]] = {}

# Module-level SDK import status. The Observatory memory route constructs a
# fresh ``AgentCoreMemory`` on every request (see
# ``routes/observatory_observatory.py::_load_live_semantic``), so a per-instance
# cache for the SDK handle is useless — every new instance would retry the
# import and log "bedrock-agentcore not installed" again. Caching the
# success/failure at module level means the warning fires once per process.
#
# ``None``  → not yet probed
# ``False`` → probed and failed (SDK not installed); use in-memory fallback
# ``True``  → probed and succeeded; SDK is importable
_SDK_AVAILABLE: Optional[bool] = None


class ManagedMemoryError(RuntimeError):
    """Stable fail-closed error for a required AgentCore Memory path."""

    code = "managed_memory_unavailable"


def probe_memory_backend_status(
    memory_id: Optional[str] = None,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify that the configured AgentCore Memory resource is ACTIVE."""
    from services.memory_contract import configuration_errors

    resolved_id = (
        memory_id if memory_id is not None else settings.AGENTCORE_MEMORY_ID
    ) or ""
    resolved_region = region or settings.aws_region_resolved

    try:
        import bedrock_agentcore  # type: ignore  # noqa: F401
    except ImportError as exc:
        return {
            "live": False,
            "source": "in-process-dict",
            "memory_id": resolved_id,
            "sdk_available": False,
            "resource_status": None,
            "fallback_reason": f"bedrock-agentcore SDK not importable: {exc}",
        }

    if not resolved_id:
        return {
            "live": False,
            "source": "in-process-dict",
            "memory_id": "",
            "sdk_available": True,
            "resource_status": None,
            "fallback_reason": "AGENTCORE_MEMORY_ID env var not set",
        }

    try:
        import boto3

        response = boto3.client(
            "bedrock-agentcore-control",
            region_name=resolved_region,
        ).get_memory(memoryId=resolved_id)
        resource_status = str(response.get("memory", {}).get("status", "UNKNOWN"))
    except Exception as exc:  # pragma: no cover - exact SDK errors vary
        return {
            "live": False,
            "source": "in-process-dict",
            "memory_id": resolved_id,
            "sdk_available": True,
            "resource_status": None,
            "fallback_reason": (
                "AgentCore GetMemory verification failed: "
                f"{exc.__class__.__name__}"
            ),
        }

    if resource_status != "ACTIVE":
        return {
            "live": False,
            "source": "in-process-dict",
            "memory_id": resolved_id,
            "sdk_available": True,
            "resource_status": resource_status,
            "fallback_reason": (
                f"AgentCore Memory resource is {resource_status}, expected ACTIVE"
            ),
        }

    return {
        "live": True,
        "source": "agentcore-sdk",
        "memory_id": resolved_id,
        "sdk_available": True,
        "resource_status": resource_status,
        "strategies_ready": not configuration_errors(response["memory"]),
        "strategy_errors": configuration_errors(response["memory"]),
        "fallback_reason": None,
    }


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

    def __init__(
        self,
        memory_id: Optional[str] = None,
        region: Optional[str] = None,
        *,
        strict: bool = False,
    ) -> None:
        self._memory_id = memory_id if memory_id is not None else settings.AGENTCORE_MEMORY_ID
        self._region = region or settings.aws_region_resolved
        self._strict = strict
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
        per-instance) because the Observatory memory route builds a fresh
        ``AgentCoreMemory`` per request — without this the warning would
        fire on every page load when ``bedrock-agentcore`` isn't
        importable in the running interpreter (e.g. uvicorn launched
        outside the venv).
        """
        if not self._memory_id:
            if self._strict:
                raise ManagedMemoryError("AGENTCORE_MEMORY_ID is not configured")
            return None
        if self._sdk_manager is not None:
            return self._sdk_manager

        global _SDK_AVAILABLE
        if _SDK_AVAILABLE is False:
            if self._strict:
                raise ManagedMemoryError("bedrock-agentcore SDK is not importable")
            return None

        try:
            import boto3
            from bedrock_agentcore.memory import MemorySessionManager

            _SDK_AVAILABLE = True
            self._sdk_manager = MemorySessionManager(
                memory_id=self._memory_id,
                region_name=self._region,
                boto3_session=boto3.Session(region_name=self._region),
            )
            return self._sdk_manager
        except ImportError as exc:
            if self._strict:
                raise ManagedMemoryError(
                    "bedrock-agentcore SDK is not importable"
                ) from exc
            if _SDK_AVAILABLE is None:
                logger.warning(
                    "bedrock-agentcore not installed — AgentCoreMemory using "
                    "in-memory fallback. If you provisioned an AgentCore Memory "
                    "resource, make sure uvicorn is launched from the venv where "
                    "``pip install -e .`` ran (e.g. "
                    "``pellier/backend/.venv/bin/python -m uvicorn app:app``)."
                )
            _SDK_AVAILABLE = False
            return None
        except Exception as exc:  # pragma: no cover - SDK init path
            if self._strict:
                raise ManagedMemoryError(
                    "AgentCore MemorySessionManager initialization failed"
                ) from exc
            logger.warning("AgentCore MemorySessionManager init failed: %s", exc)
            return None

    @staticmethod
    def _to_conversational(turn: Dict[str, Any]):
        """Map a ``{"role","content"}`` dict to the SDK's ConversationalMessage.

        The installed bedrock-agentcore SDK's ``add_turns`` requires
        ``ConversationalMessage(text, MessageRole)`` objects and RAISES
        ValueError on a raw dict — passing dicts (the old bug) meant every
        AgentCore write threw and silently fell back to the in-process store, so
        the Memory pillar never actually exercised AgentCore. Roles map to
        USER/ASSISTANT; anything else (e.g. "system") → OTHER."""
        from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

        role_str = str(turn.get("role", "user")).lower()
        role = {
            "user": MessageRole.USER,
            "assistant": MessageRole.ASSISTANT,
        }.get(role_str, MessageRole.OTHER)
        return ConversationalMessage(str(turn.get("content", "")), role)

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
        await self.append_session_turns(session_ns, [turn])

    async def append_memory_event(
        self,
        *,
        actor_id: str,
        session_id: str,
        turns: List[Dict[str, Any]],
    ) -> str:
        """The generic AgentCore Memory write: an explicit actor AND session.

        Returns which store served the write — ``BACKEND_AGENTCORE`` or
        ``BACKEND_PROCESS_LOCAL``. The caller needs that to avoid reporting a
        fallback dict as durable memory.

        AgentCore scopes short-term events by actor plus session, and the two answer
        different questions — the actor is the entity interacting with the agent, the
        session is one conversation. Pellier has two surfaces that map them
        differently, so the mapping belongs at the call site rather than being baked
        in here:

            shopper    actor_id = session_id = session_ns   (frozen, see below)
            operator   actor_id = operator subject
                       session_id = Concierge session id

        `append_session_turns` remains the shopper wrapper and its semantics are
        unchanged. Do not "simplify" the two into one: the shopper form deliberately
        collapses actor and session so `anon-{sid}` and `user-{uid}-session-{sid}`
        land in separate AgentCore actors, and the operator form deliberately does
        not, so operator preference memory accrues to the operator rather than to
        whichever client's record happened to be open.
        """
        if not turns:
            return BACKEND_PROCESS_LOCAL
        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                session = mgr.create_memory_session(
                    actor_id=actor_id,
                    session_id=session_id,
                )
                session.add_turns(
                    messages=[self._to_conversational(turn) for turn in turns]
                )
                return BACKEND_AGENTCORE
            except Exception as exc:  # pragma: no cover - SDK error path
                if self._strict:
                    raise ManagedMemoryError(
                        "AgentCore session append failed"
                    ) from exc
                logger.warning(
                    "AgentCore append_memory_event failed for %s/%s: %s — "
                    "falling back to the process-local store",
                    actor_id, session_id, exc,
                )
        # Fallback keyed by the pair, so the two surfaces never share a bucket.
        _SESSION_STORE.setdefault(_store_key(actor_id, session_id), []).extend(turns)
        return BACKEND_PROCESS_LOCAL

    async def append_session_turns(
        self,
        session_ns: str,
        turns: List[Dict[str, Any]],
    ) -> str:
        """Append one logical turn as a single AgentCore Memory event.

        SHOPPER WRAPPER — semantics frozen. `actor_id == session_id == session_ns`
        is intentional and load-bearing for shopper isolation.

        Returns which store held the write, ``BACKEND_AGENTCORE`` or
        ``BACKEND_PROCESS_LOCAL``, like ``append_memory_event``. A non-strict
        SDK failure lands the turn in the process-local dict and returns
        normally; without the backend a receipt would report that fallback
        as managed persistence.
        """
        if not turns:
            return BACKEND_PROCESS_LOCAL
        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                # MemorySessionManager.create_memory_session expects
                # actor_id + session_id. We treat the full namespace as
                # actor_id so anon-{sid} and user-{uid}-session-{sid}
                # land in separate AgentCore actors and Req 4.3.3 holds
                # end-to-end.
                session = mgr.create_memory_session(
                    actor_id=session_ns,
                    session_id=session_ns,
                )
                session.add_turns(
                    messages=[self._to_conversational(turn) for turn in turns]
                )
                return BACKEND_AGENTCORE
            except Exception as exc:  # pragma: no cover - SDK error path
                if self._strict:
                    raise ManagedMemoryError(
                        "AgentCore session append failed"
                    ) from exc
                logger.warning(
                    "AgentCore append_session_turns failed for %s: %s — "
                    "falling back to in-memory store",
                    session_ns,
                    exc,
                )
        _SESSION_STORE.setdefault(session_ns, []).extend(
            dict(turn) for turn in turns
        )
        return BACKEND_PROCESS_LOCAL

    async def get_memory_events(
        self, *, actor_id: str, session_id: str
    ) -> Tuple[List[Dict[str, Any]], str]:
        """The generic read: an explicit actor AND session, mirroring the writer.

        Returns ``(turns, backend)``. The backend matters even when the turns are
        empty: "AgentCore Memory holds nothing for this conversation" and "AgentCore
        Memory was never reached" are different facts, and an evidence surface may not
        render them identically.

        This exists because `get_session_history` is the SHOPPER reader and treats its
        single argument as both actor and session. Reading an OPERATOR conversation
        through it looked up actor=session_id when the write had used
        actor=operator_subject, so every operator turn read back empty while its write
        reported success — found live on the second Concierge turn, which should have
        seen the first.

        A generic writer needs a generic reader; a mismatched pair is worse than
        either alone because it fails silently.
        """
        return await self._read_turns_with_backend(
            actor_id=actor_id, session_id=session_id
        )

    async def get_session_history(self, session_ns: str) -> List[Dict[str, Any]]:
        """Return all turns stored under ``session_ns`` in insertion order.

        SHOPPER READER — semantics frozen: actor and session are both ``session_ns``.

        A namespace with no writes returns ``[]``. Crucially, a
        ``user-{uid}-session-{sid}`` namespace never reads from the
        corresponding ``anon-{sid}`` namespace and vice versa — they
        are different strings keying different entries (Req 4.3.3).
        """
        turns, _backend = await self._read_turns_with_backend(
            actor_id=session_ns, session_id=session_ns
        )
        return turns

    async def _read_turns_with_backend(
        self, *, actor_id: str, session_id: str
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Shared read for both surfaces. The caller decides the identity pair."""
        session_ns = session_id
        mgr = self._get_sdk_manager()
        if mgr is not None:
            try:
                session = mgr.create_memory_session(
                    actor_id=actor_id,
                    session_id=session_id,
                )
                # get_last_k_turns with a generous k stands in for "all
                # turns" — the workshop sessions are short (<20 turns).
                # The SDK returns turn objects (uppercase roles, nested
                # ``content.text``, datetime fields) that are NOT JSON
                # serializable as-is — normalize to the plain
                # ``{role, content, timestamp}`` shape the route returns
                # and the frontend hydrates from. Without this the SDK
                # path 500s at JSONResponse render time (the in-memory
                # fallback below already returns plain dicts, which is
                # why it only breaks on a provisioned account).
                #
                # ``get_last_k_turns`` returns most-recent-first; the route
                # and the frontend expect a chronological timeline, so
                # reverse after flattening. The in-memory fallback below
                # already stores in insertion (chronological) order.
                flat = self._normalize_sdk_turns(session.get_last_k_turns(k=100))
                flat.reverse()
                return flat, BACKEND_AGENTCORE
            except Exception as exc:  # pragma: no cover - SDK error path
                if self._strict:
                    raise ManagedMemoryError(
                        "AgentCore session history read failed"
                    ) from exc
                logger.warning(
                    "AgentCore get_session_history failed for %s: %s — "
                    "falling back to in-memory store",
                    session_ns,
                    exc,
                )
        return (
            list(_SESSION_STORE.get(_store_key(actor_id, session_id), [])),
            BACKEND_PROCESS_LOCAL,
        )

    @staticmethod
    def _normalize_sdk_turns(raw: Any) -> List[Dict[str, Any]]:
        """Flatten ``get_last_k_turns`` output into JSON-safe turn dicts.

        The SDK groups messages into turns, so the return is a list of
        turns where each turn is itself a list of message dicts shaped
        like ``{"role": "USER", "content": {"text": "..."}}`` (roles are
        uppercase; ``content`` may be a nested dict or a bare string;
        timestamps arrive as ``datetime``). This collapses that into the
        flat ``{"role": "user"|"assistant", "content": <str>,
        "timestamp": <str>}`` list the route serializes and Pellier
        chat hydrates from.
        """
        def _attr(obj: Any, key: str, default: Any = None) -> Any:
            # Messages arrive as plain dicts (in-memory fallback + tests) OR
            # as SDK ``EventMessage`` objects on a provisioned account. The
            # latter are dict-LIKE (they even expose ``.get``) but are NOT
            # ``dict`` instances, so ``isinstance(msg, dict)`` is False and a
            # dict-only reader silently drops every real turn. Read by
            # attribute, falling back to dict access.
            if isinstance(obj, dict):
                return obj.get(key, default)
            val = getattr(obj, key, None)
            return val if val is not None else default

        def _text(content: Any) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, dict):
                return str(content.get("text", ""))
            # SDK content block exposing ``.text``.
            text_attr = getattr(content, "text", None)
            if text_attr is not None:
                return str(text_attr)
            # A list of content blocks: join their text.
            if isinstance(content, (list, tuple)):
                return " ".join(_text(b) for b in content if b is not None)
            return str(content) if content is not None else ""

        def _role(role: Any) -> str:
            return "user" if str(role).lower() == "user" else "assistant"

        turns: List[Dict[str, Any]] = []
        for turn in (raw or []):
            # A turn is normally a list of messages; tolerate a bare
            # message (dict or SDK object) in case the shape ever changes.
            messages = turn if isinstance(turn, (list, tuple)) else [turn]
            for msg in messages:
                # Accept dict OR SDK object; only skip genuinely empty slots.
                if msg is None:
                    continue
                ts = _attr(msg, "timestamp", None)
                if ts is None:
                    ts = _attr(msg, "createdAt", "")
                turns.append({
                    "role": _role(_attr(msg, "role", "assistant")),
                    "content": _text(_attr(msg, "content", "")),
                    "timestamp": str(ts) if ts else "",
                })
        return turns

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
                # SDK param is `namespace_prefix` (NOT `namespace`); returns a
                # List[MemoryRecord] whose `content` is {"text": "<json>"}.
                # Long-term records are created by Pellier's USER_PREFERENCE
                # strategy. Typed onboarding and extracted semantic preferences
                # remain separate contracts and namespaces.
                records = mgr.list_long_term_memory_records(
                    namespace_prefix=key,
                    max_results=1,
                )
                if records:
                    content = records[0].get("content", {})
                    text = content.get("text") if isinstance(content, dict) else None
                    if text:
                        import json as _json
                        try:
                            payload = _json.loads(text)
                        except (ValueError, TypeError):
                            payload = None
                        if isinstance(payload, dict) and payload:
                            return Preferences.model_validate(payload)
            except Exception as exc:  # pragma: no cover - SDK error path
                if self._strict:
                    raise ManagedMemoryError(
                        "AgentCore preference read failed"
                    ) from exc
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
                import json as _json
                session = mgr.create_memory_session(
                    actor_id=user_id,
                    session_id="preferences",
                )
                # add_turns requires ConversationalMessage objects (not dicts).
                # Serialize the prefs payload to JSON text so get_user_preferences
                # can json.loads(content.text) symmetrically. Role "system" maps
                # to MessageRole.OTHER.
                session.add_turns(
                    messages=[self._to_conversational(
                        {"role": "system", "content": _json.dumps(payload)}
                    )]
                )
                _PREFS_STORE[key] = payload
                return prefs_obj
            except Exception as exc:  # pragma: no cover - SDK error path
                if self._strict:
                    raise ManagedMemoryError(
                        "AgentCore preference append failed"
                    ) from exc
                logger.warning(
                    "AgentCore set_user_preferences failed for %s: %s — "
                    "falling back to in-memory store",
                    user_id,
                    exc,
                )

        _PREFS_STORE[key] = payload
        return prefs_obj

    # ------------------------------------------------------------------
    # Semantic memory (durable, extracted by a USER_PREFERENCE strategy)
    # ------------------------------------------------------------------

    async def get_semantic_memories(self, actor_id: str) -> List[str]:
        """Return AgentCore-*extracted* preference strings for ``actor_id``.

        This is the **semantic** substrate — durable taste signals the
        ``USER_PREFERENCE`` extraction strategy *learns* from conversation
        and writes as long-term records under
        ``/pellier/preferences/{actor_id}/``. Each record's ``content.text``
        is a JSON string ``{"context", "preference", "categories"[]}``; we
        surface the ``preference`` field.

        This is deliberately NOT ``get_user_preferences`` — that method
        returns the *typed onboarding* ``Preferences`` blob the shopper
        explicitly entered (used for storefront personalization). Learned
        semantic memory and typed preferences are two different concepts on
        two different namespaces; never conflate them.

        Returns ``[]`` (never raises, never fabricates) when the SDK or
        ``AGENTCORE_MEMORY_ID`` is unavailable, the strategy has not
        extracted yet, or no records exist. The Observatory route renders the
        empty live state with a caveat instead of substituting seeded text.
        """
        import json as _json

        mgr = self._get_sdk_manager()
        if mgr is None:
            return []

        # Custom namespace registered at create time as
        # "/pellier/preferences/{actorId}/"; resolve {actorId} ourselves so
        # the read needs no strategy-id threading. Leading slash MUST match
        # the create-time template.
        namespace = f"/pellier/preferences/{actor_id}/"
        try:
            # 1.6.3 param is ``namespace_prefix`` (NOT ``namespace``).
            records = mgr.list_long_term_memory_records(
                namespace_prefix=namespace,
                max_results=20,
            )
        except Exception as exc:  # pragma: no cover - SDK error path
            if self._strict:
                raise ManagedMemoryError(
                    "AgentCore semantic memory read failed"
                ) from exc
            logger.warning(
                "AgentCore get_semantic_memories failed for %s: %s — "
                "semantic panel will show an empty live state",
                actor_id,
                exc,
            )
            return []

        preferences: List[str] = []
        for record in records:
            content = record.get("content", {})
            text = content.get("text") if isinstance(content, dict) else None
            if not text:
                continue
            try:
                payload = _json.loads(text)
            except (ValueError, TypeError):
                continue
            pref = payload.get("preference") if isinstance(payload, dict) else None
            if pref:
                preferences.append(str(pref))
        return preferences
# === REFERENCE: AgentCore Memory (STM) — END ===



# ---------------------------------------------------------------------------
# Legacy helpers
# ---------------------------------------------------------------------------
#
# These are support helpers outside the ``AgentCoreMemory`` class.
# ``app.py`` imports them directly for the older AgentCore Memory demo
# endpoints (``/api/user/memories``, episodic memory panel). They stay out
# of the reference block so ``AgentCoreMemory`` can evolve without breaking
# that demo surface.


def get_user_memories(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve stored memories / preferences for a user via the raw API."""
    if not settings.AGENTCORE_MEMORY_ID:
        return []

    try:
        import boto3

        # Data-plane op is `list_memory_records` (keyed by memoryId + namespace);
        # there is NO `retrieve_memories` op (the prior spelling silently failed
        # to []). Long-term records only exist on a memory created WITH an
        # extraction strategy; Pellier's is STM-only, so this returns [] in
        # practice — kept correct for when a strategy is added.
        client = boto3.client("bedrock-agentcore", region_name=settings.aws_region_resolved)
        response = client.list_memory_records(
            memoryId=settings.AGENTCORE_MEMORY_ID,
            namespace=f"user-{user_id}",
            maxResults=20,
        )
        memories = []
        for item in response.get("memoryRecordSummaries", response.get("memoryRecords", [])):
            memories.append(
                {
                    "id": item.get("memoryRecordId", ""),
                    "type": item.get("memoryStrategyId", "unknown"),
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
            region_name=settings.aws_region_resolved,
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
