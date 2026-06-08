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


def _render_runtime_templates(backend_dir: Path, substitutions: dict[str, str]) -> None:
    pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
    templates = [
        (backend_dir / "agentcore.json.template", backend_dir / "agentcore.json"),
        (backend_dir / "aws-targets.json.template", backend_dir / "aws-targets.json"),
    ]
    for src, dst in templates:
        if not src.is_file():
            raise RuntimeError(f"Template missing: {src}")
        body = src.read_text()
        rendered = pattern.sub(lambda m: substitutions.get(m.group(1), ""), body)
        dst.write_text(rendered)


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

        substitutions = {
            "AGENTCORE_ROLE_ARN": required["AGENTCORE_ROLE_ARN"],
            "OAUTH_ISSUER_URL": (
                f"https://cognito-idp.{required['AWS_REGION']}.amazonaws.com/{required['COGNITO_POOL']}"
            ),
            "COGNITO_CLIENT": required["COGNITO_CLIENT"],
            "MCP_GATEWAY_URL": gateway_url,
            "AGENT_MODEL_ID": model_id,
            "AWS_ACCOUNT": account_id,
            "AWS_REGION": required["AWS_REGION"],
        }
        _render_runtime_templates(backend_dir, substitutions)

        deploy_env = os.environ.copy()
        deploy_env["AWS_REGION"] = required["AWS_REGION"]
        deploy_env["AWS_DEFAULT_REGION"] = required["AWS_REGION"]

        runtime_deploy = _run(
            ["npx", "-y", "@aws/agentcore@latest", "deploy", "-y", "--json"],
            cwd=backend_dir,
            env=deploy_env,
        )
        runtime_arn = _parse_runtime_arn(runtime_deploy.stdout, runtime_deploy.stderr)

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
        matched = [item for item in runtime_items if item.get("agentRuntimeName") == args.runtime_name]
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
