"""Put one lab back to its as-shipped start, without touching the other labs.

``uv run scripts/lab_run.py reset --lab N`` calls :func:`reset_lab`. A lab's start has
four parts, and each is restored by the one source that defines it:

    files         the lab's marked regions and worksheets, from ``workshop/starters/``
                  through ``reset_participant_exercises`` (the same table the whole
                  reset uses, filtered to the lab)
    database      Lab 2's ``pellier.check_stock``, Lab 3's two owner policies, Lab 4's
                  credit-writer privileges: the statements between the ``SHIPPED STATE``
                  markers in ``scripts/migrations/001_schema.sql``, the file a fresh
                  database is built from, so there is no second copy to drift
    managed       the execution rail (Labs 1 and 2), the Lab 3 deploy and the Lab 4 Cedar
                  rule and enforcement mode: ``scripts/reset-agentcore-lab.sh``, which runs
                  the functions the whole reset runs
    evidence      ``tool_audit`` and ``retrieval_receipts`` are append-only, so the lab's
                  checks are told to ignore evidence older than a reset point instead
                  (see ``workshop_check.reset_point``)

Lab 4 cannot be reset once a credit has been written: a credit, its approved review and
its ``tool_audit`` row are the evidence the lab produces, and undoing them would be
rewriting a ledger. The command refuses before it changes anything and points to the
whole-workshop reset.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import reset_participant_exercises as exercises  # noqa: E402  (sibling module)
import workshop_check as check  # noqa: E402  (sibling module)

REPO = check.REPO
SCHEMA = pathlib.Path("scripts") / "migrations" / "001_schema.sql"
FULL_RESET = "bash scripts/reset-governed-workshop.sh"
AGENTCORE_SCRIPT = pathlib.Path("scripts") / "reset-agentcore-lab.sh"
AGENTCORE_TIMEOUT_SECONDS = 1500
SERVICE = "pellier"

# The part of the schema each lab's database piece is read from.
SHIPPED_BLOCKS = {2: "Lab 2 check_stock", 3: "Lab 3 row ownership", 4: "Lab 4 credit writer"}

# What a lab's database piece must remove before the shipped statements run. Lab 2's
# CREATE OR REPLACE keeps the function's comment, so the stamp is cleared; Lab 3's policies
# are dropped so the shipped policies are created on a clean name (a new policy has no stamp);
# Lab 4's worksheet grants and policies are revoked and dropped, then the shipped
# statements grant the function alone.
_CREDIT_FUNCTION = "pellier.apply_store_credit(text, text, integer, text, text)"
CLEAN_BEFORE = {
    2: "COMMENT ON FUNCTION pellier.check_stock(text) IS NULL;",
    3: ("DROP POLICY IF EXISTS orders_owner ON pellier.orders;\n"
        "DROP POLICY IF EXISTS support_tickets_owner ON pellier.support_tickets;"),
    4: f"""DO $revoke_writer$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT c.oid::regclass AS rel, c.relkind FROM pg_class c
              WHERE c.relnamespace = 'pellier'::regnamespace AND c.relkind IN ('r', 'p', 'v', 'S')
                AND (EXISTS (SELECT 1 FROM aclexplode(c.relacl) e
                              WHERE e.grantee = 'pellier_credit_writer'::regrole)
                     OR EXISTS (SELECT 1 FROM pg_attribute a, aclexplode(a.attacl) e
                                 WHERE a.attrelid = c.oid
                                   AND e.grantee = 'pellier_credit_writer'::regrole))
    LOOP
        EXECUTE format('REVOKE ALL ON %s %s FROM pellier_credit_writer',
                       CASE r.relkind WHEN 'S' THEN 'SEQUENCE' ELSE 'TABLE' END, r.rel);
    END LOOP;
    FOR r IN SELECT p.oid::regprocedure AS fn FROM pg_proc p
              WHERE p.pronamespace = 'pellier'::regnamespace
                AND EXISTS (SELECT 1 FROM aclexplode(p.proacl) e
                             WHERE e.grantee = 'pellier_credit_writer'::regrole)
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM pellier_credit_writer', r.fn);
    END LOOP;
    FOR r IN SELECT policyname, tablename FROM pg_policies
              WHERE schemaname = 'pellier' AND 'pellier_credit_writer' = ANY (roles)
    LOOP
        EXECUTE format('DROP POLICY %I ON pellier.%I', r.policyname, r.tablename);
    END LOOP;
END
$revoke_writer$;
ALTER FUNCTION {_CREDIT_FUNCTION} SECURITY INVOKER RESET ALL;
COMMENT ON FUNCTION {_CREDIT_FUNCTION} IS NULL;""",
}

# Labs whose Python or deployed package changed need the backend started again.
RESTARTS_BACKEND = frozenset({1, 2, 3})

LAB_DIRECTORY = {1: "01-retrieve", 2: "02-ground", 3: "03-deploy", 4: "04-govern"}
START_TASK = {1: "1A", 2: "2A", 3: "3A", 4: "4A"}
NOT_RESET = {
    1: "retrieval_receipts rows from earlier searches stay (append-only); Lab 1's check ignores "
       "them now.",
    2: "tool_audit rows from earlier turns stay (append-only); Lab 2's checks ignore them now.",
    3: "tool_audit rows from earlier turns stay (append-only) and Lab 3's checks ignore them "
       "now. AgentCore Memory is not touched; the whole-workshop reset cleans it.",
    4: "nothing the lab wrote can remain: the command refuses while a credit exists.",
}


class LabResetError(Exception):
    """The reset could not complete. The message says what happened and what to do next."""


@dataclass
class Step:
    """One restored part, as the command prints it."""

    label: str
    seconds: float


def shipped_sql(lab: int, repo: pathlib.Path = REPO) -> str:
    """The statements a fresh database installs for this lab, read from the schema.

    Raises:
        LabResetError: the lab has no database piece or its markers are damaged.
    """
    if lab not in SHIPPED_BLOCKS:
        raise LabResetError(f"Lab {lab} has no database piece")
    name = re.escape(SHIPPED_BLOCKS[lab])
    pattern = re.compile(
        rf"^-- === SHIPPED STATE - {name}: START ===\n(.*?)^-- === SHIPPED STATE - {name}: END ===$",
        re.DOTALL | re.MULTILINE,
    )
    text = (repo / SCHEMA).read_text(encoding="utf-8")
    found = pattern.findall(text)
    if len(found) != 1 or not found[0].strip():
        raise LabResetError(f"{SCHEMA} must hold exactly one 'SHIPPED STATE - "
                            f"{SHIPPED_BLOCKS[lab]}' block; repair the files with "
                            "uv run scripts/repair_workshop_files.py")
    return found[0].strip()


def database_sql(lab: int, repo: pathlib.Path = REPO) -> Optional[str]:
    """The one transaction that puts the lab's database piece back, or None for Lab 1."""
    if lab not in SHIPPED_BLOCKS:
        return None
    return f"{CLEAN_BEFORE[lab]}\n{shipped_sql(lab, repo)}\n"


def credit_blocker(conn: Any) -> Optional[str]:
    """Why Lab 4 cannot be reset: the credit that exists, else None."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pellier.store_credits")
        credits = int(cur.fetchone()["n"])
    if credits == 0:
        return None
    return (f"{credits} store credit(s) exist. A credit, the review a person approved and its "
            "tool_audit row are the evidence this lab produces, and none of them can be "
            "undone from a lab. Nothing was changed. To start Lab 4 over from a clean ledger "
            f"reset the whole workshop: {FULL_RESET}")


def apply_database(conn: Any, lab: int, repo: pathlib.Path = REPO) -> datetime:
    """Run the lab's database piece in one transaction; return the database's clock after it."""
    sql = database_sql(lab, repo)
    try:
        with conn.cursor() as cur:
            if sql is not None:
                cur.execute(sql)
            conn.commit()
            cur.execute("SELECT clock_timestamp() AS now")
            return cur.fetchone()["now"]
    except Exception as exc:  # noqa: BLE001 - a psycopg error rolls the transaction back
        conn.rollback()
        raise LabResetError(f"the database piece of Lab {lab} was not restored ({exc}). "
                            f"Nothing in the database changed. Run the whole-workshop reset: "
                            f"{FULL_RESET}") from exc


def restart_backend() -> str:
    """Restart the pellier service; return what happened in a few words."""
    if shutil.which("systemctl") is None:
        return "no systemd here"
    listed = subprocess.run(["systemctl", "list-unit-files", f"{SERVICE}.service"],
                            capture_output=True, text=True, check=False)
    if f"{SERVICE}.service" not in listed.stdout:
        return f"no {SERVICE} service here"
    command = ["systemctl", "restart", SERVICE]
    if os.geteuid() != 0:
        command = ["sudo", "-n", *command]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise LabResetError(f"could not restart the backend ({result.stderr.strip()}). Run: "
                            f"sudo systemctl restart {SERVICE}")
    return "restarted"


def run_agentcore_step(lab: int, repo: pathlib.Path = REPO) -> None:
    """Run the managed part of the reset, streaming its [PASS] lines."""
    script = repo / AGENTCORE_SCRIPT
    if not script.is_file():
        raise LabResetError(f"{AGENTCORE_SCRIPT} is missing. Repair the files with "
                            "uv run scripts/repair_workshop_files.py")
    try:
        result = subprocess.run(["bash", str(script), str(lab)], cwd=repo,
                                timeout=AGENTCORE_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise LabResetError(f"the managed reset ran longer than "
                            f"{AGENTCORE_TIMEOUT_SECONDS // 60} minutes") from exc
    if result.returncode != 0:
        raise LabResetError(f"Lab {lab}'s managed state was not restored. Nothing else is "
                            f"half done. To start clean, run the whole-workshop reset: "
                            f"{FULL_RESET}")


def _timed(steps: List[Step], label: str, started: float) -> None:
    steps.append(Step(label, time.monotonic() - started))


def reset_lab(
    lab: int,
    *,
    repo: pathlib.Path = REPO,
    connect: Optional[Callable[[], Any]] = None,
    report: Callable[[str], None] = print,
    wait_healthy: Optional[Callable[[], None]] = None,
    managed: Callable[[int], None] = run_agentcore_step,
    restart: Callable[[], str] = restart_backend,
) -> List[Step]:
    """Reset one lab, in order, and print what was restored.

    Args:
        lab: 1 to 4.
        repo: The repository root.
        connect: Opens a database connection; defaults to the box's settings.
        report: Prints one line of progress.
        wait_healthy: Called after the backend restarts; waits for /api/health.
        managed: Restores execution and AgentCore state for the lab.
        restart: Restarts the backend and says what happened.

    Returns:
        The steps taken, with how long each took.

    Raises:
        LabResetError: the reset was refused or a step failed.
    """
    began = time.monotonic()
    steps: List[Step] = []
    conn = _open(connect)
    try:
        if lab == 4:
            blocked = credit_blocker(conn)
            if blocked:
                raise LabResetError(blocked)
        started = time.monotonic()
        restored = exercises.restore_lab(repo, lab)
        _timed(steps, f"files: {', '.join(restored)}", started)
        report(f"  + OK    restored {len(restored)} file region(s) to their starters "
               f"({', '.join(restored)})")

        started = time.monotonic()
        point = apply_database(conn, lab, repo)
        if lab in SHIPPED_BLOCKS:
            _timed(steps, f"database: {SHIPPED_BLOCKS[lab]}", started)
            report(f"  + OK    reinstalled the shipped database piece ({SHIPPED_BLOCKS[lab]}, "
                   f"from {SCHEMA})")
        check.record_reset_point(lab, point)
        report(f"  + OK    reset point {point.astimezone(timezone.utc):%H:%M:%S} UTC: Lab "
               f"{lab}'s checks ignore earlier turns")
    finally:
        conn.close()

    started = time.monotonic()
    managed(lab)
    _timed(steps, "managed state", started)
    report("  + OK    restored the lab's execution and AgentCore state")

    if lab in RESTARTS_BACKEND:
        started = time.monotonic()
        outcome = restart()
        if outcome == "restarted" and wait_healthy is not None:
            wait_healthy()
        _timed(steps, f"backend: {outcome}", started)
        report(f"  + OK    backend {outcome}" if outcome == "restarted"
               else f"  - WAIT  backend not restarted ({outcome}); restart it yourself")
    report(f"  Not reset: {NOT_RESET[lab]}")
    report(f"  Took {time.monotonic() - began:.0f} s.")
    report("  Next: " + next_step(lab))
    return steps


def next_step(lab: int) -> str:
    """The page that starts the lab again. Lab 3 needs no switch first: its deploy moves
    Pellier onto AgentCore when it is not there yet."""
    return f"start Task {START_TASK[lab]} again from labs/{LAB_DIRECTORY[lab]}/README.md."


def _open(connect: Optional[Callable[[], Any]]) -> Any:
    if connect is not None:
        return connect()
    cfg: Optional[Dict[str, str]] = check.db_config()
    if cfg is None:
        raise LabResetError(check.missing_settings_reason() + ". Run this on the workshop box.")
    try:
        return check.connect(cfg)
    except Exception as exc:  # noqa: BLE001 - psycopg and socket errors, reported with the fix
        raise LabResetError(f"cannot reach the database ({exc}). Check the connection and "
                            "run the reset again.") from exc
