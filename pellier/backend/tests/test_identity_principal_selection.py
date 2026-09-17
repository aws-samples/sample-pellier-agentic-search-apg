"""The governed identity path resolves a principal by name, never by position.

`gateway_initiate_return.py` used to authenticate as `users[0]`, so which
principal signed a governed call depended on provisioning order rather than on
the caller's intent. Lab 4 asks a participant to compare Cedar's answer for
three different principals sending one identical request, which is unprovable if
every attempt silently authenticates as the same user.

These tests cover the selection rule itself. Minting a token needs Cognito, but
choosing *which* credential to mint is pure and is where the mistake lived.
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[3]
_CALLER = _REPO / "scripts" / "deploy" / "gateway_initiate_return.py"


def _load_selector():
    """Import the selector without importing the module's heavy CLI deps.

    The script imports mcp/anyio/httpx at module scope, which are not part of
    the backend test environment. The selector is self-contained, so it is read
    and executed on its own rather than pulling the whole CLI in.
    """
    source = _CALLER.read_text()
    start = source.index("def select_credential(")
    end = source.index("def _token_from_cognito(")
    namespace: dict = {"Any": object}
    exec(compile(source[start:end], str(_CALLER), "exec"), namespace)  # noqa: S102
    return namespace["select_credential"]


select_credential = _load_selector()


def _load_proof_driver():
    module_name = "prove_identity_boundary_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]

    script_path = _REPO / "scripts" / "prove_identity_boundary.py"
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

USERS = [
    {"username": "marco", "password": "x"},
    {"username": "anna", "password": "y"},
    {"username": "theo", "password": "z"},
    {"username": "jessica", "password": "w"},
]


def test_resolves_by_name_not_by_position():
    assert select_credential(USERS, "theo")["username"] == "theo"
    assert select_credential(USERS, "anna")["username"] == "anna"
    assert select_credential(USERS, "jessica")["username"] == "jessica"


def test_name_match_is_case_insensitive():
    assert select_credential(USERS, "THEO")["username"] == "theo"
    assert select_credential(USERS, "  Anna  ")["username"] == "anna"


def test_position_is_never_used_to_satisfy_a_named_request():
    """A request for a name absent from the secret must fail, not fall back.

    Falling back to the first user would authenticate as Marco while the
    operator believed they were Theo, which is precisely the confusion the
    exercise exists to rule out.
    """
    with pytest.raises(SystemExit) as excinfo:
        select_credential(USERS, "mallory")
    message = str(excinfo.value)
    assert "mallory" in message
    # The error names what is available so the operator can self-correct.
    assert all(name in message for name in ("marco", "anna", "theo", "jessica"))


def test_empty_request_keeps_the_first_entry():
    """Callers that do not name a principal are unaffected by this change."""
    assert select_credential(USERS, "")["username"] == "marco"
    assert select_credential(USERS, "   ")["username"] == "marco"


def test_duplicate_username_is_refused_rather_than_guessed():
    duplicated = USERS + [{"username": "Theo", "password": "second"}]
    with pytest.raises(SystemExit) as excinfo:
        select_credential(duplicated, "theo")
    assert "more than once" in str(excinfo.value)


def test_duplicate_is_refused_even_when_another_name_was_requested():
    """An ambiguous secret is rejected outright.

    A secret that names one principal twice cannot answer "who signed this
    call" for any principal, so the whole selection is refused rather than only
    the ambiguous name.
    """
    duplicated = USERS + [{"username": "anna", "password": "second"}]
    with pytest.raises(SystemExit):
        select_credential(duplicated, "marco")


def test_blank_and_missing_usernames_are_ignored_not_matched():
    users = [{"username": "  ", "password": "x"}, {"password": "y"}, *USERS]
    assert select_credential(users, "marco")["username"] == "marco"
    # The unusable entries must not become the implicit default either.
    assert select_credential(users, "")["username"] == "marco"


def test_no_usable_users_is_a_clear_failure():
    with pytest.raises(SystemExit) as excinfo:
        select_credential([{"password": "x"}], "marco")
    assert "no usable users" in str(excinfo.value)


def test_username_to_customer_mapping_is_the_single_source_of_truth():
    """The proof driver must not restate the username -> customer mapping."""
    from services.turn_identity import USERNAME_TO_CUSTOMER_ID

    assert USERNAME_TO_CUSTOMER_ID == {
        "marco": "CUST-MARCO",
        "anna": "CUST-ANNA",
        "theo": "CUST-THEO",
        "jessica": "CUST-JESSICA",
    }


def test_proof_driver_targets_one_customer_for_every_principal():
    """The three attempts must differ only by principal.

    If the driver ever varied `customer_id` per attempt, the DENY results would
    be explained by the request instead of by the identity, and the proof would
    say nothing.
    """
    driver = (_REPO / "scripts" / "prove_identity_boundary.py").read_text()
    assert 'TARGET_CUSTOMER = "CUST-JESSICA"' in driver
    # One customer for every case, supplied once from the constant.
    assert '"--customer-id", TARGET_CUSTOMER,' in driver
    assert driver.count('"--customer-id"') == 1, (
        "customer_id must be passed from one place so no case can diverge."
    )
    # The matrix: one policy denial, one business refusal, one permit, one replay
    # of the permit's key. Four attempts, four different outcomes.
    for case in ('"username": "marco", "expected_outcome": "deny"',
                 '"kind": "refuse", "username": "jessica", "expected_outcome": "allow"',
                 '"kind": "allow", "username": "jessica", "expected_outcome": "allow"'):
        assert case in driver, f"missing matrix case: {case}"
    assert '"kind": "replay"' in driver, "the idempotent replay case is missing"
    assert "_ineligible_product" in driver, "the refusal case must pick an unordered piece"
    # The replay must reuse the ALLOW key rather than mint a new one.
    assert driver.count("allow_key") >= 3
    # Absence is proved by the attempt's own key, never by a time window.
    assert "args->>'idempotency_key'" in driver
    assert "interval" not in driver.lower()


def test_the_proof_driver_asserts_a_single_canonical_effect():
    """"At least one durable write" is not an acceptance criterion.

    `pellier.write_operations` is keyed by `idempotency_key` as its primary key,
    so exactly one row per key is what success looks like and what the replay
    case must not change.
    """
    driver = (_REPO / "scripts" / "prove_identity_boundary.py").read_text()
    assert "canonical_writes" in driver
    assert 'if writes != 1:' in driver, (
        "the ALLOW case must assert exactly one canonical write."
    )
    assert "at least one" not in driver.lower()


def test_the_proof_driver_validates_the_product_before_invoking_anything():
    """A guessed product id turns an impossible ALLOW into a confusing DENY."""
    driver = (_REPO / "scripts" / "prove_identity_boundary.py").read_text()
    assert "def _resolve_product(" in driver
    assert "def _eligible_products(" in driver
    resolve_at = driver.index("product_id, candidates, note = _resolve_product(")
    invoke_at = driver.index("result = _invoke(")
    assert resolve_at < invoke_at, "preflight must run before the first invocation."


def test_the_proof_driver_proves_the_write_side_boundary_not_only_reads():
    """The asymmetry is the point: empty read versus error-and-rollback write."""
    driver = (_REPO / "scripts" / "prove_identity_boundary.py").read_text()
    assert "def _rls_read(" in driver and "def _rls_write(" in driver
    assert "ROLLBACK;" in driver, "the write probe must never leave data behind."
    assert "42501" in driver, "the row-level security refusal must be recognised."
    assert 'RUNTIME_ROLE = "pellier_agent"' in driver, (
        "the probe must run as the non-owner NOBYPASSRLS runtime role."
    )


def _evidence(
    *,
    decision: str,
    execution_rows: int,
    write_rows: int,
    canonical_writes: int,
    replay: bool = False,
) -> dict:
    return {
        "queried": True,
        "policy_receipts": 1,
        "execution_rows": execution_rows,
        "write_rows": write_rows,
        "canonical_writes": canonical_writes,
        "ledger_rows": 0,
        "recorded_decision": decision,
        "idempotent_replay": replay,
    }


def test_matrix_uses_a_receipt_key_per_invocation_and_one_replayed_write_key(monkeypatch):
    """Four attempts stay visible as four receipts while the write stays singular."""
    driver = _load_proof_driver()
    calls: list[dict] = []
    evidence = iter(
        [
            _evidence(decision="DENY", execution_rows=0, write_rows=0, canonical_writes=0),
            # The business refusal: permitted and executed, nothing finalized.
            _evidence(decision="ALLOW", execution_rows=1, write_rows=1, canonical_writes=0),
            _evidence(decision="ALLOW", execution_rows=1, write_rows=1, canonical_writes=1),
            _evidence(
                decision="ALLOW",
                execution_rows=2,
                write_rows=1,
                canonical_writes=1,
                replay=True,
            ),
        ]
    )

    monkeypatch.setattr(
        driver,
        "_load_env",
        lambda _path: {
            "DB_HOST": "db",
            "DB_NAME": "pellier",
            "DB_USER": "user",
            "DB_PASSWORD": "password",
        },
    )
    monkeypatch.setattr(
        driver,
        "_resolve_product",
        lambda _cfg, _requested: (41, [(41, "Coral Lacquer Catchall")], "resolved"),
    )
    monkeypatch.setattr(driver, "_ineligible_product", lambda _cfg: 7)
    monkeypatch.setattr(
        driver,
        "_invoke",
        lambda **kwargs: calls.append(kwargs)
        or {
            "observed_outcome": kwargs["expect"],
            "tool_status": "error" if kwargs["product_id"] == 7 else "success",
            "tool_message": "Customer CUST-JESSICA did not order product 7" if kwargs["product_id"] == 7 else "",
            "exit_code": 0,
            "stderr": "",
        },
    )
    monkeypatch.setattr(driver, "_keyed_evidence", lambda *_args, **_kwargs: next(evidence))
    monkeypatch.setattr(
        driver,
        "_return_evidence",
        lambda _cfg, idempotency_key: {} if idempotency_key.endswith("ineligible") else {
            "return_id": 77,
            "customer_id": "CUST-JESSICA",
            "product_id": 41,
            "reason": "damaged",
        },
    )
    monkeypatch.setattr(
        driver.uuid,
        "uuid4",
        lambda: type("_Run", (), {"hex": "matrixrun001000"})(),
    )

    assert driver.main(["--skip-aurora"]) == 0
    assert [call["receipt_key"] for call in calls] == [
        "identity-boundary-matrixrun0-marco",
        "identity-boundary-matrixrun0-jessica-ineligible",
        "identity-boundary-matrixrun0-jessica",
        "identity-boundary-matrixrun0-jessica-replay",
    ]
    assert [call["idempotency_key"] for call in calls] == [
        "identity-boundary-matrixrun0-marco",
        "identity-boundary-matrixrun0-jessica-ineligible",
        "identity-boundary-matrixrun0-jessica",
        "identity-boundary-matrixrun0-jessica",
    ]
    assert [call["product_id"] for call in calls] == [41, 7, 41, 41]


def test_allow_verdict_requires_one_finalized_successful_write_and_exact_return():
    driver = _load_proof_driver()
    case = {
        "kind": "allow",
        "expected_outcome": "allow",
        "observed_outcome": "allow",
        "product_id": 41,
        "domain_return": {
            "return_id": 77,
            "customer_id": "CUST-JESSICA",
            "product_id": 41,
            "reason": "damaged",
        },
    }
    unfinalized = _evidence(
        decision="ALLOW",
        execution_rows=1,
        write_rows=1,
        canonical_writes=0,
    )

    passed, note = driver._verdict(case, unfinalized)

    assert not passed
    assert "finalized successful write" in note


def test_return_evidence_joins_the_return_id_from_the_finalized_write(monkeypatch):
    driver = _load_proof_driver()
    captured = {}

    def _scalar(_cfg, sql):
        captured["sql"] = sql
        return '{"return_id":77,"customer_id":"CUST-JESSICA","product_id":41,"reason":"damaged"}'

    monkeypatch.setattr(driver, "_scalar", _scalar)

    result = driver._return_evidence({}, "jessica-write-key")

    assert result["return_id"] == 77
    assert result["customer_id"] == "CUST-JESSICA"
    assert "JOIN pellier.returns r" in captured["sql"]
    assert "wo.result->>'return_id'" in captured["sql"]
    assert "wo.result->>'status' = 'success'" in captured["sql"]


def test_rls_write_only_accepts_the_expected_row_security_sqlstate(monkeypatch):
    driver = _load_proof_driver()
    monkeypatch.setattr(
        driver,
        "_psql",
        lambda *_args, **_kwargs: (
            0,
            "RLS_PROBE_ROLE_OK\nsubject",
            "NOTICE:  RLS_PROBE_SQLSTATE:42501",
        ),
    )

    allowed_refusal = driver._rls_write({}, "marco-sub", 31)

    assert allowed_refusal == {
        "queried": True,
        "refused": True,
        "sqlstate": "42501",
        "error": "",
    }

    monkeypatch.setattr(
        driver,
        "_psql",
        lambda *_args, **_kwargs: (
            0,
            "RLS_PROBE_ROLE_OK\nsubject",
            "NOTICE:  RLS_PROBE_SQLSTATE:23505",
        ),
    )

    wrong_refusal = driver._rls_write({}, "marco-sub", 31)

    assert wrong_refusal["queried"] is True
    assert wrong_refusal["refused"] is False
    assert wrong_refusal["sqlstate"] == ""


# ---------------------------------------------------------------------------
# The identity-boundary read model: what may and may not carry identity
# ---------------------------------------------------------------------------

_OBSERVATORY = pathlib.Path(__file__).resolve().parents[1] / "routes" / "observatory.py"


def _identity_endpoint_source() -> str:
    source = _OBSERVATORY.read_text()
    start = source.index('@router.get("/identity-boundary")')
    return source[start:]


def test_the_customer_mapping_joins_on_the_subject_not_the_token_fingerprint():
    """`sub` is the durable identity. The fingerprint is a diagnostic.

    A token fingerprint identifies one minted token, not a person: it changes on
    every refresh, so mapping customer scope through it would silently unscope a
    principal the moment their token rotated. Aurora keys on the Cognito subject.
    """
    endpoint = _identity_endpoint_source()
    assert "pc.principal_sub = gr.verified_subject" in endpoint, (
        "the customer mapping must join on the Cognito subject."
    )
    assert "token_fingerprint" not in endpoint.split("LEFT JOIN")[1].split("ORDER BY")[0], (
        "the fingerprint must not appear in the identity join."
    )


def test_the_fingerprint_is_passed_through_for_display_only():
    """It is reported, never compared, counted, or used as a key."""
    endpoint = _identity_endpoint_source()
    # Present as an output field.
    assert '"tokenFingerprint": record.get("tokenFingerprint")' in endpoint
    # Absent from every decision the endpoint makes.
    for guard in ("if is_fixture", "execution_row =", "ownership ="):
        segment = endpoint[endpoint.index(guard):endpoint.index(guard) + 400]
        assert "tokenFingerprint" not in segment and "token_fingerprint" not in segment, (
            f"the fingerprint influences {guard!r}; it must be diagnostic only."
        )


def test_identity_endpoint_requires_a_matching_finalized_return():
    """A completed key for another operation must not satisfy the Lab 4 matrix."""
    endpoint = _identity_endpoint_source()
    for clause in (
        "ta.tool = 'initiate_return'",
        "JOIN pellier.returns r",
        "wo.operation = 'initiate_return'",
        "wo.result->>'status' = 'success'",
        "r.customer_id = gr.args->>'customer_id'",
        "r.product_id = gr.args->>'product_id'",
        "r.reason = gr.args->>'reason'",
    ):
        assert clause in endpoint, (
            "the identity matrix must join a finalized initiate_return to its "
            f"exact requested domain row; missing {clause!r}"
        )


def test_absence_is_never_claimed_for_a_fixture():
    """A row that was never keyed cannot prove non-execution."""
    endpoint = _identity_endpoint_source()
    assert "if is_fixture or not idempotency_key:" in endpoint
    assert 'execution_row = "unknown"' in endpoint


def test_the_page_has_no_weakest_row_wins_badge():
    """A permanent seeded fixture must not cap what a live run can report."""
    endpoint = _identity_endpoint_source()
    assert '"liveRuns"' in endpoint and '"fixtures"' in endpoint, (
        "live proof and seeded reference must be separate collections."
    )
    # The old page-level summary is gone.
    assert '"provenance": (' not in endpoint, (
        "a page-level provenance badge would let one fixture classify the page."
    )


def test_run_summaries_are_computed_within_one_run():
    """A stale failure must not follow a participant who has since fixed it."""
    endpoint = _identity_endpoint_source()
    block = endpoint[endpoint.index("for run in runs:"):]
    assert 'cases = run["attempts"]' in block
    for field in ('run["denyCount"]', 'run["allowCount"]', 'run["complete"]'):
        assert field in block
    # Every count is derived from `cases`, never from the flat list.
    assert "for c in cases" in block


class _IdentityBoundaryDb:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    async def fetch_all(self, query: str) -> list[dict]:
        self.queries.append(query)
        return self.rows


def _identity_row(
    receipt_key: str,
    *,
    username: str,
    mapped_customer: str,
    decision: str,
    audit_rows: int,
    write_rows: int,
    idempotency_key: str | None = None,
) -> dict:
    return {
        "receiptId": len(receipt_key),
        "correlationKey": receipt_key,
        "idempotencyKey": idempotency_key or receipt_key,
        "verifiedUsername": username,
        "verifiedSubject": f"{username}-subject",
        "requestedCustomerId": "CUST-JESSICA",
        "decision": decision,
        "policyName": "workshop_identity_match_forbid",
        "policyEngineId": "policy-engine",
        "tokenFingerprint": "diagnostic-only",
        "identitySource": "cognito",
        "tool": "initiate_return",
        "auditId": None if audit_rows == 0 else 100 + len(receipt_key),
        "createdAt": "2026-09-01T12:00:00+00:00",
        "mappedCustomerIds": [mapped_customer],
        "keyedAuditRows": audit_rows,
        "keyedWriteRows": write_rows,
    }


def test_identity_endpoint_requires_the_exact_four_case_replay_contract(monkeypatch):
    from routes import observatory

    run = "identity-boundary-matrixrun"
    write_key = f"{run}-jessica"
    db = _IdentityBoundaryDb(
        [
            _identity_row(
                f"{run}-marco",
                username="marco",
                mapped_customer="CUST-MARCO",
                decision="DENY",
                audit_rows=0,
                write_rows=0,
            ),
            _identity_row(
                f"{run}-jessica-ineligible",
                username="jessica",
                mapped_customer="CUST-JESSICA",
                decision="ALLOW",
                audit_rows=1,
                write_rows=0,
            ),
            _identity_row(
                write_key,
                username="jessica",
                mapped_customer="CUST-JESSICA",
                decision="ALLOW",
                audit_rows=2,
                write_rows=1,
                idempotency_key=write_key,
            ),
            _identity_row(
                f"{run}-jessica-replay",
                username="jessica",
                mapped_customer="CUST-JESSICA",
                decision="ALLOW",
                audit_rows=2,
                write_rows=1,
                idempotency_key=write_key,
            ),
        ]
    )

    db.rows[1]["businessRejected"] = True

    async def _live_db():
        return db

    monkeypatch.setattr(observatory, "_live_db", _live_db)
    payload = asyncio.run(observatory.identity_boundary())

    assert payload["selectedRunId"] == run
    assert payload["liveRuns"][0]["complete"] is True
    assert {
        attempt["correlationKey"]: attempt["idempotencyKey"]
        for attempt in payload["liveRuns"][0]["attempts"]
    }[f"{run}-jessica-replay"] == write_key
    assert "COALESCE(" in db.queries[0]
    assert "NULLIF(gr.args->>'idempotency_key', '')" in db.queries[0]


def test_identity_endpoint_does_not_call_a_three_case_run_complete(monkeypatch):
    from routes import observatory

    run = "identity-boundary-incomplete"
    db = _IdentityBoundaryDb(
        [
            _identity_row(
                f"{run}-marco",
                username="marco",
                mapped_customer="CUST-MARCO",
                decision="DENY",
                audit_rows=0,
                write_rows=0,
            ),
            _identity_row(
                f"{run}-anna",
                username="anna",
                mapped_customer="CUST-ANNA",
                decision="DENY",
                audit_rows=0,
                write_rows=0,
            ),
            _identity_row(
                f"{run}-jessica",
                username="jessica",
                mapped_customer="CUST-JESSICA",
                decision="ALLOW",
                audit_rows=1,
                write_rows=1,
            ),
        ]
    )

    async def _live_db():
        return db

    monkeypatch.setattr(observatory, "_live_db", _live_db)
    payload = asyncio.run(observatory.identity_boundary())

    assert payload["liveRuns"][0]["complete"] is False
