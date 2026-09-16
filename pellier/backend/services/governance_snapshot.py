"""Read-only, explicitly scoped observations for the Govern reference pages.

Configuration is not a decision. A policy name is not proof that its condition
is correct. This module deliberately never evaluates a policy or invokes a tool.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any

from services import managed_policy

LAB_POLICY_NAME = "workshop_identity_match_forbid"


def observed_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_revision() -> dict[str, Any]:
    """Describe this checkout, separately from any deployed Runtime artifact."""
    root = Path(__file__).resolve().parents[3]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
            text=True, check=True, timeout=2,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True,
            text=True, check=True, timeout=2,
        ).stdout
        return {"revision": revision, "modified": bool(dirty), "source": "checkout"}
    except (OSError, subprocess.SubprocessError):
        return {
            "revision": os.environ.get("WORKSHOP_SOURCE_REVISION") or None,
            "modified": None,
            "source": "deployment-declaration",
        }


def policy_snapshot() -> dict[str, Any]:
    """Read all policy pages and the Gateway attachment, without inferring ALLOW.

    Partial definitions, a failed list, an absent engine and an empty engine are
    distinct states. All AWS reads use the managed-policy client's timeouts.
    """
    from config import settings

    engine_id = managed_policy.policy_engine_id()
    gateway_arn = str(getattr(settings, "AGENTCORE_GATEWAY_ARN", "") or "").strip()
    result: dict[str, Any] = {
        "observedAt": observed_at(),
        "source": "not-configured",
        "engineId": engine_id or None,
        "gatewayMode": None,
        "gatewayState": "not-configured",
        "attachmentMatches": None,
        "policies": [],
        "complete": False,
        "labPolicyState": "unknown",
        "checkout": source_revision(),
    }
    if not engine_id:
        return result

    client = managed_policy._control_client()
    if gateway_arn:
        try:
            gateway = client.get_gateway(
                gatewayIdentifier=gateway_arn.rsplit("/", 1)[-1],
            )
            attachment = gateway.get("policyEngineConfiguration") or {}
            attached_arn = str(attachment.get("arn") or attachment.get("policyEngineArn") or "")
            mode = attachment.get("mode")
            result.update({
                "gatewayMode": mode if mode in ("ENFORCE", "LOG_ONLY") else None,
                "gatewayState": "observed",
                "attachmentMatches": (
                    attached_arn.rsplit("/", 1)[-1] == engine_id
                    if attached_arn else None
                ),
            })
        except Exception:
            result["gatewayState"] = "unavailable"

    policies = []
    complete = True
    try:
        token = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"policyEngineId": engine_id}
            if token:
                params["nextToken"] = token
            page = client.list_policies(**params)
            for summary in page.get("policies", []):
                policy_id = summary["policyId"]
                item = {
                    "id": policy_id,
                    "name": summary.get("name") or policy_id,
                    "description": summary.get("description") or "",
                    "mode": None,
                    "cedar": None,
                    "definitionHash": None,
                    "definitionState": "unavailable",
                }
                try:
                    detail = client.get_policy(policyEngineId=engine_id, policyId=policy_id)
                    cedar = (detail.get("definition") or {}).get("cedar", {}).get("statement")
                    mode = detail.get("enforcementMode")
                    item.update({
                        "name": detail.get("name") or item["name"],
                        "description": detail.get("description") or item["description"],
                        "mode": mode if mode in ("ACTIVE", "LOG_ONLY") else None,
                        "cedar": cedar or None,
                        "definitionHash": hashlib.sha256(cedar.encode()).hexdigest() if cedar else None,
                        "definitionState": "observed" if cedar else "unavailable",
                    })
                    if not cedar or item["mode"] is None:
                        complete = False
                except Exception:
                    complete = False
                policies.append(item)
            token = page.get("nextToken")
            if not token:
                break
            if token in seen_tokens:
                raise RuntimeError("Repeated policy pagination token")
            seen_tokens.add(token)
    except Exception:
        result.update({"source": "unavailable", "policies": policies})
        return result

    result.update({
        "source": "managed-engine",
        "policies": policies,
        "complete": complete,
        # Presence says nothing about the policy's semantics or a request outcome.
        "labPolicyState": (
            "present" if any(p["name"] == LAB_POLICY_NAME for p in policies)
            else "not-observed"
        ),
    })
    return result
