"""The own-account deploy script: templates, bucket, stack, outputs and teardown order."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "deploy" / "own-account" / "deploy.py"
TEMPLATES = REPO_ROOT / "deploy" / "own-account" / "templates"
PROVISIONER = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"
ACCOUNT = "123456789012"
SHA = "a" * 40
URL = "https://github.com/aws-samples/x.git"
AGENTCORE_ARN = "arn:aws:bedrock-agentcore:us-east-1:1:"
KMS_ARN = "arn:aws:kms:us-east-1:1:key/k"
TRACE: list[tuple[str, str]] = []


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("own_account_deploy", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


class _ClientError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.response = {"Error": {"Code": code, "Message": message}}


def _missing_stack(name: str) -> _ClientError:
    return _ClientError("ValidationError", f"Stack with id {name} does not exist")


class _Fake:
    """Records every call; answers from `answers`, raises from `errors`."""

    def __init__(
        self,
        answers: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
        label: str = "",
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.answers = answers or {}
        self.errors = errors or {}
        self.label = label

    def __getattr__(self, name: str) -> Any:
        def call(**kwargs: Any) -> Any:
            self.calls.append((name, kwargs))
            TRACE.append((self.label, name))
            if name in self.errors:
                raise self.errors[name]
            answer = self.answers.get(name, {})
            return answer(kwargs) if callable(answer) else answer

        return call

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args(self, name: str, key: str) -> list[Any]:
        return [kwargs[key] for called, kwargs in self.calls if called == name]


def _git_ok(cmd: list[str], **_: Any) -> SimpleNamespace:
    args = tuple(cmd[3:])
    answers = {
        ("remote", "get-url", "origin"): URL + "\n",
        ("rev-parse", "HEAD^{commit}"): SHA + "\n",
        ("status", "--porcelain"): "",
        ("fetch", "--quiet", URL, SHA): "",
    }
    return SimpleNamespace(returncode=0, stdout=answers.get(args, ""), stderr="")


OUTPUTS = [
    {"OutputKey": "OperatorPassword", "OutputValue": "hunter2"},
    {"OutputKey": "CodeEditorURL", "OutputValue": "https://d1.cloudfront.net/editor/?tkn=abc123"},
    {"OutputKey": "PellierURL", "OutputValue": "https://d1.cloudfront.net/ports/8000/"},
    {"OutputKey": "AgentCoreRuntimeLogKmsKeyArn", "OutputValue": KMS_ARN},
]
COMPLETE = {"Stacks": [{"StackStatus": "CREATE_COMPLETE", "Outputs": OUTPUTS}]}


def _clients(mod: Any, **overrides: Any) -> Any:
    TRACE.clear()
    identity = {"Account": ACCOUNT, "Arn": "arn:aws:iam::1:user/me"}
    base = {
        "sts": _Fake({"get_caller_identity": identity}),
        "iam": _Fake(),
        "s3": _Fake(errors={"head_bucket": _ClientError("404")}),
        "cloudformation": _Fake(
            {"describe_stacks": COMPLETE, "describe_stack_events": {"StackEvents": []}}
        ),
        "ssm": _Fake(),
        "ec2": _Fake({"describe_vpcs": {"Vpcs": []}, "describe_addresses": {"Addresses": []}}),
        "lambda_": _Fake(errors={"get_function": _ClientError("ResourceNotFoundException")}),
        "logs": _Fake({"describe_deliveries": {}, "describe_log_groups": {}}),
        "kms": _Fake(),
        "bedrock": _Fake(),
        "service_quotas": _Fake({"get_service_quota": {"Quota": {"Value": 100.0}}}),
        "agentcore_control": _Fake(
            {
                "list_policy_engines": {},
                "list_policies": {},
                "list_gateways": {},
                "list_memories": {},
                "list_agent_runtimes": {},
            }
        ),
    }
    base.update(overrides)
    for label, fake in base.items():
        fake.label = label
    return mod.Clients(**base)


def _run(
    mod: Any, argv: list[str], clients: Any, run: Any = _git_ok, probe: Any = None
) -> tuple[int, list[str]]:
    lines: list[str] = []
    probes: list[str] = []

    def answered(url: str) -> int:
        probes.append(url)
        return 403

    code = mod.main(
        argv,
        clients=clients,
        out=lines.append,
        run=run,
        sleep=lambda _s: None,
        now=iter(range(0, 100_000, 30)).__next__,
        probe=probe or answered,
    )
    clients.probes = probes
    return code, lines


DELETING = ("delete", "send", "schedule", "cancel", "put", "create", "detach")


def _deletes(client: Any) -> list[str]:
    return [name for name in client.names() if name.startswith(DELETING)]


# --------------------------------------------------------------------------- templates


def test_the_four_templates_ship_with_the_source() -> None:
    for name in (
        "pellier-governed.yml",
        "pellier-vpc.yml",
        "pellier-database.yml",
        "pellier-code-editor.yml",
    ):
        assert (TEMPLATES / name).is_file(), name


def test_the_root_template_carries_the_revision_of_the_four_files() -> None:
    mod = _load()
    root = (TEMPLATES / "pellier-governed.yml").read_text(encoding="utf-8")
    expected = mod.infrastructure_revision(TEMPLATES)
    assert mod.template_default(root, "InfrastructureRevision") == expected


def test_the_root_template_pins_a_full_commit_and_requires_only_the_bucket() -> None:
    mod = _load()
    root = (TEMPLATES / "pellier-governed.yml").read_text(encoding="utf-8")
    assert re.fullmatch(r"[0-9a-f]{40}", mod.template_default(root, "RepoRevision"))
    with pytest.raises(mod.OwnAccountError):
        mod.template_default(root, "AssetsBucketName")


# --------------------------------------------------------------------------- names


def test_names_follow_the_provisioner_with_and_without_a_suffix() -> None:
    mod = _load()
    plain, rc = mod.Names(""), mod.Names("rc")
    assert plain.agentcore_stack == "AgentCore-pellier-default"
    assert rc.agentcore_stack == "AgentCore-pellierrc-default"
    assert rc.functions == (
        "pellier-rc-store-tools-server-function",
        "pellier-rc-cognito-customer-claim",
    )
    store = "pellier-rc-store-tools-server-role"
    assert rc.roles[store]["inline"] == (f"{store}-policy",)


def _provisioner_delivery_name() -> Any:
    """The provisioner's own _delivery_name, lifted from its source without importing it."""
    tree = ast.parse(PROVISIONER.read_text(encoding="utf-8"))
    wanted = {"_delivery_name", "_DELIVERY_NAME_LIMIT"}
    nodes = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted)
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets)
        )
    ]
    namespace: dict[str, Any] = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PROVISIONER), "exec"), namespace)
    return namespace["_delivery_name"]


def test_delivery_names_match_the_provisioner_including_the_tail_rule() -> None:
    mod = _load()
    theirs = _provisioner_delivery_name()
    long_id = "pellierfourlab-pellier-fourlab-gateway-0123456789abcdef0123456789"
    for resource_id in ("pellier-gateway-abc", "PellierMemory-xyz", long_id):
        for kind in mod.DELIVERY_KINDS:
            assert mod.delivery_name(resource_id, kind) == theirs(resource_id, kind)
    assert len(mod.delivery_name(long_id, "traces-source")) == 60


def test_the_fetchable_url_is_https_without_credentials() -> None:
    mod = _load()
    assert mod.fetchable_url("git@github.com:aws-samples/x.git") == URL
    assert mod.fetchable_url("ssh://git@github.com/aws-samples/x") == URL
    assert mod.fetchable_url(URL) == URL
    with pytest.raises(mod.OwnAccountError):
        mod.fetchable_url("https://user:token@github.com/aws-samples/x.git")


# --------------------------------------------------------------------------- deploy


def test_deploy_refuses_an_unsupported_region() -> None:
    mod = _load()
    code, lines = _run(mod, ["deploy", "--region", "eu-west-1"], _clients(mod))
    assert code == 2 and "eu-west-1 is not supported" in lines[-1]


def test_deploy_refuses_a_dirty_tree_before_touching_the_account() -> None:
    mod = _load()
    clients = _clients(mod)

    def dirty(cmd: list[str], **kw: Any) -> SimpleNamespace:
        result = _git_ok(cmd, **kw)
        if cmd[3:] == ["status", "--porcelain"]:
            result.stdout = " M README.md\n"
        return result

    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients, run=dirty)
    assert code == 2 and "uncommitted changes" in lines[-1]
    assert clients.s3.calls == [] and clients.cloudformation.calls == []


def test_deploy_refuses_a_commit_the_origin_cannot_serve() -> None:
    mod = _load()

    def unpushed(cmd: list[str], **kw: Any) -> SimpleNamespace:
        result = _git_ok(cmd, **kw)
        if cmd[3] == "fetch":
            result.returncode = 128
        return result

    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], _clients(mod), run=unpushed)
    assert code == 2 and "cannot be fetched from" in lines[-1]


def test_deploy_fetches_from_the_given_repo_url_and_passes_it_to_the_stack() -> None:
    mod = _load()
    fork = "https://github.com/someone/fork.git"
    fetched: list[list[str]] = []

    def run(cmd: list[str], **kw: Any) -> SimpleNamespace:
        if cmd[3] == "fetch":
            fetched.append(cmd[4:])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return _git_ok(cmd, **kw)

    clients = _fresh(mod)
    code, _ = _run(mod, ["deploy", "--region", "us-east-1", "--repo-url", fork], clients, run=run)
    assert code == 0
    assert fetched == [["--quiet", fork, SHA]]
    stack = next(kw for name, kw in clients.cloudformation.calls if name == "create_stack")
    assert {p["ParameterKey"]: p["ParameterValue"] for p in stack["Parameters"]}["RepoUrl"] == fork


def test_deploy_refuses_when_the_stack_already_exists() -> None:
    mod = _load()
    clients = _clients(mod)
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 2 and "already exists (CREATE_COMPLETE)" in lines[-1]
    assert clients.s3.calls == []


def _fresh(mod: Any, **overrides: Any) -> Any:
    """Clients for a deploy into an account with no stack yet; the box is reachable after."""
    calls = {"count": 0}

    def describe_stacks(kw: dict[str, Any]) -> dict[str, Any]:
        if kw["StackName"].startswith("AgentCore-"):
            raise _missing_stack(kw["StackName"])
        calls["count"] += 1
        if calls["count"] == 1:
            raise _missing_stack(kw["StackName"])
        return COMPLETE

    def describe_stack_resource(kw: dict[str, Any]) -> dict[str, Any]:
        physical = {"CodeEditorStack": "arn:nested-editor", "CodeEditorInstance": "i-0abc"}
        return {"StackResourceDetail": {"PhysicalResourceId": physical[kw["LogicalResourceId"]]}}

    cloudformation = _Fake(
        {
            "describe_stacks": describe_stacks,
            "describe_stack_events": {"StackEvents": []},
            "describe_stack_resource": describe_stack_resource,
        }
    )
    ec2 = _Fake(
        {
            "describe_instances": {
                "Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]
            },
            "describe_vpcs": {"Vpcs": [{}] * 4},
            "describe_addresses": {"Addresses": [{}] * 3},
        }
    )
    ssm = _Fake(
        {
            "send_command": {"Command": {"CommandId": "cmd-1"}},
            "get_command_invocation": {
                "Status": "Success",
                "ResponseCode": 0,
                "StandardOutputContent": "PELLIER_RECEIPT_SAVED\n",
            },
        }
    )
    overrides = {
        "cloudformation": cloudformation,
        "ec2": ec2,
        "ssm": ssm,
        "lambda_": _Fake(errors={"get_function": _ClientError("ResourceNotFoundException")}),
        **overrides,
    }
    return _clients(mod, **overrides)


def test_dry_run_creates_nothing_and_lists_every_write() -> None:
    mod = _load()
    clients = _fresh(mod)
    code, lines = _run(mod, ["deploy", "--region", "us-west-2", "--dry-run"], clients)
    assert code == 0, lines
    assert clients.s3.names() == ["head_bucket"]
    assert [name for name in clients.cloudformation.names() if name != "describe_stacks"] == []
    assert clients.probes == [] and clients.ssm.calls == []
    writes = [line for line in lines if line.startswith("[dry-run]")]
    bucket = f"pellier-own-account-{ACCOUNT}-us-west-2"
    assert writes[0] == "[dry-run] create service-linked role for rds.amazonaws.com"
    assert writes[1] == f"[dry-run] create bucket {bucket} in us-west-2"
    assert any(line.startswith("[dry-run] put s3://") for line in writes)
    assert "[dry-run] create stack pellier-governed" in writes


def test_deploy_uploads_the_four_templates_and_passes_the_bucket_and_both_revisions() -> None:
    mod = _load()
    clients = _fresh(mod)
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 0, lines
    bucket = f"pellier-own-account-{ACCOUNT}-us-east-1"
    assert clients.s3.names()[:2] == ["head_bucket", "create_bucket"]
    assert clients.s3.names()[2] == "put_bucket_tagging"
    for call in ("put_public_access_block", "put_bucket_policy", "put_bucket_encryption"):
        assert call in clients.s3.names()
    assert clients.s3.args("put_object", "Key") == [
        "pellier/pellier-governed.yml",
        "pellier/pellier-vpc.yml",
        "pellier/pellier-database.yml",
        "pellier/pellier-code-editor.yml",
    ]
    stack = next(kw for name, kw in clients.cloudformation.calls if name == "create_stack")
    parameters = {p["ParameterKey"]: p["ParameterValue"] for p in stack["Parameters"]}
    assert parameters["AssetsBucketName"] == bucket
    assert parameters["AssetsBucketPrefix"] == "pellier/"
    assert parameters["RepoUrl"] == URL
    assert parameters["RepoRevision"] == SHA
    assert parameters["InfrastructureRevision"] == mod.infrastructure_revision(TEMPLATES)
    assert stack["TemplateURL"] == (
        f"https://{bucket}.s3.us-east-1.amazonaws.com/pellier/pellier-governed.yml"
    )
    assert stack["Capabilities"] == ["CAPABILITY_IAM"]
    assert any(line.startswith("Stack ready in ") for line in lines)
    saved = clients.ssm.calls[0][1]["Parameters"]["commands"][0]
    assert (
        "cp -p /tmp/pellier-agentcore-managed.json /var/lib/pellier/managed-receipt.json" in saved
    )
    assert saved.startswith("mkdir -p /var/lib/pellier && ")
    assert "-m 700" not in saved, "tightening the directory locks its owner out of the receipt"
    assert any("receipt saved to /var/lib/pellier/managed-receipt.json" in line for line in lines)


def test_deploy_creates_the_service_linked_role_and_waits_for_the_endpoint() -> None:
    mod = _load()
    iam = _Fake(errors={"create_service_linked_role": _ClientError("InvalidInput")})
    clients = _fresh(mod, iam=iam)
    answers = iter([307, 307, 403])
    seen: list[str] = []

    def probe(url: str) -> int:
        seen.append(url)
        return next(answers)

    code, lines = _run(mod, ["deploy", "--region", "us-west-2"], clients, probe=probe)
    assert code == 0, lines
    assert clients.iam.names() == ["create_service_linked_role"]
    assert "service-linked role for rds.amazonaws.com exists" in lines
    bucket = f"pellier-own-account-{ACCOUNT}-us-west-2"
    assert seen == [f"https://{bucket}.s3.us-west-2.amazonaws.com/pellier/pellier-vpc.yml"] * 3
    assert sum("answers 307" in line for line in lines) == 2
    assert "create_stack" in clients.cloudformation.names()


def test_deploy_refuses_an_account_that_already_holds_pellier_unless_suffixed() -> None:
    mod = _load()
    engines = {"policyEngines": [{"policyEngineId": "pellier_policy_engine-usqc5dbiek"}]}
    control = _Fake(
        {
            "list_policy_engines": engines,
            "list_gateways": {},
            "list_memories": {},
            "list_agent_runtimes": {},
        }
    )
    clients = _fresh(mod, agentcore_control=control)
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 2 and "policy engine pellier_policy_engine-usqc5dbiek" in lines[-1]
    assert "--deployment-suffix" in lines[-1]
    assert clients.s3.calls == []
    clients = _fresh(mod, agentcore_control=control)
    argv = ["deploy", "--region", "us-east-1", "--deployment-suffix", "own1030"]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    stacks = clients.cloudformation.args("describe_stacks", "StackName")
    assert "AgentCore-pellierown1030-default" in stacks
    assert clients.lambda_.args("get_function", "FunctionName") == [
        "pellier-own1030-store-tools-server-function",
        "pellier-own1030-cognito-customer-claim",
    ]
    stack = next(kw for name, kw in clients.cloudformation.calls if name == "create_stack")
    parameters = {p["ParameterKey"]: p["ParameterValue"] for p in stack["Parameters"]}
    assert parameters["DeploymentSuffix"] == "own1030"


def _quotas(vpcs: float, eips: float) -> Any:
    values = {"L-1216C47A": 1920.0, "L-952B80B8": 40.0, "L-F678F1CE": vpcs, "L-0263D0A3": eips}
    return _Fake({"get_service_quota": lambda kw: {"Quota": {"Value": values[kw["QuotaCode"]]}}})


def test_deploy_refuses_when_the_region_is_out_of_vpcs_or_elastic_ips() -> None:
    mod = _load()
    clients = _fresh(mod, service_quotas=_quotas(vpcs=5.0, eips=5.0))
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 0, lines
    clients = _fresh(mod, service_quotas=_quotas(vpcs=4.0, eips=5.0))
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 2 and "VPCs: 4 of 4 in use and the stack needs 1 more" in lines[-1]
    assert clients.s3.calls == []
    clients = _fresh(mod, service_quotas=_quotas(vpcs=5.0, eips=4.0))
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 2 and "Elastic IPs: 3 of 4 in use and the stack needs 2 more" in lines[-1]


def test_check_names_the_exhausted_quota() -> None:
    mod = _load()
    ec2 = _Fake({"describe_vpcs": {"Vpcs": [{}] * 5}, "describe_addresses": {"Addresses": []}})
    models = {"modelSummaries": [{"modelId": m} for m in mod.MODEL_IDS]}
    clients = _clients(
        mod,
        ec2=ec2,
        service_quotas=_quotas(vpcs=5.0, eips=5.0),
        bedrock=_Fake({"list_foundation_models": models}),
    )
    code, lines = _run(mod, ["check", "--region", "us-east-1"], clients)
    assert code == 1
    assert "capacity: VPCs: 5 of 5 in use and the stack needs 1 more" in "\n".join(lines)


def test_deploy_refuses_when_another_engine_holds_pelliers_policy_names() -> None:
    mod = _load()
    engines = {
        "policyEngines": [{"policyEngineId": "pelliercap1006c_pellier_cap1006c_policy_engine-0exn"}]
    }
    policies = {
        "policies": [{"name": "baseline_permit_workshop_tools"}, {"name": "workshop_credit_limit"}]
    }
    control = _Fake(
        {
            "list_policy_engines": engines,
            "list_policies": policies,
            "list_gateways": {},
            "list_memories": {},
            "list_agent_runtimes": {},
        }
    )
    clients = _fresh(mod, agentcore_control=control)
    argv = ["deploy", "--region", "us-east-1", "--deployment-suffix", "own1030"]
    code, lines = _run(mod, argv, clients)
    assert code == 2, lines
    assert "unique per account and Region" in lines[-1]
    assert "holds baseline_permit_workshop_tools, workshop_credit_limit" in lines[-1]
    assert clients.s3.calls == []
    assert clients.agentcore_control.args("list_policies", "policyEngineId") == [
        "pelliercap1006c_pellier_cap1006c_policy_engine-0exn"
    ]


def test_the_policy_names_match_the_renderer() -> None:
    """The renderer names each policy, literally or as f"{tool}_owner_only" for the reads."""
    mod = _load()
    sources = "\n".join(
        (REPO_ROOT / "scripts" / path).read_text(encoding="utf-8")
        for path in (
            "deploy/render_agentcore_project.py",
            "deploy/output_guardrail.py",
            "provision_agentcore_end_to_end.py",
        )
    )
    for name in mod.POLICY_NAMES:
        assert name in sources, name
    assert '"name": f"{tool}_owner_only"' in sources


def _shared_groups(spans_kms: str | None, signals_retention: int | None) -> Any:
    def describe(kw: dict[str, Any]) -> dict[str, Any]:
        if kw["logGroupNamePrefix"] == "aws/spans":
            return {
                "logGroups": [
                    {"logGroupName": "aws/spans", "kmsKeyId": spans_kms, "retentionInDays": 30}
                ]
            }
        return {
            "logGroups": [
                {
                    "logGroupName": "/aws/application-signals/data",
                    "kmsKeyId": "arn:k",
                    "retentionInDays": signals_retention,
                }
            ]
        }

    return _Fake({"describe_deliveries": {}, "describe_log_groups": describe})


def test_deploy_refuses_to_change_shared_trace_groups_unless_allowed() -> None:
    mod = _load()
    clients = _fresh(mod, logs=_shared_groups(spans_kms=None, signals_retention=None))
    code, lines = _run(mod, ["deploy", "--region", "us-west-2"], clients)
    assert code == 2, lines
    assert "aws/spans (unencrypted)" in lines[-1]
    assert "/aws/application-signals/data (retention unbounded)" in lines[-1]
    assert "--allow-shared-trace-log-changes" in lines[-1]
    assert clients.s3.calls == []
    clients = _fresh(mod, logs=_shared_groups(spans_kms=None, signals_retention=None))
    argv = ["deploy", "--region", "us-west-2", "--allow-shared-trace-log-changes"]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    stack = next(kw for name, kw in clients.cloudformation.calls if name == "create_stack")
    parameters = {p["ParameterKey"]: p["ParameterValue"] for p in stack["Parameters"]}
    assert parameters["AllowSharedTraceLogChanges"] == "true"
    clients = _fresh(mod, logs=_shared_groups(spans_kms="arn:k", signals_retention=30))
    code, lines = _run(mod, ["deploy", "--region", "us-west-2"], clients)
    assert code == 0, lines
    stack = next(kw for name, kw in clients.cloudformation.calls if name == "create_stack")
    assert {p["ParameterKey"]: p["ParameterValue"] for p in stack["Parameters"]}[
        "AllowSharedTraceLogChanges"
    ] == "false"


def test_teardown_finds_the_key_of_a_rolled_back_stack_in_the_nested_resources() -> None:
    mod = _load()
    clients = _teardown_clients(mod, agentcore=False, outputs=False)
    argv = ["teardown", "--region", "us-east-1", "--schedule-kms-key-deletion", "7"]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    assert clients.kms.args("schedule_key_deletion", "KeyId") == ["key-from-nested"]


def test_the_suffix_is_validated_before_anything_runs() -> None:
    mod = _load()
    for value in ("Own", "a-b", "toolongsuffix1"):
        with pytest.raises(SystemExit):
            mod.parse_args(["check", "--region", "us-east-1", "--deployment-suffix", value])


def test_deploy_refuses_a_bucket_this_script_did_not_create() -> None:
    mod = _load()
    s3 = _Fake(errors={"get_bucket_tagging": _ClientError("NoSuchTagSet")})
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], _fresh(mod, s3=s3))
    assert code == 2 and "was not created by this script" in lines[-1]
    assert "put_object" not in s3.names()


def test_deploy_waits_through_a_rollback_and_reports_the_first_failed_resource() -> None:
    mod = _load()
    statuses = iter(["ROLLBACK_IN_PROGRESS", "ROLLBACK_IN_PROGRESS", "ROLLBACK_COMPLETE"])
    seen: list[str] = []

    def describe_stacks(kw: dict[str, Any]) -> dict[str, Any]:
        if kw["StackName"].startswith("AgentCore-") or not seen:
            seen.append("first")
            raise _missing_stack(kw["StackName"])
        return {"Stacks": [{"StackStatus": next(statuses)}]}

    events = {
        "StackEvents": [
            {"LogicalResourceId": "pellier-governed", "ResourceStatus": "ROLLBACK_IN_PROGRESS"},
            {
                "LogicalResourceId": "DatabaseStack",
                "ResourceStatus": "CREATE_FAILED",
                "ResourceType": "AWS::CloudFormation::Stack",
                "ResourceStatusReason": "Embedded stack failed",
                "PhysicalResourceId": "arn:nested",
            },
        ]
    }
    nested = {
        "StackEvents": [
            {
                "LogicalResourceId": "AuroraCluster",
                "ResourceStatus": "CREATE_FAILED",
                "ResourceType": "AWS::RDS::DBCluster",
                "ResourceStatusReason": "engine 18.3 unavailable",
            }
        ]
    }
    cloudformation = _Fake(
        {
            "describe_stacks": describe_stacks,
            "describe_stack_events": lambda kw: (
                nested if kw["StackName"] == "arn:nested" else events
            ),
        }
    )
    clients = _clients(mod, cloudformation=cloudformation)
    code, lines = _run(mod, ["deploy", "--region", "us-east-1"], clients)
    assert code == 1
    assert "ended ROLLBACK_COMPLETE" in lines[-1]
    assert "DatabaseStack: AuroraCluster: engine 18.3 unavailable" in lines[-1]


def test_an_aws_error_is_reported_in_one_line_not_a_traceback() -> None:
    mod = _load()
    cloudformation = _Fake(
        errors={"describe_stacks": _ClientError("AccessDenied", "no cloudformation:DescribeStacks")}
    )
    code, lines = _run(
        mod, ["status", "--region", "us-east-1"], _clients(mod, cloudformation=cloudformation)
    )
    assert code == 1 and lines[-1] == "failed: no cloudformation:DescribeStacks"


def test_outputs_mask_the_password_and_the_editor_token_unless_asked() -> None:
    mod = _load()
    code, lines = _run(mod, ["status", "--region", "us-east-1"], _clients(mod))
    assert code == 0
    assert "  OperatorPassword: <masked; --show-secrets prints it>" in lines
    assert any("tkn=<masked" in line for line in lines)
    assert not any("hunter2" in line or "tkn=abc123" in line for line in lines)
    _, shown = _run(mod, ["status", "--region", "us-east-1", "--show-secrets"], _clients(mod))
    assert "  OperatorPassword: hunter2" in shown


def test_check_is_read_only_and_names_missing_models() -> None:
    mod = _load()
    models = {"modelSummaries": [{"modelId": "anthropic.claude-opus-5-5"}]}
    clients = _clients(
        mod,
        iam=_Fake(errors={"get_role": _ClientError("NoSuchEntity")}),
        bedrock=_Fake({"list_foundation_models": models}),
        service_quotas=_Fake({"get_service_quota": {"Quota": {"Value": 1920.0}}}),
    )
    code, lines = _run(mod, ["check", "--region", "us-east-1"], clients)
    assert code == 1
    assert "service-linked role AWSServiceRoleForRDS is missing; deploy creates it" in lines
    assert "create_service_linked_role" not in clients.iam.names()
    assert "model cohere.rerank-v3-5:0: NOT listed in this Region" in lines
    assert "quota Running On-Demand Standard instances (vCPUs): 1920" in lines
    for client in (clients.iam, clients.s3, clients.cloudformation):
        assert not _deletes(client)


def test_check_reports_an_existing_pellier_deployment() -> None:
    mod = _load()
    control = _Fake(
        {
            "list_policy_engines": {},
            "list_gateways": {"items": [{"gatewayId": "pellier-gateway-gwg"}]},
            "list_memories": {"memories": [{"id": "pelliercap1006c_PellierCap1006cMemory-6T"}]},
            "list_agent_runtimes": {},
        }
    )
    clients = _clients(
        mod,
        agentcore_control=control,
        bedrock=_Fake(
            {"list_foundation_models": {"modelSummaries": [{"modelId": m} for m in mod.MODEL_IDS]}}
        ),
        service_quotas=_Fake({"get_service_quota": {"Quota": {"Value": 8.0}}}),
    )
    code, lines = _run(mod, ["check", "--region", "us-east-1"], clients)
    assert code == 0
    assert "already in this account: gateway pellier-gateway-gwg" in lines
    assert not any("PellierCap1006cMemory" in line for line in lines)
    assert any("pass --deployment-suffix" in line for line in lines)


# --------------------------------------------------------------------------- teardown


def _resource(kind: str, logical: str, physical: str) -> dict[str, str]:
    return {"ResourceType": kind, "LogicalResourceId": logical, "PhysicalResourceId": physical}


AGENTCORE_RESOURCES = {
    "StackResources": [
        _resource("AWS::IAM::Role", "McpGatewayTargetRole", "target-role"),
        _resource("AWS::IAM::Role", "McpGatewayRole", "gw-role"),
        _resource(
            "AWS::BedrockAgentCore::Gateway", "Gw", AGENTCORE_ARN + "gateway/pellier-gateway-abc"
        ),
        _resource(
            "AWS::BedrockAgentCore::Memory", "Mem", AGENTCORE_ARN + "memory/PellierMemory-xyz"
        ),
        _resource(
            "AWS::BedrockAgentCore::Runtime",
            "Rt",
            AGENTCORE_ARN + "runtime/pellier_orchestrator-id1",
        ),
    ]
}


def _teardown_clients(
    mod: Any,
    *,
    instance: str = "running",
    agentcore: bool = True,
    stack: bool = True,
    box_exit: int = 0,
    box_output: str = "restored X-Ray settings\n",
    ours: bool = True,
    suffix: str = "",
    agentcore_older: bool = False,
    outputs: bool = True,
) -> Any:
    polls = {"count": 0}
    deleted: list[str] = []
    deleting = {
        "Stacks": [
            {
                "StackStatus": "DELETE_IN_PROGRESS",
                "CreationTime": "2026-10-30T03:10:49",
                "Outputs": OUTPUTS if outputs else [],
                "Parameters": [
                    {"ParameterKey": "ExistingRuntimeLogKmsKeyArn", "ParameterValue": ""},
                    {"ParameterKey": "DeploymentSuffix", "ParameterValue": suffix},
                ],
            }
        ]
    }

    def describe_stacks(kw: dict[str, Any]) -> dict[str, Any]:
        if kw["StackName"] == "pellier-governed" and not stack:
            raise _missing_stack(kw["StackName"])
        if kw["StackName"].startswith("AgentCore-"):
            if not agentcore or kw["StackName"] in deleted:
                raise _missing_stack(kw["StackName"])
            created = "2026-07-06T05:50:04" if agentcore_older else "2026-10-30T03:38:29"
            return {"Stacks": [{"StackStatus": "UPDATE_COMPLETE", "CreationTime": created}]}
        polls["count"] += 1
        if polls["count"] > 4:
            raise _missing_stack(kw["StackName"])
        return deleting

    def describe_stack_resource(kw: dict[str, Any]) -> dict[str, Any]:
        if instance == "absent" and kw["LogicalResourceId"] == "CodeEditorInstance":
            raise _ClientError("ValidationError", "Resource CodeEditorInstance does not exist")
        physical = {
            "CodeEditorStack": "arn:nested-editor",
            "CodeEditorInstance": "i-0abc",
            "AgentCoreRuntimeLogKey": "key-from-nested",
        }
        return {"StackResourceDetail": {"PhysicalResourceId": physical[kw["LogicalResourceId"]]}}

    cloudformation = _Fake(
        {
            "describe_stacks": describe_stacks,
            "describe_stack_events": {"StackEvents": []},
            "describe_stack_resource": describe_stack_resource,
            "delete_stack": lambda kw: deleted.append(kw["StackName"]),
        }
    )
    if agentcore:
        cloudformation.answers["describe_stack_resources"] = AGENTCORE_RESOURCES
    else:
        cloudformation.errors["describe_stack_resources"] = _missing_stack(
            "AgentCore-pellier-default"
        )
    ec2 = _Fake(
        {"describe_instances": {"Reservations": [{"Instances": [{"State": {"Name": instance}}]}]}}
    )
    ssm = _Fake(
        {
            "send_command": {"Command": {"CommandId": "cmd-1"}},
            "get_command_invocation": {
                "Status": "Success" if box_exit == 0 else "Failed",
                "ResponseCode": box_exit,
                "StandardOutputContent": box_output,
            },
        }
    )
    logs = _Fake(
        {
            "describe_deliveries": {
                "deliveries": [
                    {"id": "d-1", "deliverySourceName": "pellier-gateway-abc-logs-source"},
                    {"id": "d-2", "deliverySourceName": "other-app-logs-source"},
                ]
            }
        }
    )
    tags = [{"Key": "PellierOwnAccount", "Value": "true"}] if ours else []
    s3 = _Fake(
        {
            "get_bucket_tagging": {"TagSet": tags},
            "list_object_versions": {
                "Versions": [{"Key": "pellier/pellier-vpc.yml", "VersionId": "null"}],
                "DeleteMarkers": [],
            },
        }
    )
    control = _Fake({"get_gateway": {"roleArn": "arn:aws:iam::1:role/gw-role"}})
    return _clients(
        mod,
        cloudformation=cloudformation,
        ec2=ec2,
        ssm=ssm,
        logs=logs,
        s3=s3,
        agentcore_control=control,
    )


def test_teardown_runs_on_the_box_first_then_deletes_in_order() -> None:
    mod = _load()
    clients = _teardown_clients(mod)
    argv = [
        "teardown",
        "--region",
        "us-west-2",
        "--delete-bucket",
        "--schedule-kms-key-deletion",
        "7",
    ]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    sent = clients.ssm.calls[0][1]["Parameters"]["commands"][0]
    assert "python3.14 scripts/teardown_agentcore_observability.py --receipt $R" in sent
    assert "--confirm-workshop-cleanup --region us-west-2" in sent
    assert (
        "R=/var/lib/pellier/managed-receipt.json" in sent
        and "/tmp/pellier-agentcore-managed.json" in sent
    )
    assert 'sudo -u "$owner"' in sent
    first_write = next(i for i, (_, name) in enumerate(TRACE) if name.startswith(DELETING))
    assert TRACE[first_write] == ("ssm", "send_command")
    assert "restored X-Ray settings" in lines
    assert clients.logs.args("delete_delivery", "id") == ["d-1"]
    assert clients.logs.args("delete_delivery_source", "name") == [
        "pellier-gateway-abc-logs-source",
        "pellier-gateway-abc-traces-source",
        "PellierMemory-xyz-logs-source",
        "PellierMemory-xyz-traces-source",
    ]
    policies = [kw for name, kw in clients.iam.calls if name == "delete_role_policy"]
    guard = next(kw for kw in policies if kw["PolicyName"] == "PellierManagedOutputChecks")
    assert guard["RoleName"] == "gw-role"
    assert clients.agentcore_control.args("get_gateway", "gatewayIdentifier") == [
        "pellier-gateway-abc"
    ]
    assert clients.cloudformation.args("delete_stack", "StackName") == [
        "AgentCore-pellier-default",
        "pellier-governed",
    ]
    assert clients.lambda_.args("delete_function", "FunctionName") == [
        "pellier-store-tools-server-function",
        "pellier-cognito-customer-claim",
    ]
    assert clients.iam.args("delete_role", "RoleName") == [
        "pellier-store-tools-server-role",
        "pellier-cognito-customer-claim-role",
    ]
    groups = clients.logs.args("delete_log_group", "logGroupName")
    assert "/aws/lambda/pellier-store-tools-server-function" in groups
    assert "/aws/bedrock-agentcore/runtimes/pellier_orchestrator-id1-DEFAULT" in groups
    assert "/aws/vendedlogs/bedrock-agentcore/pellier-gateway-abc" in groups
    assert "/aws/pellier/readiness" not in groups
    assert clients.kms.names() == ["schedule_key_deletion"]
    assert clients.s3.names()[-2:] == ["delete_objects", "delete_bucket"]
    assert any(line.startswith("Stack deleted in ") for line in lines)


def test_teardown_refuses_before_deleting_when_the_box_cannot_restore_the_account() -> None:
    mod = _load()
    cases = {
        "stopped": _teardown_clients(mod, instance="stopped"),
        "exit 1": _teardown_clients(mod, box_exit=1, box_output="boom\n"),
        "absent": _teardown_clients(mod, instance="absent"),
        "no receipt": _teardown_clients(mod, box_exit=3, box_output="PELLIER_RECEIPT_MISSING\n"),
    }
    for label, clients in cases.items():
        code, lines = _run(mod, ["teardown", "--region", "us-east-1"], clients)
        assert code == 2 and lines[-1].startswith("refused: nothing deleted:"), (label, lines[-1])
        assert "--force" in lines[-1]
        if label == "no receipt":
            assert "no provisioning receipt" in lines[-1]
        for client in (
            clients.cloudformation,
            clients.lambda_,
            clients.iam,
            clients.logs,
            clients.s3,
        ):
            assert not _deletes(client), label


def test_teardown_refuses_a_missing_stack_unless_forced() -> None:
    mod = _load()
    clients = _teardown_clients(mod, stack=False)
    code, lines = _run(mod, ["teardown", "--region", "us-east-1"], clients)
    assert code == 2 and "no stack pellier-governed in us-east-1" in lines[-1]
    for client in (clients.cloudformation, clients.lambda_, clients.iam, clients.logs, clients.s3):
        assert not _deletes(client)
    clients = _teardown_clients(mod, stack=False)
    code, lines = _run(mod, ["teardown", "--region", "us-east-1", "--force"], clients)
    assert code == 0, lines
    assert clients.cloudformation.args("delete_stack", "StackName") == ["AgentCore-pellier-default"]
    assert "Stack deleted in" not in "\n".join(lines)


def test_teardown_refuses_an_agentcore_stack_older_than_the_workshop_stack() -> None:
    mod = _load()
    clients = _teardown_clients(mod, agentcore_older=True)
    code, lines = _run(mod, ["teardown", "--region", "us-east-1", "--force"], clients)
    assert code == 2 and "was created before pellier-governed" in lines[-1]
    for client in (
        clients.cloudformation,
        clients.lambda_,
        clients.iam,
        clients.logs,
        clients.s3,
        clients.ssm,
    ):
        assert not _deletes(client)


def test_teardown_refuses_a_suffix_that_does_not_match_the_stack() -> None:
    mod = _load()
    clients = _teardown_clients(mod, suffix="rc")
    code, lines = _run(mod, ["teardown", "--region", "us-east-1"], clients)
    assert code == 2 and "pass --deployment-suffix 'rc'" in lines[-1]
    assert not _deletes(clients.cloudformation)


def test_teardown_with_force_deletes_but_keeps_the_kms_key() -> None:
    mod = _load()
    clients = _teardown_clients(mod, box_exit=1, box_output="boom\n")
    argv = ["teardown", "--region", "us-east-1", "--force", "--schedule-kms-key-deletion", "7"]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    assert clients.cloudformation.args("delete_stack", "StackName") == [
        "AgentCore-pellier-default",
        "pellier-governed",
    ]
    assert clients.kms.calls == []
    left = "\n".join(lines[lines.index("Left in place:") :])
    assert "may not be restored" in left and "account-wide log groups may still use it" in left


def test_teardown_without_an_agentcore_stack_needs_no_box_and_keeps_key_and_bucket() -> None:
    mod = _load()
    clients = _teardown_clients(mod, agentcore=False, instance="stopped")
    code, lines = _run(mod, ["teardown", "--region", "us-east-1"], clients)
    assert code == 0, lines
    assert clients.ssm.calls == []
    assert clients.cloudformation.args("delete_stack", "StackName") == ["pellier-governed"]
    assert clients.kms.calls == [] and "delete_bucket" not in clients.s3.names()
    left = "\n".join(lines[lines.index("Left in place:") :])
    assert "no stack AgentCore-pellier-default" in left
    assert "--schedule-kms-key-deletion 7" in left and "--delete-bucket" in left


def test_teardown_uses_the_suffixed_names() -> None:
    mod = _load()
    clients = _teardown_clients(mod, agentcore=False, suffix="rc")
    argv = ["teardown", "--region", "us-east-1", "--deployment-suffix", "rc"]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    assert clients.cloudformation.args("describe_stack_resources", "StackName") == [
        "AgentCore-pellierrc-default"
    ]
    assert clients.lambda_.args("delete_function", "FunctionName")[0] == (
        "pellier-rc-store-tools-server-function"
    )


def test_teardown_refuses_to_delete_a_bucket_it_did_not_create() -> None:
    mod = _load()
    clients = _teardown_clients(mod, ours=False)
    code, lines = _run(mod, ["teardown", "--region", "us-east-1", "--delete-bucket"], clients)
    assert code == 2 and "was not created by this script" in lines[-1]
    assert "delete_bucket" not in clients.s3.names()


def test_teardown_dry_run_deletes_nothing() -> None:
    mod = _load()
    clients = _teardown_clients(mod)
    argv = ["teardown", "--region", "us-east-1", "--delete-bucket", "--dry-run"]
    code, lines = _run(mod, argv, clients)
    assert code == 0, lines
    for client in (
        clients.cloudformation,
        clients.lambda_,
        clients.iam,
        clients.logs,
        clients.s3,
        clients.kms,
        clients.ssm,
    ):
        assert not _deletes(client)
    assert "[dry-run] delete stack pellier-governed" in lines
    assert "Stack deleted in" not in "\n".join(lines)


def test_kms_window_is_enforced_before_anything_runs() -> None:
    mod = _load()
    for value in ("3", "31", "seven"):
        with pytest.raises(SystemExit):
            mod.parse_args(
                ["teardown", "--region", "us-east-1", "--schedule-kms-key-deletion", value]
            )
