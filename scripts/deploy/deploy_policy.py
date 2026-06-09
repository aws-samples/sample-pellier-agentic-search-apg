#!/usr/bin/env python3
"""
Deploy the managed AgentCore Policy Engine for Pellier (Act II — the 4th pillar).

Pellier's narrative is "everything is managed AgentCore — Runtime, Memory,
Gateway, AND Policy." This script makes the Policy pillar real: it creates a
managed AgentCore **Policy Engine** (a container for Cedar policies), adds the
single Cedar policy that gates ``process_return``, and attaches the engine to
the existing AgentCore Gateway in ENFORCE mode. From then on the Gateway
intercepts every tool call and evaluates it against Cedar BEFORE the Lambda
runs — argument-aware, default-deny, forbid-wins — the managed equivalent of the
old local ``BeforeToolCall`` hook (now removed).

The contract here (boto3 ``bedrock-agentcore-control``) mirrors the sibling
dat403 workshop's verified, working ``modules/06/deploy_policy.py``:
  - ``create_policy_engine(name, description)`` → standalone engine (NOT attached
    at create); poll ``get_policy_engine`` until ACTIVE.
  - ``create_policy(..., definition={"cedar":{"statement": <cedar>}})`` → direct
    Cedar (deterministic; we don't use the natural-language generation path);
    poll ``get_policy`` until ACTIVE.
  - ``update_gateway(..., policyEngineConfiguration={"mode":"ENFORCE","arn":...})``
    → MUST re-pass the gateway's existing name/roleArn/protocolType/authorizerType
    /authorizerConfiguration or the update wipes them.

Cedar action spelling is ``<gateway-target-name>___<tool-name>`` (the verified
dat403 contract: target name, triple underscore) — for Pellier process_return
that is ``pellier-concierge-experience-target___process_return``. The exact
identifier the GA engine accepts has shifted across API revisions (early builds
took the bare ``target___tool`` token; some return an ARN-qualified action), so
this script is **self-correcting**: it tries the best-guess action and, if the
engine rejects it with a ``did you mean `…``` hint, retries once with the exact
token the engine suggests. The accepted form is printed for the record.

Usage:
    uv run scripts/deploy/deploy_policy.py \
        --gateway-id <gateway-id> \
        --gateway-arn <gateway-arn> \
        --region us-west-2 \
        [--experience-target-name pellier-concierge-experience-target] \
        [--mode ENFORCE]

Prints the policy engine id on the last line as ``POLICY_ENGINE_ID=<id>`` so the
caller (provision_agentcore_end_to_end.py / deploy_all.sh) can capture it into
``.env`` as ``AGENTCORE_POLICY_ENGINE_ID``.
"""

import argparse
import re
import sys
import time

import boto3

ENGINE_NAME = "pellier_policy_engine"

# The Gateway target whose process_return tool the Cedar policy gates. The
# action identifier the engine expects is built from this (see _action_token).
EXPERIENCE_TARGET = "pellier-concierge-experience-target"


def _extract_suggested_action(reason):
    """Pull the engine's suggested action token out of a CREATE_FAILED reason.

    On an ``unrecognized action`` failure the engine returns a hint like
    ``did you mean `AgentCore::Action::"…"```. We parse that quoted token so we
    can retry with the exact identifier the engine accepts, instead of guessing
    target-vs-function name or underscore count across API revisions.
    Returns the inner identifier string (without the ``AgentCore::Action::"``
    wrapper / trailing quote) or None.
    """
    text = reason if isinstance(reason, str) else repr(reason)
    m = re.search(r'did you mean\s+`?AgentCore::Action::"([^"`]+)"?', text)
    if m:
        return m.group(1).rstrip('"`')
    return None


def wait_for_policy_engine(client, engine_id, max_wait=180, interval=10):
    """Wait for a policy engine to become ACTIVE."""
    elapsed = 0
    while elapsed < max_wait:
        resp = client.get_policy_engine(policyEngineId=engine_id)
        status = resp.get("status", "UNKNOWN")
        print(f"  Policy engine status: {status} ({elapsed}s)")
        if status == "ACTIVE":
            return
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Policy engine {engine_id} did not become ACTIVE within {max_wait}s")


class PolicyCreateFailed(RuntimeError):
    """A policy reached CREATE_FAILED. Carries the engine's reason text so the
    caller can inspect it (e.g. to extract a ``did you mean`` action hint)."""

    def __init__(self, policy_id, reason):
        self.policy_id = policy_id
        self.reason = reason
        super().__init__(f"Policy {policy_id} creation failed: {reason}")


def wait_for_policy(client, engine_id, policy_id, max_wait=180, interval=10):
    """Wait for a policy to become ACTIVE; raise PolicyCreateFailed on CREATE_FAILED."""
    elapsed = 0
    while elapsed < max_wait:
        resp = client.get_policy(policyEngineId=engine_id, policyId=policy_id)
        status = resp.get("status", "UNKNOWN")
        print(f"  Policy status: {status} ({elapsed}s)")
        if status == "ACTIVE":
            return
        if status == "CREATE_FAILED":
            reason = resp.get("statusReasons", resp.get("failureReason", "Unknown error"))
            raise PolicyCreateFailed(policy_id, reason)
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Policy {policy_id} did not become ACTIVE within {max_wait}s")


def create_or_reuse_engine(client, name=ENGINE_NAME):
    """Create the policy engine, or reuse it by name if it already exists."""
    try:
        for engine in client.list_policy_engines().get("policyEngines", []):
            if engine.get("name") == name:
                print(f"  Reusing existing policy engine: {engine['policyEngineId']}")
                return engine["policyEngineId"], engine["policyEngineArn"]
    except Exception:
        pass

    print(f"  Creating policy engine: {name}")
    resp = client.create_policy_engine(
        name=name,
        description="Pellier workshop policy engine — gates process_return to damaged-only via Cedar",
    )
    engine_id = resp["policyEngineId"]
    engine_arn = resp["policyEngineArn"]
    print(f"  Engine ID: {engine_id}")
    wait_for_policy_engine(client, engine_id)
    return engine_id, engine_arn


def _reuse_active_policy_by_name(client, engine_id, name):
    """Return the policyId of an ACTIVE policy with this name, or None.

    Skips CREATE_FAILED leftovers so a prior bad-action attempt doesn't get
    treated as a successful reuse."""
    for p in client.list_policies(policyEngineId=engine_id).get("policies", []):
        if p["name"] == name and p.get("status") not in ("CREATE_FAILED", "FAILED"):
            return p["policyId"]
    return None


def _delete_failed_policy(client, engine_id, policy_id, name):
    """Best-effort delete of a CREATE_FAILED policy so its name frees up for retry."""
    try:
        client.delete_policy(policyEngineId=engine_id, policyId=policy_id)
        print(f"    Removed failed policy {name} ({policy_id}) before retry")
    except Exception as exc:  # noqa: BLE001 — delete is best-effort
        print(f"    Warning: could not delete failed policy {policy_id}: {exc}")


def create_or_reuse_policy(client, engine_id, name, description, cedar_statement):
    """Create a Cedar policy, or reuse it by name on conflict."""
    try:
        resp = client.create_policy(
            policyEngineId=engine_id,
            name=name,
            description=description,
            validationMode="IGNORE_ALL_FINDINGS",
            definition={"cedar": {"statement": cedar_statement}},
        )
        policy_id = resp["policyId"]
        wait_for_policy(client, engine_id, policy_id)
        return policy_id
    except client.exceptions.ConflictException:
        existing = _reuse_active_policy_by_name(client, engine_id, name)
        if existing:
            print(f"    Reusing existing policy: {name}")
            return existing
        raise


def create_action_policy_with_fallback(
    client, engine_id, name, description, cedar_builder, candidate_actions
):
    """Create a Cedar policy whose statement references an AgentCore::Action, with
    a self-correcting fallback over candidate action identifiers.

    ``cedar_builder(action_token)`` returns the full Cedar string for a given
    action identifier. ``candidate_actions`` is the ordered best-guess list
    (e.g. target-name+triple, then target-name+double). On a CREATE_FAILED with
    an ``unrecognized action`` hint, the engine's suggested token is parsed and
    appended as the next candidate — so we converge on whatever the live API
    accepts regardless of which underscore/name convention this revision wants.
    Returns (policy_id, accepted_action_token).
    """
    # Reuse an already-ACTIVE policy with this name (idempotent re-runs).
    existing = _reuse_active_policy_by_name(client, engine_id, name)
    if existing:
        print(f"    Reusing existing policy: {name}")
        return existing, None

    tried = []
    queue = list(candidate_actions)
    while queue:
        action_token = queue.pop(0)
        if action_token in tried:
            continue
        tried.append(action_token)
        cedar = cedar_builder(action_token)
        try:
            resp = client.create_policy(
                policyEngineId=engine_id,
                name=name,
                description=description,
                validationMode="IGNORE_ALL_FINDINGS",
                definition={"cedar": {"statement": cedar}},
            )
            policy_id = resp["policyId"]
            wait_for_policy(client, engine_id, policy_id)
            print(f"    ✅ accepted action identifier: {action_token}")
            return policy_id, action_token
        except client.exceptions.ConflictException:
            reused = _reuse_active_policy_by_name(client, engine_id, name)
            if reused:
                print(f"    Reusing existing policy: {name}")
                return reused, None
            raise
        except PolicyCreateFailed as exc:
            suggested = _extract_suggested_action(exc.reason)
            print(f"    ✗ action '{action_token}' rejected; "
                  f"engine hint: {suggested or '(none)'}")
            # Free the name (the failed policy still occupies it) before retry.
            for p in client.list_policies(policyEngineId=engine_id).get("policies", []):
                if p["name"] == name and p.get("status") in ("CREATE_FAILED", "FAILED"):
                    _delete_failed_policy(client, engine_id, p["policyId"], name)
            if suggested and suggested not in tried and suggested not in queue:
                queue.append(suggested)
    raise RuntimeError(
        f"Policy {name}: no candidate action identifier was accepted "
        f"(tried: {', '.join(tried)})"
    )


def create_pellier_policies(client, engine_id, gateway_arn, experience_target):
    """Create Pellier's Cedar policies.

    The headline rule is a single ``forbid`` on process_return unless the return
    reason is 'damaged' — Cedar default-deny + forbid-wins means this is the
    whole gate. We ALSO add an explicit ``permit`` for the damaged path so the
    Atelier Policy surface can show both halves of the decision (and so the
    intent reads clearly to a 400-level attendee inspecting the engine).

    ``experience_target`` is the Gateway TARGET name (e.g.
    ``pellier-concierge-experience-target``), which is what the Gateway
    registers tools under. We try the dat403-verified ``target___tool`` (triple
    underscore) form first, then ``target__tool`` (double), and finally defer to
    whatever exact token the engine suggests via its ``did you mean`` hint.
    """
    gw = f'AgentCore::Gateway::"{gateway_arn}"'

    # Ordered best-guesses for the action identifier. The fallback creator will
    # also try the engine's own suggested token if all of these are rejected.
    candidate_actions = [
        f"{experience_target}___process_return",  # dat403-verified: target + triple
        f"{experience_target}__process_return",   # target + double (registered tool form)
    ]

    def forbid_builder(action_token):
        return (
            f'forbid(principal, action == AgentCore::Action::"{action_token}", resource == {gw})\n'
            'when {\n'
            '  !(context.input has reason) || context.input.reason != "damaged"\n'
            '};'
        )

    def permit_builder(action_token):
        return (
            f'permit(principal, action == AgentCore::Action::"{action_token}", resource == {gw})\n'
            'when {\n'
            '  context.input has reason && context.input.reason == "damaged"\n'
            '};'
        )

    created = []

    # forbid: anything other than a damaged return is denied at the Gateway.
    print("  Creating policy: process_return_damaged_only (forbid)")
    forbid_id, accepted_action = create_action_policy_with_fallback(
        client, engine_id, "process_return_damaged_only",
        "Forbid process_return unless reason == 'damaged'",
        forbid_builder, candidate_actions,
    )
    created.append(forbid_id)

    # permit: the allowed (damaged) path, explicit for readability. Reuse the
    # action identifier the forbid policy converged on so both halves agree.
    permit_candidates = [accepted_action] if accepted_action else candidate_actions
    print("  Creating policy: process_return_allow_damaged (permit)")
    permit_id, _ = create_action_policy_with_fallback(
        client, engine_id, "process_return_allow_damaged",
        "Permit process_return when reason == 'damaged'",
        permit_builder, permit_candidates,
    )
    created.append(permit_id)

    return created


def attach_engine_to_gateway(client, gateway_id, engine_arn, mode="ENFORCE"):
    """Attach the policy engine to the gateway in ENFORCE (or MONITOR) mode.

    update_gateway is a full replace — re-pass the gateway's existing required
    fields (name/roleArn/protocolType/authorizerType[/authorizerConfiguration])
    or they get wiped. Read them back via get_gateway first.
    """
    print(f"\n  Attaching policy engine to gateway in {mode} mode...")
    gw = client.get_gateway(gatewayIdentifier=gateway_id)
    update_kwargs = dict(
        gatewayIdentifier=gateway_id,
        name=gw["name"],
        roleArn=gw["roleArn"],
        protocolType=gw["protocolType"],
        authorizerType=gw["authorizerType"],
        policyEngineConfiguration={"mode": mode, "arn": engine_arn},
    )
    if "authorizerConfiguration" in gw:
        update_kwargs["authorizerConfiguration"] = gw["authorizerConfiguration"]
    client.update_gateway(**update_kwargs)
    print("  Policy engine attached.")


def main():
    parser = argparse.ArgumentParser(description="Deploy the managed AgentCore Policy Engine for Pellier")
    parser.add_argument("--gateway-id", required=True, help="AgentCore Gateway ID")
    parser.add_argument("--gateway-arn", required=True, help="AgentCore Gateway ARN")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument("--mode", default="ENFORCE", choices=["ENFORCE", "MONITOR"],
                        help="ENFORCE blocks denied calls; MONITOR only logs")
    parser.add_argument("--experience-target-name", default=EXPERIENCE_TARGET,
                        help="Gateway TARGET name of the experience MCP server "
                             "(Cedar action prefix; e.g. pellier-concierge-experience-target)")
    parser.add_argument("--engine-name", default=ENGINE_NAME, help="Policy engine name")
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)

    print("=" * 60)
    print("Deploying managed AgentCore Policy Engine for Pellier")
    print("=" * 60)

    print("\nStep 1: Create policy engine")
    engine_id, engine_arn = create_or_reuse_engine(client, name=args.engine_name)

    print("\nStep 2: Create Cedar policies")
    create_pellier_policies(client, engine_id, args.gateway_arn, args.experience_target_name)

    print("\nStep 3: Attach policy engine to gateway")
    attach_engine_to_gateway(client, args.gateway_id, engine_arn, mode=args.mode)

    all_policies = client.list_policies(policyEngineId=engine_id).get("policies", [])
    print("\n" + "=" * 60)
    print("Policy deployment complete!")
    print(f"  Policy Engine ID:  {engine_id}")
    print(f"  Policy Engine ARN: {engine_arn}")
    print(f"  Mode:              {args.mode}")
    print(f"  Total policies:    {len(all_policies)}")
    for p in all_policies:
        print(f"    - {p['name']} ({p['policyId']})")
    print("=" * 60)

    # Machine-readable last line for the caller to capture into .env.
    print(f"POLICY_ENGINE_ID={engine_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
