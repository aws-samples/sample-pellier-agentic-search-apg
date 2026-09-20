#!/usr/bin/env python3
"""Plan, and refuse to apply, the live baseline's restock alignment.

The divergence
--------------

Audit finding P1-04. The live policy engine's single baseline permit names every action
on the three unmigrated Gateway targets, and one of those is the restock tool. A fresh
provision from this branch does the opposite: ``baseline_permit_workshop_tools`` names 13
action ids and leaves the restock action out, so it is denied by default until something
authorizes it deliberately.

Both shapes are internally coherent. They are not the same posture, and the more
permissive one is live. An operator on the live environment can attempt a restock and
receive an ALLOW where a fresh environment produces a Cedar DENY, which is the difference
between "the workshop teaches default-deny" and "the workshop describes default-deny".

Why this script does not apply anything
---------------------------------------

It makes no control-plane write and does not import the migration's apply path. Aligning
a live policy is a decision with an audience: the Gateway is shared, the change alters a
real authorization outcome, and the correct moment is a maintenance window with the
migration's own preflight and rollback in hand. So this produces the plan, the two
hashes, the semantic diff, and the exact rollback statement, and stops.

Applying it later is `migrate_gateway_vocabulary.py`'s job: it owns the environment hard
stops (`scripts/deploy/ownership.py`), the policy waiters, the well-formedness assertion
and `rollback()`. This script exists so the decision can be reviewed before that runs.

Usage
-----

    python3 scripts/deploy/plan_restock_alignment.py
    python3 scripts/deploy/plan_restock_alignment.py --json audit/restock-alignment.json

    # No AWS available: show the desired shape and the reasoning only.
    python3 scripts/deploy/plan_restock_alignment.py --offline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "deploy"))

import migrate_gateway_vocabulary as MIG  # noqa: E402
from gateway_tool_schemas import workshop_target_tools  # noqa: E402

# The tool whose authorization diverges. Named once; both the live action id and the
# fresh action id are derived from it, because the two vocabularies differ.
RESTOCK_TOOL_CANONICAL = "restock_inventory"
PLACEHOLDER_GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/fresh"

ACTION_RE = re.compile(r'AgentCore::Action::"([^"]+)"')


def _sha(statement: str) -> str:
    """Hash of the NORMALISED statement.

    Whitespace differences between a hand-edited console value and a generated one are
    not a semantic change, and a hash that reports them as one makes the comparison
    useless. `MIG._norm` is the same normaliser the migration's own equality checks use.
    """
    return hashlib.sha256(MIG._norm(statement).encode("utf-8")).hexdigest()


def desired_fresh_action_ids() -> List[str]:
    """The action ids a FRESH stack's baseline permit names, from the renderer's source."""
    from render_agentcore_project import baseline_policies

    # Only action ids are read here; any well-formed ARN renders the same set.
    for policy in baseline_policies(gateway_arn=PLACEHOLDER_GATEWAY_ARN):
        if policy["name"] == "baseline_permit_workshop_tools":
            return sorted(set(ACTION_RE.findall(str(policy["statement"]))))
    raise SystemExit("the fresh renderer no longer emits baseline_permit_workshop_tools")


def fresh_restock_action_id() -> Optional[str]:
    """Where a fresh stack publishes the restock tool, so the diff names a real id."""
    for surface, tools in workshop_target_tools().items():
        if RESTOCK_TOOL_CANONICAL in tools:
            return f"{surface}___{RESTOCK_TOOL_CANONICAL}"
    return None


def live_restock_action_ids(live: Dict[str, Any]) -> List[str]:
    """Live action ids for the restock capability, under either vocabulary.

    The three unmigrated targets still publish the retired names, so matching on the
    canonical name alone would find nothing and the plan would claim there is no
    divergence. The retired equivalent is read from the migration's own map rather than
    written out here.
    """
    retired = [
        old for old, new in MIG.RETIRED_TO_CURRENT.items()
        if new == RESTOCK_TOOL_CANONICAL
    ]
    wanted = {RESTOCK_TOOL_CANONICAL, *retired}
    return sorted(
        f"{target.get('name')}___{tool}"
        for target in live["targets"]
        for tool in MIG._tool_names(target)
        if tool in wanted
    )


def _baseline_policy(live: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        policy for policy in live["policies"]
        if "baseline" in str(policy.get("name", "")).lower()
    ]
    if len(candidates) != 1:
        raise SystemExit(
            "expected exactly one live baseline policy, found "
            f"{[p.get('name') for p in candidates]}"
        )
    return candidates[0]


def _statement_of(policy: Dict[str, Any]) -> str:
    definition = policy.get("definition") or {}
    static = definition.get("static") or {}
    return MIG.policy_statement(policy) or str(static.get("statement") or policy.get("statement") or "")


def plan(live: Dict[str, Any]) -> Dict[str, Any]:
    policy = _baseline_policy(live)
    current = _statement_of(policy)
    if not current:
        raise SystemExit(f"could not read a statement from policy {policy.get('name')}")

    current_ids = sorted(set(ACTION_RE.findall(current)))
    restock_live = live_restock_action_ids(live)
    remove = [action for action in current_ids if action in set(restock_live)]
    desired_ids = [action for action in current_ids if action not in set(remove)]

    members = ",\n        ".join(f'AgentCore::Action::"{a}"' for a in desired_ids)
    desired = (
        "permit(\n    principal,\n    action in [\n        "
        f"{members}\n    ],\n    {MIG.gateway_resource()}\n);"
    )

    fresh_ids = desired_fresh_action_ids()
    return {
        "event": "existing-live-restock-alignment",
        "applied": False,
        "policy": {
            "name": policy.get("name"),
            "policyId": policy.get("policyId"),
            "enforcementMode": policy.get("enforcementMode"),
        },
        "current": {
            "statement": current,
            "sha256": _sha(current),
            "actionCount": len(current_ids),
            "actions": current_ids,
        },
        "desired": {
            "statement": desired,
            "sha256": _sha(desired),
            "actionCount": len(desired_ids),
            "actions": desired_ids,
        },
        "semanticDiff": {
            "removedActions": remove,
            "addedActions": [],
            "effectChanged": False,
            "conditionChanged": False,
            "consequence": (
                "the restock capability loses its matching permit, so a call becomes a "
                "Cedar DENY by default rather than an ALLOW. No other action's "
                "authorization changes."
                if remove else
                "no change: the live baseline already does not permit the restock action"
            ),
        },
        "freshComparison": {
            "freshBaselineActionCount": len(fresh_ids),
            # None: a fresh stack does not publish the restock tool on the shopper
            # Gateway, so there is no action id for any policy to permit.
            "freshRestockActionId": fresh_restock_action_id(),
            "freshPublishesRestock": fresh_restock_action_id() is not None,
            "freshPermitsRestock": fresh_restock_action_id() in set(fresh_ids),
            "convergesOnCount": len(desired_ids) == len(fresh_ids),
        },
        "rollback": {
            "method": (
                "re-apply the captured statement below to the same policyId, then "
                "confirm the hash matches currentSha256"
            ),
            "statement": current,
            "sha256": _sha(current),
        },
        "applyWith": (
            "migrate_gateway_vocabulary.py, which owns the environment hard stops, the "
            "policy waiters, the Cedar well-formedness assertion and rollback(). This "
            "script never writes."
        ),
    }


def offline_plan() -> Dict[str, Any]:
    """What can be stated without reading the live control plane."""
    fresh_ids = desired_fresh_action_ids()
    return {
        "event": "existing-live-restock-alignment",
        "applied": False,
        "offline": True,
        "freshComparison": {
            "freshBaselineActionCount": len(fresh_ids),
            "freshBaselineActions": fresh_ids,
            "freshRestockActionId": fresh_restock_action_id(),
            "freshPublishesRestock": fresh_restock_action_id() is not None,
            "freshPermitsRestock": fresh_restock_action_id() in set(fresh_ids),
        },
        "intent": (
            "remove the restock action id from the live baseline permit so the live "
            "posture matches the fresh one, where restock is published and unpermitted"
        ),
        "note": (
            "current and desired hashes require the live statement. Re-run without "
            "--offline against the expected account to compute them."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="PATH", help="write the plan")
    parser.add_argument("--offline", action="store_true",
                        help="no AWS call; show the fresh side and the intent only")
    args = parser.parse_args()

    if args.offline:
        result = offline_plan()
    else:
        MIG._load_env()
        control, sts, lam, cfn = MIG._clients()
        live = MIG.read_live(control)
        pre = MIG.preflight(control, sts, lam, cfn, live)
        if not pre.ok:
            print("preflight failed; refusing to plan against an unexpected environment",
                  file=sys.stderr)
            print(json.dumps(pre.checks, indent=2, default=str), file=sys.stderr)
            return 2
        result = plan(live)

    print(json.dumps(result, indent=2, default=str))
    if args.json:
        target = pathlib.Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(f"\nwritten to {args.json}", file=sys.stderr)
    print("\nPLAN ONLY. Nothing was applied.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
