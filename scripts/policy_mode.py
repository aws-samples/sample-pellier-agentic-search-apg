#!/usr/bin/env python3
"""Read and switch AgentCore Policy enforcement mode.

Enforcement mode is not one switch. Verified against the live
`bedrock-agentcore-control` API on 2026-08-19, there are **two independent
scopes with different vocabularies**:

| Scope                  | Operation                                     | Values                |
| ---------------------- | --------------------------------------------- | --------------------- |
| One policy             | `UpdatePolicy.enforcementMode`                | `ACTIVE`, `LOG_ONLY`  |
| Gateway attachment     | `UpdateGateway.policyEngineConfiguration.mode`| `ENFORCE`, `LOG_ONLY` |

Note the asymmetry: the "on" value is `ACTIVE` for a policy and `ENFORCE` for a
gateway. Code that assumes a single ENFORCE/LOG_ONLY vocabulary gets a
validation error on the policy call — or, worse, sets a value it believes means
enforcement when the API never accepted it. `UpdatePolicyEngine` carries no
mode at all; the engine is a container.

Effective behavior is the conjunction: a policy in `LOG_ONLY` does not deny
even when its gateway is `ENFORCE`, and a gateway in `LOG_ONLY` does not deny
even when every policy is `ACTIVE`.

WHY THE DEFAULT IS PER-POLICY
-----------------------------

`UpdatePolicy` requires only the two ids, so changing one policy's mode cannot
disturb anything else. `UpdateGateway` requires `authorizerType`, `name`, and
`roleArn`, and **drops every optional field the call omits** — so a naive
gateway-level flip silently discards the authorizer configuration, protocol
configuration, and interceptors. The gateway path here therefore reads the
current configuration and echoes it back. Prefer `--policy`.

Usage::

    python3 scripts/policy_mode.py                      # show current state
    python3 scripts/policy_mode.py --policy initiate_return_damaged_only \\
        --mode LOG_ONLY                                 # one policy
    python3 scripts/policy_mode.py --policy all --mode ACTIVE
    python3 scripts/policy_mode.py --gateway --mode ENFORCE
"""
from __future__ import annotations

import argparse
import json
import os
import re
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

_REPO = pathlib.Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "pellier" / "backend"
_DEFAULT_PROJECT = _REPO / ".agentcore-project" / "pellier"

# The account id a template render carries before provisioning
# substitutes the real one.
_PLACEHOLDER_ACCOUNT = "123456789012"

POLICY_MODES = ("ACTIVE", "LOG_ONLY")
GATEWAY_MODES = ("ENFORCE", "LOG_ONLY")

# The shipped state a reset restores: everything enforcing.
SHIPPED_POLICY_MODE = "ACTIVE"
SHIPPED_GATEWAY_MODE = "ENFORCE"

# Mode changes are not guaranteed to be read-your-writes, so a change is
# confirmed by re-reading rather than by a successful call.
_VERIFY_ATTEMPTS = 10
_VERIFY_INTERVAL_SECONDS = 2


def _load_env() -> Dict[str, str]:
    """Read the backend .env without shell interpolation."""
    values: Dict[str, str] = {}
    env_path = _BACKEND / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    values.update(
        {k: v for k, v in os.environ.items() if k.startswith(("AGENTCORE_", "AWS_"))}
    )
    return values


def gateway_id_from_arn(arn: str) -> str:
    """Return the gateway identifier from its ARN, or the input unchanged."""
    return arn.rsplit("/", 1)[-1] if "/" in arn else arn


def describe(client: Any, engine_id: str, gateway_id: Optional[str]) -> Dict[str, Any]:
    """Return the current mode at both scopes."""
    state: Dict[str, Any] = {"engine_id": engine_id, "policies": [], "gateway": None}

    for policy in client.list_policies(policyEngineId=engine_id).get("policies", []):
        state["policies"].append(
            {
                "policy_id": policy["policyId"],
                "name": policy["name"],
                "enforcement_mode": policy.get("enforcementMode"),
                "status": policy.get("status"),
                "effect": _cedar_effect(policy),
            }
        )

    if gateway_id:
        gateway = client.get_gateway(gatewayIdentifier=gateway_id)
        configuration = gateway.get("policyEngineConfiguration") or {}
        state["gateway"] = {
            "gateway_id": gateway_id,
            "mode": configuration.get("mode"),
            "engine_arn": configuration.get("arn"),
            "status": gateway.get("status"),
        }
    return state


def _cedar_effect(policy: Dict[str, Any]) -> str:
    """Report whether a policy permits or forbids, for legibility.

    A `forbid` policy is the one whose mode actually changes an outcome; a
    `permit` in LOG_ONLY looks identical to a `permit` in ACTIVE from the
    shopper's side.
    """
    statement = (policy.get("definition", {}).get("cedar", {}) or {}).get(
        "statement", ""
    )
    stripped = statement.strip().lower()
    if stripped.startswith("suppressoutput"):
        return "suppressOutput"
    if stripped.startswith("forbid"):
        return "forbid"
    if stripped.startswith("permit"):
        return "permit"
    return "unknown"


def _caller_account() -> Optional[str]:
    """Return the account these credentials belong to, or None."""
    try:
        import boto3

        return boto3.client("sts").get_caller_identity()["Account"]
    except Exception:
        return None


def _project_config(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / "agentcore" / "agentcore.json"


def read_declared_modes(project_dir: pathlib.Path) -> Dict[str, Any]:
    """Return the modes the CLI project declares, per scope."""
    config = json.loads(_project_config(project_dir).read_text())
    gateways = config.get("agentCoreGateways") or []
    engines = config.get("policyEngines") or []
    return {
        "gateway_mode": (
            (gateways[0].get("policyEngineConfiguration") or {}).get("mode")
            if gateways
            else None
        ),
        "policies": {
            policy["name"]: policy.get("enforcementMode")
            for engine in engines
            for policy in (engine.get("policies") or [])
        },
    }


def declare_modes(
    project_dir: pathlib.Path,
    *,
    policy_modes: Optional[Dict[str, str]] = None,
    gateway_mode: Optional[str] = None,
) -> List[str]:
    """Edit the CLI project so it declares the requested modes.

    The AgentCore CLI project owns resource mutation; this tool only edits the
    declaration and then asks the CLI to converge. Calling `UpdatePolicy` or
    `UpdateGateway` through boto3 would drift the live resources away from the
    declared project, so the next `agentcore deploy` would silently undo the
    change — and `UpdateGateway` is a replace that drops omitted fields.

    Returns a list of human-readable changes, empty when nothing needed editing.
    """
    path = _project_config(project_dir)
    config = json.loads(path.read_text())
    changes: List[str] = []

    if gateway_mode is not None:
        if gateway_mode not in GATEWAY_MODES:
            raise ValueError(f"gateway mode must be one of {GATEWAY_MODES}, got {gateway_mode!r}")
        for gateway in config.get("agentCoreGateways") or []:
            configuration = gateway.setdefault("policyEngineConfiguration", {})
            if configuration.get("mode") != gateway_mode:
                configuration["mode"] = gateway_mode
                changes.append(f"gateway {gateway.get('name')} mode -> {gateway_mode}")

    for name, mode in (policy_modes or {}).items():
        if mode not in POLICY_MODES:
            raise ValueError(f"policy mode must be one of {POLICY_MODES}, got {mode!r}")
        found = False
        for engine in config.get("policyEngines") or []:
            for policy in engine.get("policies") or []:
                if policy.get("name") != name:
                    continue
                found = True
                if policy.get("enforcementMode") != mode:
                    policy["enforcementMode"] = mode
                    changes.append(f"policy {name} enforcementMode -> {mode}")
        if not found:
            raise ValueError(f"policy {name!r} is not declared in the CLI project")

    if changes:
        path.write_text(json.dumps(config, indent=2) + "\n")
    return changes


def project_accounts(project_dir: pathlib.Path) -> Set[str]:
    """Return every 12-digit AWS account id the project references."""
    text = _project_config(project_dir).read_text()
    return set(re.findall(r"\b(\d{12})\b", text))


def deployability(project_dir: pathlib.Path, caller_account: Optional[str]) -> Optional[str]:
    """Return why the project cannot be deployed here, or None if it can.

    `agentcore deploy` is a whole-project CDK deploy with no scoped option, so
    it assumes a CDK role in the account the project was rendered for. A
    template render carries a placeholder account, and the failure surfaces as
    an opaque `sts:AssumeRole` error naming a role that never existed. Checking
    first turns that into an actionable message.
    """
    accounts = project_accounts(project_dir)
    if _PLACEHOLDER_ACCOUNT in accounts:
        return (
            f"the CLI project at {project_dir} is a template render "
            f"(account {_PLACEHOLDER_ACCOUNT}). `agentcore deploy` would try to "
            "assume a CDK role in an account that does not exist. Re-render the "
            "project for this account before changing mode."
        )
    if caller_account and accounts and caller_account not in accounts:
        return (
            f"the CLI project targets account(s) {', '.join(sorted(accounts))} "
            f"but these credentials are for {caller_account}."
        )
    return None


def deploy(project_dir: pathlib.Path) -> Tuple[int, str]:
    """Ask the AgentCore CLI to converge the project. Returns (rc, output)."""
    import shutil
    import subprocess

    command = (
        ["agentcore", "deploy", "--yes"]
        if shutil.which("agentcore")
        else ["npx", "-y", "@aws/agentcore@0.29.0", "deploy", "--yes"]
    )
    result = subprocess.run(
        command, cwd=str(project_dir), capture_output=True, text=True
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def verify_live(
    client: Any,
    engine_id: str,
    gateway_id: Optional[str],
    *,
    policy_modes: Optional[Dict[str, str]] = None,
    gateway_mode: Optional[str] = None,
) -> List[str]:
    """Confirm the live resources match the requested modes.

    A successful deploy is not proof. Mode changes are not guaranteed
    read-your-writes, so the live state is polled until it agrees or the
    window closes.
    """
    wanted_policies = policy_modes or {}
    for _ in range(_VERIFY_ATTEMPTS):
        state = describe(client, engine_id, gateway_id)
        observed = {p["name"]: p["enforcement_mode"] for p in state["policies"]}
        problems = [
            f"{name}: live={observed.get(name)!r} wanted={mode!r}"
            for name, mode in wanted_policies.items()
            if observed.get(name) != mode
        ]
        if gateway_mode is not None:
            live_gateway = (state.get("gateway") or {}).get("mode")
            if live_gateway != gateway_mode:
                problems.append(
                    f"gateway: live={live_gateway!r} wanted={gateway_mode!r}"
                )
        if not problems:
            return []
        time.sleep(_VERIFY_INTERVAL_SECONDS)
    return problems


def _print_state(state: Dict[str, Any]) -> None:
    print(f"engine  : {state['engine_id']}")
    gateway = state.get("gateway")
    if gateway:
        print(
            f"gateway : {gateway['gateway_id']} "
            f"mode={gateway['mode']} status={gateway['status']}"
        )
    else:
        print("gateway : (none configured)")
    print()
    print(f"{'policy':<36} {'effect':<8} {'mode':<10} status")
    print("-" * 72)
    for policy in state["policies"]:
        print(
            f"{policy['name']:<36} {policy['effect']:<8} "
            f"{str(policy['enforcement_mode']):<10} {policy['status']}"
        )
    if not state["policies"]:
        print("(no policies on this engine)")
    print()
    print(
        "A forbid policy is the one whose mode changes an outcome. Effective\n"
        "behavior is the conjunction of both scopes: LOG_ONLY at either scope\n"
        "means no denial."
    )


def _restore_shipped(project_dir: pathlib.Path, client: Any, engine_id: str,
                     gateway_id: Optional[str]) -> int:
    """Return every scope to the shipped mode through the CLI project.

    Reset needs this because the declared project and the live resource can
    disagree: a participant who switches a policy to LOG_ONLY during the
    monitor exercise leaves the engine in monitor mode. Restoring the
    declaration and deploying converges both.
    """
    declared = read_declared_modes(project_dir)
    policy_modes = {name: SHIPPED_POLICY_MODE for name in declared["policies"]}
    return _apply(
        project_dir, client, engine_id, gateway_id,
        policy_modes=policy_modes, gateway_mode=SHIPPED_GATEWAY_MODE,
        label="shipped mode",
    )


def _apply(
    project_dir: pathlib.Path,
    client: Any,
    engine_id: str,
    gateway_id: Optional[str],
    *,
    policy_modes: Optional[Dict[str, str]] = None,
    gateway_mode: Optional[str] = None,
    label: str = "requested mode",
) -> int:
    """Declare, deploy, then verify against the live resources."""
    # Checked before the declaration is touched. Editing first and failing
    # after would leave the project declaring a mode that was never applied,
    # which is worse than not trying: the next successful deploy would apply it
    # by surprise.
    blocker = deployability(project_dir, _caller_account())
    if blocker:
        print(f"cannot change mode: {blocker}", file=sys.stderr)
        print("  Nothing was changed, locally or in AWS.", file=sys.stderr)
        return 3

    changes = declare_modes(
        project_dir, policy_modes=policy_modes, gateway_mode=gateway_mode
    )
    if changes:
        print("declared:")
        for change in changes:
            print(f"  {change}")
        rc, output = deploy(project_dir)
        if rc != 0:
            print(f"agentcore deploy failed (rc={rc}):", file=sys.stderr)
            print(output[-1500:], file=sys.stderr)
            return 1
    else:
        print(f"CLI project already declares the {label}; nothing to deploy")

    problems = verify_live(
        client, engine_id, gateway_id,
        policy_modes=policy_modes, gateway_mode=gateway_mode,
    )
    if problems:
        print("live resources did not converge:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"✅ live resources match the {label}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", help="Policy name to change, or 'all'.")
    parser.add_argument(
        "--gateway", action="store_true",
        help="Change the gateway attachment mode instead of a policy.",
    )
    parser.add_argument(
        "--mode",
        help=f"{POLICY_MODES} for a policy, {GATEWAY_MODES} for a gateway.",
    )
    parser.add_argument(
        "--restore-shipped", action="store_true",
        help=(
            "Restore the shipped mode at both scopes "
            f"(policies {SHIPPED_POLICY_MODE}, gateway {SHIPPED_GATEWAY_MODE})."
        ),
    )
    parser.add_argument(
        "--project",
        default=str(_DEFAULT_PROJECT),
        help="AgentCore CLI project directory.",
    )
    parser.add_argument("--region", default=None)
    args = parser.parse_args(argv)

    cfg = _load_env()
    engine_id = cfg.get("AGENTCORE_POLICY_ENGINE_ID", "").strip()
    gateway_arn = cfg.get("AGENTCORE_GATEWAY_ARN", "").strip()
    region = args.region or cfg.get("AWS_REGION") or "us-east-1"

    if not engine_id:
        print(
            "AGENTCORE_POLICY_ENGINE_ID is not set, so there is no engine to read.\n"
            "Provision AgentCore Policy first; until then no Cedar decision exists\n"
            "and a turn's policy evidence is NOT_EVALUATED rather than ALLOW.",
            file=sys.stderr,
        )
        return 2

    try:
        import boto3
    except ImportError:
        print("boto3 is required.", file=sys.stderr)
        return 1

    # Before any client call. botocore drops unknown fields silently, and the field this
    # script exists to set is exactly the one an older bundled model lacks: a 1.43.28
    # interpreter sends `update_policy` with no `enforcementMode`, the service applies its
    # own default, the API returns 200, and Cedar enforcement is off with nothing in the
    # output to say so. Reading only, that cannot happen, so the guard is scoped to the
    # mutating paths.
    if args.mode or args.restore_shipped:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "deploy"))
        from sdk_preflight import require_policy_mode_support

        require_policy_mode_support()

    client = boto3.client("bedrock-agentcore-control", region_name=region)
    gateway_id = gateway_id_from_arn(gateway_arn) if gateway_arn else None
    project_dir = pathlib.Path(args.project)

    if not args.mode and not args.restore_shipped:
        _print_state(describe(client, engine_id, gateway_id))
        declared = (
            read_declared_modes(project_dir)
            if _project_config(project_dir).exists()
            else None
        )
        if declared:
            print()
            print("CLI project declares (this is what a deploy converges to):")
            print(f"  gateway: {declared['gateway_mode']}")
            for name, mode in sorted(declared["policies"].items()):
                print(f"  {name}: {mode}")
        return 0

    if not _project_config(project_dir).exists():
        print(
            f"no AgentCore CLI project at {project_dir}. Mode is a declared\n"
            "property of that project; render it before changing mode.",
            file=sys.stderr,
        )
        return 2

    if args.restore_shipped:
        return _restore_shipped(project_dir, client, engine_id, gateway_id)

    if args.gateway:
        return _apply(
            project_dir, client, engine_id, gateway_id, gateway_mode=args.mode
        )

    if not args.policy:
        print("--mode needs --policy <name|all> or --gateway", file=sys.stderr)
        return 2

    declared = read_declared_modes(project_dir)
    names = (
        list(declared["policies"])
        if args.policy == "all"
        else [args.policy]
    )
    return _apply(
        project_dir, client, engine_id, gateway_id,
        policy_modes={name: args.mode for name in names},
    )


if __name__ == "__main__":
    sys.exit(main())
