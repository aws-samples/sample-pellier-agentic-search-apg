"""``/api/user/*`` routes — preference persistence (Task 3.4).

Implements Requirements 3.2.1–3.2.4 and 4.4.1–4.4.3:

  * ``GET  /api/user/preferences``   return the saved ``Preferences`` for
                                     the signed-in shopper or ``null``
                                     when none are set yet.
  * ``POST /api/user/preferences``   validate the payload against the
                                     four tag ``Literal`` types (422 on
                                     unknown values) and persist via
                                     ``AgentCoreMemory.set_user_preferences``.

Both endpoints are guarded by the ``require_user`` dependency from
``services.cognito_auth`` so anonymous requests 401 uniformly (Req
4.2.2). Preferences are stored at ``user:{user_id}:preferences`` via
``AgentCoreMemory`` — never in localStorage, never in the product DB
(Req 4.4.1, 4.4.3).

Design notes
------------

* **Validation.** ``Preferences`` already uses ``Literal`` types for its
  four tag groups (``VibeTag``, ``ColorTag``, ``OccasionTag``,
  ``CategoryTag``) declared in ``models/search.py``. Pydantic
  automatically returns HTTP 422 with per-field error entries whenever
  the payload carries an unknown value, so the handler itself does no
  manual validation — it just receives a ``Preferences`` instance.
* **Wire shape.** Req 3.2.1 / 3.2.2 call for ``{ preferences }`` on GET
  and the raw saved object on POST. The frontend in Task 1.3 test
  comments distinguishes ``null`` from empty; this module returns
  ``null`` explicitly for "unseen" and the same object shape for both
  endpoints so call sites don't have to branch on response shape.
* **Single instance.** The shared ``AgentCoreMemory`` is exposed through
  ``get_agentcore_memory`` so tests can override the dependency without
  reaching into module globals — same pattern ``cognito_auth`` uses
  for its service instance.

Routes are NOT part of any workshop challenge block. This file ships
without ``# === CHALLENGE ... ===`` markers.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from models import Preferences, VerifiedUser
from services.agentcore_memory import AgentCoreMemory
from services.cognito_auth import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])


# ---------------------------------------------------------------------------
# Shared AgentCoreMemory instance
# ---------------------------------------------------------------------------

_default_memory: Optional[AgentCoreMemory] = None


def get_agentcore_memory() -> AgentCoreMemory:
    """FastAPI-friendly accessor for the shared ``AgentCoreMemory``.

    A process-wide instance keeps the in-memory fallback dicts coherent
    across requests when ``AGENTCORE_MEMORY_ID`` is unset (workshop pre-C9
    path). Tests override this dependency to inject isolated instances.
    """
    global _default_memory
    if _default_memory is None:
        _default_memory = AgentCoreMemory()
    return _default_memory


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/preferences")
async def get_preferences(
    user: VerifiedUser = Depends(require_user),
    memory: AgentCoreMemory = Depends(get_agentcore_memory),
) -> JSONResponse:
    """Return the stored preferences for the authenticated shopper.

    Wire shape per Req 3.2.1: ``{"preferences": <Preferences>|null}``.
    The ``null`` case is preserved explicitly (not an empty object) so
    the frontend can distinguish "never onboarded" from "onboarded with
    no selections" and auto-open the preferences modal on fresh
    sign-ins (Req 1.4.4).
    """
    prefs = await memory.get_user_preferences(user.user_id)
    if prefs is None:
        return JSONResponse(status_code=200, content={"preferences": None})
    return JSONResponse(
        status_code=200,
        content={"preferences": prefs.model_dump(mode="json", by_alias=True)},
    )


@router.post("/preferences")
async def set_preferences(
    payload: Preferences,
    user: VerifiedUser = Depends(require_user),
    memory: AgentCoreMemory = Depends(get_agentcore_memory),
) -> JSONResponse:
    """Persist the shopper's preferences.

    FastAPI validates ``payload`` against the four ``Literal`` tag types
    before this handler runs, so any unknown value (e.g. ``vibe: ["wild"]``)
    surfaces as a 422 response whose ``detail`` array names the offending
    field path (Req 3.2.3). That's also why there is no try/except here:
    the happy path just forwards the validated model to
    ``AgentCoreMemory.set_user_preferences``.
    """
    saved = await memory.set_user_preferences(user.user_id, payload)
    return JSONResponse(
        status_code=200,
        content={"preferences": saved.model_dump(mode="json", by_alias=True)},
    )
