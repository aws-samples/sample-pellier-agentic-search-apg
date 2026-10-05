"""``scripts/lab4_policy_check.py``: real Cedar here, and the Gateway's own answer on the box.

Part 1 evaluates the participant's file with the Cedar engine beside the
rendered baseline and the Gateway schema; a wrong rule must never pass, and
the check must prove it can tell. Part 2's verdict is judged from what the
control plane, the Gateway and the tables said; a 401 or a refusal of any
other kind is never Cedar evidence. Nothing here deploys.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
lab4 = importlib.import_module("lab4_policy_check")
renderer = importlib.import_module("render_agentcore_project")
check = lab4.check

STARTER = (REPO / "workshop" / "starters" / "workshop_credit_limit.cedar").read_text()
SOLUTION = (REPO / "solutions" / "the-concierge" / "policies"
            / "workshop_credit_limit.cedar").read_text()


def _with(body: str) -> str:
    return lab4.with_unless(STARTER, body)


# ---------------------------------------------------------------------------
# Part 1: the matrix, with real Cedar
# ---------------------------------------------------------------------------


class TestTheSchemaAndTheSet:
    def test_the_schema_types_the_credit_input_as_the_gateway_does(self) -> None:
        schema = lab4.gateway_cedar_schema()["AgentCore"]
        credit = schema["actions"][lab4.GIVE_STORE_CREDIT_ACTION]
        attrs = credit["appliesTo"]["context"]["attributes"]["input"]["attributes"]
        assert attrs["amount_cents"] == {"type": "Long", "required": True}
        assert attrs["customer_id"] == {"type": "String", "required": True}
        assert attrs["turn_id"]["required"] is False
        assert credit["memberOf"] == [{"id": "CallTool"}]
        assert schema["entityTypes"]["OAuthUser"]["tags"] == {"type": "String"}

    def test_only_published_tools_are_actions(self) -> None:
        actions = set(lab4.gateway_cedar_schema()["AgentCore"]["actions"]) - {"Mcp", "CallTool"}
        assert "pellier-store-tools___get_tickets" not in actions, "deferred until Lab 3A"
        assert len(actions) == 8

    def test_the_baseline_validates_and_alone_allows_staff_any_amount(self) -> None:
        alone = lab4.assess(None, lab4.gateway_cedar_schema(), lab4.baseline_set())
        assert alone.errors == []
        assert alone.decision_for(lab4.NADIA, 10001).decision == lab4.ALLOW
        assert alone.decision_for(lab4.SHOPPER, 10000).decision == lab4.DENY
        reads = {r.label: d.decision for r, d in alone.rows if r.tool != "give_store_credit"}
        assert reads == {"A shopper (Jessica) reads the return policy": lab4.ALLOW,
                         "A shopper (Jessica) reads her own orders": lab4.ALLOW,
                         "Nadia checks stock": lab4.ALLOW}

    def test_decide_takes_the_action_and_its_input(self) -> None:
        """A shopper's own orders are allowed, another customer's are not: the input decides."""
        schema, policies = lab4.gateway_cedar_schema(), lab4.baseline_set()
        action = "pellier-store-tools___get_orders"
        own = lab4.decide(policies, schema, lab4.SHOPPER, action, {"customer_id": "CUST-JESSICA"})
        other = lab4.decide(policies, schema, lab4.SHOPPER, action, {"customer_id": "CUST-THEO"})
        assert (own.decision, other.decision) == (lab4.ALLOW, lab4.DENY)

    def test_the_unless_block_is_found_past_comments_that_quote_it(self) -> None:
        assert "unless { false }" in STARTER, "the starter's comment quotes the block"
        mutated = _with("true")
        assert 'forbid(\n  principal is AgentCore::OAuthUser,' in mutated
        assert mutated.rstrip().endswith("unless {\n  true\n};")
        assert lab4.unless_body(SOLUTION) == (
            "context.input has amount_cents && context.input.amount_cents <= 10000")


class TestTheVerdicts:
    def test_the_solution_is_proved(self) -> None:
        assert lab4.local_check(SOLUTION, STARTER).finding.state == check.PROVED

    @pytest.mark.parametrize("body", [
        "context.input.amount_cents <= 10000",
        "context.input has amount_cents && context.input.amount_cents < 10001",
        "context.input has amount_cents && !(context.input.amount_cents > 10000)",
    ])
    def test_equivalent_rules_are_proved_too(self, body: str) -> None:
        assert lab4.local_check(_with(body), STARTER).finding.state == check.PROVED

    @pytest.mark.parametrize(("label", "body"), lab4.MUTATIONS)
    def test_every_wrong_rule_is_contradicted(self, label: str, body: str) -> None:
        finding = lab4.local_check(_with(body), STARTER).finding
        expected = check.NOT_YET if body == "false" else check.CONTRADICTED
        assert finding.state in (expected, check.CONTRADICTED), (label, finding)
        assert finding.state != check.PROVED

    @pytest.mark.parametrize("body", [
        'principal.getTag("username") == "nadia" && context.input.amount_cents <= 10000',
        "context.input.amount_cents == 10000 || context.input.amount_cents == 9999",
    ])
    def test_hardcoded_people_or_amounts_are_caught(self, body: str) -> None:
        assert lab4.local_check(_with(body), STARTER).finding.state == check.CONTRADICTED

    def test_a_rule_cedar_rejects_says_so(self) -> None:
        finding = lab4.local_check(_with("context.input.amount_cent <= 10000"), STARTER).finding
        assert finding.state == check.CONTRADICTED
        assert finding.observed.startswith("Cedar rejects your rule")
        assert "attribute name" in finding.next_step

    def test_an_evaluation_error_is_never_read_as_a_decision(self) -> None:
        """A forbid that errors is skipped. Here every decision happens to match the
        matrix, but at exactly 10000 cents the rule overflows: the check must not pass it."""
        body = ("context.input.amount_cents <= 10000 && (context.input.amount_cents < 10000 || "
                "context.input.amount_cents * 9223372036854775807 > 0)")
        assessment = lab4.assess(lab4.render_rule(_with(body)), lab4.gateway_cedar_schema(),
                                 lab4.baseline_set())
        assert all(d.decision == request.want for request, d in assessment.rows)
        assert any("overflow" in " ".join(d.errors) for _request, d in assessment.rows)
        assert lab4.local_check(_with(body), STARTER).finding.state == check.CONTRADICTED

    def test_an_unguarded_tag_read_is_rejected_by_validation(self) -> None:
        body = 'principal.getTag("custom:limit_override") == "yes"'
        finding = lab4.local_check(_with(body), STARTER).finding
        assert finding.state == check.CONTRADICTED
        assert "unable to guarantee safety of access to tag" in finding.observed

    def test_the_hints_name_the_boundary_and_the_unit(self) -> None:
        strict = lab4.local_check(_with(
            "context.input has amount_cents && context.input.amount_cents < 10000"), STARTER)
        assert "excludes the limit" in strict.finding.next_step
        loose = lab4.local_check(_with("true"), STARTER)
        assert "over-limit" in loose.finding.next_step

    def test_the_report_prints_the_matrix_beside_the_starter_and_the_baseline(self) -> None:
        table = lab4.local_check(SOLUTION, STARTER).table
        assert table[1][:5] == ["Nadia, $99.99 (9999 cents)", "ALLOW", "DENY", "ALLOW", "ALLOW"]
        assert table[3][:5] == ["Nadia, $100.01 (10001 cents)", "ALLOW", "DENY", "DENY", "DENY"]
        evidence = "\n".join(lab4.local_check(SOLUTION, STARTER).finding.evidence)
        assert "decided by workshop_credit_limit" in evidence
        assert "without your rule, Nadia at 10001 cents: ALLOW" in evidence
        assert evidence.count(": caught,") == len(lab4.MUTATIONS) + 1 == 6
        assert "policy head: the starter's, unchanged" in evidence
        assert table[7][:5] == ["A shopper (Jessica) reads the return policy", "ALLOW", "ALLOW",
                                "ALLOW", "ALLOW"]

    def test_a_rule_widened_to_every_action_is_contradicted(self) -> None:
        """Reproduced from the cut 6b review: the reference rule over every action passed
        while it denied every shopper tool. The head check and the read rows each catch it."""
        widened = SOLUTION.replace(
            f'action == AgentCore::Action::"{lab4.GIVE_STORE_CREDIT_ACTION}"', "action")
        finding = lab4.local_check(widened, STARTER).finding
        assert finding.state == check.CONTRADICTED
        assert "edit only the final unless block" in finding.next_step
        matrix = lab4.assess(lab4.render_rule(widened), lab4.gateway_cedar_schema(),
                             lab4.baseline_set())
        denied = sorted(r.label for r, d in matrix.wrong)
        assert denied == ["A shopper (Jessica) reads her own orders",
                          "A shopper (Jessica) reads the return policy", "Nadia checks stock"]
        assert "tools it does not govern" in lab4._next_step(matrix)

    def test_the_widened_mutation_is_caught_by_the_read_rows(self) -> None:
        (label, mutant), = [m for m in lab4.mutants(lab4.render_rule(SOLUTION))
                            if m[0] == lab4.WIDENED]
        assessment = lab4.assess(mutant, lab4.gateway_cedar_schema(), lab4.baseline_set())
        assert not assessment.passed
        assert all(r.tool != "give_store_credit" for r, _d in assessment.wrong), label

    def test_any_edit_before_the_unless_block_is_contradicted(self) -> None:
        """Comments may change; the principal, the action and the resource may not."""
        commented = "// my note\n" + SOLUTION
        assert lab4.local_check(commented, STARTER).finding.state == check.PROVED
        # Every principal is an OAuthUser, so Cedar decides the matrix the same way:
        # only the head check can catch this edit.
        any_principal = SOLUTION.replace("principal is AgentCore::OAuthUser,", "principal,")
        assert lab4.assess(lab4.render_rule(any_principal), lab4.gateway_cedar_schema(),
                           lab4.baseline_set()).passed
        finding = lab4.local_check(any_principal, STARTER).finding
        assert finding.state == check.CONTRADICTED
        assert finding.observed.startswith("your edit changes the lines before the unless block")

    def test_a_policy_without_an_unless_block_is_contradicted_not_a_traceback(self) -> None:
        bare = SOLUTION[:SOLUTION.rindex("unless")] + ";"
        result = lab4.local_check(bare, STARTER)
        assert result.finding.state == check.CONTRADICTED
        assert result.finding.observed == "the policy has no final unless block"
        assert result.table == []

    def test_a_check_that_cannot_tell_right_from_wrong_is_unchecked(self, monkeypatch) -> None:
        monkeypatch.setattr(lab4, "MUTATIONS", (("the right rule", lab4.unless_body(SOLUTION)),))
        assert lab4.local_check(SOLUTION, STARTER).finding.state == check.UNCHECKED


# ---------------------------------------------------------------------------
# Part 2: the deployed rule and the Gateway's answer
# ---------------------------------------------------------------------------

ENGINE = {"policy_ids": {"workshop_credit_limit": "workshop_credit_limit-abc"},
          "policy_digest": "sha256:" + "d" * 64, "gateway_mode": "ENFORCE",
          "matching": ["workshop_credit_limit"], "policy_engine_id": "engine-1"}
REVIEW = {"id": 41, "status": "approved", "decided_by_name": "nadia",
          "idempotency_key": "operator-review:41:" + "a" * 32}
DENY_PAYLOAD = {"outcome": "deny", "cedar_denial": True,
                "error": "Tool call not allowed due to policy enforcement"}


def _judge(**overrides: Any) -> check.Finding:
    rule = lab4.render_rule(SOLUTION, "arn:aws:bedrock-agentcore:us-east-1:1:gateway/g")
    kwargs: Dict[str, Any] = {"deployed": rule, "local_rule": rule, "local_proved": True,
                              "payload": DENY_PAYLOAD, "rows": {"audit_rows": 0, "credit_rows": 0},
                              "review": REVIEW, "engine": ENGINE}
    kwargs.update(overrides)
    return lab4.judge_managed(**kwargs)


class TestTheManagedVerdict:
    def test_a_cedar_denial_with_no_rows_is_proved_with_the_policy_identity(self) -> None:
        finding = _judge()
        assert finding.state == check.PROVED
        evidence = "\n".join(finding.evidence)
        assert "workshop_credit_limit-abc" in evidence and "sha256:dddd" in evidence
        assert "operator-review:41:" in evidence
        assert "tool_audit rows 0, store_credits rows 0" in evidence
        assert "opened and confirmed by the Lab 4 policy check (probe data)" in evidence
        assert "approved by" not in evidence, "no person approved the probe"
        # The starter denies 10001 too: a DENY while the update propagates proves less.
        assert "cannot tell your rule from a starter still propagating" in evidence
        assert "Jessica's $100.00 credit" in evidence

    def test_a_deployed_rule_that_is_not_the_file_is_not_yet(self) -> None:
        finding = _judge(deployed=lab4.render_rule(STARTER))
        assert finding.state == check.NOT_YET
        assert "--mode participant" in finding.next_step

    def test_comments_and_spacing_do_not_count_as_a_different_rule(self) -> None:
        rule = lab4.render_rule(SOLUTION)
        assert _judge(deployed=lab4.cedar_code(rule).replace("\n", "\n\n"),
                      local_rule=rule).state == check.PROVED

    def test_the_starter_still_deployed_denies_but_proves_nothing(self) -> None:
        """The starter denies 10001 too; the DENY counts only once your rule is deployed."""
        finding = _judge(deployed=lab4.render_rule(STARTER), payload=DENY_PAYLOAD)
        assert finding.state == check.NOT_YET

    def test_a_401_or_transport_failure_is_not_cedar_evidence(self) -> None:
        failure = {"outcome": "error", "cedar_denial": False, "error": "HTTP 401"}
        assert _judge(payload=failure).state == check.UNCHECKED

    def test_an_allow_or_any_row_contradicts(self) -> None:
        allowed = {"outcome": "allow", "cedar_denial": False, "result": {}}
        assert _judge(payload=allowed).state == check.CONTRADICTED
        assert _judge(rows={"audit_rows": 1, "credit_rows": 0}).state == check.CONTRADICTED

    def test_a_missing_policy_or_an_unproved_rule_never_probes_into_a_proof(self) -> None:
        assert _judge(deployed=None).state == check.CONTRADICTED
        assert _judge(local_proved=False).state == check.NOT_YET

    @pytest.fixture
    def managed_box(self, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
        """The Gateway is configured and the deployed rule is the solution."""
        arn = "arn:aws:bedrock-agentcore:us-east-1:1:gateway/g"
        deployed = lab4.render_rule(SOLUTION, arn)
        engine = {**ENGINE, "statements": {"workshop_credit_limit": deployed}}
        monkeypatch.setattr(lab4, "_managed_environment", lambda: ("https://gw", arn, engine))
        return {"local": lab4.local_check(SOLUTION, STARTER), "cfg": {"DB_HOST": "db"}}

    def test_a_failure_after_the_environment_check_is_a_finding_not_a_traceback(
        self, managed_box: Dict[str, Any], monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A missing secret or an unreachable database is reported as UNCHECKED with its reason."""
        import gateway_client

        def _no_secret(_user: str) -> str:
            raise SystemExit("Missing required environment variable: COGNITO_TEST_CREDENTIALS")

        monkeypatch.setattr(gateway_client, "_token_from_cognito", _no_secret)
        finding = lab4.managed_check(managed_box["local"], SOLUTION, managed_box["cfg"])
        assert finding.state == check.UNCHECKED
        assert finding.observed == "the over-limit call could not be made"
        assert "SystemExit: Missing required environment variable" in finding.evidence[-1]

        monkeypatch.setattr(gateway_client, "_token_from_cognito", lambda _user: "jwt")
        monkeypatch.setattr(gateway_client, "_verified_identity",
                            lambda _token: {"verified_subject": "sub-nadia"})

        def _unreachable(_cfg: Any) -> Any:
            raise ConnectionError("database unreachable")

        monkeypatch.setattr(lab4.check, "connect", _unreachable)
        finding = lab4.managed_check(managed_box["local"], SOLUTION, managed_box["cfg"])
        assert finding.state == check.UNCHECKED
        assert "ConnectionError: database unreachable" in finding.evidence[-1]

    def test_no_database_settings_is_unchecked_with_the_reason(self, managed_box) -> None:
        finding = lab4.managed_check(managed_box["local"], SOLUTION, None)
        assert finding.state == check.UNCHECKED
        assert finding.evidence[-1].startswith("no database settings (DB_HOST, DB_NAME, DB_USER)")

    def test_no_managed_environment_is_unchecked(self, monkeypatch) -> None:
        import gateway_client

        monkeypatch.setattr(gateway_client, "_load_env", lambda: None)
        monkeypatch.delenv("AGENTCORE_GATEWAY_URL", raising=False)
        local = lab4.local_check(SOLUTION, STARTER)
        assert lab4.managed_check(local, SOLUTION, None).state == check.UNCHECKED


class TestTheStoredAnswer:
    def test_the_gateway_answer_is_stored_in_the_desks_shape(self) -> None:
        attempt = lab4.attempt_for(DENY_PAYLOAD, REVIEW["idempotency_key"], ENGINE)
        assert (attempt["outcome"], attempt["policy"], attempt["rail"]) == (
            "denied", "DENY", "gateway-mcp")
        assert attempt["policy_digest"] == ENGINE["policy_digest"]
        assert attempt["detail"].startswith("Tool call not allowed")
        failed = lab4.attempt_for({"outcome": "error", "error": "401"}, "k", ENGINE)
        assert failed["outcome"] == "failed"

    def test_the_recorded_probe_is_judged_from_its_answer_and_its_rows(self) -> None:
        row = {"id": 41, "idempotency_key": REVIEW["idempotency_key"], "audit_rows": 0,
               "credit_rows": 0,
               "last_attempt": json.dumps({"outcome": "denied", "policy": "DENY"})}
        assert lab4.judge_recorded_probe(row).state == check.PROVED
        assert lab4.judge_recorded_probe(None).state == check.NOT_YET
        assert lab4.judge_recorded_probe({**row, "last_attempt": None}).state == check.NOT_YET
        assert lab4.judge_recorded_probe({**row, "credit_rows": 1}).state == check.CONTRADICTED


# ---------------------------------------------------------------------------
# Provisioning and reset declare the policy from a file
# ---------------------------------------------------------------------------


def test_the_reset_declares_the_starter_again(tmp_path: Path) -> None:
    arn = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/g"
    solution = renderer.credit_limit_policy(
        gateway_arn=arn,
        source=REPO / "solutions/the-concierge/policies/workshop_credit_limit.cedar")
    permit = {"name": "give_store_credit_staff_scope",
              "statement": f'permit (principal, action, resource == AgentCore::Gateway::"{arn}");'}
    config = tmp_path / "agentcore.json"
    config.write_text(json.dumps({"policyEngines": [
        {"name": "pellier_policy_engine", "policies": [permit, solution]}]}))
    starter = REPO / renderer.CREDIT_LIMIT_STARTER

    assert renderer.declare_credit_limit(config, engine_name="pellier_policy_engine",
                                         source=starter) is True
    declared = json.loads(config.read_text())["policyEngines"][0]["policies"]
    assert [p["name"] for p in declared] == [
        "give_store_credit_staff_scope", "workshop_credit_limit"]
    assert declared[1]["statement"] == starter.read_text().replace("${PELLIER_GATEWAY_ARN}", arn)
    assert declared[1]["validationMode"] == "IGNORE_ALL_FINDINGS"
    assert renderer.declare_credit_limit(config, engine_name="pellier_policy_engine",
                                         source=starter) is False, "already the starter"
