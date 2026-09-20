"""The customer claim comes from the subject map and nothing else.

``scripts/deploy/cognito_customer_claim.py`` is the Cognito pre-token trigger
that stamps ``custom:customer_id`` on shopper access tokens. Cedar binds that
claim to a tool's ``customer_id`` input, so the trigger is part of the
authorization boundary: a claim issued from anything a shopper controls would
let a persona choice become an identity.

``deploy_customer_claim_trigger.py`` attaches it with ``UpdateUserPool``, which
replaces the pool's mutable settings wholesale. The pass-through test guards
the one mistake that silently strips MFA, recovery, or admin-create settings
from a live pool.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DEPLOY / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def trigger(monkeypatch: pytest.MonkeyPatch):
    module = _load("cognito_customer_claim")
    monkeypatch.setenv(
        module.MAP_ENV,
        json.dumps({"sub-marco": "CUST-MARCO", "sub-bad": "not a customer id"}),
    )
    return module


def _event(sub: str, **extra: Any) -> Dict[str, Any]:
    return {
        "triggerSource": "TokenGeneration_Authentication",
        "request": {
            "userAttributes": {"sub": sub, "custom:customer_id": "CUST-FORGED"},
            "clientMetadata": {"customer_id": "CUST-FORGED"},
            **extra,
        },
        "response": {},
    }


def test_mapped_subject_gets_the_claim_on_the_access_token_only(trigger) -> None:
    out = trigger.handler(_event("sub-marco"), None)

    details = out["response"]["claimsAndScopeOverrideDetails"]
    assert details == {
        "accessTokenGeneration": {"claimsToAddOrOverride": {"custom:customer_id": "CUST-MARCO"}}
    }
    assert "idTokenGeneration" not in details


def test_unmapped_subject_gets_no_claim_even_when_the_request_names_one(trigger) -> None:
    out = trigger.handler(_event("sub-unknown"), None)

    assert "claimsAndScopeOverrideDetails" not in out["response"]


def test_malformed_mapping_value_is_refused(trigger) -> None:
    out = trigger.handler(_event("sub-bad"), None)

    assert "claimsAndScopeOverrideDetails" not in out["response"]


def test_missing_or_invalid_map_issues_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load("cognito_customer_claim")
    monkeypatch.setenv(module.MAP_ENV, "{not json")
    assert "claimsAndScopeOverrideDetails" not in module.handler(_event("sub-marco"), None)["response"]
    monkeypatch.delenv(module.MAP_ENV)
    assert "claimsAndScopeOverrideDetails" not in module.handler(_event("sub-marco"), None)["response"]


def test_handler_never_reads_client_metadata_or_user_attributes_for_the_value() -> None:
    source = (DEPLOY / "cognito_customer_claim.py").read_text(encoding="utf-8")
    assert "clientMetadata" not in source.split('"""', 2)[2], "clientMetadata must not reach the handler"
    body = source.split("def handler", 1)[1]
    assert 'attributes.get("sub")' in body
    assert "custom:customer_id" not in body.replace("CLAIM_NAME", "")


def _staff_event(sub: str, groups: list[str]) -> Dict[str, Any]:
    event = _event(sub)
    event["request"]["groupConfiguration"] = {"groupsToOverride": groups}
    return event


def test_operator_group_member_gets_the_staff_scope_and_no_customer(
    trigger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(trigger.STAFF_GROUP_ENV, "pellier-operators")
    monkeypatch.setenv(trigger.STAFF_SCOPE_ENV, "returns")

    out = trigger.handler(_staff_event("sub-operator", ["pellier-operators"]), None)

    claims = out["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"]
    assert claims == {"custom:staff_scope": "returns"}


def test_shopper_outside_the_group_gets_no_staff_scope(trigger, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(trigger.STAFF_GROUP_ENV, "pellier-operators")
    monkeypatch.setenv(trigger.STAFF_SCOPE_ENV, "returns")

    out = trigger.handler(_staff_event("sub-marco", ["shoppers"]), None)

    claims = out["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"]
    assert claims == {"custom:customer_id": "CUST-MARCO"}


def test_staff_scope_needs_both_group_and_scope_configured(trigger, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(trigger.STAFF_GROUP_ENV, raising=False)
    monkeypatch.setenv(trigger.STAFF_SCOPE_ENV, "returns")
    assert "claimsAndScopeOverrideDetails" not in trigger.handler(
        _staff_event("sub-operator", ["pellier-operators"]), None
    )["response"]

    monkeypatch.setenv(trigger.STAFF_GROUP_ENV, "pellier-operators")
    monkeypatch.setenv(trigger.STAFF_SCOPE_ENV, "Not A Scope!")
    assert "claimsAndScopeOverrideDetails" not in trigger.handler(
        _staff_event("sub-operator", ["pellier-operators"]), None
    )["response"]


class _FakeIdp:
    """Enough of cognito-idp to check what UpdateUserPool is told."""

    def __init__(self, pool: Dict[str, Any], members: set[str]) -> None:
        self.pool = pool
        self.updates: list[Dict[str, Any]] = []
        shape = types.SimpleNamespace(members={name: None for name in members})
        op = types.SimpleNamespace(input_shape=shape)
        self.meta = types.SimpleNamespace(
            service_model=types.SimpleNamespace(operation_model=lambda _name: op)
        )

    def describe_user_pool(self, UserPoolId: str) -> Dict[str, Any]:
        return {"UserPool": dict(self.pool)}

    def update_user_pool(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)
        self.pool["LambdaConfig"] = kwargs["LambdaConfig"]


_MEMBERS = {
    "UserPoolId", "PoolName", "Policies", "LambdaConfig", "MfaConfiguration",
    "AdminCreateUserConfig", "AccountRecoverySetting", "UserPoolTier", "DeletionProtection",
}


def _pool(tier: str = "ESSENTIALS") -> Dict[str, Any]:
    return {
        "Id": "us-east-1_test",
        "Name": "pellier-test",
        "Arn": "arn:aws:cognito-idp:us-east-1:1:userpool/us-east-1_test",
        "UserPoolTier": tier,
        "Policies": {"PasswordPolicy": {"MinimumLength": 12, "TemporaryPasswordValidityDays": 7}},
        "MfaConfiguration": "OPTIONAL",
        "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True, "UnusedAccountValidityDays": 7},
        "AccountRecoverySetting": {"RecoveryMechanisms": [{"Priority": 1, "Name": "admin_only"}]},
        "DeletionProtection": "ACTIVE",
        "LambdaConfig": {"PostConfirmation": "arn:aws:lambda:us-east-1:1:function:existing"},
        "SchemaAttributes": [{"Name": "sub"}],
    }


def test_attach_trigger_passes_every_existing_setting_through() -> None:
    deploy = _load("deploy_customer_claim_trigger")
    idp = _FakeIdp(_pool(), _MEMBERS)

    result = deploy.attach_trigger(idp, "us-east-1_test", "arn:aws:lambda:us-east-1:1:function:claim")

    (update,) = idp.updates
    assert update["UserPoolId"] == "us-east-1_test"
    assert update["PoolName"] == "pellier-test"
    assert update["MfaConfiguration"] == "OPTIONAL"
    assert update["AccountRecoverySetting"] == _pool()["AccountRecoverySetting"]
    assert update["DeletionProtection"] == "ACTIVE"
    assert update["UserPoolTier"] == "ESSENTIALS"
    assert update["Policies"] == _pool()["Policies"]
    # The deprecated validity beside the password policy's own is rejected by Cognito.
    assert update["AdminCreateUserConfig"] == {"AllowAdminCreateUserOnly": True}
    # Read-only describe fields never reach the update.
    assert "SchemaAttributes" not in update and "Arn" not in update and "Id" not in update
    # Existing triggers survive; the V2_0 config is merged in, not swapped for V1.
    assert update["LambdaConfig"] == {
        "PostConfirmation": "arn:aws:lambda:us-east-1:1:function:existing",
        "PreTokenGenerationConfig": {
            "LambdaVersion": "V2_0",
            "LambdaArn": "arn:aws:lambda:us-east-1:1:function:claim",
        },
    }
    assert result["PreTokenGenerationConfig"]["LambdaVersion"] == "V2_0"


def test_attach_trigger_refuses_a_lite_pool() -> None:
    deploy = _load("deploy_customer_claim_trigger")
    idp = _FakeIdp(_pool(tier="LITE"), _MEMBERS)

    with pytest.raises(SystemExit, match="ESSENTIALS or PLUS"):
        deploy.attach_trigger(idp, "us-east-1_test", "arn:aws:lambda:us-east-1:1:function:claim")
    assert idp.updates == []


class _Recorder:
    """Records every AWS call the deployer makes, answering just enough."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Dict[str, Any]]] = []
        self.exceptions = types.SimpleNamespace(
            ResourceConflictException=type("ResourceConflictException", (Exception,), {}),
        )

    def __getattr__(self, name: str):
        def call(**kwargs: Any) -> Dict[str, Any]:
            self.calls.append((name, kwargs))
            return {
                "get_role": {"Role": {"Arn": "arn:aws:iam::1:role/pellier-cognito-customer-claim-role"}},
                "get_function": {},
                "get_function_configuration": {"State": "Active", "LastUpdateStatus": "Successful"},
                "update_function_code": {},
                "update_function_configuration": {"FunctionArn": "arn:aws:lambda:us-east-1:1:function:pellier-cognito-customer-claim"},
                "add_permission": {},
                "describe_user_pool": {"UserPool": _pool()},
                "update_user_pool": {},
            }.get(name, {})
        return call


def test_deploy_trigger_updates_the_function_and_attaches_the_v2_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deploy = _load("deploy_customer_claim_trigger")
    recorder = _Recorder()
    monkeypatch.setattr(deploy.boto3, "client", lambda *_a, **_k: recorder)
    monkeypatch.setattr(deploy.time, "sleep", lambda *_a: None)
    recorder_pool = _FakeIdp(_pool(), _MEMBERS)
    monkeypatch.setattr(deploy, "attach_trigger", lambda idp, pool_id, arn: recorder_pool.pool["LambdaConfig"] | {
        "PreTokenGenerationConfig": {"LambdaVersion": "V2_0", "LambdaArn": arn}
    })

    receipt = deploy.deploy_trigger(
        region="us-east-1",
        pool_id="us-east-1_test",
        mapping={"sub-marco": "CUST-MARCO"},
        staff_group="pellier-operators",
        staff_scope="returns",
    )

    names = [name for name, _ in recorder.calls]
    assert "update_function_code" in names and "update_function_configuration" in names
    assert "add_permission" in names
    env = next(kw for name, kw in recorder.calls if name == "update_function_configuration")["Environment"]["Variables"]
    assert json.loads(env["CUSTOMER_CLAIM_MAP"]) == {"sub-marco": "CUST-MARCO"}
    assert env["STAFF_GROUP"] == "pellier-operators" and env["STAFF_SCOPE"] == "returns"
    assert receipt["mappedSubjects"] == 1 and receipt["customers"] == ["CUST-MARCO"]
    assert receipt["lambdaConfig"]["PreTokenGenerationConfig"]["LambdaVersion"] == "V2_0"


@pytest.mark.parametrize("suffix", ["", "rehearsal"])
@pytest.mark.parametrize("exists", [True, False])
def test_trigger_every_resource_call_uses_the_deployment_identity(monkeypatch, suffix, exists):
    from botocore.exceptions import ClientError

    deploy = _load("deploy_customer_claim_trigger")
    # Set after import to cover dotenv loading in the standalone command too.
    monkeypatch.setenv("PELLIER_DEPLOYMENT_SUFFIX", suffix)
    function = f"pellier{'-' + suffix if suffix else ''}-cognito-customer-claim"
    role = f"{function}-role"
    function_arn = f"arn:aws:lambda:us-east-1:123456789012:function:{function}"
    role_arn = f"arn:aws:iam::123456789012:role/{role}"
    calls = []

    class Provider:
        def __getattr__(self, name):
            def call(**kwargs):
                calls.append((name, kwargs))
                if name == "get_role":
                    if not exists:
                        raise ClientError({"Error": {"Code": "NoSuchEntity"}}, "GetRole")
                    return {"Role": {"Arn": role_arn}}
                if name == "create_role":
                    return {"Role": {"Arn": role_arn}}
                if name == "get_function" and not exists:
                    raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetFunction")
                if name == "get_function_configuration":
                    return {"State": "Active", "LastUpdateStatus": "Successful"}
                if name in ("create_function", "update_function_configuration"):
                    return {"FunctionArn": function_arn}
                if name == "describe_user_pool":
                    return {"UserPool": _pool()}
                return {}
            return call

    monkeypatch.setattr(deploy.boto3, "client", lambda *_args, **_kwargs: Provider())
    monkeypatch.setattr(deploy.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(deploy, "attach_trigger", lambda _idp, _pool, arn: {"PreTokenGenerationConfig": {"LambdaArn": arn}})
    receipt = deploy.deploy_trigger(region="us-east-1", pool_id="us-east-1_test", mapping={"new-sub": "CUST-THEO"})
    assert receipt["function"] == function_arn
    assert receipt["role"] == role_arn
    assert all(kwargs["FunctionName"] == function for _, kwargs in calls if "FunctionName" in kwargs)
    assert all(kwargs["RoleName"] == role for _, kwargs in calls if "RoleName" in kwargs)
    permissions = [kwargs for name, kwargs in calls if name == "add_permission"]
    assert permissions[0]["SourceArn"] == _pool()["Arn"]
    configured = next(kwargs for name, kwargs in calls if name in ("create_function", "update_function_configuration"))
    assert json.loads(configured["Environment"]["Variables"]["CUSTOMER_CLAIM_MAP"]) == {"new-sub": "CUST-THEO"}
