#!/usr/bin/env python3
"""Render Pellier's declarative AgentCore CLI project.

The AgentCore CLI owns Runtime, Memory, Gateway, Gateway target registrations,
AgentCore-managed service roles, and Policy. ``deploy_lambda.py`` separately
owns the external Lambda functions and their Lambda execution roles. This
renderer only writes CLI project inputs; it does not call AgentCore
control-plane APIs.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from gateway_tool_schemas import TOOL_SCHEMAS, schema_for


AGENTCORE_CLI = "@aws/agentcore@1.0.0-preview.26"
PROJECT_NAME = "pellier"
RUNTIME_NAME = "pellier_orchestrator"
MEMORY_NAME = "PellierMemory"
MEMORY_STRATEGY_NAME = "PellierUserPreferences"
MEMORY_NAMESPACE = "/pellier/preferences/{actorId}/"
GATEWAY_NAME = "pellier-gateway"
POLICY_ENGINE_NAME = "pellier_policy_engine"
EXPERIENCE_TARGET = "pellier-concierge-experience-target"
PROCESS_RETURN_ACTION = f"{EXPERIENCE_TARGET}___process_return"
RUNTIME_SOURCE_FILES = (
    Path("agentcore_runtime.py"),
    Path("services/__init__.py"),
    Path("services/agentcore_gateway.py"),
    Path("services/conversation_context.py"),
    Path("services/intent_router.py"),
)


def project_root(repo: Path) -> Path:
    return repo / ".agentcore-project" / PROJECT_NAME


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _render_runtime_source(root: Path, backend_dir: Path) -> Path:
    """Stage only the source files reachable from the managed entrypoint."""
    runtime_dir = root / "runtime-src"
    shutil.rmtree(runtime_dir, ignore_errors=True)
    runtime_dir.mkdir(parents=True)

    shutil.copy2(backend_dir / "pyproject.toml", runtime_dir / "pyproject.toml")
    for relative in RUNTIME_SOURCE_FILES:
        source = backend_dir / relative
        destination = runtime_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return runtime_dir


def baseline_policies(
    action_token: str = PROCESS_RETURN_ACTION,
    *,
    gateway_arn: str,
) -> list[dict[str, Any]]:
    """Return the shipped Cedar set added after the first CLI deployment."""
    if not gateway_arn or not gateway_arn.startswith("arn:"):
        raise ValueError(
            "Cedar policies require the deployed Gateway ARN; "
            "render policies after the first deploy with --gateway-arn"
        )
    gateway_resource = f"resource == AgentCore::Gateway::{json.dumps(gateway_arn)}"
    action = f'action == AgentCore::Action::"{action_token}"'
    return [
        {
            "name": "baseline_permit_gateway_tools",
            "description": "Permit Gateway tools by default; explicit forbids still win",
            "statement": f"permit (principal, action, {gateway_resource});",
            "validationMode": "IGNORE_ALL_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
        {
            "name": "process_return_damaged_only",
            "description": "Forbid process_return unless the item is damaged",
            "statement": (
                f"forbid (principal, {action}, {gateway_resource})\n"
                "when {\n"
                '  !(context.input has reason) || context.input.reason != "damaged"\n'
                "};"
            ),
            "validationMode": "IGNORE_ALL_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
        {
            "name": "process_return_allow_damaged",
            "description": "Explicitly permit damaged-item returns",
            "statement": (
                f"permit (principal, {action}, {gateway_resource})\n"
                "when {\n"
                '  context.input has reason && context.input.reason == "damaged"\n'
                "};"
            ),
            "validationMode": "IGNORE_ALL_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
    ]


def render_project(
    *,
    repo: Path,
    account_id: str,
    region: str,
    cognito_pool: str,
    cognito_client: str,
    lambda_arns: dict[str, str],
    model_id: str,
    workshop_id: str,
    include_policies: bool,
    action_token: str = PROCESS_RETURN_ACTION,
    gateway_arn: str = "",
) -> Path:
    """Write agentcore.json, aws-targets.json, and four tool-schema files."""
    root = project_root(repo)
    config_dir = root / "agentcore"
    schemas_dir = root / "tool-schemas"
    backend_dir = repo / "pellier" / "backend"
    runtime_dir = _render_runtime_source(root, backend_dir)
    discovery_url = (
        f"https://cognito-idp.{region}.amazonaws.com/"
        f"{cognito_pool}/.well-known/openid-configuration"
    )
    tags = {
        "Project": "pellier",
        "PellierWorkshopId": workshop_id,
    }

    targets: list[dict[str, Any]] = []
    for surface, schema in TOOL_SCHEMAS.items():
        schema_path = schemas_dir / f"{surface}.json"
        _write_json(schema_path, schema_for(surface))
        targets.append(
            {
                "name": schema["target_name"],
                "targetType": "lambdaFunctionArn",
                "lambdaFunctionArn": {
                    "lambdaArn": lambda_arns[surface],
                    "toolSchemaFile": str(schema_path.relative_to(root)),
                },
            }
        )

    project = {
        "$schema": "https://schema.agentcore.aws.dev/v1/agentcore.json",
        "name": PROJECT_NAME,
        "version": 1,
        "managedBy": "CDK",
        "tags": tags,
        "runtimes": [
            {
                "name": RUNTIME_NAME,
                "description": "Pellier governed dispatcher",
                "build": "CodeZip",
                "entrypoint": "agentcore_runtime.py",
                "codeLocation": str(runtime_dir),
                "runtimeVersion": "PYTHON_3_12",
                "envVars": [
                    {"name": "AGENT_MODEL_ID", "value": model_id},
                    {"name": "BEDROCK_ROUTER_MODEL", "value": model_id},
                ],
                "networkMode": "PUBLIC",
                "instrumentation": {"enableOtel": True},
                "protocol": "HTTP",
                "requestHeaderAllowlist": ["Authorization"],
                "authorizerType": "CUSTOM_JWT",
                "authorizerConfiguration": {
                    "customJwtAuthorizer": {
                        "discoveryUrl": discovery_url,
                        "allowedClients": [cognito_client],
                    }
                },
                "tags": tags,
            }
        ],
        "memories": [
            {
                "name": MEMORY_NAME,
                "eventExpiryDuration": 30,
                "strategies": [
                    {
                        "type": "USER_PREFERENCE",
                        "name": MEMORY_STRATEGY_NAME,
                        "description": "Extract durable shopper preferences",
                        "namespaceTemplates": [MEMORY_NAMESPACE],
                    }
                ],
                "tags": tags,
            }
        ],
        "knowledgeBases": [],
        "credentials": [],
        "payments": [],
        "evaluators": [],
        "onlineEvalConfigs": [],
        "agentCoreGateways": [
            {
                "name": GATEWAY_NAME,
                "description": "Pellier MCP tools for search, pricing, curation, and experience",
                "protocolType": "MCP",
                "targets": targets,
                "authorizerType": "CUSTOM_JWT",
                "authorizerConfiguration": {
                    "customJwtAuthorizer": {
                        "discoveryUrl": discovery_url,
                        "allowedClients": [cognito_client],
                    }
                },
                "enableSemanticSearch": True,
                "exceptionLevel": "NONE",
                "policyEngineConfiguration": {
                    "policyEngineName": POLICY_ENGINE_NAME,
                    "mode": "ENFORCE",
                },
                "tags": tags,
            }
        ],
        "policyEngines": [
            {
                "name": POLICY_ENGINE_NAME,
                "description": "Cedar authorization for Pellier Gateway tools",
                "tags": tags,
                "policies": (
                    baseline_policies(action_token, gateway_arn=gateway_arn)
                    if include_policies else []
                ),
            }
        ],
        "configBundles": [],
        "abTests": [],
        "harnesses": [],
        "datasets": [],
    }

    _write_json(config_dir / "agentcore.json", project)
    _write_json(
        config_dir / "aws-targets.json",
        [{"name": "default", "account": account_id, "region": region}],
    )
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--cognito-pool", required=True)
    parser.add_argument("--cognito-client", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--workshop-id", required=True)
    parser.add_argument("--lambda-arns", type=Path, required=True)
    parser.add_argument("--include-policies", action="store_true")
    parser.add_argument("--action-token", default=PROCESS_RETURN_ACTION)
    parser.add_argument("--gateway-arn", default="")
    args = parser.parse_args()

    lambda_arns = json.loads(args.lambda_arns.read_text())
    root = render_project(
        repo=args.repo.resolve(),
        account_id=args.account_id,
        region=args.region,
        cognito_pool=args.cognito_pool,
        cognito_client=args.cognito_client,
        lambda_arns=lambda_arns,
        model_id=args.model_id,
        workshop_id=args.workshop_id,
        include_policies=args.include_policies,
        action_token=args.action_token,
        gateway_arn=args.gateway_arn,
    )
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
