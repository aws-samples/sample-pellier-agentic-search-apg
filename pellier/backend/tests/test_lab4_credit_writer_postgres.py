"""Lab 4B on real PostgreSQL: the money role's privileges, starter and solution.

The starter grants what a team writes to make an invoker's-rights credit
function work: table privileges and a row policy. The credit still writes once
and replays, and only the privilege probes fail: the trigger, not a missing
privilege, refuses the direct insert (23514), and a direct UPDATE raises an
approved amount with no check. The solution leaves the role EXECUTE on a
definer's-rights function and nothing else, so both are 42501. A failing run
rolls back and changes nothing; a passing run commits the privileges and the
stamp, never the probe credit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
LIVE = REPO / "workshop" / "lab-4-credit-writer.sql"
STARTER = REPO / "workshop" / "starters" / "lab-4-credit-writer.sql"
SOLUTION = REPO / "solutions" / "the-concierge" / "sql" / "lab-4-credit-writer-solution.sql"
LABEL = "Credit writer - privileges"


def _run(cluster: Any, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-P", "pager=off", "-f", str(path)],
        capture_output=True, text=True, timeout=60,
    )


def _probes(stdout: str) -> Dict[str, List[str]]:
    rows = [[cell.strip() for cell in line.split("|")] for line in stdout.splitlines()
            if line.count("|") == 4 and not line.lstrip().startswith("probe")]
    return {row[0]: row[1:] for row in rows}


def _state(cluster: Any) -> str:
    return cluster.psql(
        "SELECT (SELECT count(*) FROM pellier.store_credits) || ' ' || prosecdef || ' ' "
        "|| coalesce(array_to_string(proconfig, ','), '') || ' ' "
        "|| coalesce(obj_description(oid, 'pg_proc'), 'no stamp') "
        "FROM pg_proc WHERE proname = 'apply_store_credit'")


def test_the_live_worksheet_ships_the_starter() -> None:
    assert LIVE.read_text(encoding="utf-8") == STARTER.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [STARTER, SOLUTION])
def test_the_solution_differs_from_the_starter_only_inside_the_region(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(f"WORKSHOP - {LABEL}: START ===") == 1
    head, rest = text.split(f"WORKSHOP - {LABEL}: START ===")
    starter_head, starter_rest = STARTER.read_text(encoding="utf-8").split(
        f"WORKSHOP - {LABEL}: START ===")
    assert head == starter_head
    assert rest.split(f"WORKSHOP - {LABEL}: END ===")[1] == starter_rest.split(
        f"WORKSHOP - {LABEL}: END ===")[1]


def test_the_starter_writes_the_credit_and_fails_only_the_privilege_probes(fresh_db) -> None:  # noqa: F811
    before = _state(fresh_db)
    done = _run(fresh_db, STARTER)
    assert done.returncode != 0
    probes = _probes(done.stdout)
    assert probes["Insert a credit row directly"][1:3] == [
        "23514", "store_credits_require_approval, a rule the owner can switch off"]
    assert probes["Raise the approved credit to $500 directly"][1] == "00000"
    assert "1 row updated" in probes["Raise the approved credit to $500 directly"][2]
    for kept in ("The approved key with a different amount", "The approved amount under another key",
                 "The approved credit, then its retry", "Who may execute the function"):
        assert probes[kept][-1] == "matches", (kept, probes[kept])
    differs = sorted(name for name, row in probes.items() if row[-1] == "differs")
    assert differs == sorted([
        "Insert a credit row directly", "Raise the approved credit to $500 directly",
        "The function's rights",
        "The role's privileges and row policies on store_credits, orders, approvals"])
    assert probes["The role's privileges and row policies on store_credits, orders, approvals"][1]\
        .endswith("; policy orders_credit_writer on orders USING (true): every customer's rows")
    assert "rolled back, the live state is unchanged" in done.stdout
    assert "Lab 4B privileges check failed" in done.stdout
    assert _state(fresh_db) == before


def test_the_solution_passes_every_probe_and_commits_only_the_privileges(fresh_db) -> None:  # noqa: F811
    credits_before = fresh_db.psql("SELECT count(*) FROM pellier.store_credits")
    done = _run(fresh_db, SOLUTION)
    assert done.returncode == 0, done.stdout + done.stderr
    probes = _probes(done.stdout)
    assert len(probes) == 8 and all(row[-1] == "matches" for row in probes.values()), probes
    assert probes["Insert a credit row directly"][1:3] == [
        "42501", "no INSERT privilege on pellier.store_credits"]
    assert probes["Raise the approved credit to $500 directly"][1:3] == [
        "42501", "no UPDATE privilege on pellier.store_credits"]
    assert "Lab 4B privileges check passed" in done.stdout
    assert fresh_db.psql("SELECT count(*) FROM pellier.store_credits") == credits_before
    assert fresh_db.psql("SELECT obj_description('pellier.apply_store_credit(text, text, integer, "
                         "text, text)'::regprocedure, 'pg_proc')").startswith(
                             "Lab 4B privileges sha256 ")
    assert fresh_db.psql("SELECT count(*) FROM information_schema.role_table_grants "
                         "WHERE grantee = 'pellier_credit_writer'") == "0"
