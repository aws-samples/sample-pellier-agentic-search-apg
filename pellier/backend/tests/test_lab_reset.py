"""``lab_run.py reset --lab N`` puts one lab back as shipped and leaves the others alone.

The unit tests use a temporary copy of the files a reset touches and fakes for the database,
AgentCore and systemd. The Postgres-backed tests run the real statements on a throwaway
cluster built from the migrations and prove the contract that matters: after a participant's
finished answer is applied, a lab reset leaves the catalog exactly as a fresh database has it.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.fresh_cluster import Cluster, fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab_reset = importlib.import_module("lab_reset")
exercises = importlib.import_module("reset_participant_exercises")
check = importlib.import_module("workshop_check")
lab_run = importlib.import_module("lab_run")
lab1_retry = importlib.import_module("lab1_retry")
lab2_check = importlib.import_module("lab2_check")
lab3_check = importlib.import_module("lab3_check")

WORKSPACE = REPO / "Pellier.code-workspace"
SCHEMA = REPO / "scripts" / "migrations" / "001_schema.sql"
SOLUTIONS = {entry["source"]: REPO / entry["solution"] for entry in json.loads(
    (REPO / "workshop" / "participant-files.json").read_text("utf-8"))}


@pytest.fixture(autouse=True)
def reset_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "points" / "lab-reset-points.json"
    monkeypatch.setenv(check.RESET_POINTS_ENV, str(path))
    return path


def all_exercises() -> List[Any]:
    return [*exercises.MARKER_EXERCISES, *exercises.FILE_EXERCISES]


def make_repo(tmp_path: Path) -> Path:
    """The files a reset reads and writes, copied from this checkout (all as shipped)."""
    repo = tmp_path / "repo"
    for exercise in all_exercises():
        for relative in (exercise.starter, exercise.destination):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
    schema = repo / lab_reset.SCHEMA
    schema.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SCHEMA, schema)
    return repo


def edit(repo: Path, exercise: Any) -> None:
    """Change a participant region or worksheet the way a participant would."""
    path = repo / exercise.destination
    if isinstance(exercise, exercises.MarkerExercise):
        text = path.read_text(encoding="utf-8")
        _start, body_start, _end, _line_end = exercises._marker_bounds(text, exercise.marker)
        path.write_text(text[:body_start] + "# participant edit\n" + text[body_start:],
                        encoding="utf-8")
    else:
        path.write_text(path.read_text(encoding="utf-8") + "-- participant edit\n",
                        encoding="utf-8")


# ---------------------------------------------------------------------------
# The lab filter
# ---------------------------------------------------------------------------


def test_every_exercise_belongs_to_a_lab_named_in_its_id() -> None:
    for exercise in all_exercises():
        assert exercise.exercise_id.startswith(f"lab-{exercise.lab}-"), exercise.exercise_id


def test_every_lab_has_something_to_restore() -> None:
    for lab in (1, 2, 3, 4):
        markers, files = exercises.exercises_for(lab)
        assert markers or files, lab


@pytest.mark.parametrize("lab", [1, 2, 3, 4])
def test_restoring_one_lab_leaves_the_other_labs_edits(tmp_path: Path, lab: int) -> None:
    repo = make_repo(tmp_path)
    for exercise in all_exercises():
        edit(repo, exercise)

    restored = exercises.restore_lab(repo, lab)

    assert sorted(restored) == sorted(e.exercise_id for e in all_exercises() if e.lab == lab)
    assert exercises._check(repo, lab) == []
    for other in {1, 2, 3, 4} - {lab}:
        assert sorted(exercises._check(repo, other)) == sorted(
            e.exercise_id for e in all_exercises() if e.lab == other), other


def test_restoring_every_lab_still_works(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for exercise in all_exercises():
        edit(repo, exercise)

    assert len(exercises.restore_lab(repo)) == len(all_exercises())
    assert exercises._check(repo) == []


def test_an_unknown_lab_is_refused() -> None:
    with pytest.raises(ValueError, match="Lab 9"):
        exercises.exercises_for(9)


def test_the_command_line_takes_a_lab(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    edit(repo, next(e for e in all_exercises() if e.lab == 2))
    edit(repo, next(e for e in all_exercises() if e.lab == 3))
    done = subprocess.run([sys.executable, str(REPO / "scripts" / "reset_participant_exercises.py"),
                           "--repo", str(repo), "--lab", "2"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert exercises._check(repo, 2) == []
    assert exercises._check(repo, 3) != []


# ---------------------------------------------------------------------------
# The database pieces come from the migration
# ---------------------------------------------------------------------------


def test_the_database_pieces_are_read_from_the_schema_markers() -> None:
    text = SCHEMA.read_text(encoding="utf-8")
    for lab in (2, 3, 4):
        piece = lab_reset.shipped_sql(lab)
        assert piece in text
        assert text.count(piece) == 1
    assert "CREATE OR REPLACE FUNCTION pellier.check_stock(" in lab_reset.shipped_sql(2)
    assert lab_reset.shipped_sql(3).count("CREATE POLICY") == 2
    assert "SECURITY DEFINER" in lab_reset.shipped_sql(4)
    assert "GRANT EXECUTE ON FUNCTION" in lab_reset.shipped_sql(4)


def test_lab_one_has_no_database_piece() -> None:
    assert lab_reset.database_sql(1) is None


def test_the_command_holds_no_copy_of_what_the_schema_ships() -> None:
    source = (REPO / "scripts" / "lab_reset.py").read_text(encoding="utf-8")
    for statement in ("CREATE POLICY", "CREATE OR REPLACE FUNCTION", "GRANT EXECUTE",
                      "SECURITY DEFINER", "GRANT USAGE", "search_path"):
        assert statement not in source, statement


def test_damaged_markers_are_refused_with_the_repair_command(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    schema = repo / lab_reset.SCHEMA
    schema.write_text(schema.read_text().replace("SHIPPED STATE - Lab 3 row ownership: END", "x"))
    with pytest.raises(lab_reset.LabResetError, match="repair_workshop_files"):
        lab_reset.shipped_sql(3, repo)


def test_the_stamps_each_worksheet_leaves_are_cleared() -> None:
    assert "COMMENT ON FUNCTION pellier.check_stock(text) IS NULL" in lab_reset.CLEAN_BEFORE[2]
    assert "COMMENT ON FUNCTION pellier.apply_store_credit" in lab_reset.CLEAN_BEFORE[4]
    assert "DROP POLICY IF EXISTS orders_owner" in lab_reset.CLEAN_BEFORE[3]
    assert "DROP POLICY IF EXISTS support_tickets_owner" in lab_reset.CLEAN_BEFORE[3]


# ---------------------------------------------------------------------------
# Lab 4 refuses once a credit exists
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self.row: Dict[str, Any] = {}

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.conn.statements.append(sql)
        if "store_credits" in sql:
            self.row = {"n": self.conn.credits}
        else:
            self.row = {"now": self.conn.clock}

    def fetchone(self) -> Dict[str, Any]:
        return self.row


class FakeConnection:
    def __init__(self, credits: int = 0) -> None:
        self.credits = credits
        self.clock = datetime(2026, 10, 15, 12, 0, 5, tzinfo=timezone.utc)
        self.statements: List[str] = []
        self.commits = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def run_reset(lab: int, repo: Path, conn: FakeConnection, events: List[str]) -> List[str]:
    lines: List[str] = []
    lab_reset.reset_lab(
        lab, repo=repo, connect=lambda: conn, report=lines.append,
        wait_healthy=lambda: events.append("healthy"),
        managed=lambda number: events.append(f"managed {number}"),
        restart=lambda: events.append("restart") or "restarted",
    )
    return lines


def test_lab_four_refuses_after_a_credit_and_changes_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for exercise in all_exercises():
        edit(repo, exercise)
    conn = FakeConnection(credits=1)
    events: List[str] = []

    with pytest.raises(lab_reset.LabResetError) as refused:
        run_reset(4, repo, conn, events)

    assert "reset the whole workshop" in str(refused.value)
    assert "bash scripts/reset-governed-workshop.sh" in str(refused.value)
    assert exercises._check(repo, 4) != []
    assert events == []
    assert all("apply_store_credit" not in s for s in conn.statements)
    assert check.reset_point(4) is None
    assert conn.closed


def test_lab_four_resets_while_no_credit_exists(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for exercise in all_exercises():
        edit(repo, exercise)

    run_reset(4, repo, FakeConnection(credits=0), [])

    assert exercises._check(repo, 4) == []
    assert exercises._check(repo, 3) != []


# ---------------------------------------------------------------------------
# The order of a reset, and what each lab restarts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("lab", "restarts"), [(1, True), (2, True), (3, True), (4, False)])
def test_a_reset_restores_files_then_database_then_managed_state_then_the_backend(
    tmp_path: Path, lab: int, restarts: bool,
) -> None:
    repo = make_repo(tmp_path)
    for exercise in all_exercises():
        edit(repo, exercise)
    conn = FakeConnection()
    events: List[str] = []

    lines = run_reset(lab, repo, conn, events)

    assert events == [f"managed {lab}", *(["restart", "healthy"] if restarts else [])]
    assert conn.commits == 1 and conn.closed
    sql = "\n".join(conn.statements)
    assert ("pellier.check_stock" in sql) is (lab == 2)
    assert ("CREATE POLICY orders_owner" in sql) is (lab == 3)
    assert ("apply_store_credit" in sql) is (lab == 4)
    joined = "\n".join(lines)
    assert "reset point 12:00:05 UTC" in joined
    assert "Took" in joined and "Next:" in joined and "Not reset:" in joined
    assert check.reset_point(lab) == conn.clock
    for other in {1, 2, 3, 4} - {lab}:
        assert check.reset_point(other) is None


def test_a_backend_that_cannot_be_restarted_is_reported_not_waited_for(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lines: List[str] = []
    waited: List[str] = []
    lab_reset.reset_lab(1, repo=repo, connect=lambda: FakeConnection(), report=lines.append,
                        wait_healthy=lambda: waited.append("healthy"),
                        managed=lambda number: None, restart=lambda: "no systemd here")
    assert waited == []
    assert any("restart it yourself" in line for line in lines)


def test_lab_three_starts_again_at_task_3a_because_its_deploy_moves_the_rail() -> None:
    assert lab_reset.next_step(3) == "start Task 3A again from labs/03-deploy/README.md."
    assert "lab3-start" not in lab_reset.next_step(3)
    assert "Task 1A" in lab_reset.next_step(1)


def test_the_command_is_wired_into_lab_run(monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    seen: List[int] = []
    monkeypatch.setattr(lab_reset, "reset_lab", lambda lab, **_kw: seen.append(lab))
    assert lab_run.main(["reset", "--lab", "2"]) == 0
    assert seen == [2]
    assert "start over" in capsys.readouterr().out


def test_a_refused_reset_exits_one_with_the_reason(monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    def refuse(lab: int, **_kw: Any) -> None:
        raise lab_reset.LabResetError("1 store credit(s) exist")

    monkeypatch.setattr(lab_reset, "reset_lab", refuse)
    assert lab_run.main(["reset", "--lab", "4"]) == 1
    assert "store credit(s) exist" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Reset points
# ---------------------------------------------------------------------------


def test_reset_points_round_trip_per_lab(reset_points: Path) -> None:
    moment = datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)
    assert check.reset_point(2) is None
    check.record_reset_point(2, moment)
    check.record_reset_point(3, moment + timedelta(minutes=1))
    assert check.reset_point(2) == moment
    assert check.reset_point(3) == moment + timedelta(minutes=1)
    assert check.reset_point(1) is None
    check.clear_reset_points()
    assert check.reset_point(2) is None


def test_a_damaged_points_file_means_no_reset_point(reset_points: Path) -> None:
    reset_points.parent.mkdir(parents=True)
    reset_points.write_text("not json")
    assert check.reset_point(2) is None


def test_the_note_names_the_reset_and_says_to_send_again(reset_points: Path) -> None:
    assert check.since_note(2, "python3 scripts/lab_run.py send --lab 2") == ""
    check.record_reset_point(2, datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc))
    note = check.since_note(2, "python3 scripts/lab_run.py send --lab 2")
    assert "send the requests again since your reset" in note
    assert "09:30:00 UTC" in note


def test_the_full_reset_clears_the_points_after_it_empties_the_tables() -> None:
    body = (REPO / "scripts" / "reset-governed-workshop.sh").read_text()
    assert body.index("database-reset.sh") < body.index("lab-reset-points.json")


# ---------------------------------------------------------------------------
# Code Editor tasks
# ---------------------------------------------------------------------------

TASK_COMMANDS = {
    "Reset Lab 1": "python3 scripts/lab_run.py reset --lab 1",
    "Reset Lab 2": "python3 scripts/lab_run.py reset --lab 2",
    "Reset Lab 3": "python3 scripts/lab_run.py reset --lab 3",
    "Reset Lab 4": "python3 scripts/lab_run.py reset --lab 4",
    "Reset the whole workshop": "bash scripts/reset-governed-workshop.sh",
    "Repair workshop files": "python3 scripts/repair_workshop_files.py",
}


def workspace_tasks() -> Dict[str, Any]:
    return json.loads(WORKSPACE.read_text(encoding="utf-8"))["tasks"]


def test_the_workspace_has_a_task_for_each_reset() -> None:
    labels = {task["label"]: task for task in workspace_tasks()["tasks"]}
    assert set(labels) == set(TASK_COMMANDS)
    for label, command in TASK_COMMANDS.items():
        assert command in labels[label]["command"], label


def test_each_task_is_guarded_by_a_confirmation_that_defaults_to_cancel() -> None:
    tasks = workspace_tasks()
    inputs = {item["id"]: item for item in tasks["inputs"]}
    for task in tasks["tasks"]:
        referenced = [name for name in inputs if "${input:" + name + "}" in task["command"]]
        assert len(referenced) == 1, task["label"]
        picker = inputs[referenced[0]]
        assert picker["type"] == "pickString"
        assert picker["default"] == "Cancel"
        assert picker["options"][0] == "Cancel" and len(picker["options"]) == 2
        yes = picker["options"][1]
        assert f"= '{yes}'" in task["command"], task["label"]
        assert "Nothing was changed" in task["command"]
        reset_at = task["command"].index(TASK_COMMANDS[task["label"]])
        assert task["command"].index("then") < reset_at < task["command"].index("else")


def test_every_confirmation_is_used_by_exactly_one_task() -> None:
    tasks = workspace_tasks()
    used = [name["id"] for name in tasks["inputs"]
            if sum("${input:" + name["id"] + "}" in t["command"] for t in tasks["tasks"]) == 1]
    assert len(used) == len(tasks["inputs"]) == len(tasks["tasks"])


def test_the_tasks_run_in_a_dedicated_visible_panel_from_the_repository_root() -> None:
    for task in workspace_tasks()["tasks"]:
        presentation = task["presentation"]
        assert presentation["panel"] == "dedicated"
        assert presentation["reveal"] == "always"
        assert task["options"]["cwd"] == "${workspaceFolder:05 - Explore Pellier source}"


def test_no_reset_task_runs_on_its_own() -> None:
    for task in workspace_tasks()["tasks"]:
        assert "runOptions" not in task, task["label"]
        assert task.get("isBackground") is not True
        assert "dependsOn" not in task


def test_every_workspace_folder_the_tasks_name_exists() -> None:
    names = {folder["name"] for folder in
             json.loads(WORKSPACE.read_text(encoding="utf-8"))["folders"]}
    for task in workspace_tasks()["tasks"]:
        assert task["options"]["cwd"][len("${workspaceFolder:"):-1] in names


# ---------------------------------------------------------------------------
# Postgres: the contract the reset exists to keep
# ---------------------------------------------------------------------------

# An ACL equal to the owner's default means the same as no ACL, and a REVOKE leaves the
# explicit form behind, so both are normalised to none before comparing.
SNAPSHOT_SQL = """
SELECT string_agg(x, E'\\n' ORDER BY x) FROM (
  SELECT 'fn ' || p.oid::regprocedure || ' ' || md5(p.prosrc) || ' ' || p.prosecdef || ' '
         || coalesce(p.proconfig::text, '') || ' '
         || coalesce((SELECT string_agg(a::text, ',' ORDER BY a::text) FROM unnest(CASE WHEN p.proacl = acldefault('f'::"char", p.proowner) THEN NULL ELSE p.proacl END) a), '')
         || ' ' || coalesce(obj_description(p.oid, 'pg_proc'), '') AS x
    FROM pg_proc p WHERE p.pronamespace = 'pellier'::regnamespace
  UNION ALL
  SELECT 'policy ' || polrelid::regclass || ' ' || polname || ' ' || polcmd::text || ' '
         || polroles::regrole[]::text || ' ' || coalesce(pg_get_expr(polqual, polrelid), '')
         || ' ' || coalesce(pg_get_expr(polwithcheck, polrelid), '') || ' '
         || coalesce(obj_description(oid, 'pg_policy'), '')
    FROM pg_policy
  UNION ALL
  SELECT 'rel ' || c.oid::regclass || ' ' || c.relrowsecurity || ' '
         || coalesce((SELECT string_agg(a::text, ',' ORDER BY a::text) FROM unnest(CASE WHEN c.relacl = acldefault((CASE c.relkind WHEN 'S' THEN 's' ELSE 'r' END)::"char", c.relowner) THEN NULL ELSE c.relacl END) a), '')
    FROM pg_class c WHERE c.relnamespace = 'pellier'::regnamespace AND c.relkind IN ('r', 'S')
  UNION ALL
  SELECT 'column ' || a.attrelid::regclass || '.' || a.attname || ' '
         || (SELECT string_agg(i::text, ',' ORDER BY i::text) FROM unnest(a.attacl) i)
    FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
   WHERE c.relnamespace = 'pellier'::regnamespace AND a.attacl IS NOT NULL
  UNION ALL
  SELECT 'schema ' || (SELECT string_agg(i::text, ',' ORDER BY i::text) FROM unnest(nspacl) i)
    FROM pg_namespace WHERE nspname = 'pellier'
) s
"""


def connect(cluster: Cluster) -> Any:
    return check.connect({"DB_HOST": str(cluster.socket), "DB_PORT": "5432", "DB_NAME": "postgres",
                          "DB_USER": "postgres", "DB_PASSWORD": ""})


def snapshot(cluster: Cluster) -> str:
    return cluster.psql(SNAPSHOT_SQL)


def apply_solution(cluster: Cluster, source: str) -> None:
    done = subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-f", str(SOLUTIONS[source])],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize(("lab", "source"), [
    (2, "workshop/lab-2-check-stock.sql"),
    (3, "workshop/lab-3-row-ownership.sql"),
    (4, "workshop/lab-4-credit-writer.sql"),
])
def test_a_reset_after_the_finished_answer_leaves_the_catalog_as_a_fresh_database_has_it(
    fresh_db: Cluster, lab: int, source: str,
) -> None:
    fresh = snapshot(fresh_db)
    apply_solution(fresh_db, source)
    assert snapshot(fresh_db) != fresh, "the answer changed nothing, so this proves nothing"

    conn = connect(fresh_db)
    try:
        lab_reset.apply_database(conn, lab)
    finally:
        conn.close()

    assert snapshot(fresh_db) == fresh


def test_a_reset_removes_the_wide_grants_and_policy_the_starter_region_holds(
    fresh_db: Cluster,
) -> None:
    """The starter's region is the widest thing a participant can leave on the money role."""
    starter = (REPO / "workshop" / "starters" / "lab-4-credit-writer.sql").read_text("utf-8")
    grants = starter.split("$privileges$")[1]
    fresh = snapshot(fresh_db)
    fresh_db.psql(grants)
    assert snapshot(fresh_db) != fresh
    assert "orders_credit_writer" in fresh_db.psql("SELECT policyname FROM pg_policies")

    conn = connect(fresh_db)
    try:
        lab_reset.apply_database(conn, 4)
    finally:
        conn.close()

    assert snapshot(fresh_db) == fresh


def test_resetting_one_lab_leaves_another_labs_finished_answer(fresh_db: Cluster) -> None:
    fresh = snapshot(fresh_db)
    apply_solution(fresh_db, "workshop/lab-3-row-ownership.sql")
    solved = snapshot(fresh_db)
    conn = connect(fresh_db)
    try:
        lab_reset.apply_database(conn, 2)
        lab_reset.apply_database(conn, 4)
    finally:
        conn.close()
    assert snapshot(fresh_db) == solved
    conn = connect(fresh_db)
    try:
        lab_reset.apply_database(conn, 3)
    finally:
        conn.close()
    assert snapshot(fresh_db) == fresh


def test_a_reset_is_idempotent(fresh_db: Cluster) -> None:
    fresh = snapshot(fresh_db)
    conn = connect(fresh_db)
    try:
        for lab in (2, 3, 4, 2, 3, 4):
            lab_reset.apply_database(conn, lab)
    finally:
        conn.close()
    assert snapshot(fresh_db) == fresh


def test_a_credit_blocks_lab_four_on_a_real_ledger(fresh_db: Cluster) -> None:
    conn = connect(fresh_db)
    try:
        assert lab_reset.credit_blocker(conn) is None
    finally:
        conn.close()


# Evidence a reset must not let a check read ------------------------------------------------

MARCO_ROW = """
INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms)
VALUES ('persona-marco-reset-test', 'check_stock', 'stock',
        '{"agent": "stock", "turn_id": "turn-reset-%(tag)s", "grant": ["check_stock"],
          "product_query": "Hadley"}', '{"status": "success"}', 5)
"""
THEO_ROW = """
INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms,
                                build_fingerprint)
VALUES ('turn-reset-%(tag)s', 'get_tickets', 'gateway', '{"customer_id": "CUST-THEO"}',
        '{"status": "success"}', 5, 'abc123')
"""
ANNA_ROW = """
INSERT INTO pellier.retrieval_receipts (session_id, turn_id, query_hash, search_plan)
VALUES ('persona-anna-reset-test', 'turn-reset-%(tag)s', 'h', '{}')
"""


def database_now(cluster: Cluster) -> datetime:
    return datetime.fromisoformat(cluster.psql("SELECT clock_timestamp()").replace(" ", "T"))


def reset_here(cluster: Cluster, lab: int) -> None:
    check.record_reset_point(lab, database_now(cluster))


def test_lab_two_ignores_a_stock_turn_from_before_its_reset(fresh_db: Cluster) -> None:
    fresh_db.psql(MARCO_ROW % {"tag": "before"})
    conn = connect(fresh_db)
    try:
        assert lab2_check.latest_stock_turn(conn), "the old turn is evidence until a reset"
        reset_here(fresh_db, 2)
        assert lab2_check.latest_stock_turn(conn) == []
        finding = lab2_check.judge_2a(conn)
        assert finding.state == check.NOT_YET
        assert "send the requests again since your reset" in finding.next_step
        assert check.render(finding).count("since your reset") == 1
        recorded = lab2_check.judge_recorded_2b(conn)
        assert recorded.state == check.NOT_YET
        assert "send the requests again since your reset" in recorded.next_step
        fresh_db.psql(MARCO_ROW % {"tag": "after"})
        rows = lab2_check.latest_stock_turn(conn)
        assert rows and "turn-reset-after" in json.dumps(rows[0]["args"])
    finally:
        conn.close()


def test_lab_three_ignores_gateway_reads_from_before_its_reset(fresh_db: Cluster) -> None:
    fresh_db.psql(THEO_ROW % {"tag": "lab3-before"})
    cfg = {"DB_HOST": str(fresh_db.socket), "DB_PORT": "5432", "DB_NAME": "postgres",
           "DB_USER": "postgres", "DB_PASSWORD": ""}
    before = lab3_check.read_rows(cfg)
    assert before["build"] and before["tickets"]
    reset_here(fresh_db, 3)
    after = lab3_check.read_rows(cfg)
    assert after["build"] is None and after["tickets"] == []
    assert lab3_check.judge_build(after["build"], "abc123").state == check.NOT_YET
    assert "since your reset" in lab3_check.judge_build(after["build"], "abc123").next_step
    fresh_db.psql(THEO_ROW % {"tag": "lab3-after"})
    again = lab3_check.read_rows(cfg)
    assert again["build"]["turn_id"] == "turn-reset-lab3-after"
    assert [row["turn_id"] for row in again["tickets"]] == ["turn-reset-lab3-after"]


def test_lab_one_ignores_a_receipt_from_before_its_reset(fresh_db: Cluster) -> None:
    fresh_db.psql(ANNA_ROW % {"tag": "before"})
    conn = connect(fresh_db)
    try:
        with conn.cursor() as cur:
            cur.execute(lab1_retry._LATEST_RECEIPT,
                        {"session": "persona-anna-%", "since": check.reset_point(1)})
            earlier = cur.fetchone()["receipt_id"]
        reset_here(fresh_db, 1)
        finding, rows = lab1_retry.evaluate(conn)
        assert finding.state == check.NOT_YET and rows == []
        assert "no search receipt" in finding.observed
        assert "send the requests again since your reset" in finding.next_step
        fresh_db.psql(ANNA_ROW % {"tag": "after"})
        with conn.cursor() as cur:
            cur.execute(lab1_retry._LATEST_RECEIPT,
                        {"session": "persona-anna-%", "since": check.reset_point(1)})
            assert cur.fetchone()["receipt_id"] > earlier
    finally:
        conn.close()


def test_one_labs_reset_does_not_hide_another_labs_evidence(fresh_db: Cluster) -> None:
    fresh_db.psql(MARCO_ROW % {"tag": "other-lab"})
    reset_here(fresh_db, 3)
    reset_here(fresh_db, 1)
    conn = connect(fresh_db)
    try:
        assert lab2_check.latest_stock_turn(conn)
    finally:
        conn.close()
