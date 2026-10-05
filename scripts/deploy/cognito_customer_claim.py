"""Cognito pre-token-generation trigger (V2_0): stamp the shopper's customer claim.

Adds ``custom:customer_id`` to the ACCESS token of an authenticated shopper,
read from a server-controlled map keyed by the Cognito username. The Gateway
validates the access token and AgentCore Policy exposes its claims as
principal tags, so a Cedar rule can bind the verified identity to a tool's
``customer_id`` input without naming individual shoppers.

What this deliberately never does:

* read ``clientMetadata`` or any attribute a shopper can write. The only input
  is the username Cognito already authenticated, looked up in a map that
  deployment administration rendered from ``pellier.customers.cognito_username``;
* add a claim for a user the map does not know. A staff account or an
  unmapped user simply has no customer claim, and every claim-scoped Cedar
  rule fails closed on ``principal.hasTag``;
* imply authority. The claim says which customer the principal *is*. Whether
  that customer owns an order, may return it, or may act at all is decided by
  Cedar, the tool, and Aurora, in that order.

Staff carry a different claim, ``custom:staff_scope``, issued only to members of
the operator group and naming a scope rather than a customer. A token with
neither claim is an authenticated stranger: Cedar's permits require one or the
other, so it can call nothing that reads or changes customer data.

V2_0 runs on sign-in and on token refresh, so a refreshed access token carries
the same claim. The user pool must be on the Essentials or Plus feature plan
for access-token customization; ``deploy_customer_claim_trigger.py`` checks.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CLAIM_NAME = "custom:customer_id"
STAFF_CLAIM_NAME = "custom:staff_scope"
STAFF_GROUP_ENV = "STAFF_GROUP"
STAFF_SCOPE_ENV = "STAFF_SCOPE"
MAP_ENV = "CUSTOMER_CLAIM_MAP"
_CUSTOMER_ID = re.compile(r"^CUST-[A-Z0-9-]{1,40}$")
_STAFF_SCOPE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")


def _mapping() -> Dict[str, str]:
    raw = os.environ.get(MAP_ENV, "").strip()
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("%s is not JSON; issuing no customer claims", MAP_ENV)
        return {}
    return {
        str(username).casefold(): str(customer)
        for username, customer in loaded.items()
        if isinstance(username, str) and isinstance(customer, str)
    }


def _staff_scope(request: Dict[str, Any]) -> str:
    """The staff claim, from group membership an administrator assigned.

    ``groupsToOverride`` is the list of groups Cognito found the user in. The
    claim value is a fixed scope name from deployment configuration, so a
    staff token says *what kind* of authority it carries, never a customer.
    """
    group = os.environ.get(STAFF_GROUP_ENV, "").strip()
    scope = os.environ.get(STAFF_SCOPE_ENV, "").strip()
    if not group or not scope or not _STAFF_SCOPE.fullmatch(scope):
        return ""
    groups = (request.get("groupConfiguration") or {}).get("groupsToOverride") or []
    return scope if group in groups else ""


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    request = event.get("request") or {}
    username = str(event.get("userName") or "").strip().casefold()
    claims: Dict[str, str] = {}

    customer_id = _mapping().get(username, "") if username else ""
    if customer_id and _CUSTOMER_ID.fullmatch(customer_id):
        claims[CLAIM_NAME] = customer_id
    elif customer_id:
        logger.error("refusing malformed customer id for user %s", username[:8])

    staff_scope = _staff_scope(request)
    if staff_scope:
        claims[STAFF_CLAIM_NAME] = staff_scope

    response = event.setdefault("response", {})
    if not claims:
        logger.info("no claims for trigger=%s", event.get("triggerSource"))
        return event
    response["claimsAndScopeOverrideDetails"] = {
        "accessTokenGeneration": {"claimsToAddOrOverride": claims},
    }
    logger.info(
        "claims issued trigger=%s claims=%s",
        event.get("triggerSource"),
        sorted(claims),
    )
    return event
