#!/usr/bin/env python3
"""Migrate the live Gateway and Cedar policies to the canonical tool vocabulary.

Ownership, and why this module may write
----------------------------------------

The audit in ``scripts/deploy/ownership.py`` established that this deployment has
two ownership models, not one:

    Runtime, Memory, IAM     CloudFormation stack AgentCore-pellier-default
    Gateway, targets, policy created by direct API, in no stack

The CLI cannot adopt the second group: ``import memory`` refuses because the
resource is already in a stack, and ``import gateway`` maps **zero** targets
because their tool schemas are inline. So ``agentcore deploy`` is the wrong tool
here — it would migrate ownership rather than rename tools, and it would put the
Runtime and Memory in the blast radius of a vocabulary change.

The supported path is an in-place update through
``bedrock-agentcore-control``: ``update-gateway-target`` accepts inline tool
schemas, and ``update-policy`` rewrites a Cedar definition while the policy id
stays stable. This module is the only place in the repository permitted to call
them, and ``tests/test_agentcore_deploy_templates.py`` enforces that.

Nothing here touches the Runtime, the Memory, IAM, Cognito, KMS, log retention,
or tags.

What the service actually permits — measured 2026-08-26, not assumed
-------------------------------------------------------------------

The first attempt at this migration widened a policy to name both the retired and
the canonical action id, so that every callable action stayed covered while the
Gateway served both vocabularies. That is impossible here. ``UpdatePolicy`` with
``FAIL_ON_ANY_FINDINGS`` rejected it, and the ``statusReasons`` gave two distinct
reasons that together constrain every possible choreography:

1. ``unrecognized action AgentCore::Action::"…___initiate_return"`` — a policy may
   only name action ids that already exist in the live Gateway schema. So a policy
   can never be widened *ahead* of the Gateway. Policy-first ordering is out.

2. A cascade of ``attribute `input` in context for AgentCore::Action::"Mcp" not
   found``, and the same for ``CallTool``, ``Http``, ``InvokeLLM``,
   ``InvokeAgent``, ``UnknownTool`` and each target-level action. Changing
   ``action ==`` to ``action in [A, B]`` widens the scope the validator
   type-checks the ``when`` clause against, and ``context.input`` does not exist
   for those other action types. So a *conditional* policy must stay pinned to a
   single ``action ==`` id. The two-action set is not merely blocked by (1); it is
   the wrong shape.

Consequence: with the broad ``baseline_permit_gateway_tools`` in place, and with
no new policy permitted, there is no ordering of target and policy updates alone
that keeps every callable sensitive action covered. The Gateway must publish the
new id before a policy can name it, and the moment it does, the baseline permits
it and no forbid covers it. Closing that requires the *permit* layer to stop
covering the target for the duration, which is what the quiesce below does.

3. ``UPDATE_FAILED`` does **not** roll the stored definition back. After the
   rejected call the policy still reported ``enforcementMode=ACTIVE`` and
   ``status=UPDATE_FAILED`` while its stored ``definition`` was the rejected
   statement. Never treat a validation failure as "nothing was written"; restore
   from the capture and diff.

The probe that established all three landed on ``process_return_allow_damaged``,
which is provably redundant under the broad baseline permit, so the effective
control was never in scope. That same redundancy is why it now serves as the
temporary quiesce control.

The one thing the probe did confirm positively: the schema *does* contain
target-level actions. The findings enumerated
``AgentCore::Action::"pellier-concierge-experience-target"`` alongside ``Mcp``,
``CallTool``, ``Http``, ``InvokeLLM``, ``InvokeAgent`` and ``UnknownTool``, and
the validator type-checked the condition against it. A target-level action id is
therefore a real, recognized action in this engine's schema, which is what the
quiesce is built on.

Target-level group membership is compiled at policy-save time — measured
------------------------------------------------------------------------

Phase 1 proved that ``forbid(principal, action in AgentCore::Action::"<target>",
...)`` denies every child tool of that target: ``escalate_to_stylist`` went from
ALLOW to denied, attributed by the service to that policy alone, and no other
policy names it.

Phase 2 then renamed the target's tools while that forbid was ACTIVE, and the
**renamed children were not denied**. Both executed:

    initiate_return    -> allow. Reached the Lambda, refused by Aurora's ownership
                          gate ("Customer CUST-THEO did not order product 1"),
                          recorded in tool_audit 233 and write_operations
                          (idempotency_key p2-canon-initiate-1). Zero domain rows
                          changed.
    escalate_to_human  -> allow. Returned a handoff payload.

The policy was ACTIVE, enforcementMode ACTIVE, statement intact, statusReasons
empty. So membership in the target action group is resolved when the policy is
saved, against the schema as it stands then. A tool added to the target afterwards
is not a member, and the group forbid is silently stale.

Consequences:

1. The quiesce cannot span a schema change. It closes the tools it was compiled
   against, and nothing else.
2. Adding a FORBID can never be made airtight here, because any newly callable
   action is uncovered until a policy naming it is saved, and a policy can only
   name actions that already exist. That circularity now provably includes groups.
3. The airtight lever is the opposite one: withdraw the broad PERMIT. "No permit
   matches" requires no action name, so a tool that appears while the baseline
   does not cover its target is DENY by default, regardless of when any policy was
   compiled.

Phase 2 was rolled back to the retired schema and the quiesce verified denying
again. Do not reinstate the group-forbid-spanning-a-rename design.

A policy write appears to recompile group membership — observed 2026-08-26
-------------------------------------------------------------------------

Differential evidence across three probes of the same two actions, same caller,
same arguments:

    After Phase B (target renamed, no policy written since):
        initiate_return   -> "No policy applies to the request (denied by default)."
        escalate_to_human -> "No policy applies to the request (denied by default)."

    After Phase C (one UpdatePolicy on process_return_damaged_only):
        initiate_return   -> "Policy evaluation denied due to
                              process_return_allow_damaged-dsd0iytknh"
        escalate_to_human -> same

`process_return_allow_damaged` is the target-level group forbid. It was not
modified by Phase C and its statement is byte-identical. Yet it went from matching
neither canonical child to being named as the deciding policy for both.

The only intervening change was a write to a *different* policy in the same engine.
So group membership is not merely resolved at the saving policy's own save time —
a write to any policy in the engine appears to recompile the set, at which point a
target group picks up children added since.

Consequences, stated no more strongly than the evidence supports:

* This does NOT weaken the migration. The boundary is still zero matching permits,
  and permits are unaffected by recompilation.
* It DOES change the Phase D expectation. If the group forbid now covers the
  canonical children, restoring the broad permit will not reopen the target on its
  own — the forbid will still deny everything on it. Phase E, which replaces that
  stale group forbid with the canonical damaged-only permit, becomes load-bearing
  for availability rather than cosmetic cleanup.
* It reinforces why a forbid is not the safety boundary: its coverage changed
  underneath a statement that never changed. A boundary must not depend on when
  something was last compiled.

Do not assume the recompile is deterministic or documented. Verify coverage from
live probes after any policy write, and treat Phase D as "permit restored", not
"target reopened", until a probe proves otherwise.

Three questions, three different answers
---------------------------------------

Phase 1 established live that these are not the same question, and conflating any
two of them produces a false migration proof:

    Control plane   What tools are configured on the target?
                    GetGatewayTarget. Authoritative for what is published, and
                    the only correct basis for a drift check.

    Discovery       What tools may this principal discover?
                    MCP list_tools, and it is POLICY-FILTERED. Under the quiesce
                    the catalog dropped 15 -> 13 while the control-plane schema
                    was untouched. A missing tool here means "not permitted to
                    you", not "not configured".

    Invocation      What happens if this principal attempts the action?
                    A configured-but-denied tool returns a policy denial naming
                    the deciding policy. An unconfigured tool returns an
                    unknown-tool error. That difference is what distinguishes
                    "exists but denied" from "does not exist".

So while the target is quiesced, publication is proved from the control plane and
reachability is proved by invocation. Never from discovery.

MIGRATION SCOPE — a rename, NOT a privilege expansion
-----------------------------------------------------

This cutover is **15 tools to 15 tools**. Do not describe it as 15 to 17.

    VOCABULARY MIGRATION (this pass)
        return target      2 tools -> 2 tools
                           process_return      -> initiate_return
                           escalate_to_stylist -> escalate_to_human
        gateway catalog    15 -> 15 throughout

    CAPABILITY EXPANSION (deferred, separate governance review)
        issue_credit       new privileged write. Requires its own Cedar
                           authorization/deny design before it becomes callable;
                           `render_agentcore_project.py` declares
                           `deny_issue_credit` and this account does not have it.
        get_ticket_history new read.

``gateway_tool_schemas.py`` legitimately describes 17 tools, because that is the
desired state for a *fresh* provision. The live migration is deliberately
narrower. Letting the rename carry the two additions would turn a vocabulary
change into a privilege expansion, which is precisely the failure mode this
repository exists to teach against. ``phase_states()`` refuses it, and
``test_the_plan_adds_no_new_tool_to_the_gateway`` pins it.

MIGRATION SCOPE
---------------

These four phases change the schema of ``pellier-concierge-experience-target``
only. The other three targets continue publishing retired names until their own
approved convergence step. That does not make every retained action equivalent:
``preference_snapshot`` and ``trace_receipt`` dispatch to customer-scoped reads,
so the baseline deliberately omits both legacy ids and their canonical
counterparts. They fail at Cedar before Lambda execution until the recommendation
target and matching scoped policies are converged together. The remaining
unaffected aliases stay in the explicit permit list.

Migration fidelity rule
-----------------------

Preserve every field that is BOTH part of the current target state AND writable
under the current AgentCore API contract.

For a field the service itself now refuses: record the before value, record why it
cannot be resubmitted, omit it from the write, read the target back after
convergence, and record the resulting canonical representation. That is an explicit
**service-normalization delta**, not silent drift, and the drift guard must not
fail merely because a non-round-trippable legacy field disappears.

Safety contract
---------------

* Every run asserts account, region, gateway id, policy engine id, target names
  and policy names before it can write. A mismatch is a hard stop.
* Every run captures full rollback JSON for each resource it intends to change,
  and writes rollback payloads *before* applying anything.
* Captures use owned 0700 directories and exclusive 0600 files. A versioned
  integrity manifest binds the complete capture to the configured deployment.
  Rollback refuses legacy, incomplete, modified or untrusted captures and checks
  current resource identities before any update. Keep the whole run directory.
* ``--plan`` is the default and mutates nothing.
* Applying requires ``--apply`` plus a phase, so no single flag can move the whole
  environment at once.

Usage
-----

Run it with the backend virtualenv interpreter, not the system one. botocore
strips fields its bundled service model does not know, and the system botocore on
this box is old enough that ``UpdatePolicy`` has no ``enforcementMode`` member at
all. Preflight hard-stops on that, but use the right interpreter to begin with:

    PY=pellier/backend/.venv/bin/python

    # Read-only. Writes preflight.json, rollback/, plan.json.
    $PY scripts/migrate_gateway_vocabulary.py

    # Phased apply, each one explicit, each touching exactly one resource:
    # close the door, change the lock, update the rule, open the door.
    $PY scripts/migrate_gateway_vocabulary.py --apply --phase quiesce
    $PY scripts/migrate_gateway_vocabulary.py --apply --phase target-canonical
    $PY scripts/migrate_gateway_vocabulary.py --apply --phase return-forbid-canonical
    $PY scripts/migrate_gateway_vocabulary.py --apply --phase unquiesce

    # Restore from a captured rollback directory.
    $PY scripts/migrate_gateway_vocabulary.py --rollback <dir>
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "deploy"))

from gateway_tool_schemas import TOOL_SCHEMAS, schema_for  # noqa: E402
from ownership import (  # noqa: E402
    EXPECTED_ACCOUNT,
    EXPECTED_DB_CLUSTER,
    EXPECTED_EXPERIENCE_LAMBDA,
    EXPECTED_EXPERIENCE_SHA,
    EXPECTED_GATEWAY_ID,
    EXPECTED_POLICY_ENGINE_ID,
    EXPECTED_POLICY_NAMES,
    EXPECTED_REGION,
    EXPECTED_TARGET_NAMES,
    CFN_STACK,
    PreflightResult,
    require_environment_pins,
)


def policy_statement(policy: Dict[str, Any]) -> str:
    """Read current AgentCore definitions and older saved migration captures."""
    definition = policy.get("definition") or {}
    body = definition.get("policy") or definition.get("cedar") or {}
    value = body.get("statement")
    return value if isinstance(value, str) else ""


# The rename, as one map. Retired names appear here and in the Lambda's
# migration-only dispatch alias, and nowhere else in the runtime.
RETIRED_TO_CURRENT: Dict[str, str] = {
    "floor_check": "check_inventory",
    "running_low": "get_low_stock",
    "restock_shelf": "restock_inventory",
    "process_return": "initiate_return",
    "find_pieces": "search_products",
    "find_pieces_hybrid": "search_products_hybrid",
    "whats_trending": "get_trending_products",
    "price_intelligence": "get_price_analysis",
    "explore_collection": "browse_category",
    "side_by_side": "compare_products",
    "returns_and_care": "get_return_policy",
    "style_match": "get_related_products",
    "preference_snapshot": "get_customer_preferences",
    "trace_receipt": "get_audit_trail",
    "escalate_to_stylist": "escalate_to_human",
}

# Quiesced target cutover:  close the door, change the lock, update the rule,
# open the door.
#
# Both earlier designs are abandoned and deleted rather than left behind:
#   * gateway-first bridge     — left a callable action outside the forbid
#   * policy-first widening    — rejected, a policy cannot name a future action
#   * two-action Cedar sets    — rejected, `action in [A, B]` broadens the
#                                validator's context type-check and fails
#
# WARNING: THE PREMISE BELOW WAS DISPROVED LIVE ON 2026-08-26. See
# "Target-level group membership is compiled at policy-save time" in the module
# docstring. A target-level forbid does NOT extend to child tools created after
# the policy was saved, so `target-canonical` reopened the target and had to be
# rolled back. These phases are retained only because Phase 1 (quiesce) is still
# a valid and proven step; the cutover needs a different Phase 2 onward, based on
# withdrawing the broad PERMIT rather than adding a group FORBID.
# Default-deny quiesce. Safety comes from withdrawing PERMISSION, never from
# adding a forbid:
#
#   A  default-deny-quiesce   baseline permit -> the 11 non-sensitive unaffected
#                             actions only.
#                             The experience target has no matching permit, so
#                             every child action is DENY by default, old name or
#                             new, named by a policy or not.
#   B  target-canonical       rename 2 -> 2 while nothing permits the target.
#   C  return-forbid-canonical repoint the restrictive forbid to the canonical id.
#   D  allow-damaged-canonical THE DAMAGED-RETURN REOPEN. Replace the stale
#                             target-group forbid with the canonical damaged-only
#                             permit it was originally. While the baseline stays
#                             narrowed this is the ONLY matching permit, so exactly
#                             one business path opens: damaged initiate_return.
#   E  explicit-baseline-final THE FINAL AUTHORIZATION. Baseline 11 -> 12 explicit
#                             actions, adding only escalate_to_human. The return action
#                             stays governed by its dedicated permit/forbid pair, the
#                             customer-scoped read aliases remain default-denied, and a
#                             future published tool gets NO matching permit.
#
#   F  restore-broad-permit  FALLBACK ONLY. Restores the historical wildcard. Requires
#                             --allow-wildcard-baseline, because a wildcard authorizes
#                             any action published afterwards — the property that made
#                             the migration window unsafe in the first place.
#
# D before E, and not the other way round. The original order assumed E was cosmetic
# cleanup after the reopen. The recompilation finding below killed that: the stale
# group forbid began matching the canonical children, so restoring the broad permit
# first would have left the target closed while looking like a successful unquiesce,
# with availability resting on an undocumented group-compilation behaviour. Doing D
# first also makes the reopen a far smaller surface — one action with one condition
# instead of the whole target.
#
# Why not a forbid: measured on 2026-08-26, a policy cannot name an action that
# does not exist yet, AND target action-group membership is compiled at
# policy-save time so it does not follow a schema change. Both forbid-based
# designs failed live. "No permit matches" needs no action name and no compiled
# membership, which is why it is the only boundary that survives a rename.
PHASES = (
    "default-deny-quiesce",
    "target-canonical",
    "return-forbid-canonical",
    "allow-damaged-canonical",
    "explicit-baseline-final",
    "restore-broad-permit",
)

# The wildcard restore is retained for rollback and reference, never as the default
# end state. Applying it needs an explicit flag: "historical" is not "desirable".
WILDCARD_PHASE = "restore-broad-permit"

BASELINE_POLICY_NAME = "baseline_permit_gateway_tools"

# The one target that publishes policy-governed writes, so the only one whose
# cutover needs the quiesce. See MIGRATION SCOPE in the module docstring for the
# other three, which no policy references.
RETURN_TARGET_NAME = "pellier-concierge-experience-target"
RECOMMENDATION_TARGET_NAME = "pellier-curation-recommendation-target"

# The existing engineering recommendation target still exposes these retired
# aliases. Both ultimately use an attacker-supplied customer_id to read customer
# facts, and the legacy policy engine has no action-specific scope policy for
# them. Keep both spellings absent from every migrated baseline so Cedar denies
# before the Lambda sees a caller-selected customer.
CUSTOMER_SCOPED_READ_TOOL_NAMES = frozenset(
    {
        "preference_snapshot",
        "trace_receipt",
        "get_customer_preferences",
        "get_audit_trail",
    }
)

# The policy whose steady-state definition contributes nothing under the broad
# baseline permit, and which therefore serves as the temporary quiesce control.
# Its NAME is historical and stays that way: policy identity carries the audit
# history, and renaming would mean delete plus create.
QUIESCE_POLICY_NAME = "process_return_allow_damaged"

# The shape process_return_allow_damaged held before the abandoned design
# repurposed it, so its canonical end state is this with the action renamed.
def permit_template() -> str:
    """The shape `process_return_allow_damaged` held before it was repurposed.

    Its canonical end state is this with the action id renamed, which is why the
    cleanup phase rewrites rather than restores: the retired action will not exist.
    """
    # One f-string, not three concatenated literals. The previous form ended with a
    # PLAIN literal containing `}}`, and brace-escaping applies per literal — so the
    # template rendered `... "damaged" }};` with a doubled closing brace. A dry run
    # printed it before any write; Cedar would have rejected it.
    return (
        f'permit(principal, action == AgentCore::Action::'
        f'"{RETURN_TARGET_NAME}___process_return", '
        f'{gateway_resource()})\n'
        f'when {{\n  context.input has reason && '
        f'context.input.reason == "damaged"\n}};'
    )

# The policy that carries the actual restrictive control.
CONTROL_POLICY_NAME = "process_return_damaged_only"

# What each policy-writing phase must produce, checked structurally on the apply path.
# `None` means "not constrained here" — the broad permit names no action at all, so a
# cardinality of zero would be wrong and a number would be wronger.
_EXPECTED_EFFECT = {
    "default-deny-quiesce": "permit",
    "return-forbid-canonical": "forbid",
    "allow-damaged-canonical": "permit",
    "restore-broad-permit": "permit",
}
_EXPECTED_ACTION_CARDINALITY = {
    "return-forbid-canonical": 1,
    "allow-damaged-canonical": 1,
}

# The governed write actions on the return target, in canonical vocabulary. A
# callable tool in this set must be covered by a restrictive forbid in every
# phase, or the per-phase proof fails and the run refuses to apply.
GOVERNED_WRITE_TOOLS = ("initiate_return", "issue_credit")

# Gateway-reserved policy-session headers. These must not be configured for
# propagation to the target, and UpdateGatewayTarget rejects them:
#
#   ValidationException: Header 'x-amzn-bedrock-agentcore-policy-session-id' is
#   restricted and cannot be configured
#
# The distinction that matters, and the wording to keep:
#
#   POLICY SESSION            client -> x-amzn-...-policy-session-id -> Gateway
#                             -> Policy evaluation.  A CALLER may still supply
#                             this header to the Gateway; it is not "managed by
#                             AWS" and Pellier does not own less of it than
#                             before.
#
#   TARGET PROPAGATION        client -> Gateway -> allowedRequestHeaders
#                             -> target backend.  This is what
#                             `metadataConfiguration` configures, and X-Amzn-*
#                             headers are reserved from it.
#
# So the header is NOT service-managed. What is reserved is configuring it for
# passthrough to the target. All four targets were created on 2026-08-01 carrying
# it in `allowedRequestHeaders`, which the current API contract no longer accepts:
# legacy, non-round-trippable control-plane state rather than canonical target
# configuration. Nothing in Pellier reads that header at the Lambda, and Cedar
# evaluates without it — proved by the Phase 1 denials, which came from a probe
# sending only Authorization.
RESTRICTED_REQUEST_HEADERS = ("x-amzn-bedrock-agentcore-policy-session-id",)

# This migration is a RENAME, and only a rename. The canonical schema for the
# return target also introduces two tools that are not on the live Gateway at
# all:
#
#   issue_credit        new. `scripts/deploy/render_agentcore_project.py` declares
#                       an unconditional `deny_issue_credit` forbid for it, and
#                       tests/test_managed_policy.py and
#                       tests/test_agentcore_deploy_templates.py both assert that
#                       policy exists. It is NOT on this account: the live engine
#                       carries three hand-made policies, not the provisioner's
#                       set. Publishing issue_credit here would make a
#                       money-moving tool reachable through the managed rail with
#                       nothing but the broad baseline permit in front of it.
#   get_ticket_history  new, and a read, so no restrictive control is implied.
#
# Adding a capability is a different decision from renaming one, and creating
# `deny_issue_credit` needs `create_policy`, which this pass explicitly forbids.
# So the target cutover carries the rename only, and both additions are deferred
# to their own approval. `phase_states()` is what caught this: with the full
# canonical set, the unquiesce row reported issue_credit callable, permitted, and
# covered by no forbid.
DEFERRED_NEW_TOOLS = ("issue_credit", "get_ticket_history", "replace_damaged_item")
# Two different enums that both contain the token "ACTIVE", which is exactly why
# they must never be read from one variable:
#   Policy.status          CREATING | ACTIVE | UPDATING | DELETING | *_FAILED
#   Policy.enforcementMode ACTIVE | LOG_ONLY
# `status=ACTIVE` means the policy is healthy. `enforcementMode=ACTIVE` means it
# is enforcing rather than merely logging. Both live policies happen to be ACTIVE
# on both fields, so a conflation here would produce correct behaviour today and
# silently wrong behaviour the first time a policy is LOG_ONLY on purpose.
ENFORCEMENT_MODES = {"ACTIVE", "LOG_ONLY"}
LIFECYCLE_TERMINAL_OK = {"ACTIVE", "READY"}

TERMINAL_OK = LIFECYCLE_TERMINAL_OK
# Terminal failure states. UPDATE_FAILED was missing here, so the live probe on
# 2026-08-26 sat in `_wait_policy` for the full 300-second timeout before
# reporting a status the service had already settled on. A poll loop that does not
# recognise the failure it is waiting for is indistinguishable from a hang.
TERMINAL_BAD = {
    "FAILED",
    "UPDATE_FAILED",
    "UPDATE_UNSUCCESSFUL",
    "CREATE_FAILED",
    "DELETE_FAILED",
}


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def _load_env() -> None:
    for env_path in (REPO / ".env", REPO / "pellier" / "backend" / ".env"):
        if not env_path.is_file():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _clients() -> Tuple[Any, Any, Any, Any]:
    import boto3

    region = os.environ.get("AWS_REGION") or EXPECTED_REGION
    return (
        boto3.client("bedrock-agentcore-control", region_name=region),
        boto3.client("sts", region_name=region),
        boto3.client("lambda", region_name=region),
        boto3.client("cloudformation", region_name=region),
    )


# ---------------------------------------------------------------------------
# Canonical desired schemas, derived from the single source
# ---------------------------------------------------------------------------


def canonical_targets() -> Dict[str, List[Dict[str, Any]]]:
    """target name -> full inline tool schema, from `gateway_tool_schemas.py`.

    Derived, never hand-maintained: a second list would drift from the one the
    provisioner uses, and Cedar action ids embed the target name.
    """
    return {
        config["target_name"]: schema_for(surface, workshop=False)
        for surface, config in TOOL_SCHEMAS.items()
    }


def validate_canonical() -> Dict[str, Any]:
    """Assert the canonical vocabulary is internally sound before comparing it.

    Checks the properties that actually matter rather than a tool count: names are
    unique, each resolves to exactly one target, and no retired name survives.
    """
    targets = canonical_targets()
    names: List[str] = []
    target_of: Dict[str, str] = {}
    for target, tools in targets.items():
        for tool in tools:
            names.append(tool["name"])
            if tool["name"] in target_of:
                raise SystemExit(
                    f"tool {tool['name']} is published by two targets: "
                    f"{target_of[tool['name']]} and {target}"
                )
            target_of[tool["name"]] = target

    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise SystemExit(f"canonical schema has duplicate tool names: {duplicates}")

    retired = sorted(set(names) & set(RETIRED_TO_CURRENT))
    if retired:
        raise SystemExit(f"canonical schema still publishes retired names: {retired}")

    missing_targets = sorted(set(targets) - set(EXPECTED_TARGET_NAMES))
    if missing_targets:
        raise SystemExit(f"canonical schema names unknown targets: {missing_targets}")

    return {
        "toolCount": len(names),
        "tools": sorted(names),
        "targetForTool": target_of,
        "targets": {t: sorted(x["name"] for x in v) for t, v in targets.items()},
    }


# ---------------------------------------------------------------------------
# Live state
# ---------------------------------------------------------------------------


def read_live(control: Any) -> Dict[str, Any]:
    """Everything this migration compares against or would need to restore."""
    gateway = control.get_gateway(gatewayIdentifier=EXPECTED_GATEWAY_ID)
    targets: List[Dict[str, Any]] = []
    for summary in control.list_gateway_targets(
        gatewayIdentifier=EXPECTED_GATEWAY_ID
    ).get("items", []):
        detail = control.get_gateway_target(
            gatewayIdentifier=EXPECTED_GATEWAY_ID, targetId=summary["targetId"]
        )
        detail.pop("ResponseMetadata", None)
        targets.append(detail)

    policies: List[Dict[str, Any]] = []
    for summary in control.list_policies(
        policyEngineId=EXPECTED_POLICY_ENGINE_ID
    ).get("policies", []):
        detail = control.get_policy(
            policyEngineId=EXPECTED_POLICY_ENGINE_ID, policyId=summary["policyId"]
        )
        detail.pop("ResponseMetadata", None)
        policies.append(detail)

    gateway.pop("ResponseMetadata", None)
    return {"gateway": gateway, "targets": targets, "policies": policies}


def _tool_names(target: Dict[str, Any]) -> List[str]:
    schema = (
        target.get("targetConfiguration", {})
        .get("mcp", {})
        .get("lambda", {})
        .get("toolSchema", {})
        or {}
    )
    return [t.get("name") for t in (schema.get("inlinePayload") or [])]


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def preflight(control: Any, sts: Any, lam: Any, cfn: Any, live: Dict[str, Any]) -> PreflightResult:
    """Assert the environment is exactly the one this migration was written for."""
    # Before comparing anything: the pins themselves must be set. They live in the
    # environment rather than in tracked source because they identify one published
    # account's resources, and an unset pin would make every comparison below a
    # match against an empty string.
    require_environment_pins()
    result = PreflightResult(ok=True)
    ident = sts.get_caller_identity()
    result.record("account", ident["Account"], EXPECTED_ACCOUNT)
    result.record("region", os.environ.get("AWS_REGION") or EXPECTED_REGION, EXPECTED_REGION)
    result.record(
        "gatewayId", live["gateway"].get("gatewayId") or EXPECTED_GATEWAY_ID, EXPECTED_GATEWAY_ID
    )
    result.record("policyEngineId", EXPECTED_POLICY_ENGINE_ID, EXPECTED_POLICY_ENGINE_ID)
    result.record(
        "targetNames",
        sorted(t.get("name") for t in live["targets"]),
        sorted(EXPECTED_TARGET_NAMES),
    )
    result.record(
        "policyNames",
        sorted(p.get("name") for p in live["policies"]),
        sorted(EXPECTED_POLICY_NAMES),
    )
    result.record(
        "targetStatuses",
        sorted({t.get("status") for t in live["targets"]}),
        ["READY"],
    )

    # The Lambda that serves the renamed tool must be the Phase B1 build, or the
    # migration would rename tools onto an implementation that cannot serve them.
    try:
        cfg = lam.get_function_configuration(FunctionName=EXPECTED_EXPERIENCE_LAMBDA)
        result.record("experienceLambdaSha", cfg["CodeSha256"], EXPECTED_EXPERIENCE_SHA)
    except Exception as exc:  # noqa: BLE001
        result.record("experienceLambdaSha", f"unreadable: {type(exc).__name__}", EXPECTED_EXPERIENCE_SHA)

    # Runtime and Memory must be exactly as the stack left them. This migration
    # never touches them; the assertion proves it started from an untouched state.
    try:
        stack = cfn.describe_stacks(StackName=CFN_STACK)["Stacks"][0]
        result.record("cfnStackStatus", stack["StackStatus"], "UPDATE_COMPLETE")
        resources = cfn.describe_stack_resources(StackName=CFN_STACK)["StackResources"]
        result.record(
            "cfnOwnedAgentCoreResources",
            sorted(
                r["ResourceType"] for r in resources if "BedrockAgentCore" in r["ResourceType"]
            ),
            ["AWS::BedrockAgentCore::Memory", "AWS::BedrockAgentCore::Runtime"],
        )
    except Exception as exc:  # noqa: BLE001
        result.record("cfnStackStatus", f"unreadable: {type(exc).__name__}", "UPDATE_COMPLETE")

    db_host = os.environ.get("DB_HOST", "")
    result.record("auroraCluster", db_host.split(".")[0] if db_host else "", EXPECTED_DB_CLUSTER)
    _record_service_model(result)
    return result


def _record_service_model(result: PreflightResult) -> None:
    """Assert botocore is new enough to see the fields this migration preserves.

    This is not defensive boilerplate. botocore parses and serializes strictly
    against its bundled service model, so an interpreter with an older botocore
    silently drops fields it does not know — in both directions. Measured on this
    box:

        botocore 1.43.28  UpdatePolicy input: definition, description,
                          policyEngineId, policyId, validationMode
        botocore 1.43.51  ... the same plus enforcementMode

    Under 1.43.28 the rollback capture loses ``enforcementMode`` (observed: the
    field is absent from every captured policy while the API returns it), and far
    worse, ``update_policy`` would be sent with no ``enforcementMode`` at all. The
    service would then apply its own default and all three policies could come
    back not ACTIVE — enforcement quietly switched off by a rename, with a
    successful API response and nothing in the diff to show it.

    So a too-old botocore is a hard stop, not a warning.
    """
    try:
        import botocore
        import botocore.session

        model = botocore.session.get_session().get_service_model(
            "bedrock-agentcore-control"
        )
        update_in = set(model.operation_model("UpdatePolicy").input_shape.members)
        get_out = set(model.operation_model("GetPolicy").output_shape.members)
        result.checks["botocoreVersion"] = {
            "observed": botocore.__version__,
            "expected": "any version whose service model has the members below",
            "ok": True,
        }
        result.record(
            "updatePolicyAcceptsEnforcementMode", "enforcementMode" in update_in, True
        )
        result.record(
            "getPolicyReturnsEnforcementMode", "enforcementMode" in get_out, True
        )
    except Exception as exc:  # noqa: BLE001
        result.record(
            "serviceModelReadable", f"unreadable: {type(exc).__name__}", True
        )


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def rewrite_actions(statement: str, *, to_canonical: bool) -> Tuple[str, List[str]]:
    """Rewrite target-qualified Cedar action ids, reporting each change.

    Only the fully qualified ``<target>___<tool>`` form is rewritten. A bare
    substring swap would also edit prose in a description or a comment.
    """
    out = statement
    changes: List[str] = []
    pairs = RETIRED_TO_CURRENT.items() if to_canonical else []
    for retired, current in pairs:
        for target in EXPECTED_TARGET_NAMES:
            old = f"{target}___{retired}"
            new = f"{target}___{current}"
            if old in out:
                out = out.replace(old, new)
                changes.append(f"{old} -> {new}")
    return out, changes


def gateway_resource() -> str:
    """The resource clause, taken from the live policies rather than rebuilt.

    The gateway ARN is account-specific. Reading it out of a definition that the
    service already accepted removes any chance of assembling a near-miss ARN
    that validates as an unrecognized resource.

    The pins are re-checked here rather than trusted from preflight. An ARN with an
    empty account or gateway segment is still a syntactically plausible string, and a
    Cedar statement carrying one would name a resource that matches nothing: a policy
    that authorizes nothing reads exactly like a policy that is working.
    """
    require_environment_pins()
    return (
        'resource == AgentCore::Gateway::'
        f'"arn:aws:bedrock-agentcore:{EXPECTED_REGION}:{EXPECTED_ACCOUNT}:'
        f'gateway/{EXPECTED_GATEWAY_ID}"'
    )


def broad_baseline_statement() -> str:
    """The ORIGINAL broad baseline permit: any action on this gateway.

    Not read from live state, and that is the point. `build_plan` re-derives from
    whatever is currently deployed, so once the quiesce had landed the "restore"
    phase was computing ``after`` = the live NARROWED statement — restoring the
    quiesce onto itself. The per-phase proof caught it: `escalate_to_human` stayed
    DENY after the phase whose whole purpose is to permit it again.

    Verified against the pre-migration capture on 2026-08-27, which recorded
    ``permit(principal, action, resource == AgentCore::Gateway::"<arn>");`` as the
    definition in force before Phase A. `assert_broad_baseline_matches_capture`
    re-checks that whenever a capture directory is available.
    """
    return f'permit(principal, action, {gateway_resource()});'


class CaptureError(SystemExit):
    """A capture cannot safely authorize a migration or rollback."""


_CAPTURE_FILES = {
    "preflight.json": "run",
    "plan.json": "run",
    "phase-proof.json": "run",
    "live.json": "rollback",
    "canonical.json": "rollback",
}
_CAPTURE_LIMIT = 16 * 1024 * 1024
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _capture_scope() -> Dict[str, str]:
    require_environment_pins()
    return {
        "account": EXPECTED_ACCOUNT,
        "region": EXPECTED_REGION,
        "gatewayId": EXPECTED_GATEWAY_ID,
        "policyEngineId": EXPECTED_POLICY_ENGINE_ID,
    }


@contextmanager
def _private_directory_at(parent_fd: int, name: str, *, create: bool = False):
    if not name or Path(name).name != name or name in {".", ".."}:
        raise CaptureError("Unsafe capture directory name.")
    try:
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
        fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise CaptureError("Capture directories must be owned by this user and mode 0700.")
            yield fd
        finally:
            os.close(fd)
    except OSError:
        raise CaptureError("Cannot safely open a capture directory; symlinks are refused.") from None


@contextmanager
def _private_directory(path: Path, *, create: bool = False):
    absolute = path.absolute()
    if ".." in absolute.parts:
        raise CaptureError("Capture paths must not contain parent-directory traversal.")
    # macOS's root-owned /tmp and /var aliases are OS paths. Caller-controlled
    # symlinks in every remaining component are rejected by descriptor traversal.
    for alias in (Path("/tmp"), Path("/var")):
        if absolute.is_relative_to(alias) and alias.is_symlink():
            if alias.lstat().st_uid != 0:
                raise CaptureError("Untrusted temporary-directory alias.")
            absolute = alias.resolve(strict=True) / absolute.relative_to(alias)
    try:
        with ExitStack() as stack:
            fd = os.open(absolute.anchor, _DIRECTORY_FLAGS)
            stack.callback(os.close, fd)
            for part in absolute.parts[1:-1]:
                fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
                stack.callback(os.close, fd)
            with _private_directory_at(fd, absolute.name, create=create) as directory_fd:
                yield directory_fd
    except OSError:
        raise CaptureError("Capture path is unavailable or contains a symlink.") from None


def _write_capture_json(directory_fd: int, name: str, value: Any) -> Dict[str, Any]:
    if Path(name).name != name or name in {"", ".", ".."}:
        raise CaptureError("Unsafe capture filename.")
    data = (json.dumps(value, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    if len(data) > _CAPTURE_LIMIT:
        raise CaptureError("Capture is too large; no complete snapshot was saved.")
    try:
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd,
        )
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    except OSError:
        raise CaptureError("Capture write failed; existing paths and partial evidence are retained.") from None
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _read_capture_bytes(directory_fd: int, name: str) -> bytes:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1
                or before.st_size > _CAPTURE_LIMIT
            ):
                raise CaptureError("Capture files must be owned regular 0600 files with one link.")
            data = stream.read(_CAPTURE_LIMIT + 1)
            after = os.fstat(stream.fileno())
            if (
                len(data) != before.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
                or before.st_size != after.st_size
            ):
                raise CaptureError("Capture changed while being read.")
            return data
    except OSError:
        raise CaptureError("Capture file is missing or unsafe; symlinks are refused.") from None


def _capture_run(
    root: Path, pre: PreflightResult, plan: Dict[str, Any],
    live: Dict[str, Any], canonical: Dict[str, Any],
) -> Path:
    """Publish a fresh private capture; the manifest is written last.

    Hashes detect corruption or replacement, not a compromise of the owning OS
    user. Directory ownership and permissions establish that local trust boundary.
    Failed writes keep their evidence but never produce an accepted partial run.
    """
    scope = _capture_scope()
    name = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex
    with _private_directory(root, create=True) as root_fd:
        try:
            # Never reuse even an owned timestamp directory from another run.
            os.mkdir(name, 0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError:
            raise CaptureError("Cannot create a fresh capture directory; no existing run was reused.") from None
        with _private_directory_at(root_fd, name) as run_fd:
            with _private_directory_at(run_fd, "rollback", create=True) as rollback_fd:
                values = {
                    "preflight.json": pre.checks,
                    "plan.json": plan,
                    "phase-proof.json": phase_states(plan),
                    "live.json": live,
                    "canonical.json": canonical,
                }
                files = {
                    filename: _write_capture_json(
                        run_fd if location == "run" else rollback_fd,
                        filename, values[filename],
                    )
                    for filename, location in _CAPTURE_FILES.items()
                }
                _write_capture_json(rollback_fd, "manifest.json", {
                    "version": 1, "scope": scope,
                    "preflightPassed": pre.ok, "files": files,
                })
    return root / name


def _load_capture(directory: Path) -> Dict[str, Any]:
    """Read and verify the whole run before consuming any rollback payload."""
    if directory.name != "rollback":
        raise CaptureError("Use the rollback directory inside a complete captured run.")
    scope = _capture_scope()
    try:
        with _private_directory(directory.parent.parent) as root_fd:
            with _private_directory_at(root_fd, directory.parent.name) as run_fd:
                with _private_directory_at(run_fd, "rollback") as rollback_fd:
                    manifest = json.loads(_read_capture_bytes(rollback_fd, "manifest.json"))
                    if (
                        not isinstance(manifest, dict)
                        or type(manifest.get("version")) is not int
                        or manifest["version"] != 1
                        or manifest.get("scope") != scope
                        or manifest.get("preflightPassed") is not True
                        or not isinstance(manifest.get("files"), dict)
                        or set(manifest["files"]) != set(_CAPTURE_FILES)
                    ):
                        raise CaptureError("Capture manifest is incomplete, unapproved or outside the pinned scope.")
                    payloads = {}
                    for name, location in _CAPTURE_FILES.items():
                        data = _read_capture_bytes(
                            run_fd if location == "run" else rollback_fd, name,
                        )
                        expected = manifest["files"][name]
                        if expected != {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}:
                            raise CaptureError("Capture integrity check failed; no payload will be applied.")
                        payloads[name] = json.loads(data)
        live = payloads["live.json"]
        if not isinstance(live, dict):
            raise CaptureError("Capture does not contain a live resource snapshot.")
        return live
    except (ValueError, TypeError):
        raise CaptureError("Capture JSON is malformed or incomplete.") from None


def assert_broad_baseline_matches_capture(directory: Path) -> None:
    """Cross-check the derived broad permit against a pre-migration capture.

    An absent run is advisory because captures live outside the repository.
    An existing but untrusted/incomplete run, or a baseline that disagrees, is a
    hard stop. Historical captures without an integrity manifest need independent
    reconciliation; changing their permissions alone does not establish trust.
    """
    if not os.path.lexists(directory):
        return
    payload = _load_capture(directory / "rollback")
    for policy in payload.get("policies") or []:
        if policy.get("name") != BASELINE_POLICY_NAME:
            continue
        captured = policy_statement(policy)
        if not captured:
            return
        parsed = parse_statement(BASELINE_POLICY_NAME, captured)
        if parsed.actions is None and _norm(captured) == _norm(broad_baseline_statement()):
            return
        if parsed.actions is None:
            # Broad, but not byte-identical after normalisation. Prefer the capture:
            # it is what the service actually accepted.
            raise SystemExit(
                "the captured original baseline is broad but does not match the "
                f"derived statement.\n  captured: {_norm(captured)}\n  derived : "
                f"{_norm(broad_baseline_statement())}\nSTOP and reconcile."
            )
        return


def unaffected_action_ids(live: Dict[str, Any]) -> List[str]:
    """Every live action id the migration may safely retain in its baseline.

    Derived from the control-plane snapshot, never hand-maintained: a stale list
    would either permit something it should not or black-hole a target that is not
    part of this migration. Customer-scoped reads are the exception: until their
    target schema and scoped Cedar constraints converge together, no spelling of
    either action may inherit the broad legacy permit.
    """
    out: List[str] = []
    for target in live["targets"]:
        name = target.get("name")
        if name == RETURN_TARGET_NAME:
            continue
        for tool in _tool_names(target):
            if (
                name == RECOMMENDATION_TARGET_NAME
                and tool in CUSTOMER_SCOPED_READ_TOOL_NAMES
            ):
                continue
            if tool:
                out.append(f"{name}___{tool}")
    return sorted(out)


def narrowed_baseline_statement(live: Dict[str, Any]) -> str:
    """The temporary baseline permit: an explicit list of unaffected actions.

    Explicit action ids rather than ``action in AgentCore::Action::"<target>"``
    even though those three targets are not changing. Target-group membership was
    just measured to have non-obvious compilation behaviour, and a migration
    safety boundary must not rest on it. An explicit list is also diffable, which
    matters when the property being asserted is "these and nothing else".

    Unconditional: no ``when``, no ``unless``, no ``context.input``. A condition
    would be type-checked against every action in scope and would fail the way the
    two-action set did. Customer-scoped reads are intentionally absent, even on
    the untouched recommendation target: the existing migration policy engine
    cannot bind their caller-provided customer_id safely.
    """
    ids = unaffected_action_ids(live)
    if not ids:
        raise SystemExit("refusing to build a baseline permit that permits nothing")
    leaked = [a for a in ids if a.startswith(f"{RETURN_TARGET_NAME}___")]
    if leaked:
        raise SystemExit(
            f"the narrowed baseline permit would still cover {leaked}; the whole "
            "point is that it covers no experience-target action"
        )
    members = ",\n        ".join(f'AgentCore::Action::"{a}"' for a in ids)
    return (
        "permit(\n    principal,\n    action in [\n        "
        f"{members}\n    ],\n    {gateway_resource()}\n);"
    )


# The canonical experience action that the FINAL baseline permits explicitly. The
# return action is deliberately absent: it is governed by its own dedicated permit and
# forbid pair, so the baseline never has to reason about a condition.
FINAL_BASELINE_EXTRA_TOOL = "escalate_to_human"


def final_baseline_statement(live: Dict[str, Any]) -> str:
    """The FINAL baseline permit: non-sensitive actions plus escalation.

    This replaces the historical wildcard ``permit(principal, action, resource == gw)``
    as the end state, and the reason is the whole lesson of this migration: a wildcard
    means any newly published Gateway action acquires a matching permit the moment it
    appears. That is exactly what created the unsafe window when ``initiate_return``
    was first published, and it would silently authorize a future ``issue_credit`` or
    ``get_ticket_history`` on publication alone.

    With an explicit list, publication and authorization stay separate decisions:

        11 non-sensitive actions explicit permit here
        escalate_to_human       explicit permit here
        initiate_return         dedicated permit (damaged) + dedicated forbid (other)
        customer reads          default DENY pending scoped policy convergence
        anything published next  no matching permit -> DENY by default

    Measured before choosing this shape (2026-08-27): policy-filtered MCP
    ``list_tools`` returned 14 tools under the partial-reopen surface and
    ``initiate_return`` WAS discoverable under its conditional damaged-only permit. So
    a conditional permit does not hide a tool from discovery, and the baseline does not
    need to name the return action to keep it callable.

    ``broad_baseline_statement`` is retained for rollback and reference. It is a
    fallback, not the default, and applying it requires an explicit CLI flag.
    """
    ids = unaffected_action_ids(live)
    if not ids:
        raise SystemExit("refusing to build a baseline permit that permits nothing")
    escalation = f"{RETURN_TARGET_NAME}___{FINAL_BASELINE_EXTRA_TOOL}"
    live_experience = {
        f"{RETURN_TARGET_NAME}___{tool}"
        for target in live["targets"] if target.get("name") == RETURN_TARGET_NAME
        for tool in _tool_names(target) if tool
    }
    if escalation not in live_experience:
        raise SystemExit(
            f"refusing to build the final baseline: {escalation} is not published on "
            f"the live target (found {sorted(live_experience)})"
        )
    ids = sorted(ids + [escalation])

    # The return action must NOT appear here. It is governed by the dedicated pair, and
    # naming it in an unconditional permit would make the damaged-only condition
    # decorative — the forbid would still deny non-damaged, but the permit would no
    # longer express that returns are conditionally authorized.
    retained = f"{RETURN_TARGET_NAME}___{RETIRED_TO_CURRENT['process_return']}"
    if retained in ids:
        raise SystemExit(
            f"the final baseline must not name {retained}; it is governed by "
            f"{QUIESCE_POLICY_NAME} and {CONTROL_POLICY_NAME}"
        )
    # Retired names only matter on the RETURN target. `RETIRED_TO_CURRENT` is the full
    # 15-tool vocabulary map, but only the experience target's two were migrated — the
    # other three targets deliberately still publish their historical names
    # (`floor_check`, `running_low`, …) and those are live, permitted actions. Scoping
    # this to the return target is the difference between the invariant and a guard that
    # rejects unrelated retained actions.
    for retired in RETIRED_TO_CURRENT:
        bad = [a for a in ids if a == f"{RETURN_TARGET_NAME}___{retired}"]
        if bad:
            raise SystemExit(
                f"the final baseline names retired experience actions {bad}"
            )

    members = ",\n        ".join(f'AgentCore::Action::"{a}"' for a in ids)
    return (
        "permit(\n    principal,\n    action in [\n        "
        f"{members}\n    ],\n    {gateway_resource()}\n);"
    )


def quiesce_statement() -> str:
    """The temporary unconditional target-level forbid.

    Three properties are load-bearing and each is asserted by a test:

    * ``forbid`` — Cedar is forbid-wins, so this overrides the broad baseline
      permit for every tool on the target.
    * ``action in AgentCore::Action::"<target>"`` — group membership, so it
      covers the child tools *that existed when this policy was saved* without
      naming them. It does NOT pick up children added later; that was measured,
      not assumed. See the docstring.
    * no ``when`` clause — the probe on 2026-08-26 showed that a condition
      touching ``context.input`` is type-checked against every action in scope,
      and ``context.input`` does not exist for the target-level action. An
      unconditional forbid has no context access and no such finding.
    """
    return (
        "forbid(principal, action in AgentCore::Action::"
        f'"{RETURN_TARGET_NAME}", {gateway_resource()});'
    )


def canonical_action_statement(previous: str) -> Tuple[str, List[str]]:
    """Rename the action id in an existing statement, preserving everything else.

    Used for both remaining policy writes. The condition, effect, and resource
    are carried through verbatim: only the fully qualified action id changes, so
    a governance rule cannot be quietly widened by a rename.
    """
    return rewrite_actions(previous, to_canonical=True)


def _declared_normalization(target: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fields the service will not accept back, declared before the write.

    Recorded in the plan so the operator sees the second expected delta up front
    rather than discovering it in a post-write diff and mistaking it for drift.
    """
    out: List[Dict[str, Any]] = []
    metadata = target.get("metadataConfiguration") or {}
    headers = list(metadata.get("allowedRequestHeaders") or [])
    reserved = [h for h in headers if h in RESTRICTED_REQUEST_HEADERS]
    if not reserved:
        return out
    writable, _ = _writable_metadata(dict(metadata))
    out.append({
        "field": "metadataConfiguration.allowedRequestHeaders",
        "before": headers,
        "omittedFromWrite": reserved,
        "sent": writable,
        "reason": (
            "Gateway-reserved policy-session header. A caller may still supply it "
            "to the Gateway; what is reserved is configuring it for propagation to "
            "the target. UpdateGatewayTarget rejects it, so the live value is "
            "legacy, non-round-trippable control-plane state."
        ),
        "pellierDependency": "none — no runtime path reads it at the target",
        "governanceDependency": (
            "none for the current non-temporal Cedar flow; Phase 1 denials were "
            "produced by a caller sending only Authorization"
        ),
        "storedAfter": "read back from GetGatewayTarget and reported",
    })
    return out


def build_plan(live: Dict[str, Any], canonical: Dict[str, Any]) -> Dict[str, Any]:
    """The five-phase default-deny cutover, resolved against live state."""
    by_name = {t["name"]: t for t in live["targets"]}
    policies = {p["name"]: p for p in live["policies"]}

    for required in (BASELINE_POLICY_NAME, QUIESCE_POLICY_NAME, CONTROL_POLICY_NAME):
        if required not in policies:
            raise SystemExit(f"live policy engine has no policy named {required}")
    if RETURN_TARGET_NAME not in by_name:
        raise SystemExit(f"live gateway has no target named {RETURN_TARGET_NAME}")

    return_target = by_name[RETURN_TARGET_NAME]
    baseline = policies[BASELINE_POLICY_NAME]
    control = policies[CONTROL_POLICY_NAME]
    redundant = policies[QUIESCE_POLICY_NAME]

    def statement_of(policy: Dict[str, Any]) -> str:
        return policy_statement(policy)

    baseline_before = statement_of(baseline)
    baseline_narrow = narrowed_baseline_statement(live)
    # The restore target is the DERIVED original broad permit, never `baseline_before`.
    # Once the quiesce has landed, `baseline_before` IS the narrowed statement, and
    # using it made the restore phase a no-op that looked like a successful unquiesce.
    baseline_broad = broad_baseline_statement()
    # Describing a phase is not applying it. Before `target-canonical` lands, the return
    # target still publishes `escalate_to_stylist`, so the final baseline cannot name a
    # canonical escalation action that does not exist yet — and `final_baseline_statement`
    # rightly refuses. Aborting the whole plan there would make `--dry-run` unusable for
    # exactly the earlier phases whose job is to reach that state, so the phase carries
    # its own unavailability instead. The apply path refuses it twice over: the
    # precondition gate below requires the canonical return pair, and `_apply_policy_update`
    # refuses an entry with no `after`.
    baseline_final, baseline_final_blocked = "", ""
    try:
        baseline_final = final_baseline_statement(live)
    except SystemExit as exc:
        baseline_final_blocked = str(exc)
    control_before = statement_of(control)
    control_after, control_renames = rewrite_actions(control_before, to_canonical=True)
    redundant_before = statement_of(redundant)
    # The redundant policy currently holds the stale target-group forbid from the
    # abandoned design. Its canonical end state is the damaged-only permit it used
    # to be, pointed at the canonical action id.
    redundant_after, redundant_renames = rewrite_actions(
        permit_template(), to_canonical=True
    )

    canonical_tools = sorted(x["name"] for x in canonical_targets()[RETURN_TARGET_NAME])
    current_tools = sorted(n for n in _tool_names(return_target) if n)
    renamed_tools = sorted(RETIRED_TO_CURRENT.get(n, n) for n in current_tools)
    unknown = sorted(set(renamed_tools) - set(canonical_tools))
    if unknown:
        raise SystemExit(f"renaming {current_tools} produces unknown tools {unknown}")

    def policy_update(policy: Dict[str, Any], before: str, after: str,
                      note: str, renames: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "policy": policy["name"],
            "policyId": policy["policyId"],
            "status": policy.get("status"),
            "enforcementMode": policy.get("enforcementMode"),
            "before": before,
            "after": after,
            "renames": renames or [],
            "note": note,
        }

    phases = [
        {
            "phase": "default-deny-quiesce",
            "intent": (
                "Withdraw permission from the return target. Nothing permits its "
                "actions, so every child is DENY by default."
            ),
            "policyUpdates": [policy_update(
                baseline, baseline_before, baseline_narrow,
                f"Broad Gateway permit narrowed to the {len(unaffected_action_ids(live))} "
                "unaffected action ids, derived from live state.",
            )],
            "targetUpdates": [],
        },
        {
            "phase": "target-canonical",
            "intent": "Rename the unpermitted target's tools in place, 2 to 2.",
            "policyUpdates": [],
            "targetUpdates": [{
                "target": RETURN_TARGET_NAME,
                "targetId": return_target["targetId"],
                "status": return_target.get("status"),
                "before": current_tools,
                "after": renamed_tools,
                "deferred": sorted(set(canonical_tools) - set(renamed_tools)),
                "preserved": [
                    "targetId", "name", "description",
                    "credentialProviderConfigurations", "privateEndpoint",
                    "all writable metadataConfiguration",
                    "targetConfiguration except toolSchema.inlinePayload",
                ],
                "serviceNormalization": _declared_normalization(return_target),
            }],
        },
        {
            "phase": "return-forbid-canonical",
            "intent": "Point the restrictive control at the canonical action id.",
            "policyUpdates": [policy_update(
                control, control_before, control_after,
                "Condition, effect and resource carried through verbatim.",
                control_renames,
            )],
            "targetUpdates": [],
        },
        {
            "phase": "allow-damaged-canonical",
            "intent": (
                "THE DAMAGED-RETURN REOPEN. Replace the stale target-group forbid "
                "with the canonical damaged-only permit it was before the abandoned "
                "design repurposed it. With the baseline still narrowed this is the "
                "only matching permit, so exactly one business path opens."
            ),
            "policyUpdates": [policy_update(
                redundant, redundant_before, redundant_after,
                "Derived from the captured pre-migration definition with only the "
                "action id renamed. No new business condition is introduced.",
                redundant_renames,
            )],
            "targetUpdates": [],
        },
        {
            "phase": "explicit-baseline-final",
            "intent": (
                "THE FINAL AUTHORIZATION. Baseline 11 -> 12 explicit actions, adding "
                "only escalate_to_human. The return action keeps its dedicated permit "
                "and forbid; customer-scoped recommendation reads remain default-denied "
                "pending their scoped-policy convergence."
            ),
            "policyUpdates": [dict(policy_update(
                baseline, baseline_before, baseline_final,
                "Explicit action list, not a wildcard: publication and authorization "
                "stay separate decisions. Measured first — policy-filtered MCP "
                "discovery showed initiate_return IS visible under its conditional "
                "permit, so the baseline does not need to name it.",
            ), unavailable=baseline_final_blocked)],
            "targetUpdates": [],
        },
        {
            "phase": "restore-broad-permit",
            "intent": (
                "THE FULL EXPERIENCE UNQUIESCE. Restore the original broad permit, "
                "reopening the rest of the target now that the canonical permit and "
                "the canonical restrictive forbid are both ACTIVE."
            ),
            "policyUpdates": [policy_update(
                baseline, baseline_before, baseline_broad,
                "Restored to the original broad permit: any action on this gateway. "
                "Derived rather than read from live state, because live state is the "
                "narrowed quiesce once Phase A has landed.",
            )],
            "targetUpdates": [],
        },
    ]

    for entry in phases:
        n = len(entry["policyUpdates"]) + len(entry["targetUpdates"])
        if n != 1:
            raise SystemExit(
                f"phase {entry['phase']} touches {n} resources; each phase must "
                "touch exactly one so it stays individually reversible"
            )


    # And the restore phase must actually reopen escalation, which is the whole point
    # of it. Asserted on the modelled authorization rather than on the statement text.
    restore = next(
        (e for e in phases if e["phase"] == "restore-broad-permit"), None
    )
    if restore is not None:
        after = restore["policyUpdates"][0]["after"]
        parsed = parse_statement(BASELINE_POLICY_NAME, after)
        if parsed.actions is not None:
            raise SystemExit(
                "restore-broad-permit does not restore a BROAD permit: it names "
                f"{len(parsed.actions)} action id(s). The unquiesce would leave "
                "escalate_to_human denied."
            )

    return {
        "gateway": {
            "gatewayId": EXPECTED_GATEWAY_ID,
            "gatewayPolicyMode": (
                live["gateway"].get("policyEngineConfiguration") or {}
            ).get("mode"),
            "gatewayPolicyModeChanged": False,
            "authorizerUnchanged": True,
            "roleUnchanged": True,
        },
        "phases": phases,
        "returnTarget": RETURN_TARGET_NAME,
        "unaffectedActionIds": unaffected_action_ids(live),
        "canonicalTools": canonical_tools,
        "targetToolsAfterMigration": renamed_tools,
        "deferredNewTools": sorted(set(canonical_tools) - set(renamed_tools)),
        "damagedReopenEvent": "allow-damaged-canonical",
        "unquiesceEvent": "restore-broad-permit",
        "safetyBoundary": "matching permit count for experience-target actions == 0",
        "outOfScopeTargets": sorted(n for n in by_name if n != RETURN_TARGET_NAME),
        "notTouched": [
            "AgentCore Runtime (CloudFormation-owned)",
            "AgentCore Memory (CloudFormation-owned)",
            "IAM roles and policies (CloudFormation-owned)",
            "Cognito / JWT authorizer configuration",
            "KMS configuration",
            "CloudWatch log retention",
            "resource tags",
            "Lambda code (Phase B1 already complete)",
            "the other three Gateway targets (schemas unchanged throughout)",
            "Policy engine identity (updated in place, never replaced)",
        ],
        "canonicalVocabulary": canonical,
    }


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _wait_target(control: Any, target_id: str, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    status = "UNKNOWN"
    while time.time() < deadline:
        detail = control.get_gateway_target(
            gatewayIdentifier=EXPECTED_GATEWAY_ID, targetId=target_id
        )
        status = str(detail.get("status") or "")
        if status in TERMINAL_OK or status in TERMINAL_BAD:
            return status
        time.sleep(5)
    return status


def _wait_policy(control: Any, policy_id: str, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    status = "UNKNOWN"
    while time.time() < deadline:
        detail = control.get_policy(
            policyEngineId=EXPECTED_POLICY_ENGINE_ID, policyId=policy_id
        )
        status = str(detail.get("status") or "")
        if status in TERMINAL_OK or status in TERMINAL_BAD:
            return status
        time.sleep(5)
    return status


def _writable_metadata(
    metadata: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Strip headers the service will not accept on a write.

    Returns the metadata to send and the headers removed. When nothing writable is
    left the metadata is dropped entirely rather than sent as an empty structure,
    because an empty `allowedRequestHeaders` and an absent one are not documented
    to mean the same thing and guessing is worse than being explicit about it in
    the log.
    """
    remaining = dict(metadata)
    headers = list(remaining.get("allowedRequestHeaders") or [])
    dropped = [h for h in headers if h in RESTRICTED_REQUEST_HEADERS]
    keep = [h for h in headers if h not in RESTRICTED_REQUEST_HEADERS]
    if keep:
        remaining["allowedRequestHeaders"] = keep
    else:
        remaining.pop("allowedRequestHeaders", None)
    if not remaining:
        return None, dropped
    return remaining, dropped


def apply_target_schemas(
    control: Any, live: Dict[str, Any], schemas: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """Update the four existing targets in place, one at a time.

    Never delete and recreate: the target ids are referenced by Cedar action ids
    and by the Gateway's own routing, and recreating them would change identity
    for a rename.
    """
    applied = []
    for target in live["targets"]:
        name = target.get("name")
        target_id = target.get("targetId")
        if target.get("status") != "READY":
            raise SystemExit(
                f"target {name} is {target.get('status')}, not READY; refusing to update"
            )
        payload = schemas.get(name)
        if payload is None:
            raise SystemExit(f"no desired schema for live target {name}")

        config = copy.deepcopy(target["targetConfiguration"])
        config["mcp"]["lambda"]["toolSchema"] = {"inlinePayload": payload}

        # Resend every optional field the live target carries. UpdateGatewayTarget
        # takes a full representation, so a field omitted here is a field cleared
        # on the target. An earlier version sent only name, targetConfiguration and
        # credentialProviderConfigurations, which would have silently dropped:
        #
        #   description            "Pellier experience-guide MCP server (...)"
        #   metadataConfiguration  allowedRequestHeaders:
        #                          [x-amzn-bedrock-agentcore-policy-session-id]
        #
        # That header is how the policy session id reaches the Gateway, so losing
        # it would have broken policy-session correlation as a side effect of a
        # tool rename — with the update reporting success.
        request: Dict[str, Any] = {
            "gatewayIdentifier": EXPECTED_GATEWAY_ID,
            "targetId": target_id,
            "targetConfiguration": config,
        }
        for field in (
            "name",
            "description",
            "credentialProviderConfigurations",
            "metadataConfiguration",
            "privateEndpoint",
        ):
            if target.get(field) is None:
                continue
            value = copy.deepcopy(target[field])
            if field == "metadataConfiguration":
                value, dropped = _writable_metadata(value)
                for header in dropped:
                    print(
                        f"      NOTE: omitting Gateway-reserved policy-session "
                        f"header {header!r} from allowedRequestHeaders. It may "
                        "still be supplied BY a caller to the Gateway; what is "
                        "reserved is configuring it for propagation to the "
                        "target. Legacy, non-round-trippable state."
                    )
                if value is None:
                    print(
                        "      NOTE: metadataConfiguration held nothing writable, so "
                        "it is omitted and will be cleared on this target."
                    )
                    continue
            request[field] = value

        preserved = sorted(k for k in request if k not in
                           ("gatewayIdentifier", "targetId", "targetConfiguration"))
        print(f"  update-gateway-target {name} -> {len(payload)} tools")
        print(f"      preserving: {', '.join(preserved)}")
        control.update_gateway_target(**request)
        status = _wait_target(control, target_id)
        print(f"      status: {status}")
        if status not in TERMINAL_OK:
            raise SystemExit(
                f"target {name} reached {status}; STOP and roll this target back "
                "before touching policies"
            )
        applied.append({"target": name, "targetId": target_id, "status": status})
    return applied


def assert_generated_cedar_is_well_formed(
    label: str,
    statement: str,
    *,
    expect_effect: Optional[str] = None,
    expect_actions: Optional[int] = None,
) -> CedarStatement:
    """Syntactic and structural gate on any statement this module is about to submit.

    Runs on the APPLY path, not only in tests. The doubled-brace defect that this
    catches was produced by a template whose test coverage looked complete: mixing an
    f-string with a plain literal containing ``}}`` rendered
    ``... "damaged" }};`` and nothing in the suite compared braces. A dry run printed
    it; a run without a dry run would have submitted it.

    ``expect_actions`` is a cardinality, not a name — the names are asserted by the
    per-phase guards against live state.
    """
    text = statement.strip()
    problems: List[str] = []
    if text.count("{") != text.count("}"):
        problems.append(
            f"unbalanced braces ({text.count('{')} open, {text.count('}')} close)"
        )
    if text.count("(") != text.count(")"):
        problems.append(
            f"unbalanced parentheses ({text.count('(')} open, {text.count(')')} close)"
        )
    if "}}" in text or "{{" in text:
        problems.append("doubled brace, which is an f-string escaping defect")
    if not text.endswith(";"):
        problems.append("no terminating semicolon")
    if problems:
        raise SystemExit(
            f"refusing to submit {label}: " + "; ".join(problems)
            + f"\n  statement: {' '.join(text.split())}"
        )

    parsed = parse_statement(label, text)
    if expect_effect and parsed.effect != expect_effect:
        raise SystemExit(
            f"refusing to submit {label}: effect is {parsed.effect}, expected "
            f"{expect_effect}"
        )
    if expect_actions is not None:
        count = len(parsed.actions or ())
        if count != expect_actions:
            raise SystemExit(
                f"refusing to submit {label}: names {count} action id(s), expected "
                f"{expect_actions}"
            )
    if gateway_resource() not in " ".join(text.split()):
        raise SystemExit(
            f"refusing to submit {label}: the resource clause is not this gateway"
        )
    return parsed


def _norm(statement: str) -> str:
    """Whitespace-insensitive form, for comparison only."""
    return " ".join((statement or "").split())


def _policy_state(control: Any, policy_id: str) -> Dict[str, Any]:
    """Read a policy, keeping the statement verbatim.

    `statement` is the raw bytes because a restore must put back exactly what was
    there; `normalised` is for comparison. An earlier version stored only the
    normalised form and then restored *that*, which put back a statement differing
    from the original in whitespace — a restore that reports success while not
    being byte-exact.
    """
    detail = control.get_policy(
        policyEngineId=EXPECTED_POLICY_ENGINE_ID, policyId=policy_id
    )
    raw = policy_statement(detail)
    return {
        "status": detail.get("status"),
        "enforcementMode": detail.get("enforcementMode"),
        "statement": raw,
        "normalised": _norm(raw),
        "statusReasons": detail.get("statusReasons") or [],
    }


def _restore_policy(control: Any, policy_id: str, statement: str, mode: str) -> Dict[str, Any]:
    """Put a policy back to a captured definition and prove it landed."""
    print(f"      RESTORING {policy_id} to its captured definition")
    control.update_policy(
        policyEngineId=EXPECTED_POLICY_ENGINE_ID,
        policyId=policy_id,
        definition={"policy": {"statement": statement}},
        enforcementMode=mode,
        validationMode="FAIL_ON_ANY_FINDINGS",
    )
    _wait_policy(control, policy_id)
    after = _policy_state(control, policy_id)
    exact = after["statement"] == statement
    print(f"      restored policy status          : {after['status']}")
    print(f"      restored policy enforcementMode : {after['enforcementMode']}")
    print(f"      restored definition exact       : {exact}")
    if after["status"] not in LIFECYCLE_TERMINAL_OK or not exact:
        raise SystemExit(
            "RESTORE DID NOT LAND. Do not proceed. Inspect the policy by hand "
            f"against the rollback capture: {policy_id}"
        )
    return after


def _live_permit_matches(
    live: Dict[str, Any], actions: List[str], compiled: Tuple[str, ...] = ()
) -> Dict[str, List[str]]:
    """Which active permit policies can match each action, parsed from live Cedar.

    The single source of the migration's safety boundary. Parsed from stored
    definitions rather than from the plan, because the plan describes intent and
    only the stored policy decides.
    """
    out: Dict[str, List[str]] = {a: [] for a in actions}
    for policy in live["policies"]:
        statement = policy_statement(policy)
        parsed = parse_statement(policy["name"], statement, compiled)
        if parsed.effect != "permit":
            continue
        for action in actions:
            if parsed.covers(action):
                out[action].append(policy["name"])
    return out


def _require_closed_canonical_target(control: Any, phase: str) -> Dict[str, Any]:
    """Assert the target is canonical AND has no matching permit. Returns live.

    Shared by the two phases that must only run while the target is closed. Reads
    live state; never infers that an earlier phase was run.
    """
    live = read_live(control)
    target = next(
        (t for t in live["targets"] if t["name"] == RETURN_TARGET_NAME), None
    )
    if target is None:
        raise SystemExit(f"live gateway has no target named {RETURN_TARGET_NAME}")
    tools = sorted(n for n in _tool_names(target) if n)
    expected = sorted(RETIRED_TO_CURRENT.get(n, n) for n in ("process_return", "escalate_to_stylist"))
    if tools != expected:
        raise SystemExit(
            f"refusing {phase}: the target publishes {tools}, not the canonical "
            f"{expected}. Run --phase target-canonical first."
        )
    actions = [f"{RETURN_TARGET_NAME}___{n}" for n in tools]
    matches = _live_permit_matches(live, actions)
    open_actions = {a: names for a, names in matches.items() if names}
    if open_actions:
        raise SystemExit(
            f"refusing {phase}: a permit can reach the target, so it is not closed.\n  "
            + "\n  ".join(f"{a} <- {names}" for a, names in sorted(open_actions.items()))
        )
    for policy in live["policies"]:
        if policy.get("enforcementMode") != "ACTIVE":
            raise SystemExit(
                f"refusing {phase}: policy {policy['name']} enforcementMode is "
                f"{policy.get('enforcementMode')}."
            )
        if policy.get("status") in LIFECYCLE_TERMINAL_OK:
            continue
        # One narrowly-matched recovery exception. The first Phase C attempt left
        # `process_return_damaged_only` in UPDATE_FAILED holding its byte-exact
        # prior definition, which cannot reach ACTIVE because that definition names
        # an action the canonical schema no longer publishes. Retrying Phase C is
        # precisely how that is resolved, so it must not be blocked by the state it
        # is meant to fix. Every other non-ACTIVE policy is still a hard stop.
        recoverable = (
            phase == IGNORE_FINDINGS_PHASE
            and policy["name"] == IGNORE_FINDINGS_POLICY
            and policy.get("status") == "UPDATE_FAILED"
        )
        if not recoverable:
            raise SystemExit(
                f"refusing {phase}: policy {policy['name']} status is "
                f"{policy.get('status')}, not ACTIVE."
            )
        parsed = parse_statement(
            policy["name"],
            policy_statement(policy),
        )
        retired = f"{RETURN_TARGET_NAME}___process_return"
        if parsed.effect != "forbid" or parsed.actions != (retired,):
            raise SystemExit(
                f"refusing {phase}: {policy['name']} is UPDATE_FAILED but does not "
                f"hold the expected prior definition (forbid on {retired}). This is "
                "not the recovery state this exception covers."
            )
        print(
            f"  NOTE: {policy['name']} is UPDATE_FAILED holding its byte-exact prior\n"
            "        definition, which names a retired action and therefore cannot\n"
            "        reach ACTIVE. Retrying this phase is the resolution."
        )
    return live


# The ONE policy write in this migration permitted to use IGNORE_ALL_FINDINGS, and
# the exact conditions under which it is permitted.
#
# AgentCore separates SCHEMA checks from SEMANTIC ANALYZER findings. Schema checks
# — valid action/tool references, context attributes, types, resource form — run
# regardless of validationMode. IGNORE_ALL_FINDINGS suppresses only analyzer
# findings: overly restrictive, overly permissive, ineffective.
#
# Phase C hits exactly one of those. Installing
#
#     forbid(... action == ___initiate_return ...) when { reason != "damaged" }
#
# while the experience target has zero matching permits makes the engine deny every
# request for that action, which the analyzer reports as:
#
#     Overly Restrictive: Policy Engine will deny every request for the specified
#     principal (AgentCore::IamEntity), action (...___initiate_return) and resource
#     (...) combination if the policy is added or updated
#
# That is the intended migration state, not a defect: DENY_ALL until Phase D. The
# analyzer is right about the effect and wrong about it being a problem.
#
# This is NOT "disable validation" and NOT "ignore Cedar errors". An unrecognized
# action, a bad context attribute, or a type mismatch still fails, which is what
# makes the exception narrow enough to accept.
IGNORE_FINDINGS_PHASE = "return-forbid-canonical"
IGNORE_FINDINGS_POLICY = "process_return_damaged_only"

# Schema-level failures that must never be accepted as "an expected finding".
SCHEMA_FAILURE_MARKERS = (
    "unrecognized action",
    "unrecognized entity",
    "invalid context",
    "not found",
    "type mismatch",
    "unable to find an applicable action",
    "invalid resource",
)


def validation_mode_for(
    phase: str, policy_name: str, live: Dict[str, Any], desired: str
) -> str:
    """Strict validation unless this is exactly the Phase C recovery write.

    Every condition is re-derived from live state, so the exception cannot be
    reached by passing a flag or by running a different phase.
    """
    if phase != IGNORE_FINDINGS_PHASE or policy_name != IGNORE_FINDINGS_POLICY:
        return "FAIL_ON_ANY_FINDINGS"

    target = next(
        (t for t in live["targets"] if t["name"] == RETURN_TARGET_NAME), None
    )
    if target is None:
        return "FAIL_ON_ANY_FINDINGS"
    tools = set(_tool_names(target))
    canonical = RETIRED_TO_CURRENT["process_return"]
    if canonical not in tools or "process_return" in tools:
        return "FAIL_ON_ANY_FINDINGS"

    actions = [f"{RETURN_TARGET_NAME}___{n}" for n in sorted(tools) if n]
    if any(_live_permit_matches(live, actions).values()):
        return "FAIL_ON_ANY_FINDINGS"

    baseline = next(
        (p for p in live["policies"] if p["name"] == BASELINE_POLICY_NAME), None
    )
    baseline_parsed = parse_statement(
        BASELINE_POLICY_NAME,
        policy_statement(baseline or {}),
    )
    if baseline_parsed.actions is None:
        return "FAIL_ON_ANY_FINDINGS"

    gateway_mode = (live["gateway"].get("policyEngineConfiguration") or {}).get("mode")
    if gateway_mode != "ENFORCE":
        return "FAIL_ON_ANY_FINDINGS"

    # The desired statement must be the restrictive rule and nothing else.
    parsed = parse_statement(policy_name, desired)
    if (
        parsed.effect != "forbid"
        or parsed.actions != (f"{RETURN_TARGET_NAME}___{canonical}",)
        or parsed.groups != ()
        or parsed.condition != "not_damaged"
    ):
        return "FAIL_ON_ANY_FINDINGS"

    return "IGNORE_ALL_FINDINGS"


def apply_policy_update(
    control: Any,
    update: Dict[str, Any],
    *,
    phase: str = "",
    live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write one policy definition, with the failure semantics the probe taught.

    capture -> update -> poll -> inspect status -> inspect stored definition.

    A rejected ``UpdatePolicy`` does NOT roll the stored definition back: on
    2026-08-26 a validation failure left ``status=UPDATE_FAILED`` with the
    rejected statement stored and ``enforcementMode`` untouched. So a non-ACTIVE
    status triggers an immediate restore from the captured definition, and the run
    stops afterwards either way. Never continue to another phase after a failed
    policy write, even when the restore succeeds.
    """
    policy_id = update["policyId"]
    if update.get("unavailable"):
        # The plan could describe the phase but not build its definition against the
        # live state it was derived from. Never fall through to a write.
        raise SystemExit(
            f"refusing to run {phase}: its definition could not be built from live "
            f"state. {update['unavailable']}"
        )
    mode = update.get("enforcementMode")
    if not mode:
        raise SystemExit(
            f"policy {update['policy']} has no captured enforcementMode; refusing to "
            "update, because omitting it lets the service apply its own default."
        )
    if mode not in ENFORCEMENT_MODES:
        raise SystemExit(
            f"policy {update['policy']}: {mode!r} is not an enforcementMode. Legal "
            f"values are {sorted(ENFORCEMENT_MODES)}. The lifecycle `status` field "
            "also uses the token 'ACTIVE', so a value copied from `status` looks "
            "plausible here and would silently enforce a LOG_ONLY policy."
        )

    captured = _policy_state(control, policy_id)
    print(f"  update-policy {update['policy']}  id={policy_id}")
    print(f"      captured policy status          : {captured['status']}")
    print(f"      captured policy enforcementMode : {captured['enforcementMode']}")
    for line in update.get("renames") or []:
        print(f"      {line}")

    validation = validation_mode_for(
        phase, update["policy"], live or read_live(control), update["after"]
    )
    if validation != "FAIL_ON_ANY_FINDINGS":
        print(f"      validationMode: {validation}")
        print("        Accepting the analyzer's Overly Restrictive / DENY_ALL finding:")
        print("        the target is intentionally default-denied until the unquiesce.")
        print("        Schema checks still run — an unrecognized action still fails.")
    else:
        print(f"      validationMode: {validation}")
    # A submission identical to what is already stored is not a phase. Measured here,
    # against the definition just captured from live, because in `build_plan` the same
    # comparison is legitimate: a plan derived before the quiesce has nothing to
    # restore yet. What this catches is the restore phase sourcing its `after` from
    # live state once the quiesce HAS landed — which reported a successful unquiesce
    # while leaving the target partially closed.
    if _norm(update["after"]) == _norm(captured["statement"]):
        raise SystemExit(
            f"refusing to run {phase}: the definition submitted for "
            f"{update['policy']} is identical to the one already deployed. Nothing "
            "would change, and for restore-broad-permit this means the broad permit "
            "is being sourced from live state instead of the canonical original."
        )

    # Structural gate. Nothing malformed may reach the service, whatever the plan says.
    assert_generated_cedar_is_well_formed(
        f"{update['policy']} ({phase})",
        update["after"],
        expect_actions=_EXPECTED_ACTION_CARDINALITY.get(phase),
        expect_effect=_EXPECTED_EFFECT.get(phase),
    )
    control.update_policy(
        policyEngineId=EXPECTED_POLICY_ENGINE_ID,
        policyId=policy_id,
        definition={"policy": {"statement": update["after"]}},
        enforcementMode=mode,
        validationMode=validation,
    )
    _wait_policy(control, policy_id)
    after = _policy_state(control, policy_id)
    print(f"      policy status          : {after['status']}")
    print(f"      policy enforcementMode : {after['enforcementMode']}")

    if after["status"] not in LIFECYCLE_TERMINAL_OK:
        reasons = " ".join(str(r).lower() for r in after["statusReasons"])
        schema_error = [m for m in SCHEMA_FAILURE_MARKERS if m in reasons]
        if schema_error:
            print(f"      SCHEMA FAILURE (never an accepted finding): {schema_error}")
        print(f"      FAILED: {after['statusReasons']}")

        # Do NOT auto-restore the captured definition when it names an action the
        # canonical schema no longer publishes. Schema checks always run, so that
        # definition can never reach ACTIVE, and the retry only produced a
        # confusing "RESTORE DID NOT LAND" on top of the real failure. Leaving the
        # stored definition alone is safe: the target has zero matching permits, so
        # default-deny closes it regardless of this policy.
        captured_parsed = parse_statement(update["policy"], captured["statement"])
        stale = any(
            a.startswith(f"{RETURN_TARGET_NAME}___")
            and a.split("___")[-1] in RETIRED_TO_CURRENT
            for a in (captured_parsed.actions or ())
        )
        if stale:
            raise SystemExit(
                f"policy {update['policy']} reached {after['status']}. Its captured "
                "definition names a retired action that the canonical schema no "
                "longer publishes, so restoring it cannot reach ACTIVE and was NOT "
                "attempted. The environment stays closed because the target has "
                "zero matching permits. STOP and report."
            )
        _restore_policy(control, policy_id, captured["statement"], captured["enforcementMode"])
        raise SystemExit(
            f"policy {update['policy']} reached {after['status']}; it has been "
            "restored to the captured definition. STOP: do not run a later phase."
        )

    if after["normalised"] != _norm(update["after"]):
        _restore_policy(control, policy_id, captured["statement"], captured["enforcementMode"])
        raise SystemExit(
            f"policy {update['policy']} reports ACTIVE but its stored definition is "
            "not what was submitted; restored and stopping."
        )
    if after["enforcementMode"] != mode:
        _restore_policy(control, policy_id, captured["statement"], captured["enforcementMode"])
        raise SystemExit(
            f"policy {update['policy']} enforcementMode drifted "
            f"{mode} -> {after['enforcementMode']}; restored and stopping."
        )
    print("      stored definition matches what was submitted")
    return after


def assert_no_mode_drift(control: Any) -> None:
    """All three policies ACTIVE and the Gateway ENFORCE. Any drift is a hard stop.

    Three distinct fields, never collapsed:
      policy status           lifecycle    CREATING|ACTIVE|UPDATING|*_FAILED
      policy enforcementMode  enforcement  ACTIVE|LOG_ONLY
      gateway policy mode     enforcement  ENFORCE|LOG_ONLY
    """
    for policy in control.list_policies(
        policyEngineId=EXPECTED_POLICY_ENGINE_ID
    ).get("policies", []):
        mode = policy.get("enforcementMode")
        if mode != "ACTIVE":
            raise SystemExit(
                f"policy {policy.get('name')} has enforcementMode={mode}; the "
                "vocabulary migration requires ACTIVE on all three. LOG_ONLY is "
                "reserved for the later governance demonstration."
            )
    gateway = control.get_gateway(gatewayIdentifier=EXPECTED_GATEWAY_ID)
    gateway_mode = (gateway.get("policyEngineConfiguration") or {}).get("mode")
    if gateway_mode != "ENFORCE":
        raise SystemExit(
            f"gateway policy mode is {gateway_mode}; the migration requires "
            "ENFORCE. Do not switch to LOG_ONLY to make a migration easier."
        )


def apply_one_target(control: Any, live: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Update exactly one target's inline tool schema in place."""
    target = next(
        (t for t in live["targets"] if t.get("name") == update["target"]), None
    )
    if target is None:
        raise SystemExit(f"live gateway has no target named {update['target']}")
    # Take the schema from the plan's `after` list, not from the full canonical
    # set: the plan deliberately excludes DEFERRED_NEW_TOOLS, and reaching for
    # canonical_targets() here would silently publish them anyway.
    wanted = set(update["after"])
    schema = [
        entry for entry in canonical_targets()[update["target"]]
        if entry["name"] in wanted
    ]
    missing = sorted(wanted - {e["name"] for e in schema})
    if missing:
        raise SystemExit(f"no canonical schema entry for {missing}")
    return apply_target_schemas(
        control, {"targets": [target]}, {update["target"]: schema}
    )[0]


# ---------------------------------------------------------------------------
# Effective authorization, phase by phase
# ---------------------------------------------------------------------------
#
# The reason this exists: a test that applies two phases back to back and asserts
# afterwards proves nothing about the state between them, and the CLI emits each
# phase as a separate operator invocation with a human-length gap in the middle.
# The first version of this migration ordered the Gateway bridge BEFORE the policy
# widening, so `--apply --phase bridge` on its own left `initiate_return`
# callable while the forbid still named only `process_return`. The broad baseline
# permit then allowed a non-damaged return. The test did not catch it because it
# asserted after `bridge + policies`, never after `bridge` alone.
#
# So the invariant is now evaluated after every individual phase, from the same
# plan the CLI writes.

SENSITIVE_TOOLS = ("process_return", "initiate_return")


@dataclass(frozen=True)
class CedarStatement:
    """Just enough of a Cedar statement to decide the cases that matter."""

    name: str
    effect: str                 # "permit" | "forbid"
    actions: Optional[Tuple[str, ...]]   # explicit ids; None means unconstrained
    groups: Tuple[str, ...]     # target-level action groups this names
    condition: str              # "none" | "damaged_only" | "not_damaged"
    compiled_members: Tuple[str, ...] = ()  # group children as of the last save

    def covers(self, action: str) -> bool:
        """Whether this statement's action scope includes `action`.

        An explicit id matches literally. A target group matches only the children
        that existed when the policy was last saved — `compiled_members` — because
        that is the behaviour measured on 2026-08-26: a group forbid saved while
        the target held `process_return` did NOT deny `initiate_return` after the
        rename, though the policy remained ACTIVE with an unchanged statement.

        Modelling a group as covering everything under the target would be the
        dangerous direction: it would make a stale forbid look protective.
        """
        if self.actions is None and not self.groups:
            return True
        if self.actions and action in self.actions:
            return True
        # `compiled_members` describes GROUP membership only. Consulting it for a
        # statement that names explicit ids would make an unrelated policy appear
        # to cover actions it never mentions — which is how the narrowed baseline
        # permit briefly looked like it still covered the experience target.
        if not self.groups:
            return False
        return action in self.compiled_members


def parse_statement(
    name: str,
    statement: str,
    compiled_members: Optional[Tuple[str, ...]] = None,
) -> CedarStatement:
    """Parse effect, action scope, and condition. Unrecognized input is fatal.

    Deliberately strict. A parser that silently treats an unrecognized condition
    as "no condition" would report a forbid as covering more than it does, which
    is the exact direction of error this whole exercise is guarding against.
    """
    text = " ".join(statement.split())
    if text.startswith("permit("):
        effect = "permit"
    elif text.startswith("forbid("):
        effect = "forbid"
    else:
        raise SystemExit(f"{name}: statement starts with neither permit nor forbid")

    equality = re.findall(r'action\s*==\s*AgentCore::Action::"([^"]+)"', text)
    members = re.findall(r"action\s+in\s+\[([^\]]+)\]", text)
    # `action in AgentCore::Action::"X"` without brackets is group membership,
    # not set membership: X is a target and the statement covers its child tools.
    group = re.findall(r'action\s+in\s+AgentCore::Action::"([^"]+)"', text)
    actions: Optional[Tuple[str, ...]] = ()
    groups: Tuple[str, ...] = ()
    if equality:
        actions = tuple(equality)
    elif members:
        actions = tuple(re.findall(r'AgentCore::Action::"([^"]+)"', members[0]))
        if not actions:
            raise SystemExit(f"{name}: `action in [...]` names no action id")
    elif group:
        groups = tuple(group)
        actions = ()
    elif re.search(r"\(\s*principal\s*,\s*action\s*,", text):
        actions = None
    else:
        raise SystemExit(f"{name}: could not determine the action scope")

    if "when" not in text and "unless" not in text:
        condition = "none"
    elif 'reason == "damaged"' in text:
        condition = "damaged_only"
    elif 'reason != "damaged"' in text:
        condition = "not_damaged"
    else:
        raise SystemExit(f"{name}: unrecognized condition; refusing to guess")
    return CedarStatement(
        name=name, effect=effect, actions=actions, groups=groups,
        condition=condition, compiled_members=tuple(compiled_members or ()),
    )


def _matches(stmt: CedarStatement, action: str, reason: str) -> bool:
    if not stmt.covers(action):
        return False
    if stmt.condition == "damaged_only":
        return reason == "damaged"
    if stmt.condition == "not_damaged":
        return reason != "damaged"
    return True


def evaluate(statements: List[CedarStatement], action: str, reason: str) -> str:
    """Cedar's decision rule: allow iff some permit matches and no forbid does."""
    if any(_matches(s, action, reason) for s in statements if s.effect == "forbid"):
        return "DENY"
    if any(_matches(s, action, reason) for s in statements if s.effect == "permit"):
        return "ALLOW"
    return "DENY"


def phase_states(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Effective authorization after each phase, from the plan the CLI applies.

    The safety metric is MATCHING PERMIT COUNT, not forbid coverage. Two
    forbid-based designs failed live — a policy cannot name a future action, and
    target-group membership is compiled at policy-save time — so a forbid is no
    longer trusted as the boundary. What is trusted:

        while the return target's vocabulary is mutating,
        no active permit may match any of its child actions.

    Cedar is default-deny, so zero matching permits denies the action whatever its
    name is and whenever any policy was compiled. The stale target-group forbid may
    still be present; it is defence in depth and is deliberately NOT counted.
    """
    target = plan["returnTarget"]
    phase_by_name = {e["phase"]: e for e in plan["phases"]}
    tracked = (BASELINE_POLICY_NAME, QUIESCE_POLICY_NAME, CONTROL_POLICY_NAME)

    def policy_after(name: str, upto: int) -> str:
        for entry in reversed(plan["phases"][: upto + 1]):
            for update in entry["policyUpdates"]:
                # An unbuildable phase contributes nothing to the model. Reading past
                # it to the previous definition would be worse than skipping it, so the
                # row for that phase is reported unavailable rather than modelled.
                if update["policy"] == name and not update.get("unavailable"):
                    return update["after"]
        for entry in plan["phases"]:
            for update in entry["policyUpdates"]:
                if update["policy"] == name:
                    return update["before"]
        return ""

    def tools_after(upto: int) -> List[str]:
        for entry in reversed(plan["phases"][: upto + 1]):
            for update in entry["targetUpdates"]:
                if update["target"] == target:
                    return list(update["after"])
        for entry in plan["phases"]:
            for update in entry["targetUpdates"]:
                if update["target"] == target:
                    return list(update["before"])
        return []

    def unavailable_reason(upto: int) -> str:
        if upto < 0:
            return ""
        return next(
            (u["unavailable"] for u in plan["phases"][upto]["policyUpdates"]
             if u.get("unavailable")),
            "",
        )

    rows = []
    for index in range(-1, len(plan["phases"])):
        label = "LIVE" if index < 0 else plan["phases"][index]["phase"]
        blocked = unavailable_reason(index)
        if blocked:
            # No decisions, and deliberately no `safe` claim either way: the phase's
            # definition could not be built from this live state, so its post-phase
            # authorization is unknown. Reporting it as safe would be a guess, and
            # reporting it as unsafe would fail a plan that is merely early.
            rows.append({
                "phase": label,
                "intent": phase_by_name.get(label, {}).get("intent", ""),
                "unavailable": blocked,
                "targetTools": sorted(tools_after(index)),
                "callable": [],
                "governedWritesCallable": [],
                "permitCoverage": {},
                "maxMatchingPermits": 0,
                "decisions": {},
                "nonDamagedAllowed": [],
                "safe": True,
                "targetOpen": False,
            })
            continue
        # The group forbid on the return target was saved while the target held
        # its pre-migration tools, so those are its compiled members. Anything
        # renamed afterwards is not a member, which is exactly the measured
        # behaviour that ended the forbid-based design.
        compiled = tuple(f"{target}___{tool}" for tool in tools_after(-1))
        statements = [
            parse_statement(name, policy_after(name, index), compiled)
            for name in tracked
        ]
        permits = [s for s in statements if s.effect == "permit"]
        actions = [f"{target}___{tool}" for tool in sorted(tools_after(index))]

        coverage = {}
        decisions = {}
        for action in actions:
            matching = sorted(
                s.name for s in permits if s.covers(action)
            )
            coverage[action] = matching
            decisions[action] = {
                "non_damaged": evaluate(statements, action, "changed_mind"),
                "damaged": evaluate(statements, action, "damaged"),
            }

        governed = [a for a in actions if a.split("___")[-1] in GOVERNED_WRITE_TOOLS]
        # A governed write is unsafe if it is permitted by anything AND no
        # restrictive forbid narrows it.
        unsafe = [
            a for a in governed
            if coverage[a] and decisions[a]["non_damaged"] == "ALLOW"
        ]
        rows.append({
            "phase": label,
            "intent": phase_by_name.get(label, {}).get("intent", "current live state"),
            "targetTools": sorted(tools_after(index)),
            "callable": actions,
            "governedWritesCallable": governed,
            "permitCoverage": coverage,
            "maxMatchingPermits": max((len(v) for v in coverage.values()), default=0),
            "decisions": decisions,
            "nonDamagedAllowed": unsafe,
            "safe": not unsafe,
            "targetOpen": any(d["damaged"] == "ALLOW" for d in decisions.values()),
        })
    return rows


def print_phase_proof(plan: Dict[str, Any]) -> bool:
    """Print the per-phase table and return whether every phase is safe."""
    rows = phase_states(plan)
    all_safe = True
    for row in rows:
        if row.get("unavailable"):
            print(f"\nPHASE: {row['phase']}   [NOT YET BUILDABLE]")
            print(f"  {row['intent']}")
            print(f"  {row['unavailable']}")
            print("  No authorization modelled: an earlier phase has to land first.")
            continue
        state = "OPEN" if row["targetOpen"] else "CLOSED (default-deny)"
        print(f"\nPHASE: {row['phase']}   [target {state}]")
        print(f"  {row['intent']}")
        print(f"  Target tools ({len(row['targetTools'])}): "
              f"{', '.join(row['targetTools']) or '(none)'}")
        print(f"  Max matching permits for any child action: {row['maxMatchingPermits']}")
        for action, matching in sorted(row["permitCoverage"].items()):
            tool = action.split("___")[-1]
            d = row["decisions"][action]
            marker = "  <- governed write" if action in row["governedWritesCallable"] else ""
            print(f"    {tool:20s} permits={len(matching)} "
                  f"{'(' + ', '.join(matching) + ')' if matching else '(none)':52s}"
                  f" non-damaged -> {d['non_damaged']:5s} damaged -> {d['damaged']:5s}{marker}")
        if row["nonDamagedAllowed"]:
            all_safe = False
            print("  UNSAFE: governed write permitted with no restrictive control:")
            for action in row["nonDamagedAllowed"]:
                print(f"    {action}")
        else:
            print("  INVARIANT: no governed write is permitted without a "
                  "restrictive control")
    return all_safe


def _rollback_resource_ids(live: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Validate every captured write target before allowing the first update."""
    if (
        not isinstance(live.get("gateway"), dict)
        or live["gateway"].get("gatewayId") != EXPECTED_GATEWAY_ID
    ):
        raise CaptureError("Rollback snapshot does not identify the pinned gateway.")
    identities = {}
    for key, id_key, names in (
        ("targets", "targetId", EXPECTED_TARGET_NAMES),
        ("policies", "policyId", EXPECTED_POLICY_NAMES),
    ):
        resources = live.get(key)
        if not isinstance(resources, list) or len(resources) != len(names):
            raise CaptureError("Rollback snapshot has an incomplete or unexpected resource set.")
        indexed = {}
        for resource in resources:
            if not isinstance(resource, dict):
                raise CaptureError("Malformed rollback resource.")
            name, resource_id = resource.get("name"), resource.get(id_key)
            if (
                not isinstance(name, str) or name not in names or name in indexed
                or not isinstance(resource_id, str) or not resource_id.strip()
                or resource_id in indexed.values()
            ):
                raise CaptureError("Rollback resource identities are missing, duplicated or out of scope.")
            if key == "targets":
                if (
                    not isinstance(resource.get("targetConfiguration"), dict)
                    or not resource["targetConfiguration"]
                    or not isinstance(resource.get("credentialProviderConfigurations"), list)
                ):
                    raise CaptureError("Rollback target configuration is incomplete.")
            else:
                try:
                    statement = policy_statement(resource)
                except (AttributeError, TypeError):
                    statement = ""
                if not statement or resource.get("enforcementMode") not in {"ACTIVE", "LOG_ONLY"}:
                    raise CaptureError("Rollback policy definition or enforcement mode is incomplete.")
            indexed[name] = resource_id
        identities[key] = indexed
    return identities


def rollback(control: Any, directory: Path, *, sts: Any) -> None:
    """Restore a verified capture only to its still-existing pinned resources."""
    live = _load_capture(directory)
    captured_ids = _rollback_resource_ids(live)
    if (
        sts.get_caller_identity().get("Account") != EXPECTED_ACCOUNT
        or getattr(getattr(control, "meta", None), "region_name", None) != EXPECTED_REGION
    ):
        raise CaptureError("Rollback caller account or client region does not match the pinned scope.")
    current = read_live(control)
    if _rollback_resource_ids(current) != captured_ids:
        raise CaptureError("Rollback resource names/IDs no longer match the live pinned deployment.")

    for target in live["targets"]:
        print(f"  restoring target {target['name']}")
        control.update_gateway_target(
            gatewayIdentifier=EXPECTED_GATEWAY_ID,
            targetId=target["targetId"],
            name=target["name"],
            targetConfiguration=target["targetConfiguration"],
            credentialProviderConfigurations=target["credentialProviderConfigurations"],
        )
        status = _wait_target(control, target["targetId"])
        if status not in TERMINAL_OK:
            raise SystemExit("Rollback target update did not converge; capture retained.")
        print(f"      status: {status}")
    for policy in live["policies"]:
        statement = policy_statement(policy)
        print(f"  restoring policy {policy['name']}")
        _restore_policy(
            control, policy["policyId"], statement, policy["enforcementMode"],
        )
    print("rollback complete")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(pre: PreflightResult, plan: Dict[str, Any]) -> None:
    print("=== PREFLIGHT ===")
    for name, check in pre.checks.items():
        mark = "OK  " if check["ok"] else "STOP"
        print(f"  [{mark}] {name}")
        if not check["ok"]:
            print(f"          observed: {check['observed']}")
            print(f"          expected: {check['expected']}")
    print(f"\n  preflight: {'PASS' if pre.ok else 'FAIL — refusing to write'}")

    print("\n=== FOUR PHASES, ONE RESOURCE EACH ===")
    for index, entry in enumerate(plan["phases"], start=1):
        n_pol, n_tgt = len(entry["policyUpdates"]), len(entry["targetUpdates"])
        print(f"\n  Phase {index}: {entry['phase']}")
        print(f"    {entry['intent']}")
        print(f"    policy updates: {n_pol}    target updates: {n_tgt}")
        for update in entry["policyUpdates"]:
            print(f"      policy {update['policy']}  id={update['policyId']}")
            print(f"        policy status          : {update['status']}")
            print(f"        policy enforcementMode : {update['enforcementMode']} (preserved)")
            print(f"        before : {' '.join(update['before'].split())}")
            print(f"        after  : {' '.join(update['after'].split())}")
            print(f"        note   : {update['note']}")
        for update in entry["targetUpdates"]:
            print(f"      target {update['target']}  id={update['targetId']}")
            print(f"        status : {update['status']}")
            print(f"        before ({len(update['before'])}): {', '.join(update['before'])}")
            print(f"        after  ({len(update['after'])}): {', '.join(update['after'])}")
            if update.get("deferred"):
                print(f"        deferred (NOT published): {', '.join(update['deferred'])}")
            for norm in update.get("serviceNormalization") or []:
                print(f"        SERVICE-NORMALIZATION DELTA (declared, not drift):")
                print(f"          field    : {norm['field']}")
                print(f"          before   : {norm['before']}")
                print(f"          omitted  : {norm['omittedFromWrite']}")
                print(f"          sent     : {norm['sent']}")
                print(f"          reason   : {norm['reason']}")
                print(f"          pellier dependency    : {norm['pellierDependency']}")
                print(f"          governance dependency : {norm['governanceDependency']}")

    print("\n=== THREE STATE FIELDS, NEVER COLLAPSED ===")
    print("  policy status          (lifecycle)   CREATING | ACTIVE | UPDATING | *_FAILED")
    print("  policy enforcementMode (enforcement) ACTIVE | LOG_ONLY")
    print("  gateway policy mode    (enforcement) ENFORCE | LOG_ONLY")
    print(f"\n  gateway policy mode observed : {plan['gateway']['gatewayPolicyMode']}")
    print(f"  gateway policy mode changed  : {plan['gateway']['gatewayPolicyModeChanged']}")

    print("\n=== NOT TOUCHED ===")
    for item in plan["notTouched"]:
        print(f"  - {item}")
    print("\n=== OUT OF SCOPE FOR THESE FOUR PHASES ===")
    for name in plan["outOfScopeTargets"]:
        print(f"  - {name} (no policy names its actions; separate approval)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the phase")
    parser.add_argument("--phase", choices=PHASES, help="which phase to apply")
    parser.add_argument("--rollback", default="", help="restore from a rollback directory")
    parser.add_argument(
        "--out", default="/tmp/pellier-agentcore-direct-migration",
        help="Owned 0700 capture root, or a new directory under an existing parent.",
    )
    parser.add_argument(
        "--allow-wildcard-baseline",
        action="store_true",
        help=(
            "Required to apply restore-broad-permit. The historical wildcard permits "
            "any action published afterwards, which is the property that made the "
            "migration window unsafe. explicit-baseline-final is the intended end "
            "state; this flag exists for rollback."
        ),
    )
    args = parser.parse_args()

    _load_env()
    if args.rollback:
        # Reject untrusted files before even constructing SDK clients. Rollback
        # verifies again and consumes its own in-memory copy before any updates.
        _load_capture(Path(args.rollback))
    else:
        with _private_directory(Path(args.out), create=True):
            pass
    control, sts, lam, cfn = _clients()

    if args.rollback:
        rollback(control, Path(args.rollback), sts=sts)
        return 0

    canonical = validate_canonical()
    live = read_live(control)
    pre = preflight(control, sts, lam, cfn, live)
    plan = build_plan(live, canonical)

    out = _capture_run(Path(args.out), pre, plan, live, canonical)

    print_report(pre, plan)

    print("\n=== PER-PHASE EFFECTIVE AUTHORIZATION ===")
    phase_safe = print_phase_proof(plan)
    print(f"\n  every phase governance-safe: {'YES' if phase_safe else 'NO'}")

    print(f"\n  preflight : {out / 'preflight.json'}")
    print(f"  phases    : {out / 'phase-proof.json'}")
    print(f"  plan      : {out / 'plan.json'}")
    print(f"  rollback  : {out / 'rollback'}")

    if not args.apply:
        print("\nPLAN ONLY. Nothing was mutated. Re-run with --apply --phase <phase>.")
        return 0

    if not pre.ok:
        raise SystemExit("preflight failed; refusing to mutate AWS")
    if not args.phase:
        raise SystemExit("--apply requires --phase")

    if not phase_safe:
        raise SystemExit(
            "at least one phase leaves a callable sensitive action outside the "
            "damaged-only forbid; refusing to mutate AWS"
        )

    _load_capture(out / "rollback")
    entry = next((e for e in plan["phases"] if e["phase"] == args.phase), None)
    if entry is None:
        raise SystemExit(f"{args.phase} is not a phase in this plan")

    # `target-canonical` renames the tools the Cedar action ids are built from, so
    # it may only run while the whole target is closed. Verified against live
    # state, not against an assumption that phase 1 was run.
    if args.phase == "target-canonical":
        # The rename may only happen while NO PERMIT can reach the target. That is
        # the boundary — not the target-group forbid, which was measured not to
        # follow a schema change and is defence in depth only. Verified against
        # live policy definitions, never against an assumption that Phase A ran.
        live_now = read_live(control)
        target = next(
            (x for x in live_now["targets"] if x["name"] == RETURN_TARGET_NAME), None
        )
        if target is None:
            raise SystemExit(f"live gateway has no target named {RETURN_TARGET_NAME}")
        current = [f"{RETURN_TARGET_NAME}___{n}" for n in _tool_names(target) if n]
        canonical_ids = [
            f"{RETURN_TARGET_NAME}___{RETIRED_TO_CURRENT.get(n, n)}"
            for n in _tool_names(target) if n
        ]
        offenders = []
        for policy in live_now["policies"]:
            statement = policy_statement(policy)
            parsed = parse_statement(policy["name"], statement, tuple(current))
            if parsed.effect != "permit":
                continue
            # Check BOTH the current ids and the ids this phase is about to
            # publish: a permit that would match the canonical name is exactly
            # what must not exist before the rename.
            for action in set(current) | set(canonical_ids):
                if parsed.covers(action):
                    offenders.append(f"{policy['name']} -> {action}")
        if offenders:
            raise SystemExit(
                "refusing to rename the target: a permit can still reach it, so the "
                "renamed actions would be callable the instant they exist.\n  "
                + "\n  ".join(sorted(offenders))
                + "\nRun --phase default-deny-quiesce first."
            )
        for policy in live_now["policies"]:
            if policy.get("status") not in LIFECYCLE_TERMINAL_OK:
                raise SystemExit(
                    f"refusing to rename the target: policy {policy['name']} status "
                    f"is {policy.get('status')}, not ACTIVE."
                )
            if policy.get("enforcementMode") != "ACTIVE":
                raise SystemExit(
                    f"refusing to rename the target: policy {policy['name']} "
                    f"enforcementMode is {policy.get('enforcementMode')}."
                )

    # `unquiesce` reopens the target, so it may only run once the restrictive
    # control already names the canonical action. Checked against live state
    # rather than against an assumption about what earlier phases did.
    # The unquiesce is `restore-broad-permit`: it is the phase that lets a permit
    # reach the target again. Keyed on the live phase name — an earlier version
    # still said "unquiesce", a name no longer in PHASES, so the guard could never
    # fire and the most dangerous phase was the only unguarded one.
    # Phase C repoints the restrictive rule. It must happen while the target is
    # closed, so a bad UpdatePolicy cannot expose anything.
    # Cross-check the derived broad permit against the earliest pre-migration capture
    # available on this machine, before any write.
    root = Path(args.out)
    for candidate in sorted(p for p in root.glob("*") if p.is_dir()):
        assert_broad_baseline_matches_capture(candidate)
        break

    if args.phase == WILDCARD_PHASE and not args.allow_wildcard_baseline:
        raise SystemExit(
            f"refusing to run {WILDCARD_PHASE} without --allow-wildcard-baseline.\n"
            "  The historical wildcard permit authorizes any action published after it, "
            "which is the property that made this migration's own window unsafe and "
            "would silently authorize a future issue_credit on publication alone.\n"
            "  The intended end state is --phase explicit-baseline-final: 12 explicit "
            "actions, with the return action governed by its dedicated pair and a "
            "future tool denied by default."
        )

    # The FINAL authorization phase. It reopens escalation, so it takes preconditions —
    # but NOT `_require_closed_canonical_target`, which asserts zero matching permits.
    # The damaged permit is deliberately active by this point, so that gate would be
    # both wrong and unpassable here. What must hold is that the dedicated return pair
    # is already canonical, and that the baseline is still the narrowed list.
    if args.phase == "explicit-baseline-final":
        live_now = read_live(control)
        canonical_id = f"{RETURN_TARGET_NAME}___{RETIRED_TO_CURRENT['process_return']}"
        expected = {
            QUIESCE_POLICY_NAME: ("permit", (canonical_id,), "damaged_only"),
            CONTROL_POLICY_NAME: ("forbid", (canonical_id,), "not_damaged"),
        }
        for name, want in expected.items():
            found = next(
                (p for p in live_now["policies"] if p["name"] == name), None
            )
            if found is None:
                raise SystemExit(f"live policy engine has no policy named {name}")
            parsed = parse_statement(
                name, policy_statement(found)
            )
            got = (parsed.effect, parsed.actions, parsed.condition)
            if got != want:
                raise SystemExit(
                    f"refusing to run {args.phase}: {name} is {got}, expected {want}. "
                    "The dedicated return pair must be canonical before the baseline "
                    "reopens the rest of the target."
                )
            if parsed.groups:
                raise SystemExit(
                    f"refusing to run {args.phase}: {name} still names a target action "
                    f"group {parsed.groups}."
                )
        baseline_live = next(
            (p for p in live_now["policies"] if p["name"] == BASELINE_POLICY_NAME), None
        )
        baseline_parsed = parse_statement(
            BASELINE_POLICY_NAME,
            policy_statement(baseline_live or {}),
        )
        if baseline_parsed.actions is None:
            raise SystemExit(
                f"refusing to run {args.phase}: the baseline is already a wildcard. "
                "Narrow it first, or this phase would tighten authorization without "
                "the quiesce proof behind it."
            )

    if args.phase == "return-forbid-canonical":
        _require_closed_canonical_target(control, args.phase)

    # Phase D is the DAMAGED-RETURN REOPEN and Phase E is the full unquiesce. Both
    # let a permit reach the target, so both take the same preconditions, checked
    # against policy CONTENT — never a policy name, never createdAt, never target
    # action-group membership.
    if args.phase in ("allow-damaged-canonical", "restore-broad-permit"):
        live_now = _require_closed_canonical_target(control, args.phase)
        control_live = next(
            (p for p in live_now["policies"] if p["name"] == CONTROL_POLICY_NAME), None
        )
        if control_live is None:
            raise SystemExit(f"live policy engine has no policy named {CONTROL_POLICY_NAME}")
        statement = policy_statement(control_live)
        parsed = parse_statement(CONTROL_POLICY_NAME, statement)
        canonical_id = f"{RETURN_TARGET_NAME}___{RETIRED_TO_CURRENT['process_return']}"
        if parsed.effect != "forbid":
            raise SystemExit(
                f"refusing to run {args.phase}: {CONTROL_POLICY_NAME} is a "
                f"{parsed.effect}, not a forbid."
            )
        if parsed.actions != (canonical_id,):
            raise SystemExit(
                f"refusing to run {args.phase}: {CONTROL_POLICY_NAME} names "
                f"{parsed.actions}, not exactly ({canonical_id},). Reopening now "
                "would leave the canonical return action permitted with no "
                "restrictive control. Run --phase return-forbid-canonical first."
            )
        if parsed.condition != "not_damaged":
            raise SystemExit(
                f"refusing to run {args.phase}: {CONTROL_POLICY_NAME} "
                f"condition parsed as {parsed.condition!r}, not the damaged-only "
                "rule. A rename must not have altered the guard."
            )
        # ORDERING GUARD, for the full unquiesce only. Phase D is the write that
        # REPLACES the group forbid, so it must not refuse on its presence; Phase E
        # must refuse, because after Phase C that stale group forbid began matching
        # the canonical children (see the recompilation finding in the module
        # docstring). Restoring the broad permit first would leave the target closed
        # while looking like a successful unquiesce, and would make availability
        # depend on an undocumented group-compilation behaviour.
        stale_group = next(
            (p for p in live_now["policies"] if p["name"] == QUIESCE_POLICY_NAME), None
        )
        if args.phase == "restore-broad-permit" and stale_group is not None:
            stale_parsed = parse_statement(
                QUIESCE_POLICY_NAME,
                policy_statement(stale_group),
            )
            if stale_parsed.effect == "forbid" and stale_parsed.groups:
                raise SystemExit(
                    f"refusing to restore the broad permit: {QUIESCE_POLICY_NAME} "
                    f"still holds a target-group forbid on {stale_parsed.groups}. "
                    "Restoring the permit would not reliably reopen the target and "
                    "would make availability depend on group-compilation behaviour. "
                    "The reopening sequence needs a revised, approved design."
                )

        baseline_live = next(
            (p for p in live_now["policies"] if p["name"] == BASELINE_POLICY_NAME), None
        )
        baseline_parsed = parse_statement(
            BASELINE_POLICY_NAME,
            policy_statement(baseline_live or {}),
        )
        if baseline_parsed.actions is None:
            raise SystemExit(
                f"refusing to run {args.phase}: the baseline permit is already broad, "
                "so the target is not currently closed."
            )

    # Phase E additionally requires that Phase D has landed: the canonical damaged
    # permit must be in place before the rest of the target reopens, so that the
    # first thing the broad permit widens is a path whose restrictive control has
    # already been proven.
    if args.phase == "restore-broad-permit":
        allow_live = next(
            (p for p in live_now["policies"] if p["name"] == QUIESCE_POLICY_NAME), None
        )
        if allow_live is None:
            raise SystemExit(f"live policy engine has no policy named {QUIESCE_POLICY_NAME}")
        allow_parsed = parse_statement(
            QUIESCE_POLICY_NAME,
            policy_statement(allow_live),
        )
        canonical_id = f"{RETURN_TARGET_NAME}___{RETIRED_TO_CURRENT['process_return']}"
        if (allow_parsed.effect, allow_parsed.actions, allow_parsed.condition) != (
            "permit", (canonical_id,), "damaged_only"
        ):
            raise SystemExit(
                "refusing to restore the broad permit: "
                f"{QUIESCE_POLICY_NAME} is not yet the canonical damaged-only permit "
                f"(effect={allow_parsed.effect}, actions={allow_parsed.actions}, "
                f"condition={allow_parsed.condition!r}). Run "
                "--phase allow-damaged-canonical first and prove the three governed "
                "outcomes before reopening the rest of the target."
            )

    assert_no_mode_drift(control)

    print(f"\n=== APPLYING PHASE: {args.phase} ===")
    print(f"  {entry['intent']}")
    for update in entry["policyUpdates"]:
        apply_policy_update(control, update, phase=args.phase, live=read_live(control))
    for update in entry["targetUpdates"]:
        apply_one_target(control, live, update)

    assert_no_mode_drift(control)
    print("\nphase complete. Verify against the real Gateway before the next phase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
