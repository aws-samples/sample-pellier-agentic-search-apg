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
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, NamedTuple
from output_guardrail import policy as output_guardrail_policy

from gateway_tool_schemas import (
    OWNER_SCOPED_GATEWAY_TOOLS,
    TOOL_SCHEMAS,
    WORKSHOP_DEFERRED_TOOLS,
    schema_for,
    workshop_published_tools,
    workshop_target_tools,
)


AGENTCORE_CLI = "@aws/agentcore@0.29.0"

# StackProps from the pinned CLI's agentcore/cdk/bin/cdk.ts scaffold. Keep this
# customization separate from resource naming: labels must not select a new stack.
_CDK_STACK_TAGS = """      tags: {
        'agentcore:project-name': spec.name,
        'agentcore:target-name': target.name,
      },"""
_CDK_STACK_TAGS_WITH_PROJECT = _CDK_STACK_TAGS.replace(
    "      tags: {\n", "      tags: {\n        ...spec.tags,\n", 1
)


def _customize_governed_cdk_tags(config_dir: Path) -> None:
    """Merge project labels into the reviewed 0.29.0 StackProps tag block."""
    entrypoint = config_dir / "cdk" / "bin" / "cdk.ts"
    if not entrypoint.exists() and not entrypoint.parent.parent.exists():
        # Configuration-only rendering is also supported. The provisioner creates
        # the CLI scaffold before rendering a project that it will deploy.
        return
    source = entrypoint.read_text(encoding="utf-8")
    original_count = source.count(_CDK_STACK_TAGS)
    customized_count = source.count(_CDK_STACK_TAGS_WITH_PROJECT)
    if original_count == 0 and customized_count == 1:
        return
    if original_count != 1 or customized_count != 0:
        raise SystemExit(
            f"Unsupported {AGENTCORE_CLI} CDK stack tags in {entrypoint}; "
            "review the pinned scaffold before deploying governed labels"
        )
    entrypoint.write_text(
        source.replace(_CDK_STACK_TAGS, _CDK_STACK_TAGS_WITH_PROJECT, 1),
        encoding="utf-8",
    )


def _deployment_suffix(value: str | None = None) -> str:
    """An optional label that isolates a second deployment in one account.

    ``PELLIER_DEPLOYMENT_SUFFIX=rc`` renders ``pellier-rc`` resources and a
    ``pellierrc`` CLI project beside a live ``pellier`` set, so a release
    candidate can be deployed and proved without touching the environment a
    workshop or a demo is running on. Empty by default, which is what every
    workshop box uses. Lowercase letters and digits only, so the label is valid
    in every resource name it lands in; the CLI project name in particular
    accepts nothing but letters and digits.
    """
    raw = (os.environ.get("PELLIER_DEPLOYMENT_SUFFIX", "") if value is None else value).strip().lower()
    if raw and not re.fullmatch(r"[a-z][a-z0-9]{0,11}", raw):
        raise SystemExit(
            "PELLIER_DEPLOYMENT_SUFFIX must be 1-12 lowercase letters or digits"
        )
    return raw


class DeploymentIdentity(NamedTuple):
    suffix: str
    project_name: str
    runtime_name: str
    operator_runtime_name: str
    memory_name: str
    gateway_name: str
    policy_engine_name: str
    server_prefix: str


def deployment_identity(suffix: str | None = None) -> DeploymentIdentity:
    """Resolve one immutable set of names after configuration is available."""
    suffix = _deployment_suffix(suffix)
    dash = f"-{suffix}" if suffix else ""
    under = f"_{suffix}" if suffix else ""
    return DeploymentIdentity(
        suffix, f"pellier{suffix}", f"pellier{under}_orchestrator",
        f"pellier{under}_operator", f"Pellier{suffix.capitalize()}Memory",
        f"pellier{dash}-gateway", f"pellier{under}_policy_engine", f"pellier{dash}",
    )


def deployment_identity_from_repo(repo: Path) -> DeploymentIdentity:
    """Read only the saved label as data; explicit process input always wins."""
    if "PELLIER_DEPLOYMENT_SUFFIX" in os.environ:
        return deployment_identity()
    for path in (repo / "pellier/backend/.env", repo / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key.strip() == "PELLIER_DEPLOYMENT_SUFFIX":
                return deployment_identity(value.strip().strip("\"'"))
    return deployment_identity("")


# Compatibility aliases for consumers that inspect the default identity. The
# provisioner passes a resolved identity after loading its saved configuration.
_IDENTITY = deployment_identity()
DEPLOYMENT_SUFFIX = _IDENTITY.suffix
PROJECT_NAME = _IDENTITY.project_name
RUNTIME_NAME = _IDENTITY.runtime_name
OPERATOR_RUNTIME_NAME = _IDENTITY.operator_runtime_name
MEMORY_NAME = _IDENTITY.memory_name
GATEWAY_NAME = _IDENTITY.gateway_name
POLICY_ENGINE_NAME = _IDENTITY.policy_engine_name


def customer_claim_resource_names() -> tuple[str, str]:
    """Resolve trigger names after callers have loaded their environment."""
    function = f"{deployment_identity().server_prefix}-cognito-customer-claim"
    return function, f"{function}-role"


EXPERIENCE_TARGET = "pellier-concierge-experience-target"
INITIATE_RETURN_ACTION = f"{EXPERIENCE_TARGET}___initiate_return"
RECOMMENDATION_TARGET = "pellier-curation-recommendation-target"
CUSTOMER_PREFERENCES_ACTION = f"{RECOMMENDATION_TARGET}___get_customer_preferences"
AUDIT_TRAIL_ACTION = f"{RECOMMENDATION_TARGET}___get_audit_trail"
RESTOCK_ACTION = "pellier-discovery-search-target___restock_inventory"
ISSUE_CREDIT_ACTION = f"{EXPERIENCE_TARGET}___issue_credit"
WORKSHOP_RUNTIME_EXPOSURE = "public-workshop-only"

# The packaged-file list and the digest algorithm live in the backend so that
# what is staged and what is fingerprinted cannot drift apart. Import them
# rather than keeping a second copy of the tuple here: a file added to the
# runtime but not to the shared list would ship unfingerprinted, weakening the
# executed-revision proof silently instead of failing loudly.
_BACKEND_DIR = Path(__file__).resolve().parents[2] / "pellier" / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.build_fingerprint import (  # noqa: E402
    FINGERPRINT_ENV_VAR,
    RUNTIME_DEPENDENCY_FILES,
    RUNTIME_SOURCE_FILES,
    compute_fingerprint,
)


def project_root(repo: Path, deployment_suffix: str | None = None) -> Path:
    return repo / ".agentcore-project" / deployment_identity(deployment_suffix).project_name


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _render_runtime_source(root: Path, backend_dir: Path) -> tuple[Path, str]:
    """Stage the source files reachable from the managed entrypoint, and digest them.

    Returns the staged directory and the content fingerprint of what was staged.
    The fingerprint is injected as an environment variable on the runtime rather
    than written into a staged file, so it cannot alter the very bytes it
    describes.
    """
    runtime_dir = root / "runtime-src"
    shutil.rmtree(runtime_dir, ignore_errors=True)
    runtime_dir.mkdir(parents=True)

    for relative in RUNTIME_DEPENDENCY_FILES:
        shutil.copy2(backend_dir / relative, runtime_dir / relative)
    for relative in RUNTIME_SOURCE_FILES:
        source = backend_dir / relative
        destination = runtime_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    # Digest the staged copy, not the working tree: this is the thing that ships.
    return runtime_dir, compute_fingerprint(runtime_dir)


CUSTOMER_CLAIM = "custom:customer_id"
STAFF_CLAIM = "custom:staff_scope"
STAFF_RETURNS_SCOPE = "returns"
OAUTH_PRINCIPAL = "principal is AgentCore::OAuthUser"


def _gateway_resource(gateway_arn: str) -> str:
    """The resource clause every tool-specific policy must carry.

    The service rejects ``resource is AgentCore::Gateway`` once the action is
    constrained ("constrain the resource to a specific AgentCore::Gateway
    resource when creating tool-specific policies", live 2026-09-09), and the
    CLI passes statements through verbatim. So the ARN is a render-time input,
    which is why policies render only after the Gateway exists.
    """
    if not gateway_arn or not gateway_arn.startswith("arn:"):
        raise SystemExit(
            "refusing to render Cedar policies without the deployed Gateway ARN; "
            "render policies after the first deploy, with --gateway-arn"
        )
    return f'resource == AgentCore::Gateway::"{gateway_arn}"'


def _customer_scoped_permit_statement(action: str, gateway_arn: str) -> str:
    """Permit a customer-scoped read only for the customer the token names.

    The principal is typed: an untyped ``hasTag`` rule fails validation because
    an IAM principal carries no tags, so the analyzer reports it as denying
    every request. ``custom:customer_id`` is stamped by the Cognito pre-token
    trigger from the principal mapping, never from anything a shopper can
    write, and Cedar sees it as a principal tag (live-proved 2026-09-09).
    """
    return (
        f"permit ({OAUTH_PRINCIPAL}, action == AgentCore::Action::\"{action}\", "
        f"{_gateway_resource(gateway_arn)})\n"
        "when {\n"
        f'  principal.hasTag("{CUSTOMER_CLAIM}") &&\n'
        "  context.input has customer_id &&\n"
        f'  principal.getTag("{CUSTOMER_CLAIM}") == context.input.customer_id\n'
        "};"
    )


def baseline_policies(
    action_token: str = INITIATE_RETURN_ACTION,
    *,
    gateway_arn: str,
) -> list[dict[str, Any]]:
    """The fail-closed Cedar baseline a fresh workshop provision installs.

    Every policy is a permit with a typed principal, pinned to one Gateway ARN,
    and every permit that touches customer data requires an identity claim
    the pre-token trigger stamped from a server-controlled mapping. There is
    no forbid in the baseline: Cedar is default-deny, forbid wins over permit,
    and a forbid scoped too widely would silently block the staff permit as
    well. The one forbid in the workshop is the Lab 4 rule a participant
    writes, and it is scoped by ``when`` to principals carrying a customer
    claim so it never touches staff.

    THE PERMITS

    1. ``baseline_permit_workshop_tools`` — an EXACT allow-list of the
       catalogue reads that expose no customer data. Never a wildcard: a
       wildcard hands every future published tool a permit the moment it
       appears. Any authenticated ``AgentCore::OAuthUser`` may call these.

    2. ``get_customer_preferences_owner_only`` and
       ``get_audit_trail_owner_only`` — the two customer-scoped reads, each
       permitted only when ``custom:customer_id`` equals the requested
       ``customer_id``. The Lambda receives no verified principal, so this is
       the only place the caller's identity meets the caller-controlled input
       before the target runs.

    3. ``initiate_return_shopper_damaged`` — a shopper (any principal with a
       customer claim) may file a return whose stated reason is ``damaged``.
       The ownership condition binding the claim to
       ``context.input.customer_id`` is absent on purpose. That is Lab 4: a
       participant observes
       that Marco's token can file Theo's return, writes the forbid, and
       proves the DENY is theirs. ``tests/test_fresh_policy_set.py`` fails if
       the ownership binding reappears here.

    4. ``initiate_return_staff_scope`` and ``issue_credit_staff_scope`` — staff
       (principals whose ``custom:staff_scope`` is ``returns``) may execute a
       return or a store credit the operator desk confirmed. The desk calls the
       Gateway with the operator's own token, so each permit
       authorizes a person, not a service. Neither carries a reason condition: a resolved
       dispute is not a damaged-goods return. No shopper permit names
       ``issue_credit``, so a shopper token is denied it by default.

    5. When Lab 3 publishes ``get_ticket_history``, an owner-only permit for it
       lands in the same deployment as its publication.

    EXCLUDED

        restock_inventory   an operator capability with no shopper permit.
                            Cedar is default-deny, so omission is the control.
        issue_credit        published, staff only: its one permit requires the
                            staff scope claim and no shopper-facing
                            specialist may bind it.

    A token with neither claim is an authenticated stranger. It may read the
    catalogue and nothing else. This is a teaching baseline, not a claim about a
    complete production posture: the Lab 4 solution adds the return ownership
    dimension, and a production deployment would keep it.
    """
    gateway = _gateway_resource(gateway_arn)
    published = workshop_target_tools()
    reviewed_tools = {
        "search_products", "search_products_hybrid", "browse_category",
        "check_inventory", "get_low_stock", "get_price_analysis",
        "compare_products", "get_trending_products", "get_return_policy",
        "get_related_products", "escalate_to_human",
    }
    allowed: list[str] = [
        f"{target}___{tool}"
        for target, tools in published.items()
        for tool in tools
        if tool in reviewed_tools
    ]
    if not allowed:
        raise SystemExit(
            "refusing to render a baseline permit that permits nothing; "
            "check WORKSHOP_DEFERRED_TOOLS"
        )
    action_list = ",\n".join(
        f'    AgentCore::Action::"{action}"' for action in sorted(allowed)
    )
    policies: list[dict[str, Any]] = [
        {
            "name": "baseline_permit_workshop_tools",
            "description": (
                f"Permit exactly the {len(allowed)} catalogue reads that expose no "
                "customer data. No wildcard, so a newly published tool is denied by default."
            ),
            "statement": (
                f"permit (\n  {OAUTH_PRINCIPAL},\n  action in [\n{action_list}\n  ],\n  {gateway}\n);"
            ),
            "validationMode": "FAIL_ON_ANY_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
    ]
    for tool in sorted(OWNER_SCOPED_GATEWAY_TOOLS):
        target = next(
            (name for name, tools in published.items() if tool in tools), None
        )
        if target is None:
            continue
        policies.append({
            "name": f"{tool}_owner_only",
            "description": (
                f"Permit {tool} only when the token's customer claim names the requested customer"
            ),
            "statement": _customer_scoped_permit_statement(f"{target}___{tool}", gateway_arn),
            "validationMode": "FAIL_ON_ANY_FINDINGS",
            "enforcementMode": "ACTIVE",
        })
    policies.extend([
        {
            "name": "initiate_return_shopper_damaged",
            "description": (
                "Permit a shopper with a customer claim to file a return whose reason is damaged"
            ),
            "statement": (
                f"permit ({OAUTH_PRINCIPAL}, action == AgentCore::Action::\"{action_token}\", "
                f"{gateway})\n"
                "when {\n"
                f'  principal.hasTag("{CUSTOMER_CLAIM}") &&\n'
                '  context.input has reason && context.input.reason == "damaged"\n'
                "};"
            ),
            "validationMode": "FAIL_ON_ANY_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
        {
            "name": "initiate_return_staff_scope",
            "description": (
                "Permit staff holding the returns scope to execute a confirmed return"
            ),
            "statement": (
                f"permit ({OAUTH_PRINCIPAL}, action == AgentCore::Action::\"{action_token}\", "
                f"{gateway})\n"
                "when {\n"
                f'  principal.hasTag("{STAFF_CLAIM}") &&\n'
                f'  principal.getTag("{STAFF_CLAIM}") == "{STAFF_RETURNS_SCOPE}"\n'
                "};"
            ),
            "validationMode": "FAIL_ON_ANY_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
        {
            "name": "issue_credit_staff_scope",
            "description": (
                "Permit staff holding the returns scope to execute a confirmed store credit"
            ),
            "statement": (
                f"permit ({OAUTH_PRINCIPAL}, action == AgentCore::Action::\"{ISSUE_CREDIT_ACTION}\", "
                f"{gateway})\n"
                "when {\n"
                f'  principal.hasTag("{STAFF_CLAIM}") &&\n'
                f'  principal.getTag("{STAFF_CLAIM}") == "{STAFF_RETURNS_SCOPE}"\n'
                "};"
            ),
            "validationMode": "FAIL_ON_ANY_FINDINGS",
            "enforcementMode": "ACTIVE",
        },
    ])
    policies.append({
        "name": "replace_damaged_item_staff_scope",
        "description": "Permit returns staff to execute an approved order-bound replacement",
        "statement": (
            f'permit ({OAUTH_PRINCIPAL}, action == AgentCore::Action::"{EXPERIENCE_TARGET}___replace_damaged_item", '
            f"{gateway})\nwhen {{\n"
            f'  principal.hasTag("{STAFF_CLAIM}") &&\n'
            f'  principal.getTag("{STAFF_CLAIM}") == "{STAFF_RETURNS_SCOPE}" &&\n'
            '  context.input.reason == "damaged"\n};'
        ),
        "validationMode": "FAIL_ON_ANY_FINDINGS",
        "enforcementMode": "ACTIVE",
    })
    return policies


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
    opus_model_id: str | None = None,
    sonnet_model_id: str | None = None,
    fast_model_id: str | None = None,
    action_token: str = INITIATE_RETURN_ACTION,
    gateway_arn: str = "",
    identity: DeploymentIdentity | None = None,
) -> Path:
    """Write agentcore.json, aws-targets.json, and four tool-schema files."""
    governed = os.environ.get("WORKSHOP_FORMAT", "").strip().lower() == "governed"
    identity = identity or deployment_identity()
    root = project_root(repo, identity.suffix)
    config_dir = root / "agentcore"
    if governed:
        _customize_governed_cdk_tags(config_dir)
    schemas_dir = root / "tool-schemas"
    backend_dir = repo / "pellier" / "backend"
    runtime_dir, build_fingerprint = _render_runtime_source(root, backend_dir)
    runtime_opus_model = opus_model_id or model_id
    runtime_sonnet_model = sonnet_model_id or model_id
    runtime_fast_model = fast_model_id or model_id
    discovery_url = (
        f"https://cognito-idp.{region}.amazonaws.com/"
        f"{cognito_pool}/.well-known/openid-configuration"
    )
    tags = {
        "Project": "pellier",
        "PellierWorkshopId": workshop_id,
        "PellierDeploymentClass": "workshop",
        "PellierRuntimeExposure": WORKSHOP_RUNTIME_EXPOSURE,
    }
    if governed:
        tags.update(
            Name="pellier-governed-managed",
            PellierVariant="governed",
            PellierComponent="agentcore",
        )

    targets: list[dict[str, Any]] = []
    for surface, schema in TOOL_SCHEMAS.items():
        schema_path = schemas_dir / f"{surface}.json"
        _write_json(schema_path, schema_for(surface, workshop=True))
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
        "$schema": "https://raw.githubusercontent.com/aws/agentcore-cli/v0.29.0/schemas/agentcore.schema.v1.json",
        "name": identity.project_name,
        "version": 1,
        "managedBy": "CDK",
        "tags": tags,
        "runtimes": [
            {
                "name": identity.runtime_name,
                "description": (
                    "Pellier governed dispatcher "
                    "(workshop-only public runtime; not production-ready)"
                ),
                "build": "CodeZip",
                "entrypoint": "agentcore_runtime.py",
                "codeLocation": str(runtime_dir),
                "runtimeVersion": "PYTHON_3_12",
                "envVars": [
                    {"name": "AGENT_MODEL_ID", "value": model_id},
                    {"name": "BEDROCK_ROUTER_MODEL", "value": model_id},
                    {
                        "name": "BEDROCK_OPUS_MODEL",
                        "value": runtime_opus_model,
                    },
                    {
                        "name": "BEDROCK_SONNET_MODEL",
                        "value": runtime_sonnet_model,
                    },
                    {
                        "name": "BEDROCK_REPORTING_MODEL",
                        "value": runtime_sonnet_model,
                    },
                    {
                        "name": "BEDROCK_FAST_MODEL",
                        "value": runtime_fast_model,
                    },
                    {
                        "name": "UNIFIED_TRACES_DESTINATION_ENABLED",
                        "value": "true",
                    },
                    # The digest of the sources staged immediately above. The
                    # entrypoint echoes it on every response so a participant can
                    # prove Runtime executed the revision they just packaged
                    # rather than a previous deployment. Carried as an env var,
                    # not a staged file, so it cannot change the bytes it
                    # describes.
                    {
                        "name": FINGERPRINT_ENV_VAR,
                        "value": build_fingerprint,
                    },
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
                "name": identity.memory_name,
                "eventExpiryDuration": 30,
                "strategies": [
                    {
                        "type": "USER_PREFERENCE",
                        "name": "PellierUserPreferences",
                        "description": "Extract durable shopper preferences",
                        "namespaceTemplates": ["/pellier/preferences/{actorId}/"],
                    },
                    {
                        "type": "SEMANTIC",
                        "name": "PellierFacts",
                        "namespaceTemplates": ["/pellier/facts/{actorId}/"],
                    },
                    {
                        "type": "SUMMARIZATION",
                        "name": "PellierSessionSummary",
                        "namespaceTemplates": ["/pellier/summaries/{actorId}/{sessionId}/"],
                    },
                    {
                        "type": "EPISODIC",
                        "name": "PellierEpisodes",
                        "namespaceTemplates": ["/pellier/episodes/{actorId}/{sessionId}/"],
                        "reflectionNamespaceTemplates": ["/pellier/episodes/{actorId}/"],
                    }
                ],
                "tags": tags,
            }
        ],
        "credentials": [],
        "payments": [],
        "evaluators": [],
        "onlineEvalConfigs": [],
        "agentCoreGateways": [
            {
                "name": identity.gateway_name,
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
                    "policyEngineName": identity.policy_engine_name,
                    "mode": "ENFORCE",
                },
                "tags": tags,
            }
        ],
        "policyEngines": [
            {
                "name": identity.policy_engine_name,
                "description": "Cedar authorization for Pellier Gateway tools",
                "tags": tags,
                "policies": (
                    baseline_policies(action_token, gateway_arn=gateway_arn)
                    + [output_guardrail_policy(gateway_arn)]
                    if include_policies
                    else []
                ),
            }
        ],
    }

    # A separate IAM-authenticated endpoint accepts evidence only from the
    # backend role. Shopper JWTs cannot invoke the Operator graph.
    project["runtimes"].append({
        "name": identity.operator_runtime_name,
        "description": "Pellier read-only Operator investigation and resolution graph",
        "build": "CodeZip",
        "entrypoint": "operator_agentcore_runtime.py",
        "codeLocation": str(runtime_dir),
        "runtimeVersion": "PYTHON_3_12",
        "envVars": [
            {"name": "AGENT_MODEL_ID", "value": runtime_sonnet_model},
            {"name": "BEDROCK_SONNET_MODEL", "value": runtime_sonnet_model},
            {"name": "UNIFIED_TRACES_DESTINATION_ENABLED", "value": "true"},
            {"name": FINGERPRINT_ENV_VAR, "value": build_fingerprint},
        ],
        "networkMode": "PUBLIC",
        "instrumentation": {"enableOtel": True},
        "protocol": "HTTP",
        "tags": tags,
    })
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
    parser.add_argument("--opus-model-id")
    parser.add_argument("--sonnet-model-id")
    parser.add_argument("--fast-model-id")
    parser.add_argument("--workshop-id", required=True)
    parser.add_argument("--lambda-arns", type=Path, required=True)
    parser.add_argument("--include-policies", action="store_true")
    parser.add_argument("--action-token", default=INITIATE_RETURN_ACTION)
    parser.add_argument(
        "--gateway-arn",
        default="",
        help="Deployed Gateway ARN; required with --include-policies",
    )
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
        opus_model_id=args.opus_model_id,
        sonnet_model_id=args.sonnet_model_id,
        fast_model_id=args.fast_model_id,
        action_token=args.action_token,
        gateway_arn=args.gateway_arn,
        identity=deployment_identity_from_repo(args.repo.resolve()),
    )
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
