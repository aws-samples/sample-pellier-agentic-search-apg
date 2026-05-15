#!/usr/bin/env python3
"""
Provision AgentCore Runtime for Builder's Session bootstrap.

Runs ``agentcore configure`` + ``agentcore launch`` from pellier/backend,
then prints the runtime ARN for .env (AGENTCORE_RUNTIME_ENDPOINT).

Best-effort: logs to stderr and exits 0 on failure so bootstrap continues.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REGION = os.environ.get("AWS_REGION", "us-west-2")
REPO = Path(os.environ.get("REPO_PATH", ".")).resolve()
BACKEND = REPO / "pellier" / "backend"
ROLE_NAME = "pellier-agentcore-runtime-execution"
AGENT_NAME = "pellier-agent"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _ensure_execution_role_arn() -> str | None:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        _log("boto3 not available — cannot create execution role")
        return os.environ.get("AGENTCORE_EXECUTION_ROLE_ARN")

    existing = os.environ.get("AGENTCORE_EXECUTION_ROLE_ARN")
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
            AssumeRolePolicyDocument=__import__("json").dumps(trust),
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


def _run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AWS_REGION"] = REGION
    env["AWS_DEFAULT_REGION"] = REGION
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
    combined = f"{stdout}\n{stderr}"
    for pattern in (
        r"(arn:aws:bedrock-agentcore:[^:\s]+:\d+:runtime/[a-zA-Z0-9_-]+)",
        r"(arn:aws[a-z-]*:bedrock-agentcore:[^:\s]+:\d+:runtime/[a-zA-Z0-9_-]+)",
    ):
        m = re.search(pattern, combined)
        if m:
            return m.group(1)
    return None


def main() -> int:
    if not BACKEND.is_dir():
        _log(f"Backend path missing: {BACKEND}")
        return 0

    role_arn = _ensure_execution_role_arn()
    if not role_arn:
        _log("No execution role — skipping AgentCore Runtime pre-launch")
        return 0

    configure = _run(
        [
            "agentcore",
            "configure",
            "--name",
            AGENT_NAME,
            "--entrypoint",
            "agentcore_runtime.py",
            "--requirements-file",
            "requirements.txt",
            "--non-interactive",
            "--region",
            REGION,
            "--execution-role",
            role_arn,
        ],
        BACKEND,
        timeout=120,
    )
    if configure.returncode != 0:
        _log(f"agentcore configure failed: {configure.stderr or configure.stdout}")
        return 0

    launch = _run(
        ["agentcore", "launch", "--agent", AGENT_NAME],
        BACKEND,
        timeout=600,
    )
    if launch.returncode != 0:
        _log(f"agentcore launch failed: {launch.stderr or launch.stdout}")
        return 0

    arn = _parse_runtime_arn(launch.stdout, launch.stderr)
    if arn:
        print(arn)
        return 0

    _log("Launch succeeded but runtime ARN not found in CLI output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
