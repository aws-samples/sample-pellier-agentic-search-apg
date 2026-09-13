#!/usr/bin/env python3
"""Provision and prove Pellier's managed AgentCore path.

AgentCore CLI is the only control-plane deployment path for Runtime, Memory,
Gateway, Gateway target registrations, AgentCore-managed service roles, Policy
engine, and Cedar policies. ``deploy_lambda.py`` owns the external Lambda
functions and their Lambda execution roles. The remaining Python/AWS SDK code
is limited to Aurora preflight, Memory data seeding, authentication, and
post-deploy proof.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


DEPLOY_DIR = Path(__file__).resolve().parent / "deploy"
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

from gateway_tool_schemas import TOOL_SCHEMAS, schema_for  # noqa: E402
from render_agentcore_project import (  # noqa: E402
    AGENTCORE_CLI,
    GATEWAY_NAME,
    MEMORY_NAME,
    POLICY_ENGINE_NAME,
    PROCESS_RETURN_ACTION,
    PROJECT_NAME,
    RUNTIME_NAME,
    project_root,
    render_project,
)


EXPECTED_TARGETS = {
    "search": {
        "handler": "pellier_search_server.lambda_handler",
        "server_name": "pellier-search-server",
        "entrypoint": "scripts/deploy/pellier_search_server.py",
    },
    "pricing": {
        "handler": "pellier_pricing_server.lambda_handler",
        "server_name": "pellier-pricing-server",
        "entrypoint": "scripts/deploy/pellier_pricing_server.py",
    },
    "recommendation": {
        "handler": "pellier_recommend_server.lambda_handler",
        "server_name": "pellier-recommend-server",
        "entrypoint": "scripts/deploy/pellier_recommend_server.py",
    },
    "experience": {
        "handler": "pellier_experience_server.lambda_handler",
        "server_name": "pellier-experience-server",
        "entrypoint": "scripts/deploy/pellier_experience_server.py",
    },
}

AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=60,
)


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        redacted = list(cmd)
        for index, value in enumerate(redacted[:-1]):
            if value in {"--bearer-token", "--token", "--password", "--client-secret"}:
                redacted[index + 1] = "<redacted>"
        raise RuntimeError(
            f"Command failed: {' '.join(redacted)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _region_from_arn(arn: str, fallback: str) -> str:
    match = re.match(r"^arn:[^:]+:[^:]+:([^:]+):", arn or "")
    return match.group(1) if match else fallback


def _ensure_data_api_enabled(region: str, db_cluster_arn: str) -> None:
    rds = boto3.client("rds", region_name=region, config=AWS_CONFIG)
    cluster_id = db_cluster_arn.rsplit(":", 1)[-1]

    def enabled() -> bool:
        response = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
        return bool(response["DBClusters"][0].get("HttpEndpointEnabled"))

    if enabled():
        return

    print(f"Enabling Aurora Data API on {cluster_id}...")
    rds.enable_http_endpoint(ResourceArn=db_cluster_arn)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        time.sleep(5)
        if enabled():
            time.sleep(10)
            return
    raise RuntimeError(f"Aurora Data API did not become ready on {cluster_id}")


def _compute_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    digest = hmac.new(
        client_secret.encode("utf-8"),
        msg=f"{username}{client_id}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _cognito_access_token(
    *,
    region: str,
    user_pool_id: str,
    client_id: str,
    credentials_secret_arn: str,
    client_secret_arn: str | None,
) -> tuple[str, str]:
    secrets = boto3.client("secretsmanager", region_name=region, config=AWS_CONFIG)
    cognito = boto3.client("cognito-idp", region_name=region, config=AWS_CONFIG)
    credentials_raw = secrets.get_secret_value(
        SecretId=credentials_secret_arn
    ).get("SecretString", "")
    credentials = json.loads(credentials_raw) if credentials_raw else {}
    users = credentials.get("users", [])
    if not users:
        raise RuntimeError("Cognito test credentials secret has no users")

    username = str(users[0].get("username", ""))
    password = str(users[0].get("password", ""))
    if not username or not password:
        raise RuntimeError("Cognito test credentials are missing username/password")

    auth_parameters = {"USERNAME": username, "PASSWORD": password}
    if client_secret_arn:
        client_secret_raw = secrets.get_secret_value(
            SecretId=client_secret_arn
        ).get("SecretString", "")
        client_secret_payload = json.loads(client_secret_raw) if client_secret_raw else {}
        client_secret = str(client_secret_payload.get("client_secret", ""))
        if client_secret:
            auth_parameters["SECRET_HASH"] = _compute_secret_hash(
                username, client_id, client_secret
            )

    response = cognito.admin_initiate_auth(
        UserPoolId=user_pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters=auth_parameters,
    )
    access_token = response.get("AuthenticationResult", {}).get("AccessToken")
    if not access_token:
        raise RuntimeError("Cognito did not return an access token")
    return str(access_token), username


def _scaffold_cli_project(
    *,
    repo: Path,
    env: dict[str, str],
) -> Path:
    root = project_root(repo)
    config_path = root / "agentcore" / "agentcore.json"
    output_dir = root.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_root = repo / "pellier" / "backend" / ".agentcore-project"
    if legacy_root.exists():
        shutil.rmtree(legacy_root, ignore_errors=True)

    if not config_path.is_file():
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        _run(
            [
                "npx",
                "-y",
                AGENTCORE_CLI,
                "create",
                "--project-name",
                PROJECT_NAME,
                "--no-agent",
                "--skip-git",
                "--skip-python-setup",
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            cwd=output_dir,
            env=env,
        )
    return root


def _agentcore(
    root: Path,
    *args: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return _run(
        ["npx", "-y", AGENTCORE_CLI, *args],
        cwd=root,
        env=env,
    )


def _deploy_cli_project(
    *,
    repo: Path,
    account_id: str,
    region: str,
    cognito_pool: str,
    cognito_client: str,
    lambda_arns: dict[str, str],
    model_id: str,
    workshop_id: str,
    env: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    """Deploy infrastructure first, then add Gateway-scoped Cedar policies."""
    root = _scaffold_cli_project(repo=repo, env=env)
    common = {
        "repo": repo,
        "account_id": account_id,
        "region": region,
        "cognito_pool": cognito_pool,
        "cognito_client": cognito_client,
        "lambda_arns": lambda_arns,
        "model_id": model_id,
        "workshop_id": workshop_id,
    }

    render_project(**common, include_policies=False)
    _agentcore(root, "validate", env=env)
    _agentcore(root, "deploy", "--yes", "--json", env=env)

    state = _read_deployed_state(root)
    gateway_state = _require_gateway_state(state, GATEWAY_NAME)
    _require_state_resource(state, "policyEngines", POLICY_ENGINE_NAME)

    render_project(
        **common,
        include_policies=True,
        action_token=PROCESS_RETURN_ACTION,
        gateway_arn=str(gateway_state["gatewayArn"]),
    )
    _agentcore(root, "validate", env=env)
    _agentcore(root, "deploy", "--yes", "--json", env=env)
    return root, _read_deployed_state(root)


def _read_deployed_state(root: Path) -> dict[str, Any]:
    path = root / "agentcore" / ".cli" / "deployed-state.json"
    if not path.is_file():
        raise RuntimeError(f"AgentCore CLI deployed state not found: {path}")
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AgentCore CLI deployed state is invalid JSON: {path}") from exc
    if not isinstance(state.get("targets"), dict):
        raise RuntimeError("AgentCore CLI deployed state has no targets map")
    return state


def _state_resources(state: dict[str, Any]) -> dict[str, Any]:
    target = state.get("targets", {}).get("default")
    if not isinstance(target, dict):
        target = next(iter(state.get("targets", {}).values()), {})
    resources = target.get("resources", {}) if isinstance(target, dict) else {}
    if not isinstance(resources, dict):
        raise RuntimeError("AgentCore CLI deployed state has no resources")
    return resources


def _require_state_resource(
    state: dict[str, Any],
    category: str,
    name: str,
) -> dict[str, Any]:
    value = _state_resources(state).get(category, {}).get(name)
    if not isinstance(value, dict):
        raise RuntimeError(
            f"AgentCore CLI deployed state is missing {category}.{name}"
        )
    return value


def _require_gateway_state(
    state: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    mcp = _state_resources(state).get("mcp", {})
    value = mcp.get("gateways", {}).get(name) if isinstance(mcp, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError(
            f"AgentCore CLI deployed state is missing mcp.gateways.{name}"
        )
    return value


def _deploy_lambdas(
    *,
    repo: Path,
    deploy_dir: Path,
    region: str,
    db_region: str,
    db_cluster_arn: str,
    db_secret_arn: str,
    db_name: str,
) -> dict[str, str]:
    lambda_client = boto3.client("lambda", region_name=region, config=AWS_CONFIG)
    arns: dict[str, str] = {}
    for surface, config in EXPECTED_TARGETS.items():
        _run(
            [
                sys.executable,
                str(deploy_dir / "deploy_lambda.py"),
                "--region",
                region,
                "--server-name",
                config["server_name"],
                "--db-cluster-arn",
                db_cluster_arn,
                "--db-region",
                db_region,
                "--secret-arn",
                db_secret_arn,
                "--database",
                db_name,
                "--mcp-server-path",
                str(repo / config["entrypoint"]),
                "--handler",
                config["handler"],
            ],
            cwd=repo,
        )
        function_name = f"{config['server_name']}-function"
        response = lambda_client.get_function(FunctionName=function_name)
        arns[surface] = response["Configuration"]["FunctionArn"]
    return arns


def _verify_local_schema() -> dict[str, Any]:
    names = [
        tool["name"]
        for surface in TOOL_SCHEMAS
        for tool in schema_for(surface)
    ]
    if len(names) != 15 or len(set(names)) != 15:
        raise RuntimeError(
            f"Canonical Gateway schema must contain 15 unique tools, found {len(names)}"
        )
    return {"count": len(names), "canonical_names": sorted(names)}


def _verify_gateway_control_plane(
    *,
    region: str,
    gateway_id: str,
) -> dict[str, Any]:
    control = boto3.client(
        "bedrock-agentcore-control",
        region_name=region,
        config=AWS_CONFIG,
    )
    expected = {schema["target_name"] for schema in TOOL_SCHEMAS.values()}
    observed: set[str] = set()
    paginator = control.get_paginator("list_gateway_targets")
    for page in paginator.paginate(gatewayIdentifier=gateway_id):
        observed.update(
            str(item["name"])
            for item in page.get("items", [])
            if item.get("name")
        )
    if observed != expected:
        raise RuntimeError(
            "Gateway target mismatch: "
            f"expected {sorted(expected)}, observed {sorted(observed)}"
        )
    gateway = control.get_gateway(gatewayIdentifier=gateway_id)
    policy_config = gateway.get("policyEngineConfiguration", {})
    if policy_config.get("mode") != "ENFORCE":
        raise RuntimeError("Gateway Policy mode is not ENFORCE")
    return {
        "target_count": len(observed),
        "target_names": sorted(observed),
        "status": gateway.get("status", "UNKNOWN"),
        "policy_mode": policy_config.get("mode"),
    }


def _discover_live_gateway_tools(
    *,
    deploy_dir: Path,
    gateway_url: str,
    access_token: str,
) -> dict[str, Any]:
    deploy_path = str(deploy_dir)
    if deploy_path not in sys.path:
        sys.path.insert(0, deploy_path)
    from test_gateway_tools import discover_gateway_tools

    tools = discover_gateway_tools(gateway_url, access_token)
    full_names = sorted(str(tool.name) for tool in tools)
    canonical_names = {name.rsplit("__", 1)[-1] for name in full_names}
    expected = {
        tool["name"]
        for surface in TOOL_SCHEMAS
        for tool in schema_for(surface)
    }
    if len(tools) != 15 or canonical_names != expected:
        raise RuntimeError(
            "Live Gateway discovery mismatch: "
            f"expected {sorted(expected)}, observed {sorted(canonical_names)}"
        )
    return {
        "count": len(tools),
        "canonical_names": sorted(canonical_names),
        "prefixed_names": full_names,
    }


def _seed_memory(
    *,
    repo: Path,
    memory_id: str,
    region: str,
    env: dict[str, str],
) -> dict[str, Any]:
    proc = _run(
        [
            sys.executable,
            str(repo / "scripts" / "deploy" / "seed_agentcore_memory.py"),
            "--memory-id",
            memory_id,
            "--region",
            region,
        ],
        cwd=repo,
        env=env,
    )
    return json.loads(proc.stdout)


def _authenticated_runtime_smoke(
    *,
    root: Path,
    access_token: str,
    username: str,
    env: dict[str, str],
) -> dict[str, Any]:
    # A reused Runtime session can keep executing the sandbox from an earlier
    # deployment. Each readiness proof must start a fresh session.
    session_id = f"builders-smoke-{uuid.uuid4().hex}"
    proc = _agentcore(
        root,
        "invoke",
        "--runtime",
        RUNTIME_NAME,
        "--session-id",
        session_id,
        "--bearer-token",
        access_token,
        "--prompt",
        "Smoke test: find one linen item under 150. Do not mutate data.",
        "--json",
        env=env,
    )
    try:
        cli_payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AgentCore CLI invoke did not return JSON") from exc
    if cli_payload.get("success") is not True:
        raise RuntimeError("AgentCore CLI invoke did not report success")

    raw_response = cli_payload.get("response")
    if isinstance(raw_response, str):
        try:
            decoded = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AgentCore CLI Runtime response was not a JSON object"
            ) from exc
    elif isinstance(raw_response, dict):
        decoded = raw_response
    else:
        raise RuntimeError("AgentCore CLI Runtime response was missing")

    if not str(decoded.get("response", "")).strip():
        raise RuntimeError("Runtime smoke returned an empty response")
    if decoded.get("rail") != "gateway-mcp":
        raise RuntimeError(
            "Runtime smoke did not use Gateway MCP "
            f"(rail={decoded.get('rail') or 'missing'})"
        )
    return {
        "username": username,
        "session_id": session_id,
        "rail": decoded["rail"],
        "intent": decoded.get("intent"),
        "specialist": decoded.get("specialist"),
        "gateway_tools": decoded.get("gateway_tools", []),
        "response_preview": str(decoded["response"])[:200],
    }


def _live_policy_proof(
    *,
    repo: Path,
    deploy_dir: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    helper = deploy_dir / "gateway_process_return.py"
    proofs: dict[str, Any] = {}
    for expected, reason, session_id in (
        ("allow", "damaged", "provision-policy-allow"),
        ("deny", "changed_mind", "provision-policy-deny"),
    ):
        proc = _run(
            [
                sys.executable,
                str(helper),
                "--product-id",
                "31",
                "--reason",
                reason,
                "--expect",
                expected,
                "--record-receipt",
                "--session-id",
                session_id,
            ],
            cwd=repo,
            env=env,
        )
        payload = json.loads(proc.stdout)
        if payload.get("outcome") != expected:
            raise RuntimeError(
                f"Policy {expected.upper()} proof returned {payload.get('outcome')}"
            )
        if expected == "allow" and payload.get("tool_audit_row_after_call") is None:
            raise RuntimeError("Policy ALLOW produced no execution audit row")
        if expected == "deny" and (
            payload.get("tool_audit_row_after_call") is not None
            or payload.get("cedar_denial") is not True
        ):
            raise RuntimeError("Policy DENY did not prove pre-execution blocking")
        proofs[expected] = payload
    return proofs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", default=os.environ.get("REPO_PATH", "."))
    parser.add_argument("--output-json", default="/tmp/pellier-agentcore-managed.json")
    args = parser.parse_args()

    repo = Path(args.repo_path).resolve()
    deploy_dir = repo / "scripts" / "deploy"
    output_path = Path(args.output_json)
    region = _require_env("AWS_REGION")
    required = {
        "db_cluster_arn": _require_env("DB_CLUSTER_ARN"),
        "db_secret_arn": _require_env("DB_SECRET_ARN"),
        "cognito_pool": _require_env("COGNITO_POOL"),
        "cognito_client": _require_env("COGNITO_CLIENT"),
        "credentials_secret": _require_env(
            "COGNITO_TEST_CREDENTIALS_SECRET_ARN"
        ),
        "workshop_id": _require_env("WORKSHOP_ID"),
        "model_id": _require_env("AGENT_MODEL_ID"),
    }
    client_secret_arn = (
        os.environ.get("COGNITO_CLIENT_SECRET_ARN", "").strip() or None
    )
    db_region = os.environ.get("DB_REGION", "").strip() or _region_from_arn(
        required["db_cluster_arn"], region
    )
    db_name = os.environ.get("DB_NAME", "pellier")
    deploy_env = os.environ.copy()
    deploy_env.update({"AWS_REGION": region, "AWS_DEFAULT_REGION": region})

    result: dict[str, Any] = {
        "status": "failed",
        "region": region,
        "cli": {"package": AGENTCORE_CLI},
        "lambdas": {},
        "gateway": {},
        "memory": {},
        "policy": {},
        "runtime": {},
        "verification": {},
    }

    try:
        _ensure_data_api_enabled(db_region, required["db_cluster_arn"])
        local_schema = _verify_local_schema()
        result["verification"]["local_tool_schema"] = local_schema

        lambda_arns = _deploy_lambdas(
            repo=repo,
            deploy_dir=deploy_dir,
            region=region,
            db_region=db_region,
            db_cluster_arn=required["db_cluster_arn"],
            db_secret_arn=required["db_secret_arn"],
            db_name=db_name,
        )
        result["lambdas"] = {
            surface: {"function_arn": arn}
            for surface, arn in lambda_arns.items()
        }

        sts = boto3.client("sts", region_name=region, config=AWS_CONFIG)
        account_id = sts.get_caller_identity()["Account"]
        root, state = _deploy_cli_project(
            repo=repo,
            account_id=account_id,
            region=region,
            cognito_pool=required["cognito_pool"],
            cognito_client=required["cognito_client"],
            lambda_arns=lambda_arns,
            model_id=required["model_id"],
            workshop_id=required["workshop_id"],
            env=deploy_env,
        )
        result["cli"]["project_root"] = str(root)

        runtime_state = _require_state_resource(state, "runtimes", RUNTIME_NAME)
        memory_state = _require_state_resource(state, "memories", MEMORY_NAME)
        gateway_state = _require_gateway_state(state, GATEWAY_NAME)
        policy_state = _require_state_resource(
            state, "policyEngines", POLICY_ENGINE_NAME
        )
        runtime_arn = str(runtime_state["runtimeArn"])
        memory_id = str(memory_state["memoryId"])
        gateway_id = str(gateway_state["gatewayId"])
        gateway_arn = str(gateway_state["gatewayArn"])
        gateway_url = str(gateway_state.get("gatewayUrl", ""))
        policy_engine_id = str(policy_state["policyEngineId"])
        if not gateway_url:
            raise RuntimeError("AgentCore CLI state did not include Gateway URL")

        result["runtime"] = {
            "runtime_arn": runtime_arn,
            "agent_model_id": required["model_id"],
        }
        result["memory"] = {
            "memory_id": memory_id,
            "memory_arn": memory_state.get("memoryArn"),
        }
        result["gateway"] = {
            "gateway_id": gateway_id,
            "gateway_arn": gateway_arn,
            "gateway_url": gateway_url,
        }
        result["policy"] = {
            "policy_engine_id": policy_engine_id,
            "policy_engine_arn": policy_state.get("policyEngineArn"),
            "mode": "ENFORCE",
            "gated_tool": "process_return",
        }

        control_proof = _verify_gateway_control_plane(
            region=region,
            gateway_id=gateway_id,
        )
        result["verification"]["gateway_control_plane"] = control_proof
        result["verification"]["targets_attached"] = (
            control_proof["target_count"] == 4
        )

        access_token, smoke_username = _cognito_access_token(
            region=region,
            user_pool_id=required["cognito_pool"],
            client_id=required["cognito_client"],
            credentials_secret_arn=required["credentials_secret"],
            client_secret_arn=client_secret_arn,
        )
        live_gateway = _discover_live_gateway_tools(
            deploy_dir=deploy_dir,
            gateway_url=gateway_url,
            access_token=access_token,
        )
        result["verification"]["gateway_tools_discovered"] = True
        result["verification"]["gateway_tool_count"] = live_gateway["count"]
        result["verification"]["gateway_tool_names"] = live_gateway[
            "canonical_names"
        ]
        result["verification"]["gateway_prefixed_tool_names"] = live_gateway[
            "prefixed_names"
        ]

        memory_seed = _seed_memory(
            repo=repo,
            memory_id=memory_id,
            region=region,
            env=deploy_env,
        )
        result["memory"]["seed"] = memory_seed
        result["verification"]["memory_seeded"] = (
            memory_seed.get("status") == "ready"
        )

        proof_env = deploy_env.copy()
        proof_env.update(
            {
                "AGENTCORE_GATEWAY_URL": gateway_url,
                "AGENTCORE_GATEWAY_ARN": gateway_arn,
                "AGENTCORE_POLICY_ENGINE_ID": policy_engine_id,
                "PELLIER_TOKEN": access_token,
            }
        )
        policy_proof = _live_policy_proof(
            repo=repo,
            deploy_dir=deploy_dir,
            env=proof_env,
        )
        result["verification"]["live_policy_allow"] = True
        result["verification"]["live_policy_deny"] = True
        result["verification"]["live_policy_proof"] = policy_proof

        runtime_smoke = _authenticated_runtime_smoke(
            root=root,
            access_token=access_token,
            username=smoke_username,
            env=deploy_env,
        )
        result["verification"]["authenticated_runtime_invoke_smoke"] = True
        result["verification"]["runtime_invoke_smoke"] = runtime_smoke

        required_checks = (
            "targets_attached",
            "gateway_tools_discovered",
            "memory_seeded",
            "live_policy_allow",
            "live_policy_deny",
            "authenticated_runtime_invoke_smoke",
        )
        missing = [
            check
            for check in required_checks
            if result["verification"].get(check) is not True
        ]
        if missing:
            raise RuntimeError(
                "Managed readiness checks did not pass: " + ", ".join(missing)
            )
        result["status"] = "ready"
        output_path.write_text(json.dumps(result, indent=2) + "\n")
        output_path.chmod(0o600)
        print(json.dumps({"status": "ready", "output_json": str(output_path)}))
        return 0
    except (ClientError, RuntimeError, OSError, ValueError) as exc:
        result["error"] = str(exc)
        output_path.write_text(json.dumps(result, indent=2) + "\n")
        output_path.chmod(0o600)
        print(
            json.dumps(
                {"status": "failed", "output_json": str(output_path)}
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
