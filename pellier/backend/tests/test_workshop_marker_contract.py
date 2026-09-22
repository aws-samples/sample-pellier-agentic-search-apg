"""The anchors the lab guide points at, asserted from the source side.

Why this file exists
--------------------

The Workshop Studio guide names exact paths, exact marker strings, and exact CLI flags.
A participant does not debug a drifted instruction; they read "edit between the markers",
find no markers, and stop. Every anchor below is quoted from the shipped guide, so a
rename in this repository fails here instead of in a room.

These tests cannot read the guide: the lab content lives in the sibling
``build-governed-agentic-ai-search-with-aurora-rds-bedrock-agentcore`` repository, which
CI does not clone. The anchors are therefore written out once, each with the page and
step it comes from, and this file is the source-side half of the contract. Changing an
anchor means changing both repositories, which is the point.

What each lab needs from the source tree
----------------------------------------

**Lab 1 - Ground the Answer.** Two marker regions to fill and two fallback
files to copy. A missing marker breaks the primary lane; a missing fallback breaks the
recovery lane, which is worse, because it only fails for the participant who is already
behind.

**Lab 2 - Build and Measure PostgreSQL Hybrid Retrieval.** A runnable psql
worksheet whose RRF expression starts degraded, plus a bounded search-plan
fallback that must preserve the original requirements.

**Lab 3 - Deploy and Operate Agents with Amazon Bedrock AgentCore.** Two marker regions and two
fallback files. 3A publishes ``get_ticket_history`` on the Gateway and reconciles the
tools the Runtime asks the Gateway for, binding that read to the caller. One of the two
files is a packaged runtime source. Task 3B deploys those edits and checks the executed
fingerprint, which is how the participant proves their own build answered.

**Lab 4 - Build Governed Agent Actions with Cedar.** A starter Cedar file that must NOT contain
the answer, a reference rule that must, one proof script whose flags the guide passes
verbatim, and a keyed absence worksheet whose counts start as NULL placeholders. The
OpenTelemetry trace contract is a provided check the guide runs, not a build.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

import pytest

REPO = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Lab 1, "10-ground-answers-in-live-data", steps 1 and 2 plus the pacing fallback.
# ---------------------------------------------------------------------------

LAB1_REGIONS: Tuple[Tuple[str, str], ...] = (
    ("pellier/backend/agents/inventory_agent.py",
     "WORKSHOP · Inventory Agent · definition"),
    ("pellier/backend/services/agent_tools.py",
     "WORKSHOP · Inventory Agent · check_inventory"),
)

# The exact `cp` sources in the guide's pacing fallback. A participant runs these
# verbatim, so a renamed solution file is a dead recovery lane.
LAB1_FALLBACK_COPIES: Tuple[Tuple[str, str], ...] = (
    ("solutions/waking-the-stock-keeper/agents/inventory_agent_solution.py",
     "pellier/backend/agents/inventory_agent.py"),
    ("solutions/closing-marcos-gap/services/agent_tools_check_inventory_solution.py",
     "pellier/backend/services/agent_tools.py"),
)

# ---------------------------------------------------------------------------
# Lab 2, bounded build artifact plus pacing fallback.
# ---------------------------------------------------------------------------

LAB2_STARTER = "workshop/lab-2-rrf.sql"
LAB2_PLAN_REGION = (
    "pellier/backend/services/search_plan.py",
    "WORKSHOP · Search plan · preserve requirements",
)
LAB2_PLAN_REFERENCE = (
    "solutions/the-quiet-search/retrieval/search_plan_solution.py"
)
# The ids the documented predicate yields from `scripts/seed_pellier_catalog.py`:
# in-stock Home Decor at or under $100 tagged both `gift` and `home`.
LAB2_GOLDEN_IDS = ("21", "22", "23", "25", "27", "29")
LAB2_REFERENCE = "solutions/the-quiet-search/sql/lab-2-rrf-solution.sql"
LAB2_MARKER = "WORKSHOP · PostgreSQL RRF · fusion expression"

# ---------------------------------------------------------------------------
# Lab 3, two marker regions that together move the build onto the managed path.
# 3A publishes a Gateway tool and reconciles what the Runtime asks the Gateway
# for. `agentcore_gateway.py` is a packaged runtime source, so that edit changes
# the deployed build fingerprint checked in Task 3B.
# ---------------------------------------------------------------------------

LAB3_REGIONS: Tuple[Tuple[str, str], ...] = (
    ("scripts/deploy/gateway_tool_schemas.py",
     "WORKSHOP · Gateway catalogue · published tools"),
    ("pellier/backend/services/agentcore_gateway.py",
     "WORKSHOP · Managed catalogue · support reconcile"),
)

LAB3_FALLBACK_COPIES: Tuple[Tuple[str, str], ...] = (
    ("solutions/the-ledger/gateway/gateway_tool_schemas_solution.py",
     "scripts/deploy/gateway_tool_schemas.py"),
    ("solutions/the-ledger/services/agentcore_gateway.py",
     "pellier/backend/services/agentcore_gateway.py"),
)

# The tool Task 3A publishes and binds to the caller, the one that stays
# deferred, and the staff-only tool the shopper specialist must drop in 3A.
# Getting these backwards is the whole lesson.
LAB3_PUBLISHED_TOOL = "get_ticket_history"
LAB3_DEFERRED_TOOL = "restock_inventory"
LAB3_STAFF_ONLY_TOOL = "issue_credit"

# ---------------------------------------------------------------------------
# Lab 4, "40-govern-actions-and-prove-outcomes": a Cedar rule and a trace
# contract.
# ---------------------------------------------------------------------------

LAB4_ABSENCE_STARTER = "workshop/lab-4-absence.sql"
LAB4_ABSENCE_REFERENCE = "solutions/the-ledger/observability/lab-4-absence-solution.sql"
LAB4_ABSENCE_MARKER = "WORKSHOP · Keyed absence · deny proof"
LAB4_ABSENCE_PLACEHOLDERS = (
    "NULL::bigint AS denied_execution_rows",
    "NULL::bigint AS denied_write_rows",
    "NULL::bigint AS denied_finalized_writes",
    "NULL::bigint AS denied_ledger_rows",
    "NULL::bigint AS allowed_finalized_writes",
)
LAB3_TRACE_CONTRACT = "workshop/lab-3-otel-contract.jq"

LAB4_STARTER = "policies/workshop_identity_match_forbid.cedar"
LAB4_REFERENCE = "solutions/the-concierge/policies/identity_match_forbid.cedar"
LAB4_PROOF_SCRIPT = "scripts/prove_identity_boundary.py"
LAB4_RLS_PROOF = "workshop/lab-4-rls.sql"

# The policy name passed to `agentcore add policy --name` and to the proof script's
# `--policy-name`. One string in three places.
LAB4_POLICY_NAME = "workshop_identity_match_forbid"

# The target-qualified action Gateway generates. The guide shows it inside the starter,
# and the rule is inert against any other action id.
LAB4_ACTION = "pellier-concierge-experience-target___initiate_return"

# Every flag the guide passes to the one-command Lab 4 proof driver.
LAB4_PROOF_FLAGS = (
    "--json",
)

# The identity pairs the reference rule binds. Each pair joins a Cognito username to an
# Aurora customer id, which is the whole lesson of the lab.
LAB4_IDENTITY_PAIRS = (
    ("marco", "CUST-MARCO"),
    ("anna", "CUST-ANNA"),
    ("theo", "CUST-THEO"),
    ("jessica", "CUST-JESSICA"),
)

PARTICIPANT_EXERCISE_RESET = "scripts/reset_participant_exercises.py"
PARTICIPANT_STARTERS = {
    "lab-1-inventory-agent": (
        "workshop/starters/lab-1/inventory-agent-definition.pyfrag",
        "pellier/backend/agents/inventory_agent.py",
    ),
    "lab-1-inventory-tool": (
        "workshop/starters/lab-1/check-inventory-tool.pyfrag",
        "pellier/backend/services/agent_tools.py",
    ),
    "lab-2-rrf": (
        "workshop/starters/lab-2-rrf.sql",
        LAB2_STARTER,
    ),
    "lab-2-preserve-requirements": (
        "workshop/starters/lab-2/preserve-requirements.pyfrag",
        "pellier/backend/services/search_plan.py",
    ),
    "lab-3-gateway-catalogue": (
        "workshop/starters/lab-3/gateway-published-tools.pyfrag",
        "scripts/deploy/gateway_tool_schemas.py",
    ),
    "lab-3-support-reconcile": (
        "workshop/starters/lab-3/support-reconcile.pyfrag",
        "pellier/backend/services/agentcore_gateway.py",
    ),
    "lab-4-rls": ("workshop/starters/lab-4-rls.sql", "workshop/lab-4-rls.sql"),
    "lab-4-absence": (
        "workshop/starters/lab-4-absence.sql",
        LAB4_ABSENCE_STARTER,
    ),
    "lab-4-cedar": (
        "workshop/starters/workshop_identity_match_forbid.cedar",
        LAB4_STARTER,
    ),
}


def _module_constant(tree: ast.Module, name: str):
    """Read one module-level constant without importing the module.

    These modules build ``Settings`` at import time, so importing them to read
    a tuple would demand database credentials the test environment has no
    reason to hold.
    """
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a module-level constant any more")


def _load_module(name: str, rel: str):
    """Import a solution file by path without adding it to the package tree.

    Solution twins live outside ``pellier/backend`` and share module names with
    the live modules they replace, so importing them normally would either fail
    or shadow the real one for every later test in the session.
    """
    path = REPO / rel
    assert path.is_file(), f"{rel} is named by the lab guide but is not in the repository"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(rel: str) -> str:
    path = REPO / rel
    assert path.is_file(), f"{rel} is named by the lab guide but is not in the repository"
    return path.read_text(encoding="utf-8")


def _marker_pair(text: str, label: str) -> Tuple[int, int]:
    start = text.find(f"{label}: START ===")
    end = text.find(f"{label}: END ===")
    return start, end


@pytest.mark.parametrize("rel,label", LAB1_REGIONS)
def test_lab1_region_has_exactly_one_marker_pair(rel: str, label: str) -> None:
    """Two pairs would make "edit between the markers" ambiguous; zero makes it false."""
    text = _read(rel)
    assert text.count(f"{label}: START ===") == 1, f"{rel}: expected one START for {label}"
    assert text.count(f"{label}: END ===") == 1, f"{rel}: expected one END for {label}"


@pytest.mark.parametrize("rel,label", LAB1_REGIONS)
def test_lab1_region_is_ordered_and_not_empty(rel: str, label: str) -> None:
    """An inverted or empty region reads as "nothing to do here"."""
    text = _read(rel)
    start, end = _marker_pair(text, label)
    assert start < end, f"{rel}: START must precede END for {label}"
    body = text[text.index("\n", start) + 1:end]
    assert body.strip(), f"{rel}: the {label} region is empty"


@pytest.mark.parametrize("rel,label", LAB1_REGIONS)
def test_lab1_marker_uses_the_middle_dot_the_guide_quotes(rel: str, label: str) -> None:
    """The guide quotes the marker with U+00B7.

    A participant searching the file for the string in the guide finds nothing if this
    ever becomes a hyphen or an ASCII dot, and "search for this text" is the only
    instruction that lane gives.
    """
    text = _read(rel)
    assert "·" in label
    assert label in text


@pytest.mark.parametrize("source,destination", LAB1_FALLBACK_COPIES)
def test_lab1_fallback_copy_exists_at_both_ends(source: str, destination: str) -> None:
    assert (REPO / source).is_file(), f"the guide copies {source}, which is absent"
    assert (REPO / destination).is_file(), f"the guide copies onto {destination}, which is absent"


@pytest.mark.parametrize("source,destination", LAB1_FALLBACK_COPIES)
def test_lab1_fallback_copy_keeps_the_markers(source: str, destination: str) -> None:
    """The recovery lane must not destroy the anchor.

    A participant who takes the fallback and then wants to read what changed needs the
    same marker region in the copied file. A solution written without markers turns one
    recovery into a dead end for the rest of the lab.
    """
    text = (REPO / source).read_text(encoding="utf-8")
    labels = [label for rel, label in LAB1_REGIONS if rel == destination]
    assert labels, f"{destination} is not a Lab 1 marker file"
    for label in labels:
        assert f"{label}: START ===" in text, f"{source} lost the {label} START marker"
        assert f"{label}: END ===" in text, f"{source} lost the {label} END marker"


@pytest.mark.parametrize(
    "starter,reference,label",
    (
        (LAB2_STARTER, LAB2_REFERENCE, LAB2_MARKER),
        (LAB4_ABSENCE_STARTER, LAB4_ABSENCE_REFERENCE, LAB4_ABSENCE_MARKER),
    ),
)
def test_labs_2_and_3_have_matching_build_markers(
    starter: str,
    reference: str,
    label: str,
) -> None:
    for rel in (starter, reference):
        text = _read(rel)
        assert text.count(f"{label}: START ===") == 1
        assert text.count(f"{label}: END ===") == 1


def test_lab2_starter_fails_until_rrf_is_authored() -> None:
    starter = _read(LAB2_STARTER)
    reference = _read(LAB2_REFERENCE)
    assert "0::numeric AS recomputed_rrf" in starter
    assert "0::numeric AS recomputed_rrf" not in reference
    assert reference.count("1.0 / (60 +") == 2
    assert "\\if :fusion_matches" in starter
    # `\quit` takes no argument; a raised exception under ON_ERROR_STOP is what makes
    # the worksheet exit non-zero, so a shell `&&` or `set -e` sees the failure.
    assert "\\quit 1" not in starter
    assert "RAISE EXCEPTION" in starter


def test_lab4_starter_fails_until_the_absence_query_is_authored() -> None:
    """The starter's counts are NULL, which the worksheet refuses; the twin reads the tables."""
    starter = _read(LAB4_ABSENCE_STARTER)
    reference = _read(LAB4_ABSENCE_REFERENCE)
    for placeholder in LAB4_ABSENCE_PLACEHOLDERS:
        assert placeholder in starter
        assert placeholder not in reference
    assert "\\if :lab_4_authored" in starter and "\\quit 1" not in starter
    assert "RAISE EXCEPTION" in starter
    for required in (
        "pellier.tool_audit",
        "args->>'idempotency_key' = :'deny_key'",
        "pellier.write_operations",
        "completed_at IS NOT NULL",
        "result->>'status' = 'success'",
        "pellier.inventory_ledger",
        ":'allow_key'",
    ):
        assert required in reference, f"reference absence query lacks {required}"
    region = reference.split(f"{LAB4_ABSENCE_MARKER}: START ===")[1].split(f"{LAB4_ABSENCE_MARKER}: END ===")[0]
    assert region.count(":'deny_key'") == 4 and region.count(":'allow_key'") == 1
    # The worksheet's own verdict: absence AND positive control, never absence alone.
    assert ":lab_4_allowed_finalized_writes = 1" in starter


def test_the_trace_contract_is_a_provided_check_not_a_build() -> None:
    contract = _read(LAB3_TRACE_CONTRACT)
    assert "WORKSHOP ·" not in contract, "the trace contract is provided; it carries no build markers"
    for predicate in ("invoke_agent", "gen_ai.request.model", "execute_tool", "gen_ai.tool.name", 'attributes["session.id"]'):
        assert predicate in contract
    assert ": false" not in contract


def test_lab2_golden_set_region_has_exactly_one_marker_pair() -> None:
    rel, label = LAB2_PLAN_REGION
    text = _read(rel)
    assert text.count(f"# === {label}: START ===") == 1
    assert text.count(f"# === {label}: END ===") == 1


def test_lab2_starter_refuses_an_unfinished_fallback() -> None:
    from services.search_plan import SearchPlan, SoftPreferences
    plan = SearchPlan(intent="gift", soft=SoftPreferences(tags=("minimalist",)))
    with pytest.raises(ValueError, match="Complete Task 2B"):
        plan.relaxation_ladder()
    assert plan.soft.tags == ("minimalist",)
    assert plan.relaxations == []


def test_lab2_reference_preserves_the_plan_contract() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("lab2_plan_check", REPO / "scripts/lab2_plan_contract_check.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    reference = checker.load_plan_module(REPO / LAB2_PLAN_REFERENCE)
    assert checker.check(reference)["passed"] is True


def test_lab2_golden_set_is_stated_once() -> None:
    """The eval harness must derive the labels, not carry a second copy.

    A duplicate literal would score the harness against a labeling the backend
    no longer uses and report a regression that exists only in that file.
    """
    harness = _read("scripts/eval_retrieval_harness.py")
    assert "CANONICAL_ANNA_GOLDEN_IDS" in harness
    for product_id in LAB2_GOLDEN_IDS:
        assert f'"{product_id}", "' not in harness.split("GOLDEN_QUERIES")[0], (
            "the harness appears to carry its own copy of the golden ids"
        )


# ---------------------------------------------------------------------------
# Lab 3, "30-deploy-and-operate-the-managed-path", steps 1 and 2.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("rel", "label"), LAB3_REGIONS)
def test_lab3_region_has_exactly_one_marker_pair(rel: str, label: str) -> None:
    text = _read(rel)
    assert text.count(f"# === {label}: START ===") == 1
    assert text.count(f"# === {label}: END ===") == 1


@pytest.mark.parametrize(("rel", "label"), LAB3_REGIONS)
def test_lab3_region_is_ordered_and_not_empty(rel: str, label: str) -> None:
    text = _read(rel)
    start = text.index(f"# === {label}: START ===")
    end = text.index(f"# === {label}: END ===")
    assert start < end, f"{rel} has its {label} markers inverted"
    assert text[start:end].strip(), f"{rel} has an empty {label} region"


@pytest.mark.parametrize(("source", "destination"), LAB3_FALLBACK_COPIES)
def test_lab3_fallback_copy_exists_at_both_ends(source: str, destination: str) -> None:
    assert (REPO / source).is_file(), f"missing Lab 3 recovery source {source}"
    assert (REPO / destination).is_file(), f"missing Lab 3 destination {destination}"


@pytest.mark.parametrize(("source", "destination"), LAB3_FALLBACK_COPIES)
def test_lab3_fallback_copy_keeps_the_markers(source: str, destination: str) -> None:
    """A recovery copy that loses the markers breaks every later reset."""
    label = dict(LAB3_REGIONS)[destination]
    text = _read(source)
    assert text.count(f"# === {label}: START ===") == 1
    assert text.count(f"# === {label}: END ===") == 1


def test_lab3_starter_withholds_the_tool_theo_needs() -> None:
    """3a is unbuilt until `get_ticket_history` leaves the deferred set."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    import gateway_tool_schemas

    published = gateway_tool_schemas.workshop_published_tools()
    assert LAB3_PUBLISHED_TOOL not in published, (
        f"{LAB3_PUBLISHED_TOOL} is already published; Lab 3a ships its own answer"
    )
    assert LAB3_DEFERRED_TOOL not in published
    assert LAB3_PUBLISHED_TOOL in gateway_tool_schemas.canonical_tool_names(), (
        "the participant publishes an existing schema; it must stay in the catalogue"
    )


def test_lab3_reference_publishes_the_read_and_withholds_the_money_movement() -> None:
    solution = _load_module(
        "lab3_gateway_solution",
        "solutions/the-ledger/gateway/gateway_tool_schemas_solution.py",
    )
    published = solution.workshop_published_tools()
    assert LAB3_PUBLISHED_TOOL in published
    assert LAB3_DEFERRED_TOOL not in published, (
        "restock_inventory moves stock and belongs to the operator desk, not a shopper agent"
    )
    assert LAB3_STAFF_ONLY_TOOL in published, (
        "issue_credit is published for the operator desk under a staff-only permit"
    )


def test_lab3_starter_leaves_the_support_specialist_unserveable() -> None:
    """The authentic failure Lab 3 fixes: the Runtime asks for unpublished tools."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    import gateway_tool_schemas

    from services import agentcore_gateway

    published = gateway_tool_schemas.workshop_published_tools()
    unserveable = set(agentcore_gateway.SUPPORT_MANAGED_TOOLS) - published
    assert unserveable, (
        "Lab 3 has nothing to fix: the starter support specialist is already serveable"
    )
    assert agentcore_gateway.SUPPORT_CALLER_BOUND_TOOLS == frozenset(), (
        "the starter must not pre-bind the ownership condition"
    )


def test_lab3_reference_reconciles_the_runtime_with_the_gateway() -> None:
    schemas = _load_module(
        "lab3_gateway_schemas_ref",
        "solutions/the-ledger/gateway/gateway_tool_schemas_solution.py",
    )
    runtime = _load_module(
        "lab3_runtime_ref",
        "solutions/the-ledger/services/agentcore_gateway.py",
    )
    published = schemas.workshop_published_tools()
    for specialist, names in runtime.MANAGED_SPECIALIST_TOOLS.items():
        missing = sorted(set(names) - published)
        assert not missing, f"{specialist} still asks for unpublished tools: {missing}"
    assert LAB3_PUBLISHED_TOOL in runtime.SUPPORT_CALLER_BOUND_TOOLS, (
        f"{LAB3_PUBLISHED_TOOL} must be bound to the authenticated caller"
    )
    assert LAB3_PUBLISHED_TOOL in runtime._CUSTOMER_SCOPED_TOOL_NAMES


def test_lab3_build_ships_to_the_managed_runtime() -> None:
    """3A must edit a packaged source for 3B to prove the executed build."""
    from services.build_fingerprint import RUNTIME_SOURCE_FILES

    packaged = {path.as_posix() for path in RUNTIME_SOURCE_FILES}
    assert "services/agentcore_gateway.py" in packaged, (
        "Task 3A's file left the runtime package, so completing it no longer "
        "changes the deployed build fingerprint"
    )


def test_lab4_starter_does_not_ship_the_answer() -> None:
    """The starter must hold the placeholder, not the identity mapping.

    This is the same failure the fresh policy renderer had: a stack that pre-installs the
    participant's answer makes step 3's DENY fire before they have written anything, and
    the exercise silently becomes a copy-paste.
    """
    text = _read(LAB4_STARTER)
    assert re.search(r"unless\s*\{\s*false\s*\}", text), (
        f"{LAB4_STARTER} no longer holds the `unless {{ false }}` starter the guide "
        "tells the participant to replace"
    )
    for username, customer_id in LAB4_IDENTITY_PAIRS:
        assert f'"{customer_id}"' not in text, (
            f"{LAB4_STARTER} contains {customer_id}: the starter is shipping the answer"
        )
        assert f'getTag("username") == "{username}"' not in text


def test_lab4_starter_targets_the_generated_action() -> None:
    """A `forbid` on the wrong action id is inert, and an inert rule looks like an ALLOW."""
    text = _read(LAB4_STARTER)
    assert LAB4_ACTION in text, f"{LAB4_STARTER} must forbid {LAB4_ACTION}"
    # The live analyzer rejects `resource is AgentCore::Gateway` for a pinned action;
    # the guide substitutes the deployed ARN before the policy is added.
    assert 'resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"' in text
    assert "resource is AgentCore::Gateway" not in text
    assert text.lstrip().startswith("//") or "forbid(" in text


def test_lab4_reference_rule_binds_every_identity_pair() -> None:
    """The fallback must be complete, or the participant who takes it still fails step 4."""
    text = _read(LAB4_REFERENCE)
    assert LAB4_ACTION in text
    # Scoped to principals carrying a customer claim, so staff are never caught by it.
    assert re.search(r'when\s*\{\s*principal\.hasTag\("custom:customer_id"\)\s*\}', text)
    assert "context.input has customer_id" in text
    assert 'principal.getTag("custom:customer_id") == context.input.customer_id' in text
    # The rule binds a claim, never a list of shoppers.
    for username, customer_id in LAB4_IDENTITY_PAIRS:
        assert f'"{username}"' not in text, f"{LAB4_REFERENCE} names {username}"
        assert customer_id not in text, f"{LAB4_REFERENCE} names {customer_id}"


def test_lab4_reference_rule_is_the_starter_plus_the_condition() -> None:
    """Same head, different body.

    If the reference drifted to a different action or effect, the fallback would deploy a
    policy that cannot produce the DENY the guide's step 3 asserts.
    """
    starter = _read(LAB4_STARTER)
    reference = _read(LAB4_REFERENCE)
    for fragment in ("forbid(", "principal is AgentCore::OAuthUser,",
                     f'action == AgentCore::Action::"{LAB4_ACTION}"',
                     'resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"',
                     'when {\n  principal.hasTag("custom:customer_id")\n}', "unless {"):
        assert fragment in starter, f"{LAB4_STARTER} lost {fragment!r}"
        assert fragment in reference, f"{LAB4_REFERENCE} lost {fragment!r}"


def test_lab4_proof_script_accepts_every_flag_the_guide_passes() -> None:
    """Parsed from the argparse calls, so a renamed flag fails here.

    The guide's step 3 and step 4 commands are identical apart from the bearer token, and
    both are pasted verbatim. A dropped flag is an immediate `unrecognized arguments`.
    """
    source = _read(LAB4_PROOF_SCRIPT)
    declared = set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', source))
    missing = sorted(flag for flag in LAB4_PROOF_FLAGS if flag not in declared)
    assert not missing, f"{LAB4_PROOF_SCRIPT} does not declare {missing}"


def test_lab4_policy_name_matches_the_cli_source() -> None:
    """The starter filename is the policy name passed by the guide's CLI step."""
    assert Path(LAB4_STARTER).stem == LAB4_POLICY_NAME, (
        "the starter filename is what the guide's --source points at; it must match "
        "the policy name"
    )


def test_lab4_proof_script_parses() -> None:
    """A syntax error in the one script the required proof runs is not a runtime problem."""
    ast.parse(_read(LAB4_PROOF_SCRIPT))


def test_lab4_rls_proof_covers_read_write_and_rolls_everything_back() -> None:
    """The required psql proof must exercise both RLS clauses without durable writes."""
    text = _read(LAB4_RLS_PROOF)
    for fragment in (
        r"\set ON_ERROR_STOP on",
        "SET LOCAL ROLE pellier_query",
        "SET LOCAL ROLE pellier_agent",
        "current_setting('pellier.principal_sub', true)",
        "CUST-MARCO",
        "CUST-JESSICA",
        "RLS_READ_MARCO_JESSICA_ROWS:",
        "RLS_READ_JESSICA_JESSICA_ROWS:",
        "RLS_PROBE_ROLE_OK",
        "RLS_PROBE_MARCO_SQLSTATE:42501",
        "RLS_PROBE_JESSICA_SQLSTATE:00000",
        "ROLLBACK",
    ):
        assert fragment in text, f"{LAB4_RLS_PROOF} lost {fragment!r}"

    assert "COMMIT" not in text
    assert len(re.findall(r"^BEGIN;", text, re.MULTILINE)) == 1
    assert len(re.findall(r"^ROLLBACK;", text, re.MULTILINE)) == 1
    assert text.index("BEGIN;") < text.index("ALTER POLICY")
    assert text.rindex("ROLLBACK;") > text.index("RLS_PROBE_JESSICA_SQLSTATE:00000")


def test_lab4_rls_proof_fails_when_the_positive_controls_do_not_hold() -> None:
    """A deny-everyone database must not look like a successful RLS proof."""
    text = _read(LAB4_RLS_PROOF)
    for condition in (
        "mapped_shoppers <> 4",
        ":'marco_jessica_rows'::INTEGER <> 0",
        ":'jessica_jessica_rows'::INTEGER = 0",
        "RLS_PROBE_MARCO_SQLSTATE:00000",
    ):
        assert condition in text, (
            f"{LAB4_RLS_PROOF} must fail closed when {condition!r} is observed"
        )


def test_no_lab_anchor_is_a_broken_path() -> None:
    """One list, so a future anchor cannot be added without an existence check."""
    anchors: List[str] = [rel for rel, _ in LAB1_REGIONS]
    anchors += [source for source, _ in LAB1_FALLBACK_COPIES]
    anchors += [destination for _, destination in LAB1_FALLBACK_COPIES]
    anchors += [
        LAB2_STARTER,
        LAB2_REFERENCE,
        LAB2_PLAN_REFERENCE,
        LAB2_PLAN_REGION[0],
        LAB3_TRACE_CONTRACT,
        LAB4_ABSENCE_STARTER,
        LAB4_ABSENCE_REFERENCE,
        LAB4_STARTER,
        LAB4_REFERENCE,
        LAB4_PROOF_SCRIPT,
        LAB4_RLS_PROOF,
    ]
    absent = sorted({rel for rel in anchors if not (REPO / rel).is_file()})
    assert not absent, f"lab anchors missing from the repository: {absent}"


def test_participant_exercise_reset_declares_every_incomplete_artifact() -> None:
    source = _read(PARTICIPANT_EXERCISE_RESET)
    for exercise_id, (starter, destination) in PARTICIPANT_STARTERS.items():
        assert exercise_id in source
        assert starter in source
        assert destination in source


def test_participant_starter_copies_are_incomplete_not_solutions() -> None:
    inventory_agent = _read(PARTICIPANT_STARTERS["lab-1-inventory-agent"][0])
    inventory_tool = _read(PARTICIPANT_STARTERS["lab-1-inventory-tool"][0])
    lab2 = _read(PARTICIPANT_STARTERS["lab-2-rrf"][0])
    absence = _read(PARTICIPANT_STARTERS["lab-4-absence"][0])
    lab4 = _read(PARTICIPANT_STARTERS["lab-4-cedar"][0])

    assert "_INVENTORY_AGENT_STUBBED = True" in inventory_agent
    assert "_INVENTORY_TOOLS = []" in inventory_agent
    assert "_INVENTORY_SYSTEM_PROMPT_FOR_AGENT = _INVENTORY_SYSTEM_PROMPT" in inventory_agent
    assert '"error": "check_inventory is in stub state"' in inventory_tool
    assert "result = _run_async(logic.check_inventory" not in inventory_tool
    assert "0::numeric AS recomputed_rrf" in lab2
    assert all(placeholder in absence for placeholder in LAB4_ABSENCE_PLACEHOLDERS)
    assert "FROM pellier.tool_audit" not in absence
    assert re.search(r"unless\s*\{\s*false\s*\}", lab4)
    assert "CUST-JESSICA" not in lab4


def test_participant_exercise_reset_check_accepts_the_checked_in_starters() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO / PARTICIPANT_EXERCISE_RESET),
            "--repo",
            str(REPO),
            "--check",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    for exercise_id in PARTICIPANT_STARTERS:
        assert exercise_id in completed.stdout


def test_participant_exercise_reset_restores_only_the_named_marker_region() -> None:
    reset_script = REPO / PARTICIPANT_EXERCISE_RESET
    with tempfile.TemporaryDirectory() as tempdir:
        repo = Path(tempdir)
        for _exercise_id, (starter, destination) in PARTICIPANT_STARTERS.items():
            source_path = repo / starter
            destination_path = repo / destination
            source_path.parent.mkdir(parents=True, exist_ok=True)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text((REPO / starter).read_text(encoding="utf-8"))
            destination_path.write_text(
                (REPO / destination).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        inventory_destination = (
            repo / PARTICIPANT_STARTERS["lab-1-inventory-agent"][1]
        )
        inventory_destination.write_text(
            inventory_destination.read_text(encoding="utf-8").replace(
                "_INVENTORY_AGENT_STUBBED = True",
                "_INVENTORY_AGENT_STUBBED = False",
            )
            + "\n# PARTICIPANT_UNRELATED_EDIT\n",
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(reset_script), "--repo", str(repo)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        restored = inventory_destination.read_text(encoding="utf-8")
        assert "_INVENTORY_AGENT_STUBBED = True" in restored
        assert "# PARTICIPANT_UNRELATED_EDIT" in restored


# ---------------------------------------------------------------------------
# Lab titles, as the participant reads them in TWO products.
#
# Previously the guide was renamed without updating the
# shipped application, so the Observatory's Workshop Map and Proof Board went on
# naming "Design the Retrieval Strategy" while the guide beside them said "Measure Hybrid
# Retrieval Trade-offs". Nothing failed: the naming guards in this repository scan for
# retired SURFACE and TOOL names, and a lab title is neither.
#
# The same constraint as the rest of this file applies. CI does not clone the guide, so the
# canonical titles are written out once here and the source side is asserted against them.
# Changing a title means changing both repositories, which is the point.
# ---------------------------------------------------------------------------

CANONICAL_LAB_TITLE_PARTS: Tuple[Tuple[str, str], ...] = (
    ("Lab 1", "Build a PostgreSQL-Grounded Agent"),
    ("Lab 2", "Build and Measure PostgreSQL Hybrid Retrieval"),
    ("Lab 3", "Deploy and Operate Agents with Amazon Bedrock AgentCore"),
    ("Lab 4", "Build Governed Agent Actions with Cedar"),
)

# Titles the rename replaced. Present anywhere in the shipped product, they are drift.
RETIRED_LAB_TITLES: Tuple[str, ...] = (
    "Design the Retrieval Strategy",
    "Run Agents in a Managed Runtime",
    "Govern and Trace Agent Actions",
    "Operate and Observe the AgentCore Managed Path",
    "Deploy and Operate the Managed Agent Path",
    "Govern and Prove Agent Actions",
)

# Surfaces a participant actually reads a lab title on, plus the API that supplies one.
LAB_TITLE_SURFACES: Tuple[str, ...] = (
    "pellier/backend/routes/observatory.py",
    "pellier/frontend/src/observatory/surfaces/observe/WorkshopMap.tsx",
    "pellier/frontend/src/observatory/surfaces/observe/ProofBoard.tsx",
    "pellier/frontend/src/observatory/labs/labCatalog.ts",
)


def test_no_shipped_surface_names_a_retired_lab_title() -> None:
    """The finding this closes, asserted where a participant would see it."""
    findings = []
    for rel in LAB_TITLE_SURFACES:
        text = _read(rel)
        for retired in RETIRED_LAB_TITLES:
            if retired in text:
                line = text[: text.index(retired)].count("\n") + 1
                findings.append(f"  {rel}:{line}  {retired}")
    assert not findings, (
        "shipped surfaces still name retired lab titles, so the application and the guide "
        "disagree in the same viewport:\n" + "\n".join(findings)
    )


def test_the_workshop_map_and_proof_board_use_the_canonical_titles() -> None:
    """Absence of the old name is not presence of the new one.

    A surface that dropped its lab labels entirely would satisfy the check above while
    telling a participant less than before.
    """
    workshop_map = _read(
        "pellier/frontend/src/observatory/surfaces/observe/WorkshopMap.tsx"
    )
    for primary, subtitle in CANONICAL_LAB_TITLE_PARTS:
        assert primary in workshop_map, (
            f"the Workshop Map no longer names {primary!r}"
        )
        assert subtitle in workshop_map, (
            f"the Workshop Map no longer names {subtitle!r}"
        )

    api = _read("pellier/backend/routes/observatory.py")
    catalog = _read("pellier/frontend/src/observatory/labs/labCatalog.ts")
    for primary, subtitle in CANONICAL_LAB_TITLE_PARTS:
        assert f'"lab": "{primary}: {subtitle}"' in api, (
            f"the Proof Board API no longer names {primary}: {subtitle}"
        )
        assert f"title: '{subtitle}'" in catalog, (
            f"the Lab Collection no longer names {subtitle!r}"
        )


def test_the_retired_and_canonical_title_lists_do_not_overlap() -> None:
    """Guards the two lists above from being edited into agreement."""
    title_parts = {part for title in CANONICAL_LAB_TITLE_PARTS for part in title}
    assert not title_parts & set(RETIRED_LAB_TITLES)
    assert len(CANONICAL_LAB_TITLE_PARTS) == 4


# ---------------------------------------------------------------------------
# Build state, the surface a participant checks after each build.
# ---------------------------------------------------------------------------

_BUILD_STATE_DETECTORS = (
    ("2b", "_lab2_search_plan_is_workshop_stub"),
    ("3a", "_lab3_gateway_catalogue_is_workshop_stub"),
    ("3a-binding", "_lab3_support_contract_is_workshop_stub"),
)


@pytest.mark.parametrize(("step", "detector"), _BUILD_STATE_DETECTORS)
def test_build_state_reports_each_new_exercise_as_unbuilt(
    step: str, detector: str
) -> None:
    """The shipped tree is the starter state, so every step reads `exercise`.

    A detector that returned False here would tell a participant their build
    had landed before they made it, which is worse than reporting nothing.
    """
    from routes import observatory

    assert getattr(observatory, detector)() is True, (
        f"step {step}: the shipped starter is not detected as unbuilt"
    )


@pytest.mark.parametrize(("step", "detector"), _BUILD_STATE_DETECTORS)
def test_build_state_detects_each_reference_solution_as_built(
    step: str, detector: str
) -> None:
    """And the recovery copy must flip it, or the fallback lane proves nothing."""
    import shutil

    from routes import observatory

    live_for_step = {
        "2b": (
            "pellier/backend/services/search_plan.py",
            "solutions/the-quiet-search/retrieval/search_plan_solution.py",
        ),
        "3a": (
            "scripts/deploy/gateway_tool_schemas.py",
            "solutions/the-ledger/gateway/gateway_tool_schemas_solution.py",
        ),
        "3a-binding": (
            "pellier/backend/services/agentcore_gateway.py",
            "solutions/the-ledger/services/agentcore_gateway.py",
        ),
    }
    live_rel, solution_rel = live_for_step[step]
    live = REPO / live_rel
    backup = live.read_bytes()
    reloaded = ("services.search_plan", "services.agentcore_gateway")
    # Other test modules hold references to these module objects. Popping them
    # for good would leave those references stale and their monkeypatches
    # aimed at an object nothing imports any more; the originals go back.
    originals = {name: sys.modules.get(name) for name in reloaded}
    try:
        shutil.copyfile(REPO / solution_rel, live)
        for module in reloaded:
            sys.modules.pop(module, None)
        assert getattr(observatory, detector)() is False, (
            f"step {step}: the reference solution is not detected as built"
        )
    finally:
        live.write_bytes(backup)
        for module, original in originals.items():
            if original is not None:
                sys.modules[module] = original
            else:
                sys.modules.pop(module, None)


# ---------------------------------------------------------------------------
# Every reference solution the guide copies over a live file must be that live
# file plus the answer. On 2026-09-19 three twins had drifted outside their
# marker regions: the Lab 3a schema twin lacked `replace_damaged_item`, the Lab 3b
# runtime twin lacked the traceparent injection, and the Lab 1a agent twin carried
# older instructions. A participant taking the documented catch-up lane silently
# regressed the running application. This is the tripwire.
# ---------------------------------------------------------------------------

_PY_MARKER_BLOCK = re.compile(
    r"# === WORKSHOP · [^\n]*: START ===.*?# === WORKSHOP · [^\n]*: END ===", re.S
)
_SQL_MARKER_BLOCK = re.compile(
    r"-- === WORKSHOP · [^\n]*: START ===.*?-- === WORKSHOP · [^\n]*: END ===", re.S
)

REFERENCE_TWINS: Tuple[Tuple[str, str, re.Pattern], ...] = tuple(
    (source, destination, _PY_MARKER_BLOCK)
    for source, destination in LAB1_FALLBACK_COPIES + LAB3_FALLBACK_COPIES
) + (
    (LAB2_PLAN_REFERENCE, LAB2_PLAN_REGION[0], _PY_MARKER_BLOCK),
    (LAB2_REFERENCE, LAB2_STARTER, _SQL_MARKER_BLOCK),
    (LAB4_ABSENCE_REFERENCE, "workshop/lab-4-absence.sql", _SQL_MARKER_BLOCK),
)


@pytest.mark.parametrize(("source", "destination", "block"), REFERENCE_TWINS)
def test_reference_solution_matches_live_outside_the_markers(
    source: str, destination: str, block: re.Pattern
) -> None:
    """The catch-up copy changes the marker region and nothing else."""
    solution = (REPO / source).read_text(encoding="utf-8")
    live = (REPO / destination).read_text(encoding="utf-8")
    solution_blocks = block.findall(solution)
    live_blocks = block.findall(live)
    assert solution_blocks and len(solution_blocks) == len(live_blocks), (
        f"{source} and {destination} do not carry the same marker regions"
    )
    outside_solution = block.sub("<MARKER>", solution)
    outside_live = block.sub("<MARKER>", live)
    assert outside_solution == outside_live, (
        f"{source} drifted from {destination} outside the marker region; regenerate "
        "the reference from the live file so the catch-up lane cannot regress the app"
    )
