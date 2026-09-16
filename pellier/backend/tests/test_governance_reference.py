"""Identity projections and policy observations must never invent authorization."""
import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from routes import governance
from services.cognito_auth import CognitoAuthService, get_cognito_auth_service
from services import governance_snapshot as snapshot


@pytest.fixture
def identity_client():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "reference-test"
    service = CognitoAuthService(pool_id="us-east-1_TEST", region="us-east-1", client_id="web")
    service._fetch_jwks = lambda: {"keys": [jwk]}
    app = FastAPI()
    app.include_router(governance.router)
    app.dependency_overrides[get_cognito_auth_service] = lambda: service

    def token(**overrides):
        claims = {
            "iss": service.issuer, "client_id": "web", "token_use": "access",
            "sub": "private-full-subject", "username": "marco",
            "exp": int(time.time()) + 600, "custom:customer_id": "CUST-MARCO",
            "email": "private-email@example.test", "custom:unrelated": "private-extra-claim",
        }
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "reference-test"})

    with TestClient(app) as client:
        yield client, token, service


def test_anonymous_reference_does_not_claim_validation(identity_client):
    client, _, service = identity_client
    service._fetch_jwks = lambda: pytest.fail("An anonymous observation must not call the IdP")
    response = client.get("/api/observatory/governance/identity")
    assert response.status_code == 200
    assert response.json()["state"] == "anonymous"
    assert response.json()["caller"] is None
    assert response.headers["cache-control"] == "no-store"


def test_validated_claims_are_projected_without_sensitive_payload(identity_client):
    client, token, _ = identity_client
    bearer = token()
    response = client.get("/api/observatory/governance/identity", headers={"Authorization": f"Bearer {bearer}"})
    assert response.status_code == 200
    caller = response.json()["caller"]
    assert caller["customerClaim"] == "CUST-MARCO"
    assert caller["operatorGroup"] is False
    assert caller["tokenUse"] == "access"
    assert len(caller["subjectFingerprint"]) == 12
    for secret in [bearer, "private-full-subject", "private-email@example.test", "private-extra-claim"]:
        assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"token_use": "id"}, {"client_id": "other-app"}, {"iss": "https://untrusted.test"},
])
def test_invalid_tokens_are_not_decoded_into_a_verified_panel(identity_client, claims):
    client, token, _ = identity_client
    response = client.get("/api/observatory/governance/identity", headers={"Authorization": f"Bearer {token(**claims)}"})
    assert response.status_code == 401
    assert "caller" not in response.json()
    assert response.headers["cache-control"] == "no-store"


def test_signature_tampering_does_not_grant_operator_panel(identity_client):
    client, token, _ = identity_client
    claims = jwt.decode(token(), options={"verify_signature": False})
    claims["cognito:groups"] = ["pellier-operators"]
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims, wrong_key, algorithm="RS256", headers={"kid": "reference-test"})
    assert client.get("/api/observatory/governance/identity", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_operator_claims_and_cookie_path(identity_client):
    client, token, _ = identity_client
    client.cookies.set("access_token", token(**{"cognito:groups": ["pellier-operators"], "custom:staff_scope": "returns"}))
    response = client.get("/api/observatory/governance/identity")
    assert response.json()["caller"]["operatorGroup"] is True
    assert response.json()["caller"]["staffScope"] == "returns"


def test_unavailable_identity_is_not_a_policy_denial(identity_client):
    client, token, service = identity_client
    async def unavailable(_request):
        raise RuntimeError("private-provider-details")
    service.extract_user = unavailable
    response = client.get("/api/observatory/governance/identity", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 503
    assert "private-provider-details" not in response.text
    assert "DENY" not in response.text


@pytest.fixture
def control(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_ARN", "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/gw")
    monkeypatch.setattr(snapshot.managed_policy, "policy_engine_id", lambda: "engine")
    monkeypatch.setattr(snapshot, "source_revision", lambda: {"revision": "a" * 40, "modified": False, "source": "checkout"})
    client = SimpleNamespace(
        get_gateway=lambda **_: {"policyEngineConfiguration": {"arn": "arn:aws:bedrock-agentcore:us-east-1:000000000000:policy-engine/engine", "mode": "ENFORCE"}},
        list_policies=lambda **_: {"policies": []},
        get_policy=lambda **_: {"name": "read_catalogue", "enforcementMode": "ACTIVE", "definition": {"cedar": {"statement": "permit(principal, action, resource);"}}},
    )
    monkeypatch.setattr(snapshot.managed_policy, "_control_client", lambda: client)
    return client


def test_snapshot_reads_pagination_and_preserves_each_policy_mode(control):
    def pages(**kwargs):
        if kwargs.get("nextToken"):
            return {"policies": [{"policyId": "second"}]}
        return {"policies": [{"policyId": "first"}], "nextToken": "page-two"}
    control.list_policies = pages
    def details(**kwargs):
        return {
            "name": "workshop_identity_match_forbid" if kwargs["policyId"] == "second" else "read_catalogue",
            "enforcementMode": "LOG_ONLY" if kwargs["policyId"] == "second" else "ACTIVE",
            "definition": {"cedar": {"statement": "forbid(principal, action, resource);"}},
        }
    control.get_policy = details
    data = snapshot.policy_snapshot()
    assert len(data["policies"]) == 2
    assert data["policies"][1]["mode"] == "LOG_ONLY"
    assert data["gatewayMode"] == "ENFORCE"
    assert data["attachmentMatches"] is True
    assert data["labPolicyState"] == "present"
    assert len(data["policies"][1]["definitionHash"]) == 64
    assert "decision" not in data  # Even a deployed forbid is not a request result.


def test_missing_engine_is_distinct_from_empty_engine(control, monkeypatch):
    assert snapshot.policy_snapshot()["source"] == "managed-engine"
    assert snapshot.policy_snapshot()["complete"] is True
    monkeypatch.setattr(snapshot.managed_policy, "policy_engine_id", lambda: "")
    data = snapshot.policy_snapshot()
    assert data["source"] == "not-configured"
    assert data["complete"] is False
    assert data["labPolicyState"] == "unknown"


def test_failed_policy_list_cannot_establish_absence(control):
    def failed(**_):
        raise RuntimeError("private-aws-message")
    control.list_policies = failed
    data = snapshot.policy_snapshot()
    assert data["source"] == "unavailable"
    assert data["labPolicyState"] == "unknown"
    assert "private-aws-message" not in json.dumps(data)


def test_failed_definition_is_preserved_as_partial(control):
    control.list_policies = lambda **_: {"policies": [{"policyId": "one", "name": "read_catalogue"}]}
    def failed(**_):
        raise RuntimeError("unavailable")
    control.get_policy = failed
    data = snapshot.policy_snapshot()
    assert data["source"] == "managed-engine"
    assert data["complete"] is False
    assert data["policies"][0]["cedar"] is None
    assert data["policies"][0]["mode"] is None


@pytest.mark.parametrize("attachment,match,mode", [
    ({"arn": "arn:aws:bedrock-agentcore:us-east-1:000000000000:policy-engine/other", "mode": "ENFORCE"}, False, "ENFORCE"),
    ({"arn": "arn:aws:bedrock-agentcore:us-east-1:000000000000:policy-engine/engine", "mode": "LOG_ONLY"}, True, "LOG_ONLY"),
    ({}, None, None),
])
def test_attachment_mismatch_or_unknown_cannot_be_presented_as_enforcement(control, attachment, match, mode):
    control.get_gateway = lambda **_: {"policyEngineConfiguration": attachment}
    data = snapshot.policy_snapshot()
    assert data["attachmentMatches"] is match
    assert data["gatewayMode"] == mode


def test_gateway_failure_does_not_hide_readable_policies(control):
    def failed(**_):
        raise RuntimeError("unavailable")
    control.get_gateway = failed
    data = snapshot.policy_snapshot()
    assert data["gatewayState"] == "unavailable"
    assert data["gatewayMode"] is None
    assert data["source"] == "managed-engine"


def test_observation_routes_are_read_only_and_policy_errors_are_sanitized(identity_client, monkeypatch):
    client, _, _ = identity_client
    assert client.post("/api/observatory/governance/policies", json={}).status_code == 405
    def failed():
        raise RuntimeError("private control-plane error")
    monkeypatch.setattr(governance, "policy_snapshot", failed)
    response = client.get("/api/observatory/governance/policies")
    assert response.status_code == 503
    assert "private control-plane error" not in response.text
    assert response.headers["cache-control"] == "no-store"
