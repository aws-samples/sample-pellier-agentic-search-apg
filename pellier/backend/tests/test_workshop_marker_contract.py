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

**Lab 2 - Build a PostgreSQL-grounded agent.** Two marker regions to fix and two
fallback files to copy: 2A connects ``check_stock`` to the Stock agent in Python, and 2B
writes the not-carried test in the ``pellier.check_stock`` worksheet. A missing marker
breaks the primary lane; a missing fallback breaks the recovery lane, which is worse,
because it only fails for the participant who is already behind.

**Lab 1 - Build and measure PostgreSQL hybrid retrieval.** Two marker regions: the
vector search, which starts ranking nothing by meaning, and a search-plan fallback that
starts by dropping the shopper's limits. The RRF worksheet is Lab 1's Go deeper: it keeps
its marker region and starter, but it is not a task.

Each lab's starters fail the way its guide's See it fail step shows, and its solutions do
not: ``tests/test_lab1_vector.py``, ``tests/test_lab1_starter_failure.py`` and
``tests/test_lab2_starter_failure.py``.

**Lab 3 - Deploy agents and bind the caller with Amazon Bedrock AgentCore.** Three marker
regions and their fallback files. 3A publishes ``get_tickets`` on the Gateway and
matches the tools the Runtime asks the Gateway for, binding that read to the caller.
One of the two files is a packaged runtime source. Task 3B deploys those edits and checks
the executed fingerprint, which is how the participant proves their own build answered,
and writes the row-ownership predicate in an RLS worksheet whose one expression starts as
``false``. The OpenTelemetry trace contract is supplied, with no region to author.

**Lab 4 - Govern agent actions with Cedar policies and PostgreSQL privileges.** A starter
Cedar file that must NOT contain the answer, a reference rule that must (an amount rule on
``give_store_credit``, not an identity-pair match), and a credit-writer worksheet whose
starter over-grants the credit-writer role. The keyed absence check is supplied, with no region to
author.

Nine marked regions in all: eight marker regions and the Cedar ``unless`` block.
``tests/test_lab3_starter_failure.py`` and ``tests/test_lab4_starter_failure.py`` hold
Labs 3 and 4 to their See it fail steps.
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
# Lab 2, "10-ground-answers-in-live-data", steps 1 and 2 plus the pacing fallback.
# ---------------------------------------------------------------------------

LAB2_CHECK_STOCK_WORKSHEET = "workshop/lab-2-check-stock.sql"
LAB2_CHECK_STOCK_REFERENCE = "solutions/lab-2-ground/sql/lab-2-check-stock-solution.sql"
LAB2_CHECK_STOCK_MARKER = "WORKSHOP - Stock check - not carried"

LAB2_REGIONS: Tuple[Tuple[str, str], ...] = (
    ("pellier/backend/agents/stock_agent.py",
     "WORKSHOP - Stock agent - definition"),
    (LAB2_CHECK_STOCK_WORKSHEET, LAB2_CHECK_STOCK_MARKER),
)

# The exact `cp` sources in the guide's pacing fallback. A participant runs these
# verbatim, so a renamed solution file is a dead recovery lane.
LAB2_FALLBACK_COPIES: Tuple[Tuple[str, str], ...] = (
    ("solutions/lab-2-ground/agents/stock_agent_solution.py",
     "pellier/backend/agents/stock_agent.py"),
    (LAB2_CHECK_STOCK_REFERENCE, LAB2_CHECK_STOCK_WORKSHEET),
)

# ---------------------------------------------------------------------------
# Lab 1, bounded build artifact plus pacing fallback.
# ---------------------------------------------------------------------------

LAB1_VECTOR_REGION = (
    "pellier/backend/services/store_tools.py",
    "WORKSHOP - Vector search - order by meaning",
)
LAB1_VECTOR_REFERENCE = "solutions/lab-1-retrieve/retrieval/store_tools_solution.py"
LAB1_VECTOR_STARTER = "workshop/starters/lab-1/vector-search.pyfrag"
# Lab 1's Go deeper worksheet: a marker region and a starter, not a task.
LAB1_FUSION_WORKSHEET = "workshop/lab-1-fusion.sql"
LAB1_PLAN_REGION = (
    "pellier/backend/services/search_plan.py",
    "WORKSHOP - Search plan - preserve requirements",
)
LAB1_PLAN_REFERENCE = (
    "solutions/lab-1-retrieve/retrieval/search_plan_solution.py"
)
# The ids the documented predicate yields from `scripts/seed_pellier_catalog.py`:
# in-stock Home at or under $100 tagged both `gift` and `home`.
LAB1_GOLDEN_IDS = ("21", "23", "25", "27", "29", "80", "83")
LAB1_FUSION_REFERENCE = "solutions/lab-1-retrieve/sql/lab-1-fusion-solution.sql"
LAB1_FUSION_MARKER = "WORKSHOP - PostgreSQL RRF - fusion expression"

# ---------------------------------------------------------------------------
# Lab 3, two marker regions that together move the build onto the managed path.
# 3A publishes a Gateway tool and matches what the Runtime asks the Gateway
# for. `agentcore_gateway.py` is a packaged runtime source, so that edit changes
# the deployed build fingerprint checked in Task 3B.
# ---------------------------------------------------------------------------

LAB3_REGIONS: Tuple[Tuple[str, str], ...] = (
    ("scripts/deploy/gateway_tool_schemas.py",
     "WORKSHOP - Gateway - published tools"),
    ("pellier/backend/services/agentcore_gateway.py",
     "WORKSHOP - Support agent - Gateway tools"),
)

LAB3_FALLBACK_COPIES: Tuple[Tuple[str, str], ...] = (
    ("solutions/lab-3-deploy/gateway/gateway_tool_schemas_solution.py",
     "scripts/deploy/gateway_tool_schemas.py"),
    ("solutions/lab-3-deploy/services/agentcore_gateway.py",
     "pellier/backend/services/agentcore_gateway.py"),
)

# The tool Task 3A publishes and binds to the caller, and the staff-only tool no
# shopper agent may bind. There is no second deferred tool: the starter defers
# exactly the one the participant publishes.
LAB3_PUBLISHED_TOOL = "get_tickets"
LAB3_STAFF_ONLY_TOOL = "give_store_credit"

# ---------------------------------------------------------------------------
# Lab 4, "40-govern-actions-and-prove-outcomes": a Cedar rule and a trace
# contract.
# ---------------------------------------------------------------------------

LAB4_ABSENCE_CHECK = "workshop/lab-4-absence.sql"
LAB1_INDEX_CHECK = "workshop/lab-1-index.sql"
LAB1_MEANING_WORKSHEET = "workshop/lab-1-meaning.sql"
LAB3_TRACE_CONTRACT = "workshop/lab-3-otel-contract.jq"

LAB4_STARTER = "policies/credit_limit.cedar"
LAB4_REFERENCE = "solutions/lab-4-govern/policies/credit_limit.cedar"
LAB3_RLS_PROOF = "workshop/lab-3-row-ownership.sql"
LAB3_RLS_REFERENCE = "solutions/lab-3-deploy/sql/lab-3-row-ownership-solution.sql"
LAB3_RLS_MARKER = "WORKSHOP - Row ownership - predicate"
LAB4_WRITER_WORKSHEET = "workshop/lab-4-credit-writer.sql"
LAB4_WRITER_REFERENCE = "solutions/lab-4-govern/sql/lab-4-credit-writer-solution.sql"
LAB4_WRITER_MARKER = "WORKSHOP - Credit writer - privileges"

# The policy provisioning deploys and the participant's step updates.
LAB4_POLICY_NAME = "credit_limit"

# The target-qualified action Gateway generates: the one target `pellier-store-tools`
# plus the tool name. The guide shows it inside the starter, and the rule is inert
# against any other action id.
LAB4_ACTION = "pellier-store-tools___give_store_credit"

# The amount the reference rule admits, in cents ($100.00), and the input field it
# reads. The starter must carry neither in code.
LAB4_AMOUNT_FIELD = "amount_cents"
LAB4_AMOUNT_LIMIT_CENTS = "10000"

PARTICIPANT_EXERCISE_RESET = "scripts/reset_participant_exercises.py"
PARTICIPANT_STARTERS = {
    "lab-1-vector-search": (
        "workshop/starters/lab-1/vector-search.pyfrag",
        "pellier/backend/services/store_tools.py",
    ),
    "lab-2-stock-agent": (
        "workshop/starters/lab-2/stock-agent-definition.pyfrag",
        "pellier/backend/agents/stock_agent.py",
    ),
    "lab-2-check-stock": (
        "workshop/starters/lab-2-check-stock.sql",
        LAB2_CHECK_STOCK_WORKSHEET,
    ),
    "lab-1-fusion": (
        "workshop/starters/lab-1-fusion.sql",
        LAB1_FUSION_WORKSHEET,
    ),
    "lab-1-preserve-requirements": (
        "workshop/starters/lab-1/preserve-requirements.pyfrag",
        "pellier/backend/services/search_plan.py",
    ),
    "lab-3-gateway-catalog": (
        "workshop/starters/lab-3/gateway-published-tools.pyfrag",
        "scripts/deploy/gateway_tool_schemas.py",
    ),
    "lab-3-support-gateway-tools": (
        "workshop/starters/lab-3/support-gateway-tools.pyfrag",
        "pellier/backend/services/agentcore_gateway.py",
    ),
    "lab-3-row-ownership": (
        "workshop/starters/lab-3-row-ownership.sql",
        "workshop/lab-3-row-ownership.sql",
    ),
    "lab-4-cedar": (
        "workshop/starters/credit_limit.cedar",
        LAB4_STARTER,
    ),
    "lab-4-credit-writer": (
        "workshop/starters/lab-4-credit-writer.sql",
        "workshop/lab-4-credit-writer.sql",
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


@pytest.mark.parametrize("rel,label", LAB2_REGIONS)
def test_lab2_region_has_exactly_one_marker_pair(rel: str, label: str) -> None:
    """Two pairs would make "edit between the markers" ambiguous; zero makes it false."""
    text = _read(rel)
    assert text.count(f"{label}: START ===") == 1, f"{rel}: expected one START for {label}"
    assert text.count(f"{label}: END ===") == 1, f"{rel}: expected one END for {label}"


@pytest.mark.parametrize("rel,label", LAB2_REGIONS)
def test_lab2_region_is_ordered_and_not_empty(rel: str, label: str) -> None:
    """An inverted or empty region reads as "nothing to do here"."""
    text = _read(rel)
    start, end = _marker_pair(text, label)
    assert start < end, f"{rel}: START must precede END for {label}"
    body = text[text.index("\n", start) + 1:end]
    assert body.strip(), f"{rel}: the {label} region is empty"


@pytest.mark.parametrize("rel,label", LAB2_REGIONS)
def test_lab2_marker_uses_the_hyphen_the_guide_quotes(rel: str, label: str) -> None:
    """The guide quotes the marker with a plain hyphen, never a middle dot.

    A participant searching the file for the string in the guide finds nothing if the
    separators drift apart, and "search for this text" is the only instruction that
    lane gives.
    """
    text = _read(rel)
    assert " - " in label and "\u00b7" not in label
    assert label in text


@pytest.mark.parametrize("source,destination", LAB2_FALLBACK_COPIES)
def test_lab2_fallback_copy_exists_at_both_ends(source: str, destination: str) -> None:
    assert (REPO / source).is_file(), f"the guide copies {source}, which is absent"
    assert (REPO / destination).is_file(), f"the guide copies onto {destination}, which is absent"


@pytest.mark.parametrize("source,destination", LAB2_FALLBACK_COPIES)
def test_lab2_fallback_copy_keeps_the_markers(source: str, destination: str) -> None:
    """The recovery lane must not destroy the anchor.

    A participant who takes the fallback and then wants to read what changed needs the
    same marker region in the copied file. A solution written without markers turns one
    recovery into a dead end for the rest of the lab.
    """
    text = (REPO / source).read_text(encoding="utf-8")
    labels = [label for rel, label in LAB2_REGIONS if rel == destination]
    assert labels, f"{destination} is not a Lab 2 marker file"
    for label in labels:
        assert f"{label}: START ===" in text, f"{source} lost the {label} START marker"
        assert f"{label}: END ===" in text, f"{source} lost the {label} END marker"


@pytest.mark.parametrize(
    "starter,reference,label",
    (
        (LAB1_FUSION_WORKSHEET, LAB1_FUSION_REFERENCE, LAB1_FUSION_MARKER),
        (LAB2_CHECK_STOCK_WORKSHEET, LAB2_CHECK_STOCK_REFERENCE, LAB2_CHECK_STOCK_MARKER),
        (LAB3_RLS_PROOF, LAB3_RLS_REFERENCE, LAB3_RLS_MARKER),
        (LAB4_WRITER_WORKSHEET, LAB4_WRITER_REFERENCE, LAB4_WRITER_MARKER),
    ),
)
def test_the_sql_worksheets_have_matching_build_markers(
    starter: str,
    reference: str,
    label: str,
) -> None:
    for rel in (starter, reference):
        text = _read(rel)
        assert text.count(f"{label}: START ===") == 1
        assert text.count(f"{label}: END ===") == 1


def test_lab1_worksheet_finds_annas_receipt_and_fails_until_the_expression_is_right() -> None:
    starter = _read(LAB1_FUSION_WORKSHEET)
    reference = _read(LAB1_FUSION_REFERENCE)
    # Plausible but wrong: a missing rank counted as rank zero.
    assert "1.0 / (60 + coalesce(vector_rank, 0))" in starter
    assert "coalesce(1.0 / (60 + vector_rank), 0)" in reference
    for text in (starter, reference):
        assert "session_id LIKE 'persona-anna-%'" in text
        for retired in ("receipt_high_water", "comparison_id"):
            assert retired not in text
        assert "\\if :lab_1_passed" in text
        # `\quit` takes no argument; a raised exception under ON_ERROR_STOP is what
        # makes the worksheet exit non-zero, so a shell `&&` or `set -e` sees it.
        assert "\\quit 1" not in text
        assert "RAISE EXCEPTION" in text
        for line in ("Expected  ", "Observed ", "Evidence  ", "Next      "):
            assert line in text


def test_the_absence_check_is_supplied_and_finds_both_keys_itself() -> None:
    """No region to author, no keys to paste: it reads the probe review and Jessica's credit."""
    text = _read(LAB4_ABSENCE_CHECK)
    assert "WORKSHOP -" not in text, "the absence check is supplied; it carries no build markers"
    assert ":{?deny_key}" not in text and "-v deny_key" not in text
    sys.path.insert(0, str(REPO / "scripts"))
    import lab4_policy

    assert f"a.issue = '{lab4_policy.PROBE_ISSUE}'" in text
    for fragment in (
        "args->>'idempotency_key' = :'lab_4_deny_key'",
        "WHERE idempotency_key = :'lab_4_deny_key'",
        "WHERE idempotency_key = :'lab_4_allow_key'",
        "a.customer_id = 'CUST-JESSICA'",
        # Both keys are derived the same way, so the positive control covers it.
        "WHERE c.approval_id = a.id",
        ":lab_4_allowed_credit_rows = 1 AND :lab_4_allowed_audit_rows = 1 AS lab_4_control_holds",
        "Expected  ", "Observed ", "Evidence  ", "Next      ",
    ):
        assert fragment in text, fragment
    assert text.count("'operator-review:' || a.id || ':' || left(a.action_hash, 32)") == 2
    assert "INSERT" not in text and "UPDATE" not in text and "DELETE" not in text


def test_the_trace_contract_is_a_provided_check_not_a_build() -> None:
    contract = _read(LAB3_TRACE_CONTRACT)
    assert "WORKSHOP -" not in contract, "the trace contract is provided; it carries no build markers"
    for predicate in ("invoke_agent", "gen_ai.request.model", "execute_tool", "gen_ai.tool.name", 'attributes["session.id"]'):
        assert predicate in contract
    assert ": false" not in contract


def test_lab1_golden_set_region_has_exactly_one_marker_pair() -> None:
    rel, label = LAB1_PLAN_REGION
    text = _read(rel)
    assert text.count(f"# === {label}: START ===") == 1
    assert text.count(f"# === {label}: END ===") == 1


def test_lab1_golden_set_is_stated_once() -> None:
    """The eval harness must derive the labels, not carry a second copy.

    A duplicate literal would score the harness against a labeling the backend
    no longer uses and report a regression that exists only in that file.
    """
    harness = _read("scripts/eval_retrieval_harness.py")
    assert "CANONICAL_ANNA_GOLDEN_IDS" in harness
    for product_id in LAB1_GOLDEN_IDS:
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
    """3a is unbuilt until `get_tickets` leaves the deferred set."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    import gateway_tool_schemas

    published = gateway_tool_schemas.workshop_published_tools()
    assert LAB3_PUBLISHED_TOOL not in published, (
        f"{LAB3_PUBLISHED_TOOL} is already published; Lab 3a ships its own answer"
    )
    assert gateway_tool_schemas.UNPUBLISHED_TOOLS == frozenset({LAB3_PUBLISHED_TOOL}), (
        "the starter defers exactly the tool the participant publishes, and no other"
    )
    assert LAB3_PUBLISHED_TOOL in gateway_tool_schemas.canonical_tool_names(), (
        "the participant publishes an existing schema; it must stay in the catalog"
    )


def test_lab3_reference_publishes_the_read_and_the_staff_only_tool() -> None:
    solution = _load_module(
        "lab3_gateway_solution",
        "solutions/lab-3-deploy/gateway/gateway_tool_schemas_solution.py",
    )
    published = solution.workshop_published_tools()
    assert solution.UNPUBLISHED_TOOLS == frozenset(), "the reference defers nothing"
    assert LAB3_PUBLISHED_TOOL in published
    assert LAB3_STAFF_ONLY_TOOL in published, (
        "give_store_credit is published for the operator desk under a staff-only permit"
    )
    assert solution.STAFF_ONLY_GATEWAY_TOOLS == frozenset({LAB3_STAFF_ONLY_TOOL})
    assert solution.OWNER_SCOPED_GATEWAY_TOOLS == frozenset({"get_orders", "get_tickets"})


def test_lab3_starter_is_a_working_agent_without_theos_reads() -> None:
    """The failure Lab 3 fixes: a Support agent that works, but cannot read Theo's records."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    import gateway_tool_schemas

    from services import agentcore_gateway

    published = gateway_tool_schemas.workshop_published_tools()
    starter = set(agentcore_gateway.SUPPORT_GATEWAY_TOOLS)
    assert starter == {"get_return_policy", "ask_a_person"} and starter <= published, (
        "the starter Support agent must still answer a returns question"
    )
    assert LAB3_PUBLISHED_TOOL not in published, "the starter must withhold get_tickets"
    assert not starter & {"get_orders", LAB3_PUBLISHED_TOOL}, (
        "Lab 3 has nothing to assemble: the starter already asks for Theo's reads"
    )
    assert agentcore_gateway.SUPPORT_CALLER_BOUND_TOOLS == frozenset(), (
        "the starter must not pre-bind the ownership condition"
    )


def test_lab3_reference_matches_the_runtime_to_the_gateway() -> None:
    schemas = _load_module(
        "lab3_gateway_schemas_ref",
        "solutions/lab-3-deploy/gateway/gateway_tool_schemas_solution.py",
    )
    runtime = _load_module(
        "lab3_runtime_ref",
        "solutions/lab-3-deploy/services/agentcore_gateway.py",
    )
    published = schemas.workshop_published_tools()
    for agent, names in runtime.MANAGED_SPECIALIST_TOOLS.items():
        missing = sorted(set(names) - published)
        assert not missing, f"{agent} still asks for unpublished tools: {missing}"
    assert runtime.SUPPORT_CALLER_BOUND_TOOLS == frozenset({"get_orders", LAB3_PUBLISHED_TOOL})
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


def _cedar_code(text: str) -> str:
    """The policy with its `//` comment lines removed."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def test_lab4_starter_does_not_ship_the_answer() -> None:
    """The starter must hold the placeholder, not the amount rule.

    This is the same failure the fresh policy renderer had: a stack that pre-installs the
    participant's answer makes step 3's DENY fire before they have written anything, and
    the exercise silently becomes a copy-paste.
    """
    text = _read(LAB4_STARTER)
    assert re.search(r"unless\s*\{\s*false\s*\}", text), (
        f"{LAB4_STARTER} no longer holds the `unless {{ false }}` starter the guide "
        "tells the participant to replace"
    )
    code = _cedar_code(text)
    assert LAB4_AMOUNT_FIELD not in code, f"{LAB4_STARTER} reads {LAB4_AMOUNT_FIELD} already"
    assert LAB4_AMOUNT_LIMIT_CENTS not in code, f"{LAB4_STARTER} carries the limit already"


def test_lab4_starter_targets_the_generated_action() -> None:
    """A `forbid` on the wrong action id is inert, and an inert rule looks like an ALLOW."""
    text = _read(LAB4_STARTER)
    assert LAB4_ACTION in text, f"{LAB4_STARTER} must forbid {LAB4_ACTION}"
    # The live analyzer rejects `resource is AgentCore::Gateway` for a pinned action;
    # the guide substitutes the deployed ARN before the policy is added.
    assert 'resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"' in text
    assert "resource is AgentCore::Gateway" not in text
    assert text.lstrip().startswith("//") or "forbid(" in text


def test_lab4_reference_rule_admits_an_amount_up_to_the_limit() -> None:
    """The fallback must be complete, or the participant who takes it still fails the proof.

    The rule is an amount rule on `give_store_credit`, not an identity-pair match: the
    baseline permit already scopes the action to staff, and this forbid caps what one
    approved review may give.
    """
    text = _read(LAB4_REFERENCE)
    code = _cedar_code(text)
    assert LAB4_ACTION in code
    assert "context.input has amount_cents" in code
    assert "context.input.amount_cents <= 10000" in code
    # The rule reads the tool's input, never a list of shoppers.
    assert "CUST-" not in code and "getTag" not in code


def test_lab4_reference_rule_is_byte_identical_to_the_starter_outside_the_unless_block() -> None:
    """The Cedar pair keeps the twin convention: only the final unless block differs.

    ``same_rule`` ignores comments, so a header that drifted would still deploy the
    same rule; this keeps the recovery copy's comments the participant's own.
    """
    starter = _read(PARTICIPANT_STARTERS["lab-4-cedar"][0])
    reference = _read(LAB4_REFERENCE)
    assert starter[:starter.rindex("unless")] == reference[:reference.rindex("unless")]
    assert starter == _read(LAB4_STARTER), "the live file holds its starter"


def test_lab4_reference_rule_is_the_starter_plus_the_condition() -> None:
    """Same head, different body.

    If the reference drifted to a different action or effect, the fallback would deploy a
    policy that cannot produce the DENY the guide's step 3 asserts.
    """
    def head(text: str) -> str:
        code = _cedar_code(text)
        return code[code.index("forbid("):code.index("unless {")]

    starter = _read(LAB4_STARTER)
    reference = _read(LAB4_REFERENCE)
    for fragment in ("forbid(", "principal is AgentCore::OAuthUser,",
                     f'action == AgentCore::Action::"{LAB4_ACTION}"',
                     'resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"', "unless {"):
        assert fragment in starter, f"{LAB4_STARTER} lost {fragment!r}"
        assert fragment in reference, f"{LAB4_REFERENCE} lost {fragment!r}"
    assert head(starter) == head(reference)


def test_lab4_policy_name_matches_the_deployed_policy() -> None:
    """The file's name is the deployed policy's name, and the renderer reads that file."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    import render_agentcore_project as renderer

    assert Path(LAB4_STARTER).stem == LAB4_POLICY_NAME == renderer.CREDIT_LIMIT_POLICY
    assert renderer.CREDIT_LIMIT_SOURCE.as_posix() == LAB4_STARTER
    assert renderer.CREDIT_LIMIT_STARTER.as_posix() == PARTICIPANT_STARTERS["lab-4-cedar"][0]


def test_lab3_rls_proof_deploys_only_a_predicate_that_passes_every_probe() -> None:
    """One expression for USING and WITH CHECK on both tables, probed inside a savepoint.

    The probe writes are undone with the savepoint. The transaction commits, making
    the predicate the live policy, only on the passing branch, and rolls back on the
    failing one.
    """
    for rel in (LAB3_RLS_PROOF, LAB3_RLS_REFERENCE):
        text = _read(rel)
        for fragment in (
            "\\set ON_ERROR_STOP on",
            "ALTER POLICY orders_own_rows ON pellier.orders\n"
            "    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);",
            "ALTER POLICY support_tickets_own_rows ON pellier.support_tickets\n"
            "    USING (:ownership_predicate) WITH CHECK (:ownership_predicate);",
            "COMMENT ON POLICY orders_own_rows ON pellier.orders IS :'stamp';",
            "COMMENT ON POLICY support_tickets_own_rows ON pellier.support_tickets IS :'stamp';",
            "SET LOCAL ROLE pellier_agent",
            "set_config('pellier.principal_username', 'theo', true)",
            "set_config('pellier.principal_username', 'jessica', true)",
            "WHEN insufficient_privilege",
            "'42501'",
            "No one signed in reads orders",
            "Customers who see exactly their own orders and tickets",
            "ON COMMIT DROP",
            "Lab 3B predicate check passed", "Lab 3B predicate check failed",
            "Expected  ", "Observed ", "Evidence  ", "Next      ",
        ):
            assert fragment in text, f"{rel} lost {fragment!r}"
        assert "principal_customers" not in text and "pellier_query" not in text
        # A probe comparing the owner's count with the owner's count cannot fail.
        assert "The Operator desk reads every order" not in text
        assert len(re.findall(r"^BEGIN;", text, re.MULTILINE)) == 1
        assert len(re.findall(r"^SAVEPOINT probes;", text, re.MULTILINE)) == 1
        assert len(re.findall(r"^ROLLBACK TO SAVEPOINT probes;", text, re.MULTILINE)) == 1
        assert len(re.findall(r"^\s*COMMIT;", text, re.MULTILINE)) == 1
        assert len(re.findall(r"^\s*ROLLBACK;", text, re.MULTILINE)) == 1
        order = ["BEGIN;", "ALTER POLICY", "COMMENT ON POLICY", "SAVEPOINT probes;",
                 "SET LOCAL ROLE pellier_agent", "ROLLBACK TO SAVEPOINT probes;",
                 "\\if :lab_3_passed", "  COMMIT;", "Lab 3B predicate check passed", "\\else",
                 "  ROLLBACK;", "Lab 3B predicate check failed", "\\endif"]
        positions = [text.index(marker) for marker in order]
        assert positions == sorted(positions), list(zip(order, positions))
        after_probes = text[text.index("ROLLBACK TO SAVEPOINT probes;"):]
        writes = re.findall(r"\b(INSERT INTO|UPDATE|DELETE FROM)\s+(\S+)", after_probes)
        assert writes == [("INSERT INTO", "lab_3_probes")], writes


def test_lab3_rls_starter_is_false_and_the_reference_names_the_bound_customer() -> None:
    starter = _read(PARTICIPANT_STARTERS["lab-3-row-ownership"][0])
    reference = _read(LAB3_RLS_REFERENCE)
    assert "SELECT $predicate$\n  false\n$predicate$ AS ownership_predicate" in starter
    assert "current_setting('pellier.principal_username', true)" in reference
    assert "cognito_username" in reference


def test_the_lab1_index_check_is_read_only_and_forces_the_index_only_inside_it() -> None:
    """The worksheet changes nothing: one read-only transaction, rolled back, and every
    planner or scan setting it changes is SET LOCAL, so it ends with that transaction."""
    sql = _read(LAB1_INDEX_CHECK)
    statements = [line.strip() for line in sql.splitlines()
                  if line.strip() and not line.strip().startswith(("--", "\\"))]
    assert "BEGIN READ ONLY;" in statements and statements.count("ROLLBACK;") == 1
    assert statements.index("BEGIN READ ONLY;") < statements.index("ROLLBACK;")
    settings = [line for line in statements if line.upper().startswith("SET ")]
    assert settings and all(line.startswith(("SET LOCAL ", "SET client_min_messages"))
                            for line in settings), settings
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", sql.split("Run:")[1])


def test_the_lab1_meaning_worksheet_is_supplied_and_only_reads() -> None:
    """Task 1A's discovery worksheet has no region to author and changes nothing.

    It measures distances but never orders by one, so the order Task 1A writes
    and its direction cannot be copied from it.
    """
    sql = _read(LAB1_MEANING_WORKSHEET)
    body = sql.split("Run:")[1]
    assert "=== WORKSHOP" not in sql
    assert "p.embedding <=> q.emb" in body and "vector_cosine_ops" in sql
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|GRANT)\b", body)
    assert not re.search(r"ORDER BY[^;]*<=>|\bDESC\b", body)


def test_no_lab_anchor_is_a_broken_path() -> None:
    """One list, so a future anchor cannot be added without an existence check."""
    anchors: List[str] = [rel for rel, _ in LAB2_REGIONS]
    anchors += [source for source, _ in LAB2_FALLBACK_COPIES]
    anchors += [destination for _, destination in LAB2_FALLBACK_COPIES]
    anchors += [
        LAB1_FUSION_WORKSHEET,
        LAB1_FUSION_REFERENCE,
        LAB1_PLAN_REFERENCE,
        LAB1_PLAN_REGION[0],
        LAB1_INDEX_CHECK,
        LAB1_MEANING_WORKSHEET,
        LAB3_TRACE_CONTRACT,
        LAB4_ABSENCE_CHECK,
        LAB4_STARTER,
        LAB4_REFERENCE,
        LAB3_RLS_PROOF,
        LAB3_RLS_REFERENCE,
        LAB1_VECTOR_REGION[0],
        LAB1_VECTOR_REFERENCE,
        LAB1_VECTOR_STARTER,
        LAB4_WRITER_WORKSHEET,
        LAB4_WRITER_REFERENCE,
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
    stock_agent = _read(PARTICIPANT_STARTERS["lab-2-stock-agent"][0])
    stock_tool = _read(PARTICIPANT_STARTERS["lab-2-check-stock"][0])
    lab1 = _read(PARTICIPANT_STARTERS["lab-1-fusion"][0])
    rls = _read(PARTICIPANT_STARTERS["lab-3-row-ownership"][0])
    lab4 = _read(PARTICIPANT_STARTERS["lab-4-cedar"][0])
    vector = _read(PARTICIPANT_STARTERS["lab-1-vector-search"][0])
    writer = _read(PARTICIPANT_STARTERS["lab-4-credit-writer"][0])

    lab1_plan = _read(PARTICIPANT_STARTERS["lab-1-preserve-requirements"][0])

    # Each starter runs and fails visibly; none is a stub.
    assert "agent_tools.search_products," in stock_agent
    assert "check_stock" not in stock_agent.split("_STOCK_TOOLS = [", 1)[1].split("]", 1)[0]
    assert "_STOCK_SYSTEM_PROMPT_FOR_AGENT = _STOCK_SYSTEM_PROMPT" in stock_agent
    # The not-carried region holds only its comment; the aggregate below it is supplied.
    region = stock_tool.split(f"{LAB2_CHECK_STOCK_MARKER}: START ===", 1)[1].split(
        f"{LAB2_CHECK_STOCK_MARKER}: END ===", 1)[0]
    assert all(line.strip().startswith("--") for line in region.splitlines()[1:] if line.strip())
    assert "coalesce(sum(w.quantity), 0)::integer" in stock_tool
    assert "return SearchPlan(" in lab1_plan and "hard=" not in lab1_plan
    assert "1.0 / (60 + coalesce(vector_rank, 0))" in lab1
    for starter in (stock_agent, lab1_plan):
        assert "WORKSHOP_EXERCISE_STUB" not in starter
        assert "raise" not in starter
    assert "SELECT $predicate$\n  false\n$predicate$" in rls
    assert re.search(r"unless\s*\{\s*false\s*\}", lab4)
    assert "CUST-JESSICA" not in lab4
    assert "NULL::float AS similarity" in vector and "ORDER BY" not in vector
    assert "GRANT SELECT, INSERT, UPDATE ON pellier.store_credits" in writer
    assert "SECURITY DEFINER" not in writer


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

        stock_destination = (
            repo / PARTICIPANT_STARTERS["lab-2-stock-agent"][1]
        )
        starter_grant = "_STOCK_TOOLS = [\n    agent_tools.search_products,"
        stock_destination.write_text(
            stock_destination.read_text(encoding="utf-8").replace(
                starter_grant, "_STOCK_TOOLS = [\n    # PARTICIPANT_EDIT",
            )
            + "\n# PARTICIPANT_UNRELATED_EDIT\n",
            encoding="utf-8",
        )
        assert "# PARTICIPANT_EDIT" in stock_destination.read_text(encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, str(reset_script), "--repo", str(repo)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        restored = stock_destination.read_text(encoding="utf-8")
        assert starter_grant in restored and "# PARTICIPANT_EDIT" not in restored
        assert "# PARTICIPANT_UNRELATED_EDIT" in restored


# ---------------------------------------------------------------------------
# Lab titles, as the participant reads them in TWO products.
#
# Previously the guide was renamed without updating the
# shipped application, so the application's workshop map went on
# naming "Design the Retrieval Strategy" while the guide beside it said "Measure Hybrid
# Retrieval Trade-offs". Nothing failed: the naming guards in this repository scan for
# retired SURFACE and TOOL names, and a lab title is neither.
#
# The same constraint as the rest of this file applies. CI does not clone the guide, so the
# canonical titles are written out once here and the source side is asserted against them.
# Changing a title means changing both repositories, which is the point.
# ---------------------------------------------------------------------------

CANONICAL_LAB_TITLE_PARTS: Tuple[Tuple[str, str], ...] = (
    ("Lab 2", "Build a PostgreSQL-grounded agent"),
    ("Lab 1", "Build and measure PostgreSQL hybrid retrieval"),
    ("Lab 3", "Deploy agents and bind the caller with Amazon Bedrock AgentCore"),
    ("Lab 4", "Govern agent actions with Cedar policies and PostgreSQL privileges"),
)

# Titles the rename replaced. Present anywhere in the shipped product, they are drift.
RETIRED_LAB_TITLES: Tuple[str, ...] = (
    "Design the Retrieval Strategy",
    "Run Agents in a Managed Runtime",
    "Govern and Trace Agent Actions",
    "Operate and Observe the AgentCore Managed Path",
    "Deploy and Operate the Managed Agent Path",
    "Govern and Prove Agent Actions",
    "Deploy and Operate Agents with Amazon Bedrock AgentCore",
    "Build Governed Agent Actions with Cedar",
    "Govern Agent Actions with Cedar and PostgreSQL Row-Level Security",
    # Title case, retired for sentence case on 2026-10-28 (Workshop Studio content scan).
    "Build and Measure PostgreSQL Hybrid Retrieval",
    "Build a PostgreSQL-Grounded Agent",
    "Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore",
    "Govern Agent Actions with Cedar Policies and PostgreSQL Privileges",
)

# Surfaces a participant actually reads a lab title on, plus the API that supplies one.
# The Workshop Map is retired; the Workbench heading and the lab guide replaced it.






def test_the_retired_and_canonical_title_lists_do_not_overlap() -> None:
    """Guards the two lists above from being edited into agreement."""
    title_parts = {part for title in CANONICAL_LAB_TITLE_PARTS for part in title}
    assert not title_parts & set(RETIRED_LAB_TITLES)
    assert len(CANONICAL_LAB_TITLE_PARTS) == 4


# ---------------------------------------------------------------------------
# Every reference solution the guide copies over a live file must be that live
# file plus the answer. On 2026-09-19 three twins had drifted outside their
# marker regions: the Lab 3a schema twin lacked a published tool schema, the Lab 3b
# runtime twin lacked the traceparent injection, and the Lab 2a agent twin carried
# older instructions. A participant taking the documented catch-up lane silently
# regressed the running application. This is the tripwire.
# ---------------------------------------------------------------------------

_PY_MARKER_BLOCK = re.compile(
    r"# === WORKSHOP - [^\n]*: START ===.*?# === WORKSHOP - [^\n]*: END ===", re.S
)
_SQL_MARKER_BLOCK = re.compile(
    r"-- === WORKSHOP - [^\n]*: START ===.*?-- === WORKSHOP - [^\n]*: END ===", re.S
)

REFERENCE_TWINS: Tuple[Tuple[str, str, re.Pattern], ...] = tuple(
    (source, destination, _SQL_MARKER_BLOCK if destination.endswith(".sql") else _PY_MARKER_BLOCK)
    for source, destination in LAB2_FALLBACK_COPIES + LAB3_FALLBACK_COPIES
) + (
    (LAB1_VECTOR_REFERENCE, LAB1_VECTOR_REGION[0], _PY_MARKER_BLOCK),
    (LAB1_PLAN_REFERENCE, LAB1_PLAN_REGION[0], _PY_MARKER_BLOCK),
    (LAB1_FUSION_REFERENCE, LAB1_FUSION_WORKSHEET, _SQL_MARKER_BLOCK),
    (LAB3_RLS_REFERENCE, LAB3_RLS_PROOF, _SQL_MARKER_BLOCK),
    (LAB4_WRITER_REFERENCE, LAB4_WRITER_WORKSHEET, _SQL_MARKER_BLOCK),
)


def test_the_participant_path_is_nine_marked_regions() -> None:
    """Five marker regions in source, three worksheets' regions, and the Cedar block.

    The RRF worksheet's region is Lab 1's Go deeper and is not counted.
    """
    marked = [LAB1_VECTOR_REGION, LAB1_PLAN_REGION, *LAB2_REGIONS, *LAB3_REGIONS,
              (LAB3_RLS_PROOF, LAB3_RLS_MARKER), (LAB4_WRITER_WORKSHEET, LAB4_WRITER_MARKER)]
    for rel, label in marked:
        assert _read(rel).count(f"{label}: START ===") == 1, rel
        assert _read(rel).count(f"{label}: END ===") == 1, rel
    assert len(marked) + 1 == 9, "eight marker regions and the Cedar unless block"


def test_lab1_vector_region_starts_ranking_nothing_and_the_reference_orders_by_meaning() -> None:
    rel, label = LAB1_VECTOR_REGION
    starter = _read(LAB1_VECTOR_STARTER)
    reference = _read(LAB1_VECTOR_REFERENCE)
    assert "NULL::float AS similarity" in starter and "ORDER BY" not in starter
    assert "LIMIT %s" in starter, "the parameter order is fixed, so LIMIT stays in the starter"
    assert reference.count(f"{label}: START ===") == 1
    assert "1 - (embedding <=> (SELECT emb FROM query_embedding)) AS similarity" in reference
    assert "ORDER BY embedding <=> (SELECT emb FROM query_embedding)" in reference


def test_every_checked_in_starter_is_under_the_reset_guard() -> None:
    """A starter with no reset entry lets a solution sit in the working tree unnoticed.

    The reset's ``--check`` compares each live region or worksheet with its starter, so a
    tree that holds a solution fails the suite only if every starter is listed here.
    """
    on_disk = {path.relative_to(REPO).as_posix()
               for path in (REPO / "workshop" / "starters").rglob("*") if path.is_file()}
    listed = {starter for starter, _destination in PARTICIPANT_STARTERS.values()}
    assert on_disk == listed


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
