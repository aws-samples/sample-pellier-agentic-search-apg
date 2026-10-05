"""The Lab 4 Cedar files, the token trigger, and the baseline must agree.

Identity reaches Cedar as a claim, not as a list of shoppers
------------------------------------------------------------
The baseline's owner-only permits compare the access token's
``custom:customer_id`` tag with the tool's ``customer_id`` input. The claim is
stamped by the Cognito pre-token trigger from ``pellier.customers.cognito_username``,
which is also what row-level security reads, so the policy, the token, and
the database share one mapping and no policy file has to enumerate shoppers.

The Lab 4 file is a different rule: an amount limit on ``give_store_credit``.
The baseline staff permit does not bound the amount, and the participant's
forbid does.

What is checked
---------------
* the trigger issues the claim the baseline's owner-only permit reads;
* the starter stays unsolved and gives nothing away;
* the reference is an amount rule that admits only a present amount up to $100;
* both files target the same action and pin the Gateway by ARN placeholder;
* neither file names a shopper, a customer id, or the ID-token claim;
* the trigger's mapping source is the same column RLS reads.

Nothing here writes to either file. A validator that repaired the starter would
delete the exercise.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[3]
# The four shoppers, as scripts/migrations/002_seed.sql seeds them.
SHOPPERS = {
    "marco": "CUST-MARCO", "anna": "CUST-ANNA", "theo": "CUST-THEO", "jessica": "CUST-JESSICA",
}
STARTER = _REPO / "policies" / "workshop_credit_limit.cedar"
TEMPLATE = _REPO / "workshop" / "starters" / "workshop_credit_limit.cedar"
REFERENCE = _REPO / "solutions" / "the-concierge" / "policies" / "workshop_credit_limit.cedar"
TRIGGER = _REPO / "scripts" / "deploy" / "cognito_customer_claim.py"
DEPLOYER = _REPO / "scripts" / "deploy" / "deploy_customer_claim_trigger.py"
ACTION = re.compile(r'action\s*==\s*AgentCore::Action::"([^"]+)"')
RESOURCE = 'resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"'


def _trigger_claim_name() -> str:
    spec = importlib.util.spec_from_file_location("cognito_customer_claim", TRIGGER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["cognito_customer_claim"] = module
    spec.loader.exec_module(module)
    return module.CLAIM_NAME


def test_all_three_policy_files_exist() -> None:
    for path in (STARTER, TEMPLATE, REFERENCE):
        assert path.is_file(), f"missing: {path}"


def test_the_working_copy_starts_as_the_starter() -> None:
    assert STARTER.read_bytes() == TEMPLATE.read_bytes()


def test_the_trigger_issues_the_claim_the_baseline_owner_permit_reads() -> None:
    claim = _trigger_claim_name()
    deploy = str(_REPO / "scripts" / "deploy")
    if deploy not in sys.path:
        sys.path.insert(0, deploy)
    import render_agentcore_project as renderer

    arn = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"
    owner = next(
        policy for policy in renderer.baseline_policies(gateway_arn=arn)
        if policy["name"] == "get_orders_owner_only"
    )
    assert f'principal.getTag("{claim}") == context.input.customer_id' in owner["statement"]


def test_the_participant_starter_is_still_unsolved() -> None:
    starter = STARTER.read_text()
    assert re.search(r"unless\s*\{\s*false\s*\}", starter), (
        "the participant starter must ship with `unless { false }`; it currently "
        "contains something else, so either the exercise was solved in place or "
        "the fail-closed shape was lost."
    )
    assert "getTag(" not in starter, "the starter must not carry the comparison"


def test_neither_file_names_a_shopper_or_a_customer() -> None:
    for path in (STARTER, REFERENCE):
        text = path.read_text()
        for username, customer_id in SHOPPERS.items():
            assert f'"{username}"' not in text, f"{path.name} names {username!r}"
            assert customer_id not in text, f"{path.name} names {customer_id!r}"
        assert 'getTag("username")' not in text, path.name


def test_the_reference_is_an_amount_rule_not_an_identity_match() -> None:
    code = "\n".join(
        line for line in REFERENCE.read_text().splitlines()
        if not line.strip().startswith("//")
    )
    assert code.lstrip().startswith("forbid(")
    assert re.search(
        r"unless\s*\{\s*context\.input has amount_cents\s*&&\s*"
        r"context\.input\.amount_cents <= 10000\s*\}",
        code,
    ), "a request with no amount must be denied rather than compared against an absent field"
    assert "principal.getTag(" not in code
    assert "when" not in code.replace("whenever", ""), "the forbid applies to every principal"
    assert "custom:staff_scope" not in code, "staff authority is a permit, not a carve-out"


def test_both_files_target_the_same_action_and_pin_the_gateway() -> None:
    starter_action = ACTION.search(STARTER.read_text())
    reference_action = ACTION.search(REFERENCE.read_text())
    assert starter_action and reference_action
    assert starter_action.group(1) == reference_action.group(1)
    for path in (STARTER, REFERENCE):
        text = path.read_text()
        assert "principal is AgentCore::OAuthUser" in text, path.name
        assert RESOURCE in text, path.name
        assert "resource is AgentCore::Gateway" not in text, path.name


def test_the_claim_is_on_the_access_token_not_the_id_token() -> None:
    """`cognito:username` is on the ID token; the Gateway validates the access token."""
    for path in (STARTER, REFERENCE):
        assert "cognito:username" not in path.read_text(), path.name


def test_the_seed_names_exactly_these_shoppers() -> None:
    seed = (_REPO / "scripts" / "migrations" / "002_seed.sql").read_text()
    for username, customer_id in SHOPPERS.items():
        assert re.search(rf"'{customer_id}', '[^']+', '{username}'", seed), customer_id


def test_the_trigger_maps_users_from_the_row_level_security_column() -> None:
    deployer = DEPLOYER.read_text()
    assert "SELECT cognito_username, id FROM pellier.customers" in deployer
    assert "current_setting('pellier.principal_username', true)" in (
        _REPO / "scripts" / "migrations" / "001_schema.sql"
    ).read_text()
    trigger = TRIGGER.read_text()
    assert "clientMetadata" not in trigger.split("def handler", 1)[1]


@pytest.mark.parametrize("path", [STARTER, REFERENCE])
def test_no_file_carries_an_account_specific_arn(path: pathlib.Path) -> None:
    assert not re.search(r"arn:aws:bedrock-agentcore:[a-z0-9-]+:\d{12}:", path.read_text()), path.name
