#!/usr/bin/env python3
"""
Provision full AgentCore managed path for Builder's Session.

This script is strict by design:
  - Deploy 4 MCP Lambda servers.
  - Create/update AgentCore Gateway with Cognito JWT auth.
  - Verify expected targets are attached.
  - Render AgentCore runtime templates.
  - Deploy Runtime via @aws/agentcore CLI.
  - Emit one JSON payload with managed endpoints + status.

Any failure exits non-zero so bootstrap can fail readiness gates.
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
from pathlib import Path
from typing import Any

import boto3


EXPECTED_TARGETS = {
    "search": {
        "target_name": "pellier-discovery-search-target",
        "handler": "pellier_search_server.lambda_handler",
        "server_name": "pellier-search-server",
        "entrypoint": "scripts/deploy/pellier_search_server.py",
    },
    "pricing": {
        "target_name": "pellier-value-pricing-target",
        "handler": "pellier_pricing_server.lambda_handler",
        "server_name": "pellier-pricing-server",
        "entrypoint": "scripts/deploy/pellier_pricing_server.py",
    },
    "recommendation": {
        "target_name": "pellier-curation-recommendation-target",
        "handler": "pellier_recommend_server.lambda_handler",
        "server_name": "pellier-recommend-server",
        "entrypoint": "scripts/deploy/pellier_recommend_server.py",
    },
    "experience": {
        "target_name": "pellier-concierge-experience-target",
        "handler": "pellier_experience_server.lambda_handler",
        "server_name": "pellier-experience-server",
        "entrypoint": "scripts/deploy/pellier_experience_server.py",
    },
}

EXPECTED_TOOL_NAMES = {
    "search": [
        "semantic_search",
        "find_pieces_hybrid",
        "get_inventory_health",
        "get_low_stock_products",
        "restock_product",
    ],
    "pricing": [
        "find_deals",
        "get_price_analysis",
        "compare_products",
    ],
    "recommendation": [
        "get_recommendations",
        "get_trending_products",
    ],
    "experience": [
        "process_return",
        "escalate_to_stylist",
    ],
}


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def _parse_runtime_arn(stdout: str, stderr: str) -> str:
    for blob in (stdout, stderr):
        for line in blob.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in ("runtimeArn", "agentRuntimeArn", "arn"):
                if isinstance(payload.get(key), str):
                    return payload[key]
            runtimes = payload.get("runtimes")
            if isinstance(runtimes, list):
                for runtime in runtimes:
                    if not isinstance(runtime, dict):
                        continue
                    for key in ("arn", "runtimeArn", "agentRuntimeArn"):
                        if isinstance(runtime.get(key), str):
                            return runtime[key]
    combined = f"{stdout}\n{stderr}"
    match = re.search(
        r"(arn:aws[a-z-]*:bedrock-agentcore:[^:\s]+:\d+:runtime/[a-zA-Z0-9_-]+)",
        combined,
    )
    if match:
        return match.group(1)
    raise RuntimeError("Runtime deploy succeeded but runtime ARN was not found in output")


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _compute_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    digest = hmac.new(
        client_secret.encode("utf-8"),
        msg=f"{username}{client_id}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _authenticated_runtime_smoke(
    region: str,
    runtime_arn: str,
    user_pool_id: str,
    client_id: str,
    creds_secret_arn: str,
    client_secret_arn: str | None,
) -> dict[str, Any]:
    sm = boto3.client("secretsmanager", region_name=region)
    cognito = boto3.client("cognito-idp", region_name=region)
    runtime = boto3.client("bedrock-agentcore-runtime", region_name=region)

    creds_raw = sm.get_secret_value(SecretId=creds_secret_arn).get("SecretString", "")
    creds = json.loads(creds_raw) if creds_raw else {}
    users = creds.get("users", [])
    if not users:
        raise RuntimeError("Cognito test credentials secret has no users array")

    user0 = users[0]
    username = user0.get("username", "")
    password = user0.get("password", "")
    if not username or not password:
        raise RuntimeError("Cognito test credentials secret is missing username/password")

    auth_params: dict[str, str] = {"USERNAME": username, "PASSWORD": password}
    if client_secret_arn:
        client_secret_raw = sm.get_secret_value(SecretId=client_secret_arn).get("SecretString", "")
        client_secret_payload = json.loads(client_secret_raw) if client_secret_raw else {}
        client_secret = client_secret_payload.get("client_secret", "")
        if client_secret:
            auth_params["SECRET_HASH"] = _compute_secret_hash(username, client_id, client_secret)

    auth = cognito.admin_initiate_auth(
        UserPoolId=user_pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters=auth_params,
    )
    access_token = auth.get("AuthenticationResult", {}).get("AccessToken")
    if not access_token:
        raise RuntimeError("Failed to obtain Cognito access token for runtime smoke")

    runtime_id = runtime_arn.rsplit("/", 1)[-1]
    payload = json.dumps(
        {
            "prompt": "Smoke test: find one linen item under 150.",
            "session_id": "builders-smoke-session",
        }
    )
    invoke = runtime.invoke_agent_runtime(
        agentRuntimeId=runtime_id,
        payload=payload,
        authToken=access_token,
    )
    body = invoke.get("body")
    decoded = json.loads(body.read()) if hasattr(body, "read") else {}
    response_text = str(decoded.get("response", "")).strip()
    if not response_text:
        raise RuntimeError("Runtime smoke invoke returned empty response payload")

    return {
        "runtime_id": runtime_id,
        "username": username,
        "response_preview": response_text[:200],
    }


# The @aws/agentcore CLI is pinned. @latest drifted from a flat-config
# `deploy` (which read agentcore.json + aws-targets.json directly) to a
# stateful, CDK-based project model (create -> add -> deploy). Pinning a
# known-good version keeps every fresh participant account on identical,
# tested CLI behavior instead of whatever @latest resolves to mid-event.
AGENTCORE_CLI = "@aws/agentcore@0.18.0"

# Allowed JSON-Schema-ish runtimeVersion values the CLI accepts. The CLI
# defaults to PYTHON_3_14, which the CodeZip build / Lambda runtime may not
# support yet — pin to a known-supported line.
RUNTIME_PYTHON_VERSION = "PYTHON_3_12"


def _agentcore_project_paths(backend_dir: Path) -> tuple[Path, Path]:
    """Return (project_root, agentcore_config_path) for the scaffolded 0.18
    project. We root the project under backend_dir/.agentcore-project so the
    generated agentcore/ tree never collides with the existing backend files,
    and so `deploy` (which must run from the dir CONTAINING agentcore/) has an
    unambiguous cwd."""
    project_root = backend_dir / ".agentcore-project" / "pellier"
    config_path = project_root / "agentcore" / "agentcore.json"
    return project_root, config_path


def _patch_agentcore_config(
    config_path: Path,
    *,
    runtime_name: str,
    execution_role_arn: str,
    env_vars: dict[str, str],
    account_id: str,
    region: str,
    discovery_url: str = "",
    allowed_client: str = "",
) -> None:
    """Inject the fields the 0.18 CLI has NO flags for — the execution role,
    envVars, a pinned runtimeVersion, networkMode, and the JWT header
    allowlist — into runtimes[<our agent>], and write aws-targets.json in the
    new ARRAY shape. `agentcore add agent` sets name/entrypoint/protocol via
    flags; everything here is the gap.

    Field spellings are taken from the WORKING dat403 reference
    (`modules/05/strands/deploy/setup_deploy.sh:90-113`), which hand-writes the
    full runtime object that `agentcore deploy` consumes:
      * ``roleArn`` — NOT ``executionRoleArn``. This is the single most
        important key: ``add agent`` has no role flag, so this patch is the
        ONLY thing that sets the runtime's execution role. dat403's working
        config uses ``roleArn``; a wrong key deploys a runtime with no role and
        every Bedrock call fails at invoke.
      * ``networkMode: "PUBLIC"`` — dat403 sets it explicitly; don't rely on a
        CLI default.
      * ``requestHeaderAllowlist: ["Authorization"]`` — required for the runtime
        to forward the Cognito JWT inward.

    Defensive by design: match the runtime object by name with a single-runtime
    fallback, and only SET our fields (never strip what the CLI added). We also
    re-assert the CUSTOM_JWT authorizer block in dat403's proven shape if the
    add-agent flags didn't populate it."""
    if not config_path.is_file():
        raise RuntimeError(
            f"agentcore.json not found at {config_path} — `agentcore create`/`add agent` did not scaffold it"
        )
    config = json.loads(config_path.read_text())
    runtimes = config.get("runtimes")
    if not isinstance(runtimes, list) or not runtimes:
        raise RuntimeError(
            f"agentcore.json has no runtimes[] to patch (found: {type(runtimes).__name__}); "
            "`agentcore add agent` likely failed"
        )

    target = None
    for rt in runtimes:
        if isinstance(rt, dict) and rt.get("name") == runtime_name:
            target = rt
            break
    if target is None:
        if len(runtimes) == 1 and isinstance(runtimes[0], dict):
            target = runtimes[0]  # single-runtime project: unambiguous
        else:
            names = [rt.get("name") for rt in runtimes if isinstance(rt, dict)]
            raise RuntimeError(
                f"Could not find runtime '{runtime_name}' to patch in {names}"
            )

    # roleArn (NOT executionRoleArn) — matches dat403's working config.
    target["roleArn"] = execution_role_arn
    target["runtimeVersion"] = RUNTIME_PYTHON_VERSION
    target["networkMode"] = "PUBLIC"
    target["requestHeaderAllowlist"] = ["Authorization"]
    target["envVars"] = [{"name": k, "value": v} for k, v in env_vars.items()]

    # Re-assert the CUSTOM_JWT authorizer in dat403's proven shape if add-agent
    # didn't populate it (the flag→JSON translation is the one thing dat403
    # can't confirm). Note the runtime SDK uses lowercase-j `customJwtAuthorizer`
    # (the Gateway API uses caps `customJWTAuthorizer` — different surfaces).
    if discovery_url and allowed_client and not target.get("authorizerConfiguration"):
        target["authorizerType"] = "CUSTOM_JWT"
        target["authorizerConfiguration"] = {
            "customJwtAuthorizer": {
                "discoveryUrl": discovery_url,
                "allowedClients": [allowed_client],
            }
        }

    config_path.write_text(json.dumps(config, indent=2))

    # aws-targets.json is an ARRAY in 0.18 ([{name,account,region}]) and no
    # longer carries the execution role (that conflation is gone).
    targets_path = config_path.parent / "aws-targets.json"
    targets_path.write_text(
        json.dumps(
            [{"name": "default", "account": account_id, "region": region}],
            indent=2,
        )
    )


def _extract_runtime_arn_from_state(project_root: Path) -> str | None:
    """Prefer the authoritative deployed-state file over scraping stdout.
    The 0.18 CLI records the deployed runtime ARN in agentcore/.cli/
    deployed-state.json. Returns None if absent/unparseable so the caller can
    fall back to _parse_runtime_arn."""
    state_path = project_root / "agentcore" / ".cli" / "deployed-state.json"
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Field name is agentRuntimeArn per the probed schema; search defensively
    # for any runtime ARN-shaped value in case the key differs across minors.
    def _find_arn(node: Any) -> str | None:
        if isinstance(node, str):
            if re.fullmatch(
                r"arn:aws[a-z-]*:bedrock-agentcore:[^:\s]+:\d+:runtime/[A-Za-z0-9_-]+",
                node,
            ):
                return node
            return None
        if isinstance(node, dict):
            # Prefer the documented key first.
            for key in ("agentRuntimeArn", "runtimeArn", "arn"):
                val = node.get(key)
                if isinstance(val, str) and val.startswith("arn:"):
                    return val
            for val in node.values():
                found = _find_arn(val)
                if found:
                    return found
        if isinstance(node, list):
            for item in node:
                found = _find_arn(item)
                if found:
                    return found
        return None

    return _find_arn(state)


def _deploy_runtime_via_cli(
    *,
    backend_dir: Path,
    runtime_name: str,
    region: str,
    account_id: str,
    cognito_pool: str,
    cognito_client: str,
    execution_role_arn: str,
    gateway_url: str,
    model_id: str,
    deploy_env: dict[str, str],
) -> str:
    """Scaffold a 0.18 AgentCore project, register our in-repo orchestrator as
    a BYO agent (HTTP + CUSTOM_JWT), patch in the role/envVars the CLI can't set
    via flags, and `agentcore deploy` (CDK). Returns the deployed runtime ARN.

    Idempotent: skips `create` if the project exists, and re-adds the agent
    cleanly so a re-run (facilitator recovery) doesn't error on a duplicate."""
    project_root, config_path = _agentcore_project_paths(backend_dir)
    output_dir = project_root.parent  # `create` writes <output_dir>/<project>/
    # Only ensure the PARENT (.agentcore-project) exists – do NOT pre-create
    # project_root (.agentcore-project/pellier). `agentcore create` scaffolds
    # that folder itself and ABORTS if it already exists ("A folder named
    # 'pellier' already exists in this directory"). Pre-creating it here (the
    # old `project_root.mkdir`) defeated the `config_path.is_file()` skip-guard
    # below: the empty dir had no agentcore.json, so the guard said "create"
    # while the CLI refused the existing folder → Runtime never deployed.
    output_dir.mkdir(parents=True, exist_ok=True)

    discovery_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{cognito_pool}/.well-known/openid-configuration"
    )

    # 1. Scaffold an EMPTY project (no agent) so we can BYO ours. Skip if the
    #    project already exists AND is complete (re-run safety). If project_root
    #    exists but has no agentcore.json, a prior `create` died partway (or
    #    something pre-created the dir): the CLI would abort with "folder already
    #    exists", so clear the incomplete dir first and let create scaffold clean.
    if not config_path.is_file():
        if project_root.exists():
            shutil.rmtree(project_root, ignore_errors=True)
        _run(
            [
                "npx", "-y", AGENTCORE_CLI, "create",
                "--project-name", "pellier",
                "--no-agent",
                "--defaults",
                "--build", "CodeZip",
                "--language", "Python",
                "--framework", "Strands",
                "--model-provider", "Bedrock",
                "--protocol", "HTTP",
                "--skip-git",
                "--skip-python-setup",
                # NOTE: do NOT pass --skip-install. The 0.18 CLI scaffolds a
                # TypeScript CDK app (agentcore-cdk-app) and `deploy` compiles
                # it with `tsc`, which needs that app's node_modules
                # (aws-cdk-lib, constructs, @aws/agentcore-cdk, @types/node).
                # --skip-install skips the npm install for it → deploy fails
                # with TS2307 "Cannot find module 'aws-cdk-lib'" etc. We keep
                # --skip-python-setup because the agent is BYO Python (our own
                # backend venv); only the CDK app's Node deps must install.
                "--output-dir", str(output_dir),
                "--json",
            ],
            cwd=output_dir,
            env=deploy_env,
        )

    # 2. Register our existing orchestrator entrypoint as a BYO agent with the
    #    real CUSTOM_JWT authorizer. Remove first so a re-run is clean (the CLI
    #    errors on a duplicate agent name); ignore remove failure when absent.
    try:
        _run(
            ["npx", "-y", AGENTCORE_CLI, "remove", "agent", "--name", runtime_name, "--yes"],
            cwd=project_root,
            env=deploy_env,
        )
    except RuntimeError:
        pass  # agent not present yet — expected on first run

    _run(
        [
            "npx", "-y", AGENTCORE_CLI, "add", "agent",
            "--name", runtime_name,
            "--type", "byo",
            "--build", "CodeZip",
            "--language", "Python",
            "--framework", "Strands",
            "--model-provider", "Bedrock",
            "--protocol", "HTTP",
            "--code-location", str(backend_dir),
            "--entrypoint", "agentcore_runtime.py",
            "--authorizer-type", "CUSTOM_JWT",
            "--discovery-url", discovery_url,
            "--allowed-clients", cognito_client,
            "--json",
        ],
        cwd=project_root,
        env=deploy_env,
    )

    # 3. Patch in roleArn + envVars + runtimeVersion + networkMode +
    #    requestHeaderAllowlist (no CLI flags for these), re-assert the JWT
    #    authorizer if needed, and write aws-targets.json (array shape).
    _patch_agentcore_config(
        config_path,
        runtime_name=runtime_name,
        execution_role_arn=execution_role_arn,
        env_vars={"MCP_GATEWAY_URL": gateway_url, "AGENT_MODEL_ID": model_id},
        account_id=account_id,
        region=region,
        discovery_url=discovery_url,
        allowed_client=cognito_client,
    )

    # 3.5 Self-heal the CDK app's node_modules. `deploy` compiles agentcore/cdk
    #     with `npm run build` (tsc) but NEVER installs its deps — only `create`
    #     does. A project scaffolded by an older script version (which passed
    #     --skip-install) is skipped by the create-guard above and would fail
    #     tsc forever with TS2307 "Cannot find module 'aws-cdk-lib'". Detect the
    #     missing install and run it ourselves so re-runs recover in place.
    cdk_dir = project_root / "agentcore" / "cdk"
    if cdk_dir.is_dir() and not (cdk_dir / "node_modules" / "aws-cdk-lib").is_dir():
        _run(["npm", "install"], cwd=cdk_dir, env=deploy_env)

    # 4. Deploy (CDK) from the PROJECT ROOT (the dir containing agentcore/).
    runtime_deploy = _run(
        ["npx", "-y", AGENTCORE_CLI, "deploy", "-y", "--json"],
        cwd=project_root,
        env=deploy_env,
    )

    # 5. Prefer the authoritative deployed-state file; fall back to scraping.
    return _extract_runtime_arn_from_state(project_root) or _parse_runtime_arn(
        runtime_deploy.stdout, runtime_deploy.stderr
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision full AgentCore managed path for builders")
    parser.add_argument("--repo-path", default=os.environ.get("REPO_PATH", "."))
    parser.add_argument("--gateway-name", default="pellier-gateway")
    parser.add_argument("--runtime-name", default="pellier_orchestrator")
    parser.add_argument("--output-json", default="/tmp/pellier-agentcore-managed.json")
    args = parser.parse_args()

    repo = Path(args.repo_path).resolve()
    backend_dir = repo / "pellier" / "backend"
    deploy_dir = repo / "scripts" / "deploy"
    output_path = Path(args.output_json)

    required = {
        "AWS_REGION": _require_env("AWS_REGION"),
        "DB_CLUSTER_ARN": _require_env("DB_CLUSTER_ARN"),
        "DB_SECRET_ARN": _require_env("DB_SECRET_ARN"),
        "COGNITO_POOL": _require_env("COGNITO_POOL"),
        "COGNITO_CLIENT": _require_env("COGNITO_CLIENT"),
        "AGENTCORE_ROLE_ARN": _require_env("AGENTCORE_ROLE_ARN"),
        "COGNITO_TEST_CREDENTIALS_SECRET_ARN": _require_env("COGNITO_TEST_CREDENTIALS_SECRET_ARN"),
    }
    client_secret_arn = os.environ.get("COGNITO_CLIENT_SECRET_ARN", "").strip() or None
    db_name = os.environ.get("DB_NAME", "pellier")
    model_id = os.environ.get("AGENT_MODEL_ID", "global.anthropic.claude-opus-4-6-v1")

    result: dict[str, Any] = {
        "status": "failed",
        "region": required["AWS_REGION"],
        "gateway_name": args.gateway_name,
        "runtime_name": args.runtime_name,
        "lambdas": {},
        "gateway": {},
        "runtime": {},
        "verification": {"targets_attached": False},
    }

    try:
        lambda_arns: dict[str, str] = {}
        for surface, cfg in EXPECTED_TARGETS.items():
            cmd = [
                "python3",
                str(deploy_dir / "deploy_lambda.py"),
                "--region",
                required["AWS_REGION"],
                "--server-name",
                cfg["server_name"],
                "--db-cluster-arn",
                required["DB_CLUSTER_ARN"],
                "--secret-arn",
                required["DB_SECRET_ARN"],
                "--database",
                db_name,
                "--mcp-server-path",
                str(repo / cfg["entrypoint"]),
                "--handler",
                cfg["handler"],
            ]
            _run(cmd, cwd=repo)

            # deploy_lambda.py creates the function as f"{server_name}-function"
            # (e.g. pellier-search-server-function), NOT target_name (which is
            # the Gateway *target* alias, e.g. pellier-discovery-search-target).
            # Look it up by its real function name or get-function 404s and the
            # whole provision marks failed.
            function_name = f"{cfg['server_name']}-function"
            get_fn = _run(
                [
                    "aws",
                    "lambda",
                    "get-function",
                    "--function-name",
                    function_name,
                    "--region",
                    required["AWS_REGION"],
                    "--query",
                    "Configuration.FunctionArn",
                    "--output",
                    "text",
                ],
                cwd=repo,
            )
            arn = get_fn.stdout.strip()
            lambda_arns[surface] = arn
            result["lambdas"][surface] = {"function_arn": arn, "function_name": cfg["target_name"]}

        gateway_cmd = [
            "python3",
            str(deploy_dir / "deploy_gateway.py"),
            "--region",
            required["AWS_REGION"],
            "--gateway-name",
            args.gateway_name,
            "--search-lambda-arn",
            lambda_arns["search"],
            "--pricing-lambda-arn",
            lambda_arns["pricing"],
            "--recommendation-lambda-arn",
            lambda_arns["recommendation"],
            "--experience-lambda-arn",
            lambda_arns["experience"],
            "--cognito-user-pool-id",
            required["COGNITO_POOL"],
            "--cognito-client-id",
            required["COGNITO_CLIENT"],
        ]
        _run(gateway_cmd, cwd=repo)

        gateway_id_proc = _run(
            [
                "aws",
                "bedrock-agentcore-control",
                "list-gateways",
                "--region",
                required["AWS_REGION"],
                "--query",
                f"items[?name=='{args.gateway_name}'].gatewayId | [0]",
                "--output",
                "text",
            ],
            cwd=repo,
        )
        gateway_id = gateway_id_proc.stdout.strip()
        if not gateway_id or gateway_id == "None":
            raise RuntimeError(f"Gateway id not found for name {args.gateway_name}")

        gateway_url_proc = _run(
            [
                "aws",
                "bedrock-agentcore-control",
                "get-gateway",
                "--gateway-identifier",
                gateway_id,
                "--region",
                required["AWS_REGION"],
                "--query",
                "gatewayUrl",
                "--output",
                "text",
            ],
            cwd=repo,
        )
        gateway_url = gateway_url_proc.stdout.strip()
        result["gateway"] = {"gateway_id": gateway_id, "gateway_url": gateway_url}

        targets_proc = _run(
            [
                "aws",
                "bedrock-agentcore-control",
                "list-gateway-targets",
                "--gateway-identifier",
                gateway_id,
                "--region",
                required["AWS_REGION"],
                "--output",
                "json",
            ],
            cwd=repo,
        )
        target_payload = json.loads(targets_proc.stdout)
        attached = {item.get("name") for item in target_payload.get("items", [])}
        expected = {cfg["target_name"] for cfg in EXPECTED_TARGETS.values()}
        missing_targets = sorted(expected - attached)
        if missing_targets:
            raise RuntimeError(f"Gateway targets missing after deploy: {', '.join(missing_targets)}")
        result["verification"]["targets_attached"] = True
        result["verification"]["target_names"] = sorted(attached)

        prefixed_expected: list[str] = []
        prefixed_observed: set[str] = set()
        for surface, cfg in EXPECTED_TARGETS.items():
            for name in EXPECTED_TOOL_NAMES[surface]:
                prefixed_expected.append(f"{cfg['target_name']}__{name}")

        for item in target_payload.get("items", []):
            target_name = item.get("name")
            target_id = item.get("targetId")
            if not target_name or not target_id:
                continue
            target_detail_proc = _run(
                [
                    "aws",
                    "bedrock-agentcore-control",
                    "get-gateway-target",
                    "--gateway-identifier",
                    gateway_id,
                    # NOTE: get-gateway-target uses the SHORT form --target-id
                    # (not --target-identifier like the gateway arg). The AWS
                    # CLI is inconsistent here; --target-identifier raises
                    # "ParamValidation: the following arguments are required:
                    # --target-id" and aborts after targets are already attached.
                    "--target-id",
                    target_id,
                    "--region",
                    required["AWS_REGION"],
                    "--output",
                    "json",
                ],
                cwd=repo,
            )
            target_detail = json.loads(target_detail_proc.stdout)
            inline_tools = (
                target_detail.get("targetConfiguration", {})
                .get("mcp", {})
                .get("lambda", {})
                .get("toolSchema", {})
                .get("inlinePayload", [])
            )
            for tool in inline_tools:
                tool_name = tool.get("name")
                if isinstance(tool_name, str) and tool_name:
                    prefixed_observed.add(f"{target_name}__{tool_name}")

        missing_prefixed = sorted(set(prefixed_expected) - prefixed_observed)
        if missing_prefixed:
            raise RuntimeError(
                "Gateway tool schema missing expected prefixed tools: "
                + ", ".join(missing_prefixed)
            )
        result["verification"]["prefixed_tools_verified"] = True
        result["verification"]["prefixed_tools"] = sorted(prefixed_observed)

        account_proc = _run(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            cwd=repo,
        )
        account_id = account_proc.stdout.strip()

        deploy_env = os.environ.copy()
        deploy_env["AWS_REGION"] = required["AWS_REGION"]
        deploy_env["AWS_DEFAULT_REGION"] = required["AWS_REGION"]

        # Managed AgentCore Policy (the 4th pillar): create a Cedar policy
        # engine, gate process_return to damaged-only, and attach to THIS
        # gateway in ENFORCE mode. Policy enforces at the Gateway boundary, so
        # it gates the agents_as_tools rail (process_return runs in the
        # experience Lambda). Best-effort: a policy failure must not nuke the
        # rest of provisioning, but the dry-run/health gate surfaces it.
        try:
            gateway_arn_proc = _run(
                [
                    "aws", "bedrock-agentcore-control", "get-gateway",
                    "--gateway-identifier", gateway_id,
                    "--region", required["AWS_REGION"],
                    "--query", "gatewayArn", "--output", "text",
                ],
                cwd=repo,
            )
            gateway_arn = gateway_arn_proc.stdout.strip()
            policy_proc = _run(
                [
                    "python3", str(deploy_dir / "deploy_policy.py"),
                    "--gateway-id", gateway_id,
                    "--gateway-arn", gateway_arn,
                    "--region", required["AWS_REGION"],
                    "--mode", "ENFORCE",
                ],
                cwd=repo,
                env=deploy_env,
            )
            policy_engine_id = ""
            for line in policy_proc.stdout.splitlines():
                if line.startswith("POLICY_ENGINE_ID="):
                    policy_engine_id = line.split("=", 1)[1].strip()
            result["policy"] = {
                "policy_engine_id": policy_engine_id,
                "mode": "ENFORCE",
                "gated_tool": "process_return",
            }
            result["verification"]["managed_policy_attached"] = bool(policy_engine_id)
        except RuntimeError as exc:
            # Surface but don't abort — Runtime/Memory/Gateway still provision.
            result["policy"] = {"error": str(exc)}
            result["verification"]["managed_policy_attached"] = False

        # Scaffold the 0.18 project, register our in-repo orchestrator as a BYO
        # agent (HTTP + CUSTOM_JWT), patch in the role/envVars the CLI has no
        # flags for, and CDK-deploy. Returns the deployed runtime ARN.
        runtime_arn = _deploy_runtime_via_cli(
            backend_dir=backend_dir,
            runtime_name=args.runtime_name,
            region=required["AWS_REGION"],
            account_id=account_id,
            cognito_pool=required["COGNITO_POOL"],
            cognito_client=required["COGNITO_CLIENT"],
            execution_role_arn=required["AGENTCORE_ROLE_ARN"],
            gateway_url=gateway_url,
            model_id=model_id,
            deploy_env=deploy_env,
        )

        runtime_lookup_proc = _run(
            [
                "aws",
                "bedrock-agentcore-control",
                "list-agent-runtimes",
                "--region",
                required["AWS_REGION"],
                "--output",
                "json",
            ],
            cwd=repo,
        )
        runtime_lookup = json.loads(runtime_lookup_proc.stdout)
        runtime_items = runtime_lookup.get("agentRuntimes", [])
        # The Node CLI prefixes the deployed runtime name with the project name
        # (dat403 changelog: e.g. "pellier_pellier_orchestrator-…"), so an exact
        # match can miss a successful deploy. Match exact first, then fall back
        # to substring. (The authoritative ARN already came from
        # deployed-state.json; this lookup is only a control-plane visibility
        # gate, so a too-strict match would hard-fail an otherwise-good deploy.)
        matched = [i for i in runtime_items if i.get("agentRuntimeName") == args.runtime_name]
        if not matched:
            matched = [
                i for i in runtime_items
                if args.runtime_name in (i.get("agentRuntimeName") or "")
            ]
        if not matched:
            raise RuntimeError(f"Runtime {args.runtime_name} not found in list-agent-runtimes")
        runtime_status = matched[0].get("status") or matched[0].get("agentRuntimeStatus") or "UNKNOWN"
        result["verification"]["runtime_control_plane_visible"] = True
        result["verification"]["runtime_status"] = runtime_status

        smoke = _authenticated_runtime_smoke(
            region=required["AWS_REGION"],
            runtime_arn=runtime_arn,
            user_pool_id=required["COGNITO_POOL"],
            client_id=required["COGNITO_CLIENT"],
            creds_secret_arn=required["COGNITO_TEST_CREDENTIALS_SECRET_ARN"],
            client_secret_arn=client_secret_arn,
        )
        result["verification"]["authenticated_runtime_invoke_smoke"] = True
        result["verification"]["runtime_invoke_smoke"] = smoke

        result["runtime"] = {
            "runtime_arn": runtime_arn,
            "agent_model_id": model_id,
            "mcp_gateway_url": gateway_url,
        }
        result["status"] = "ready"

        output_path.write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        output_path.write_text(json.dumps(result, indent=2))
        print(json.dumps(result), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
