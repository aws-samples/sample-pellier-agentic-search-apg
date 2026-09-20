"""Read model for five independently observed Lab 4 outcomes.

No outcome is inferred from an HTTP success, a missing response, or an absent
database read. The CLI's protocol observations and keyed SQL snapshots are
bounded evidence, not provider decision logs. No live invocation happens here.
"""
from __future__ import annotations

import json

OUTCOMES = (
    "authentication_failed", "cedar_denied", "transaction_rejected",
    "committed", "output_suppressed",
)


def assess(observation: dict) -> dict:
    auth = observation.get("authentication", "UNKNOWN")
    policy = observation.get("authorization", "UNKNOWN")
    output = observation.get("output", "UNKNOWN")
    evidence = observation.get("database") or {}
    queried = evidence.get("queried") is True
    counts = [evidence.get(k) for k in ("executionRows", "writeRows", "committedRows", "domainRows", "ledgerRows")]
    measured = queried and all(type(v) is int and v >= 0 for v in counts)
    pending = evidence.get("pendingClaimRows", 0)
    pending_matches = type(pending) is int and pending in (0, 1) and measured and pending == counts[1]
    executed = (counts[0] > 0) if measured else None
    changed = None
    if measured:
        if counts[2] > 0 and counts[3] > 0:
            changed = True
        elif not any(counts[1:]) or (pending_matches and not any(counts[2:])):
            changed = False
    outcome = "inconclusive"
    contradiction = None
    if measured:
        executions, writes, commits, domain, ledger = counts
        if output == "SUPPRESSED" and observation.get("canaryReturned") is True:
            contradiction = "Suppression was reported, but the synthetic email reached the caller."
        elif auth == "REJECTED" or policy == "DENY":
            if any(counts):
                contradiction = "A pre-execution rejection has keyed execution or data-change evidence."
            elif auth == "REJECTED" and policy == "NOT_EVALUATED":
                outcome = "authentication_failed"
            elif auth == "VERIFIED" and policy == "DENY":
                outcome = "cedar_denied"
        elif auth == "VERIFIED" and policy == "ALLOW" and executions > 0:
            if commits != domain or commits > 1 or writes > 1:
                contradiction = "The finalized operation and domain row do not establish one matching effect."
            elif output == "SUPPRESSED":
                # Suppression never derives a write verdict. This workshop
                # checkpoint specifically proves a committed credit survives.
                if commits == domain == writes == 1:
                    outcome = "output_suppressed"
            elif commits == domain == writes == 1 and output == "RETURNED":
                outcome = "committed"
            elif (not (commits or domain or ledger) and pending_matches
                  and observation.get("businessRejected") is True):
                outcome = "transaction_rejected"
    return {
        "outcome": outcome, "control": {
            "authentication_failed": "Authentication", "cedar_denied": "Cedar",
            "transaction_rejected": "Business transaction", "committed": "Aurora commit",
            "output_suppressed": "Managed output Guardrail", "inconclusive": "Not established",
        }[outcome],
        "toolExecuted": executed, "dataChanged": changed,
        "authentication": auth, "authorization": policy, "output": output,
        "database": evidence, "contradiction": contradiction,
    }


def summarize(rows: list[dict]) -> dict:
    runs = {}
    for row in rows:
        run_id = row["proofRunId"]
        run = runs.setdefault(run_id, {"runId": run_id, "observedAt": row["createdAt"], "attempts": []})
        observation = row["observation"]
        if isinstance(observation, str):
            observation = json.loads(observation)
        if row["caseName"] == "run-checks":
            run["checks"] = observation.get("runChecks", {})
            continue
        assessed = assess(observation)
        run["attempts"].append({
            "id": row["observationId"], "case": row["caseName"],
            "operationKey": row["operationKey"], "invocationId": row["invocationId"],
            "tool": row["tool"], "principal": row.get("verifiedUsername"),
            "observedAt": row["createdAt"], **assessed,
        })
    for run in runs.values():
        observed = {r["outcome"] for r in run["attempts"]}
        run["outcomes"] = {name: name in observed for name in OUTCOMES}
        # Every attempted control must hold, including benign and replay controls.
        checks = run.get("checks", {})
        run["complete"] = all(checks.get(k) is True for k in (
            "identityProofPassed", "configurationUnchanged", "outputControlsPassed",
        )) and all(run["outcomes"].values()) and all(
            a["outcome"] != "inconclusive" and not a["contradiction"] for a in run["attempts"]
        )
    return {"runs": list(runs.values()), "source": "CLI observations + keyed Aurora snapshots"}
