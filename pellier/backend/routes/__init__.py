"""FastAPI routers for the Pellier backend.

Routers live here so ``app.py`` only wires them up with ``include_router``
rather than declaring every endpoint inline.

  * ``auth`` — ``/api/auth/*`` Cognito Hosted UI sign-in loop.
  * ``user`` — ``/api/user/preferences`` GET/POST protected by Cognito JWT.
  * ``agent`` — ``/api/agent/chat`` SSE stream + session history.
  * ``products`` — editorial and personalized product and inventory APIs.
  * ``search`` — Pellier vector search.
  * ``storefront`` — storefront briefing and pulse APIs.
  * ``operator`` — Pellier Operator client book and governed operator actions.
"""

from __future__ import annotations

from .agent import router as agent_router
from .auth import router as auth_router
from .products import router as products_router
from .search import router as search_router
from .storefront import router as storefront_router
from .user import router as user_router
from .operator import router as operator_router

__all__ = [
    "agent_router",
    "auth_router",
    "products_router",
    "search_router",
    "storefront_router",
    "user_router",
    "operator_router",
]
