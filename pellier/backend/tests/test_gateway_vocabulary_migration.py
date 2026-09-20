"""The in-place Gateway/Cedar vocabulary migration, as a tested contract.

This exists so the migration is repeatable rather than a one-off admin script. The
assertions below are mostly about refusing to run: a migration that writes to the
wrong account, or against unexpected live state, or that quietly widens its own
blast radius, is far more dangerous than one that stops.

Every AWS interaction is faked. Nothing here touches a real account.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "scripts" / "deploy"
for path in (str(DEPLOY), str(REPO / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

# The migration's environment pins are read from the environment, because they
# identify one published account's Gateway, policy engine, Aurora cluster and Lambda
# build. Set BEFORE importing `ownership`: that module binds them once at import, and
# a preflight comparing two empty strings would pass against any account at all.
#
# These are placeholders, and they have to be. A test that reused the real ids would
# put them back into tracked source, and a test that left them empty would assert
# nothing: `_preflight` compares the observed account against the pin, so the pin
# must be a value the fakes can be wrong about.
FAKE_ACCOUNT = "123456789012"
os.environ.setdefault("PELLIER_EXPECTED_ACCOUNT", FAKE_ACCOUNT)
os.environ.setdefault("PELLIER_EXPECTED_GATEWAY_ID", "pellier-gateway-testfixture")
os.environ.setdefault(
    "PELLIER_EXPECTED_POLICY_ENGINE_ID", "pellier_policy_engine-testfixture"
)
os.environ.setdefault("PELLIER_EXPECTED_DB_CLUSTER", "pellier-test-cluster")
os.environ.setdefault("PELLIER_EXPECTED_EXPERIENCE_SHA", "testfixtureSha256Value=")


def _module():
    """Load the migration module fresh so module state cannot leak between tests."""
    spec = importlib.util.spec_from_file_location(
        "pellier_gateway_migration", REPO / "scripts" / "migrate_gateway_vocabulary.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before executing. `@dataclass` resolves `cls.__module__` through
    # sys.modules to look for KW_ONLY, so a module that is never registered makes
    # every dataclass in it fail to build with a bare AttributeError.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


MIG = _module()
import ownership  # noqa: E402

# No test may sleep. The poll loops back off five seconds between reads, which is
# right against a real control plane and pointless against a fake.
MIG.time.sleep = lambda _seconds: None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

LIVE_TARGET_TOOLS = {
    "pellier-discovery-search-target": [
        "find_pieces", "find_pieces_hybrid", "explore_collection",
        "floor_check", "running_low", "restock_shelf",
    ],
    "pellier-value-pricing-target": ["price_intelligence", "side_by_side"],
    "pellier-concierge-experience-target": ["process_return", "escalate_to_stylist"],
    "pellier-curation-recommendation-target": [
        "preference_snapshot", "trace_receipt", "whats_trending",
        "returns_and_care", "style_match",
    ],
}

# These three statements are the live Cedar definitions, shape for shape. An
# earlier version of this fake built the permit by string-replacing "forbid" with
# "permit" in the statement below, which produced a permit carrying the *negated*
# condition — a policy pair that live does not have and that no rewrite test
# could then meaningfully check.
GATEWAY_RESOURCE = (
    'resource == AgentCore::Gateway::'
    '"arn:aws:bedrock-agentcore:us-east-1:' + FAKE_ACCOUNT + ':gateway/'
    + ownership.EXPECTED_GATEWAY_ID + '"'
)

BASELINE_STATEMENT = f"permit(principal, action, {GATEWAY_RESOURCE});"

PERMIT_STATEMENT = (
    'permit(principal, action == AgentCore::Action::'
    '"pellier-concierge-experience-target___process_return", '
    f'{GATEWAY_RESOURCE})\n'
    'when {\n  context.input has reason && context.input.reason == "damaged"\n};'
)

# What process_return_allow_damaged holds live after Phase 1: the unconditional
# target-level forbid. Retained in the fake because the remaining phases read it,
# and because the cleanup phase must rewrite it to a canonical permit.
GROUP_FORBID_STATEMENT = (
    'forbid(principal, action in AgentCore::Action::'
    '"pellier-concierge-experience-target", '
    f'{GATEWAY_RESOURCE});'
)

FORBID_STATEMENT = (
    'forbid(principal, action == AgentCore::Action::'
    '"pellier-concierge-experience-target___process_return", '
    f'{GATEWAY_RESOURCE})\n'
    'when {\n  !(context.input has reason) || context.input.reason != "damaged"\n};'
)


def _live_target(name: str, tools: List[str], status: str = "READY") -> Dict[str, Any]:
    return {
        # Distinct ids. Every target name ends in "-target", so a suffix-derived
        # id gave all four the same value and the fake returned one target four
        # times — which the plan then reported as four identical updates.
        "targetId": "tid-" + name.replace("pellier-", "").replace("-target", ""),
        "name": name,
        "status": status,
        "description": f"{name} description",
        "targetConfiguration": {
            "mcp": {
                "lambda": {
                    "lambdaArn": f"arn:aws:lambda:us-east-1:{FAKE_ACCOUNT}:function:{name}",
                    "toolSchema": {"inlinePayload": [{"name": t} for t in tools]},
                }
            }
        },
        "credentialProviderConfigurations": [
            {"credentialProviderType": "GATEWAY_IAM_ROLE"}
        ],
        # Live carries this, and it is the field a rename would most easily drop:
        # the header it allows is how the policy session id reaches the Gateway.
        # The fake lacked it, so the preservation test passed vacuously.
        "metadataConfiguration": {
            "allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"]
        },
    }


def _live_policies() -> List[Dict[str, Any]]:
    return [
        {
            "policyId": "baseline_permit_gateway_tools-aaa",
            "name": "baseline_permit_gateway_tools",
            "enforcementMode": "ACTIVE",
            "status": "ACTIVE",
            "definition": {"policy": {"statement": BASELINE_STATEMENT}},
        },
        {
            "policyId": "process_return_allow_damaged-bbb",
            "name": "process_return_allow_damaged",
            "enforcementMode": "ACTIVE",
            "status": "ACTIVE",
            # CURRENT LIVE STATE, not the original. Phase 1 repurposed this
            # policy into the target-level group forbid, and the fake must model
            # what the next phase will actually read. Modelling the old permit
            # made Phase A look like it left two matching permits on the
            # experience target when live it leaves zero.
            "definition": {"policy": {"statement": GROUP_FORBID_STATEMENT}},
        },
        {
            "policyId": "process_return_damaged_only-ccc",
            "name": "process_return_damaged_only",
            "enforcementMode": "ACTIVE",
            "status": "ACTIVE",
            "definition": {"policy": {"statement": FORBID_STATEMENT}},
        },
    ]


class FakeControl:
    def __init__(self, *, target_status: str = "READY", update_status: str = "READY") -> None:
        self.meta = SimpleNamespace(region_name=ownership.EXPECTED_REGION)
        self.targets = {
            name: _live_target(name, tools, target_status)
            for name, tools in LIVE_TARGET_TOOLS.items()
        }
        self.policies = {p["policyId"]: p for p in _live_policies()}
        self.update_status = update_status
        self.target_updates: List[Dict[str, Any]] = []
        self.policy_updates: List[Dict[str, Any]] = []
        self.gateway_updates: List[Dict[str, Any]] = []

    # reads
    def get_gateway(self, **_: Any) -> Dict[str, Any]:
        return {
            "gatewayId": ownership.EXPECTED_GATEWAY_ID,
            "policyEngineConfiguration": {"mode": "ENFORCE"},
            "roleArn": f"arn:aws:iam::{FAKE_ACCOUNT}:role/gw",
            "authorizerType": "CUSTOM_JWT",
        }

    def list_gateway_targets(self, **_: Any) -> Dict[str, Any]:
        return {"items": [{"targetId": t["targetId"]} for t in self.targets.values()]}

    def get_gateway_target(self, *, targetId: str, **_: Any) -> Dict[str, Any]:
        for t in self.targets.values():
            if t["targetId"] == targetId:
                return copy.deepcopy(t)
        raise KeyError(targetId)

    def list_policies(self, **_: Any) -> Dict[str, Any]:
        # Live returns full summaries here, including name and enforcementMode.
        # A fake that returned only the id let `assert_no_mode_drift` pass
        # vacuously.
        return {"policies": [copy.deepcopy(p) for p in self.policies.values()]}

    def get_policy(self, *, policyId: str, **_: Any) -> Dict[str, Any]:
        return copy.deepcopy(self.policies[policyId])

    # writes
    def update_gateway_target(self, **kwargs: Any) -> Dict[str, Any]:
        self.target_updates.append(copy.deepcopy(kwargs))
        for t in self.targets.values():
            if t["targetId"] == kwargs["targetId"]:
                t["targetConfiguration"] = kwargs["targetConfiguration"]
                t["status"] = self.update_status
        return {}

    def update_policy(self, **kwargs: Any) -> Dict[str, Any]:
        self.policy_updates.append(copy.deepcopy(kwargs))
        self.policies[kwargs["policyId"]]["definition"] = kwargs["definition"]
        self.policies[kwargs["policyId"]]["status"] = self.update_status
        return {}

    def update_gateway(self, **kwargs: Any) -> Dict[str, Any]:
        self.gateway_updates.append(copy.deepcopy(kwargs))
        return {}


class FakeSts:
    def __init__(self, account: str = ownership.EXPECTED_ACCOUNT) -> None:
        self.account = account

    def get_caller_identity(self) -> Dict[str, str]:
        return {"Account": self.account}


class FakeLambda:
    def __init__(self, sha: str = ownership.EXPECTED_EXPERIENCE_SHA) -> None:
        self.sha = sha

    def get_function_configuration(self, **_: Any) -> Dict[str, str]:
        return {"CodeSha256": self.sha}


class FakeCfn:
    def __init__(self, status: str = "UPDATE_COMPLETE") -> None:
        self.status = status

    def describe_stacks(self, **_: Any) -> Dict[str, Any]:
        return {"Stacks": [{"StackStatus": self.status}]}

    def describe_stack_resources(self, **_: Any) -> Dict[str, Any]:
        return {
            "StackResources": [
                {"ResourceType": "AWS::BedrockAgentCore::Memory"},
                {"ResourceType": "AWS::BedrockAgentCore::Runtime"},
                {"ResourceType": "AWS::IAM::Role"},
            ]
        }


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch: pytest.MonkeyPatch):
    def unexpected_transport(*_args, **_kwargs):
        pytest.fail("No real AWS, database or external CLI calls are allowed.")

    monkeypatch.setattr("boto3.client", unexpected_transport)
    monkeypatch.setattr("psycopg.connect", unexpected_transport)
    monkeypatch.setattr("subprocess.run", unexpected_transport)
    monkeypatch.setattr(MIG.time, "sleep", lambda *_: None)
    monkeypatch.setenv("AWS_REGION", ownership.EXPECTED_REGION)
    monkeypatch.setenv("DB_HOST", f"{ownership.EXPECTED_DB_CLUSTER}.cluster-x.us-east-1.rds.amazonaws.com")
    yield


def _preflight(control=None, sts=None, lam=None, cfn=None):
    control = control or FakeControl()
    live = MIG.read_live(control)
    return MIG.preflight(control, sts or FakeSts(), lam or FakeLambda(), cfn or FakeCfn(), live), live, control


# ---------------------------------------------------------------------------
# Canonical vocabulary is derived, not asserted by count
# ---------------------------------------------------------------------------

def test_the_canonical_schema_is_derived_and_internally_sound() -> None:
    result = MIG.validate_canonical()
    assert result["toolCount"] == len(set(result["tools"])), "duplicate tool names"
    assert len(result["targetForTool"]) == result["toolCount"], "a tool has two targets"
    for expected in (
        "check_inventory", "search_products", "search_products_hybrid",
        "initiate_return", "issue_credit", "escalate_to_human",
        "get_customer_preferences", "get_audit_trail",
    ):
        assert expected in result["tools"], f"{expected} missing from the canonical set"
    assert set(result["targets"]) == set(ownership.EXPECTED_TARGET_NAMES)


def test_the_canonical_schema_publishes_no_retired_name() -> None:
    tools = set(MIG.validate_canonical()["tools"])
    leaked = sorted(tools & set(MIG.RETIRED_TO_CURRENT))
    assert not leaked, f"canonical schema still publishes retired names: {leaked}"


def test_every_retired_name_maps_to_a_published_tool() -> None:
    tools = set(MIG.validate_canonical()["tools"])
    for retired, current in MIG.RETIRED_TO_CURRENT.items():
        assert current in tools, f"{retired} maps to {current}, which is not published"


# ---------------------------------------------------------------------------
# Preflight refuses on any mismatch
# ---------------------------------------------------------------------------

def test_preflight_passes_on_the_expected_environment() -> None:
    pre, _, _ = _preflight()
    assert pre.ok, f"preflight failed on the expected environment: {pre.checks}"


def test_a_wrong_account_is_a_hard_stop() -> None:
    pre, _, _ = _preflight(sts=FakeSts(account="111122223333"))
    assert not pre.ok
    assert pre.checks["account"]["ok"] is False


def test_a_wrong_region_is_a_hard_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    pre, _, _ = _preflight()
    assert not pre.ok
    assert pre.checks["region"]["ok"] is False


def test_an_unexpected_target_set_is_a_hard_stop() -> None:
    control = FakeControl()
    control.targets.pop("pellier-value-pricing-target")
    pre, _, _ = _preflight(control=control)
    assert not pre.ok
    assert pre.checks["targetNames"]["ok"] is False


def test_a_target_not_ready_is_a_hard_stop() -> None:
    pre, _, _ = _preflight(control=FakeControl(target_status="UPDATING"))
    assert not pre.ok
    assert pre.checks["targetStatuses"]["ok"] is False


def test_an_unexpected_policy_set_is_a_hard_stop() -> None:
    control = FakeControl()
    control.policies.pop("process_return_damaged_only-ccc")
    pre, _, _ = _preflight(control=control)
    assert not pre.ok
    assert pre.checks["policyNames"]["ok"] is False


def test_a_lambda_that_is_not_the_phase_b1_build_is_a_hard_stop() -> None:
    """Renaming tools onto an implementation that cannot serve them is the risk."""
    pre, _, _ = _preflight(lam=FakeLambda(sha="someOtherBuild="))
    assert not pre.ok
    assert pre.checks["experienceLambdaSha"]["ok"] is False


def test_a_stack_not_in_update_complete_is_a_hard_stop() -> None:
    pre, _, _ = _preflight(cfn=FakeCfn(status="UPDATE_ROLLBACK_COMPLETE"))
    assert not pre.ok


def test_a_wrong_aurora_cluster_is_a_hard_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_HOST", "some-other-cluster.cluster-x.us-east-1.rds.amazonaws.com")
    pre, _, _ = _preflight()
    assert not pre.ok
    assert pre.checks["auroraCluster"]["ok"] is False


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# The service accepts a header on read that it refuses on write
# ---------------------------------------------------------------------------

def test_the_restricted_header_is_filtered_not_resent() -> None:
    """Resending what GetGatewayTarget returned is a ValidationException.

    All four targets were created carrying
    `allowedRequestHeaders: [x-amzn-bedrock-agentcore-policy-session-id]`. The
    service later made that header service-managed, so UpdateGatewayTarget now
    rejects it: "Header '...' is restricted and cannot be configured". Read/write
    asymmetry, so a faithful round-trip is impossible.
    """
    metadata = {
        "allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"]
    }
    value, dropped = MIG._writable_metadata(metadata)
    assert value is None, "nothing writable remained, so the field must be omitted"
    assert dropped == ["x-amzn-bedrock-agentcore-policy-session-id"]


def test_a_writable_header_alongside_a_restricted_one_survives() -> None:
    value, dropped = MIG._writable_metadata(
        {"allowedRequestHeaders": [
            "x-amzn-bedrock-agentcore-policy-session-id",
            "x-pellier-correlation-id",
        ]}
    )
    assert value == {"allowedRequestHeaders": ["x-pellier-correlation-id"]}
    assert dropped == ["x-amzn-bedrock-agentcore-policy-session-id"]


def test_unrelated_metadata_keys_are_preserved() -> None:
    value, dropped = MIG._writable_metadata(
        {"allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"],
         "someOtherKey": {"a": 1}}
    )
    assert value == {"someOtherKey": {"a": 1}}
    assert dropped == ["x-amzn-bedrock-agentcore-policy-session-id"]


def test_the_restricted_header_is_never_sent_in_an_update_request() -> None:
    control = FakeControl()
    plan = _plan(control)
    MIG.apply_one_target(control, MIG.read_live(control), plan["phases"][1]["targetUpdates"][0])
    sent = json.dumps(control.target_updates[-1])
    assert "policy-session-id" not in sent, (
        "the request still carries the header the service refuses"
    )


def test_allowed_response_headers_survive_the_normalization() -> None:
    value, dropped = MIG._writable_metadata({
        "allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"],
        "allowedResponseHeaders": ["x-pellier-turn-id"],
    })
    assert value == {"allowedResponseHeaders": ["x-pellier-turn-id"]}
    assert dropped == ["x-amzn-bedrock-agentcore-policy-session-id"]


def test_allowed_query_parameters_survive_the_normalization() -> None:
    value, dropped = MIG._writable_metadata({
        "allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"],
        "allowedQueryParameters": ["persona"],
    })
    assert value == {"allowedQueryParameters": ["persona"]}
    assert dropped == ["x-amzn-bedrock-agentcore-policy-session-id"]


def test_stripping_the_only_header_never_emits_an_empty_list() -> None:
    """An empty allowedRequestHeaders and an absent one are not documented to mean
    the same thing, so the field is dropped rather than emptied."""
    value, _ = MIG._writable_metadata(
        {"allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"]}
    )
    assert value is None
    value, _ = MIG._writable_metadata({
        "allowedRequestHeaders": ["x-amzn-bedrock-agentcore-policy-session-id"],
        "allowedResponseHeaders": ["x-keep"],
    })
    assert "allowedRequestHeaders" not in value


def test_no_replacement_header_is_manufactured() -> None:
    """A custom copy would recreate propagation Pellier does not consume."""
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "x-pellier-policy-session" not in source
    control = FakeControl()
    plan = _plan(control)
    MIG.apply_one_target(control, MIG.read_live(control), plan["phases"][1]["targetUpdates"][0])
    sent = json.dumps(control.target_updates[-1]).lower()
    assert "policy-session" not in sent


def test_no_pellier_runtime_path_reads_the_header_at_the_target() -> None:
    """The Lambda and the tool layer must not depend on receiving it.

    Grep-based by necessity, but scoped to the code that actually runs at the
    target: if any of it read the header, omitting the propagation entry would be
    a functional regression rather than a normalization.
    """
    roots = [
        REPO / "scripts" / "deploy",
        REPO / "pellier" / "backend" / "services",
        REPO / "pellier" / "backend" / "routes",
    ]
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            if "migrate_gateway_vocabulary" in path.name:
                continue
            text = path.read_text(errors="ignore")
            if "policy-session-id" in text or "policy_session_id" in text:
                offenders.append(str(path.relative_to(REPO)))
    assert not offenders, (
        "runtime code references the policy-session header; omitting its target "
        f"propagation entry may be a regression, not a normalization: {offenders}"
    )


def test_the_terminology_is_frozen_correctly() -> None:
    """`restricted` reserves target propagation; it does not mean AWS owns the header.

    A caller may still supply the policy-session id to the Gateway, and for
    temporal policies the caller owns creating it. Describing it as
    "service-managed" would mislead whoever next reads this and could lead them to
    stop sending it.
    """
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "POLICY SESSION" in source and "TARGET PROPAGATION" in source
    assert "NOT service-managed" in source
    assert "reserved from it" in source or "reserved from" in source
    # The two mechanisms must be named as distinct, not conflated.
    assert "propagation to the target" in source


def test_the_plan_declares_the_normalization_before_the_write() -> None:
    update = _plan(FakeControl())["phases"][1]["targetUpdates"][0]
    norms = update["serviceNormalization"]
    assert len(norms) == 1
    n = norms[0]
    assert n["field"] == "metadataConfiguration.allowedRequestHeaders"
    assert n["before"] == ["x-amzn-bedrock-agentcore-policy-session-id"]
    assert n["omittedFromWrite"] == ["x-amzn-bedrock-agentcore-policy-session-id"]
    assert n["sent"] is None
    assert "none" in n["pellierDependency"]
    assert "reserved" in n["reason"]


def test_a_target_without_the_legacy_header_declares_no_normalization() -> None:
    """The declaration must be derived from live state, not hardcoded."""
    control = FakeControl()
    control.targets[RETURN_TARGET]["metadataConfiguration"] = {
        "allowedRequestHeaders": ["x-pellier-correlation-id"]
    }
    update = _plan(control)["phases"][1]["targetUpdates"][0]
    assert update["serviceNormalization"] == []
    MIG.apply_one_target(control, MIG.read_live(control), update)
    assert control.target_updates[-1]["metadataConfiguration"] == {
        "allowedRequestHeaders": ["x-pellier-correlation-id"]
    }


# ---------------------------------------------------------------------------
# Measured 2026-08-26: a target action group is compiled at policy-save time
# ---------------------------------------------------------------------------

def test_the_module_does_not_claim_a_group_forbid_spans_a_rename() -> None:
    """The premise was disproved live; it must not survive in the source.

    Phase 2 renamed the target's tools while the target-level forbid was ACTIVE,
    and both renamed children executed. Group membership is resolved when the
    policy is saved, so a tool added later is not a member. Anyone reading this
    module must not find the old claim stated as fact.
    """
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "compiled at policy-save time" in source
    assert "DISPROVED LIVE" in source
    forbidden_claims = (
        "so it stays valid across the schema change that renames",
        "stays valid while they are renamed. This is what makes the cutover",
    )
    for claim in forbidden_claims:
        assert claim not in source, f"disproved claim still asserted: {claim!r}"


def test_the_recorded_lever_is_withdrawing_the_permit_not_adding_a_forbid() -> None:
    """The finding's actionable consequence must be written down, not just the bug."""
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "withdraw the broad PERMIT" in source or "withdrawing the broad PERMIT" in source
    assert "No permit" in source and "requires no action name" in source


# ---------------------------------------------------------------------------
# Default-deny cutover: safety is permit withdrawal, never a forbid
# ---------------------------------------------------------------------------

RETURN_TARGET = "pellier-concierge-experience-target"


def _plan(control: "FakeControl") -> Dict[str, Any]:
    return MIG.build_plan(MIG.read_live(control), MIG.validate_canonical())


def test_the_narrowed_baseline_names_exactly_the_unaffected_actions() -> None:
    control = FakeControl()
    live = MIG.read_live(control)
    ids = MIG.unaffected_action_ids(live)
    assert len(ids) == 11, ids
    assert all(not a.startswith(f"{RETURN_TARGET}___") for a in ids)
    statement = MIG.narrowed_baseline_statement(live)
    for action in ids:
        assert f'AgentCore::Action::"{action}"' in statement


def test_customer_scoped_recommendation_actions_stay_default_denied() -> None:
    """Retired target aliases must not bypass the scoped fresh-stack policies."""
    live = MIG.read_live(FakeControl())
    recommendation = next(
        target
        for target in live["targets"]
        if target["name"] == MIG.RECOMMENDATION_TARGET_NAME
    )
    published = set(MIG._tool_names(recommendation))
    expected = {"preference_snapshot", "trace_receipt"}
    assert expected <= published

    for statement in (
        MIG.narrowed_baseline_statement(live),
        MIG.final_baseline_statement(_migrated_live()),
    ):
        parsed = MIG.parse_statement("customer-read-default-deny", statement)
        for tool in MIG.CUSTOMER_SCOPED_READ_TOOL_NAMES:
            action = f"{MIG.RECOMMENDATION_TARGET_NAME}___{tool}"
            assert action not in (parsed.actions or ()), action
            assert MIG.evaluate([parsed], action, "damaged") == "DENY", action


def test_the_narrowed_baseline_excludes_every_experience_action() -> None:
    statement = MIG.narrowed_baseline_statement(MIG.read_live(FakeControl()))
    for tool in ("process_return", "escalate_to_stylist",
                 "initiate_return", "escalate_to_human",
                 "issue_credit", "get_ticket_history"):
        assert f"{RETURN_TARGET}___{tool}" not in statement, tool


def test_the_narrowed_baseline_uses_explicit_ids_not_target_groups() -> None:
    """Group membership compiles at save time, so it cannot be a safety boundary."""
    statement = MIG.narrowed_baseline_statement(MIG.read_live(FakeControl()))
    assert "action in [" in statement
    assert 'action in AgentCore::Action::"pellier-' not in statement


def test_the_narrowed_baseline_is_unconditional() -> None:
    statement = MIG.narrowed_baseline_statement(MIG.read_live(FakeControl()))
    assert "when" not in statement and "unless" not in statement
    assert "context" not in statement
    assert statement.startswith("permit(")


def test_a_baseline_that_would_leak_an_experience_action_is_refused() -> None:
    control = FakeControl()
    live = MIG.read_live(control)
    # Force the leak the guard exists to catch.
    original = MIG.unaffected_action_ids
    MIG.unaffected_action_ids = lambda _live: [f"{RETURN_TARGET}___process_return"]
    try:
        with pytest.raises(SystemExit, match="would still cover"):
            MIG.narrowed_baseline_statement(live)
    finally:
        MIG.unaffected_action_ids = original


def test_every_phase_touches_one_resource_each() -> None:
    plan = _plan(FakeControl())
    assert [e["phase"] for e in plan["phases"]] == list(MIG.PHASES)
    expected = {
        "default-deny-quiesce": (1, 0),
        "target-canonical": (0, 1),
        "return-forbid-canonical": (1, 0),
        "allow-damaged-canonical": (1, 0),
        "explicit-baseline-final": (1, 0),
        "restore-broad-permit": (1, 0),
    }
    for entry in plan["phases"]:
        counts = (len(entry["policyUpdates"]), len(entry["targetUpdates"]))
        assert counts == expected[entry["phase"]], f"{entry['phase']}: {counts}"


def test_no_permit_matches_an_experience_action_during_the_closed_phases() -> None:
    """The load-bearing assertion of the whole design."""
    rows = {r["phase"]: r for r in MIG.phase_states(_plan(FakeControl()))}
    for phase in ("default-deny-quiesce", "target-canonical",
                  "return-forbid-canonical"):
        row = rows[phase]
        assert row["maxMatchingPermits"] == 0, f"{phase}: {row['permitCoverage']}"
        for action, decision in row["decisions"].items():
            assert decision["non_damaged"] == "DENY", (phase, action)
            assert decision["damaged"] == "DENY", (phase, action)
        assert row["targetOpen"] is False, phase


def test_the_canonical_names_are_default_denied_immediately_after_the_rename() -> None:
    """The exact condition the forbid-based design failed."""
    row = next(r for r in MIG.phase_states(_plan(FakeControl()))
               if r["phase"] == "target-canonical")
    assert sorted(row["targetTools"]) == ["escalate_to_human", "initiate_return"]
    for action in row["callable"]:
        assert row["permitCoverage"][action] == [], action
        assert row["decisions"][action]["damaged"] == "DENY", action


def test_restoring_the_broad_permit_is_the_unquiesce() -> None:
    plan = _plan(FakeControl())
    assert plan["unquiesceEvent"] == "restore-broad-permit"
    rows = {r["phase"]: r for r in MIG.phase_states(plan)}
    assert rows["return-forbid-canonical"]["targetOpen"] is False
    assert rows["restore-broad-permit"]["targetOpen"] is True


def test_the_restrictive_forbid_is_canonical_before_the_permit_returns() -> None:
    plan = _plan(FakeControl())
    order = [e["phase"] for e in plan["phases"]]
    assert order.index("return-forbid-canonical") < order.index("restore-broad-permit")
    rows = {r["phase"]: r for r in MIG.phase_states(plan)}
    final = rows["restore-broad-permit"]
    action = f"{RETURN_TARGET}___initiate_return"
    assert final["decisions"][action]["non_damaged"] == "DENY"
    assert final["decisions"][action]["damaged"] == "ALLOW"


def test_the_broad_permit_is_restored_to_the_derived_original_not_to_live_state() -> None:
    """The restore target must be the ORIGINAL broad permit, not whatever is live.

    `build_plan` re-derives from deployed state, so once the quiesce had landed
    `baseline_before` WAS the narrowed statement and the restore phase computed
    ``after`` = that same narrowed statement — restoring the quiesce onto itself while
    reporting a successful unquiesce. The per-phase proof caught it: `escalate_to_human`
    stayed DENY after the phase whose entire purpose is to permit it again.
    """
    plan = _plan(FakeControl())
    by_name = {e["phase"]: e for e in plan["phases"]}
    narrow = by_name["default-deny-quiesce"]
    restore = by_name["restore-broad-permit"]

    after = restore["policyUpdates"][0]["after"]
    assert after == MIG.broad_baseline_statement()
    parsed = MIG.parse_statement(MIG.BASELINE_POLICY_NAME, after)
    # `actions is None` is the bare `action` form: any action on this gateway.
    assert parsed.actions is None, f"the restored permit is not broad: {after}"
    assert parsed.condition == "none"
    assert MIG.gateway_resource() in after

    # And it is NOT the narrowed statement, which is what the bug produced.
    assert after != narrow["policyUpdates"][0]["after"]
    # `before` is whatever is deployed when the plan is built, so it is deliberately
    # NOT asserted against the narrowed statement: that only holds once the quiesce
    # has landed, and an assertion that depends on how far the migration has already
    # run is a test of the environment rather than of the plan.
    assert restore["policyUpdates"][0]["before"] == (
        MIG.read_live(FakeControl())["policies"] and
        next(p["definition"]["policy"]["statement"]
             for p in MIG.read_live(FakeControl())["policies"]
             if p["name"] == MIG.BASELINE_POLICY_NAME)
    )


def test_a_capture_that_disagrees_with_the_derived_broad_permit_stops_the_run(
    tmp_path,
) -> None:
    """The derived statement is cross-checked against the pre-migration capture."""
    live = MIG.read_live(FakeControl())
    # A capture whose baseline was broad but written differently must not be assumed
    # equivalent; the service accepted the captured form, so a mismatch is a stop.
    live["policies"][0]["definition"] = {"policy": {"statement":
        'permit(principal, action, resource == AgentCore::Gateway::"arn:other");'}}
    capture = MIG._capture_run(
        tmp_path, MIG.PreflightResult(ok=True), _plan(FakeControl()),
        live, MIG.validate_canonical(),
    )
    with pytest.raises(SystemExit) as exc:
        MIG.assert_broad_baseline_matches_capture(capture)
    assert "STOP and reconcile" in str(exc.value)


def test_a_matching_capture_passes_the_cross_check(tmp_path) -> None:
    capture = MIG._capture_run(
        tmp_path, MIG.PreflightResult(ok=True), _plan(FakeControl()),
        MIG.read_live(FakeControl()), MIG.validate_canonical(),
    )
    MIG.assert_broad_baseline_matches_capture(capture)


def test_a_missing_capture_is_advisory_not_fatal(tmp_path) -> None:
    """Captures live outside the repository, so absence cannot be a hard stop."""
    MIG.assert_broad_baseline_matches_capture(tmp_path / "does-not-exist")


def test_a_group_forbid_is_never_the_safety_proof() -> None:
    """Measured: group membership does not follow a schema change."""
    compiled = (f"{RETURN_TARGET}___process_return",)
    stmt = MIG.parse_statement("stale", MIG.quiesce_statement(), compiled)
    assert stmt.groups == (RETURN_TARGET,)
    assert stmt.covers(f"{RETURN_TARGET}___process_return")
    assert not stmt.covers(f"{RETURN_TARGET}___initiate_return"), (
        "the evaluator models a group as covering a child added after the policy "
        "was saved, which is the dangerous direction and contradicts the measurement"
    )
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "MATCHING PERMIT COUNT" in source
    assert "not forbid coverage" in source


def test_created_at_is_never_used_as_provenance() -> None:
    """UpdateGatewayTarget rewrote createdAt twice while targetId held.

    Asserts it is never READ, not that the word never appears: the module
    deliberately documents why it is ignored, and a mention-based check would
    forbid explaining the finding.
    """
    for path in ("scripts/migrate_gateway_vocabulary.py", "scripts/deploy/ownership.py"):
        source = (REPO / path).read_text()
        for usage in ('["createdAt"]', "get('createdAt')", 'get("createdAt")',
                      ".createdAt", "['createdAt']"):
            assert usage not in source, (
                f"{path} reads createdAt via {usage}; it is rewritten by an "
                "in-place update and is not provenance evidence"
            )


def test_the_plan_still_adds_no_new_tool() -> None:
    plan = _plan(FakeControl())
    update = plan["phases"][1]["targetUpdates"][0]
    assert len(update["after"]) == len(update["before"]) == 2
    assert set(plan["deferredNewTools"]) == set(MIG.DEFERRED_NEW_TOOLS)


def test_the_plan_never_touches_a_target_other_than_the_return_target() -> None:
    plan = _plan(FakeControl())
    targets = {u["target"] for e in plan["phases"] for u in e["targetUpdates"]}
    assert targets == {RETURN_TARGET}


def test_the_gateway_policy_mode_is_never_changed_by_the_plan() -> None:
    plan = _plan(FakeControl())
    assert plan["gateway"]["gatewayPolicyMode"] == "ENFORCE"
    assert plan["gateway"]["gatewayPolicyModeChanged"] is False


def test_no_phase_cascades() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    dispatch = source[source.index('print(f"\\n=== APPLYING PHASE'):]
    dispatch = dispatch[: dispatch.index("phase complete")]
    assert dispatch.count("apply_policy_update(") == 1
    assert dispatch.count("apply_one_target(") == 1


# ---------------------------------------------------------------------------
# Phase B gates
# ---------------------------------------------------------------------------

def _guard_source(phase: str) -> str:
    """The guard block covering one phase, ending at the next top-level phase guard.

    Line-wise on INDENTATION, not on substring position. Two earlier versions of this
    helper each read the wrong code:

      * slicing to `assert_no_mode_drift` let a later phase's guard leak into an
        earlier phase's slice;
      * searching for the next `if args.phase` substring stopped at an inner,
        phase-scoped condition WITHIN the block it was trying to read.

    A top-level guard in `main()` sits at exactly four spaces of indent, so that is
    the only thing treated as a boundary.
    """
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    lines = source.splitlines()

    def is_top_level_guard(line: str) -> bool:
        return line.startswith("    if args.phase") and not line.startswith("     ")

    starts = [
        i for i, line in enumerate(lines)
        if is_top_level_guard(line) and f'"{phase}"' in line
    ]
    if not starts:
        raise AssertionError(f"no guard block found for phase {phase}")

    # EVERY top-level block that names this phase, concatenated. A phase's guard can
    # legitimately be split — the two reopen phases share one block of preconditions
    # and the unquiesce carries a second, phase-specific one — and returning only the
    # first made an assertion about the second read the wrong code.
    blocks = []
    for begin in starts:
        stop = len(lines)
        for i in range(begin + 1, len(lines)):
            if is_top_level_guard(lines[i]) or "assert_no_mode_drift(control)" in lines[i]:
                stop = i
                break
        blocks.append("\n".join(lines[begin:stop]))
    return "\n".join(blocks)


def test_phase_b_is_gated_on_zero_matching_permits() -> None:
    """Not on the target-group forbid, which was measured not to follow a rename."""
    guard = _guard_source("target-canonical")
    assert "parse_statement" in guard
    assert 'parsed.effect != "permit"' in guard
    assert "Run --phase default-deny-quiesce first" in guard
    assert "QUIESCE_POLICY_NAME" not in guard, (
        "the guard still keys on the group forbid rather than permit coverage"
    )


def test_phase_b_gate_also_checks_the_ids_it_is_about_to_publish() -> None:
    """A permit matching the canonical name must block the rename too."""
    guard = _guard_source("target-canonical")
    assert "canonical_ids" in guard
    assert "set(current) | set(canonical_ids)" in guard


def test_the_unquiesce_guard_is_keyed_to_a_phase_that_exists() -> None:
    """An earlier version keyed on a retired name, so it could never fire."""
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    guarded = set(re.findall(r'if args\.phase == "([a-z-]+)":', source))
    assert guarded <= set(MIG.PHASES), f"guard names not in PHASES: {guarded - set(MIG.PHASES)}"
    assert "restore-broad-permit" in guarded, "the unquiesce is unguarded"


def test_rollback_of_phase_b_keeps_the_baseline_narrowed(tmp_path: Path) -> None:
    """Governance before availability: rolling back the rename must NOT reopen."""
    control = FakeControl()
    live = MIG.read_live(control)
    plan = MIG.build_plan(live, MIG.validate_canonical())
    # Simulate the post-Phase-A world.
    narrowed = plan["phases"][0]["policyUpdates"][0]["after"]
    control.policies["baseline_permit_gateway_tools-aaa"]["definition"] = {
        "policy": {"statement": narrowed}
    }
    after_a = MIG.read_live(control)
    capture = MIG._capture_run(
        tmp_path, MIG.PreflightResult(ok=True), plan, after_a, MIG.validate_canonical(),
    )
    directory = capture / "rollback"

    MIG.apply_one_target(control, after_a, plan["phases"][1]["targetUpdates"][0])
    MIG.rollback(control, directory, sts=FakeSts())

    restored = sorted(
        x["name"] for x in control.targets[RETURN_TARGET]["targetConfiguration"]
        ["mcp"]["lambda"]["toolSchema"]["inlinePayload"]
    )
    assert restored == ["escalate_to_stylist", "process_return"]
    baseline = control.policies["baseline_permit_gateway_tools-aaa"]["definition"]["policy"]["statement"]
    assert "action in [" in baseline, "rollback reopened the gateway"
    assert "action," not in " ".join(baseline.split()), "the broad permit came back"


def test_a_pre_lambda_denial_expects_no_write_evidence() -> None:
    """A default-denied action never reaches the Lambda, so there is nothing to
    receipt. Asserting the expectation keeps a future 'helpful' receipt out."""
    rows = {r["phase"]: r for r in MIG.phase_states(_plan(FakeControl()))}
    row = rows["target-canonical"]
    assert row["maxMatchingPermits"] == 0
    for decision in row["decisions"].values():
        assert decision["damaged"] == "DENY"
        assert decision["non_damaged"] == "DENY"


# ---------------------------------------------------------------------------
# Phase C and the Phase D gate
# ---------------------------------------------------------------------------

def _canonical_control(control: "FakeControl") -> None:
    """Put the fake into the post-Phase-B, post-Phase-C world."""
    plan = _plan(control)
    control.policies["baseline_permit_gateway_tools-aaa"]["definition"] = {
        "policy": {"statement": plan["phases"][0]["policyUpdates"][0]["after"]}
    }
    MIG.apply_one_target(control, MIG.read_live(control), plan["phases"][1]["targetUpdates"][0])


def test_phase_c_only_renames_the_action() -> None:
    update = _plan(FakeControl())["phases"][2]["policyUpdates"][0]
    assert update["policy"] == MIG.CONTROL_POLICY_NAME
    before = MIG.parse_statement("b", update["before"])
    after = MIG.parse_statement("a", update["after"])
    assert before.effect == after.effect == "forbid"
    assert before.condition == after.condition == "not_damaged"
    assert before.groups == after.groups == ()
    assert before.actions == (f"{RETURN_TARGET}___process_return",)
    assert after.actions == (f"{RETURN_TARGET}___initiate_return",)


def test_phase_c_preserves_the_damaged_only_condition_verbatim() -> None:
    update = _plan(FakeControl())["phases"][2]["policyUpdates"][0]
    condition = '!(context.input has reason) || context.input.reason != "damaged"'
    assert condition in " ".join(update["before"].split())
    assert condition in " ".join(update["after"].split())


def test_phase_c_generates_no_action_set_and_no_group() -> None:
    update = _plan(FakeControl())["phases"][2]["policyUpdates"][0]
    assert "action in [" not in update["after"]
    assert 'action in AgentCore::Action::"pellier-' not in update["after"]
    assert update["after"].count("AgentCore::Action::") == 1


def test_phase_c_requires_a_closed_canonical_target() -> None:
    guard = _guard_source("return-forbid-canonical")
    assert "_require_closed_canonical_target" in guard
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    helper = source[source.index("def _require_closed_canonical_target"):]
    helper = helper[: helper.index("\n\ndef ")]
    assert "not the canonical" in helper, "canonical vocabulary is not required"
    assert "_live_permit_matches" in helper, "permit coverage is not checked"
    assert "is not closed" in helper


def test_the_phase_c_guard_refuses_a_retired_target() -> None:
    control = FakeControl()  # still retired
    with pytest.raises(SystemExit, match="not the canonical"):
        MIG._require_closed_canonical_target(control, "return-forbid-canonical")


def test_the_phase_c_guard_refuses_while_a_permit_can_reach_the_target() -> None:
    control = FakeControl()
    plan = _plan(control)
    # Canonical target, but the broad permit is still in place.
    MIG.apply_one_target(control, MIG.read_live(control), plan["phases"][1]["targetUpdates"][0])
    with pytest.raises(SystemExit, match="a permit can reach the target"):
        MIG._require_closed_canonical_target(control, "return-forbid-canonical")


def test_the_phase_d_guard_inspects_policy_content_not_names() -> None:
    guard = _guard_source("restore-broad-permit")
    assert "parse_statement" in guard
    assert 'parsed.condition != "not_damaged"' in guard
    assert "parsed.actions != (canonical_id,)" in guard
    assert "baseline_parsed.actions is None" in guard, (
        "Phase D does not verify the baseline is currently narrowed"
    )
    for forbidden in ("createdAt", "AgentCore::Action::\"pellier-concierge-experience-target\""):
        assert forbidden not in guard, f"the guard relies on {forbidden}"


def test_phase_d_refuses_while_the_control_still_names_the_retired_action() -> None:
    control = FakeControl()
    _canonical_control(control)  # canonical target, narrowed baseline, retired forbid
    live = MIG.read_live(control)
    ctl = next(p for p in live["policies"] if p["name"] == MIG.CONTROL_POLICY_NAME)
    parsed = MIG.parse_statement(MIG.CONTROL_POLICY_NAME,
                                ctl["definition"]["policy"]["statement"])
    assert parsed.actions == (f"{RETURN_TARGET}___process_return",), (
        "fixture no longer models the pre-Phase-C control policy"
    )
    # The guard's own condition, asserted directly.
    canonical = f"{RETURN_TARGET}___initiate_return"
    assert parsed.actions != (canonical,), "Phase D would wrongly be allowed to run"


def test_phase_c_failure_leaves_the_environment_closed() -> None:
    """A failed Phase C must not restore availability."""
    control = FakeControl()
    _canonical_control(control)
    plan = _plan(control)
    update = next(u for e in plan["phases"] for u in e["policyUpdates"]
                  if u["policy"] == MIG.CONTROL_POLICY_NAME)
    captured = control.policies[update["policyId"]]["definition"]["policy"]["statement"]
    _fail_nth_policy_write(control, 1)
    # The captured definition names a retired action, so a restore is correctly not
    # attempted; either way the run must stop and the baseline must stay narrowed.
    with pytest.raises(SystemExit, match="STOP"):
        MIG.apply_policy_update(control, update, phase="return-forbid-canonical",
                                live=MIG.read_live(control))
    baseline = control.policies["baseline_permit_gateway_tools-aaa"]["definition"]["policy"]["statement"]
    assert "action in [" in baseline, "the baseline was widened by a failure path"


def test_the_final_damaged_distinction_is_not_claimed_before_phase_d() -> None:
    """While permits are zero, BOTH damaged and non-damaged must read DENY."""
    rows = {r["phase"]: r for r in MIG.phase_states(_plan(FakeControl()))}
    row = rows["return-forbid-canonical"]
    action = f"{RETURN_TARGET}___initiate_return"
    assert row["decisions"][action]["damaged"] == "DENY", (
        "a damaged ALLOW here would be claiming the Phase D outcome early"
    )
    assert row["decisions"][action]["non_damaged"] == "DENY"
    assert rows["restore-broad-permit"]["decisions"][action]["damaged"] == "ALLOW"


# ---------------------------------------------------------------------------
# Failure semantics: a rejected UpdatePolicy still stores the definition
# ---------------------------------------------------------------------------
#
# Measured 2026-08-26: a validation failure left status=UPDATE_FAILED with the
# rejected statement stored and enforcementMode untouched. So a non-ACTIVE status
# must trigger an immediate restore from the capture, and the run stops either way.

def _fail_nth_policy_write(control: "FakeControl", *which: int) -> None:
    """Make specific policy writes settle in UPDATE_FAILED, by call ordinal.

    Per-call rather than one global status, because the interesting cases are "the
    write failed but the restore worked" and "both failed", and a single flag
    cannot express the difference.
    """
    real = control.update_policy
    seen = {"n": 0}

    def patched(**kwargs: Any) -> Dict[str, Any]:
        seen["n"] += 1
        result = real(**kwargs)
        control.policies[kwargs["policyId"]]["status"] = (
            "UPDATE_FAILED" if seen["n"] in which else "ACTIVE"
        )
        return result

    control.update_policy = patched  # type: ignore[method-assign]


def test_a_failed_policy_update_restores_the_captured_definition() -> None:
    control = FakeControl()
    plan = _plan(control)
    update = plan["phases"][0]["policyUpdates"][0]
    captured = control.policies[update["policyId"]]["definition"]["policy"]["statement"]
    _fail_nth_policy_write(control, 1)

    with pytest.raises(SystemExit, match="restored to the captured definition"):
        MIG.apply_policy_update(control, update)

    assert len(control.policy_updates) == 2, "expected one write and one restore"
    assert control.policy_updates[-1]["definition"]["policy"]["statement"] == captured
    assert control.policies[update["policyId"]]["definition"]["policy"]["statement"] == captured
    assert control.policies[update["policyId"]]["status"] == "ACTIVE"


def test_a_successful_restore_still_stops_the_run() -> None:
    """Never continue to another phase after a failed policy write."""
    control = FakeControl()
    plan = _plan(control)
    _fail_nth_policy_write(control, 1)
    with pytest.raises(SystemExit, match="STOP: do not run a later phase"):
        MIG.apply_policy_update(control, plan["phases"][0]["policyUpdates"][0])


def test_a_restore_that_does_not_land_is_fatal_and_says_so() -> None:
    control = FakeControl()
    plan = _plan(control)
    _fail_nth_policy_write(control, 1, 2)
    with pytest.raises(SystemExit, match="RESTORE DID NOT LAND"):
        MIG.apply_policy_update(control, plan["phases"][0]["policyUpdates"][0])


def test_a_stored_definition_that_differs_from_the_submission_is_restored() -> None:
    """ACTIVE is not enough; the stored Cedar must be what was submitted."""
    control = FakeControl()
    plan = _plan(control)
    update = plan["phases"][0]["policyUpdates"][0]
    real = control.update_policy

    def tamper(**kwargs: Any) -> Dict[str, Any]:
        result = real(**kwargs)
        if "action in [" in kwargs["definition"]["policy"]["statement"]:
            control.policies[kwargs["policyId"]]["definition"] = {
                "policy": {"statement": "permit(principal, action, resource);"}
            }
        return result

    control.update_policy = tamper  # type: ignore[method-assign]
    with pytest.raises(SystemExit, match="stored definition is"):
        MIG.apply_policy_update(control, update)


def test_the_enforcement_mode_and_validation_mode_are_always_sent() -> None:
    control = FakeControl()
    plan = _plan(control)
    MIG.apply_policy_update(control, plan["phases"][0]["policyUpdates"][0])
    assert control.policy_updates[-1]["enforcementMode"] == "ACTIVE"
    assert control.policy_updates[-1]["validationMode"] == "FAIL_ON_ANY_FINDINGS"


def test_a_lifecycle_status_passed_as_enforcement_mode_is_refused() -> None:
    """`status` and `enforcementMode` are different enums sharing the token ACTIVE."""
    control = FakeControl()
    plan = _plan(control)
    update = dict(plan["phases"][0]["policyUpdates"][0], enforcementMode="UPDATING")
    with pytest.raises(SystemExit, match="is not an enforcementMode"):
        MIG.apply_policy_update(control, update)
    assert control.policy_updates == []


# ---------------------------------------------------------------------------
# The one narrowly-scoped IGNORE_ALL_FINDINGS exception
# ---------------------------------------------------------------------------
#
# AgentCore separates schema checks from semantic analyzer findings. Schema checks
# run regardless of validationMode; IGNORE_ALL_FINDINGS suppresses only analyzer
# findings (overly restrictive / permissive / ineffective). Phase C trips exactly
# one: installing the damaged-only forbid while the target has zero permits makes
# the engine deny every request for that action, which is the intended migration
# state.

def _phase_c_world() -> "FakeControl":
    """Canonical target, narrowed baseline, zero permits — the Phase C world."""
    control = FakeControl()
    plan = _plan(control)
    control.policies["baseline_permit_gateway_tools-aaa"]["definition"] = {
        "policy": {"statement": plan["phases"][0]["policyUpdates"][0]["after"]}
    }
    MIG.apply_one_target(control, MIG.read_live(control), plan["phases"][1]["targetUpdates"][0])
    return control


def _desired_forbid(control: "FakeControl") -> str:
    return next(
        u for e in _plan(control)["phases"] for u in e["policyUpdates"]
        if u["policy"] == MIG.CONTROL_POLICY_NAME
    )["after"]


def test_the_exception_applies_to_exactly_one_phase_and_policy() -> None:
    control = _phase_c_world()
    live = MIG.read_live(control)
    desired = _desired_forbid(control)
    assert MIG.validation_mode_for(
        "return-forbid-canonical", MIG.CONTROL_POLICY_NAME, live, desired
    ) == "IGNORE_ALL_FINDINGS"
    # Any other phase or policy stays strict.
    for phase in ("default-deny-quiesce", "restore-broad-permit",
                  "redundant-policy-cleanup", "target-canonical"):
        assert MIG.validation_mode_for(
            phase, MIG.CONTROL_POLICY_NAME, live, desired
        ) == "FAIL_ON_ANY_FINDINGS", phase
    for policy in (MIG.BASELINE_POLICY_NAME, MIG.QUIESCE_POLICY_NAME, "anything_else"):
        assert MIG.validation_mode_for(
            "return-forbid-canonical", policy, live, desired
        ) == "FAIL_ON_ANY_FINDINGS", policy


def test_the_exception_requires_a_canonical_target() -> None:
    control = FakeControl()  # retired vocabulary
    live = MIG.read_live(control)
    assert MIG.validation_mode_for(
        "return-forbid-canonical", MIG.CONTROL_POLICY_NAME, live, _desired_forbid(control)
    ) == "FAIL_ON_ANY_FINDINGS"


def test_the_exception_requires_zero_matching_permits() -> None:
    control = FakeControl()
    plan = _plan(control)
    # Canonical target but the BROAD permit is still in place.
    MIG.apply_one_target(control, MIG.read_live(control), plan["phases"][1]["targetUpdates"][0])
    live = MIG.read_live(control)
    assert MIG.validation_mode_for(
        "return-forbid-canonical", MIG.CONTROL_POLICY_NAME, live, _desired_forbid(control)
    ) == "FAIL_ON_ANY_FINDINGS", "the exception was granted while the target was open"


def test_the_exception_requires_enforce_mode() -> None:
    control = _phase_c_world()
    live = MIG.read_live(control)
    live["gateway"]["policyEngineConfiguration"] = {"mode": "LOG_ONLY"}
    assert MIG.validation_mode_for(
        "return-forbid-canonical", MIG.CONTROL_POLICY_NAME, live, _desired_forbid(control)
    ) == "FAIL_ON_ANY_FINDINGS"


def test_the_exception_refuses_anything_but_the_exact_restrictive_rule() -> None:
    control = _phase_c_world()
    live = MIG.read_live(control)
    resource = MIG.gateway_resource()
    for bad in (
        # a permit instead of a forbid
        f'permit(principal, action == AgentCore::Action::"{RETURN_TARGET}___initiate_return", {resource});',
        # an action set
        f'forbid(principal, action in [AgentCore::Action::"{RETURN_TARGET}___initiate_return"], {resource});',
        # a target group
        f'forbid(principal, action in AgentCore::Action::"{RETURN_TARGET}", {resource});',
        # the condition dropped
        f'forbid(principal, action == AgentCore::Action::"{RETURN_TARGET}___initiate_return", {resource});',
    ):
        assert MIG.validation_mode_for(
            "return-forbid-canonical", MIG.CONTROL_POLICY_NAME, live, bad
        ) == "FAIL_ON_ANY_FINDINGS", bad[:60]


def test_only_one_call_site_can_use_a_relaxed_validation_mode() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert source.count("validationMode=validation") == 1
    assert source.count('validationMode="FAIL_ON_ANY_FINDINGS"') == 1, (
        "restores must stay strict and there should be exactly one strict literal"
    )
    assert source.count('"IGNORE_ALL_FINDINGS"') == 1, (
        "IGNORE_ALL_FINDINGS should be returned from exactly one place"
    )


def test_a_schema_error_is_never_an_accepted_finding() -> None:
    """IGNORE_ALL_FINDINGS does not disable schema checks, and neither do we."""
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "SCHEMA_FAILURE_MARKERS" in source
    for marker in ("unrecognized action", "invalid context", "type mismatch"):
        assert marker in source, marker
    assert "never an accepted finding" in source


def test_the_reason_for_the_exception_is_recorded_precisely() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "Overly Restrictive" in source
    assert "Schema checks" in source
    # The mischaracterisations must be explicitly REFUTED, not merely absent — the
    # point is that the next reader is told what this is not.
    assert 'NOT "disable validation"' in source
    assert 'NOT "ignore Cedar errors"' in source
    # Comment text wraps and carries `#` markers, so strip both before matching.
    flat = " ".join(source.replace("#", " ").split())
    assert "regardless of validationMode" in flat, (
        "the source does not state that schema checks always run"
    )


def test_a_stale_captured_definition_is_not_auto_restored() -> None:
    """Restoring a definition that names a retired action can never reach ACTIVE."""
    control = _phase_c_world()
    plan = _plan(control)
    update = next(u for e in plan["phases"] for u in e["policyUpdates"]
                  if u["policy"] == MIG.CONTROL_POLICY_NAME)
    before = control.policies[update["policyId"]]["definition"]["policy"]["statement"]
    _fail_nth_policy_write(control, 1)
    with pytest.raises(SystemExit, match="was NOT\\s+attempted|cannot reach ACTIVE"):
        MIG.apply_policy_update(control, update, phase="return-forbid-canonical",
                                live=MIG.read_live(control))
    # Exactly one write: the attempt. No restore attempt.
    assert len(control.policy_updates) == 1, "a restore was attempted anyway"


def test_the_phase_c_guard_accepts_only_the_documented_recovery_state() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    helper = source[source.index("def _require_closed_canonical_target"):]
    helper = helper[: helper.index("\n\ndef ")]
    assert 'policy.get("status") == "UPDATE_FAILED"' in helper
    assert "IGNORE_FINDINGS_PHASE" in helper and "IGNORE_FINDINGS_POLICY" in helper
    assert "not the recovery state this exception covers" in helper
    assert 'enforcementMode") != "ACTIVE"' in helper, (
        "enforcementMode must still be required unconditionally"
    )


def test_phase_d_is_not_described_as_reopening_the_target() -> None:
    """Observed: a policy write appears to recompile group membership.

    After Phase C the stale group forbid began matching the canonical children it
    had not matched after Phase B, so restoring the broad permit may not reopen the
    target by itself. The source must not promise that it does.
    """
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    flat = " ".join(source.replace("#", " ").split())
    assert "recompile group membership" in flat
    assert "becomes load-bearing" in flat, (
        "the source does not record that Phase E may be required for availability"
    )
    assert "permit restored" in flat and "target reopened" in flat


def test_the_module_does_not_treat_group_coverage_as_stable() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    flat = " ".join(source.replace("#", " ").split())
    assert "its coverage changed underneath a statement that never changed" in flat


def test_restore_broad_permit_refuses_while_the_stale_group_forbid_exists() -> None:
    """The full unquiesce must not run before the damaged reopen has replaced it."""
    guard = _guard_source("restore-broad-permit")
    assert "ORDERING GUARD" in guard
    assert "still holds a target-group forbid" in guard
    assert "revised, approved design" in guard
    # Ordered before the baseline check so it fires first.
    assert guard.index("stale_group") < guard.index("baseline_live")
    # And it is scoped to the unquiesce: the damaged-reopen phase is the write that
    # REPLACES that forbid, so refusing on its presence there would be unrunnable.
    assert 'args.phase == "restore-broad-permit" and stale_group is not None' in guard


# ---------------------------------------------------------------------------
# Phase 6: the damaged-return reopen precedes the full unquiesce
# ---------------------------------------------------------------------------

def test_the_damaged_reopen_runs_before_the_full_unquiesce() -> None:
    """Order is load-bearing, not cosmetic.

    The stale group forbid began matching the canonical children after Phase C, so
    restoring the broad permit first would have left the target closed while looking
    like a successful unquiesce. Replacing that policy first also makes the reopen one
    action with one condition instead of the whole target.
    """
    phases = list(MIG.PHASES)
    assert phases.index("allow-damaged-canonical") < phases.index(
        "restore-broad-permit"
    )
    assert "redundant-policy-cleanup" not in phases, (
        "the old name implied cosmetic cleanup after the reopen"
    )


def test_the_damaged_permit_is_the_captured_original_with_only_the_action_renamed() -> None:
    """No new business condition. The reason clause is carried through verbatim."""
    original = MIG.permit_template()
    desired, renames = MIG.rewrite_actions(original, to_canonical=True)
    assert renames, "nothing was renamed"

    before = MIG.parse_statement("original", original)
    after = MIG.parse_statement("desired", desired)
    assert before.effect == after.effect == "permit"
    assert before.condition == after.condition == "damaged_only"
    assert before.actions == (f"{RETURN_TARGET}___process_return",)
    assert after.actions == (f"{RETURN_TARGET}___initiate_return",)
    # No group anywhere in the final pair.
    assert after.groups == ()
    # And the resource is untouched.
    assert MIG.gateway_resource() in desired


def test_the_damaged_reopen_opens_exactly_one_business_path() -> None:
    """With the baseline still narrowed, the damaged permit is the only match."""
    rows = {r["phase"]: r for r in MIG.phase_states(_plan(FakeControl()))}
    row = rows["allow-damaged-canonical"]
    canonical = f"{RETURN_TARGET}___initiate_return"
    escalate = f"{RETURN_TARGET}___escalate_to_human"

    # Damaged returns open; nothing else does.
    assert row["decisions"][canonical]["damaged"] == "ALLOW"
    assert row["decisions"][canonical]["non_damaged"] == "DENY"
    assert row["decisions"][escalate]["damaged"] == "DENY"
    assert row["decisions"][escalate]["non_damaged"] == "DENY"
    # Exactly one permit matches the reopened action, and none matches escalation.
    assert len(row["permitCoverage"][canonical]) == 1
    assert row["permitCoverage"][escalate] == []
    # The invariant still holds: the reopened write is covered by a restrictive rule.
    assert row["safe"] is True
    assert row["targetOpen"] is True


def test_the_full_unquiesce_permits_escalation_and_keeps_the_return_rule() -> None:
    rows = {r["phase"]: r for r in MIG.phase_states(_plan(FakeControl()))}
    row = rows["restore-broad-permit"]
    canonical = f"{RETURN_TARGET}___initiate_return"
    escalate = f"{RETURN_TARGET}___escalate_to_human"

    assert row["decisions"][canonical]["damaged"] == "ALLOW"
    assert row["decisions"][canonical]["non_damaged"] == "DENY", (
        "the broad permit widened past the restrictive control"
    )
    assert row["decisions"][escalate]["damaged"] == "ALLOW"
    assert row["decisions"][escalate]["non_damaged"] == "ALLOW"
    assert row["safe"] is True


def test_the_unquiesce_requires_the_canonical_damaged_permit_first() -> None:
    guard = _guard_source("restore-broad-permit")
    assert "is not yet the canonical damaged-only permit" in guard
    assert '"permit", (canonical_id,), "damaged_only"' in guard
    assert "prove the three governed" in guard


def test_the_damaged_reopen_is_gated_on_a_closed_canonical_target() -> None:
    guard = _guard_source("allow-damaged-canonical")
    assert "_require_closed_canonical_target" in guard
    assert 'parsed.condition != "not_damaged"' in guard
    assert "parsed.actions != (canonical_id,)" in guard


def test_the_damaged_reopen_validates_strictly() -> None:
    """No IGNORE_ALL_FINDINGS: the canonical action exists and the permit is meaningful."""
    live = MIG.read_live(FakeControl())
    mode = MIG.validation_mode_for(
        "allow-damaged-canonical", MIG.QUIESCE_POLICY_NAME, live,
        MIG.rewrite_actions(MIG.permit_template(), to_canonical=True)[0],
    )
    assert mode == "FAIL_ON_ANY_FINDINGS"


def test_no_final_policy_keeps_a_retired_action_or_a_target_group() -> None:
    plan = _plan(FakeControl())
    by_name = {e["phase"]: e for e in plan["phases"]}
    finals = {
        MIG.BASELINE_POLICY_NAME:
            by_name["restore-broad-permit"]["policyUpdates"][0]["after"],
        MIG.QUIESCE_POLICY_NAME:
            by_name["allow-damaged-canonical"]["policyUpdates"][0]["after"],
        MIG.CONTROL_POLICY_NAME:
            by_name["return-forbid-canonical"]["policyUpdates"][0]["after"],
    }
    for name, statement in finals.items():
        parsed = MIG.parse_statement(name, statement)
        assert parsed.groups == (), f"{name} keeps a target action group"
        for retired in MIG.RETIRED_TO_CURRENT:
            assert f"___{retired}" not in statement, f"{name} keeps {retired}"


def test_every_generated_statement_is_syntactically_balanced() -> None:
    """Regression: mixed f-string and plain-literal concatenation.

    `permit_template()` ended with a PLAIN literal containing `}}`, and brace escaping
    applies per literal — so the template rendered `... "damaged" }};` with a doubled
    closing brace. A dry run printed it before any write, but nothing in the suite
    would have caught it. Cedar would have rejected the update.
    """
    generated = {
        "permit_template": MIG.permit_template(),
        "quiesce_statement": MIG.quiesce_statement(),
        "broad_baseline": MIG.broad_baseline_statement(),
        "narrowed_baseline": MIG.narrowed_baseline_statement(MIG.read_live(FakeControl())),
    }
    generated["canonical_permit"] = MIG.rewrite_actions(
        MIG.permit_template(), to_canonical=True
    )[0]

    for label, statement in generated.items():
        assert statement.count("{") == statement.count("}"), (
            f"{label} has unbalanced braces: {' '.join(statement.split())}"
        )
        assert statement.count("(") == statement.count(")"), label
        assert statement.rstrip().endswith(";"), f"{label} does not end in a semicolon"
        assert "}}" not in statement, f"{label} contains a doubled brace"
        assert "{{" not in statement, f"{label} contains a doubled brace"
        # And every one of them must parse under the module's own strict parser.
        MIG.parse_statement(label, statement)


def test_the_canonical_permit_records_its_rename() -> None:
    """The plan's audit trail must name the substitution it made."""
    plan = _plan(FakeControl())
    entry = next(e for e in plan["phases"] if e["phase"] == "allow-damaged-canonical")
    renames = entry["policyUpdates"][0].get("renames") or []
    assert renames, "the damaged reopen reports no rename"
    assert any("___process_return -> " in r and "___initiate_return" in r
               for r in renames), renames


# ---------------------------------------------------------------------------
# The generated-Cedar gate runs on the APPLY path, not only in tests
# ---------------------------------------------------------------------------

def test_a_malformed_statement_cannot_reach_the_service() -> None:
    """The exact defect that was caught by eye, now caught by the code."""
    doubled = (
        'permit(principal, action == AgentCore::Action::"x", '
        f'{MIG.gateway_resource()})\nwhen {{\n  context.input has reason && '
        'context.input.reason == "damaged"\n}};'
    )
    assert "}}" in doubled, "fixture no longer reproduces the defect"
    with pytest.raises(SystemExit) as exc:
        MIG.assert_generated_cedar_is_well_formed("fixture", doubled)
    assert "doubled brace" in str(exc.value)


def test_the_gate_rejects_structural_damage() -> None:
    base = MIG.rewrite_actions(MIG.permit_template(), to_canonical=True)[0]
    for label, broken, marker in (
        ("no semicolon", base.rstrip(";"), "no terminating semicolon"),
        ("unbalanced paren", base.replace(")", "", 1), "unbalanced parentheses"),
        ("unbalanced brace", base.replace("}", "", 1), "unbalanced braces"),
    ):
        with pytest.raises(SystemExit) as exc:
            MIG.assert_generated_cedar_is_well_formed(label, broken)
        assert marker in str(exc.value), (label, str(exc.value))


def test_the_gate_rejects_a_wrong_effect_or_cardinality() -> None:
    permit = MIG.rewrite_actions(MIG.permit_template(), to_canonical=True)[0]
    with pytest.raises(SystemExit) as exc:
        MIG.assert_generated_cedar_is_well_formed(
            "p", permit, expect_effect="forbid"
        )
    assert "effect is permit" in str(exc.value)
    with pytest.raises(SystemExit) as exc:
        MIG.assert_generated_cedar_is_well_formed("p", permit, expect_actions=2)
    assert "names 1 action id" in str(exc.value)


def test_the_gate_rejects_a_foreign_gateway_resource() -> None:
    foreign = (
        'permit(principal, action == AgentCore::Action::"x", '
        'resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:'
        '000000000000:gateway/someone-elses");'
    )
    with pytest.raises(SystemExit) as exc:
        MIG.assert_generated_cedar_is_well_formed("foreign", foreign)
    assert "not this gateway" in str(exc.value)


def test_the_apply_path_calls_the_gate_before_update_policy() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    body = source[source.index("def apply_policy_update("):]
    body = body[: body.index("\ndef ")]
    gate = body.index("assert_generated_cedar_is_well_formed")
    write = body.index("control.update_policy(")
    assert gate < write, "the structural gate runs after the write"


def test_the_apply_path_refuses_a_no_op_policy_write() -> None:
    """`after == captured` is not a phase, and for the restore it was the bug.

    Checked on the APPLY path against the definition captured from live, not in
    `build_plan`: a plan derived before the quiesce has nothing to restore yet, so the
    same comparison there is legitimate and an invariant placed there refused every
    pre-quiesce plan — including the whole fixture suite.
    """
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    body = source[source.index("def apply_policy_update("):]
    body = body[: body.index("\ndef ")]
    assert "identical to the one already deployed" in body
    assert "sourced from live state instead" in body
    # Ordered before the write.
    assert body.index("identical to the one already deployed") < body.index(
        "control.update_policy("
    )


def test_the_plan_refuses_a_restore_that_is_not_broad() -> None:
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "does not restore a BROAD permit" in source
    assert "would leave" in source and "escalate_to_human denied" in source


# ---------------------------------------------------------------------------
# Phase 6C: the final authorization contract is explicit, not a wildcard
# ---------------------------------------------------------------------------

def _migrated_live() -> Dict[str, Any]:
    """Live state AFTER `target-canonical` has landed, which is where live is now.

    `FakeControl` deliberately models the pre-migration starting state — the rename is
    what the earlier phases test — so the final baseline, which names the canonical
    escalation action, cannot be built from it. This applies only the rename.
    """
    live = MIG.read_live(FakeControl())
    for target in live["targets"]:
        if target["name"] != RETURN_TARGET:
            continue
        schema = target["targetConfiguration"]["mcp"]["lambda"]["toolSchema"]
        schema["inlinePayload"] = [
            {**tool, "name": MIG.RETIRED_TO_CURRENT.get(tool["name"], tool["name"])}
            for tool in schema["inlinePayload"]
        ]
    return live


def test_the_migrated_fixture_publishes_the_canonical_return_vocabulary() -> None:
    """Guards the helper itself, so a rename map change cannot quietly hollow it out."""
    target = next(t for t in _migrated_live()["targets"] if t["name"] == RETURN_TARGET)
    assert sorted(n for n in MIG._tool_names(target)) == [
        "escalate_to_human", "initiate_return",
    ]


def test_the_final_baseline_names_twelve_explicit_actions() -> None:
    live = _migrated_live()
    parsed = MIG.parse_statement("final", MIG.final_baseline_statement(live))
    assert parsed.actions is not None, "the final baseline is a wildcard"
    assert len(parsed.actions) == 12
    assert parsed.groups == ()
    assert parsed.condition == "none"


def test_the_final_baseline_adds_only_escalation() -> None:
    live = _migrated_live()
    narrowed = set(MIG.parse_statement("n", MIG.narrowed_baseline_statement(live)).actions)
    final = set(MIG.parse_statement("f", MIG.final_baseline_statement(live)).actions)
    assert final - narrowed == {f"{RETURN_TARGET}___escalate_to_human"}
    assert narrowed - final == set()


def test_the_final_baseline_never_names_the_return_action() -> None:
    """The return stays governed by its dedicated permit/forbid pair.

    Naming it in an unconditional baseline permit would make the damaged-only condition
    decorative: the forbid would still deny non-damaged, but the permit would stop
    expressing that returns are conditionally authorized.
    """
    live = _migrated_live()
    parsed = MIG.parse_statement("f", MIG.final_baseline_statement(live))
    assert not any(a.endswith("___initiate_return") for a in parsed.actions)


def test_a_future_published_tool_gets_no_permit() -> None:
    """The whole reason for abandoning the wildcard.

    Under `permit(principal, action, resource == gw)` a tool acquires authorization the
    moment it is published. That is what made this migration's own window unsafe, and it
    would silently authorize `issue_credit` on publication alone.
    """
    live = _migrated_live()
    statements = [
        MIG.parse_statement(MIG.BASELINE_POLICY_NAME, MIG.final_baseline_statement(live)),
        MIG.parse_statement(MIG.QUIESCE_POLICY_NAME,
                            MIG.rewrite_actions(MIG.permit_template(), to_canonical=True)[0]),
        MIG.parse_statement(MIG.CONTROL_POLICY_NAME,
                            MIG.rewrite_actions(_retired_forbid(), to_canonical=True)[0]),
    ]
    for future in ("issue_credit", "get_ticket_history", "anything_at_all"):
        action = f"{RETURN_TARGET}___{future}"
        assert MIG.evaluate(statements, action, "damaged") == "DENY", future
        assert MIG.evaluate(statements, action, "other") == "DENY", future

    # And under the wildcard it would have been ALLOW, which is the contrast.
    wildcard = [MIG.parse_statement(MIG.BASELINE_POLICY_NAME, MIG.broad_baseline_statement())]
    assert MIG.evaluate(wildcard, f"{RETURN_TARGET}___issue_credit", "damaged") == "ALLOW"


def _retired_forbid() -> str:
    return (
        f'forbid(principal, action == AgentCore::Action::'
        f'"{RETURN_TARGET}___process_return", {MIG.gateway_resource()})\n'
        'when {\n  !(context.input has reason) || context.input.reason != "damaged"\n};'
    )


def test_the_final_authorization_matrix() -> None:
    """The shipped contract, evaluated from the generated statements."""
    live = _migrated_live()
    statements = [
        MIG.parse_statement(MIG.BASELINE_POLICY_NAME, MIG.final_baseline_statement(live)),
        MIG.parse_statement(MIG.QUIESCE_POLICY_NAME,
                            MIG.rewrite_actions(MIG.permit_template(), to_canonical=True)[0]),
        MIG.parse_statement(MIG.CONTROL_POLICY_NAME,
                            MIG.rewrite_actions(_retired_forbid(), to_canonical=True)[0]),
    ]
    ret = f"{RETURN_TARGET}___initiate_return"
    esc = f"{RETURN_TARGET}___escalate_to_human"
    assert MIG.evaluate(statements, ret, "damaged") == "ALLOW"
    assert MIG.evaluate(statements, ret, "not_as_described") == "DENY"
    assert MIG.evaluate(statements, esc, "damaged") == "ALLOW"
    assert MIG.evaluate(statements, esc, "not_as_described") == "ALLOW"
    # The return is permitted by its dedicated policy only, never by the baseline.
    permits = [s.name for s in statements if s.effect == "permit" and s.covers(ret)]
    assert permits == [MIG.QUIESCE_POLICY_NAME]


def test_the_wildcard_restore_requires_an_explicit_flag() -> None:
    """Historical is not desirable. Applying the wildcard needs a deliberate opt-in."""
    source = (REPO / "scripts" / "migrate_gateway_vocabulary.py").read_text()
    assert "--allow-wildcard-baseline" in source
    assert 'if args.phase == WILDCARD_PHASE and not args.allow_wildcard_baseline:' in source
    assert "authorizes any action published after it" in source
    # And the explicit phase is named as the intended end state in the refusal.
    assert "The intended end state is --phase explicit-baseline-final" in source


def test_the_final_phase_does_not_require_a_closed_target() -> None:
    """`_require_closed_canonical_target` asserts ZERO permits.

    The damaged permit is deliberately active by the time the final baseline lands, so
    reusing that gate here would be both wrong and unpassable. What must hold instead is
    that the dedicated return pair is already canonical.
    """
    guard = _guard_source("explicit-baseline-final")
    assert "_require_closed_canonical_target" not in guard
    assert "damaged_only" in guard and "not_damaged" in guard
    assert "baseline_parsed.actions is None" in guard


def test_the_final_baseline_refuses_if_escalation_is_not_published() -> None:
    control = FakeControl()
    live = MIG.read_live(control)
    for target in live["targets"]:
        if target["name"] == RETURN_TARGET:
            target["targetConfiguration"] = {"mcp": {"lambda": {"toolSchema":
                {"inlinePayload": [{"name": "initiate_return"}]}}}}
    with pytest.raises(SystemExit) as exc:
        MIG.final_baseline_statement(live)
    assert "is not published on the live target" in str(exc.value)
