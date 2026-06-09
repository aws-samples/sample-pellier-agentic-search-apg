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

Cedar action spelling is ``<lambda-function-name>___<tool-name>`` (triple
underscore). For Pellier process_return that is
``pellier-experience-server-function___process_return``.

Usage:
    uv run scripts/deploy/deploy_policy.py \
        --gateway-id <gateway-id> \
        --gateway-arn <gateway-arn> \
        --region us-west-2 \
        [--experience-function-name pellier-experience-server-function] \
        [--mode ENFORCE]

Prints the policy engine id on the last line as ``POLICY_ENGINE_ID=<id>`` so the
caller (provision_agentcore_end_to_end.py / deploy_all.sh) can capture it into
``.env`` as ``AGENTCORE_POLICY_ENGINE_ID``.
"""

import argparse
import sys
import time

import boto3

ENGINE_NAME = "pellier_policy_engine"


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


def wait_for_policy(client, engine_id, policy_id, max_wait=180, interval=10):
    """Wait for a policy to become ACTIVE; raise on CREATE_FAILED."""
    elapsed = 0
    while elapsed < max_wait:
        resp = client.get_policy(policyEngineId=engine_id, policyId=policy_id)
        status = resp.get("status", "UNKNOWN")
        print(f"  Policy status: {status} ({elapsed}s)")
        if status == "ACTIVE":
            return
        if status == "CREATE_FAILED":
            reason = resp.get("statusReasons", resp.get("failureReason", "Unknown error"))
            raise RuntimeError(f"Policy {policy_id} creation failed: {reason}")
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
        for p in client.list_policies(policyEngineId=engine_id).get("policies", []):
            if p["name"] == name:
                print(f"    Reusing existing policy: {name}")
                return p["policyId"]
        raise


def create_pellier_policies(client, engine_id, gateway_arn, experience_function):
    """Create Pellier's Cedar policies.

    The headline rule is a single ``forbid`` on process_return unless the return
    reason is 'damaged' — Cedar default-deny + forbid-wins means this is the
    whole gate. We ALSO add an explicit ``permit`` for the damaged path so the
    Atelier Policy surface can show both halves of the decision (and so the
    intent reads clearly to a 400-level attendee inspecting the engine).
    """
    action = f'AgentCore::Action::"{experience_function}___process_return'
    gw = f'AgentCore::Gateway::"{gateway_arn}"'
    created = []

    # forbid: anything other than a damaged return is denied at the Gateway.
    forbid_cedar = (
        f'forbid(principal, action == {action}", resource == {gw})\n'
        'when {\n'
        '  !(context.input has reason) || context.input.reason != "damaged"\n'
        '};'
    )
    print("  Creating policy: process_return_damaged_only (forbid)")
    created.append(create_or_reuse_policy(
        client, engine_id, "process_return_damaged_only",
        "Forbid process_return unless reason == 'damaged'", forbid_cedar,
    ))

    # permit: the allowed (damaged) path, explicit for readability.
    permit_cedar = (
        f'permit(principal, action == {action}", resource == {gw})\n'
        'when {\n'
        '  context.input has reason && context.input.reason == "damaged"\n'
        '};'
    )
    print("  Creating policy: process_return_allow_damaged (permit)")
    created.append(create_or_reuse_policy(
        client, engine_id, "process_return_allow_damaged",
        "Permit process_return when reason == 'damaged'", permit_cedar,
    ))

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
    parser.add_argument("--experience-function-name", default="pellier-experience-server-function",
                        help="Lambda function name of the experience MCP server (Cedar action prefix)")
    parser.add_argument("--engine-name", default=ENGINE_NAME, help="Policy engine name")
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)

    print("=" * 60)
    print("Deploying managed AgentCore Policy Engine for Pellier")
    print("=" * 60)

    print("\nStep 1: Create policy engine")
    engine_id, engine_arn = create_or_reuse_engine(client, name=args.engine_name)

    print("\nStep 2: Create Cedar policies")
    create_pellier_policies(client, engine_id, args.gateway_arn, args.experience_function_name)

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
