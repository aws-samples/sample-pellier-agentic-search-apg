"""Tests for the Observatory Proof Board and readiness API."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import observatory
from routes.observatory import router as observatory_router


def test_observatory_has_no_fixture_loader() -> None:
    """Participant surfaces must fail visibly rather than read local fixtures."""
    assert not hasattr(observatory, "_load_fixture")


class _ProofDB:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch_all(self, query: str, *params: Any) -> list[dict]:
        """A fully provisioned stack, which is what the ready-status test asserts.

        The evidence-substrate readiness check reads `information_schema` and
        `pg_indexes`. A fake that answered nothing reported `warn`, and this test's
        "ready" assertion turned into "attention" — correctly, because the fake stack
        was missing the tables an evidence reconstruction depends on.
        """
        self.calls.append((query, params))
        if "pg_indexes" in query:
            return [{"indexname": "operator_episodes_outcome_idx"}]
        if "information_schema.tables" in query:
            # The retired span table is deliberately absent, which is what the
            # substrate check requires. Named only in the migration that removes it
            # and the test that asserts it, per the repository naming contract.
            return [
                {"table_name": "execution_receipts"},
                {"table_name": "operator_episodes"},
                {"table_name": "observatory_spans"},
                {"table_name": "model_invocation_receipts"},
                {"table_name": "evidence_ledger_event_refs"},
            ]
        return []

    async def fetch_one(self, query: str, *params: Any) -> dict | None:
        self.calls.append((query, params))
        if "catalog_count" in query:
            return {
                "catalog_count": 60,
                "warehouse_count": 180,
                "audit_count": 7,
            }
        if "FROM pellier.governed_receipts" in query:
            return {
                "receipt_id": 505,
                "audit_id": 303,
                "session_id": "gateway-marco-for-theo-incident",
                "principal_id": "CUST-MARCO",
                "principal_label": "Marco (Cognito JWT)",
                "tool": "initiate_return",
                "caller": "gateway",
                "decision": "ALLOW",
                "args": {
                    "customer_id": "theo",
                    "product_id": "37",
                    "reason": "damaged",
                    "idempotency_key": "operator-review:8:aaaaaaaa",
                },
                "policy_engine_id": "policy-1",
                "policy_name": "initiate_return_damaged_only",
                "created_at": None,
            }
        if "FROM pellier.write_operations" in query:
            return {
                "idempotency_key": "operator-review:8:aaaaaaaa",
                "operation": "initiate_return",
                "request_hash": "b" * 64,
                "created_at": None,
                "completed_at": "2026-08-29T12:00:00+00:00",
                "result": {"return_id": 77},
            }
        if "FROM pellier.tool_audit" not in query:
            return None
        if "ta.audit_id = %s" in query:
            return {
                "audit_id": 303,
                "session_id": "managed-proof",
                "tool": "initiate_return",
                "caller": "gateway",
                "args": {
                    "customer_id": "theo",
                    "product_id": "37",
                    "reason": "damaged",
                    "idempotency_key": "operator-review:8:aaaaaaaa",
                },
                "result": {"status": "success"},
                "latency_ms": 55,
                "created_at": None,
            }
        if "check_inventory" in params:
            return {
                "audit_id": 101,
                "session_id": "marco-proof",
                "tool": "check_inventory",
                "caller": "agent",
                "args": {"query": "Kyoto Linen Overshirt"},
                "result": {"quantity": 20},
                "latency_ms": 42,
                "created_at": None,
            }
        if "initiate_return" in params:
            return {
                "audit_id": 202,
                "session_id": "theo-proof",
                "tool": "initiate_return",
                "caller": "agent",
                "args": {"reason": "damaged"},
                "result": {"status": "accepted"},
                "latency_ms": 81,
                "created_at": None,
            }
        if "gateway" in params:
            return {
                "audit_id": 303,
                "session_id": "managed-proof",
                "tool": "check_inventory",
                "caller": "gateway",
                "args": {},
                "result": {},
                "latency_ms": 55,
                "created_at": None,
            }
        return {
            "audit_id": 404,
            "session_id": "latest",
            "tool": "check_inventory",
            "caller": "agent",
            "args": {},
            "result": {},
            "latency_ms": 11,
            "created_at": None,
        }


class _DenyProofDB(_ProofDB):
    async def fetch_one(self, query: str, *params: Any) -> dict | None:
        if (
            "FROM pellier.governed_receipts" in query
            and "gateway-identity-mismatch-proof" in params
        ):
            return {
                "receipt_id": 606,
                "audit_id": None,
                "session_id": "gateway-identity-mismatch-proof",
                "principal_id": "CUST-MARCO",
                "principal_label": "Marco (Cognito JWT)",
                "tool": "initiate_return",
                "caller": "gateway",
                "decision": "DENY",
                "args": {
                    "customer_id": "theo",
                    "product_id": 37,
                    "reason": "damaged",
                    "idempotency_key": self.declared_key,
                    "absence_verified": True,
                },
                "policy_engine_id": "policy-1",
                "policy_name": "workshop_identity_match_forbid",
                "created_at": None,
            }
        if "AS execution_rows" in query:
            self.absence_searches.append(params)
            return dict(self.absence_counts)
        return await super().fetch_one(query, *params)

    # The DENY receipt's own declared key; ``None`` models a receipt that
    # declared nothing searchable.
    declared_key: str | None = "workshop-attempt:theo:37"
    absence_counts: dict = {
        "execution_rows": 0,
        "write_rows": 0,
        "completed_writes": 0,
        "ledger_rows": 0,
    }

    def __init__(self) -> None:
        super().__init__()
        self.absence_searches: list = []


def _client(stub_db: _ProofDB) -> TestClient:
    import app as app_module

    app_module.db_service = stub_db  # type: ignore[attr-defined]
    fast = FastAPI()
    fast.include_router(observatory_router)
    fast.dependency_overrides[observatory.get_current_user] = lambda: {
        "sub": "CUST-MARCO",
        "username": "marco",
        "access_token": "jwt",
    }

    @fast.get("/api/observatory/readiness")
    async def _readiness_probe() -> dict[str, Any]:
        return await observatory._collect_readiness()

    return TestClient(fast)


def _configure_managed(monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
    monkeypatch.setattr(settings, "COGNITO_POOL_ID", "pool-1", raising=False)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "client-1", raising=False)
    monkeypatch.setattr(settings, "COGNITO_DOMAIN", "auth.example.com", raising=False)
    monkeypatch.setattr(settings, "COGNITO_TEST_CREDENTIALS_SECRET_ARN", "secret-1", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_MEMORY_ID", "mem-1", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_RUNTIME_ENDPOINT", "runtime-arn", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "https://gateway.example/mcp", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "policy-1", raising=False)


def test_readiness_reports_live_pillars(monkeypatch) -> None:
    _configure_managed(monkeypatch)
    client = _client(_ProofDB())

    r = client.get("/api/observatory/readiness")
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "ready"
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["aurora"]["state"] == "pass"
    assert checks["identity"]["state"] == "pass"
    assert checks["runtime"]["state"] == "pass"
    assert checks["gateway"]["state"] == "pass"
    assert checks["policy"]["state"] == "pass"
    assert body["counts"]["catalog_count"] == 60


def test_governed_readiness_fails_without_managed_policy(monkeypatch) -> None:
    _configure_managed(monkeypatch)
    from config import settings

    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "", raising=False)
    client = _client(_ProofDB())

    body = client.get("/api/observatory/readiness").json()

    assert body["status"] == "not_ready"
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["policy"]["required"] is True
    assert checks["policy"]["state"] == "fail"


def test_governed_readiness_requires_exact_warehouse_seed(monkeypatch) -> None:
    class _WrongWarehouseCountDB(_ProofDB):
        async def fetch_one(self, query: str, *params: Any) -> dict | None:
            if "catalog_count" in query:
                return {
                    "catalog_count": 60,
                    "warehouse_count": 179,
                    "audit_count": 7,
                }
            return await super().fetch_one(query, *params)

    _configure_managed(monkeypatch)
    client = _client(_WrongWarehouseCountDB())

    body = client.get("/api/observatory/readiness").json()

    assert body["status"] == "not_ready"
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["aurora"]["state"] == "fail"
    assert "expected exactly 180" in checks["aurora"]["detail"]


def test_identity_boundary_requires_an_operator_and_allows_the_operator(monkeypatch) -> None:
    """Cross-principal receipt material is never a public Observatory feed."""
    fast = FastAPI()
    fast.include_router(observatory_router)

    anonymous = TestClient(fast).get("/api/observatory/identity-boundary")
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "authentication_required"

    class _Shopper:
        user_id = "shopper-sub"
        username = "marco"
        email = "marco@example.com"
        given_name = "Marco"
        access_token = "shopper-token"
        groups = ()

    class _AuthService:
        async def extract_user(self, _request):
            return _Shopper()

    from services import cognito_auth

    monkeypatch.setattr(
        cognito_auth,
        "get_cognito_auth_service",
        lambda: _AuthService(),
    )
    shopper = TestClient(fast).get(
        "/api/observatory/identity-boundary",
        headers={"Authorization": "Bearer shopper-token"},
    )
    assert shopper.status_code == 403
    assert shopper.json()["detail"] == "operator_group_required"

    class _EmptyIdentityDb:
        async def fetch_all(self, _query: str) -> list[dict]:
            return []

    async def _live_db():
        return _EmptyIdentityDb()

    monkeypatch.setattr(observatory, "_live_db", _live_db)
    fast.dependency_overrides[observatory.require_operator] = lambda: {
        "sub": "operator-sub",
        "groups": ("pellier-operators",),
    }
    operator = TestClient(fast).get("/api/observatory/identity-boundary")
    assert operator.status_code == 200
    assert operator.json()["count"] == 0


def test_proof_board_returns_cards_receipt_and_fallbacks(monkeypatch) -> None:
    _configure_managed(monkeypatch)
    monkeypatch.setattr(
        observatory,
        "_check_inventory_is_workshop_stub",
        lambda: False,
    )
    monkeypatch.setattr(
        observatory,
        "_latest_managed_receipt",
        lambda session_id=None, *, principal_sub: {
            "present": True,
            "traceKind": "managed-runtime-receipt",
            "runtime": "agentcore-managed",
            "rail": "gateway-mcp",
            "jwtPassthrough": True,
            "gatewayPassthrough": True,
            "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
            "runtimeRequestId": "request-123",
            "sessionId": session_id,
            "evidenceProvenance": "agentcore-service-telemetry",
            "managedTrace": {
                "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
                "runtimeRequestId": "request-123",
                "sessionId": session_id,
                "xrayConsoleUrl": "https://console.example/xray",
                "logsConsoleUrl": "https://console.example/logs",
            },
        },
    )
    client = _client(_ProofDB())

    r = client.get("/api/observatory/proof-board?session_id=managed-proof")
    assert r.status_code == 200
    body = r.json()

    assert body["managedReceipt"]["jwtPassthrough"] is True
    assert (
        body["managedReceipt"]["traceId"]
        == "4bf92f3577b34da6a3ce929d0e0e4736"
    )
    assert body["managedReceipt"]["runtimeRequestId"] == "request-123"
    assert body["managedReceipt"]["sessionId"] == "managed-proof"
    assert (
        body["managedReceipt"]["evidenceProvenance"]
        == "agentcore-service-telemetry"
    )
    assert (
        body["managedReceipt"]["managedTrace"]["xrayConsoleUrl"]
        == "https://console.example/xray"
    )
    assert body["managedReceipt"]["governedPrincipalId"] == "CUST-MARCO"
    assert body["managedReceipt"]["governedDecision"] == "ALLOW"
    assert body["managedReceipt"]["writeOperationPresent"] is True
    assert (
        body["managedReceipt"]["writeOperationKey"]
        == "operator-review:8:aaaaaaaa"
    )
    assert (
        body["managedReceipt"]["writeOperationName"]
        == "initiate_return"
    )
    cards = {c["id"]: c for c in body["cards"]}
    assert cards["marco-floor-check"]["status"] == "complete"
    assert cards["marco-floor-check"]["group"] == "Agent and tool evidence"
    assert "act" not in cards["marco-floor-check"]
    assert cards["audit-ledger"]["status"] == "complete"
    assert cards["managed-rail"]["status"] == "complete"
    assert cards["marco-floor-check"]["lab"] == "Lab 1: Build a PostgreSQL-Grounded Agent"
    assert cards["retrieval-comparison"]["lab"] == (
        "Lab 2: Build and Measure PostgreSQL Hybrid Retrieval"
    )
    assert cards["retrieval-comparison"]["status"] == "available"
    assert cards["managed-rail"]["lab"] == (
        "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore"
    )
    assert cards["managed-rail"]["required"] is True
    assert cards["audit-ledger"]["lab"] == (
        "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore"
    )
    assert cards["runtime-gateway-policy"]["lab"] == "Lab 4: Build Governed Agent Actions with Cedar"
    assert cards["runtime-gateway-policy"]["required"] is True
    assert all("act" not in card for card in cards.values())
    assert (
        "npx -y @aws/agentcore@0.29.0 invoke"
        in cards["managed-rail"]["fallback"]["command"]
    )
    assert "retrieval_receipts" in cards["retrieval-comparison"]["fallback"]["command"]
    assert "initiate_return" in cards["audit-ledger"]["fallback"]["command"]


def test_proof_board_fallbacks_use_psql_and_agentcore_cli(
    monkeypatch,
) -> None:
    """Fallbacks inspect PostgreSQL or the managed boundary directly."""
    _configure_managed(monkeypatch)
    monkeypatch.setattr(
        observatory,
        "_check_inventory_is_workshop_stub",
        lambda: False,
    )
    client = _client(_ProofDB())

    response = client.get("/api/observatory/proof-board?session_id=managed-proof")
    assert response.status_code == 200
    cards = {card["id"]: card for card in response.json()["cards"]}

    inventory = cards["marco-floor-check"]["fallback"]["command"]
    managed = cards["managed-rail"]["fallback"]["command"]
    assert inventory.startswith("psql -X -v ON_ERROR_STOP=1")
    assert "FROM pellier.tool_audit" in inventory
    assert "npx -y @aws/agentcore@0.29.0 invoke" in managed
    assert '--bearer-token "$PELLIER_TOKEN"' in managed
    assert "curl " not in inventory
    assert "curl " not in managed


def test_proof_board_is_available_without_a_principal_specific_receipt() -> None:
    import app as app_module

    app_module.db_service = _ProofDB()  # type: ignore[attr-defined]
    fast = FastAPI()
    fast.include_router(observatory_router)
    response = TestClient(fast).get("/api/observatory/proof-board")

    assert response.status_code == 200
    assert response.json()["managedReceipt"]["present"] is False


def test_proof_board_joins_evidence_to_the_verified_principal(monkeypatch) -> None:
    _configure_managed(monkeypatch)
    db = _ProofDB()
    client = _client(db)

    response = client.get("/api/observatory/proof-board?session_id=managed-proof")

    assert response.status_code == 200
    audit_queries = [
        (query, params)
        for query, params in db.calls
        if "FROM pellier.tool_audit ta" in query
    ]
    assert audit_queries
    assert all("governed_turn_receipts" in query for query, _ in audit_queries)
    assert all(
        "jsonb_build_object('audit_id', ta.audit_id)" in query
        for query, _ in audit_queries
    )
    assert all(params.count("CUST-MARCO") >= 2 for _, params in audit_queries)
    governed_queries = [
        (query, params)
        for query, params in db.calls
        if "FROM pellier.governed_receipts gr" in query
    ]
    assert governed_queries
    assert all(params[0] == "CUST-MARCO" for _, params in governed_queries)


def test_proof_board_scopes_gateway_deny_absence(monkeypatch) -> None:
    _configure_managed(monkeypatch)
    db = _DenyProofDB()
    client = _client(db)

    r = client.get("/api/observatory/proof-board?session_id=gateway-identity-mismatch-proof")
    assert r.status_code == 200
    receipt = r.json()["managedReceipt"]

    assert receipt["governedDecision"] == "DENY"
    assert receipt["governedAuditId"] is None
    assert receipt["gatewayAuditPresent"] is False
    assert receipt["gatewayAuditAbsenceVerified"] is True
    # Absence is a search result, not a null column: the declared key was
    # looked for in every table an execution writes.
    assert db.absence_searches == [("workshop-attempt:theo:37",) * 4]
    assert "workshop-attempt:theo:37" in receipt["absenceCheckDetail"]
    assert "tool_audit" in receipt["absenceCheckDetail"]
    assert "write_operations" in receipt["absenceCheckDetail"]


def test_proof_board_reports_a_deny_whose_key_executed_as_a_contradiction(
    monkeypatch,
) -> None:
    """A DENY beside a completed write for the same key is not absence."""
    _configure_managed(monkeypatch)
    db = _DenyProofDB()
    db.absence_counts = {
        "execution_rows": 1,
        "write_rows": 1,
        "completed_writes": 1,
        "ledger_rows": 0,
    }
    client = _client(db)

    r = client.get("/api/observatory/proof-board?session_id=gateway-identity-mismatch-proof")
    assert r.status_code == 200
    receipt = r.json()["managedReceipt"]

    assert receipt["governedDecision"] == "DENY"
    assert receipt["gatewayAuditAbsenceVerified"] is False
    assert "contradict" in receipt["absenceCheckDetail"].lower()
    assert "write_operations" in receipt["absenceCheckDetail"]


def test_proof_board_cannot_verify_absence_without_a_declared_key(
    monkeypatch,
) -> None:
    """A null audit_id alone never proves the tool did not run."""
    _configure_managed(monkeypatch)
    db = _DenyProofDB()
    db.declared_key = None
    client = _client(db)

    r = client.get("/api/observatory/proof-board?session_id=gateway-identity-mismatch-proof")
    assert r.status_code == 200
    receipt = r.json()["managedReceipt"]

    assert receipt["governedDecision"] == "DENY"
    assert receipt["governedAuditId"] is None
    assert receipt["gatewayAuditAbsenceVerified"] is False
    assert db.absence_searches == []
    assert "no idempotency key" in receipt["absenceCheckDetail"]


def test_build_state_reports_inventory_agent_midpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        observatory,
        "_inventory_agent_definition_is_workshop_stub",
        lambda: False,
    )
    monkeypatch.setattr(
        observatory,
        "_check_inventory_is_workshop_stub",
        lambda: True,
    )
    client = _client(_ProofDB())

    r = client.get("/api/observatory/build-state")
    assert r.status_code == 200
    body = r.json()

    assert body["agents"]["Inventory Agent"] == "shipped"
    assert body["tools"]["check_inventory"] == "exercise"


def test_build_state_does_not_promote_scaffolded_inventory_agent_from_tool(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        observatory,
        "_inventory_agent_definition_is_workshop_stub",
        lambda: True,
    )
    monkeypatch.setattr(
        observatory,
        "_check_inventory_is_workshop_stub",
        lambda: False,
    )
    client = _client(_ProofDB())

    r = client.get("/api/observatory/build-state")
    assert r.status_code == 200
    body = r.json()

    assert body["agents"]["Inventory Agent"] == "exercise"
    assert body["tools"]["check_inventory"] == "shipped"


def test_memory_semantic_empty_is_marked_settling(monkeypatch) -> None:
    async def _empty(_persona: str, *, namespace=None) -> list:
        return []

    async def _episodic(_persona: str) -> list:
        return [{"id": "ep-1", "content": "order", "substrate": "episodic"}]

    async def _procedural() -> list:
        return [{"id": "pr-1", "content": "skill", "substrate": "procedural"}]

    async def _operational() -> list:
        return [{"id": "op-1", "content": "check_inventory", "substrate": "operational"}]

    monkeypatch.setattr(
        observatory,
        "_load_live_working",
        _empty,
    )
    monkeypatch.setattr(
        observatory,
        "_load_live_semantic",
        _empty,
    )
    monkeypatch.setattr(
        observatory,
        "_load_live_episodic",
        _episodic,
    )
    monkeypatch.setattr(
        observatory,
        "_load_live_procedural",
        _procedural,
    )
    monkeypatch.setattr(
        observatory,
        "_load_live_operational_history",
        _operational,
    )
    client = _client(_ProofDB())

    r = client.get("/api/observatory/memory/marco")
    assert r.status_code == 200
    body = r.json()

    assert body["semantic"]["source"] == "settling"
    assert body["semantic"]["items"] == []
    assert "asynchronous" in body["semantic"]["caveat"]
    assert body["episodic"]["source"] == "live"
    assert body["procedural"]["source"] == "live"
    assert body["operational"]["source"] == "live"


def test_readiness_missing_database_is_not_ready(monkeypatch) -> None:
    import app as app_module

    _configure_managed(monkeypatch)
    app_module.db_service = None  # type: ignore[attr-defined]
    fast = FastAPI()
    fast.include_router(observatory_router)

    @fast.get("/api/observatory/readiness")
    async def _readiness_probe() -> dict[str, Any]:
        return await observatory._collect_readiness()

    client = TestClient(fast)

    r = client.get("/api/observatory/readiness")
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "not_ready"
    aurora = next(c for c in body["checks"] if c["id"] == "aurora")
    assert aurora["state"] == "fail"


def teardown_function() -> None:
    try:
        import app as app_module

        app_module.db_service = None  # type: ignore[attr-defined]
    except Exception:
        pass


def test_receipt_json_text_decodes_without_inventing_missing_evidence():
    from routes.observatory import _json_object
    assert _json_object('{"idempotency_key":"exact-key"}') == {"idempotency_key": "exact-key"}
    for missing in (None, "{broken", '[]', '"text"'):
        assert _json_object(missing) == {}
