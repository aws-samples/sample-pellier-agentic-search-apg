"""Managed output checks for the staff credit tool. No custom interceptor.

The Lambda returns an MCP content envelope, whose first text block contains
the JSON result (including the free-text credit reason). Keep this path aligned
with pellier_experience_server.lambda_handler. Deployment is not runtime proof.
"""
from __future__ import annotations

import json

POLICY_NAME = "credit_output_sensitive_information"
ACTION = "pellier-concierge-experience-target___issue_credit"
OUTPUT_PATH = "context.output.content[0].text"


def policy(gateway_arn: str) -> dict:
    if not gateway_arn.startswith("arn:") or ":gateway/" not in gateway_arn:
        raise ValueError("A deployed Gateway ARN is required")
    return {
        "name": POLICY_NAME,
        "description": "Suppress credit responses containing email addresses in free-text output",
        "statement": (
            f'suppressOutput (principal, action == AgentCore::Action::"{ACTION}", '
            f'resource == AgentCore::Gateway::"{gateway_arn}")\n'
            "when guardrails {\n"
            f'  BedrockGuardrails::SensitiveInformation(["EMAIL"], [{OUTPUT_PATH}])'
            '["EMAIL"].confidenceScore.greaterThan(decimal("0.2"))\n};'
        ),
        # Guardrail policies use their own service validation, not the standard
        # Cedar analyzer. This matches the AgentCore Guardrails CLI guide.
        "validationMode": "IGNORE_ALL_FINDINGS",
        "enforcementMode": "ACTIVE",
    }


def ensure_permission(control, iam, *, gateway_id: str, region: str) -> dict:
    """Grant only the managed check API on the actual Gateway execution role."""
    gateway = control.get_gateway(gatewayIdentifier=gateway_id)
    role_arn = gateway["roleArn"]
    document = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow", "Action": "bedrock:InvokeGuardrailChecks",
            "Resource": "*",  # This check API does not take a guardrail ARN.
            "Condition": {"StringEquals": {"aws:RequestedRegion": region}},
        }],
    }
    iam.put_role_policy(
        RoleName=role_arn.rsplit("/", 1)[-1],
        PolicyName="PellierManagedOutputChecks",
        PolicyDocument=json.dumps(document),
    )
    return {"policy": POLICY_NAME, "roleArn": role_arn, "runtimeProved": False}
