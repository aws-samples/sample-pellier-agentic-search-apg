#!/usr/bin/env python3
"""What a fresh provision would publish and authorize, derived from source.

Why this is a script and not a document
---------------------------------------

The pre-handoff audit produced these numbers by hand and they were wrong within a day of
being written, because the hand-written copy could not notice a change to
``gateway_tool_schemas.py``. Everything below is read out of the two modules that actually
drive a provision:

  * ``scripts/deploy/gateway_tool_schemas.py`` - the canonical tool vocabulary, which of
    those tools this workshop iteration defers, and the target each one is published on.
  * ``scripts/deploy/render_agentcore_project.py::baseline_policies`` - the Cedar a fresh
    stack is created with.

So the answer to "how many tools would a clean account see" is computed, never asserted.
``pellier/backend/tests/test_fresh_policy_set.py`` pins the same values, which is what
makes a drift fail in CI rather than in a room.

Usage
-----

    python3 scripts/describe_workshop_publication.py
    python3 scripts/describe_workshop_publication.py --json audit/handoff/publication.json
    python3 scripts/describe_workshop_publication.py --policies-json out/fresh-policy-set.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List

REPO = pathlib.Path(__file__).resolve().parents[1]
DEPLOY = REPO / "scripts" / "deploy"
sys.path.insert(0, str(DEPLOY))

from gateway_tool_schemas import (  # noqa: E402
    TOOL_SCHEMAS,
    WORKSHOP_DEFERRED_TOOLS,
    canonical_tool_names,
    workshop_published_tools,
    workshop_target_tools,
)
from render_agentcore_project import baseline_policies  # noqa: E402

PLACEHOLDER_GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/placeholder"

ACTION_RE = re.compile(r'AgentCore::Action::"([^"]+)"')

# Vocabulary a Cedar condition uses when it binds caller identity to tool input. Recorded
# per policy because the presence of one in the BASELINE is what would silently ship the
# Lab 4 answer on a fresh stack.
OWNERSHIP_TOKENS = ("getTag", "hasTag", "customer_id", "principal.")
REASON_TOKENS = ("reason",)


def tools_view() -> Dict[str, Any]:
    canonical = sorted(canonical_tool_names())
    published = sorted(workshop_published_tools())
    targets = workshop_target_tools()
    return {
        "canonicalCount": len(canonical),
        "canonical": canonical,
        "deferred": sorted(WORKSHOP_DEFERRED_TOOLS),
        "publishedCount": len(published),
        "published": published,
        "byTarget": {surface: sorted(tools) for surface, tools in sorted(targets.items())},
        "byTargetCount": {surface: len(tools) for surface, tools in sorted(targets.items())},
    }


def policies_view() -> Dict[str, Any]:
    # Tool-specific statements pin the Gateway by ARN, which this AWS-free view
    # does not have; the placeholder keeps the statement shape reviewable.
    policies = baseline_policies(gateway_arn=PLACEHOLDER_GATEWAY_ARN)
    described: Dict[str, Any] = {}
    for policy in policies:
        statement = str(policy.get("statement", ""))
        described[str(policy["name"])] = {
            "effect": "forbid" if statement.lstrip().startswith("forbid") else "permit",
            "enforcementMode": policy.get("enforcementMode", ""),
            "conditional": ("when {" in statement) or ("unless {" in statement),
            "actionForm": (
                "action in [...]" if "action in [" in statement
                else "action ==" if "action ==" in statement
                else "unqualified"
            ),
            "actions": sorted(set(ACTION_RE.findall(statement))),
            "namesOwnership": any(token in statement for token in OWNERSHIP_TOKENS),
            "namesReason": any(token in statement for token in REASON_TOKENS),
        }
    permitted = {
        action
        for entry in described.values()
        if entry["effect"] == "permit"
        for action in entry["actions"]
    }
    return {
        "freshPolicyCount": len(policies),
        "freshPolicies": described,
        "permittedActionCount": len(permitted),
        "permittedActions": sorted(permitted),
        "wildcardPermit": any(
            entry["effect"] == "permit" and entry["actionForm"] == "unqualified"
            for entry in described.values()
        ),
    }


def unauthorized_published_tools(tools: Dict[str, Any], policies: Dict[str, Any]) -> List[str]:
    """Published tools no baseline permit reaches.

    Default-deny means a published-but-unpermitted tool is a DENY, not a hole. That is the
    intended shape for ``give_store_credit`` (Lab 4 owns it) and ``get_tickets``
    (operator-side, gated separately), so this is reported rather than treated as an error.
    """
    permitted_short = {
        action.split("___", 1)[-1] for action in policies["permittedActions"]
    }
    return sorted(set(tools["published"]) - permitted_short)


def describe() -> Dict[str, Any]:
    tools = tools_view()
    policies = policies_view()
    return {
        "tools": tools,
        "policies": policies,
        "publishedWithoutBaselinePermit": unauthorized_published_tools(tools, policies),
        "derivedFrom": [
            "scripts/deploy/gateway_tool_schemas.py",
            "scripts/deploy/render_agentcore_project.py::baseline_policies",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="PATH", help="write the whole description")
    parser.add_argument("--tools-json", metavar="PATH", help="write only the tool contract")
    parser.add_argument("--policies-json", metavar="PATH", help="write only the policy set")
    args = parser.parse_args()

    result = describe()
    tools = result["tools"]
    policies = result["policies"]

    print("TOOL PUBLICATION")
    print(f"  canonical vocabulary : {tools['canonicalCount']}")
    print(f"  deferred this round  : {len(tools['deferred'])}  {tools['deferred']}")
    print(f"  published to Gateway : {tools['publishedCount']}")
    for surface, count in tools["byTargetCount"].items():
        print(f"    {surface:44} {count}")
    print(f"  Gateway targets      : {len(TOOL_SCHEMAS)}")

    print("\nBASELINE AUTHORIZATION")
    print(f"  policies on a fresh stack : {policies['freshPolicyCount']}")
    for name, entry in policies["freshPolicies"].items():
        flags = []
        if entry["conditional"]:
            flags.append("conditional")
        if entry["namesOwnership"]:
            flags.append("names-ownership")
        if entry["namesReason"]:
            flags.append("names-reason")
        print(f"    {name:38} {entry['effect']:6} {entry['actionForm']:16} "
              f"{len(entry['actions']):>2} action(s)  {' '.join(flags)}")
    print(f"  distinct permitted actions: {policies['permittedActionCount']}")
    print(f"  wildcard permit present   : {policies['wildcardPermit']}")

    print("\nPUBLISHED WITHOUT A BASELINE PERMIT (default-deny, by design)")
    for name in result["publishedWithoutBaselinePermit"]:
        print(f"  {name}")

    for path, payload in (
        (args.json, result),
        (args.tools_json, tools),
        (args.policies_json, policies),
    ):
        if path:
            target = pathlib.Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2) + "\n")
            print(f"\nwritten to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
