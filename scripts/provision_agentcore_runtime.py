#!/usr/bin/env python3
"""
DEPRECATED — do not run. Superseded by ``scripts/provision_agentcore_end_to_end.py``.

This script targeted an OLD deploy contract: render flat ``agentcore.json`` /
``aws-targets.json`` files from ``.template`` siblings via env substitution,
then ``npx @aws/agentcore@latest deploy``. That contract no longer exists:

  * The ``.template`` files it rendered have been DELETED (the @aws/agentcore
    0.18 CLI is a stateful, CDK-based project model — create -> add agent ->
    deploy — not a flat-config deploy). So step 2 below would fail outright.
  * Nothing invokes this file. ``bootstrap-labs.sh`` calls
    ``provision_agentcore_end_to_end.py`` (Lambdas + Gateway + Runtime in one
    pass), which contains the live 0.18 ``create -> add -> patch -> deploy``
    logic in ``_deploy_runtime_via_cli``.

Kept only as a historical reference for the IAM execution-role recipe
(``_ensure_execution_role_arn``). For the real deploy path see:
    scripts/provision_agentcore_end_to_end.py  (bootstrap entry)
    scripts/deploy/deploy_all.sh               (manual / documented path)

A hard guard in ``main()`` refuses to run so a stale invocation fails loudly
instead of silently deploying a broken flat config.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REGION = os.environ.get("AWS_REGION", "us-west-2")
REPO = Path(os.environ.get("REPO_PATH", ".")).resolve()
BACKEND = REPO / "pellier" / "backend"
ROLE_NAME = "pellier-agentcore-runtime-execution"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _ensure_execution_role_arn() -> str | None:
    """Return the AgentCore Runtime execution role ARN, creating it if absent.

    The Runtime needs an IAM role with ``bedrock-agentcore.amazonaws.com``
    in its trust policy so AgentCore can assume it when the microVM cold
    starts. We prefer an env-supplied ARN (workshop CFNs typically pass
    one in), but fall back to ``GetRole`` and finally ``CreateRole`` for
    the standalone case.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        # boto3 isn't on the bootstrap path's PYTHONPATH — the AMI
        # bakes it into the workshop venv, but we still want this script
        # to run during early provisioning where it isn't available yet.
        _log("boto3 not available — cannot create execution role")
        return os.environ.get("AGENTCORE_ROLE_ARN") or os.environ.get(
            "AGENTCORE_EXECUTION_ROLE_ARN"
        )

    existing = os.environ.get("AGENTCORE_ROLE_ARN") or os.environ.get(
        "AGENTCORE_EXECUTION_ROLE_ARN"
    )
    if existing:
        return existing

    iam = boto3.client("iam", region_name=REGION)
    try:
        return iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            _log(f"IAM get_role failed: {exc}")
            return None

    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Pellier AgentCore Runtime execution role (Builder's Session)",
        )["Role"]["Arn"]
        for policy_arn in (
            "arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
            "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess",
        ):
            try:
                iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy_arn)
            except ClientError:
                pass
        return role
    except ClientError as exc:
        _log(f"IAM create_role failed (Runtime pre-launch skipped): {exc}")
        return None


def _run(
    cmd: list[str], cwd: Path, env: dict[str, str], timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _parse_runtime_arn(stdout: str, stderr: str) -> str | None:
    """Extract the runtime ARN from `agentcore deploy --json` output.

    The CLI emits a JSON envelope on stdout when ``--json`` is set; the
    exact key varies (``runtimeArn`` / ``agentRuntimeArn`` / ``arn``)
    across CLI versions, so we try a few. As a final fallback we run a
    regex over the combined stream for any ARN with the bedrock-agentcore
    runtime shape — the CLI also prints those in human-readable lines.
    """
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
            if isinstance(runtimes, list) and runtimes:
                for runtime in runtimes:
                    if isinstance(runtime, dict):
                        for key in ("arn", "runtimeArn", "agentRuntimeArn"):
                            if isinstance(runtime.get(key), str):
                                return runtime[key]
    combined = f"{stdout}\n{stderr}"
    m = re.search(
        r"(arn:aws[a-z-]*:bedrock-agentcore:[^:\s]+:\d+:runtime/[a-zA-Z0-9_-]+)",
        combined,
    )
    return m.group(1) if m else None


def _render_templates(role_arn: str) -> bool:
    """Render agentcore.json + aws-targets.json from their templates.

    The Node CLI's "config-as-file" model means every CFN-output value
    has to be substituted into the JSON before ``agentcore deploy`` runs.
    We support the same ``${VAR}`` placeholders ``envsubst(1)`` would
    expand, but in pure Python so the bootstrap doesn't depend on the
    GNU gettext tools being on the AMI's PATH.

    Returns False (and logs why) if a required env var is missing or the
    templates aren't on disk. The caller treats False as "skip pre-launch"
    rather than "fail bootstrap" — Pellier still works without a deployed
    Runtime; the Runtime card just shows ``fixture`` provenance.
    """
    template_pairs = [
        (BACKEND / "agentcore.json.template", BACKEND / "agentcore.json"),
        (BACKEND / "aws-targets.json.template", BACKEND / "aws-targets.json"),
    ]
    for src, _ in template_pairs:
        if not src.is_file():
            _log(f"Template missing: {src}")
            return False

    # Variables consumed by the templates. The Node CLI has no way to
    # pass these via flags, so they MUST be substituted in before deploy.
    # Workshop Studio CFN outputs all of them; outside Workshop Studio
    # they need to be exported by the caller.
    cognito_pool = os.environ.get("COGNITO_POOL", "")
    cognito_client = os.environ.get("COGNITO_CLIENT", "")
    mcp_gateway_url = os.environ.get("MCP_GATEWAY_URL", "")

    # AWS_ACCOUNT goes into aws-targets.json. Fall back to STS
    # GetCallerIdentity (https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)
    # when the env var is unset — a common case during AMI bootstrap.
    aws_account = os.environ.get("AWS_ACCOUNT", "")
    if not aws_account:
        try:
            import boto3

            aws_account = (
                boto3.client("sts", region_name=REGION)
                .get_caller_identity()
                .get("Account", "")
            )
        except Exception as exc:
            _log(f"sts:GetCallerIdentity failed: {exc}")
            return False

    missing = [
        name
        for name, value in (
            ("COGNITO_POOL", cognito_pool),
            ("COGNITO_CLIENT", cognito_client),
            ("MCP_GATEWAY_URL", mcp_gateway_url),
        )
        if not value
    ]
    if missing:
        _log(
            "Skipping Runtime pre-launch — missing env: " + ", ".join(missing)
        )
        return False

    # The full substitution table — every placeholder our templates
    # reference must have a value here, otherwise the rendered JSON
    # carries an empty string and AgentCore rejects the deploy with an
    # error that doesn't point back at the missing env var.
    substitutions = {
        "AGENTCORE_ROLE_ARN": role_arn,
        # Cognito's OIDC issuer URL — the Runtime's JWT authorizer
        # fetches `/.well-known/openid-configuration` from this URL on
        # every cold start to validate incoming Bearer tokens.
        "OAUTH_ISSUER_URL": (
            f"https://cognito-idp.{REGION}.amazonaws.com/{cognito_pool}"
        ),
        "COGNITO_CLIENT": cognito_client,
        "MCP_GATEWAY_URL": mcp_gateway_url,
        "AGENT_MODEL_ID": os.environ.get(
            "AGENT_MODEL_ID", "global.anthropic.claude-opus-4-6-v1"
        ),
        "AWS_ACCOUNT": aws_account,
        "AWS_REGION": REGION,
    }

    # Match ``${VAR}`` placeholders in the templates. We deliberately
    # don't match bare ``$VAR`` (no braces) so a Python expression like
    # ``$base_url`` in a doc string can't accidentally get rewritten.
    pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")

    for src, dst in template_pairs:
        body = src.read_text()
        rendered = pattern.sub(lambda m: substitutions.get(m.group(1), ""), body)
        dst.write_text(rendered)

    return True


def main() -> int:
    """DEPRECATED entrypoint — refuses to run (see module docstring).

    This drove the old flat-template deploy contract, whose ``.template``
    files no longer exist and whose CLI verb (flat ``deploy``) was removed in
    @aws/agentcore 0.18. Running it would render empty configs and fail at the
    AWS call. Fail loudly here instead, and point at the live path.
    """
    sys.stderr.write(
        "provision_agentcore_runtime.py is DEPRECATED and disabled.\n"
        "Use scripts/provision_agentcore_end_to_end.py (bootstrap entry) or\n"
        "scripts/deploy/deploy_all.sh (manual). See the module docstring.\n"
    )
    return 2

    # --- unreachable: retained only as a reference for _ensure_execution_role_arn ---
    if not BACKEND.is_dir():
        _log(f"Backend path missing: {BACKEND}")
        return 0

    # Prefer `npx @aws/agentcore@latest` so every bootstrap run picks up the
    # latest CLI even when a host has an older global install.
    if shutil.which("npx") is None:
        _log("npx not on PATH — install Node.js/npm to run @aws/agentcore CLI")
        return 0

    role_arn = _ensure_execution_role_arn()
    if not role_arn:
        _log("No execution role — skipping AgentCore Runtime pre-launch")
        return 0

    if not _render_templates(role_arn):
        return 0

    # `agentcore deploy` reads the AWS_REGION env var to pick the target
    # region (it's NOT read from aws-targets.json — that file only
    # carries the account id). We pin both AWS_REGION and the legacy
    # AWS_DEFAULT_REGION to be safe.
    env = os.environ.copy()
    env["AWS_REGION"] = REGION
    env["AWS_DEFAULT_REGION"] = REGION

    # Deploy timeout is generous (15 min) because the first deploy
    # against a fresh account can take a while — AgentCore provisions
    # ECR repos, Lambda layers, and warm pools on demand.
    deploy = _run(
        ["npx", "-y", "@aws/agentcore@latest", "deploy", "-y", "--json"],
        BACKEND,
        env=env,
        timeout=900,
    )
    if deploy.returncode != 0:
        _log(f"agentcore deploy failed: {deploy.stderr or deploy.stdout}")
        return 0

    arn = _parse_runtime_arn(deploy.stdout, deploy.stderr)
    if arn:
        print(arn)
        return 0

    _log("Deploy succeeded but runtime ARN not found in CLI output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
