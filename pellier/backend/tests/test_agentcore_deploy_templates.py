"""Static tests for Pellier's AgentCore CLI 0.29 project contract."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import os
import shutil
import subprocess
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "pellier" / "backend"
DEPLOY_DIR = REPO_ROOT / "scripts" / "deploy"
DEPLOY_SCRIPT = DEPLOY_DIR / "deploy_all.sh"
PROVISIONER_PATH = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"
RENDERER_PATH = DEPLOY_DIR / "render_agentcore_project.py"
ENTRYPOINT = BACKEND_DIR / "agentcore_runtime.py"
RUNTIME_SERVICE = BACKEND_DIR / "services" / "agentcore_runtime.py"
RUNTIME_SOLUTION = (
    REPO_ROOT / "solutions" / "the-ledger" / "services" / "agentcore_runtime.py"
)
PYPROJECT = BACKEND_DIR / "pyproject.toml"

if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

import gateway_tool_schemas as schemas_module  # noqa: E402
import render_agentcore_project as renderer  # noqa: E402


def _load_provisioner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "pellier_agentcore_provisioner", PROVISIONER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lambda_arns() -> dict[str, str]:
    return {
        surface: f"arn:aws:lambda:us-east-1:123456789012:function:pellier-{surface}"
        for surface in renderer.TOOL_SCHEMAS
    }


def _seed_runtime_sources(repo: Path) -> None:
    backend = repo / "pellier" / "backend"
    for relative in (
        Path("pyproject.toml"),
        Path("uv.lock"),
        *renderer.RUNTIME_SOURCE_FILES,
    ):
        source = BACKEND_DIR / relative
        destination = backend / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    # The checked-in skills and Lab 4's policy sit beside pellier/ at the repository root.
    for relative in (*renderer.RUNTIME_SKILL_FILES, renderer.CREDIT_LIMIT_SOURCE):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)


def _render(tmp_path: Path, *, include_policies: bool, runtime_arns=None) -> tuple[Path, dict[str, Any]]:
    repo = tmp_path / "repo"
    _seed_runtime_sources(repo)
    root = renderer.render_project(
        repo=repo,
        account_id="123456789012",
        region="us-east-1",
        cognito_pool="us-east-1_example",
        cognito_client="client-id",
        lambda_arns=_lambda_arns(),
        model_id="global.anthropic.claude-sonnet-5",
        workshop_id="p12345678",
        include_policies=include_policies,
        gateway_arn=TEST_GATEWAY_ARN if include_policies else "",
        runtime_arns=runtime_arns,
    )
    config = json.loads((root / "agentcore" / "agentcore.json").read_text())
    return root, config


TEST_GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"


def test_the_codezip_runtime_exports_to_the_group_the_cli_queries(tmp_path):
    identity = renderer.deployment_identity()
    arns = {
        identity.runtime_name: "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier_orchestrator-abc123",
    }
    _, project = _render(tmp_path, include_policies=False, runtime_arns=arns)
    for runtime in project["runtimes"]:
        env = {item["name"]: item["value"] for item in runtime["envVars"]}
        identifier = arns[runtime["name"]].rsplit("/", 1)[-1]
        group = "/aws/bedrock-agentcore/runtimes/" + identifier + "-DEFAULT"
        assert env["OTEL_EXPORTER_OTLP_TRACES_HEADERS"] == f"x-aws-log-group={group},x-aws-log-stream=spans"
        assert "x-aws-log-stream=runtime-logs" in env["OTEL_EXPORTER_OTLP_LOGS_HEADERS"]
        assert group in env["OTEL_EXPORTER_OTLP_LOGS_HEADERS"]


def test_agentcore_cli_is_pinned_once() -> None:
    assert renderer.AGENTCORE_CLI == "@aws/agentcore@0.29.0"
    source = PROVISIONER_PATH.read_text()
    assert "AGENTCORE_CLI" in source
    assert "@aws/agentcore@latest" not in source


@pytest.mark.parametrize("command", [("traces", "list"), ("traces", "get"), ("invoke",)])
def test_cli_endpoint_alias_does_not_inherit_or_replace_application_arn(
    tmp_path: Path, monkeypatch, command: tuple[str, ...],
) -> None:
    provisioner = _load_provisioner()
    application_env = {
        "AGENTCORE_RUNTIME_ENDPOINT": (
            "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test-runtime"
        ),
        "AWS_REGION": "us-east-1",
    }
    observed = {}

    def run(args, *, cwd, env):
        observed.update(args=args, cwd=cwd, env=env)
        return subprocess.CompletedProcess(args, 0, stdout='{"success": true}')

    monkeypatch.setattr(provisioner, "_run", run)
    result = provisioner._agentcore(tmp_path, *command, env=application_env)
    assert result.returncode == 0
    assert observed["env"]["AGENTCORE_RUNTIME_ENDPOINT"] == "DEFAULT"
    assert observed["env"]["AWS_REGION"] == application_env["AWS_REGION"]
    assert observed["args"][-len(command):] == list(command)
    assert observed["cwd"] == tmp_path
    assert application_env["AGENTCORE_RUNTIME_ENDPOINT"].startswith("arn:")


def test_renderer_emits_valid_cdk_managed_project_shape(tmp_path: Path) -> None:
    root, project = _render(tmp_path, include_policies=False)

    assert project["managedBy"] == "CDK"
    assert project["name"] == "pellier"
    assert project["version"] == 1
    assert project["credentials"] == []
    assert project["payments"] == []
    assert json.loads((root / "agentcore" / "aws-targets.json").read_text()) == [
        {
            "name": "default",
            "account": "123456789012",
            "region": "us-east-1",
        }
    ]


def test_runtime_uses_cli_managed_role_and_resource_discovery(tmp_path: Path) -> None:
    root, project = _render(tmp_path, include_policies=False)
    runtime = project["runtimes"][0]

    assert runtime["name"] == renderer.RUNTIME_NAME
    assert runtime["build"] == "CodeZip"
    assert runtime["entrypoint"] == "agentcore_runtime.py"
    assert runtime["runtimeVersion"] == "PYTHON_3_12"
    assert runtime["protocol"] == "HTTP"
    assert runtime["networkMode"] == "PUBLIC"
    assert runtime["tags"]["PellierDeploymentClass"] == "workshop"
    assert (
        runtime["tags"]["PellierRuntimeExposure"]
        == renderer.WORKSHOP_RUNTIME_EXPOSURE
    )
    assert "workshop-only public runtime" in runtime["description"]
    assert runtime["requestHeaderAllowlist"] == ["Authorization"]
    assert runtime["authorizerType"] == "CUSTOM_JWT"
    assert "executionRoleArn" not in runtime
    assert Path(runtime["codeLocation"]) == root / "runtime-src"

    env = {item["name"]: item["value"] for item in runtime["envVars"]}

    # The build fingerprint is a content digest of the staged sources, so it
    # changes whenever the runtime source changes -- which is the point. Assert
    # its shape and that it matches what the renderer digested, then compare the
    # rest of the environment exactly.
    build_fingerprint = env.pop(renderer.FINGERPRINT_ENV_VAR)
    assert len(build_fingerprint) == 64
    assert set(build_fingerprint) <= set("0123456789abcdef")
    assert build_fingerprint == renderer.compute_fingerprint(
        root / "runtime-src", skills_root=root / "runtime-src"
    )

    assert env == {
        "AGENT_MODEL_ID": "global.anthropic.claude-sonnet-5",
        "BEDROCK_OPUS_MODEL": "global.anthropic.claude-sonnet-5",
        "BEDROCK_REPORTING_MODEL": "global.anthropic.claude-sonnet-5",
        "BEDROCK_SONNET_MODEL": "global.anthropic.claude-sonnet-5",
        "UNIFIED_TRACES_DESTINATION_ENABLED": "true",
    }
    assert runtime["instrumentation"] == {"enableOtel": True}
    assert "AGENTCORE_GATEWAY_URL" not in env
    assert "AGENTCORE_MEMORY_ID" not in env


def test_runtime_bundle_contains_only_managed_import_graph(tmp_path: Path) -> None:
    root, _ = _render(tmp_path, include_policies=False)
    runtime_dir = root / "runtime-src"
    actual = {
        path.relative_to(runtime_dir)
        for path in runtime_dir.rglob("*")
        if path.is_file()
    }
    assert actual == {
        Path("pyproject.toml"),
        Path("uv.lock"),
        *renderer.RUNTIME_SOURCE_FILES,
        *renderer.RUNTIME_SKILL_FILES,
    }
    assert Path("config.py") not in actual
    assert Path("services/specialist_models.py") in actual
    # The skills ship inside the bundle's skills package, where the loader
    # looks when there is no repository root beside it.
    assert Path("skills/the-gift-table/SKILL.md") in actual
    assert not any("tests" in path.parts for path in actual)


def test_the_staged_bundle_loads_its_own_skills_into_the_managed_prompt(tmp_path: Path) -> None:
    """From the bundle alone, the managed Support agent carries its skills and output rules."""
    root, _ = _render(tmp_path, include_policies=False)
    runtime_dir = root / "runtime-src"
    env = os.environ.copy()
    env.update({
        "PELLIER_DISABLE_DOTENV": "1",
        "AGENTCORE_GATEWAY_URL": "https://gateway.example.test/mcp",
        "AGENT_MODEL_ID": "test-model",
        "PYTHONPATH": str(runtime_dir),
    })
    env.pop("PELLIER_SKILLS_DIR", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from services.agentcore_gateway import _managed_specialist_spec; "
                "_, prompt, _, skills = _managed_specialist_spec('support'); "
                "print(json.dumps({'names': [s['name'] for s in skills], "
                "'paths': [s['path'] for s in skills], "
                "'in_prompt': 'The Care Card' in prompt, "
                "'rules': 'Set credit_request to true only when' in prompt}))"
            ),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["names"] == ["the-care-card", "the-proof-counter"]
    assert report["paths"] == ["skills/the-care-card/SKILL.md", "skills/the-proof-counter/SKILL.md"]
    assert report["in_prompt"] is True
    assert report["rules"] is True


def test_runtime_bridges_cli_injected_discovery_names() -> None:
    """The entrypoint resolves the injected names by shape, not by spelling.

    The CLI names the variables after the project's resources, so the default
    ``pellier-gateway`` and a suffixed ``pellier-rc-gateway`` inject different
    names; a hardcoded spelling left a suffixed Runtime without its Gateway.
    """
    from services.runtime_env import bridge_cli_injected_names

    source = ENTRYPOINT.read_text()
    assert "bridge_cli_injected_names(os.environ)" in source
    assert "AGENTCORE_GATEWAY_PELLIER_GATEWAY_URL" not in source

    default = {
        "AGENTCORE_GATEWAY_PELLIER_GATEWAY_URL": "https://d/mcp",
        "MEMORY_PELLIERMEMORY_ID": "mem-d",
    }
    assert bridge_cli_injected_names(default) == {
        "AGENTCORE_GATEWAY_URL": "https://d/mcp", "AGENTCORE_MEMORY_ID": "mem-d",
    }
    suffixed = {
        "AGENTCORE_GATEWAY_PELLIER_RC_GATEWAY_URL": "https://rc/mcp",
        "AGENTCORE_GATEWAY_PELLIER_RC_GATEWAY_AUTH_TYPE": "CUSTOM_JWT",
        "MEMORY_PELLIERRCMEMORY_ID": "mem-rc",
    }
    assert bridge_cli_injected_names(suffixed) == {
        "AGENTCORE_GATEWAY_URL": "https://rc/mcp", "AGENTCORE_MEMORY_ID": "mem-rc",
    }
    explicit = {**suffixed, "AGENTCORE_GATEWAY_URL": "https://x/mcp", "AGENTCORE_MEMORY_ID": "m"}
    assert bridge_cli_injected_names(explicit) == {}
    assert bridge_cli_injected_names({"MCP_GATEWAY_URL": "https://legacy/mcp"}) == {
        "AGENTCORE_GATEWAY_URL": "https://legacy/mcp",
    }
    assert bridge_cli_injected_names({}) == {}


def test_memory_gateway_targets_and_policy_engine_share_one_project(
    tmp_path: Path,
) -> None:
    root, project = _render(tmp_path, include_policies=False)

    memory = project["memories"][0]
    assert memory["name"] == renderer.MEMORY_NAME
    assert [s["type"] for s in memory["strategies"]] == ["USER_PREFERENCE", "SEMANTIC", "SUMMARIZATION", "EPISODIC"]
    assert memory["eventExpiryDuration"] == 30
    assert memory["strategies"][-1]["reflectionNamespaceTemplates"] == ["/pellier/episodes/{actorId}/"]

    gateway = project["agentCoreGateways"][0]
    assert gateway["name"] == renderer.GATEWAY_NAME
    assert gateway["protocolType"] == "MCP"
    assert gateway["policyEngineConfiguration"] == {
        "policyEngineName": renderer.POLICY_ENGINE_NAME,
        "mode": "ENFORCE",
    }
    assert [t["name"] for t in gateway["targets"]] == ["pellier-store-tools"]
    assert {target["targetType"] for target in gateway["targets"]} == {
        "lambdaFunctionArn"
    }
    assert {
        target["lambdaFunctionArn"]["lambdaArn"] for target in gateway["targets"]
    } == set(_lambda_arns().values())

    schemas = sorted((root / "tool-schemas").glob("*.json"))
    assert [path.name for path in schemas] == ["store.json"]
    # 8 at the start, not the canonical 9: `get_tickets` is deferred until Lab 3a
    # publishes it. Derived rather than written as a literal, because the literal is
    # what went stale.
    assert sum(len(json.loads(path.read_text())) for path in schemas) == len(
        schemas_module.workshop_published_tools()
    )

    engine = project["policyEngines"][0]
    assert engine["name"] == renderer.POLICY_ENGINE_NAME
    assert engine["policies"] == []


def test_second_phase_attaches_the_baseline_cedar_set(tmp_path: Path) -> None:
    """The rendered project carries the baseline policies, whatever they are.

    This test used to enumerate all eighteen policy names, which duplicated
    ``baseline_policies`` in a second place and is how the set drifted to a shape nobody
    had validated: an eighteen-policy model with username/customer ownership baked into
    the baseline, so a fresh stack shipped the Lab 4 answer. The policy-by-policy
    contract now lives in ``test_fresh_policy_set.py``. What belongs HERE is the
    project-level property: every policy the renderer produces reaches the project's
    single engine, enforced and validated, with no wildcard among them.
    """
    _, project = _render(tmp_path, include_policies=True)
    policies = project["policyEngines"][0]["policies"]
    baseline = renderer.baseline_policies(gateway_arn=TEST_GATEWAY_ARN)
    output = renderer.output_guardrail_policy(TEST_GATEWAY_ARN)
    credit_limit = renderer.credit_limit_policy(
        gateway_arn=TEST_GATEWAY_ARN, source=REPO_ROOT / renderer.CREDIT_LIMIT_SOURCE)
    expected = baseline + [output, credit_limit]

    assert [policy["name"] for policy in policies] == [p["name"] for p in expected]
    assert all(policy["enforcementMode"] == "ACTIVE" for policy in policies)
    assert all(
        policy["validationMode"] == "FAIL_ON_ANY_FINDINGS" for policy in policies[:-2]
    )
    assert policies[-2] == output
    assert output["statement"].startswith("suppressOutput")
    assert output["validationMode"] == "IGNORE_ALL_FINDINGS"
    # Lab 4's starter is deployed at provisioning, so the live DENY comes
    # before any edit. It forbids every credit, which semantic validation
    # reports as overly restrictive, so only schema checks run on it.
    assert policies[-1] == credit_limit
    assert credit_limit["name"] == "workshop_credit_limit"
    assert credit_limit["validationMode"] == "IGNORE_ALL_FINDINGS"
    assert "unless {\n  false\n};" in credit_limit["statement"]
    assert "${PELLIER_GATEWAY_ARN}" not in credit_limit["statement"]
    statements = "\n".join(policy["statement"] for policy in policies)
    assert renderer.GIVE_STORE_CREDIT_ACTION in statements
    assert renderer.STORE_TARGET == "pellier-store-tools"
    # Tool-specific policies must pin the deployed Gateway by ARN; the service
    # rejects `resource is AgentCore::Gateway` for a constrained action.
    assert f'resource == AgentCore::Gateway::"{TEST_GATEWAY_ARN}"' in statements
    assert "resource is AgentCore::Gateway" not in statements
    # A wildcard permit authorizes any action published later, including one added after
    # this project was reviewed. Default-deny is the whole reason the allow-list is
    # written out action by action.
    assert "permit (principal, action, resource" not in statements
    assert "permit (\n  principal,\n  action,\n" not in statements


def test_the_published_schema_and_the_permits_agree(tmp_path: Path) -> None:
    """`get_tickets` is deferred, so it is neither published nor permitted at the start.

    No permit names a deferred tool, so publishing it later is denied by default until
    its own owner-only permit lands in the same deployment. `give_store_credit` is
    published, and only its staff-scope permit names it.
    """
    _, project = _render(tmp_path, include_policies=True)
    policies = project["policyEngines"][0]["policies"]

    permits = [
        policy["statement"]
        for policy in policies
        if policy["statement"].lstrip().startswith("permit")
    ]
    assert permits, "the baseline emitted no permit at all"
    for statement in permits:
        assert f"{renderer.STORE_TARGET}___get_tickets" not in statement, (
            "a permit reaches get_tickets before Task 3A publishes it"
        )
    credit = [s for s in permits if renderer.GIVE_STORE_CREDIT_ACTION in s]
    assert len(credit) == 1
    assert 'principal.getTag("custom:staff_scope") == "returns"' in credit[0]

    schemas = sorted(Path(tmp_path).rglob("tool-schemas/*.json"))
    published = {
        tool["name"]
        for path in schemas
        for tool in json.loads(path.read_text())
    }
    assert "get_tickets" not in published
    assert "give_store_credit" in published
    assert len(published) == 8


def test_deployed_state_reads_mcp_gateway_shape() -> None:
    provisioner = _load_provisioner()
    state = {
        "targets": {
            "default": {
                "resources": {
                    "mcp": {
                        "gateways": {
                            renderer.GATEWAY_NAME: {
                                "gatewayId": "gateway-1",
                                "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:123:gateway/gateway-1",
                                "gatewayUrl": "https://gateway.example/mcp",
                            }
                        }
                    }
                }
            }
        }
    }

    gateway = provisioner._require_gateway_state(state, renderer.GATEWAY_NAME)
    assert gateway["gatewayId"] == "gateway-1"


def test_deployed_state_rejects_obsolete_flat_gateway_shape() -> None:
    provisioner = _load_provisioner()
    state = {
        "targets": {
            "default": {
                "resources": {
                    "gateways": {renderer.GATEWAY_NAME: {"gatewayId": "wrong"}}
                }
            }
        }
    }

    with pytest.raises(RuntimeError, match=r"mcp\.gateways\.pellier-gateway"):
        provisioner._require_gateway_state(state, renderer.GATEWAY_NAME)


def test_cloudtrail_audit_receipt_is_recent_correlated_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisioner = _load_provisioner()
    deployment_started_at = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    requested: dict[str, Any] = {}

    class _Paginator:
        def paginate(self, **kwargs: Any) -> list[dict[str, list[dict[str, Any]]]]:
            requested.update(kwargs)
            return [
                {
                    "Events": [
                        {
                            "EventSource": "bedrock-agentcore.amazonaws.com",
                            "EventName": "CreateAgentRuntime",
                            "EventTime": deployment_started_at,
                            "CloudTrailEvent": json.dumps(
                                {
                                    "requestParameters": {
                                        "agentRuntimeName": renderer.RUNTIME_NAME
                                    },
                                    "responseElements": {
                                        "agentRuntimeArn": (
                                            "arn:aws:bedrock-agentcore:us-east-1:"
                                            "123456789012:runtime/pellier-runtime"
                                        )
                                    },
                                    "userIdentity": {
                                        "arn": "must-not-appear-in-receipt"
                                    },
                                }
                            ),
                        }
                    ]
                }
            ]

    class _CloudTrail:
        def get_paginator(self, name: str) -> _Paginator:
            assert name == "lookup_events"
            return _Paginator()

    monkeypatch.setattr(
        provisioner.boto3,
        "client",
        lambda service, **_: _CloudTrail() if service == "cloudtrail" else None,
    )

    proof = provisioner._verify_agentcore_control_plane_audit(
        region="us-east-1",
        deployment_started_at=deployment_started_at,
        runtime_arn=(
            "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
            "runtime/pellier-runtime"
        ),
        gateway_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/gateway",
        memory_id="memory-123",
        policy_engine_id="policy-123",
    )

    assert requested["LookupAttributes"] == [
        {
            "AttributeKey": "EventSource",
            "AttributeValue": "bedrock-agentcore.amazonaws.com",
        }
    ]
    assert proof == {
        "source": "CloudTrail Event History",
        "event_source": "bedrock-agentcore.amazonaws.com",
        "event_name": "CreateAgentRuntime",
        "event_time": "2026-08-13T12:00:00Z",
        "resource_type": "runtime",
    }
    assert "userIdentity" not in proof
    assert "must-not-appear-in-receipt" not in json.dumps(proof)


def test_transaction_search_setup_is_scoped_and_requires_active_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisioner = _load_provisioner()

    class _Logs:
        policy_name = ""
        policy_document = ""

        def describe_resource_policies(self, **_: Any) -> dict[str, Any]:
            return {"resourcePolicies": []}

        def put_resource_policy(
            self, *, policyName: str, policyDocument: str
        ) -> None:
            self.policy_name = policyName
            self.policy_document = policyDocument

    class _XRay:
        updated_to = ""
        responses = iter(
            (
                {"Destination": "XRay", "Status": "ACTIVE"},
                {"Destination": "CloudWatchLogs", "Status": "ACTIVE"},
            )
        )

        def get_trace_segment_destination(self) -> dict[str, str]:
            return next(self.responses)

        def get_indexing_rules(self) -> dict[str, Any]:
            return {"IndexingRules": [{"Name": "Default", "Rule": {
                "Probabilistic": {"DesiredSamplingPercentage": 100},
            }}]}

        def update_trace_segment_destination(self, *, Destination: str) -> None:
            self.updated_to = Destination

    logs = _Logs()
    xray = _XRay()

    def _client(service: str, **_: Any) -> Any:
        return {"logs": logs, "xray": xray}[service]

    monkeypatch.setattr(provisioner.boto3, "client", _client)
    monkeypatch.setattr(provisioner.time, "sleep", lambda _: None)

    proof = provisioner._configure_transaction_search(
        region="us-east-1",
        account_id="123456789012",
        partition="aws",
    )

    assert xray.updated_to == "CloudWatchLogs"
    assert proof == {
        "destination": "CloudWatchLogs",
        "status": "ACTIVE",
        "resource_policy": "TransactionSearchXRayAccess",
        "resource_policy_document": logs.policy_document,
        "span_log_group": "aws/spans",
        "indexing_rule": {"name": "Default", "desired_sampling_percentage": 100},
        "cleanup": {
            "destination_changed": True,
            "previous_destination": "XRay",
            "resource_policy_created": True,
            "previous_resource_policy_document": None,
            "previous_indexing_rule": {"name": "Default", "desired_sampling_percentage": 100},
            "indexing_rule_changed": False,
            "indexing_rule_update_started": False,
        },
    }
    assert logs.policy_name == "TransactionSearchXRayAccess"
    policy = json.loads(logs.policy_document)
    statement = policy["Statement"][0]
    assert statement["Principal"] == {"Service": "xray.amazonaws.com"}
    assert statement["Action"] == "logs:PutLogEvents"
    assert statement["Resource"] == [
        "arn:aws:logs:us-east-1:123456789012:log-group:aws/spans:*",
        (
            "arn:aws:logs:us-east-1:123456789012:"
            "log-group:/aws/application-signals/data:*"
        ),
    ]
    assert statement["Condition"] == {
        "StringEquals": {"aws:SourceAccount": "123456789012"},
        "ArnLike": {
            "aws:SourceArn": "arn:aws:xray:us-east-1:123456789012:*"
        },
    }


def test_runtime_log_group_is_customer_encrypted_and_retention_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisioner = _load_provisioner()
    runtime_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
        "runtime/pellier_orchestrator-abc123"
    )
    kms_key_arn = (
        "arn:aws:kms:us-east-1:123456789012:"
        "key/12345678-1234-1234-1234-1234567890ab"
    )

    class _Paginator:
        def __init__(self, logs: Any) -> None:
            self.logs = logs

        def paginate(self, **_: Any) -> list[dict[str, list[dict[str, Any]]]]:
            return [{"logGroups": [self.logs.group]}]

    class _Logs:
        class exceptions:
            class ResourceAlreadyExistsException(Exception):
                pass

        def __init__(self) -> None:
            self.group = {
                "logGroupName": provisioner._runtime_log_group_name(runtime_arn),
                "kmsKeyId": "arn:aws:kms:us-east-1:123456789012:key/old",
                "retentionInDays": 7,
            }
            self.associated_kms_key = ""
            self.retention_days = 0

        def create_log_group(self, **_: Any) -> None:
            raise self.exceptions.ResourceAlreadyExistsException()

        def get_paginator(self, name: str) -> _Paginator:
            assert name == "describe_log_groups"
            return _Paginator(self)

        def associate_kms_key(self, *, logGroupName: str, kmsKeyId: str) -> None:
            assert logGroupName == self.group["logGroupName"]
            self.associated_kms_key = kmsKeyId
            self.group["kmsKeyId"] = kmsKeyId

        def put_retention_policy(
            self, *, logGroupName: str, retentionInDays: int
        ) -> None:
            assert logGroupName == self.group["logGroupName"]
            self.retention_days = retentionInDays
            self.group["retentionInDays"] = retentionInDays

    logs = _Logs()
    def initialize_delivery(client: Any, arn: str, **_: Any) -> dict[str, bool]:
        assert client is logs
        assert arn == runtime_arn
        assert logs.group["kmsKeyId"] == kms_key_arn
        assert logs.group["retentionInDays"] == 30
        return {"initialized_after_protection": True}

    monkeypatch.setattr(provisioner, "ensure_runtime_log_delivery", initialize_delivery)
    monkeypatch.setattr(
        provisioner.boto3,
        "client",
        lambda service, **_: logs if service == "logs" else None,
    )

    proof = provisioner._ensure_runtime_log_group(
        region="us-east-1",
        runtime_arn=runtime_arn,
        kms_key_arn=kms_key_arn,
        retention_days=30,
    )

    assert proof.pop("delivery") == {"initialized_after_protection": True}
    assert proof == {
        "name": "/aws/bedrock-agentcore/runtimes/pellier_orchestrator-abc123-DEFAULT",
        "kms_key_arn": kms_key_arn,
        "retention_days": 30,
        "requested": {"kms_key_arn": kms_key_arn, "retention_days": 30},
        "observed": {"kms_key_arn": kms_key_arn, "retention_days": 30},
        "cleanup": {
            "created_by_workshop": False,
            "creation_pending": False,
            "previous_kms_key_arn": (
                "arn:aws:kms:us-east-1:123456789012:key/old"
            ),
            "previous_retention_days": 7,
        },
    }
    assert logs.associated_kms_key == kms_key_arn
    assert logs.retention_days == 30


def test_runtime_log_group_rejects_alias_and_unbounded_retention() -> None:
    provisioner = _load_provisioner()

    with pytest.raises(RuntimeError, match="customer-managed KMS key ARN"):
        provisioner._ensure_runtime_log_group(
            region="us-east-1",
            runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123:runtime/test",
            kms_key_arn="arn:aws:kms:us-east-1:123456789012:alias/pellier",
            retention_days=30,
        )
    with pytest.raises(RuntimeError, match="must be one of"):
        provisioner._runtime_log_retention_days("0")


def test_trace_log_groups_are_created_encrypted_and_retention_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisioner = _load_provisioner()
    kms_key_arn = (
        "arn:aws:kms:us-east-1:123456789012:"
        "key/12345678-1234-1234-1234-1234567890ab"
    )

    class _Paginator:
        def __init__(self, logs: Any) -> None:
            self.logs = logs

        def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
            name = kwargs["logGroupNamePrefix"]
            group = self.logs.groups.get(name)
            return [{"logGroups": [group] if group else []}]

    class _Logs:
        class exceptions:
            class ResourceAlreadyExistsException(Exception):
                pass

        def __init__(self) -> None:
            self.groups: dict[str, dict[str, Any]] = {}

        def create_log_group(
            self, *, logGroupName: str, kmsKeyId: str
        ) -> None:
            assert logGroupName != "aws/spans", "AWS reserves this name"
            self.groups[logGroupName] = {
                "logGroupName": logGroupName,
                "kmsKeyId": kmsKeyId,
            }

        def get_paginator(self, name: str) -> _Paginator:
            assert name == "describe_log_groups"
            return _Paginator(self)

        def associate_kms_key(
            self, *, logGroupName: str, kmsKeyId: str
        ) -> None:
            self.groups[logGroupName]["kmsKeyId"] = kmsKeyId

        def put_retention_policy(
            self, *, logGroupName: str, retentionInDays: int
        ) -> None:
            self.groups[logGroupName]["retentionInDays"] = retentionInDays

    logs = _Logs()
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: logs)

    def activate() -> None:
        assert logs.groups["/aws/application-signals/data"]["retentionInDays"] == 30
        logs.groups["aws/spans"] = {"logGroupName": "aws/spans"}

    proof = provisioner._ensure_trace_log_groups(
        region="us-east-1",
        kms_key_arn=kms_key_arn,
        retention_days=30,
        activate_transaction_search=activate,
    )

    assert [group["name"] for group in proof["groups"]] == [
        "aws/spans",
        "/aws/application-signals/data",
    ]
    assert all(group["kms_key_arn"] == kms_key_arn for group in proof["groups"])
    assert all(group["retention_days"] == 30 for group in proof["groups"])
    assert all(
        group["cleanup"]
        == {
            "created_by_workshop": group["name"] != "aws/spans",
            "creation_pending": False,
            "previous_kms_key_arn": None,
            "previous_retention_days": None,
        }
        for group in proof["groups"]
    )
    assert {
        name: (group["kmsKeyId"], group["retentionInDays"])
        for name, group in logs.groups.items()
    } == {
        "aws/spans": (kms_key_arn, 30),
        "/aws/application-signals/data": (kms_key_arn, 30),
    }


def test_log_group_create_race_checkpoints_existing_ownership_before_repair() -> None:
    provisioner = _load_provisioner()
    kms_key_arn = (
        "arn:aws:kms:us-east-1:123456789012:"
        "key/12345678-1234-1234-1234-1234567890ab"
    )
    log_group_name = "/aws/application-signals/data"
    events: list[str] = []
    checkpoints: list[dict[str, Any]] = []

    class _Paginator:
        def __init__(self, logs: Any) -> None:
            self.logs = logs

        def paginate(self, **_: Any) -> list[dict[str, Any]]:
            return [{"logGroups": [self.logs.group] if self.logs.group else []}]

    class _Logs:
        class exceptions:
            class ResourceAlreadyExistsException(Exception):
                pass

        def __init__(self) -> None:
            self.group: dict[str, Any] | None = None

        def get_paginator(self, _: str) -> _Paginator:
            return _Paginator(self)

        def create_log_group(self, **_: Any) -> None:
            events.append("create")
            self.group = {
                "logGroupName": log_group_name,
                "kmsKeyId": "arn:aws:kms:us-east-1:123456789012:key/external",
                "retentionInDays": 7,
            }
            raise self.exceptions.ResourceAlreadyExistsException()

        def associate_kms_key(self, **_: Any) -> None:
            events.append("associate")
            assert self.group is not None
            self.group["kmsKeyId"] = kms_key_arn

        def put_retention_policy(self, **_: Any) -> None:
            events.append("retention")
            assert self.group is not None
            self.group["retentionInDays"] = 30

    def checkpoint(group: dict[str, Any]) -> None:
        checkpoints.append(json.loads(json.dumps(group)))
        if group["cleanup"]["creation_pending"]:
            ownership = "pending"
        elif group["cleanup"]["created_by_workshop"]:
            ownership = "created"
        else:
            ownership = "preexisting"
        events.append(f"checkpoint:{ownership}")

    proof = provisioner._ensure_protected_log_group(
        logs=_Logs(),
        log_group_name=log_group_name,
        kms_key_arn=kms_key_arn,
        retention_days=30,
        on_cleanup_state=checkpoint,
    )

    assert events == [
        "checkpoint:pending",
        "create",
        "checkpoint:preexisting",
        "associate",
        "retention",
    ]
    assert checkpoints[-1]["cleanup"] == {
        "created_by_workshop": False,
        "creation_pending": False,
        "previous_kms_key_arn": (
            "arn:aws:kms:us-east-1:123456789012:key/external"
        ),
        "previous_retention_days": 7,
    }
    assert proof["cleanup"] == checkpoints[-1]["cleanup"]


def test_trace_log_group_failure_keeps_partial_cleanup_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisioner = _load_provisioner()
    kms_key_arn = (
        "arn:aws:kms:us-east-1:123456789012:"
        "key/12345678-1234-1234-1234-1234567890ab"
    )
    checkpoints: list[dict[str, Any]] = []

    class _Paginator:
        def __init__(self, logs: Any) -> None:
            self.logs = logs

        def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
            group = self.logs.groups.get(kwargs["logGroupNamePrefix"])
            return [{"logGroups": [group] if group else []}]

    class _Logs:
        class exceptions:
            class ResourceAlreadyExistsException(Exception):
                pass

        def __init__(self) -> None:
            self.groups: dict[str, dict[str, Any]] = {}

        def get_paginator(self, _: str) -> _Paginator:
            return _Paginator(self)

        def create_log_group(
            self,
            *,
            logGroupName: str,
            kmsKeyId: str,
        ) -> None:
            if logGroupName == "/aws/application-signals/data":
                raise RuntimeError("injected create failure")
            self.groups[logGroupName] = {
                "logGroupName": logGroupName,
                "kmsKeyId": kmsKeyId,
            }

        def associate_kms_key(self, **_: Any) -> None:
            raise AssertionError("new groups already use the required key")

        def put_retention_policy(
            self,
            *,
            logGroupName: str,
            retentionInDays: int,
        ) -> None:
            self.groups[logGroupName]["retentionInDays"] = retentionInDays

    logs = _Logs()
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: logs)

    activated = []
    with pytest.raises(RuntimeError, match="injected create failure"):
        provisioner._ensure_trace_log_groups(
            region="us-east-1",
            kms_key_arn=kms_key_arn,
            retention_days=30,
            activate_transaction_search=lambda: activated.append(True),
            on_cleanup_state=lambda group: checkpoints.append(
                json.loads(json.dumps(group))
            ),
        )

    assert not activated, "ordinary destination protection must precede activation"
    assert [group["name"] for group in checkpoints] == ["/aws/application-signals/data"]
    assert checkpoints[0]["cleanup"] == {
        "created_by_workshop": False,
        "creation_pending": True,
        "previous_kms_key_arn": None,
        "previous_retention_days": None,
    }
    assert logs.groups == {}



def test_transaction_search_checkpoints_prior_state_before_policy_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisioner = _load_provisioner()
    events: list[str] = []
    checkpoints: list[dict[str, Any]] = []

    class _Logs:
        def describe_resource_policies(self, **_: Any) -> dict[str, Any]:
            return {"resourcePolicies": []}

        def put_resource_policy(self, **_: Any) -> None:
            events.append("put-policy")
            raise RuntimeError("injected policy failure")

    class _XRay:
        def get_trace_segment_destination(self) -> dict[str, str]:
            return {"Destination": "XRay", "Status": "ACTIVE"}

        def get_indexing_rules(self) -> dict[str, Any]:
            return {"IndexingRules": [{"Name": "Default", "Rule": {
                "Probabilistic": {"DesiredSamplingPercentage": 100},
            }}]}

    logs = _Logs()
    xray = _XRay()
    monkeypatch.setattr(
        provisioner.boto3,
        "client",
        lambda service, **_: logs if service == "logs" else xray,
    )

    def checkpoint(receipt: dict[str, Any]) -> None:
        events.append("checkpoint")
        checkpoints.append(json.loads(json.dumps(receipt)))

    with pytest.raises(RuntimeError, match="injected policy failure"):
        provisioner._configure_transaction_search(
            region="us-east-1",
            account_id="123456789012",
            partition="aws",
            on_cleanup_state=checkpoint,
        )

    assert events == ["checkpoint", "put-policy"]
    policy_document = checkpoints[0].pop("resource_policy_document")
    assert json.loads(policy_document)["Statement"][0]["Sid"] == (
        "TransactionSearchXRayAccess"
    )
    assert checkpoints == [
        {
            "destination": "CloudWatchLogs",
            "status": "CONFIGURING",
            "resource_policy": "TransactionSearchXRayAccess",
            "span_log_group": "aws/spans",
            "indexing_rule": {"name": "Default", "desired_sampling_percentage": 100},
            "cleanup": {
                "destination_changed": True,
                "previous_destination": "XRay",
                "resource_policy_created": True,
                "previous_resource_policy_document": None,
                "previous_indexing_rule": {"name": "Default", "desired_sampling_percentage": 100},
                "indexing_rule_changed": False,
                "indexing_rule_update_started": False,
            },
        }
    ]


def _unified_trace_records(
    *, trace_id: str, session_id: str, runtime_arn: str
) -> list[dict[str, Any]]:
    def resource() -> dict[str, dict[str, str]]:
        return {"attributes": {"cloud.resource_id": runtime_arn}}

    return [
        {
            "@message": {
                "traceId": trace_id,
                "name": "invoke_agent pellier_orchestrator",
                "startTimeUnixNano": "1000000000",
                "endTimeUnixNano": "1900000000",
                "attributes": {
                    "session.id": session_id,
                    "gen_ai.input.messages": {"stringValue": "find linen"},
                    "gen_ai.output.messages": {"stringValue": "linen dress"},
                },
                "resource": resource(),
            }
        },
        {
            "@message": json.dumps(
                {
                    "traceId": trace_id,
                    "name": "chat",
                    "durationNanos": "320000000",
                    "attributes": {
                        "gen_ai.request.model": "global.anthropic.claude-sonnet-5"
                    },
                    "resource": resource(),
                }
            )
        },
        {
            "@message": {
                "traceId": trace_id,
                "name": "execute_tool search_products",
                "durationMs": 45,
                "attributes": {
                    "gen_ai.tool.name": "search_products",
                    "gen_ai.tool.call.arguments": {"query": "linen"},
                    "gen_ai.tool.call.result": {"product_ids": ["P-101"]},
                },
                "resource": resource(),
            }
        },
        {
            "@message": {
                "traceId": "another-trace",
                "name": "execute_tool ignored",
                "attributes": {"gen_ai.tool.name": "ignored"},
                "resource": resource(),
            }
        },
    ]


def test_unified_trace_summary_requires_correlated_agent_model_and_tool_spans() -> None:
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = "runtime-proof-000000000000000000001"
    runtime_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
        "runtime/pellier_orchestrator-abc123"
    )

    proof = provisioner._summarize_trace_records(
        _unified_trace_records(
            trace_id=trace_id,
            session_id=session_id,
            runtime_arn=runtime_arn,
        ),
        trace_id=trace_id,
        session_id=session_id,
        runtime_arn=runtime_arn,
    )

    assert proof["span_count"] == 3
    assert proof["runtime_arn"] == runtime_arn
    assert proof["agent_span"] is True
    assert proof["model_span"] is True
    assert proof["tool_span"] is True
    assert proof["agent_input_observed"] is True
    assert proof["agent_output_observed"] is True
    assert proof["tool_input_output_structured"] is True
    assert proof["tool_input_output_sanitized"] is True
    assert proof["attribute_contract"] == {
        "agent_input": "gen_ai.input.messages",
        "agent_output": "gen_ai.output.messages",
        "tool_input": "gen_ai.tool.call.arguments",
        "tool_output": "gen_ai.tool.call.result",
    }
    assert proof["step_latency_ms"] == {"agent": 900, "model": 320, "tool": 45}
    assert proof["model_ids"] == ["global.anthropic.claude-sonnet-5"]
    assert proof["tool_names"] == ["search_products"]
    assert proof["provenance"] == "agentcore-unified-telemetry"


def test_unified_trace_summary_rejects_spans_from_another_runtime() -> None:
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = "runtime-proof-000000000000000000001"
    runtime_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
        "runtime/pellier_orchestrator-abc123"
    )
    records = _unified_trace_records(
        trace_id=trace_id,
        session_id=session_id,
        runtime_arn=runtime_arn,
    )
    records[2]["@message"]["resource"]["attributes"]["cloud.resource_id"] = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/other"
    )

    with pytest.raises(RuntimeError, match="another Runtime"):
        provisioner._summarize_trace_records(
            records,
            trace_id=trace_id,
            session_id=session_id,
            runtime_arn=runtime_arn,
        )


def test_unified_trace_summary_rejects_secret_bearing_tool_io() -> None:
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = "runtime-proof-000000000000000000001"
    runtime_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
        "runtime/pellier_orchestrator-abc123"
    )
    records = _unified_trace_records(
        trace_id=trace_id,
        session_id=session_id,
        runtime_arn=runtime_arn,
    )
    records[2]["@message"]["attributes"]["gen_ai.tool.call.arguments"] = {
        "authorization": "Bearer token"
    }

    with pytest.raises(RuntimeError, match="secret or credential marker"):
        provisioner._summarize_trace_records(
            records,
            trace_id=trace_id,
            session_id=session_id,
            runtime_arn=runtime_arn,
        )


def test_unified_trace_summary_rejects_unstructured_tool_io() -> None:
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = "runtime-proof-000000000000000000001"
    runtime_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
        "runtime/pellier_orchestrator-abc123"
    )
    records = _unified_trace_records(
        trace_id=trace_id,
        session_id=session_id,
        runtime_arn=runtime_arn,
    )
    records[2]["@message"]["attributes"]["gen_ai.tool.call.result"] = (
        "free-form result"
    )

    with pytest.raises(RuntimeError, match="structured JSON"):
        provisioner._summarize_trace_records(
            records,
            trace_id=trace_id,
            session_id=session_id,
            runtime_arn=runtime_arn,
        )


def test_trace_poll_uses_pinned_cli_and_downloads_the_matching_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = f"runtime-proof-{uuid.uuid4().hex}"
    runtime_arn = (
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
        "runtime/pellier_orchestrator-abc123"
    )
    calls: list[tuple[str, ...]] = []
    outputs: list[Path] = []
    legacy_path = Path(f"/tmp/pellier-agentcore-trace-{session_id}.json")
    legacy_path.symlink_to(tmp_path / "unrelated-target.json")
    legacy_path.write_text("unrelated local file", encoding="utf-8")

    def _agentcore(
        _root: Path, *args: str, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        del env
        calls.append(args)
        if args[:2] == ("traces", "list"):
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "success": True,
                        "traces": [
                            {
                                "traceId": trace_id,
                                "sessionId": session_id,
                                "spanCount": 3,
                            }
                        ],
                    }
                ),
                stderr="",
            )
        output = Path(args[args.index("--output") + 1])
        outputs.append(output)
        assert output.parent.stat().st_mode & 0o777 == 0o700
        assert output.parent.stat().st_uid == os.geteuid()
        assert not output.exists()
        output.write_text(
            json.dumps(
                _unified_trace_records(
                    trace_id=trace_id,
                    session_id=session_id,
                    runtime_arn=runtime_arn,
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args, 0, stdout='{"success":true}', stderr=""
        )

    monkeypatch.setattr(provisioner, "_agentcore", _agentcore)
    # The fixture trace carries clear-text content, which is the unredacted
    # contract; a redacting Runtime would keep polling for a trace without it.
    monkeypatch.setenv("OTEL_REDACT_MODEL_CONTENT", "0")

    try:
        proof = provisioner._wait_for_unified_trace(
            root=tmp_path,
            session_id=session_id,
            runtime_arn=runtime_arn,
            env={},
        )
        assert legacy_path.is_symlink()
        assert legacy_path.read_text() == "unrelated local file"
    finally:
        legacy_path.unlink(missing_ok=True)

    assert proof["trace_id"] == trace_id
    assert proof["listed_span_count"] == 3
    assert proof["runtime_log_group"].endswith(
        "/pellier_orchestrator-abc123-DEFAULT"
    )
    assert len(outputs) == 1
    assert not outputs[0].exists()
    assert not outputs[0].parent.exists()
    assert calls == [
        (
            "traces",
            "list",
            "--runtime",
            "pellier_orchestrator",
            "--since",
            "30m",
            "--limit",
            "20",
            "--json",
        ),
        (
            "traces",
            "get",
            trace_id,
            "--runtime",
            "pellier_orchestrator",
            "--since",
            "30m",
            "--output",
            str(outputs[0]),
            "--json",
        ),
    ]


def test_failed_trace_download_removes_its_private_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    provisioner = _load_provisioner()
    session_id = f"runtime-proof-{uuid.uuid4().hex}"
    outputs: list[Path] = []
    clock = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(provisioner, "TRACE_DELIVERY_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(provisioner.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(provisioner.time, "sleep", lambda _seconds: None)

    def command(_root: Path, *args: str, **_kwargs):
        if args[:2] == ("traces", "list"):
            return subprocess.CompletedProcess(
                args, 0, stdout=json.dumps({
                    "success": True,
                    "traces": [{"traceId": "trace-id", "sessionId": session_id}],
                }),
            )
        output = Path(args[args.index("--output") + 1])
        assert output.parent.stat().st_mode & 0o777 == 0o700
        output.write_text("partial trace", encoding="utf-8")
        outputs.append(output)
        raise RuntimeError("download failed")

    monkeypatch.setattr(provisioner, "_agentcore", command)
    with pytest.raises(RuntimeError, match="download failed"):
        provisioner._wait_for_unified_trace(
            root=tmp_path, session_id=session_id,
            runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
            env={},
        )
    assert len(outputs) == 1
    assert not outputs[0].parent.exists()


def test_deploy_sequence_validates_both_cli_phases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provisioner = _load_provisioner()
    root = tmp_path / "project"
    calls: list[tuple[str, ...]] = []
    render_phases: list[bool] = []
    rendered_runtime_arns = []
    state = {
        "targets": {
            "default": {
                "resources": {
                    "runtimes": {
                        renderer.RUNTIME_NAME: {"runtimeArn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier_orchestrator-abc123"},
                    },
                    "mcp": {
                        "gateways": {
                            renderer.GATEWAY_NAME: {
                                "gatewayId": "gateway-1",
                                "gatewayArn": "arn:gateway",
                            }
                        }
                    },
                    "policyEngines": {
                        renderer.POLICY_ENGINE_NAME: {
                            "policyEngineId": "engine-1",
                            "policyEngineArn": "arn:engine",
                        }
                    },
                }
            }
        }
    }

    monkeypatch.setattr(
        provisioner, "_scaffold_cli_project", lambda **_: root
    )
    config_path = root / "agentcore" / "agentcore.json"
    deployed_policies: list[list[str]] = []

    def render(**kwargs):
        render_phases.append(kwargs["include_policies"])
        rendered_runtime_arns.append(kwargs.get("runtime_arns"))
        names = ["baseline_permit_workshop_tools", renderer.CREDIT_LIMIT_POLICY]
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"policyEngines": [{
            "name": "engine",
            "policies": [{"name": n} for n in names] if kwargs["include_policies"] else [],
        }]}))

    def agentcore(_root, *args, **_):
        calls.append(args)
        if args[0] == "deploy":
            config = json.loads(config_path.read_text())
            deployed_policies.append([p["name"] for p in config["policyEngines"][0]["policies"]])

    monkeypatch.setattr(provisioner, "render_project", render)
    monkeypatch.setattr(provisioner, "_agentcore", agentcore)
    monkeypatch.setattr(provisioner, "_read_deployed_state", lambda _root: state)

    returned_root, returned_state = provisioner._deploy_cli_project(
        repo=tmp_path,
        account_id="123456789012",
        region="us-east-1",
        cognito_pool="pool",
        cognito_client="client",
        lambda_arns=_lambda_arns(),
        model_id="model",
        workshop_id="workshop",
        env={},
    )

    assert returned_root == root
    assert returned_state is state
    assert render_phases == [False, True]
    assert rendered_runtime_arns[0] is None
    assert rendered_runtime_arns[1] == {
        name: resource["runtimeArn"]
        for name, resource in state["targets"]["default"]["resources"]["runtimes"].items()
    }
    assert calls == [
        ("validate",),
        ("deploy", "--yes", "--json"),
        ("validate",),
        ("deploy", "--yes", "--json"),
        ("validate",),
        ("deploy", "--yes", "--json"),
    ]
    # The baseline lands first; Lab 4's starter forbid follows in a deploy of its own.
    assert deployed_policies == [
        [],
        ["baseline_permit_workshop_tools"],
        ["baseline_permit_workshop_tools", renderer.CREDIT_LIMIT_POLICY],
    ]


def test_pyproject_contains_only_runtime_import_roots() -> None:
    deps = PYPROJECT.read_text()
    for package in (
        "strands-agents",
        "aws-opentelemetry-distro",
        "bedrock-agentcore",
        "mcp",
    ):
        assert package in deps
    for app_only_package in ("pydantic-settings", "psycopg", "pgvector", "fastapi"):
        assert app_only_package not in deps


def test_managed_runtime_imports_without_database_configuration(
    tmp_path: Path,
) -> None:
    root, _ = _render(tmp_path, include_policies=False)
    runtime_dir = root / "runtime-src"
    env = os.environ.copy()
    for key in (
        "DB_HOST",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DATABASE_URL",
    ):
        env.pop(key, None)
    env.update(
        {
            "PELLIER_DISABLE_DOTENV": "1",
            "AGENTCORE_GATEWAY_URL": "https://gateway.example.test/mcp",
            "AGENT_MODEL_ID": "test-model",
            "PYTHONPATH": str(runtime_dir),
        }
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from services.agentcore_gateway import "
                "_managed_specialist_spec, create_gateway_dispatcher; "
                "from services.conversation_context import "
                "build_conversation_prompt; "
                "assert create_gateway_dispatcher('jwt') is not None; "
                "assert _managed_specialist_spec('stock')[0] == 'stock'; "
                "assert build_conversation_prompt('hello') == 'hello'"
            ),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_entrypoint_is_fail_closed_byo_app() -> None:
    text = ENTRYPOINT.read_text()
    assert "BedrockAgentCoreApp" in text
    assert "@app.entrypoint" in text
    assert '"error": "authentication_required"' in text
    assert '"error": "managed_gateway_unavailable"' in text
    assert "create_gateway_dispatcher" in text
    assert "from agents.orchestrator import create_orchestrator" not in text
    for field in ('"intent"', '"specialist"', '"gateway_tools"'):
        assert field in text


def test_runtime_smoke_uses_pinned_agentcore_cli() -> None:
    provisioner = PROVISIONER_PATH.read_text()
    assert '"invoke"' in provisioner
    assert '"--runtime"' in provisioner
    assert '"--bearer-token"' in provisioner
    assert '"--session-id"' in provisioner
    assert "urllib.request" not in provisioner


def test_bootstrap_runtime_solution_matches_fail_closed_service() -> None:
    assert RUNTIME_SOLUTION.read_text() == RUNTIME_SERVICE.read_text()


def test_obsolete_flat_templates_and_runtime_provisioner_are_removed() -> None:
    for stale in (
        BACKEND_DIR / ".bedrock_agentcore.yaml",
        BACKEND_DIR / "agentcore.json.template",
        BACKEND_DIR / "aws-targets.json.template",
        BACKEND_DIR / "scripts" / "create_local_memory.py",
        REPO_ROOT / "scripts" / "provision_agentcore_runtime.py",
    ):
        assert not stale.exists()


def _scannable_sources():
    excluded_parts = {
        ".agentcore-project", ".git", ".venv", "__pycache__", "node_modules", "tests", ".local",}
    for path in (*REPO_ROOT.rglob("*.py"), *REPO_ROOT.rglob("*.sh")):
        relative = path.relative_to(REPO_ROOT)
        if excluded_parts.intersection(relative.parts):
            continue
        try:
            yield relative, path.read_text()
        except (UnicodeDecodeError, OSError):
            continue


# Runtime, Memory and their IAM live in a CloudFormation stack owned by the CLI project.
# A direct control-plane update would drift the stack from reality, and the next CLI
# deploy would silently revert it.
FORBIDDEN_CONTROL_PLANE_WRITES = (
    "update_agent_runtime",
    "UpdateAgentRuntime",
    "update-agent-runtime",
    "update_memory(",
    "UpdateMemory",
    "update-memory",
)


def test_cfn_owned_resources_are_never_mutated_directly() -> None:
    """Forbidden everywhere in the repository, with no exception module."""
    for relative, source in _scannable_sources():
        for operation in FORBIDDEN_CONTROL_PLANE_WRITES:
            assert operation not in source, (
                f"{relative} mutates a CloudFormation-owned AgentCore resource with "
                f"{operation}; change Runtime and Memory through the CLI project."
            )


def test_the_cli_project_path_is_still_the_only_creator() -> None:
    """Nothing may create AgentCore resources outside the CLI project."""
    for relative, source in _scannable_sources():
        assert "bedrock-agentcore-control create-" not in source, relative
        assert "bedrock-agentcore-control delete-" not in source, relative


def test_deploy_all_is_only_a_canonical_provisioner_wrapper() -> None:
    source = DEPLOY_SCRIPT.read_text()
    assert "provision_agentcore_end_to_end.py" in source
    assert "deploy_gateway.py" not in source
    assert "deploy_policy.py" not in source
    assert "bedrock-agentcore-control create" not in source


def test_a_deployment_suffix_isolates_every_resource_name() -> None:
    """A release candidate deploys beside a live set without touching it."""
    import subprocess

    script = (
        "import render_agentcore_project as r;"
        "print(r.PROJECT_NAME, r.RUNTIME_NAME, r.MEMORY_NAME, r.GATEWAY_NAME, r.POLICY_ENGINE_NAME)"
    )
    env = {**os.environ, "PELLIER_DEPLOYMENT_SUFFIX": "rc", "PYTHONPATH": str(DEPLOY_DIR)}
    out = subprocess.run(
        [sys.executable, "-c", script], cwd=DEPLOY_DIR, env=env,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert out == [
        "pellierrc", "pellier_rc_orchestrator", "PellierRcMemory",
        "pellier-rc-gateway", "pellier_rc_policy_engine",
    ]
    bad = subprocess.run(
        [sys.executable, "-c", script], cwd=DEPLOY_DIR,
        env={**env, "PELLIER_DEPLOYMENT_SUFFIX": "Not-Valid"},
        capture_output=True, text=True,
    )
    assert bad.returncode != 0 and "PELLIER_DEPLOYMENT_SUFFIX" in bad.stderr
    # The default, which every workshop box uses, is unchanged.
    assert renderer.PROJECT_NAME == "pellier"
    assert renderer.GATEWAY_NAME == "pellier-gateway"


def test_lambda_names_follow_the_suffix_while_target_names_do_not() -> None:
    """Target names are inside the Cedar action ids the workshop teaches."""
    import subprocess

    script = (
        "import provision_agentcore_end_to_end as p;"
        "print(sorted(c['server_name'] for c in p.EXPECTED_TARGETS.values()))"
    )
    env = {**os.environ, "PELLIER_DEPLOYMENT_SUFFIX": "rc", "PYTHONPATH": f"{DEPLOY_DIR}:{DEPLOY_DIR.parent}"}
    out = subprocess.run(
        [sys.executable, "-c", script], cwd=DEPLOY_DIR.parent, env=env,
        capture_output=True, text=True, check=True,
    ).stdout
    assert out.strip() == "['pellier-rc-store-tools-server']"
    schemas = PROVISIONER_PATH.parent / "deploy" / "gateway_tool_schemas.py"
    assert '"target_name": "pellier-store-tools"' in schemas.read_text()


def test_the_provisioner_attaches_identity_and_tracing_before_any_proof() -> None:
    """Claims must exist before a token is minted; tracing before spans are awaited."""
    source = PROVISIONER_PATH.read_text()
    assert source.index("_deploy_claim_trigger(\n") < source.index("access_token, smoke_username = _cognito_access_token(")
    assert source.index("_enable_gateway_observability(\n") < source.index("_discover_live_gateway_tools(\n")
    assert "logType=\"TRACES\"" in source and "deliveryDestinationType=\"XRAY\"" in source
    assert "claim_trigger_attached" in source and "gateway_tracing_enabled" in source


@pytest.mark.parametrize("kind", ["gateway", "memory"])
def test_service_observability_protects_logs_before_delivery_and_reuses_paginated_delivery(
    monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    provisioner = _load_provisioner()
    resource_id = "gw-1" if kind == "gateway" else "memory-1"
    log_group = "/aws/vendedlogs/bedrock-agentcore/" + (
        resource_id if kind == "gateway" else "memory/APPLICATION_LOGS/" + resource_id
    )
    key = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-1234567890ab"

    class _Logs:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.group = {"logGroupName": log_group}
            self.exceptions = types.SimpleNamespace(
                ResourceAlreadyExistsException=type("RAE", (Exception,), {}),
                ConflictException=type("Conflict", (Exception,), {}),
            )

        def create_log_group(self, **kw):
            self.calls.append("create_log_group")
            raise self.exceptions.ResourceAlreadyExistsException()

        def get_paginator(self, operation):
            assert operation == "describe_log_groups"
            return types.SimpleNamespace(paginate=lambda **kw: iter([{"logGroups": [dict(self.group)]}]))

        def associate_kms_key(self, **kw):
            self.group["kmsKeyId"] = kw["kmsKeyId"]

        def put_retention_policy(self, **kw):
            self.group["retentionInDays"] = kw["retentionInDays"]

        def put_delivery_source(self, **kw):
            assert self.group.get("kmsKeyId") == key
            assert self.group.get("retentionInDays") == 30
            self.calls.append(f"source:{kw['logType']}")
            return {"deliverySource": {"name": kw["name"]}}

        def put_delivery_destination(self, **kw):
            self.calls.append(f"destination:{kw['deliveryDestinationType']}")
            return {"deliveryDestination": {"arn": f"arn:dest:{kw['name']}"}}

        def create_delivery(self, **kw):
            self.calls.append("create_delivery")
            raise self.exceptions.ConflictException()

        def describe_deliveries(self, **kw):
            if not kw.get("nextToken"):
                return {"deliveries": [], "nextToken": "page-2"}
            return {"deliveries": [
                {"id": "d-logs", "deliverySourceName": f"{resource_id}-logs-source", "deliveryDestinationArn": f"arn:dest:{resource_id}-logs-destination"},
                {"id": "d-traces", "deliverySourceName": f"{resource_id}-traces-source", "deliveryDestinationArn": f"arn:dest:{resource_id}-traces-destination"},
            ]}

    logs = _Logs()
    monkeypatch.setattr(provisioner.boto3, "client", lambda *a, **k: logs)
    enable = getattr(provisioner, f"_enable_{kind}_observability")
    receipt = enable(
        region="us-east-1", account_id="123456789012",
        kms_key_arn=key, retention_days=30,
        **{f"{kind}_arn": f"arn:aws:bedrock-agentcore:us-east-1:123456789012:{kind}/{resource_id}", f"{kind}_id": resource_id},
    )
    assert receipt["log_group"] == log_group
    assert receipt["logs_delivery_id"] == "d-logs"
    assert receipt["traces_delivery_id"] == "d-traces"
    assert receipt["log_group_protection"]["observed"] == {"kms_key_arn": key, "retention_days": 30}
    assert receipt["log_group_protection"]["cleanup"]["created_by_workshop"] is False
    assert "source:TRACES" in logs.calls and "destination:XRAY" in logs.calls


def _cli_invoke_result(fingerprint: str, text: str = "One linen shirt under 150.") -> Any:
    import subprocess

    body = {"response": text, "rail": "gateway-mcp", "build_fingerprint": fingerprint}
    return subprocess.CompletedProcess(
        args=["npx"], returncode=0, stdout=json.dumps({"success": True, "response": body}), stderr=""
    )


def test_runtime_smoke_waits_for_the_deployed_build_to_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A warm container of the previous version answers first; the smoke keeps going."""
    provisioner = _load_provisioner()
    answers = iter(["old" * 8, "old" * 8, "new" * 8])
    calls: list[tuple[str, ...]] = []

    def _fake_agentcore(_root: Path, *args: str, env: dict[str, str]) -> Any:
        calls.append(args)
        return _cli_invoke_result(next(answers))

    monkeypatch.setattr(provisioner, "_agentcore", _fake_agentcore)
    monkeypatch.setattr(provisioner.time, "sleep", lambda _s: None)
    smoke = provisioner._authenticated_runtime_smoke(
        root=tmp_path, access_token="t", username="marco", env={},
        expected_fingerprint="new" * 8, attempts=5, wait_seconds=0,
    )
    assert smoke["build_fingerprint_match"] is True and smoke["attempts"] == 3
    assert smoke["build_fingerprint"] == "new" * 8 and len(calls) == 3
    assert all(args[0] == "invoke" and "--session-id" in args for args in calls)


def test_runtime_smoke_refuses_when_only_the_previous_build_ever_answers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provisioner = _load_provisioner()
    monkeypatch.setattr(provisioner, "_agentcore", lambda _r, *a, env: _cli_invoke_result("old" * 8))
    monkeypatch.setattr(provisioner.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError, match="still serving the previous version"):
        provisioner._authenticated_runtime_smoke(
            root=tmp_path, access_token="t", username="marco", env={},
            expected_fingerprint="new" * 8, attempts=3, wait_seconds=0,
        )


def test_rendered_build_fingerprint_is_read_from_the_project(tmp_path: Path) -> None:
    provisioner = _load_provisioner()
    assert provisioner._rendered_build_fingerprint(tmp_path) == ""
    config = tmp_path / "agentcore"
    config.mkdir()
    (config / "agentcore.json").write_text(json.dumps({
        "runtimes": [{"name": "r", "environmentVariables": [
            {"name": "OTHER", "value": "x"},
            {"name": provisioner.FINGERPRINT_ENV_VAR, "value": " abc123 "},
        ]}],
    }))
    assert provisioner._rendered_build_fingerprint(tmp_path) == "abc123"


def _strip_content_attributes(records: list) -> list:
    """What a redacting Runtime exports: the same spans without any content attribute."""
    provisioner = _load_provisioner()
    for record in records:
        message = record["@message"]
        encoded = isinstance(message, str)
        span = json.loads(message) if encoded else message
        attrs = span.get("attributes", {})
        for key in provisioner._CONTENT_ATTRIBUTE_KEYS:
            attrs.pop(key, None)
        record["@message"] = json.dumps(span) if encoded else span
    return records


def test_unified_trace_summary_accepts_a_redacted_trace() -> None:
    """With redaction on, Strands emits no content attributes; the structure still proves the turn."""
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = "runtime-proof-000000000000000000001"
    runtime_arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier_orchestrator-abc123"
    records = _strip_content_attributes(
        _unified_trace_records(trace_id=trace_id, session_id=session_id, runtime_arn=runtime_arn)
    )
    proof = provisioner._summarize_trace_records(
        records, trace_id=trace_id, session_id=session_id, runtime_arn=runtime_arn,
        content_redacted=True,
    )
    assert proof["content_redacted"] is True
    assert proof["agent_span"] and proof["model_span"] and proof["tool_span"]
    assert proof["agent_input_observed"] is False and proof["tool_input_output_observed"] is False
    assert proof["tool_input_output_sanitized"] is True
    assert proof["step_latency_observed"] is True


def test_the_readiness_gate_asks_for_content_only_when_the_runtime_keeps_it() -> None:
    """A deployment that redacts model content must not fail for redacting it.

    The gate used to require `unified_trace_agent_input`, `agent_output` and
    `tool_io_structured` unconditionally. With redaction on by default those are
    False, False and None on a completely healthy stack, and a real provision run
    failed on 2026-09-10 for exactly that reason.
    """
    source = (
        pathlib.Path(__file__).resolve().parents[3]
        / "scripts"
        / "provision_agentcore_end_to_end.py"
    ).read_text(encoding="utf-8")
    start = source.index("required_checks = (")
    gate = source[start:source.index("missing = [", start)]

    # Structure is always required; it is what a redacted trace still proves.
    for always in (
        "unified_trace_agent_span",
        "unified_trace_model_span",
        "unified_trace_tool_span",
        "unified_trace_step_latency",
        "unified_trace_tool_io_sanitized",
    ):
        assert always in gate

    redacted, kept = gate.split("else:", 1)
    # The content checks live only on the not-redacted side.
    for content_check in (
        "unified_trace_agent_input",
        "unified_trace_agent_output",
        "unified_trace_tool_io_structured",
    ):
        assert content_check in kept
        assert content_check not in redacted
    assert "unified_trace_content_redacted" in redacted


def test_unified_trace_summary_rejects_clear_text_content_when_redaction_is_on() -> None:
    provisioner = _load_provisioner()
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    session_id = "runtime-proof-000000000000000000001"
    runtime_arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier_orchestrator-abc123"
    records = _unified_trace_records(trace_id=trace_id, session_id=session_id, runtime_arn=runtime_arn)
    with pytest.raises(RuntimeError, match="clear text"):
        provisioner._summarize_trace_records(
            records, trace_id=trace_id, session_id=session_id, runtime_arn=runtime_arn,
            content_redacted=True,
        )


def test_runtime_redaction_flag_mirrors_the_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    provisioner = _load_provisioner()
    monkeypatch.delenv("OTEL_REDACT_MODEL_CONTENT", raising=False)
    assert provisioner._runtime_redacts_content() is True
    for raw in ("0", "false", "No", "off"):
        monkeypatch.setenv("OTEL_REDACT_MODEL_CONTENT", raw)
        assert provisioner._runtime_redacts_content() is False
    monkeypatch.setenv("OTEL_REDACT_MODEL_CONTENT", "1")
    assert provisioner._runtime_redacts_content() is True


def test_the_publication_view_renders_without_aws() -> None:
    """The handoff's AWS-free gate must run; a required ARN it cannot have is a placeholder."""
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "describe_workshop_publication.py")],
        capture_output=True, text=True, env={**os.environ, "PELLIER_DISABLE_DOTENV": "1"},
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "baseline_permit_workshop_tools" in proc.stdout


def _participant_state(identity: Any) -> dict[str, Any]:
    return {
        "targets": {
            "default": {
                "resources": {
                    "runtimes": {
                        identity.runtime_name: {"runtimeArn": "arn:runtime"},
                    },
                    "mcp": {
                        "gateways": {
                            identity.gateway_name: {
                                "gatewayId": "gateway-1",
                                "gatewayArn": "arn:gateway",
                                "gatewayUrl": "https://gateway.example/mcp",
                            }
                        }
                    },
                    "policyEngines": {
                        identity.policy_engine_name: {
                            "policyEngineId": "engine-1",
                            "policyEngineArn": "arn:engine",
                        }
                    },
                }
            }
        }
    }


@pytest.mark.parametrize("new_policy", [False, True])
def test_participant_update_orders_new_actions_before_policies_without_dropping_enforcement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    new_policy: bool,
) -> None:
    """A fresh action cannot validate until the preceding deploy publishes it."""
    provisioner = _load_provisioner()
    identity = provisioner.deployment_identity()
    root = tmp_path / "project"
    (root / "agentcore").mkdir(parents=True)
    (root / "agentcore" / "agentcore.json").write_text("{}")

    render_calls: list[dict[str, Any]] = []
    cli_calls: list[tuple[str, ...]] = []
    deployed_configs: list[dict[str, Any]] = []
    existing = {"name": "existing_forbid", "statement": "keep this policy unchanged"}
    policies = [existing] + ([{"name": "new_owner_permit"}] if new_policy else [])
    desired = {
        "policyEngines": [{"name": identity.policy_engine_name, "policies": policies}],
        "agentCoreGateways": [{"policyEngineConfiguration": {"mode": "ENFORCE"}}],
    }

    def render(**kwargs):
        render_calls.append(kwargs)
        (root / "agentcore/agentcore.json").write_text(json.dumps(desired))

    def cli(_root, *args, **_kwargs):
        cli_calls.append(args)
        if args[0] == "deploy":
            config = json.loads((root / "agentcore/agentcore.json").read_text())
            staged_policies = config["policyEngines"][0]["policies"]
            assert existing in staged_policies
            assert config["agentCoreGateways"] == desired["agentCoreGateways"]
            if new_policy and not deployed_configs:
                assert staged_policies == [existing], "new policy would validate before action publication"
            deployed_configs.append(config)

    monkeypatch.setattr(provisioner, "project_root", lambda *_a, **_k: root)
    monkeypatch.setattr(provisioner, "render_project", render)
    monkeypatch.setattr(provisioner, "_active_policy_names", lambda **_k: {"existing_forbid"})
    monkeypatch.setattr(provisioner, "_agentcore", cli)
    monkeypatch.setattr(
        provisioner, "_read_deployed_state", lambda _root: _participant_state(identity)
    )

    returned_root, state = provisioner._redeploy_participant_edits(
        repo=tmp_path,
        account_id="123456789012",
        region="us-east-1",
        cognito_pool="pool",
        cognito_client="client",
        lambda_arns=_lambda_arns(),
        model_id="model",
        opus_model_id="opus",
        sonnet_model_id="sonnet",
        workshop_id="dat416",
        env={},
        identity=identity,
    )

    assert returned_root == root
    assert state == _participant_state(identity)
    assert len(render_calls) == 1
    assert render_calls[0]["include_policies"] is True
    assert render_calls[0]["gateway_arn"] == "arn:gateway"
    assert cli_calls == [("validate",), ("deploy", "--yes", "--json")] * (2 if new_policy else 1)
    assert deployed_configs[-1] == desired
    assert json.loads((root / "agentcore/agentcore.json").read_text()) == desired


def test_participant_update_refuses_to_remove_an_active_policy(monkeypatch, tmp_path) -> None:
    provisioner = _load_provisioner()
    identity = provisioner.deployment_identity()
    root = tmp_path / "project"
    (root / "agentcore").mkdir(parents=True)
    config = {"policyEngines": [{"name": identity.policy_engine_name, "policies": []}]}
    (root / "agentcore/agentcore.json").write_text(json.dumps(config))
    monkeypatch.setattr(provisioner, "project_root", lambda *_a, **_k: root)
    monkeypatch.setattr(provisioner, "render_project", lambda **_k: None)
    monkeypatch.setattr(provisioner, "_read_deployed_state", lambda _r: _participant_state(identity))
    monkeypatch.setattr(provisioner, "_active_policy_names", lambda **_k: {"a_policy_added_by_hand"})
    monkeypatch.setattr(provisioner, "_agentcore", lambda *_a, **_k: pytest.fail("must not deploy"))
    with pytest.raises(RuntimeError, match="would remove active policies: a_policy_added_by_hand"):
        provisioner._redeploy_participant_edits(
            repo=tmp_path, account_id="123456789012", region="us-east-1",
            cognito_pool="pool", cognito_client="client", lambda_arns=_lambda_arns(),
            model_id="model", opus_model_id="opus", sonnet_model_id="sonnet",
            workshop_id="dat416", env={}, identity=identity,
        )


def test_participant_update_refuses_an_unprovisioned_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A participant edit cannot create the environment it is editing."""
    provisioner = _load_provisioner()
    identity = provisioner.deployment_identity()
    monkeypatch.setattr(
        provisioner, "project_root", lambda *_a, **_k: tmp_path / "absent"
    )

    with pytest.raises(RuntimeError) as exc_info:
        provisioner._redeploy_participant_edits(
            repo=tmp_path,
            account_id="123456789012",
            region="us-east-1",
            cognito_pool="pool",
            cognito_client="client",
            lambda_arns=_lambda_arns(),
            model_id="model",
            opus_model_id="opus",
            sonnet_model_id="sonnet",
            workshop_id="dat416",
            env={},
            identity=identity,
        )

    message = str(exc_info.value)
    assert "No deployed AgentCore project" in message
    assert "facilitator" in message


def test_participant_update_skips_the_preparation_stages_it_cannot_change() -> None:
    """The two 900-second waits must not sit on a participant's critical path."""
    source = PROVISIONER_PATH.read_text(encoding="utf-8")
    start = source.index("def _participant_update(")
    body = source[start : source.index("\n\ndef main() -> int:", start)]

    for skipped in (
        "_deploy_lambdas(",
        "_configure_transaction_search(",
        "_wait_for_unified_trace(",
        "_verify_agentcore_control_plane_audit(",
        "_ensure_trace_log_groups(",
        "_ensure_runtime_log_group(",
        "_deploy_claim_trigger(",
        "_enable_gateway_observability(",
        "_enable_memory_observability(",
        "_seed_memory(",
    ):
        assert skipped not in body, skipped

    # What it must still prove: the deploy landed, the published catalogue is
    # live, Cedar survived, and the running revision serves the edited package.
    for required in (
        "_redeploy_participant_edits(",
        "_verify_gateway_control_plane(",
        "_discover_live_gateway_tools(",
        "_authenticated_runtime_smoke(",
        "runtime_build_fingerprint_match",
        '"policyEngines", identity.policy_engine_name',
    ):
        assert required in body, required


def test_participant_mode_never_overwrites_the_full_managed_receipt() -> None:
    """lab3-start.sh and health-gate.sh validate the full receipt during Lab 3."""
    source = PROVISIONER_PATH.read_text(encoding="utf-8")
    start = source.index("output_path = Path(")
    selection = source[start : source.index("\n\n", start)]

    assert '"/tmp/pellier-agentcore-managed.json"' in selection
    assert '"/tmp/pellier-agentcore-participant.json"' in selection
    assert 'args.mode == "full"' in selection


def _lab4_check() -> Any:
    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("lab4_policy_check")


LAB4_SOLUTION = REPO_ROOT / "solutions/the-concierge/policies/workshop_credit_limit.cedar"
LAB4_STARTER = REPO_ROOT / "workshop" / "starters" / "workshop_credit_limit.cedar"


def _lab4_repo(tmp_path: Path, rule: str) -> Path:
    """A scratch checkout holding ``rule`` as Lab 4's policy beside the real starter."""
    starter = LAB4_STARTER
    (tmp_path / "policies").mkdir()
    (tmp_path / "workshop" / "starters").mkdir(parents=True)
    (tmp_path / "workshop" / "starters" / "workshop_credit_limit.cedar").write_text(
        starter.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "policies" / "workshop_credit_limit.cedar").write_text(rule, encoding="utf-8")
    return tmp_path


def test_a_deploy_refuses_a_lab_4_rule_the_cedar_check_contradicts(tmp_path, capsys) -> None:
    """The policy deploys under IGNORE_ALL_FINDINGS, so the local Cedar check is its gate."""
    provisioner = _load_provisioner()
    lab4 = _lab4_check()
    solution = LAB4_SOLUTION.read_text(encoding="utf-8")
    widened = _lab4_repo(tmp_path, lab4.widen_action(solution))
    with pytest.raises(RuntimeError, match="fails the Cedar check, so it was not deployed"):
        provisioner._lab4_rule_gate(widened)
    assert "Task 4A  CONTRADICTED" in capsys.readouterr().err


@pytest.mark.parametrize("which, state", [("starter", "NOT YET"), ("solution", "PROVED")])
def test_a_deploy_allows_the_starter_and_a_correct_rule(tmp_path, which, state) -> None:
    provisioner = _load_provisioner()
    source = {"starter": LAB4_STARTER, "solution": LAB4_SOLUTION}
    repo = _lab4_repo(tmp_path, source[which].read_text(encoding="utf-8"))
    assert provisioner._lab4_rule_gate(repo) == state


def _cedar_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: Any) -> Any:
        raise ImportError("cedarpy is not installed")

    monkeypatch.setattr(_lab4_check(), "local_check", broken)


def test_a_deploy_warns_and_deploys_the_starter_when_the_cedar_check_cannot_run(
    tmp_path, monkeypatch, capsys
) -> None:
    """Bootstrap and Lab 3 deploy the untouched starter; a missing checker must not stop them."""
    provisioner = _load_provisioner()
    _cedar_unavailable(monkeypatch)
    repo = _lab4_repo(tmp_path, LAB4_STARTER.read_text(encoding="utf-8"))
    assert provisioner._lab4_rule_gate(repo) == "UNCHECKED"
    assert "was not checked before this deploy: ImportError" in capsys.readouterr().err


def test_a_deploy_refuses_an_edited_rule_the_cedar_check_cannot_run_on(
    tmp_path, monkeypatch
) -> None:
    """Under IGNORE_ALL_FINDINGS nothing else would assess the edit before the Gateway."""
    provisioner = _load_provisioner()
    _cedar_unavailable(monkeypatch)
    repo = _lab4_repo(tmp_path, LAB4_SOLUTION.read_text(encoding="utf-8"))
    with pytest.raises(RuntimeError, match="differs from its starter, and the Cedar check could"):
        provisioner._lab4_rule_gate(repo)


def test_a_deploy_refuses_an_edited_rule_the_check_could_not_decide(tmp_path, monkeypatch) -> None:
    provisioner = _load_provisioner()
    lab4 = _lab4_check()
    undecided = types.SimpleNamespace(
        finding=types.SimpleNamespace(state="UNCHECKED", observed="unsound"))
    monkeypatch.setattr(lab4, "local_check", lambda *_args: undecided)
    repo = _lab4_repo(tmp_path, LAB4_SOLUTION.read_text(encoding="utf-8"))
    with pytest.raises(RuntimeError, match=r"could not run \(unsound\)"):
        provisioner._lab4_rule_gate(repo)


def test_delivery_names_fit_the_logs_limit_for_a_suffixed_deployment() -> None:
    """A dev-account deploy with suffix ``fourlab`` failed PutDeliverySource at 64 characters."""
    provisioner = _load_provisioner()
    kinds = ("logs-source", "traces-source", "logs-destination", "traces-destination")
    short = "pellier-pellier-gateway-gwgjwkwczj"
    assert [provisioner._delivery_name(short, kind) for kind in kinds] == [
        f"{short}-{kind}" for kind in kinds
    ]
    for resource_id in (
        "pellierfourlab-pellier-fourlab-gateway-ru1p9ac0r0",
        "pellierabcdefghijkl-pellier-abcdefghijkl-gateway-ru1p9ac0r0",
        "pellierfourlab_PellierFourlabMemory-uuQGPhBbs2",
    ):
        names = [provisioner._delivery_name(resource_id, kind) for kind in kinds]
        assert all(len(name) <= 60 for name in names), names
        assert all(name.endswith(kind) for name, kind in zip(names, kinds))
        assert all(resource_id.rsplit("-", 1)[1] in name for name in names)
        assert len(set(names)) == len(kinds)
