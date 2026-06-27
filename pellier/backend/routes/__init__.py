"""FastAPI routers for the Pellier backend.

Routers live here so ``app.py`` only wires them up with ``include_router``
rather than declaring every endpoint inline.

  * ``auth``     (Task 3.3) — ``/api/auth/*`` Cognito Hosted UI sign-in loop.
  * ``user``     (Task 3.4) — ``/api/user/preferences`` GET/POST protected by
                              the Cognito JWT middleware.
  * ``agent``    (Task 3.5) — ``/api/agent/chat`` SSE stream + session history.
  * ``products`` (Task 3.6) — ``/api/products`` editorial + personalized list,
                              ``/api/products/{id}``, ``/api/inventory``.
  * ``search``   (Task 3.7) — ``POST /api/search`` boutique vector search
                              wrapping the C1 ``vector_search`` method.
  * ``workshop``  (Week 1)   — ``POST /api/atelier/query`` + ``/api/atelier/resume``
                               flat replay payloads for the Atelier telemetry surface.
  * ``boutique`` (pre-W3)    — ``GET /api/storefront/briefing`` + ``/pulse``
                               for the homepage ambient agent chrome.
"""

from __future__ import annotations

from .agent import router as agent_router
from .auth import router as auth_router
from .products import router as products_router
from .search import router as search_router
from .boutique import router as boutique_router
from .user import router as user_router
from .workshop import router as workshop_router
from .atelier_observatory import router as atelier_observatory_router

__all__ = [
    "agent_router",
    "atelier_observatory_router",
    "auth_router",
    "products_router",
    "search_router",
    "boutique_router",
    "user_router",
    "workshop_router",
]
