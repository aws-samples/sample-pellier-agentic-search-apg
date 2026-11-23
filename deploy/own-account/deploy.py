#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""Deploy, inspect and tear down Pellier in your own AWS account.

Run from the repository root with uv, which installs boto3 for the script:

    uv run deploy/own-account/deploy.py check    --region us-east-1
    uv run deploy/own-account/deploy.py deploy   --region us-east-1
    uv run deploy/own-account/deploy.py status   --region us-east-1
    uv run deploy/own-account/deploy.py teardown --region us-east-1 --delete-bucket

``deploy`` creates a private bucket in your account, uploads the four CloudFormation
templates under ``deploy/own-account/templates/`` in the layout the Workshop Studio bucket
uses, and creates the stack with that bucket as its two asset parameters. The box then
fetches this repository at the commit you deployed from, so the tree must be clean and the
commit must be fetchable from the repository's origin. ``--dry-run`` makes the read-only
calls that describe your account and prints every write it would make, making none.

``teardown`` removes what the stack does not own: the AgentCore CDK stack the box created,
the three Lambda functions and their roles, the log deliveries, and the log groups; it first
runs the repository's observability teardown on the box over SSM, because the receipt that
restores the account-wide X-Ray settings lives only there, and it stops before deleting
anything when that step cannot run. It writes only to a stack that carries Pellier's tags, and
it records the KMS key and the other identifiers the stack holds under ``.local/own-account/``
before deleting the stack, so the command it prints for finishing a partial run still works
once the stack is gone. Then it deletes the workshop stack and, with ``--delete-bucket``, the
bucket the deploy created. ``docs/run-in-your-own-account.md`` is
the guide.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

SUPPORTED_REGIONS = ("us-east-1", "us-west-2")
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
TEMPLATE_DIR = HERE / "templates"
# Teardown saves what it needs after the stack is gone here; .local/ is untracked.
DEFAULT_STATE_DIR = REPO_ROOT / ".local" / "own-account"
STATE_FIELDS = ("deployment_suffix", "workshop_id", "kms_key_arn", "kms_key_is_ours", "restored")
ROOT_TEMPLATE = "pellier-governed.yml"
NESTED_TEMPLATES = ("pellier-vpc.yml", "pellier-database.yml", "pellier-code-editor.yml")
TEMPLATE_FILES = (ROOT_TEMPLATE, *NESTED_TEMPLATES)
# The Workshop Studio repo computes the same digest over these paths, so both agree.
STUDIO_PATHS = {
    ROOT_TEMPLATE: "static/pellier-governed.yml",
    "pellier-vpc.yml": "assets/pellier-vpc.yml",
    "pellier-database.yml": "assets/pellier-database.yml",
    "pellier-code-editor.yml": "assets/pellier-code-editor.yml",
}
INFRASTRUCTURE_DEFAULT_RE = re.compile(
    r"(?ms)(^\s*InfrastructureRevision:\s*$(?:(?!^\S).)*?^\s+Default:\s*)([\"']?)[0-9a-f]{16}\2"
)
SSH_URL_RE = re.compile(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$")
DEFAULT_STACK_NAME = "pellier-governed"
DEFAULT_PREFIX = "pellier/"
DEFAULT_INSTANCE_TYPE = "c6g.2xlarge"
EVENT_NAME = "own-account"
BUCKET_TAG = ("PellierOwnAccount", "true")
PROJECT_TAG = ("Project", "pellier")
# The tags create_stack puts on the root stack; teardown writes only to a stack that has both.
STACK_OWNER_TAGS = (PROJECT_TAG, BUCKET_TAG)
WORKSHOP_ID_TAG = "PellierWorkshopId"
RDS_SERVICE_LINKED_ROLE = "rds.amazonaws.com"
RDS_SERVICE_LINKED_ROLE_NAME = "AWSServiceRoleForRDS"
GLOBAL_ENDPOINT_WAIT_SECONDS = 600
MODEL_IDS = (
    "anthropic.claude-opus-5-5",
    "anthropic.claude-sonnet-5-5",
    "cohere.embed-v4:0",
    "cohere.rerank-v3-5:0",
)
QUOTAS = (
    ("ec2", "L-1216C47A", "Running On-Demand Standard instances (vCPUs)"),
    ("rds", "L-952B80B8", "DB clusters"),
)
# What the stack adds to the Region, against quotas a busy account can have used up.
CAPACITY = (
    ("vpc", "L-F678F1CE", "VPCs", 1),
    ("ec2", "L-0263D0A3", "Elastic IPs", 2),
)
POLL_SECONDS = 30
STACK_WAIT_SECONDS = 4 * 3600
SSM_WAIT_SECONDS = 900
SSM_RUNNING = ("Pending", "InProgress", "Delayed", "Cancelling")
BOX_REPO = "/workshop/sample-pellier-agentic-search-apg"
TMP_RECEIPT = "/tmp/pellier-agentcore-managed.json"
SAVED_RECEIPT = "/var/lib/pellier/managed-receipt.json"
RECEIPT_MISSING = "PELLIER_RECEIPT_MISSING"
RECEIPT_MISSING_CODE = 3
# Runs as root over SSM. The provisioner wrote the receipt as the bootstrap user with mode
# 0600, and the observability teardown reads it only as its owner, so the teardown runs as
# that owner. The deploy copies the receipt out of /tmp, which is memory-backed on the host.
# mkdir -p, not install -m: the bootstrap owns /var/lib/pellier (root:participant, 775), and
# tightening its mode would lock the receipt's owner out of the copy.
PRESERVE_RECEIPT = (
    f"mkdir -p /var/lib/pellier && cp -p {TMP_RECEIPT} {SAVED_RECEIPT} "
    f"&& echo PELLIER_RECEIPT_SAVED"
)
OBSERVABILITY_TEARDOWN = (
    f'R={SAVED_RECEIPT}; [ -f "$R" ] || R={TMP_RECEIPT}; '
    f'if [ ! -f "$R" ]; then echo {RECEIPT_MISSING}; exit {RECEIPT_MISSING_CODE}; fi; '
    'owner=$(stat -c %U "$R"); sudo -u "$owner" -H bash -lc '
    f'"cd {BOX_REPO} && python3.14 scripts/teardown_agentcore_observability.py '
    '--receipt $R --confirm-workshop-cleanup --region {region}"'
)
DELIVERY_NAME_LIMIT = 60
DELIVERY_KINDS = ("logs-source", "traces-source", "logs-destination", "traces-destination")
GATEWAY_INLINE_POLICY = "PellierManagedOutputChecks"
READINESS_LOG_GROUP = "/aws/pellier/readiness"
# Account-wide X-Ray Transaction Search groups. The host encrypts them with the stack's key
# and bounds their retention; when they already exist with other settings, the provisioner
# refuses to change them unless the stack says the account owner allows it.
SHARED_TRACE_LOG_GROUPS = ("aws/spans", "/aws/application-signals/data")
SHARED_TRACE_RETENTION_DAYS = 30
KMS_KEY_LOGICAL_ID = "AgentCoreRuntimeLogKey"
SECRET_OUTPUTS = ("OperatorPassword",)
KMS_WINDOW = (7, 30)
SUFFIX_RE = re.compile(r"^[a-z][a-z0-9]{0,11}$")
POLICY_COLLISION_ADVICE = (
    "AgentCore keeps Cedar policy names unique per account and Region, so a Region holds one "
    "Pellier deployment. Remove that deployment first, or deploy in the other Region with its "
    "own --deployment-suffix, because IAM role names are account-wide"
)
# The Cedar policies the box creates. AgentCore keeps policy names unique per account and
# Region, across policy engines, so a second Pellier deployment collides on them whatever its
# suffix; the test pins these to scripts/deploy/render_agentcore_project.py.
POLICY_NAMES = (
    "baseline_permit_workshop_tools",
    "get_orders_owner_only",
    "get_tickets_owner_only",
    "ask_a_person_caller_bound",
    "give_store_credit_staff_scope",
    "credit_output_sensitive_information",
    "credit_limit",
)


class OwnAccountError(Exception):
    """A refusal with a message the participant can act on."""


@dataclass
class Clients:
    """The boto3 clients a command uses; tests pass fakes."""

    sts: Any = None
    iam: Any = None
    s3: Any = None
    cloudformation: Any = None
    ssm: Any = None
    ec2: Any = None
    lambda_: Any = None
    logs: Any = None
    kms: Any = None
    bedrock: Any = None
    service_quotas: Any = None
    agentcore_control: Any = None

    @classmethod
    def from_session(cls, region: str, profile: str | None) -> "Clients":
        import boto3  # noqa: PLC0415 - imported here so --help works without boto3

        session = boto3.session.Session(region_name=region, profile_name=profile)
        return cls(
            sts=session.client("sts"),
            iam=session.client("iam"),
            s3=session.client("s3"),
            cloudformation=session.client("cloudformation"),
            ssm=session.client("ssm"),
            ec2=session.client("ec2"),
            lambda_=session.client("lambda"),
            logs=session.client("logs"),
            kms=session.client("kms"),
            bedrock=session.client("bedrock"),
            service_quotas=session.client("service-quotas"),
            agentcore_control=session.client("bedrock-agentcore-control"),
        )


@dataclass
class Runner:
    """Routes every AWS call through one place, so --dry-run can print and skip the writes."""

    clients: Clients
    out: Callable[[str], None]
    dry_run: bool = False
    writes: list[str] = field(default_factory=list)

    def read(self, label: str, call: Callable[..., Any], **kwargs: Any) -> Any:
        return call(**kwargs)

    def write(self, label: str, call: Callable[..., Any], **kwargs: Any) -> Any:
        self.writes.append(label)
        if self.dry_run:
            self.out(f"[dry-run] {label}")
            return None
        self.out(label)
        return call(**kwargs)


def error_code(exc: Exception) -> str:
    """The AWS error code inside a botocore ClientError, or an empty string."""
    response = getattr(exc, "response", None) or {}
    return str((response.get("Error") or {}).get("Code") or "")


def is_missing(exc: Exception) -> bool:
    """True for the errors AWS raises when the thing asked about does not exist."""
    return error_code(exc) in (
        "ResourceNotFoundException",
        "NoSuchEntity",
        "NoSuchBucket",
        "NoSuchTagSet",
        "InvalidInstanceID.NotFound",
        "404",
    ) or "does not exist" in str(exc)


def ignore_missing(call: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(**kwargs: Any) -> Any:
        try:
            return call(**kwargs)
        except Exception as exc:  # noqa: BLE001 - only absence is tolerated
            if is_missing(exc):
                return None
            raise

    return wrapped


def ignore_pending_deletion(call: Callable[..., Any]) -> Callable[..., Any]:
    """Treat a KMS key AWS already holds for deletion as scheduled: a recovery rerun may meet it."""

    def wrapped(**kwargs: Any) -> Any:
        try:
            return call(**kwargs)
        except Exception as exc:  # noqa: BLE001 - only a key already pending deletion is tolerated
            if (error_code(exc) == "KMSInvalidStateException"
                    and "pending deletion" in str(exc).lower()):
                return None
            raise

    return wrapped


# --------------------------------------------------------------------------- names


@dataclass(frozen=True)
class Names:
    """Every name the box's provisioner derives from PELLIER_DEPLOYMENT_SUFFIX."""

    suffix: str

    @property
    def dash(self) -> str:
        return f"-{self.suffix}" if self.suffix else ""

    @property
    def agentcore_stack(self) -> str:
        return f"AgentCore-pellier{self.suffix}-default"

    @property
    def functions(self) -> tuple[str, ...]:
        return (
            f"pellier{self.dash}-store-tools-server-function",
            f"pellier{self.dash}-operator-tools-server-function",
            f"pellier{self.dash}-cognito-customer-claim",
        )

    @property
    def roles(self) -> dict[str, dict[str, tuple[str, ...]]]:
        store = f"pellier{self.dash}-store-tools-server-role"
        operator = f"pellier{self.dash}-operator-tools-server-role"
        claim = f"pellier{self.dash}-cognito-customer-claim-role"
        return {
            store: {"inline": (f"{store}-policy",), "managed": ()},
            operator: {"inline": (f"{operator}-policy",), "managed": ()},
            claim: {
                "inline": (),
                "managed": ("arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",),
            },
        }


def collision_prefixes(names: Names) -> tuple[str, str]:
    """The AgentCore CLI prefixes every resource it creates with the project name."""
    project = f"pellier{names.suffix}"
    return (f"{project}_", f"{project}-")


def list_all(
    runner: Runner, label: str, call: Callable[..., Any], key: str, **kwargs: Any
) -> list[dict[str, Any]]:
    """Every item of an AgentCore listing, following nextToken to the last page."""
    items: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        page_kwargs = {**kwargs, "nextToken": token} if token else kwargs
        page = runner.read(label, call, **page_kwargs)
        items.extend(page.get(key, []))
        token = page.get("nextToken")
        if not token:
            return items


def policy_name_holders(runner: Runner) -> list[str]:
    """Policy engines in the Region that already hold one of Pellier's policy names."""
    control = runner.clients.agentcore_control
    holders: list[str] = []
    for engine in list_all(
        runner, "list policy engines", control.list_policy_engines, "policyEngines"
    ):
        engine_id = str(engine.get("policyEngineId") or "")
        if not engine_id:
            continue
        policies = list_all(
            runner,
            f"list policies of {engine_id}",
            control.list_policies,
            "policies",
            policyEngineId=engine_id,
        )
        taken = sorted({str(p.get("name")) for p in policies} & set(POLICY_NAMES))
        if taken:
            holders.append(f"policy engine {engine_id} holds {', '.join(taken)}")
    return holders


def role_holders(runner: Runner, names: Names, own_workshop_id: str | None = None) -> list[str]:
    """IAM roles under this deployment's names that another deployment (or a leftover) holds.

    Role names are account-wide, so a deployment in another Region with the same suffix finds
    the first one's roles, and the Lambda deployer would reuse them and replace their policies.
    A role is this deployment's only when its PellierWorkshopId tag is its own id.
    """
    holders: list[str] = []
    for role_name in names.roles:
        role = role_if_present(runner, role_name)
        if role is None:
            continue
        tagged = tags_of(role).get(WORKSHOP_ID_TAG)
        if own_workshop_id and tagged == own_workshop_id:
            continue
        detail = f"tagged {WORKSHOP_ID_TAG}={tagged}" if tagged else "not tagged by Pellier"
        holders.append(f"IAM role {role_name} ({detail})")
    return holders


def role_collision_message(holders: list[str]) -> str:
    """What to do about roles another deployment holds; one line, shared by check and deploy."""
    return (
        f"IAM role names are account-wide, not per Region, and these already exist: "
        f"{'; '.join(holders)}. They belong to another Pellier deployment or to leftovers of "
        "one, and deploying under these names would reuse the roles and replace their "
        "policies, which can break that deployment. Pass --deployment-suffix <letters or "
        "digits>, for example --deployment-suffix west, to give this deployment its own role "
        "names, and pass the same value on every later command"
    )


def role_if_present(runner: Runner, role_name: str) -> dict[str, Any] | None:
    """The IAM role with its tags, or None when it does not exist."""
    try:
        response = runner.read(
            f"get role {role_name}", runner.clients.iam.get_role, RoleName=role_name
        )
    except Exception as exc:  # noqa: BLE001 - absence only
        if is_missing(exc):
            return None
        raise
    return response.get("Role") or None


def existing_deployment(runner: Runner, names: Names) -> list[str]:
    """What this account already holds under the names the box would create or update."""
    found: list[str] = []
    if describe_stack(runner, names.agentcore_stack) is not None:
        found.append(f"stack {names.agentcore_stack}")
    prefixes = collision_prefixes(names)
    control = runner.clients.agentcore_control
    for label, call, key, field_name in (
        ("policy engine", control.list_policy_engines, "policyEngines", "policyEngineId"),
        ("gateway", control.list_gateways, "items", "gatewayId"),
        ("memory", control.list_memories, "memories", "id"),
        ("runtime", control.list_agent_runtimes, "agentRuntimes", "agentRuntimeId"),
    ):
        for item in list_all(runner, f"list {label}s", call, key):
            ident = str(item.get(field_name) or "")
            if ident.lower().startswith(prefixes):
                found.append(f"{label} {ident}")
    for function in names.functions:
        try:
            runner.read(
                f"get function {function}",
                runner.clients.lambda_.get_function,
                FunctionName=function,
            )
        except Exception as exc:  # noqa: BLE001 - absence is the good case
            if is_missing(exc):
                continue
            raise
        found.append(f"function {function}")
    return found


def delivery_name(resource_id: str, kind: str) -> str:
    """The provisioner's delivery name: the id's tail is kept when the name is over 60."""
    name = f"{resource_id}-{kind}"
    if len(name) <= DELIVERY_NAME_LIMIT:
        return name
    return f"{resource_id[-(DELIVERY_NAME_LIMIT - len(kind) - 1) :]}-{kind}"


# --------------------------------------------------------------------------- templates


def template_default(text: str, parameter: str) -> str:
    """The Default of one top-level template parameter, as written."""
    match = re.search(
        rf"(?ms)^  {re.escape(parameter)}:\s*$(?:(?!^  \S).)*?^\s+Default:\s*([\"']?)([^\n\"']*)\1",
        text,
    )
    if match is None:
        raise OwnAccountError(f"{parameter} has no Default in the root template")
    return match.group(2).strip()


def infrastructure_revision(templates_dir: Path = TEMPLATE_DIR) -> str:
    """The 16-character digest of the four templates, as the Workshop Studio repo computes it."""
    digest = hashlib.sha256()
    for name in TEMPLATE_FILES:
        text = (templates_dir / name).read_text(encoding="utf-8")
        if name == ROOT_TEMPLATE:
            # The Studio tool's replacement keeps the backslashes before the quotes; the
            # digest must match it, so this does too.
            text, count = INFRASTRUCTURE_DEFAULT_RE.subn(r"\g<1>\"<InfrastructureRevision>\"", text)
            if count != 1:
                raise OwnAccountError("expected one InfrastructureRevision default in the root")
        digest.update(STUDIO_PATHS[name].encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


# --------------------------------------------------------------------------- git


def fetchable_url(url: str) -> str:
    """The URL the box can fetch anonymously: https, no SSH, no embedded credentials."""
    ssh = SSH_URL_RE.match(url)
    if ssh:
        url = f"https://{ssh.group(1)}/{ssh.group(2)}.git"
    if "@" in url.split("://", 1)[-1].split("/", 1)[0]:
        raise OwnAccountError(
            "the repository URL carries credentials; pass --repo-url with the public https URL"
        )
    if not url.startswith("https://"):
        raise OwnAccountError(f"the box fetches over https; {url} is not an https URL")
    return url


def git_identity(
    run: Callable[..., Any],
    repo: Path,
    repo_url: str | None,
    revision: str | None,
    out: Callable[[str], None],
) -> tuple[str, str]:
    """The URL and commit the box will fetch; refuses a dirty tree or an unfetchable commit."""

    def git(*args: str) -> str:
        result = run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
        if result.returncode:
            raise OwnAccountError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    url = fetchable_url(repo_url or git("remote", "get-url", "origin"))
    sha = git("rev-parse", f"{revision or 'HEAD'}^{{commit}}")
    if revision:
        out(
            f"deploying the templates in this working tree with source {sha[:12]} on the box; "
            "they must be the templates that commit ships"
        )
    elif git("status", "--porcelain"):
        raise OwnAccountError(
            "the working tree has uncommitted changes; the box fetches the commit you deploy "
            "from, so commit or stash them first"
        )
    probe = run(
        ["git", "-C", str(repo), "fetch", "--quiet", url, sha],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode:
        raise OwnAccountError(
            f"commit {sha[:12]} cannot be fetched from {url}, so the box could not either; "
            "push it first"
        )
    return url, sha


# --------------------------------------------------------------------------- bucket


def bucket_name(account: str, region: str) -> str:
    return f"pellier-own-account-{account}-{region}"


def normalise_prefix(prefix: str) -> str:
    prefix = prefix.strip("/")
    return f"{prefix}/" if prefix else ""


def tls_only_policy(bucket: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "TLSOnly",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            ],
        }
    )


def bucket_is_ours(runner: Runner, bucket: str) -> bool:
    """True when the bucket carries the tag the deploy puts on the buckets it creates."""
    try:
        tags = runner.read(
            f"get tags of {bucket}", runner.clients.s3.get_bucket_tagging, Bucket=bucket
        )
    except Exception as exc:  # noqa: BLE001 - no tag set means not ours
        if is_missing(exc):
            return False
        raise
    return any(
        tag.get("Key") == BUCKET_TAG[0] and tag.get("Value") == BUCKET_TAG[1]
        for tag in tags.get("TagSet", [])
    )


def ensure_bucket(runner: Runner, bucket: str, region: str) -> None:
    """Create the private bucket in the stack's Region, or reuse one this deploy created."""
    s3 = runner.clients.s3
    try:
        runner.read(f"head bucket {bucket}", s3.head_bucket, Bucket=bucket)
    except Exception as exc:  # noqa: BLE001 - anything but absence is a refusal
        if error_code(exc) in ("301", "PermanentRedirect"):
            raise OwnAccountError(
                f"bucket {bucket} exists in another Region; pass --bucket with another name"
            ) from exc
        if not is_missing(exc):
            raise OwnAccountError(f"cannot use bucket {bucket}: {exc}") from exc
    else:
        if not bucket_is_ours(runner, bucket):
            raise OwnAccountError(
                f"bucket {bucket} exists but was not created by this script; pass --bucket "
                "with another name"
            )
        runner.out(f"bucket {bucket} exists; reusing it")
        return
    create: dict[str, Any] = {"Bucket": bucket}
    if region != "us-east-1":
        create["CreateBucketConfiguration"] = {"LocationConstraint": region}
    runner.write(f"create bucket {bucket} in {region}", s3.create_bucket, **create)
    runner.write(
        f"tag {bucket} {BUCKET_TAG[0]}={BUCKET_TAG[1]}",
        s3.put_bucket_tagging,
        Bucket=bucket,
        Tagging={"TagSet": [{"Key": BUCKET_TAG[0], "Value": BUCKET_TAG[1]}]},
    )
    runner.write(
        f"block public access on {bucket}",
        s3.put_public_access_block,
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    runner.write(
        f"encrypt {bucket} with SSE-S3",
        s3.put_bucket_encryption,
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    runner.write(
        f"require TLS on {bucket}",
        s3.put_bucket_policy,
        Bucket=bucket,
        Policy=tls_only_policy(bucket),
    )


def upload_templates(
    runner: Runner, templates_dir: Path, bucket: str, prefix: str
) -> dict[str, str]:
    """Upload the four templates under the prefix; returns each key's sha256."""
    digests: dict[str, str] = {}
    for name in TEMPLATE_FILES:
        body = (templates_dir / name).read_bytes()
        key = f"{prefix}{name}"
        runner.write(
            f"put s3://{bucket}/{key}",
            runner.clients.s3.put_object,
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/x-yaml",
        )
        digests[key] = hashlib.sha256(body).hexdigest()
    return digests


def empty_and_delete_bucket(runner: Runner, bucket: str) -> None:
    """Delete every version and delete marker, then the bucket; refuses a bucket not ours."""
    s3 = runner.clients.s3
    try:
        ours = bucket_is_ours(runner, bucket)
    except Exception as exc:  # noqa: BLE001
        if is_missing(exc):
            runner.out(f"bucket {bucket} is already gone")
            return
        raise
    if not ours:
        raise OwnAccountError(
            f"bucket {bucket} was not created by this script, so it stays; delete it yourself"
        )
    markers: dict[str, str | None] = {}
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, **{k: v for k, v in markers.items() if v}}
        page = runner.read(f"list versions in {bucket}", s3.list_object_versions, **kwargs)
        objects = [
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for group in ("Versions", "DeleteMarkers")
            for item in page.get(group, [])
        ]
        if objects:
            response = runner.write(
                f"delete {len(objects)} object versions from {bucket}",
                s3.delete_objects,
                Bucket=bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            if response and response.get("Errors"):
                first = response["Errors"][0]
                raise OwnAccountError(
                    f"could not delete {first.get('Key')} from {bucket}: {first.get('Message')}"
                )
        if not page.get("IsTruncated"):
            break
        markers = {
            "KeyMarker": page.get("NextKeyMarker"),
            "VersionIdMarker": page.get("NextVersionIdMarker"),
        }
    runner.write(f"delete bucket {bucket}", s3.delete_bucket, Bucket=bucket)


def lake_bucket_left(runner: Runner, workshop_id: str | None) -> str | None:
    """The optional aurora_analytics page's bucket, if its prepare ran and its cleanup did not.

    scripts/aurora_analytics.py creates the bucket outside the stack and carries no ownership
    tag, so the teardown only names it; it never deletes an untagged bucket.
    """
    if not workshop_id:
        return None
    bucket = f"pellier-lake-{workshop_id}"
    try:
        runner.read(f"look for bucket {bucket}", runner.clients.s3.head_bucket, Bucket=bucket)
    except Exception as exc:  # noqa: BLE001
        if is_missing(exc) or error_code(exc) in ("403", "AccessDenied", "Forbidden"):
            return None
        raise
    return (
        f"bucket {bucket} stays: the optional aurora_analytics page created it outside the stack; "
        "empty and delete it in the S3 console"
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def probe_status(url: str) -> int:
    """The HTTP status of an unsigned HEAD, redirects not followed.

    307 means S3's global endpoint has not learned the bucket yet; 403 or 200 means it has.
    """
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, method="HEAD"), timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def wait_for_endpoint(
    runner: Runner,
    bucket: str,
    region: str,
    key: str,
    probe: Callable[[str], int],
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> None:
    """Wait until the Region's S3 endpoint serves the bucket without redirecting.

    The templates name their nested stacks through the regional endpoint, because the global
    one redirected a fresh us-west-2 bucket for more than ten minutes.
    """
    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    if runner.dry_run:
        runner.out(f"[dry-run] would wait until {url} stops redirecting")
        return
    started = now()
    while True:
        status = probe(url)
        if status not in (301, 307):
            return
        if now() - started > GLOBAL_ENDPOINT_WAIT_SECONDS:
            raise OwnAccountError(
                f"{url} still redirects after {GLOBAL_ENDPOINT_WAIT_SECONDS // 60} minutes; "
                "wait a little and run deploy again"
            )
        runner.out(f"  the S3 endpoint answers {status} for the new bucket; waiting")
        sleep(POLL_SECONDS)


# --------------------------------------------------------------------------- stack


def describe_stack(runner: Runner, stack_name: str) -> dict[str, Any] | None:
    """The stack's description, or None when it does not exist."""
    try:
        stacks = runner.read(
            f"describe stack {stack_name}",
            runner.clients.cloudformation.describe_stacks,
            StackName=stack_name,
        )["Stacks"]
    except Exception as exc:  # noqa: BLE001
        if is_missing(exc):
            return None
        raise
    return stacks[0]


def wait_for_stack(
    runner: Runner, stack_name: str, sleep: Callable[[float], None], now: Callable[[], float]
) -> tuple[str, float]:
    """Poll until the stack reaches a terminal state; returns (status, elapsed seconds).

    A rollback is not terminal: the loop waits for ROLLBACK_COMPLETE or ROLLBACK_FAILED, so
    the account is quiet when the command returns.
    """
    cloudformation = runner.clients.cloudformation
    started = now()
    last_event = ""
    while True:
        stack = describe_stack(runner, stack_name)
        if stack is None:
            return "DELETE_COMPLETE", now() - started
        status = stack["StackStatus"]
        try:
            events = runner.read(
                "describe events", cloudformation.describe_stack_events, StackName=stack_name
            ).get("StackEvents", [])
        except Exception as exc:  # noqa: BLE001 - the stack can vanish between the two calls
            if is_missing(exc):
                return "DELETE_COMPLETE", now() - started
            raise
        if events:
            latest = events[0]
            line = f"  {latest.get('LogicalResourceId')}: {latest.get('ResourceStatus')}"
            if line != last_event:
                runner.out(f"{int((now() - started) // 60):3d} min {line}")
                last_event = line
        if status.endswith(("_COMPLETE", "_FAILED")):
            return status, now() - started
        if now() - started > STACK_WAIT_SECONDS:
            raise OwnAccountError(
                f"stack {stack_name} is still {status} after {STACK_WAIT_SECONDS // 3600} hours"
            )
        sleep(POLL_SECONDS)


def first_failure(runner: Runner, stack_name: str, newest: bool = False) -> str:
    """A failed resource's reason, following nested stacks down.

    A create's root cause is the oldest failed event; a delete's is the newest, because the
    stack's history may hold an older failure from its creation.
    """
    cloudformation = runner.clients.cloudformation
    try:
        events = runner.read(
            "describe events", cloudformation.describe_stack_events, StackName=stack_name
        ).get("StackEvents", [])
    except Exception as exc:  # noqa: BLE001
        if is_missing(exc):
            return "the stack is gone"
        raise
    for event in events if newest else reversed(events):
        if str(event.get("ResourceStatus", "")).endswith("_FAILED"):
            reason = event.get("ResourceStatusReason", "")
            nested = event.get("ResourceType") == "AWS::CloudFormation::Stack"
            if nested and event.get("PhysicalResourceId") and "Embedded stack" in reason:
                return f"{event.get('LogicalResourceId')}: " + first_failure(
                    runner, event["PhysicalResourceId"], newest
                )
            return f"{event.get('LogicalResourceId')}: {reason}"
    return "no failed event recorded"


def outputs_of(stack: dict[str, Any]) -> dict[str, str]:
    return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}


def tags_of(resource: dict[str, Any]) -> dict[str, str]:
    """A CloudFormation or IAM resource's tags as a dict; empty when it has none."""
    return {str(tag.get("Key")): str(tag.get("Value")) for tag in resource.get("Tags") or []}


# A deployment id as the root template derives it from the stack id: p plus the UUID's head.
DEPLOYMENT_ID = re.compile(r"p[0-9a-f]{8}")


def workshop_id_of(stack: dict[str, Any]) -> str | None:
    """The WorkshopId the root template derives from the stack id: p plus the UUID's head."""
    match = re.search(r"/([0-9a-f]{8})-[0-9a-f-]+$", str(stack.get("StackId") or ""))
    return f"p{match.group(1)}" if match else None


def parameters_of(stack: dict[str, Any]) -> dict[str, str]:
    return {
        item["ParameterKey"]: item.get("ParameterValue", "") for item in stack.get("Parameters", [])
    }


def render_outputs(outputs: dict[str, str], show_secrets: bool) -> list[str]:
    """One line per output; the staff password and the editor token are masked by default."""
    lines = []
    for key in sorted(outputs):
        value = outputs[key]
        if not show_secrets:
            if key in SECRET_OUTPUTS:
                value = "<masked; --show-secrets prints it>"
            elif key == "CodeEditorURL":
                value = re.sub(r"(tkn=)[^&]+", r"\1<masked; --show-secrets prints it>", value)
        lines.append(f"  {key}: {value}")
    return lines


def format_elapsed(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} min {rest} s"


# --------------------------------------------------------------------------- the box


def find_editor_instance(runner: Runner, stack_name: str) -> tuple[str | None, str]:
    """The Code Editor instance of the nested CodeEditorStack and its state name."""
    cloudformation = runner.clients.cloudformation
    try:
        nested = runner.read(
            "describe CodeEditorStack",
            cloudformation.describe_stack_resource,
            StackName=stack_name,
            LogicalResourceId="CodeEditorStack",
        )["StackResourceDetail"].get("PhysicalResourceId")
        instance_id = (
            runner.read(
                "describe CodeEditorInstance",
                cloudformation.describe_stack_resource,
                StackName=nested,
                LogicalResourceId="CodeEditorInstance",
            )["StackResourceDetail"].get("PhysicalResourceId")
            if nested
            else None
        )
        if not instance_id:
            return None, "absent"
        described = runner.read(
            "describe instance", runner.clients.ec2.describe_instances, InstanceIds=[instance_id]
        )
        return instance_id, described["Reservations"][0]["Instances"][0]["State"]["Name"]
    except Exception as exc:  # noqa: BLE001 - absence only; other errors are real
        if is_missing(exc):
            return None, "absent"
        raise


def created_kms_key(runner: Runner, stack_name: str) -> str | None:
    """The key the CodeEditorStack created, for a stack whose Outputs are gone."""
    cloudformation = runner.clients.cloudformation
    try:
        nested = runner.read(
            "describe CodeEditorStack",
            cloudformation.describe_stack_resource,
            StackName=stack_name,
            LogicalResourceId="CodeEditorStack",
        )["StackResourceDetail"].get("PhysicalResourceId")
        if not nested:
            return None
        key = runner.read(
            f"describe {KMS_KEY_LOGICAL_ID}",
            cloudformation.describe_stack_resource,
            StackName=nested,
            LogicalResourceId=KMS_KEY_LOGICAL_ID,
        )["StackResourceDetail"].get("PhysicalResourceId")
        return key or None
    except Exception as exc:  # noqa: BLE001 - absence only
        if is_missing(exc):
            return None
        raise


def run_on_box(
    runner: Runner,
    instance_id: str,
    command: str,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> tuple[int, str]:
    """Run one shell command on the box as root over SSM; returns (exit code, output)."""
    ssm = runner.clients.ssm
    try:
        sent = runner.write(
            f"ssm run on {instance_id}: {command[:72]}...",
            ssm.send_command,
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [command]},
            Comment="Pellier own-account",
        )
    except Exception as exc:  # noqa: BLE001 - an unmanaged or stopped instance
        return 1, f"SSM could not reach {instance_id}: {exc}"
    if sent is None:
        return 0, ""
    command_id = sent["Command"]["CommandId"]
    deadline = now() + SSM_WAIT_SECONDS
    while now() < deadline:
        sleep(3)
        try:
            result = runner.read(
                "ssm invocation",
                ssm.get_command_invocation,
                CommandId=command_id,
                InstanceId=instance_id,
            )
        except Exception as exc:  # noqa: BLE001 - the invocation appears a moment later
            if "InvocationDoesNotExist" in str(exc):
                continue
            raise
        if result["Status"] not in SSM_RUNNING:
            output = (result.get("StandardOutputContent") or "") + (
                result.get("StandardErrorContent") or ""
            )
            return int(result.get("ResponseCode", 1)), output
    runner.write(
        f"cancel ssm command {command_id}",
        ignore_missing(ssm.cancel_command),
        CommandId=command_id,
    )
    return 1, f"SSM command {command_id} did not finish within {SSM_WAIT_SECONDS} s"


def preserve_receipt(
    runner: Runner, stack_name: str, sleep: Callable[[float], None], now: Callable[[], float]
) -> None:
    """Copy the provisioning receipt out of /tmp on the box, so a later teardown can read it."""
    instance_id, state = find_editor_instance(runner, stack_name)
    if not instance_id or state != "running":
        runner.out("the Code Editor instance is not running; the receipt stays in /tmp")
        return
    code, output = run_on_box(runner, instance_id, PRESERVE_RECEIPT, sleep, now)
    if runner.dry_run:
        return
    if code or "PELLIER_RECEIPT_SAVED" not in output:
        runner.out(
            f"could not copy the receipt to {SAVED_RECEIPT} ({output.strip() or code}); "
            "tear down before the host reboots, since /tmp is memory-backed there"
        )
        return
    runner.out(f"provisioning receipt saved to {SAVED_RECEIPT} on the box")


# --------------------------------------------------------------------------- commands


def account_id(runner: Runner) -> str:
    return runner.read("get caller identity", runner.clients.sts.get_caller_identity)["Account"]


def require_region(region: str) -> None:
    if region not in SUPPORTED_REGIONS:
        raise OwnAccountError(
            f"Region {region} is not supported; the templates run in "
            f"{' and '.join(SUPPORTED_REGIONS)}"
        )


def service_linked_role_exists(runner: Runner) -> bool:
    """Read-only: whether the RDS service-linked role is already in the account."""
    try:
        runner.read(
            f"get role {RDS_SERVICE_LINKED_ROLE_NAME}",
            runner.clients.iam.get_role,
            RoleName=RDS_SERVICE_LINKED_ROLE_NAME,
        )
    except Exception as exc:  # noqa: BLE001 - absence only
        if is_missing(exc):
            return False
        raise
    return True


def ensure_service_linked_role(runner: Runner) -> None:
    """Create the RDS service-linked role when the account has never used RDS."""
    try:
        runner.write(
            f"create service-linked role for {RDS_SERVICE_LINKED_ROLE}",
            runner.clients.iam.create_service_linked_role,
            AWSServiceName=RDS_SERVICE_LINKED_ROLE,
        )
    except Exception as exc:  # noqa: BLE001 - InvalidInput means it already exists
        if error_code(exc) != "InvalidInput":
            raise
        runner.out(f"service-linked role for {RDS_SERVICE_LINKED_ROLE} exists")


def capacity_report(runner: Runner) -> list[tuple[str, bool]]:
    """One line per quota the stack draws on (a VPC, two Elastic IPs), flagged when short."""
    report: list[tuple[str, bool]] = []
    ec2 = runner.clients.ec2
    used = {
        "VPCs": len(runner.read("describe vpcs", ec2.describe_vpcs).get("Vpcs", [])),
        "Elastic IPs": len(
            runner.read("describe addresses", ec2.describe_addresses).get("Addresses", [])
        ),
    }
    for service, code, label, needed in CAPACITY:
        try:
            quota = runner.read(
                f"quota {code}",
                runner.clients.service_quotas.get_service_quota,
                ServiceCode=service,
                QuotaCode=code,
            )["Quota"]["Value"]
        except Exception as exc:  # noqa: BLE001 - a quota the Region does not expose
            if error_code(exc) != "NoSuchResourceException":
                raise
            continue
        if used[label] + needed > quota:
            report.append(
                (
                    f"{label}: {used[label]:g} of {quota:g} in use and the stack needs {needed} "
                    "more; release some or request a quota increase first",
                    True,
                )
            )
        else:
            report.append(
                (f"{label}: {used[label]:g} of {quota:g} in use; the stack needs {needed}", False)
            )
    return report


def capacity_problems(runner: Runner) -> list[str]:
    return [line for line, short in capacity_report(runner) if short]


def shared_trace_groups_needing_changes(runner: Runner) -> list[str]:
    """The account-wide trace groups the host would have to re-encrypt or re-bound."""
    logs = runner.clients.logs
    needing: list[str] = []
    for name in SHARED_TRACE_LOG_GROUPS:
        groups = runner.read(
            f"describe log group {name}", logs.describe_log_groups, logGroupNamePrefix=name
        ).get("logGroups", [])
        group = next((g for g in groups if g.get("logGroupName") == name), None)
        if group is None:
            continue
        changes = []
        if not group.get("kmsKeyId"):
            changes.append("unencrypted")
        if group.get("retentionInDays") != SHARED_TRACE_RETENTION_DAYS:
            changes.append(f"retention {group.get('retentionInDays') or 'unbounded'}")
        if changes:
            needing.append(f"{name} ({', '.join(changes)})")
    return needing


def report_collisions(args: argparse.Namespace, runner: Runner, names: Names) -> bool:
    """Print what the account already holds under these names; True when deploy would refuse."""
    existing = existing_deployment(runner, names)
    for item in existing:
        runner.out(f"already in this account: {item}")
    if existing:
        runner.out(
            "this account already holds a Pellier deployment under these names; pass "
            "--deployment-suffix <letters or digits> to keep the new one apart from it"
        )
    holders = policy_name_holders(runner)
    for item in holders:
        runner.out(f"already in this Region: {item}")
    if holders:
        runner.out(POLICY_COLLISION_ADVICE)
    own_stack = describe_stack(runner, args.stack_name)
    roles = role_holders(runner, names, workshop_id_of(own_stack) if own_stack else None)
    if roles:
        runner.out(role_collision_message(roles))
    return bool(existing or holders or roles)


def cmd_check(args: argparse.Namespace, runner: Runner) -> int:
    """Account, Region, service-linked role, quotas and model listings; all read-only."""
    identity = runner.read("get caller identity", runner.clients.sts.get_caller_identity)
    runner.out(f"account {identity['Account']} as {identity['Arn']} in {args.region}")
    if service_linked_role_exists(runner):
        runner.out(f"service-linked role {RDS_SERVICE_LINKED_ROLE_NAME} exists")
    else:
        runner.out(
            f"service-linked role {RDS_SERVICE_LINKED_ROLE_NAME} is missing; deploy creates it"
        )
    names = Names(args.deployment_suffix)
    collision = report_collisions(args, runner, names)
    for service, code, label in QUOTAS:
        try:
            quota = runner.read(
                f"quota {code}",
                runner.clients.service_quotas.get_service_quota,
                ServiceCode=service,
                QuotaCode=code,
            )["Quota"]["Value"]
        except Exception as exc:  # noqa: BLE001 - a quota the Region does not expose
            if error_code(exc) != "NoSuchResourceException":
                raise
            runner.out(f"quota {label}: not reported in {args.region}")
            continue
        runner.out(f"quota {label}: {quota:g}")
    report = capacity_report(runner)
    for line, _short in report:
        runner.out(f"capacity: {line}")
    problems = [line for line, short in report if short]
    shared = shared_trace_groups_needing_changes(runner)
    for line in shared:
        runner.out(f"shared trace log group: {line}")
    if shared:
        runner.out(
            "the host must encrypt and bound these account-wide groups; deploy needs "
            "--allow-shared-trace-log-changes, and teardown restores their previous settings"
        )
    listed = {
        model["modelId"]
        for model in runner.read(
            "list foundation models", runner.clients.bedrock.list_foundation_models
        )["modelSummaries"]
    }
    missing = [model for model in MODEL_IDS if model not in listed]
    for model in MODEL_IDS:
        state = "listed" if model in listed else "NOT listed in this Region"
        runner.out(f"model {model}: {state}")
    runner.out(
        "a listing is not access: prove invoke access with "
        f"`uv run --with boto3 scripts/check_model_access.py --region {args.region}` "
        "before deploying"
    )
    return 1 if missing or problems or collision else 0


def cmd_publish(
    args: argparse.Namespace,
    runner: Runner,
    probe: Callable[[str], int],
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> tuple[str, str, str]:
    """Create the bucket and upload the templates; returns (bucket, prefix, root template URL)."""
    account = account_id(runner)
    bucket = args.bucket or bucket_name(account, args.region)
    prefix = normalise_prefix(args.prefix)
    ensure_bucket(runner, bucket, args.region)
    for key, digest in upload_templates(runner, args.assets_dir, bucket, prefix).items():
        runner.out(f"  {key} sha256 {digest}")
    wait_for_endpoint(
        runner, bucket, args.region, f"{prefix}{NESTED_TEMPLATES[0]}", probe, sleep, now
    )
    url = f"https://{bucket}.s3.{args.region}.amazonaws.com/{prefix}{ROOT_TEMPLATE}"
    return bucket, prefix, url


def refuse_name_collisions(runner: Runner, names: Names) -> None:
    """Stop before any write when the account holds what this deployment would create."""
    existing = existing_deployment(runner, names)
    if existing:
        raise OwnAccountError(
            "this account already holds a Pellier deployment under the names the box would "
            f"create or update ({', '.join(existing)}); pass --deployment-suffix <letters or "
            "digits> so nothing collides, or remove it first"
        )
    holders = policy_name_holders(runner)
    if holders:
        raise OwnAccountError(
            "AgentCore keeps Cedar policy names unique per account and Region, and this Region "
            f"already has them: {'; '.join(holders)}. {POLICY_COLLISION_ADVICE}"
        )
    roles = role_holders(runner, names)
    if roles:
        raise OwnAccountError(role_collision_message(roles))


def cmd_deploy(
    args: argparse.Namespace,
    runner: Runner,
    run: Callable[..., Any],
    sleep: Callable[[float], None],
    now: Callable[[], float],
    probe: Callable[[str], int],
) -> int:
    repo_url, revision = git_identity(
        run, REPO_ROOT, args.repo_url, args.source_revision, runner.out
    )
    infra = infrastructure_revision(args.assets_dir)
    runner.out(f"deploying {repo_url} at {revision} (infrastructure revision {infra})")
    existing = describe_stack(runner, args.stack_name)
    if existing is not None:
        raise OwnAccountError(
            f"stack {args.stack_name} already exists ({existing['StackStatus']}); run status, "
            "or teardown first"
        )
    refuse_name_collisions(runner, Names(args.deployment_suffix))
    problems = capacity_problems(runner)
    if problems:
        raise OwnAccountError("the stack would exceed a quota: " + "; ".join(problems))
    shared = shared_trace_groups_needing_changes(runner)
    if shared and not args.allow_shared_trace_log_changes:
        raise OwnAccountError(
            "the host would have to change these account-wide trace log groups: "
            f"{'; '.join(shared)}. Pass --allow-shared-trace-log-changes if you authorize "
            "that; the teardown restores their previous settings but cannot re-encrypt what "
            "was written in between"
        )
    ensure_service_linked_role(runner)
    bucket, prefix, template_url = cmd_publish(args, runner, probe, sleep, now)
    parameters = {
        "AssetsBucketName": bucket,
        "AssetsBucketPrefix": prefix,
        "EditorInstanceType": args.instance_type,
        "RepoUrl": repo_url,
        "RepoRevision": revision,
        "InfrastructureRevision": infra,
        "EventName": EVENT_NAME,
        "DeploymentSuffix": args.deployment_suffix,
        "AllowSharedTraceLogChanges": "true" if args.allow_shared_trace_log_changes else "false",
    }
    runner.write(
        f"create stack {args.stack_name}",
        runner.clients.cloudformation.create_stack,
        StackName=args.stack_name,
        TemplateURL=template_url,
        Capabilities=["CAPABILITY_IAM"],
        Parameters=[{"ParameterKey": k, "ParameterValue": v} for k, v in parameters.items()],
        Tags=[{"Key": key, "Value": value} for key, value in STACK_OWNER_TAGS],
        OnFailure="ROLLBACK",
    )
    if runner.dry_run:
        runner.out(f"[dry-run] would wait for {args.stack_name} and print its Outputs")
        return 0
    status, elapsed = wait_for_stack(runner, args.stack_name, sleep, now)
    if status != "CREATE_COMPLETE":
        runner.out(
            f"stack {args.stack_name} ended {status} after {format_elapsed(elapsed)}: "
            f"{first_failure(runner, args.stack_name)}"
        )
        return 1
    runner.out(f"Stack ready in {format_elapsed(elapsed)}")
    preserve_receipt(runner, args.stack_name, sleep, now)
    runner.out("Outputs:")
    stack = describe_stack(runner, args.stack_name) or {}
    for line in render_outputs(outputs_of(stack), args.show_secrets):
        runner.out(line)
    return 0


def cmd_status(args: argparse.Namespace, runner: Runner) -> int:
    stack = describe_stack(runner, args.stack_name)
    if stack is None:
        runner.out(f"stack {args.stack_name} does not exist in {args.region}")
        return 1
    runner.out(f"stack {args.stack_name}: {stack['StackStatus']}")
    for line in render_outputs(outputs_of(stack), args.show_secrets):
        runner.out(line)
    return 0


# --------------------------------------------------------------------------- teardown


@dataclass
class Discovered:
    """What the teardown found before it deletes anything."""

    stack_exists: bool = False
    stack_suffix: str = ""
    stack_problem: str | None = None
    workshop_id: str | None = None
    agentcore_problem: str | None = None
    agentcore_tags: dict[str, str] = field(default_factory=dict)
    instance_id: str | None = None
    instance_state: str = "absent"
    agentcore_stack: str | None = None
    gateway_role: str | None = None
    resource_ids: list[str] = field(default_factory=list)
    runtime_id: str | None = None
    kms_key_arn: str | None = None
    kms_key_is_ours: bool = False
    stack_created: Any = None
    agentcore_stack_created: Any = None


def gateway_role_name(runner: Runner, gateway_id: str) -> str | None:
    """The Gateway's execution role, from the control plane, as the provisioner found it."""
    try:
        gateway = runner.read(
            f"get gateway {gateway_id}",
            runner.clients.agentcore_control.get_gateway,
            gatewayIdentifier=gateway_id,
        )
    except Exception as exc:  # noqa: BLE001
        if is_missing(exc):
            return None
        raise
    role_arn = gateway.get("roleArn") or ""
    return role_arn.rsplit("/", 1)[-1] or None


def stack_ownership_problem(stack_name: str, stack: dict[str, Any]) -> str | None:
    """Why this stack is not a Pellier own-account deployment, or None when it is.

    A stack without the DeploymentSuffix parameter would read as the empty suffix, which is
    also the default suffix, so the parameter must be present and both tags must match.
    """
    tags = tags_of(stack)
    missing = [f"{key}={value}" for key, value in STACK_OWNER_TAGS if tags.get(key) != value]
    if missing:
        return (
            f"stack {stack_name} is not a Pellier own-account deployment: it lacks the tag "
            f"{' and '.join(missing)} that deploy puts on its stack. Check --stack-name"
        )
    if "DeploymentSuffix" not in parameters_of(stack):
        return (
            f"stack {stack_name} is not a Pellier own-account deployment: it has no "
            "DeploymentSuffix parameter. Check --stack-name"
        )
    return None


def agentcore_ownership_problem(
    stack_name: str, tags: dict[str, str], workshop_id: str | None
) -> str | None:
    """Why the AgentCore CDK stack, judged by its tags, is not this deployment's, or None.

    The provisioner tags it Project=pellier and PellierWorkshopId=<the root stack's id>.
    """
    if tags.get(PROJECT_TAG[0]) != PROJECT_TAG[1]:
        return (
            f"stack {stack_name} lacks the tag {PROJECT_TAG[0]}={PROJECT_TAG[1]}, so Pellier "
            "did not create it"
        )
    tagged = tags.get(WORKSHOP_ID_TAG)
    if workshop_id and not tagged:
        return (
            f"stack {stack_name} has no {WORKSHOP_ID_TAG} tag, so it cannot be shown to be "
            f"deployment {workshop_id}'s; remove it yourself if it is yours, then rerun"
        )
    if workshop_id and tagged != workshop_id:
        return f"stack {stack_name} belongs to deployment {tagged}, not {workshop_id}"
    return None


def discover(runner: Runner, stack_name: str, names: Names) -> Discovered:
    """Find everything the teardown will delete, before it deletes anything."""
    found = Discovered()
    stack = describe_stack(runner, stack_name)
    if stack is not None:
        found.stack_exists = True
        found.stack_suffix = parameters_of(stack).get("DeploymentSuffix", "")
        found.stack_problem = stack_ownership_problem(stack_name, stack)
        found.workshop_id = workshop_id_of(stack)
        found.instance_id, found.instance_state = find_editor_instance(runner, stack_name)
        found.kms_key_arn = outputs_of(stack).get("AgentCoreRuntimeLogKmsKeyArn")
        found.kms_key_is_ours = not parameters_of(stack).get("ExistingRuntimeLogKmsKeyArn")
        if not found.kms_key_arn and found.kms_key_is_ours:
            found.kms_key_arn = created_kms_key(runner, stack_name)
        found.stack_created = stack.get("CreationTime")
    cloudformation = runner.clients.cloudformation
    try:
        resources = runner.read(
            f"describe resources of {names.agentcore_stack}",
            cloudformation.describe_stack_resources,
            StackName=names.agentcore_stack,
        )["StackResources"]
        found.agentcore_stack = names.agentcore_stack
        agentcore = describe_stack(runner, names.agentcore_stack) or {}
        found.agentcore_stack_created = agentcore.get("CreationTime")
        found.agentcore_tags = tags_of(agentcore)
        found.agentcore_problem = agentcore_ownership_problem(
            names.agentcore_stack, found.agentcore_tags, found.workshop_id
        )
    except Exception as exc:  # noqa: BLE001
        if not is_missing(exc):
            raise
        resources = []
    for resource in resources:
        kind = resource.get("ResourceType", "")
        physical = (resource.get("PhysicalResourceId") or "").rsplit("/", 1)[-1]
        if not physical:
            continue
        if kind == "AWS::BedrockAgentCore::Gateway":
            found.resource_ids.append(physical)
            found.gateway_role = gateway_role_name(runner, physical)
        elif kind == "AWS::BedrockAgentCore::Memory":
            found.resource_ids.append(physical)
        elif kind == "AWS::BedrockAgentCore::Runtime":
            found.runtime_id = physical
    return found


def delete_deliveries(runner: Runner, resource_ids: list[str]) -> None:
    """Delete the log deliveries, sources and destinations the provisioner named after each ID."""
    logs = runner.clients.logs
    source_names = {delivery_name(rid, kind) for rid in resource_ids for kind in DELIVERY_KINDS[:2]}
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"nextToken": token} if token else {}
        page = runner.read("describe deliveries", logs.describe_deliveries, **kwargs)
        for delivery in page.get("deliveries", []):
            if delivery.get("deliverySourceName") in source_names:
                runner.write(
                    f"delete delivery {delivery['id']} ({delivery['deliverySourceName']})",
                    logs.delete_delivery,
                    id=delivery["id"],
                )
        token = page.get("nextToken")
        if not token:
            break
    for resource_id in resource_ids:
        for kind in DELIVERY_KINDS:
            name = delivery_name(resource_id, kind)
            if kind.endswith("source"):
                runner.write(
                    f"delete delivery source {name}",
                    ignore_missing(logs.delete_delivery_source),
                    name=name,
                )
            else:
                runner.write(
                    f"delete delivery destination {name}",
                    ignore_missing(logs.delete_delivery_destination),
                    name=name,
                )


@dataclass
class RolePlan:
    """Which of the deployment's IAM roles teardown may delete, decided before any write."""

    delete: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    left: list[str] = field(default_factory=list)


def plan_role_deletion(runner: Runner, names: Names, workshop_id: str | None) -> RolePlan:
    """Sort the roles under these names into delete, refuse and leave.

    Role names are account-wide, so a name match proves nothing. A role is deleted only when
    its PellierWorkshopId tag is this deployment's id. A tag naming another deployment stops
    the teardown. A role with no tag, a tag that is not a deployment id, or no known id to
    compare is left in place.
    """
    plan = RolePlan()
    for role_name, policies in names.roles.items():
        role = role_if_present(runner, role_name)
        if role is None:
            continue
        tagged = tags_of(role).get(WORKSHOP_ID_TAG)
        if workshop_id and tagged == workshop_id:
            plan.delete[role_name] = policies
        elif tagged and not DEPLOYMENT_ID.fullmatch(tagged):
            plan.left.append(
                f"IAM role {role_name} stays: it is tagged {WORKSHOP_ID_TAG}={tagged}, which "
                "is not a deployment id, so it cannot be tied to this deployment; delete it "
                "yourself if it is yours"
            )
        elif workshop_id and tagged:
            plan.conflicts.append(
                f"IAM role {role_name} is tagged {WORKSHOP_ID_TAG}={tagged}, so it belongs to "
                f"another deployment, not {workshop_id}"
            )
        elif tagged:
            plan.left.append(
                f"IAM role {role_name} stays: the stack is gone, so its id is unknown and "
                "the role cannot be tied to this deployment; delete it yourself if it is yours"
            )
        else:
            plan.left.append(
                f"IAM role {role_name} stays: it is not tagged {WORKSHOP_ID_TAG}, so it "
                "cannot be tied to this deployment; delete it yourself if it is yours"
            )
    return plan


def delete_lambdas(
    runner: Runner, names: Names, roles: dict[str, dict[str, tuple[str, ...]]]
) -> None:
    lambda_, iam, logs = runner.clients.lambda_, runner.clients.iam, runner.clients.logs
    for function in names.functions:
        runner.write(
            f"delete function {function}",
            ignore_missing(lambda_.delete_function),
            FunctionName=function,
        )
        runner.write(
            f"delete log group /aws/lambda/{function}",
            ignore_missing(logs.delete_log_group),
            logGroupName=f"/aws/lambda/{function}",
        )
    for role, policies in roles.items():
        for inline in policies["inline"]:
            runner.write(
                f"delete inline policy {inline} from {role}",
                ignore_missing(iam.delete_role_policy),
                RoleName=role,
                PolicyName=inline,
            )
        for managed in policies["managed"]:
            runner.write(
                f"detach {managed.rsplit('/', 1)[-1]} from {role}",
                ignore_missing(iam.detach_role_policy),
                RoleName=role,
                PolicyArn=managed,
            )
        runner.write(f"delete role {role}", ignore_missing(iam.delete_role), RoleName=role)


def delete_stack_and_wait(
    runner: Runner, stack_name: str, sleep: Callable[[float], None], now: Callable[[], float]
) -> float:
    runner.write(
        f"delete stack {stack_name}",
        runner.clients.cloudformation.delete_stack,
        StackName=stack_name,
    )
    if runner.dry_run:
        return 0.0
    status, elapsed = wait_for_stack(runner, stack_name, sleep, now)
    if status != "DELETE_COMPLETE":
        raise OwnAccountError(
            f"stack {stack_name} ended {status}: {first_failure(runner, stack_name, newest=True)}"
        )
    return elapsed


def box_cleanup(
    args: argparse.Namespace,
    runner: Runner,
    found: Discovered,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> tuple[bool, str]:
    """Restore the account-wide settings from the receipt on the box.

    Returns (restored, reason). Nothing needs restoring when the box never created the
    AgentCore stack, because the provisioner changes the account-wide settings in that same
    run.
    """
    if not found.agentcore_stack:
        return True, ""
    if not found.stack_exists:
        return False, "the workshop stack is already gone, so its box could not restore them"
    if found.instance_state != "running" or not found.instance_id:
        return False, (
            f"the Code Editor instance is {found.instance_state}; start it and rerun, or pass "
            "--force to delete without restoring the account-wide X-Ray settings"
        )
    command = OBSERVABILITY_TEARDOWN.format(region=args.region)
    code, output = run_on_box(runner, found.instance_id, command, sleep, now)
    if output.strip():
        runner.out(output.rstrip())
    if runner.dry_run:
        runner.out("[dry-run] the box's observability teardown was not run, so nothing is proven")
        return True, ""
    if code == RECEIPT_MISSING_CODE or RECEIPT_MISSING in output:
        return False, (
            f"the box has no provisioning receipt at {SAVED_RECEIPT} or {TMP_RECEIPT}, so the "
            "account-wide X-Ray settings cannot be restored from it; pass --force to delete "
            "anyway and restore them by hand (see the guide)"
        )
    if code:
        return False, (
            f"the box's observability teardown exited {code}; fix it and rerun, or pass --force "
            "to delete without restoring the account-wide X-Ray settings"
        )
    return True, ""


def state_file(args: argparse.Namespace) -> Path:
    """Where teardown keeps what it must remember once the stack is gone."""
    directory = Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR
    return directory / f"teardown-{args.stack_name}-{args.region}.json"


def load_state(args: argparse.Namespace) -> dict[str, Any] | None:
    """The record an earlier teardown left for this stack and Region, or None."""
    path = state_file(args)
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or any(key not in state for key in STATE_FIELDS):
            raise ValueError("a required field is missing")
    except (OSError, ValueError) as exc:
        raise OwnAccountError(
            f"cannot read the teardown record {path}: {exc}; delete the file, then rerun with "
            "--force to remove leftovers by name"
        ) from exc
    return state


def save_state(args: argparse.Namespace, found: Discovered, restored: bool) -> None:
    """Record the identifiers a rerun needs, before the stack that holds them is deleted."""
    path = state_file(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "stack_name": args.stack_name,
        "region": args.region,
        "deployment_suffix": args.deployment_suffix,
        "workshop_id": found.workshop_id,
        "kms_key_arn": found.kms_key_arn,
        "kms_key_is_ours": found.kms_key_is_ours,
        "restored": restored,
    }
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def adopt_state(args: argparse.Namespace, found: Discovered, state: dict[str, Any]) -> None:
    """Fill what the missing stack would have said from the earlier teardown's record."""
    if state["deployment_suffix"] != args.deployment_suffix:
        raise OwnAccountError(
            f"the teardown record {state_file(args)} was made for deployment suffix "
            f"{state['deployment_suffix']!r}; pass --deployment-suffix "
            f"{state['deployment_suffix']!r}"
        )
    found.workshop_id = state["workshop_id"]
    found.kms_key_arn = state["kms_key_arn"]
    found.kms_key_is_ours = bool(state["kms_key_is_ours"])
    if found.agentcore_stack:
        found.agentcore_problem = agentcore_ownership_problem(
            found.agentcore_stack, found.agentcore_tags, found.workshop_id
        )


def recovery_command(args: argparse.Namespace, kms_pending: bool, bucket_pending: bool) -> str:
    """The exact command that finishes what this run kept; it works once the stack is gone."""
    parts = ["uv", "run", "deploy/own-account/deploy.py", "teardown", "--region", args.region]
    for flag, value, default in (
        ("--profile", args.profile, None),
        ("--stack-name", args.stack_name, DEFAULT_STACK_NAME),
        ("--deployment-suffix", args.deployment_suffix, ""),
        ("--bucket", args.bucket, None),
        ("--state-dir", args.state_dir, None),
    ):
        if value != default:
            parts += [flag, str(value)]
    if kms_pending:
        parts += ["--schedule-kms-key-deletion", str(KMS_WINDOW[0])]
    if bucket_pending:
        parts.append("--delete-bucket")
    return shlex.join(parts)


def refuse_unsafe_teardown(
    args: argparse.Namespace, found: Discovered, names: Names, resumed: bool
) -> None:
    """The refusals that apply before anything is written."""
    if not found.stack_exists and not (args.force or resumed):
        raise OwnAccountError(
            f"no stack {args.stack_name} in {args.region}; check --stack-name, or pass --force "
            f"to remove leftovers by name ({names.agentcore_stack}, the Lambda functions, the "
            "bucket)"
        )
    if found.stack_exists and found.stack_suffix != args.deployment_suffix:
        raise OwnAccountError(
            f"stack {args.stack_name} was deployed with DeploymentSuffix "
            f"{found.stack_suffix!r}; pass --deployment-suffix {found.stack_suffix!r}"
        )
    if (
        found.agentcore_stack
        and found.stack_created
        and found.agentcore_stack_created
        and found.agentcore_stack_created < found.stack_created
    ):
        raise OwnAccountError(
            f"nothing deleted: stack {found.agentcore_stack} was created before "
            f"{args.stack_name}, so this deployment did not create it; it belongs to an earlier "
            "Pellier deployment in this account. Remove it yourself if it is yours, then rerun"
        )


def delete_agentcore(
    runner: Runner,
    found: Discovered,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> None:
    """Delete the deliveries, the Gateway role's inline policy and the AgentCore CDK stack."""
    delete_deliveries(runner, found.resource_ids)
    if found.gateway_role:
        runner.write(
            f"delete inline policy {GATEWAY_INLINE_POLICY} from {found.gateway_role}",
            ignore_missing(runner.clients.iam.delete_role_policy),
            RoleName=found.gateway_role,
            PolicyName=GATEWAY_INLINE_POLICY,
        )
    delete_stack_and_wait(runner, found.agentcore_stack or "", sleep, now)


def delete_agentcore_log_groups(runner: Runner, found: Discovered) -> None:
    groups = []
    if found.runtime_id:
        groups.append(f"/aws/bedrock-agentcore/runtimes/{found.runtime_id}-DEFAULT")
    for resource_id in found.resource_ids:
        groups.append(f"/aws/vendedlogs/bedrock-agentcore/{resource_id}")
        groups.append(f"/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/{resource_id}")
    for group in groups:
        runner.write(
            f"delete log group {group}",
            ignore_missing(runner.clients.logs.delete_log_group),
            logGroupName=group,
        )


def finish_kms_key(
    args: argparse.Namespace, runner: Runner, found: Discovered, restored: bool, left: list[str]
) -> bool:
    """Schedule the retained key's deletion when that is safe; returns True when a rerun could."""
    key = found.kms_key_arn
    if not key:
        return False
    if not found.kms_key_is_ours:
        left.append(f"KMS key {key} was supplied to the stack, not created by it")
    elif not restored:
        left.append(f"KMS key {key} stays: the account-wide log groups may still use it")
    elif not args.schedule_kms_key_deletion:
        left.append(f"the retained KMS key {key} stays until the command below schedules it")
        return True
    else:
        runner.write(
            f"schedule deletion of {key} in {args.schedule_kms_key_deletion} days",
            ignore_pending_deletion(runner.clients.kms.schedule_key_deletion),
            KeyId=key,
            PendingWindowInDays=args.schedule_kms_key_deletion,
        )
    return False


def cmd_teardown(
    args: argparse.Namespace,
    runner: Runner,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> int:
    """Delete what the box created, then the stack, then on request the key and the bucket."""
    names = Names(args.deployment_suffix)
    found = discover(runner, args.stack_name, names)
    saved = None if found.stack_exists else load_state(args)
    if saved is not None:
        adopt_state(args, found, saved)
    problem = found.stack_problem or found.agentcore_problem
    if problem:
        raise OwnAccountError(f"nothing changed: {problem}")
    role_plan = plan_role_deletion(runner, names, found.workshop_id)
    if role_plan.conflicts:
        raise OwnAccountError(f"nothing deleted: {'; '.join(role_plan.conflicts)}")
    refuse_unsafe_teardown(args, found, names, saved is not None)
    left: list[str] = []
    if saved is not None:
        restored = bool(saved["restored"])
        runner.out(f"the stack is gone; finishing the teardown recorded in {state_file(args)}")
    else:
        restored, reason = box_cleanup(args, runner, found, sleep, now)
    if saved is None and not restored:
        if not args.force:
            raise OwnAccountError(f"nothing deleted: {reason}")
        left.append(f"account-wide X-Ray settings and log policies may not be restored: {reason}")
    if not runner.dry_run:
        save_state(args, found, restored)
    if found.agentcore_stack:
        delete_agentcore(runner, found, sleep, now)
    elif saved is None:
        left.append(f"no stack {names.agentcore_stack}: the box never provisioned AgentCore")
    delete_lambdas(runner, names, role_plan.delete)
    left.extend(role_plan.left)
    delete_agentcore_log_groups(runner, found)
    if found.stack_exists:
        elapsed = delete_stack_and_wait(runner, args.stack_name, sleep, now)
        if not runner.dry_run:
            runner.out(f"Stack deleted in {format_elapsed(elapsed)}")
    kms_pending = finish_kms_key(args, runner, found, restored, left)
    left.append(
        f"log group {READINESS_LOG_GROUP} stays: every Pellier deployment in this Region shares it"
    )
    left.append(
        "the CDKToolkit stack and its cdk-hnb659fds-* bucket stay: other CDK apps in the account "
        "may use them"
    )
    lake = lake_bucket_left(runner, found.workshop_id)
    if lake:
        left.append(lake)
    bucket = args.bucket or bucket_name(account_id(runner), args.region)
    if args.delete_bucket:
        empty_and_delete_bucket(runner, bucket)
    else:
        left.append(f"bucket {bucket} stays until the command below removes it")
    pending = kms_pending or not args.delete_bucket
    if pending:
        left.append(f"to finish: {recovery_command(args, kms_pending, not args.delete_bucket)}")
    if not (pending or runner.dry_run):
        state_file(args).unlink(missing_ok=True)
    runner.out("Left in place:")
    for line in left:
        runner.out(f"  {line}")
    return 0


# --------------------------------------------------------------------------- CLI


def deployment_suffix(value: str) -> str:
    if value and not SUFFIX_RE.match(value):
        raise argparse.ArgumentTypeError("a suffix is 1 to 12 lowercase letters or digits")
    return value


def kms_days(value: str) -> int:
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("DAYS must be a whole number") from exc
    if not KMS_WINDOW[0] <= days <= KMS_WINDOW[1]:
        raise argparse.ArgumentTypeError(f"KMS allows {KMS_WINDOW[0]} to {KMS_WINDOW[1]} days")
    return days


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--region", required=True, help=f"one of {', '.join(SUPPORTED_REGIONS)}")
    common.add_argument("--profile", default=None, help="an AWS CLI profile to use")
    common.add_argument("--stack-name", default=DEFAULT_STACK_NAME)
    common.add_argument(
        "--bucket", default=None, help="defaults to pellier-own-account-<account>-<region>"
    )
    common.add_argument("--prefix", default=DEFAULT_PREFIX, help="key prefix, ends with /")
    common.add_argument(
        "--assets-dir", type=Path, default=TEMPLATE_DIR, help="where the four templates are"
    )
    common.add_argument(
        "--show-secrets",
        action="store_true",
        help="print the staff password and the editor token unmasked",
    )
    common.add_argument(
        "--dry-run", action="store_true", help="print every write without making it"
    )
    common.add_argument(
        "--deployment-suffix",
        type=deployment_suffix,
        default="",
        help="1 to 12 lowercase letters or digits that keep this deployment's names apart "
        "from another Pellier deployment in the account; the same value on every command",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", parents=[common], help="account, Region, roles, quotas, models")
    sub.add_parser("publish", parents=[common], help="create the bucket and upload the templates")
    deploy = sub.add_parser("deploy", parents=[common], help="publish, create the stack, wait")
    deploy.add_argument("--repo-url", default=None, help="defaults to the checkout's origin")
    deploy.add_argument(
        "--source-revision",
        default=None,
        help="defaults to HEAD; with a value, the templates still come from this working tree",
    )
    deploy.add_argument("--instance-type", default=DEFAULT_INSTANCE_TYPE)
    deploy.add_argument(
        "--allow-shared-trace-log-changes",
        action="store_true",
        help="let the host re-encrypt and bound the account-wide X-Ray trace log groups",
    )
    sub.add_parser("status", parents=[common], help="stack status and Outputs")
    teardown = sub.add_parser(
        "teardown", parents=[common], help="delete what the box created, then the stack"
    )
    teardown.add_argument("--delete-bucket", action="store_true")
    teardown.add_argument(
        "--state-dir",
        default=None,
        help="where teardown records what a rerun needs once the stack is gone; "
        "defaults to .local/own-account in the repository",
    )
    teardown.add_argument(
        "--schedule-kms-key-deletion",
        type=kms_days,
        default=0,
        metavar="DAYS",
        help="7 to 30; only when the box restored the account-wide settings",
    )
    teardown.add_argument(
        "--force",
        action="store_true",
        help="delete even when the box cannot restore the account-wide X-Ray settings",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    clients: Clients | None = None,
    out: Callable[[str], None] = print,
    run: Callable[..., Any] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    probe: Callable[[str], int] = probe_status,
) -> int:
    """Entry point; tests pass fake clients and clocks."""
    args = parse_args(argv)
    try:
        require_region(args.region)
        runner = Runner(
            clients or Clients.from_session(args.region, args.profile), out, dry_run=args.dry_run
        )
        if args.command == "check":
            return cmd_check(args, runner)
        if args.command == "publish":
            cmd_publish(args, runner, probe, sleep, now)
            return 0
        if args.command == "deploy":
            return cmd_deploy(args, runner, run, sleep, now, probe)
        if args.command == "status":
            return cmd_status(args, runner)
        return cmd_teardown(args, runner, sleep, now)
    except OwnAccountError as exc:
        out(f"refused: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - an AWS error, reported in one line
        out(f"failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
