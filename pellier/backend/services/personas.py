"""The shopper profiles in ``data/personas.json``, the one place a persona names its customer.

The storefront's persona API, the agent tools' reading of a customer the model
named by first name, and the Operator's link to a client's storefront all read
that mapping here, so a persona and its customer cannot drift apart between
them. A persona is a storefront choice, never an identity: who a turn may read
comes from the signed token (``services.turn_identity``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

PERSONAS_FILE = Path(__file__).resolve().parents[3] / "data" / "personas.json"


@lru_cache(maxsize=1)
def persona_profiles() -> tuple[dict[str, Any], ...]:
    """Every shopper profile in the file, in its order."""
    return tuple(json.loads(PERSONAS_FILE.read_text()))


def _customers_by_persona() -> Dict[str, str]:
    return {
        str(profile["id"]): str(profile["customer_id"])
        for profile in persona_profiles()
        if profile.get("customer_id")
    }


def customer_for_persona(persona_id: str) -> Optional[str]:
    """``marco`` -> ``CUST-MARCO``; ``None`` for a persona with no customer."""
    return _customers_by_persona().get(str(persona_id or "").strip().lower())


def persona_for_customer(customer_id: str) -> Optional[str]:
    """``CUST-MARCO`` -> ``marco``; ``None`` for a customer no persona names."""
    wanted = str(customer_id or "").strip().upper()
    return next((persona for persona, customer in _customers_by_persona().items()
                 if customer == wanted), None)
