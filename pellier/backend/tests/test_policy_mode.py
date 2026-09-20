"""Enforcement mode is two switches with two vocabularies.

Verified against the live `bedrock-agentcore-control` API on 2026-08-19:

| Scope              | Operation                                      | Values                |
| ------------------ | ---------------------------------------------- | --------------------- |
| One policy         | `UpdatePolicy.enforcementMode`                 | `ACTIVE`, `LOG_ONLY`  |
| Gateway attachment | `UpdateGateway.policyEngineConfiguration.mode` | `ENFORCE`, `LOG_ONLY` |

`UpdatePolicyEngine` carries no mode; the engine is a container.

The asymmetry is the trap: the "on" value is `ACTIVE` for a policy and
`ENFORCE` for a gateway. Sending `ENFORCE` to `UpdatePolicy` is rejected, and
code that treats them as one vocabulary either errors or believes it enabled
enforcement when it did not. These tests pin the vocabularies apart.

The second trap is `UpdateGateway` being a replace rather than a patch: every
optional field the call omits is dropped, so a mode flip that does not echo the
current configuration back silently removes the authorizer and breaks every
authenticated call.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


def _load_tool():
    module_name = "policy_mode_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "policy_mode.py"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


class _FakeControlPlane:
    """Records calls and models the per-scope vocabularies."""

    def __init__(self, policies: List[Dict[str, Any]], gateway: Dict[str, Any] | None = None):
        self._policies = {p["policyId"]: dict(p) for p in policies}
        self._gateway = dict(gateway) if gateway else None
        self.update_policy_calls: List[Dict[str, Any]] = []
        self.update_gateway_calls: List[Dict[str, Any]] = []

    def list_policies(self, policyEngineId):  # noqa: N803 - boto3 casing
        return {"policies": [dict(p) for p in self._policies.values()]}

    def get_policy(self, policyEngineId, policyId):  # noqa: N803
        return dict(self._policies[policyId])

    def update_policy(self, policyEngineId, policyId, **kwargs):  # noqa: N803
        mode = kwargs.get("enforcementMode")
        if mode not in (None, "ACTIVE", "LOG_ONLY"):
            raise ValueError(f"ValidationException: bad enforcementMode {mode!r}")
        self.update_policy_calls.append({"policyId": policyId, **kwargs})
        if mode:
            self._policies[policyId]["enforcementMode"] = mode
        return dict(self._policies[policyId])

    def get_gateway(self, gatewayIdentifier):  # noqa: N803
        assert self._gateway is not None
        return dict(self._gateway)

    def update_gateway(self, **kwargs):
        self.update_gateway_calls.append(dict(kwargs))
        assert self._gateway is not None
        # Model the replace semantics: anything omitted disappears.
        preserved = {"gatewayId": self._gateway["gatewayId"]}
        self._gateway = {**preserved, **kwargs}
        self._gateway.pop("gatewayIdentifier", None)
        return dict(self._gateway)


def _policy(name: str, mode: str = "ACTIVE", effect: str = "forbid") -> Dict[str, Any]:
    return {
        "policyId": f"{name}-abc123",
        "name": name,
        "enforcementMode": mode,
        "status": "ACTIVE",
        "definition": {"cedar": {"statement": f'{effect}(principal, action, resource);'}},
    }


def test_describe_identifies_general_output_policy_statement():
    policy = _policy("output")
    policy["definition"] = {"policy": {"statement": "suppressOutput(principal, action, resource);"}}
    state = _load_tool().describe(_FakeControlPlane([policy]), "engine", None)
    assert state["policies"][0]["effect"] == "suppressOutput"


def _write_project(tmp_path: Path, *, gateway_mode: str, policy_mode: str) -> Path:
    """Write a minimal AgentCore CLI project to edit."""
    import json

    project = tmp_path / "pellier"
    (project / "agentcore").mkdir(parents=True)
    (project / "agentcore" / "agentcore.json").write_text(
        json.dumps(
            {
                "agentCoreGateways": [
                    {
                        "name": "pellier-gateway",
                        "policyEngineConfiguration": {
                            "policyEngineName": "e",
                            "mode": gateway_mode,
                        },
                    }
                ],
                "policyEngines": [
                    {"name": "e", "policies": [
                        {"name": "gate", "enforcementMode": policy_mode}
                    ]}
                ],
            }
        )
    )
    return project


def _gateway(mode: str = "ENFORCE") -> Dict[str, Any]:
    return {
        "gatewayId": "pellier-gateway-abc",
        "name": "pellier-gateway",
        "roleArn": "arn:aws:iam::1:role/gw",
        "authorizerType": "CUSTOM_JWT",
        "authorizerConfiguration": {"customJWTAuthorizer": {"discoveryUrl": "https://x"}},
        "protocolType": "MCP",
        "protocolConfiguration": {"mcp": {"instructions": "x"}},
        "description": "Pellier gateway",
        "status": "READY",
        "policyEngineConfiguration": {"arn": "arn:aws:...:policy-engine/e", "mode": mode},
    }


# ---------------------------------------------------------------------------
# The two vocabularies are kept apart
# ---------------------------------------------------------------------------


def test_policy_and_gateway_modes_use_different_vocabularies():
    tool = _load_tool()

    assert tool.POLICY_MODES == ("ACTIVE", "LOG_ONLY")
    assert tool.GATEWAY_MODES == ("ENFORCE", "LOG_ONLY")
    # The trap, stated as an assertion: "ENFORCE" is not a policy mode.
    assert "ENFORCE" not in tool.POLICY_MODES
    assert "ACTIVE" not in tool.GATEWAY_MODES


def test_shipped_mode_names_the_right_value_per_scope():
    tool = _load_tool()

    assert tool.SHIPPED_POLICY_MODE == "ACTIVE"
    assert tool.SHIPPED_GATEWAY_MODE == "ENFORCE"


# ---------------------------------------------------------------------------
# Mutation goes through the CLI project, never the SDK
# ---------------------------------------------------------------------------


def test_the_tool_never_mutates_through_the_sdk():
    """The AgentCore CLI project owns resource mutation.

    Calling `UpdatePolicy` or `UpdateGateway` directly would drift the live
    resources away from the declared project, so the next `agentcore deploy`
    would silently undo the change. `UpdateGateway` is also a replace that
    drops omitted fields, which would remove the authorizer.
    """
    tool = _load_tool()
    source = Path(tool.__file__).read_text()

    for forbidden in (".update_policy(", ".update_gateway(", ".create_policy(",
                      ".delete_policy(", ".update_policy_engine("):
        assert forbidden not in source, forbidden


def test_declaring_a_policy_mode_edits_the_project(tmp_path):
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="ENFORCE", policy_mode="ACTIVE")

    changes = tool.declare_modes(project, policy_modes={"gate": "LOG_ONLY"})

    assert changes and "gate" in changes[0]
    assert tool.read_declared_modes(project)["policies"]["gate"] == "LOG_ONLY"
    # The gateway is untouched.
    assert tool.read_declared_modes(project)["gateway_mode"] == "ENFORCE"


def test_declaring_a_gateway_mode_edits_only_the_gateway(tmp_path):
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="ENFORCE", policy_mode="ACTIVE")

    tool.declare_modes(project, gateway_mode="LOG_ONLY")

    declared = tool.read_declared_modes(project)
    assert declared["gateway_mode"] == "LOG_ONLY"
    assert declared["policies"]["gate"] == "ACTIVE"


def test_declaring_an_unchanged_mode_reports_no_changes(tmp_path):
    """No change means no deploy, so the caller can skip it."""
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="ENFORCE", policy_mode="ACTIVE")

    assert tool.declare_modes(project, policy_modes={"gate": "ACTIVE"}) == []


def test_declaring_an_unknown_policy_is_refused(tmp_path):
    """Silently doing nothing would look like success."""
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="ENFORCE", policy_mode="ACTIVE")

    with pytest.raises(ValueError, match="not declared in the CLI project"):
        tool.declare_modes(project, policy_modes={"absent": "LOG_ONLY"})


def test_declared_modes_are_validated_per_scope(tmp_path):
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="ENFORCE", policy_mode="ACTIVE")

    with pytest.raises(ValueError, match="policy mode must be one of"):
        tool.declare_modes(project, policy_modes={"gate": "ENFORCE"})
    with pytest.raises(ValueError, match="gateway mode must be one of"):
        tool.declare_modes(project, gateway_mode="ACTIVE")


def test_live_verification_polls_until_it_agrees(monkeypatch):
    """A successful deploy is not proof; the live resource is re-read."""
    tool = _load_tool()
    monkeypatch.setattr(tool.time, "sleep", lambda _s: None)

    reads = {"n": 0}

    class _Lagging(_FakeControlPlane):
        def list_policies(self, policyEngineId):  # noqa: N803
            reads["n"] += 1
            mode = "ACTIVE" if reads["n"] < 3 else "LOG_ONLY"
            return {"policies": [_policy("gate", mode=mode)]}

    client = _Lagging([_policy("gate")])

    assert tool.verify_live(client, "engine", None, policy_modes={"gate": "LOG_ONLY"}) == []


def test_live_verification_reports_a_mismatch(monkeypatch):
    tool = _load_tool()
    monkeypatch.setattr(tool.time, "sleep", lambda _s: None)
    client = _FakeControlPlane([_policy("gate", mode="ACTIVE")])

    problems = tool.verify_live(
        client, "engine", None, policy_modes={"gate": "LOG_ONLY"}
    )

    assert problems and "gate" in problems[0]


# ---------------------------------------------------------------------------
# Reading state
# ---------------------------------------------------------------------------


def test_describe_reports_both_scopes():
    tool = _load_tool()
    client = _FakeControlPlane(
        [_policy("gate", mode="LOG_ONLY", effect="forbid")], _gateway("ENFORCE")
    )

    state = tool.describe(client, "engine", "pellier-gateway-abc")

    assert state["gateway"]["mode"] == "ENFORCE"
    assert state["policies"][0]["enforcement_mode"] == "LOG_ONLY"


def test_forbid_and_permit_are_distinguished():
    """Only a forbid policy's mode changes an outcome."""
    tool = _load_tool()
    client = _FakeControlPlane(
        [_policy("gate", effect="forbid"), _policy("base", effect="permit")]
    )

    effects = {
        p["name"]: p["effect"] for p in tool.describe(client, "engine", None)["policies"]
    }

    assert effects == {"gate": "forbid", "base": "permit"}


def test_gateway_id_is_derived_from_the_arn():
    tool = _load_tool()

    assert (
        tool.gateway_id_from_arn(
            "arn:aws:bedrock-agentcore:us-east-1:1:gateway/pellier-gateway-abc"
        )
        == "pellier-gateway-abc"
    )
    assert tool.gateway_id_from_arn("pellier-gateway-abc") == "pellier-gateway-abc"


# ---------------------------------------------------------------------------
# Restoring the shipped mode
# ---------------------------------------------------------------------------


def test_restore_shipped_declares_the_shipped_values(tmp_path, monkeypatch):
    tool = _load_tool()
    monkeypatch.setattr(tool.time, "sleep", lambda _s: None)
    project = _write_project(tmp_path, gateway_mode="LOG_ONLY", policy_mode="LOG_ONLY")
    deployed = {"count": 0}
    monkeypatch.setattr(tool, "deploy", lambda _p: (deployed.__setitem__("count", 1), (0, "")) [1])
    monkeypatch.setattr(tool, "verify_live", lambda *a, **kw: [])

    assert tool._restore_shipped(project, object(), "engine", "gw") == 0

    declared = tool.read_declared_modes(project)
    assert declared["gateway_mode"] == "ENFORCE"
    assert declared["policies"]["gate"] == "ACTIVE"
    assert deployed["count"] == 1, "a drifted project must be deployed"


def test_restore_shipped_skips_the_deploy_when_nothing_drifted(tmp_path, monkeypatch):
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="ENFORCE", policy_mode="ACTIVE")
    deployed = {"count": 0}
    monkeypatch.setattr(tool, "deploy", lambda _p: (deployed.__setitem__("count", 1), (0, ""))[1])
    monkeypatch.setattr(tool, "verify_live", lambda *a, **kw: [])

    assert tool._restore_shipped(project, object(), "engine", "gw") == 0
    assert deployed["count"] == 0, "no drift means no deploy"


def test_a_failed_deploy_is_reported(tmp_path, monkeypatch):
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="LOG_ONLY", policy_mode="ACTIVE")
    monkeypatch.setattr(tool, "deploy", lambda _p: (1, "boom"))

    assert tool._apply(project, object(), "engine", "gw", gateway_mode="ENFORCE") == 1


def test_live_mismatch_after_deploy_is_a_failure(tmp_path, monkeypatch):
    """Declared and deployed is not the same as live and converged."""
    tool = _load_tool()
    project = _write_project(tmp_path, gateway_mode="LOG_ONLY", policy_mode="ACTIVE")
    monkeypatch.setattr(tool, "deploy", lambda _p: (0, ""))
    monkeypatch.setattr(tool, "verify_live", lambda *a, **kw: ["gateway: live='LOG_ONLY'"])

    assert tool._apply(project, object(), "engine", "gw", gateway_mode="ENFORCE") == 1
