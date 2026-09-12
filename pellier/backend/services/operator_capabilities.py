"""What the Operator can actually do right now, from live governance state.

Why this cannot be a constant
-----------------------------

The obvious implementation reads the local MCP catalog and reports everything as
available. That catalog deliberately includes tools the managed Gateway does not
publish. Live control-plane state remains the only authority for the operator desk.

**The three cases below describe the MIGRATED LIVE Gateway, not a fresh provision.**
That distinction is the whole point of this module and it is easy to lose: on a fresh
stack `initiate_return` DOES have a matching permit, `initiate_return_damaged_only`, so
the first case reads the opposite way there. `issue_credit` is unpublished in both, which
is why only one of the two needs re-reading per environment. Do not treat this list as the
fresh contract; `scripts/describe_workshop_publication.py` prints that.

    initiate_return     published on the Gateway, but the baseline permit was
                        narrowed to 13 unaffected actions, so it has ZERO matching
                        permits and Cedar denies it by default.
    escalate_to_human   same.
    issue_credit        deliberately NOT published: it is a new privileged write
                        whose `deny_issue_credit` policy does not exist here, so
                        the vocabulary migration excluded it.

Those two situations look identical in source and are completely different in
truth. One is a temporary migration boundary that will lift; the other is an absent
capability that needs its own governance review first. A UI that shows both as
"unavailable" with no distinction cannot explain itself, and a UI that shows either
as available lies.

So capability state is derived from the live control plane: which actions the
Gateway publishes, and whether any active permit can match them.

Cost
----

A control-plane read per browser render would be absurd, so results are cached for
``CAPABILITY_TTL_SECONDS``. Capability state changes on the order of a deployment or
a migration phase; client and order data changes far more often. A short TTL is
correct here and a long one would be a stale-governance hazard.

Fail closed
-----------

If live state cannot be determined, writes report ``temporarily_unavailable`` with
reason ``capability_state_unverified``. Reads stay available when their own paths are
healthy. A control-plane error must never resolve to ``available``: that is the one
direction where being wrong hands out a capability nobody authorized.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# States. `review_required` is included because a capability can be live and still
# require a human decision before it executes — that is Pellier's normal path for a
# consequential write, not an error.
AVAILABLE = "available"
REVIEW_REQUIRED = "review_required"
TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
NOT_ENABLED = "not_enabled"

# Reasons, kept coarse on purpose. The browser gets a cause it can phrase; it does
# not get Cedar source, policy ids, engine ids, or AWS configuration.
REASON_PUBLISHED_AND_PERMITTED = "published_and_permitted"
REASON_HUMAN_REVIEW = "human_review_required"
REASON_GOVERNED_UNAVAILABLE = "governed_action_unavailable"
REASON_NOT_PUBLISHED = "capability_not_published"
REASON_UNVERIFIED = "capability_state_unverified"
REASON_MANAGED_RESOURCES_MISSING = "managed_resources_missing"
REASON_LOCAL = "local_read_path"

# Sixty seconds: long enough that a page load never triggers a control-plane call in
# practice, short enough that a migration phase or deploy is reflected within a
# minute without anyone clearing a cache by hand.
CAPABILITY_TTL_SECONDS = 60

# The governed writes the Operator surface can offer. Reads are not listed here:
# they run in-process against Aurora and do not pass through Gateway authorization,
# so their availability is a different question answered by `_read_capabilities`.
GOVERNED_WRITE_TOOLS: Tuple[str, ...] = (
    "initiate_return",
    "escalate_to_human",
    "issue_credit",
    "replace_damaged_item",
)

# Governed writes that additionally require a human decision before execution, via
# the existing review rail. Being in this set does not make a tool available.
REVIEW_GATED_TOOLS: Tuple[str, ...] = ("initiate_return", "issue_credit", "replace_damaged_item")

# Local read paths the Concierge depends on. These do not traverse the Gateway.
READ_CAPABILITIES: Tuple[str, ...] = (
    "client_read",
    "order_read",
    "return_read",
    "ticket_read",
    "catalog_search",
    "inventory_read",
)


@dataclass
class Capability:
    state: str
    reason: str

    def to_payload(self) -> Dict[str, str]:
        return {"state": self.state, "reason": self.reason}


@dataclass
class _CacheEntry:
    payload: Dict[str, Any]
    expires_at: float


_cache: Optional[_CacheEntry] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_cache() -> None:
    """Drop the cached snapshot. For tests and explicit invalidation."""
    global _cache
    _cache = None


def _read_capabilities() -> Dict[str, Capability]:
    return {
        name: Capability(AVAILABLE, REASON_LOCAL) for name in READ_CAPABILITIES
    }


def _unverified_writes(reason: str = REASON_UNVERIFIED) -> Dict[str, Capability]:
    """Fail-closed write states, used whenever live state is unknown."""
    return {
        name: Capability(TEMPORARILY_UNAVAILABLE, reason)
        for name in GOVERNED_WRITE_TOOLS
    }


def _classify(published: List[str], permitted: Dict[str, int]) -> Dict[str, Capability]:
    """Turn live Gateway facts into capability states.

    `published` is the set of tool names the Gateway currently serves for the
    experience target; `permitted` maps a published tool to how many active permit
    policies can match it.
    """
    out: Dict[str, Capability] = {}
    for tool in GOVERNED_WRITE_TOOLS:
        if tool not in published:
            out[tool] = Capability(NOT_ENABLED, REASON_NOT_PUBLISHED)
            continue
        if permitted.get(tool, 0) <= 0:
            # Published but nothing permits it: Cedar denies by default. This is the
            # migration boundary, and it lifts without any code change here.
            out[tool] = Capability(TEMPORARILY_UNAVAILABLE, REASON_GOVERNED_UNAVAILABLE)
            continue
        if tool in REVIEW_GATED_TOOLS:
            out[tool] = Capability(REVIEW_REQUIRED, REASON_HUMAN_REVIEW)
        else:
            out[tool] = Capability(AVAILABLE, REASON_PUBLISHED_AND_PERMITTED)
    return out


def _live_gateway_facts() -> Tuple[List[str], Dict[str, int]]:
    """Published tool names and matching-permit counts, from the control plane.

    Imported lazily and defensively: this module must degrade to fail-closed rather
    than break the Operator console when AgentCore configuration is absent, which is
    the normal case for a local developer.
    """
    from config import settings

    gateway_arn = getattr(settings, "AGENTCORE_GATEWAY_ARN", "") or ""
    engine_id = getattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "") or ""
    if not gateway_arn or not engine_id:
        raise RuntimeError("AgentCore Gateway/policy engine not configured")

    import boto3

    client = boto3.client(
        "bedrock-agentcore-control",
        region_name=settings.aws_region_resolved,
    )
    gateway_id = gateway_arn.rsplit("/", 1)[-1]

    published: List[str] = []
    target_names: List[str] = []
    for item in client.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", []):
        detail = client.get_gateway_target(
            gatewayIdentifier=gateway_id, targetId=item["targetId"]
        )
        schema = (
            detail.get("targetConfiguration", {})
            .get("mcp", {})
            .get("lambda", {})
            .get("toolSchema", {})
            or {}
        )
        names = [t.get("name") for t in (schema.get("inlinePayload") or []) if t.get("name")]
        published.extend(names)
        target_names.extend([detail.get("name", "")] * len(names))

    qualified = {
        name: f"{target}___{name}"
        for name, target in zip(published, target_names)
        if name in GOVERNED_WRITE_TOOLS
    }

    permitted: Dict[str, int] = {name: 0 for name in qualified}
    for policy in client.list_policies(policyEngineId=engine_id).get("policies", []):
        if policy.get("enforcementMode") != "ACTIVE":
            continue
        statement = (policy.get("definition") or {}).get("cedar", {}).get("statement", "")
        flat = " ".join(statement.split())
        if not flat.startswith("permit("):
            continue
        unconstrained = "(principal, action," in flat
        for name, action_id in qualified.items():
            if unconstrained or f'"{action_id}"' in flat:
                permitted[name] += 1

    return published, permitted


def _control_plane_failure_reason(exc: Exception) -> str:
    """Classify only the safe, actionable absence case.

    The browser must never receive a Gateway ARN, policy id, Cedar source, or
    raw AWS exception. A configured resource that no longer exists is still
    materially different from a transient control-plane outage: neither may
    enable a write, but only the former means this environment has not reached
    its managed-action readiness boundary.
    """
    response = getattr(exc, "response", None)
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    code = str(error.get("Code", ""))
    if code == "ResourceNotFoundException" or exc.__class__.__name__ == "ResourceNotFoundException":
        return REASON_MANAGED_RESOURCES_MISSING
    return REASON_UNVERIFIED


def get_capabilities(*, force_refresh: bool = False) -> Dict[str, Any]:
    """The capability snapshot, cached for CAPABILITY_TTL_SECONDS."""
    global _cache
    now = time.monotonic()
    if not force_refresh and _cache is not None and _cache.expires_at > now:
        payload = dict(_cache.payload)
        payload["cached"] = True
        return payload

    capabilities = _read_capabilities()
    try:
        published, permitted = _live_gateway_facts()
        capabilities.update(_classify(published, permitted))
        source = "agentcore"
    except Exception as exc:  # noqa: BLE001 - unknown must not become available
        reason = _control_plane_failure_reason(exc)
        logger.warning(
            "managed capability state unavailable (%s); governed writes "
            "reported temporarily_unavailable with reason %s",
            exc,
            reason,
        )
        capabilities.update(_unverified_writes(reason))
        source = "unverified"

    payload: Dict[str, Any] = {
        "capabilities": {k: v.to_payload() for k, v in sorted(capabilities.items())},
        "observedAt": _now_iso(),
        "source": source,
        "ttlSeconds": CAPABILITY_TTL_SECONDS,
        "governedActionsAvailable": any(
            capabilities[t].state in (AVAILABLE, REVIEW_REQUIRED)
            for t in GOVERNED_WRITE_TOOLS
        ),
        "cached": False,
    }
    _cache = _CacheEntry(payload=dict(payload), expires_at=now + CAPABILITY_TTL_SECONDS)
    return payload
