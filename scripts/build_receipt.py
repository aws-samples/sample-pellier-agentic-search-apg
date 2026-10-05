#!/usr/bin/env python3
"""Assemble one portable build receipt for a participant's workshop run.

What this is
------------

Four labs each end in durable evidence, but that evidence is spread across the
Aurora tables, a source-state check, and a managed-runtime receipt. A
participant who finishes the workshop has proved a great deal and has nothing
to take home that says so. This assembles exactly one artifact from evidence
that already exists -- it creates no tables, writes no rows, and invents no
state.

It is also the fastest table-lead diagnostic in the room: one command that says
which boundary a stuck participant has not crossed yet, and names the row that
would prove it.

The honesty rule
----------------

Every line reports one of four states, never two:

    PROVED       a durable row exists and satisfies the claim
    NOT YET      the lab has not left its evidence
    UNCHECKED    the query could not run (no database, no credentials)
    CONTRADICTED the search ran and found evidence against the claim

UNCHECKED is not a soft NOT YET. "This did not happen" and "I could not look"
are different findings, and a receipt that blurs them is worse than no receipt,
because it invites a participant to conclude they failed at something the tool
simply never examined.

The scope
---------

One workshop box serves one participant, and a reset rebuilds its database
from scratch, so every query reads the newest evidence on the box.

Usage
-----

    python3 scripts/build_receipt.py
    python3 scripts/build_receipt.py --strict            # exit 1 unless complete
    python3 scripts/build_receipt.py --json receipt.json --markdown receipt.md
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import quote_plus

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"
DEFAULT_ENV = BACKEND / ".env"

PROVED = "PROVED"
NOT_YET = "NOT YET"
UNCHECKED = "UNCHECKED"
# A claim whose own evidence refutes it. Distinct from NOT YET (no evidence)
# and from UNCHECKED (no look): here the search ran, and what it found says the
# opposite of the claim.
CONTRADICTED = "CONTRADICTED"


# ---------------------------------------------------------------------------
# Source state -- read as text, deliberately
# ---------------------------------------------------------------------------
# The backend decides shipped-vs-exercise by importing the modules and
# inspecting their source. Importing them here would drag in FastAPI, settings,
# and a database handle, so a receipt could not be produced on a box whose
# backend does not start -- which is precisely when a table lead needs one. The
# marker strings below are the same ones routes/observatory.py looks for.


def _reads_as_stub(path: pathlib.Path, markers: tuple[str, ...]) -> Optional[bool]:
    """True when the file still reads as the shipped starter, None if unreadable."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return any(marker in source for marker in markers)


def _region_reads_as_stub(
    path: pathlib.Path, region: str, markers: tuple[str, ...]
) -> Optional[bool]:
    """Same question, asked only inside one ``WORKSHOP ·`` marked region.

    Several starters are a value the participant edits rather than a sentinel
    they delete, and that value's text also appears elsewhere in the same file
    (a docstring, a neighbouring catalogue). Searching the whole file would
    report a completed build as untouched forever.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    start = source.find(f"WORKSHOP - {region}: START ===")
    end = source.find(f"WORKSHOP - {region}: END ===")
    if start == -1 or end == -1 or end <= start:
        # The region is gone. That is not a starter, and it is not a finished
        # build either -- it is a file this receipt can no longer speak about.
        return None
    block = source[start:end]
    return any(marker in block for marker in markers)


# Source regions supporting four labs and eight participant tasks.
# A task may contain several edits or a deployed investigation. Source inspection
# alone does not establish that a participant ran the corresponding checks.
_BUILDS: tuple[tuple[str, str, pathlib.Path, Optional[str], tuple[str, ...]], ...] = (
    (
        "01_measure_hybrid_retrieval", "1a_rrf_expression_authored",
        REPO / "workshop" / "lab-1-rrf.sql",
        "PostgreSQL RRF - fusion expression", ("0::numeric AS recomputed_rrf",),
    ),
    (
        "01_measure_hybrid_retrieval", "1b_requirements_preserved",
        BACKEND / "services" / "search_plan.py",
        "Search plan - preserve requirements",
        ("Complete Task 1B before relaxing a preference",),
    ),
    (
        "02_ground_the_answer", "2b_stock_agent_defined",
        BACKEND / "agents" / "stock_agent.py",
        None, ("_STOCK_AGENT_STUBBED = True",),
    ),
    (
        "02_ground_the_answer", "2a_stock_tool_written",
        BACKEND / "services" / "agent_tools.py",
        None, ("check_stock is in stub state", "received_product_query"),
    ),
    (
        "03_operate_the_managed_path", "3a_gateway_tool_published",
        REPO / "scripts" / "deploy" / "gateway_tool_schemas.py",
        "Gateway catalogue - published tools", ('"get_tickets"',),
    ),
    (
        "03_operate_the_managed_path", "3a_runtime_catalogue_reconciled",
        BACKEND / "services" / "agentcore_gateway.py",
        "Managed catalogue - support reconcile",
        ("SUPPORT_CALLER_BOUND_TOOLS: frozenset[str] = frozenset()",),
    ),
    (
        "04_govern_and_prove", "4a_identity_rule_authored",
        REPO / "policies" / "workshop_identity_match_forbid.cedar",
        None, ("unless {\n  false\n}",),
    ),
    (
        "04_govern_and_prove", "4b_rls_predicate_authored",
        REPO / "workshop" / "lab-4-rls.sql",
        "Row ownership - predicate", ("ownership_predicate 'false'",),
    ),
    (
        "04_govern_and_prove", "4b_absence_query_authored",
        REPO / "workshop" / "lab-4-absence.sql",
        "Keyed absence - deny proof",
        ("NULL::bigint AS denied_execution_rows",
         "NULL::bigint AS denied_write_rows",
         "NULL::bigint AS denied_finalized_writes",
         "NULL::bigint AS denied_ledger_rows",
         "NULL::bigint AS allowed_finalized_writes"),
    ),
)


def _source_state(is_stub: Optional[bool]) -> str:
    if is_stub is None:
        return UNCHECKED
    return NOT_YET if is_stub else PROVED


def collect_source_state() -> Dict[str, Any]:
    """Inspect every authored source region, not only Lab 2's two.

    A receipt that checked Lab 2's source and nothing else could report a
    complete workshop for a participant who never opened Labs 1, 3, or 4's
    starters, because their evidence rows can be produced by the shipped
    reference implementation running underneath them.
    """
    state: Dict[str, Any] = {}
    for lab, name, path, region, markers in _BUILDS:
        stub = (
            _region_reads_as_stub(path, region, markers)
            if region
            else _reads_as_stub(path, markers)
        )
        state[name] = {"lab": lab, "state": _source_state(stub)}
    return state


def collect_provenance() -> Dict[str, Any]:
    """Which content this box is running, and which revision it would deploy."""
    provenance: Dict[str, Any] = {}

    ref_file = REPO / ".workshop-ref.json"
    if ref_file.exists():
        try:
            provenance["source"] = json.loads(ref_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            provenance["source"] = {"error": "unreadable .workshop-ref.json"}
    else:
        # The env var is exported by CloudFormation UserData and dies with the
        # bootstrap shell, so it is a fallback, not the primary record.
        revision = os.environ.get("WORKSHOP_SOURCE_REVISION", "")
        provenance["source"] = {"repo_ref": revision} if revision else {}

    # The digest the renderer would stamp on a deploy from this tree. Comparing
    # it against what Runtime echoes is what proves the managed path executed
    # the participant's revision rather than a previous deployment.
    try:
        sys.path.insert(0, str(BACKEND))
        from services.build_fingerprint import compute_fingerprint

        provenance["runtime_build_fingerprint"] = compute_fingerprint(BACKEND)
    except Exception as exc:  # noqa: BLE001 - provenance is never load-bearing
        provenance["runtime_build_fingerprint"] = ""
        provenance["runtime_build_fingerprint_error"] = (
            f"{type(exc).__name__}: {str(exc)[:120]}"
        )
    return provenance


# ---------------------------------------------------------------------------
# Aurora evidence
# ---------------------------------------------------------------------------

# Lab 1 -- a receipt carrying BOTH retrieval ranks and their fusion. Vector or
# lexical alone is not hybrid retrieval, so all three must be populated.
_LAB1 = """
SELECT receipt_id, turn_id, query_preview, embedding_model, rerank_model,
       retrieval_config, latency_breakdown, modeled_cost_usd,
       jsonb_array_length(COALESCE(citation_ids, '[]'::jsonb)) AS citations,
       (rerank_scores IS NOT NULL AND rerank_scores <> '{}'::jsonb) AS reranked
  FROM pellier.retrieval_receipts
 WHERE rrf_scores <> '{}'::jsonb
   AND vector_ranks <> '{}'::jsonb
   AND lexical_ranks <> '{}'::jsonb
 ORDER BY receipt_id DESC
 LIMIT 1;
"""

# Lab 2 -- the tool ran and left a completed execution row.
_LAB2 = """
SELECT audit_id, session_id, caller, latency_ms, created_at
  FROM pellier.tool_audit
 WHERE tool = 'check_stock'
   AND result IS NOT NULL
 ORDER BY audit_id DESC
 LIMIT 1;
"""

# Lab 3 -- the managed rail, proved durably. The Gateway Lambda writes a
# shopper turn's read with the turn id as its session and the build the Runtime
# reported, so the newest such row says which deployed build answered. Rows
# that carry a build are preferred, because only they can be compared with
# this checkout.
_LAB3 = """
SELECT audit_id, session_id AS turn_id, tool, build_fingerprint AS deployed_fingerprint,
       created_at
  FROM pellier.tool_audit
 WHERE caller = 'gateway'
   AND session_id LIKE 'turn-%'
 ORDER BY (build_fingerprint IS NOT NULL) DESC, audit_id DESC
 LIMIT 1;
"""

# Lab 4 -- an approved credit executed once. The write key is the approved
# review's own, so the credit and its tool_audit row are found by that key and
# by nothing else; a retry must leave both counts at one.
_LAB4 = """
SELECT sc.credit_id, sc.approval_id, sc.customer_id, sc.amount_cents,
       sc.idempotency_key,
       (a.args->>'amount_cents')::int AS approved_cents,
       (SELECT count(*) FROM pellier.store_credits
         WHERE idempotency_key = sc.idempotency_key) AS credit_rows,
       (SELECT count(*) FROM pellier.tool_audit
         WHERE tool = 'give_store_credit'
           AND args->>'idempotency_key' = sc.idempotency_key) AS audit_rows
  FROM pellier.store_credits sc
  JOIN pellier.approvals a ON a.id = sc.approval_id
 ORDER BY sc.credit_id DESC
 LIMIT 1;
"""


def parse_dotenv(env_path: pathlib.Path) -> Dict[str, str]:
    """Read KEY=value lines from a dotenv file without shell interpolation."""
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            values[key] = value.strip().strip('"').strip("'")
    return values


def db_config(env_path: pathlib.Path) -> Optional[Dict[str, str]]:
    """Database settings from the backend .env, with the environment overriding."""
    cfg = parse_dotenv(env_path)
    for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_PORT"):
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    if not all(cfg.get(k) for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")):
        return None
    return cfg


def connection_dsn(cfg: Dict[str, str]) -> str:
    return (
        f"postgresql://{cfg['DB_USER']}:{quote_plus(cfg['DB_PASSWORD'])}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT', '5432')}/{cfg['DB_NAME']}"
    )


def psycopg_connector() -> Optional[Callable[[str], Any]]:
    """Return a factory that opens one dict-row connection from a DSN.

    Sibling scripts (``workshop_doctor.py``) read the same Aurora with the same
    driver settings, so the factory is public rather than reimplemented there.

    Returns:
        A callable taking a DSN and returning a connection, or None when
        psycopg is not installed on this box.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        return None
    return lambda dsn: psycopg.connect(dsn, row_factory=dict_row, connect_timeout=15)


def read_evidence(
    env_path: pathlib.Path,
    connect: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Read every lab's newest evidence row.

    Args:
        env_path: Backend ``.env`` to take database settings from.
        connect: Connection factory taking a DSN; defaults to psycopg. Tests
            inject one here.

    Returns:
        A dict with ``available`` and, when True, one entry per lab.
    """
    cfg = db_config(env_path)
    if cfg is None:
        return {
            "available": False,
            "reason": f"no database settings in {env_path} or the environment",
        }
    connect = connect or psycopg_connector()
    if connect is None:
        return {"available": False, "reason": "psycopg is not installed"}

    out: Dict[str, Any] = {"available": True}
    try:
        with connect(connection_dsn(cfg)) as conn:
            for label, sql in (("lab1", _LAB1), ("lab2", _LAB2), ("lab3", _LAB3), ("lab4", _LAB4)):
                with conn.cursor() as cur:
                    cur.execute(sql)
                    out[label] = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - report, never raise, to the room
        return {
            "available": False,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _fingerprint_state(
    lab3_row: Optional[Dict[str, Any]], local: str, available: bool
) -> str:
    """Did the managed Runtime execute THIS checkout's package?

    A successful managed turn proves the service answered. It does not say
    whose code answered: ``qualifier=DEFAULT`` reads identically for the
    participant's deployment and for the one before it, which is exactly why
    the renderer stamps a content digest into the package and the Runtime
    stamps it on every tool call it makes. This compares that stamp with the
    digest of this checkout.
    """
    if not available:
        return UNCHECKED
    if not lab3_row:
        return NOT_YET
    deployed = str(lab3_row.get("deployed_fingerprint") or "").strip()
    if not deployed or not local:
        # A row written before the stamp existed, or a checkout whose digest
        # could not be computed: neither is a failed comparison.
        return UNCHECKED
    return PROVED if deployed == local else CONTRADICTED


def _lab4_findings(row: Optional[Dict[str, Any]], available: bool) -> Dict[str, Any]:
    """One approved credit, recorded once, for the amount a person approved."""
    if not available:
        return {"credit_recorded_once": UNCHECKED, "approved_amount_recorded": UNCHECKED}
    if not row:
        return {"credit_recorded_once": NOT_YET, "approved_amount_recorded": NOT_YET}
    once = int(row.get("credit_rows") or 0) == 1 and int(row.get("audit_rows") or 0) == 1
    amount = row.get("approved_cents") is not None and int(row["approved_cents"]) == int(
        row.get("amount_cents") or 0
    )
    return {
        "credit_recorded_once": PROVED if once else CONTRADICTED,
        "approved_amount_recorded": PROVED if amount else CONTRADICTED,
    }


def assemble(evidence: Dict[str, Any]) -> Dict[str, Any]:
    source = collect_source_state()
    available = bool(evidence.get("available"))

    def row_state(key: str) -> str:
        if not available:
            return UNCHECKED
        return PROVED if evidence.get(key) else NOT_YET

    provenance = collect_provenance()
    lab3_row = evidence.get("lab3") if available else None
    lab4_row = evidence.get("lab4") if available else None

    def builds_for(lab: str) -> Dict[str, str]:
        return {
            name: entry["state"]
            for name, entry in source.items()
            if entry["lab"] == lab
        }

    receipt: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence_source": (
            "aurora" if available else f"unavailable ({evidence.get('reason', '')})"
        ),
        "provenance": provenance,
        "labs": {
            "01_measure_hybrid_retrieval": {
                **builds_for("01_measure_hybrid_retrieval"),
                "hybrid_receipt": row_state("lab1"),
                "detail": evidence.get("lab1") if available else None,
            },
            "02_ground_the_answer": {
                **builds_for("02_ground_the_answer"),
                "execution_row": row_state("lab2"),
                "detail": evidence.get("lab2") if available else None,
            },
            "03_operate_the_managed_path": {
                **builds_for("03_operate_the_managed_path"),
                "managed_rail": row_state("lab3"),
                "runtime_revision_is_yours": _fingerprint_state(
                    lab3_row, str(provenance.get("runtime_build_fingerprint") or ""), available
                ),
                "detail": lab3_row,
            },
            "04_govern_and_prove": {
                **builds_for("04_govern_and_prove"),
                **_lab4_findings(lab4_row, available),
                "detail": lab4_row,
            },
        },
    }

    # An explicit list of what this run has NOT established. A receipt that only
    # lists successes reads as a certificate; the unproven column is the half a
    # participant can act on, and the half a table lead needs.
    unproven: List[str] = []
    _reported = {PROVED, NOT_YET, UNCHECKED, CONTRADICTED}
    for lab, claims in receipt["labs"].items():
        for claim, state in claims.items():
            # Only the four states are graded. `policy_name` and the search
            # detail are context, not claims, and must not be read as a pass
            # merely by not being one of the failure words.
            if not isinstance(state, str) or state not in _reported:
                continue
            if state != PROVED:
                unproven.append(f"{lab}.{claim}: {state}")
    receipt["unproven"] = unproven
    receipt["complete"] = not unproven
    return receipt


def _fmt(state: Any) -> str:
    return str(state) if isinstance(state, str) else str(state)


def render_markdown(receipt: Dict[str, Any]) -> str:
    lines: List[str] = []
    add = lines.append
    add("# Pellier build receipt")
    add("")
    add(f"- Generated: `{receipt['generated_at']}`")
    add(f"- Evidence source: `{receipt['evidence_source']}`")
    prov = receipt.get("provenance", {})
    src = prov.get("source") or {}
    if src.get("repo_ref") or src.get("resolved_sha"):
        add(
            f"- Source: `{src.get('repo_ref', '?')}` @ "
            f"`{str(src.get('resolved_sha', '?'))[:12]}`"
        )
    if prov.get("runtime_build_fingerprint"):
        add(f"- Runtime build (this checkout): `{prov['runtime_build_fingerprint'][:12]}`")
    lab3 = receipt["labs"].get("03_operate_the_managed_path", {})
    detail3 = lab3.get("detail") if isinstance(lab3.get("detail"), dict) else {}
    if detail3.get("deployed_fingerprint"):
        add(
            f"- Runtime build (executed): `{str(detail3['deployed_fingerprint'])[:12]}`"
            f" -- {lab3.get('runtime_revision_is_yours', UNCHECKED)}"
        )
    add("")

    # The lab as the participant met it. The keys are join keys and never
    # change; these are display strings and must match the guide's own titles,
    # because the receipt is the artifact that leaves the room and a reader
    # comparing it to the page should not have to work out that "02 Measure
    # hybrid retrieval" and "Build and Measure PostgreSQL Hybrid Retrieval"
    # are the same lab.
    titles = {
        "01_measure_hybrid_retrieval": (
            "Lab 1: Build and Measure PostgreSQL Hybrid Retrieval"
        ),
        "02_ground_the_answer": "Lab 2: Build a PostgreSQL-Grounded Agent",
        "03_operate_the_managed_path": (
            "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore"
        ),
        "04_govern_and_prove": "Lab 4: Build Governed Agent Actions with Cedar",
    }
    for key, claims in receipt["labs"].items():
        add(f"## {titles.get(key, key)}")
        add("")
        for claim, state in claims.items():
            if claim == "detail" or not isinstance(state, str):
                continue
            add(f"- {claim.replace('_', ' ')}: **{_fmt(state)}**")
        detail = claims.get("detail")
        if isinstance(detail, dict):
            keys = [
                k
                for k in ("audit_id", "receipt_id", "turn_id", "credit_id", "idempotency_key")
                if detail.get(k)
            ]
            if keys:
                add("")
                add("  " + ", ".join(f"`{k}={detail[k]}`" for k in keys))
        add("")

    add("## Not yet proven")
    add("")
    if receipt["unproven"]:
        for item in receipt["unproven"]:
            add(f"- {item}")
        add("")
        add(
            "> `UNCHECKED` means the query could not run, not that the step "
            "failed. `CONTRADICTED` is neither: the search ran and found "
            "evidence against the claim. Three different findings."
        )
    else:
        add("- Nothing. Every boundary above is backed by a durable row.")
    add("")
    return "\n".join(lines)


def _write_outputs(args: argparse.Namespace, receipt: Dict[str, Any], markdown: str) -> None:
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8"
        )
    if args.md_out:
        pathlib.Path(args.md_out).write_text(markdown, encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(markdown)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 unless every lab's evidence contract is proved",
    )
    parser.add_argument("--env", default=str(DEFAULT_ENV), help="backend .env path")
    parser.add_argument("--json", dest="json_out", default="", help="write JSON here")
    parser.add_argument(
        "--markdown", dest="md_out", default="", help="write Markdown here"
    )
    args = parser.parse_args(argv)

    evidence = read_evidence(pathlib.Path(args.env))
    receipt = assemble(evidence)
    _write_outputs(args, receipt, render_markdown(receipt))

    if not evidence.get("available"):
        # Only an unreadable evidence source is an error, because then the
        # receipt cannot speak to the run at all.
        return 1
    if args.strict and not receipt["complete"]:
        print(f"STRICT: {len(receipt['unproven'])} claim(s) not proved:", file=sys.stderr)
        for item in receipt["unproven"]:
            print(f"  {item}", file=sys.stderr)
        return 1
    # Default mode exits 0 even when boundaries are unproven: an incomplete run
    # is a true report, not a tool failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
