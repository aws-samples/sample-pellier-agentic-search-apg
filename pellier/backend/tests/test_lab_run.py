"""The catch-up command installs a lab's answers and makes its requests on the right path.

``scripts/lab_run.py`` backs each guide's "Short on time?" block. These tests
run it against a fake backend over real HTTP, so the SSE parsing, the persona
sessions, the rail check and the Operator sequence are exercised end to end
without AWS. The live behaviour is proved on a workshop box.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab_run = importlib.import_module("lab_run")
lab1_retry = importlib.import_module("lab1_retry")

PROPOSAL = {"reviewId": 41, "amount": "100.00", "orderIds": [7, 9], "actionHash": "a" * 64,
            "status": "pending"}


@pytest.fixture(autouse=True)
def _no_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A checkout's own .env must not steer these tests' rail pre-check."""
    monkeypatch.setattr(lab_run, "ENV_FILE", tmp_path / "no-such.env")


@pytest.fixture(autouse=True)
def _fresh_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test is one command: its first failure opens a new retry budget."""
    monkeypatch.setattr(lab_run, "_retry_deadline", None)


@pytest.fixture(autouse=True)
def _starter_catalog_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 1A's send reads the catalog itself; here it finds what the starter finds."""
    lookup_module = importlib.import_module("lab1_vector")
    monkeypatch.setattr(lookup_module, "lookup", lambda: lookup_module.Lookup())


class FakeBackend:
    """What the fake server answers, and every request it received."""

    def __init__(self) -> None:
        self.rail = lab_run.IN_PROCESS
        self.health = "healthy"
        self.health_fields: Dict[str, Any] = {}
        self.chat_error = ""
        # The next turns that fail before succeeding: an error event, or an HTTP status.
        self.chat_failures: List[Any] = []
        # The next turns that go silent for this long before answering, and those that go
        # silent this long after their first event.
        self.stalls: List[float] = []
        self.midstream_stalls: List[float] = []
        self.proposal: Dict[str, Any] = dict(PROPOSAL)
        self.advisor = "no basis"
        self.policies: List[str] = ["ALLOW"]
        self.requests: List[Dict[str, Any]] = []
        self.sessions = 0
        self.steps: List[Dict[str, Any]] = []
        self.reviews: List[Dict[str, Any]] = []
        self.credited = False
        self.replay_writes_again = False
        # Pellier's answer to each turn; None answers with the request it received.
        self.reply: Optional[str] = None

    def answer(self, path: str, body: Dict[str, Any]) -> Any:
        if path == "/api/health":
            return {"status": self.health, **self.health_fields}
        if path == "/api/operator/reviews":
            return {"reviews": self.reviews}
        if path == "/api/persona/switch":
            self.sessions += 1
            return {"session_id": f"persona-{body['persona_id']}-{self.sessions:032x}"}
        if path == "/api/chat/stream":
            return self._turn(body)
        if path.endswith("/investigate"):
            answer = {"type": "answer", "proposal": self.proposal, "advisor": self.advisor}
            return [("status", {"type": "status"}), ("step", {"type": "step"}),
                    ("answer", answer), ("complete", {**answer, "type": "complete"})]
        if path.endswith("/confirm"):
            return {"status": "approved"}
        if path.endswith("/execute"):
            policy = self.policies.pop(0) if len(self.policies) > 1 else self.policies[0]
            if policy == "502":
                return 502, {"detail": "gateway_unavailable:ReadTimeout"}
            if policy.startswith("409:"):
                return 409, {"detail": {"error": "governed_rail_unavailable", "missing": [
                    f"policy_engine_mode=ENFORCE (observed: {policy[4:]})"]}}
            replay = self.credited and not self.replay_writes_again
            if policy == "ALLOW":
                self.credited = True
            return {"assurance": {"policy": policy}, "idempotencyKey": "credit-41-abc",
                    "notes": {"policy": "engine state unreadable"},
                    "result": {"idempotent_replay": replay},
                    "record": {"creditRows": 1 if policy == "ALLOW" else 0}}
        raise AssertionError(f"unexpected path {path}")

    def _turn(self, body: Dict[str, Any]) -> Any:
        if self.stalls:
            time.sleep(self.stalls.pop(0))
        if self.chat_failures:
            failure = self.chat_failures.pop(0)
            if isinstance(failure, int):
                return failure, {"detail": "service_unavailable"}
            # (steps, error): an attempt that streams its own steps, then fails.
            steps, error = failure if isinstance(failure, tuple) else ([], failure)
            return [(None, {"type": "turn_start"}), *[(None, step) for step in steps],
                    (None, {"type": "error", "error": error})]
        if self.chat_error:
            return [(None, {"type": "turn_start"}),
                    (None, {"type": "error", "error": self.chat_error})]
        response = {"response": self.reply or f"Answer to {body['message']}", "rail": self.rail,
                    "turn_id": f"turn-{len(self.requests)}",
                    "railDecision": {"reason": "managed rail selected"}}
        return [(None, {"type": "turn_start"}), *[(None, step) for step in self.steps],
                (None, {"type": "text", "text": "Ans"}),
                (None, {"type": "complete", "response": response})]


def _handler(fake: FakeBackend) -> type:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _reply(self, body: Dict[str, Any]) -> None:
            fake.requests.append({"path": self.path, "body": body,
                                  "auth": self.headers.get("Authorization", "")})
            if self.headers.get("Authorization") == "Bearer expired":
                self._send(401, "application/json", json.dumps({"detail": "token_expired"}))
                return
            result = fake.answer(self.path, body)
            if isinstance(result, tuple):
                self._send(result[0], "application/json", json.dumps(result[1]))
            elif isinstance(result, list):
                events = ["".join((f"event: {name}\n" if name else "") +
                                  f"data: {json.dumps(data)}\n\n") for name, data in result]
                pause = fake.midstream_stalls.pop(0) if (
                    self.path == "/api/chat/stream" and fake.midstream_stalls) else 0
                self._send(200, "text/event-stream", "".join(events), pause_after=events[0],
                           pause=pause)
            else:
                self._send(200, "application/json", json.dumps(result))

        def _send(self, status: int, kind: str, text: str, pause_after: str = "",
                  pause: float = 0) -> None:
            payload = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if pause:
                head = pause_after.encode("utf-8")
                self.wfile.write(head)
                self.wfile.flush()
                time.sleep(pause)
                payload = payload[len(head):]
            try:
                self.wfile.write(payload)
            except OSError:
                pass  # the client gave up at its deadline

        def do_GET(self) -> None:
            self._reply({})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self._reply(json.loads(self.rfile.read(length) or b"{}"))

    return Handler


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBackend]:
    monkeypatch.setattr(lab_run, "HEALTH_WAIT_SECONDS", 0)
    monkeypatch.setattr(lab_run, "POLICY_WAIT_SECONDS", 60)
    monkeypatch.setattr(lab_run, "RETRY_SECONDS", 0)
    monkeypatch.setattr(lab_run, "TURN_RETRY_SECONDS", 0)
    monkeypatch.setattr(lab_run, "TURN_DEADLINE_SECONDS",
                        {lab_run.IN_PROCESS: 0.5, lab_run.MANAGED: 0.5})
    backend = FakeBackend()
    # The HTTP double records requests. PostgreSQL-backed tests check the actual handoff join.
    monkeypatch.setattr(lab_run, "jessicas_handoff",
                        lambda turn=None, review_id=None: bool(turn or review_id))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(backend))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend.url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield backend
    finally:
        server.shutdown()
        server.server_close()


def _run(fake: FakeBackend, lab: int, token_for: Any = None, *extra: str) -> int:
    return lab_run.main(["send", "--lab", str(lab), *extra], base_url=fake.url,
                        token_for=token_for or (lambda user: f"token-{user}"))


def _turns(fake: FakeBackend) -> List[Dict[str, Any]]:
    return [r for r in fake.requests if r["path"] == "/api/chat/stream"]


# ---------------------------------------------------------------------------
# the requests come from the seeded scenarios, and agree with the checks
# ---------------------------------------------------------------------------


def test_every_lab_conversation_resolves_to_seeded_required_requests() -> None:
    for lab, conversations in lab_run.CONVERSATIONS.items():
        for persona, stages in conversations:
            requests = lab_run.required_requests(persona, stages)
            assert len(requests) == len(stages) and all(requests), (lab, persona)


def test_annas_requests_are_her_sentence_then_the_one_the_lab_1b_check_asks_for() -> None:
    first, full = lab_run.required_requests("anna", ("establish", "exercise"))
    assert full == lab1_retry.ANNA_REQUEST
    assert full.startswith(first) and len(full) > len(first)


def test_an_unknown_stage_names_what_is_missing() -> None:
    with pytest.raises(lab_run.LabRunError, match="no required anna request for encore"):
        lab_run.required_requests("anna", ("exercise", "encore"))


# ---------------------------------------------------------------------------
# solution
# ---------------------------------------------------------------------------


def test_each_lab_installs_exactly_its_own_task_files() -> None:
    for lab in (1, 2, 3, 4):
        entries = lab_run.solution_files(lab)
        assert entries and all(e["alias"].startswith(f"labs/0{lab}-") for e in entries)
        assert all((REPO / e["solution"]).is_file() for e in entries)
    assert len(lab_run.solution_files(3)) == 3


def test_the_go_deeper_worksheet_is_not_a_task_file(tmp_path: Path) -> None:
    """A catch-up must not overwrite the optional worksheet a participant may be editing."""
    assert [Path(e["alias"]).name for e in lab_run.solution_files(1)] == [
        "1A-vector-search.py", "1B-search-plan.py"]
    repo = _scratch_repo(tmp_path)
    (repo / "workshop/lab-1-fusion.sql").write_text("my fusion attempt\n")
    lab_run.install_solution(1, repo)
    assert (repo / "workshop/lab-1-fusion.sql").read_text() == "my fusion attempt\n"


def test_solution_keeps_the_participants_file_beside_the_link(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    plan = next(e for e in lab_run.solution_files(1, repo) if e["alias"].endswith("1B-search-plan.py"))
    (repo / plan["source"]).write_text("my 1B\n")

    lab_run.install_solution(1, repo)
    assert (repo / (plan["alias"] + ".bak")).read_text() == "my 1B\n"

    (repo / plan["source"]).write_text("my second 1B\n")
    lab_run.install_solution(1, repo)
    assert (repo / (plan["alias"] + ".bak.2")).read_text() == "my second 1B\n"


def _scratch_repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "workshop", tmp_path / "workshop")
    for entry in json.loads((REPO / "workshop/participant-files.json").read_text("utf-8")):
        for key in ("source", "solution"):
            target = tmp_path / entry[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / entry[key], target)
    return tmp_path


OLD_LINK_TIME = 1_000_000_000


def _link_alias(repo: Path, entry: Dict[str, str]) -> Path:
    """The editor link as a box has it: a relative symbolic link under labs/, aged."""
    import os

    link = repo / entry["alias"]
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(os.path.relpath(repo / entry["source"], link.parent))
    os.utime(link, (OLD_LINK_TIME, OLD_LINK_TIME), follow_symlinks=False)
    return link


def test_applying_a_task_reports_the_change_at_its_editor_link(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """A tab opened through labs/ reloads only when the change is reported at the link."""
    repo = _scratch_repo(tmp_path)
    entry = lab_run.task_files("2A", repo)[0]
    link = _link_alias(repo, entry)
    (repo / entry["source"]).write_text("my 2A\n")

    lab_run.install_task("2A", repo, next_line=False)

    assert link.is_symlink() and link.lstat().st_mtime > OLD_LINK_TIME
    assert link.read_bytes() == (repo / entry["solution"]).read_bytes()
    assert lab_run.RELOAD_HINT in capsys.readouterr().out

    lab_run.install_task("2A", repo, next_line=False)
    assert lab_run.RELOAD_HINT not in capsys.readouterr().out


def test_a_lab_catch_up_reports_each_change_at_its_editor_link(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    links = [_link_alias(repo, entry) for entry in lab_run.solution_files(2, repo)]
    for entry in lab_run.solution_files(2, repo):
        (repo / entry["source"]).write_text("starter\n")

    lab_run.install_solution(2, repo)

    assert all(link.lstat().st_mtime > OLD_LINK_TIME for link in links)


def test_solution_replaces_the_task_file_and_reports_a_second_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    (repo / "pellier/backend/services/search_plan.py").write_text("half-finished edit\n")
    lab_run.install_solution(1, repo)
    for entry in lab_run.solution_files(1, repo):
        assert (repo / entry["source"]).read_bytes() == (repo / entry["solution"]).read_bytes()
    first = capsys.readouterr().out
    assert "1B-search-plan.py now holds the solution" in first
    # The send that follows restarts Pellier itself, so the next step names only the send.
    assert "systemctl" not in first and "restart" not in first
    assert "uv run scripts/lab_run.py send --lab 1" in first

    lab_run.install_solution(1, repo)
    assert "1B-search-plan.py already holds the solution" in capsys.readouterr().out


def test_solution_leaves_other_labs_untouched(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    marco = repo / "pellier/backend/services/agent_tools.py"
    marco.write_text("starter\n")
    lab_run.install_solution(1, repo)
    assert marco.read_text() == "starter\n"


# ---------------------------------------------------------------------------
# solution --task: one task's answer, previewed, with the participant's file kept
# ---------------------------------------------------------------------------


def _task_entries(repo: Path, task: str) -> List[Dict[str, str]]:
    return [e for e in lab_run.solution_files(int(task[0]), repo)
            if Path(e["alias"]).name.startswith(task)]


def _restarts() -> Any:
    calls: List[str] = []

    def restart() -> None:
        calls.append("restart")
    restart.calls = calls  # type: ignore[attr-defined]
    return restart


@pytest.mark.parametrize("task,later", [("1A", "1B"), ("2A", "2B"), ("3A", "3B"), ("4A", "4B")])
def test_a_task_answer_leaves_the_next_tasks_file_alone(tmp_path: Path, task: str,
                                                        later: str) -> None:
    repo = _scratch_repo(tmp_path)
    for entry in _task_entries(repo, later):
        (repo / entry["source"]).write_text(f"my {later} work\n")
    lab_run.install_task(task, repo, restart=_restarts())
    for entry in _task_entries(repo, task):
        assert (repo / entry["source"]).read_bytes() == (repo / entry["solution"]).read_bytes()
    for entry in _task_entries(repo, later):
        assert (repo / entry["source"]).read_text() == f"my {later} work\n"
        assert not (repo / (entry["alias"] + ".bak")).exists()


def test_3a_installs_both_of_its_files(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    assert [Path(e["alias"]).name for e in _task_entries(repo, "3A")] == [
        "3A-1-publish-tool.py", "3A-2-bind-caller.py"]


def test_reapplying_1a_keeps_a_1b_that_already_passed(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    (one_b,) = _task_entries(repo, "1B")
    shutil.copyfile(repo / one_b["solution"], repo / one_b["source"])
    for _ in range(2):
        lab_run.install_task("1A", repo, restart=_restarts())
    assert (repo / one_b["source"]).read_bytes() == (repo / one_b["solution"]).read_bytes()


def test_every_attempt_the_answer_replaces_is_kept_and_none_is_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    (entry,) = _task_entries(repo, "1B")
    source = repo / entry["source"]
    first, second = (repo / (entry["alias"] + suffix) for suffix in (".bak", ".bak.2"))
    source.write_text("my first attempt\n")

    lab_run.install_task("1B", repo, restart=_restarts())
    assert first.read_text() == "my first attempt\n"
    assert "kept in labs/01-retrieve/1B-search-plan.py.bak" in capsys.readouterr().out

    source.write_text("my second attempt\n")
    lab_run.install_task("1B", repo, restart=_restarts())
    assert first.read_text() == "my first attempt\n"
    assert second.read_text() == "my second attempt\n"
    assert source.read_bytes() == (repo / entry["solution"]).read_bytes()
    assert "kept in labs/01-retrieve/1B-search-plan.py.bak.2" in capsys.readouterr().out

    source.write_text("my first attempt\n")
    lab_run.install_task("1B", repo, restart=_restarts())
    assert not (repo / (entry["alias"] + ".bak.3")).exists()
    assert "already kept in labs/01-retrieve/1B-search-plan.py.bak" in capsys.readouterr().out


def test_a_file_that_already_holds_the_answer_is_left_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    (entry,) = _task_entries(repo, "2A")
    shutil.copyfile(repo / entry["solution"], repo / entry["source"])
    restart = _restarts()
    lab_run.install_task("2A", repo, restart=restart)
    out = capsys.readouterr().out
    assert "labs/02-ground/2A-stock-agent.py already holds the answer" in out
    assert not (repo / (entry["alias"] + ".bak")).exists()
    assert restart.calls == []


def test_the_preview_shows_the_change_from_your_file_to_the_answer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    (entry,) = _task_entries(repo, "2A")
    lines = (repo / entry["solution"]).read_text().split("\n")
    at = next(i for i, line in enumerate(lines) if line.strip() and lines.count(line) == 1)
    finished, lines[at] = lines[at], "    my unfinished line"
    (repo / entry["source"]).write_text("\n".join(lines))

    lab_run.install_task("2A", repo, restart=_restarts())

    out = capsys.readouterr().out
    del finished
    assert "2A-stock-agent.py   (Stock agent - definition)" in out
    assert "--- yours" not in out and "@@" not in out
    assert "(the answer changes lines outside the marked region)" in out
    assert "uv run scripts/lab_run.py diff --lab 2" in out


def test_the_printed_change_is_only_the_changed_code_lines_in_the_region() -> None:
    old = (b"keep = 1\n# WORKSHOP - Gateway - published tools: START ===\n# a long comment\n"
           b"X = frozenset({\"a\"})\n\n# WORKSHOP - Gateway - published tools: END ===\n")
    new = old.replace(b'frozenset({"a"})', b"frozenset()")
    label, lines = lab_run.changed_code(old, new)
    assert label == "Gateway - published tools"
    assert lines == ['    - X = frozenset({"a"})', "    + X = frozenset()"]


@pytest.mark.parametrize("task,restarted", [
    ("1A", True), ("1B", True), ("2A", True), ("3A", True),
    ("2B", False), ("3B", False), ("4A", False), ("4B", False)])
def test_the_app_restarts_only_when_a_backend_file_changed(
    tmp_path: Path, task: str, restarted: bool,
) -> None:
    repo = _scratch_repo(tmp_path)
    for entry in _task_entries(repo, task):
        (repo / entry["source"]).write_text("starter\n")
    restart = _restarts()
    lab_run.install_task(task, repo, restart=restart)
    assert restart.calls == (["restart"] if restarted else [])


@pytest.mark.parametrize("task,expected", [
    ("1A", ["uv run scripts/lab1_check.py --task 1A"]),
    ("1B", ["uv run scripts/lab_run.py send --lab 1 --task 1B",
            "uv run scripts/lab1_check.py --task 1B"]),
    ("2A", ["uv run scripts/lab_run.py send --lab 2 --task 2A",
            "uv run scripts/lab2_check.py --task 2A"]),
    ("2B", ["psql -f labs/02-ground/2B-check-stock.sql",
            "uv run scripts/lab2_check.py --task 2B"]),
    ("3A", ["uv run scripts/lab3_check.py --task 3A", lab_run.DEPLOY]),
    ("3B", ["psql -f labs/03-deploy/3B-row-ownership.sql"]),
    ("4A", ["uv run scripts/lab4_check.py --task 4A", lab_run.DEPLOY]),
    ("4B", ["psql -f labs/04-govern/4B-credit-writer.sql",
            "uv run scripts/lab4_check.py --task 4B"]),
])
def test_each_task_names_its_next_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], task: str, expected: List[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    lab_run.install_task(task, repo, restart=_restarts())
    out = capsys.readouterr().out
    assert all(command in out for command in expected), out


def test_solution_with_a_task_from_another_lab_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        lab_run.main(["solution", "--lab", "1", "--task", "2A"])
    assert "--task 2A goes with solution --lab 2" in capsys.readouterr().err


def test_send_still_refuses_a_task_without_its_own_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        lab_run.main(["send", "--lab", "4", "--task", "4A"])
    assert "send --task takes one of" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def test_diff_shows_the_finished_lines_as_minus_and_the_participants_as_plus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    lab_run.install_solution(2, repo)
    capsys.readouterr()
    entry = next(e for e in lab_run.solution_files(2, repo) if e["alias"].endswith("2A-stock-agent.py"))
    lines = (repo / entry["solution"]).read_text().split("\n")
    at = next(i for i, line in enumerate(lines) if line.strip() and lines.count(line) == 1)
    finished, lines[at] = lines[at], "    my unfinished line"
    (repo / entry["source"]).write_text("\n".join(lines))

    differs = lab_run.show_diff(2, repo, color=False)

    out = capsys.readouterr().out
    assert differs == 1
    assert f"--- expected (Lab 2 solution: {entry['source']})" in out
    assert f"+++ yours ({entry['source']})" in out
    assert f"\n-{finished}\n" in out
    assert "\n+    my unfinished line\n" in out
    assert "2B-check-stock.sql matches the solution" in out
    assert "uv run scripts/lab_run.py solution --lab 2" in out
    assert "\x1b[" not in out


def test_diff_reports_a_finished_lab_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    lab_run.install_solution(4, repo)
    before = {e["source"]: (repo / e["source"]).read_bytes() for e in lab_run.solution_files(4, repo)}
    capsys.readouterr()

    assert lab_run.show_diff(4, repo, color=False) == 0

    out = capsys.readouterr().out
    assert "--- expected" not in out
    assert "4A-credit-limit.cedar matches the solution" in out
    assert "4B-credit-writer.sql matches the solution" in out
    assert {s: (repo / s).read_bytes() for s in before} == before


def test_diff_colours_only_when_asked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _scratch_repo(tmp_path)
    (repo / "pellier/backend/services/search_plan.py").write_text("starter\n")
    lab_run.show_diff(1, repo, color=True)
    assert "\x1b[31m-" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# server-sent events
# ---------------------------------------------------------------------------


def test_sse_events_reads_named_unnamed_and_unterminated_events() -> None:
    lines = [b"event: step\n", b'data: {"n": 1}\n', b"\n", b": keep-alive\n", b"\n",
             b'data: {"n": 2}\r\n', b"\r\n", b'data: {"n": 3}\n']
    assert list(lab_run.sse_events(lines)) == [
        ("step", {"n": 1}), ("message", {"n": 2}), ("message", {"n": 3})]


def test_sse_events_refuses_data_that_is_not_json() -> None:
    with pytest.raises(lab_run.LabRunError, match="not JSON"):
        list(lab_run.sse_events([b"data: <html>\n", b"\n"]))


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def test_lab_1_sends_annas_two_requests_each_in_a_new_persona_session(fake: FakeBackend) -> None:
    assert _run(fake, 1) == 0
    first, full = _turns(fake)
    for turn in (first, full):
        assert turn["auth"] == "Bearer token-anna"
        assert turn["body"]["session_id"].startswith("persona-anna-")
        assert turn["body"]["customer_id"] == "CUST-ANNA"
    assert first["body"]["session_id"] != full["body"]["session_id"]
    assert full["body"]["message"] == lab1_retry.ANNA_REQUEST
    assert first["body"]["message"] == "A housewarming gift for a friend who loves slow mornings."


@pytest.mark.parametrize("task,message", [
    ("1A", "A housewarming gift for a friend who loves slow mornings."),
    ("1B", lab1_retry.ANNA_REQUEST),
])
def test_a_lab_1_task_sends_only_its_own_request(fake: FakeBackend, task: str,
                                                  message: str) -> None:
    assert _run(fake, 1, None, "--task", task) == 0
    (turn,) = _turns(fake)
    assert turn["body"]["message"] == message


def test_lab_2_tasks_send_the_brooklyn_count_then_the_cape(fake: FakeBackend) -> None:
    assert _run(fake, 2, None, "--task", "2A") == 0
    assert _run(fake, 2, None, "--task", "2B") == 0
    hadley, cape = _turns(fake)
    assert "units of the Hadley Linen Shirt are" in hadley["body"]["message"]
    assert cape["body"]["message"] == "Is the Velvet Opera Cape in stock?"


@pytest.mark.parametrize("extra", [(), ("--task", "2A")])
def test_2a_send_records_its_turn_and_2b_keeps_it(fake, tmp_path, extra) -> None:
    receipt = tmp_path / "lab-2a-turn.json"
    assert _run(fake, 2, None, *extra) == 0
    shirt = _turns(fake)[-1]
    assert "Hadley Linen Shirt" in shirt["body"]["message"]
    saved = json.loads(receipt.read_text())
    assert saved == {"session": shirt["body"]["session_id"], "turn": f"turn-{len(fake.requests)}"}
    assert _run(fake, 2, None, "--task", "2B") == 0
    assert json.loads(receipt.read_text()) == saved
    fake.chat_error = "unable to finish"
    assert _run(fake, 2, None, "--task", "2A") == 1
    assert receipt.read_text() == ""


def test_overlapping_shirt_sends_keep_the_newest_attempt() -> None:
    path = lab_run.check.lab2_shirt_turn_path()
    with lab_run._begin_turn_record(path) as older:
        with lab_run._begin_turn_record(path) as newer:
            newer.write("newer")
        older.write("older")
    assert path.read_text() == "newer"


def test_lab_3a_sends_theos_ticket_question_alone_on_agentcore(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 3, None, "--task", "3A") == 0
    (turn,) = _turns(fake)
    assert turn["body"]["message"] == (
        "My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?")


def test_a_task_from_another_lab_is_refused_before_anything_is_sent(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        _run(fake, 2, None, "--task", "1A")
    assert "--task 1A goes with send --lab 1" in capsys.readouterr().err
    assert _turns(fake) == []


def test_lab_2_sends_marcos_two_requests_in_one_conversation(fake: FakeBackend) -> None:
    assert _run(fake, 2) == 0
    cape, hadley = _turns(fake)
    assert cape["body"]["session_id"] == hadley["body"]["session_id"]
    assert "Velvet Opera Cape" in cape["body"]["message"]
    assert hadley["body"]["conversation_history"] == [
        {"role": "user", "content": cape["body"]["message"]},
        {"role": "assistant", "content": f"Answer to {cape['body']['message']}"}]


def test_an_in_process_lab_refuses_a_turn_that_ran_on_agentcore(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 1) == 1
    err = capsys.readouterr().err
    assert "Lab 1 runs in process, but this turn ran on gateway-mcp" in err
    # Going back is one command, never a hand edit of the setting.
    assert "uv run scripts/lab_run.py local" in err
    assert "USE_AGENTCORE_RUNTIME" not in err


def test_a_managed_lab_refuses_an_in_process_turn(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(fake, 3) == 1
    err = capsys.readouterr().err
    deploy = err.index(lab_run.DEPLOY)
    assert "Lab 3's deploy moves Pellier onto AgentCore" in " ".join(err.split())
    assert err.index("bash scripts/lab3-start.sh theo") > deploy
    assert len(_turns(fake)) == 1


def test_a_managed_turn_says_it_ran_on_agentcore(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 3, None, "--task", "3A") == 0
    assert "  + OK    Answered on AgentCore (Runtime \u2192 Gateway)" in capsys.readouterr().out


def test_lab_3_starts_a_new_conversation_before_the_ticket_requests(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 3) == 0
    pick, ticket, household = _turns(fake)
    assert pick["body"]["session_id"] != ticket["body"]["session_id"]
    assert ticket["body"]["session_id"] == household["body"]["session_id"]
    assert "Wabi-Sabi Bowl" in ticket["body"]["message"]
    assert "Jessica" in household["body"]["message"]
    assert len(household["body"]["conversation_history"]) == 2
    assert {t["auth"] for t in (pick, ticket, household)} == {"Bearer token-theo"}


def test_a_failed_turn_stops_the_command(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.chat_error = "model_unavailable"
    assert _run(fake, 1) == 1
    assert "the turn failed: model_unavailable" in capsys.readouterr().err
    assert len(_turns(fake)) == lab_run.TURN_ATTEMPTS, "sent three times, then stopped"


@pytest.mark.parametrize("failure", ["ThrottlingException: slow down", 503])
def test_a_turn_the_model_or_server_fails_is_sent_again(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], failure: Any,
) -> None:
    fake.chat_failures = [failure, failure]
    assert _run(fake, 2) == 0
    turns = _turns(fake)
    assert len(turns) == 4, "the first request twice more, then the second once"
    assert turns[0]["body"] == turns[1]["body"] == turns[2]["body"]
    assert turns[3]["body"]["conversation_history"][0]["content"] == turns[0]["body"]["message"]
    out = capsys.readouterr().out
    assert "sending the same request again in 0 s (2 of 3)" in out
    assert "sending the same request again in 0 s (3 of 3)" in out


def test_an_empty_runtime_reply_is_sent_again(fake: FakeBackend) -> None:
    """A test event, 25 Nov 2026: the AgentCore data plane answered a completed turn with an empty
    body. The app reports it as runtime_invalid_response, which the stream classifies as
    request_failed; a terminal send resends it like any failed turn."""
    from services.chat_error_taxonomy import classify_chat_error

    event = classify_chat_error("runtime_invalid_response")
    assert event["code"] == "request_failed" and event["retryable"] is True
    fake.chat_failures = [event["error"]]
    assert _run(fake, 2) == 0
    assert len(_turns(fake)) == 3, "the first request twice, then the second once"


def test_resends_wait_longer_each_time(
    fake: FakeBackend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run, "TURN_RETRY_SECONDS", 0.01)
    pauses: list[float] = []
    real_sleep = time.sleep
    client = threading.current_thread()

    def sleep(seconds: float) -> None:
        # lab_run.time is the global time module, so the fake server's thread sleeps through
        # this patch too (between streamed events); only the client's resend waits count here.
        if threading.current_thread() is client:
            pauses.append(seconds)
            real_sleep(0)
        else:
            real_sleep(seconds)

    monkeypatch.setattr(lab_run.time, "sleep", sleep)
    fake.chat_failures = [503, 503]
    assert _run(fake, 2) == 0
    assert pauses[:2] == pytest.approx([0.01, 0.04])


@pytest.mark.parametrize("where", ["before it answers", "after its first event"])
def test_a_turn_that_goes_silent_is_cut_at_its_deadline_and_sent_again(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], where: str,
) -> None:
    if where == "before it answers":
        fake.stalls = [3.0]
    else:
        fake.midstream_stalls = [3.0]
    started = time.monotonic()
    assert _run(fake, 2) == 0
    assert time.monotonic() - started < 2.5, "the client gave up at its deadline, not the server"
    assert len(_turns(fake)) == 3
    assert "no answer after 0.5 s" in capsys.readouterr().out


@pytest.mark.parametrize("budget,sends", [(0, 1), (60, 3)])
def test_resends_stop_once_the_retry_budget_is_spent(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    budget: int, sends: int,
) -> None:
    monkeypatch.setattr(lab_run, "RETRY_BUDGET_SECONDS", budget)
    fake.chat_error = "ThrottlingException: slow down"
    assert _run(fake, 1) == 1
    assert len(_turns(fake)) == sends
    err = " ".join(capsys.readouterr().err.split())
    assert "your files are fine" in err and "Run the same command again in a minute" in err


@pytest.mark.usefixtures("box")
def test_a_spent_budget_also_stops_a_check_from_sending_again(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run, "RETRY_BUDGET_SECONDS", 0)
    repo = _scratch_repo(tmp_path)
    commands = Commands(failing="lab1_check.py --task 1B", times=1)
    assert _finish(fake, 1, repo, commands) == 1
    assert commands.ran.count("uv run scripts/lab1_check.py --task 1B") == 1
    assert len(_turns(fake)) == 2


def test_an_http_error_names_the_path_and_the_detail(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(fake, 1, token_for=lambda user: "expired") == 1
    assert "/api/chat/stream answered HTTP 401: token_expired" in capsys.readouterr().err
    assert len(_turns(fake)) == 1, "a refused sign-in is not sent again"


def test_a_turn_on_the_wrong_path_is_not_sent_again(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 1) == 1
    assert len(_turns(fake)) == 1


def test_an_unhealthy_backend_stops_before_any_turn(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.health = "starting"
    assert _run(fake, 1) == 1
    assert "not healthy" in capsys.readouterr().err
    assert not _turns(fake)


def _operator(fake: FakeBackend) -> List[Dict[str, Any]]:
    return [r for r in fake.requests if r["path"].startswith("/api/operator/")]


def test_lab_4_has_nadia_approve_and_execute_the_proposed_credit(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 4) == 0
    (jessica,) = _turns(fake)
    assert jessica["auth"] == "Bearer token-jessica"
    operator = _operator(fake)
    assert [r["path"] for r in operator] == [
        "/api/operator/reviews",
        "/api/operator/clients/CUST-JESSICA/investigate",
        "/api/operator/reviews/41/confirm",
        "/api/operator/reviews/41/execute"]
    assert operator[2]["body"] == {"actionHash": "a" * 64}
    assert {r["auth"] for r in operator} == {"Bearer token-nadia"}


def _review(status: str, aurora: str, review_id: int = 41, **extra: Any) -> Dict[str, Any]:
    return {"reviewId": review_id, "customerId": "CUST-JESSICA", "status": status,
            "actionHash": "a" * 64, "amount": "100.00", "orderIds": [7, 9],
            "assurance": {"aurora": aurora}, "policyCheckProbe": False, **extra}


def test_lab_4_never_opens_a_second_credit_when_jessica_was_already_credited(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.credited = True
    fake.reviews = [_review("approved", "PERMITTED"),
                    _review("approved", "PERMITTED", 77, customerId="CUST-THEO"),
                    _review("approved", "NOT_REACHED", 90, policyCheckProbe=True)]
    assert _run(fake, 4) == 0
    paths = [r["path"] for r in _operator(fake)]
    assert paths == ["/api/operator/reviews"]
    assert _turns(fake) == [], "reusing a paid review must not leave an unrelated open handoff"
    assert "review 41 already credited Jessica" in capsys.readouterr().out


def test_lab_4_finishes_the_review_a_person_approved_without_investigating_again(
    fake: FakeBackend,
) -> None:
    fake.rail = lab_run.MANAGED
    fake.reviews = [_review("approved", "NOT_REACHED")]
    assert _run(fake, 4) == 0
    assert _turns(fake) == []
    assert [r["path"] for r in _operator(fake)] == [
        "/api/operator/reviews", "/api/operator/reviews/41/execute"]


@pytest.mark.parametrize("status", ["approved", "pending"])
def test_an_unlinked_review_never_pays_or_reopens_jessicas_case(
    fake: FakeBackend, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], status: str,
) -> None:
    fake.rail = lab_run.MANAGED
    fake.reviews = [_review(status, "NOT_REACHED")]
    def no_handoff(turn=None, review_id=None):
        assert turn is None and review_id == 41
        return False
    monkeypatch.setattr(lab_run, "jessicas_handoff", no_handoff)
    assert _run(fake, 4) == 1
    assert "no shopper request links to review 41" in capsys.readouterr().err
    assert _turns(fake) == []
    assert [r["path"] for r in _operator(fake)] == ["/api/operator/reviews"]


def test_a_new_review_without_a_link_to_jessicas_request_is_never_approved_or_paid(
    fake: FakeBackend, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Jessica's request exists, but the review the investigation returned never linked to it."""
    fake.rail = lab_run.MANAGED
    checked: List[Optional[int]] = []
    def handoff(turn: Optional[str] = None, review_id: Optional[int] = None) -> bool:
        checked.append(review_id)
        return review_id is None
    monkeypatch.setattr(lab_run, "jessicas_handoff", handoff)
    assert _run(fake, 4) == 1
    paths = [r["path"] for r in _operator(fake)]
    assert paths == ["/api/operator/reviews", "/api/operator/clients/CUST-JESSICA/investigate"]
    assert sum(p.endswith("/confirm") for p in paths) == 0, "approval must not be called"
    assert sum(p.endswith("/execute") for p in paths) == 0, "execution must not be called"
    assert 41 in checked, "the review the investigation returned must be checked by its ID"
    err = " ".join(capsys.readouterr().err.split())
    assert "no shopper request links to review 41" in err
    assert "Keep review 41 open" in err and "facilitator" in err


def test_lab_4_finishes_the_approved_review_before_a_newer_pending_one(
    fake: FakeBackend,
) -> None:
    fake.rail = lab_run.MANAGED
    fake.reviews = [_review("pending", "NOT_REACHED", 52), _review("approved", "NOT_REACHED")]
    assert _run(fake, 4) == 0
    assert [r["path"] for r in _operator(fake)] == [
        "/api/operator/reviews", "/api/operator/reviews/41/execute"]


def test_lab_4_stops_rather_than_overrule_a_person_who_rejected_the_credit(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.reviews = [_review("rejected", "NOT_REACHED")]
    assert _run(fake, 4) == 1
    assert [r["path"] for r in _operator(fake)] == ["/api/operator/reviews"]
    err = " ".join(capsys.readouterr().err.split())
    assert "review 41 was rejected" in err
    assert "investigate Jessica's case in the Operator" in err


def test_lab_4_retries_while_the_new_cedar_rule_applies(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.policies = ["DENY", "DENY", "ALLOW"]
    assert _run(fake, 4) == 0
    executes = [r for r in fake.requests if r["path"].endswith("/execute")]
    assert len(executes) == 3
    assert capsys.readouterr().out.count("Policy DENY") == 2


def test_lab_4_retries_while_the_gateway_and_policy_state_settle(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.policies = ["502", "EVALUATION_INCOMPLETE", "ALLOW"]
    assert _run(fake, 4) == 0
    out = capsys.readouterr().out
    assert "the Gateway did not answer (gateway_unavailable:ReadTimeout)" in out
    assert "Policy could not confirm enforcement yet" in out


def test_lab_4_retries_when_the_policy_engine_could_not_be_read(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    """A Lab 4 check reading the engine at the same moment got the control plane throttled on
    the 2026-11-09 test event; the app refused the Execute as unreadable and wrote nothing."""
    fake.rail = lab_run.MANAGED
    fake.policies = ["409:unreadable", "ALLOW"]
    assert _run(fake, 4) == 0
    assert "the policy engine's mode could not be read just now" in capsys.readouterr().out


def test_lab_4_stops_when_the_gateway_is_not_enforcing(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    fake.policies = ["409:LOG_ONLY"]
    assert _run(fake, 4) == 1
    assert len([r for r in fake.requests if r["path"].endswith("/execute")]) == 1


def test_lab_4_stops_on_an_execution_error_that_will_not_clear(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.policies = ["NOT_EVALUATED"]
    assert _run(fake, 4) == 1
    assert "Policy reported NOT_EVALUATED for review 41" in capsys.readouterr().err
    assert len([r for r in fake.requests if r["path"].endswith("/execute")]) == 1


def test_lab_4_skips_approval_a_person_already_gave(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    fake.proposal = {**PROPOSAL, "status": "approved"}
    assert _run(fake, 4) == 0
    assert not [r for r in fake.requests if r["path"].endswith("/confirm")]


def test_lab_4_gives_up_when_cedar_keeps_denying(
    fake: FakeBackend, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(lab_run, "POLICY_WAIT_SECONDS", 0)
    fake.rail = lab_run.MANAGED
    fake.policies = ["DENY"]
    assert _run(fake, 4) == 1
    err = capsys.readouterr().err
    assert "review 41 has no Policy ALLOW after 0 minutes" in err
    assert "last: Policy DENY" in err


def test_lab_4_reports_an_advisor_that_proposed_nothing(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.proposal = None
    assert _run(fake, 4) == 1
    assert "the Advisor proposed no credit for Jessica: no basis" in capsys.readouterr().err


def test_lab_4_quotes_the_advisors_sentence_without_a_doubled_stop(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.proposal = None
    fake.advisor = "Please send the two order ids."
    assert _run(fake, 4) == 1
    err = capsys.readouterr().err
    assert "Please send the two order ids. Rerun this command" in err
    assert ".." not in err


def test_lab_4_shopper_only_sends_jessicas_request_and_leaves_the_decision_to_nadia(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    seen: List[str] = []

    def token_for(user: str) -> str:
        seen.append(user)
        return f"token-{user}"

    assert _run(fake, 4, token_for, "--shopper-only") == 0
    (jessica,) = _turns(fake)
    assert "store credit for the two items I returned" in jessica["body"]["message"]
    assert not [r for r in fake.requests if r["path"].startswith("/api/operator/")]
    assert seen == ["jessica"], "Nadia's token is never minted"
    assert "as Nadia in the Operator" in capsys.readouterr().out


def test_a_completed_shopper_turn_without_a_saved_request_does_not_send_you_to_nadia(
    fake: FakeBackend, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED

    def missing(turn: str) -> bool:
        assert turn.startswith("turn-")
        return False

    monkeypatch.setattr(lab_run, "jessicas_handoff", missing)
    assert _run(fake, 4, None, "--shopper-only") == 1
    output = capsys.readouterr()
    assert "could not confirm an open credit request" in output.err
    assert "as Nadia in the Operator" not in output.out
    assert not _operator(fake)


def test_shopper_only_ends_with_nadias_username_and_where_her_password_is(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 4, None, "--shopper-only") == 0
    out = capsys.readouterr().out
    last = " ".join(out.rstrip("\n").split())
    assert last.endswith(
        "Nadia's sign-in for the Operator: username nadia. Copy her password from the Event "
        "Dashboard: Event outputs, OperatorPassword.")
    assert "password " not in out.replace("her password", "").replace("OperatorPassword", "")


def test_no_send_prints_a_password_from_the_credentials_file(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    credentials = tmp_path / "test-credentials.txt"
    credentials.write_text("Username: nadia\nPassword: Nadia-Sign-In-7\n")
    monkeypatch.setenv("PELLIER_TEST_CREDENTIALS", str(credentials))
    fake.rail = lab_run.MANAGED
    assert _run(fake, 4) == 0
    assert _run(fake, 3) == 0
    assert "Nadia-Sign-In-7" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# finish: the lab's "Running behind?" sequence as one command
# ---------------------------------------------------------------------------


class Commands:
    """Every command finish runs, with exit statuses scripted by a command's last words."""

    def __init__(self, failing: str = "", times: Optional[int] = None) -> None:
        self.ran: List[str] = []
        self.executed: List[List[str]] = []
        self.failing = failing
        self.times = times

    def __call__(self, argv: List[str], **kwargs: Any) -> Any:
        self.executed.append(list(argv))
        typed = ["uv", "run", *argv[1:]] if argv[0] == sys.executable else list(argv)
        if typed[:8] == ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-v", "quiet_next=1", "-P",
                         "pager=off"]:
            typed = ["psql", *typed[8:]]
        shown = " ".join(typed)
        self.ran.append(shown)
        failed = bool(self.failing) and shown.endswith(self.failing)
        if failed and self.times is not None:
            failed = self.times > 0
            self.times -= 1
        return type("Completed", (), {"returncode": 1 if failed else 0})()


@pytest.fixture
def box(monkeypatch: pytest.MonkeyPatch) -> None:
    """A workshop box: systemctl is installed and the participant is not root."""
    monkeypatch.setattr(lab_run.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(lab_run.os, "geteuid", lambda: 1000)


def _finish(fake: FakeBackend, lab: int, repo: Path, commands: Commands) -> int:
    try:
        lab_run.finish(lab, lab_run.Backend(fake.url), lambda user: f"token-{user}",
                       run=commands, repo=repo)
    except lab_run.LabRunError as exc:
        lab_run.fail(str(exc))
        return 1
    return 0




def test_finish_prints_uv_and_psql_but_runs_without_either_setup() -> None:
    """The catch-up shows the commands the guide teaches, but runs a check with this
    interpreter and psql with its flags spelled out, so it never needs uv or ~/.psqlrc."""
    assert lab_run._executable(["uv", "run", "scripts/lab2_check.py", "--task", "2B"]) == [
        sys.executable, "scripts/lab2_check.py", "--task", "2B"]
    assert lab_run._executable(lab_run._psql("labs/02-ground/2B-check-stock.sql")) == [
        "psql", "-X", "-v", "ON_ERROR_STOP=1", "-v", "quiet_next=1", "-P", "pager=off", "-f",
        "labs/02-ground/2B-check-stock.sql"]
    assert lab_run._executable(["sudo", "-n", "systemctl", "restart", "pellier"]) == [
        "sudo", "-n", "systemctl", "restart", "pellier"]

RESTART = "sudo -n systemctl restart pellier"
DEPLOY_RUN = ("uv run scripts/provision_agentcore_end_to_end.py --repo-path {repo} "
              "--mode participant")


@pytest.mark.usefixtures("box")
def test_finish_lab_1_installs_restarts_sends_and_checks(fake: FakeBackend, tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    for entry in lab_run.solution_files(1, repo):
        (repo / entry["source"]).write_text("starter\n")
    commands = Commands()
    assert _finish(fake, 1, repo, commands) == 0
    assert commands.ran == [RESTART, "uv run scripts/lab1_check.py --task 1A",
                            "uv run scripts/lab1_check.py --task 1B"]
    assert len(_turns(fake)) == 2
    for entry in lab_run.solution_files(1, repo):
        assert (repo / entry["source"]).read_bytes() == (repo / entry["solution"]).read_bytes()
        assert (repo / (entry["alias"] + ".bak")).read_text() == "starter\n"


FINISH_STEPS = {
    1: ["Putting the lab's answers in place", "Restarting the backend",
        "Sending Anna's requests in process", "Running Task 1A's check",
        "Running Task 1B's check"],
    2: ["Putting the lab's answers in place", "Running the Task 2B SQL file",
        "Restarting the backend", "Sending Marco's requests in process",
        "Running Task 2A's check", "Running Task 2B's check"],
    3: ["Putting the lab's answers in place", "Running Task 3A's check",
        "Deploying the Task 3A files to AgentCore", "Running the Task 3B SQL file",
        "Sending Theo's requests on AgentCore", "Running Task 3B's check"],
    4: ["Putting the lab's answers in place", "Running the Task 4B SQL file",
        "Deploying the Cedar rule to AgentCore",
        "Sending Jessica's request and settling the credit", "Running Task 4A's check",
        "Running Task 4B's check", "Running the Lab 4 absence check"],
}


def _started(out: str, name: str) -> List[str]:
    """Each numbered step's label, from the line it prints as it starts."""
    prefix = f"  - {name} "
    return [line[len(prefix):].split("  ", 1)[1].rsplit(" (usually", 1)[0]
            for line in out.splitlines() if line.startswith(prefix)]


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("lab", [1, 2, 3, 4])
def test_finish_numbers_its_steps_and_says_how_long_each_usually_takes(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str], lab: int,
) -> None:
    fake.rail = lab_run.LAB_RAIL[lab]
    assert _finish(fake, lab, _scratch_repo(tmp_path), Commands()) == 0
    out = capsys.readouterr().out
    total = len(FINISH_STEPS[lab])
    assert _started(out, f"Lab {lab} step") == FINISH_STEPS[lab]
    assert f"  - Lab {lab} step {total}/{total}  " in out
    assert out.count(f"  Lab {lab} step ") == total, "each step leaves one end line"
    summary = next(line for line in out.splitlines() if line.startswith(f"  {total} steps"))
    assert summary.startswith(f"  {total} steps, usually about ")
    assert "  Done in " in out


@pytest.mark.usefixtures("box")
def test_a_failed_step_is_marked_failed_and_the_steps_after_it_never_start(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    commands = Commands(failing="lab1_check.py --task 1A")
    assert _finish(fake, 1, _scratch_repo(tmp_path), commands) == 1
    out = capsys.readouterr().out
    assert "Lab 1 step 4/5  Running Task 1A's check: failed" in out
    assert "Lab 1 step 5/5" not in out and "Done in" not in out


@pytest.mark.usefixtures("box")
def test_finish_keeps_a_finished_task_and_backs_up_only_the_unfinished_one(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    repo = _scratch_repo(tmp_path)
    (one_a,) = _task_entries(repo, "1A")
    (one_b,) = _task_entries(repo, "1B")
    shutil.copyfile(repo / one_a["solution"], repo / one_a["source"])
    (repo / one_b["source"]).write_text("half of 1B\n")
    assert _finish(fake, 1, repo, Commands()) == 0
    assert not (repo / (one_a["alias"] + ".bak")).exists()
    assert (repo / (one_b["alias"] + ".bak")).read_text() == "half of 1B\n"


@pytest.mark.usefixtures("box")
def test_a_second_finish_keeps_the_first_backup_and_runs_the_proof_again(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    repo = _scratch_repo(tmp_path)
    (one_b,) = _task_entries(repo, "1B")
    (repo / one_b["source"]).write_text("my 1B\n")
    commands = Commands()
    assert _finish(fake, 1, repo, commands) == 0
    assert _finish(fake, 1, repo, commands) == 0
    assert (repo / (one_b["alias"] + ".bak")).read_text() == "my 1B\n"
    assert commands.ran.count("uv run scripts/lab1_check.py --task 1B") == 2


@pytest.mark.usefixtures("box")
def test_finish_stops_at_the_first_failed_check(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    commands = Commands(failing="lab1_check.py --task 1A")
    assert _finish(fake, 1, repo, commands) == 1
    assert commands.ran[-1] == "uv run scripts/lab1_check.py --task 1A"
    err = capsys.readouterr().err
    assert "uv run scripts/lab1_check.py --task 1A exited 1" in err
    assert "uv run scripts/lab_run.py finish --lab 1" in err
    assert commands.ran.count("uv run scripts/lab1_check.py --task 1A") == 1, (
        "1A runs the code against stored embeddings; no new turn can change its verdict")


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("lab,task,resent", [
    (1, "1B", ["Bearer token-anna"]), (2, "2A", ["Bearer token-marco"]),
    (3, "3B", ["Bearer token-theo"] * 3),
])
def test_a_check_that_judges_the_newest_turn_gets_a_new_turn_and_a_second_look(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    lab: int, task: str, resent: List[str],
) -> None:
    fake.rail = lab_run.LAB_RAIL[lab]
    repo = _scratch_repo(tmp_path)
    check = f"lab{lab}_check.py --task {task}"
    commands = Commands(failing=check, times=1)
    sent_by_the_lab = {1: 2, 2: 2, 3: 3}[lab]
    assert _finish(fake, lab, repo, commands) == 0
    assert commands.ran.count(f"uv run scripts/{check}") == 2
    turns = _turns(fake)
    assert [turn["auth"] for turn in turns[sent_by_the_lab:]] == resent
    assert f"sending the request Task {task}'s check judges again (2 of 3)" in " ".join(
        capsys.readouterr().out.split())


@pytest.mark.usefixtures("box")
def test_a_turn_judged_check_that_keeps_failing_stops_after_three_looks(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    commands = Commands(failing="lab2_check.py --task 2A")
    assert _finish(fake, 2, repo, commands) == 1
    assert commands.ran.count("uv run scripts/lab2_check.py --task 2A") == lab_run.CHECK_ATTEMPTS
    assert "uv run scripts/lab2_check.py --task 2B" not in commands.ran
    assert "uv run scripts/lab2_check.py --task 2A exited 1" in capsys.readouterr().err


@pytest.mark.usefixtures("box")
def test_finish_lab_2_commits_the_exercise_before_the_restart_and_requests(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    repo = _scratch_repo(tmp_path)
    commands = Commands()
    assert _finish(fake, 2, repo, commands) == 0
    assert commands.ran == [
        "psql -f labs/02-ground/2B-check-stock.sql",
        RESTART, "uv run scripts/lab2_check.py --task 2A",
        "uv run scripts/lab2_check.py --task 2B"]
    assert len(_turns(fake)) == 2


@pytest.mark.usefixtures("box")
def test_finish_lab_3_deploys_writes_the_rule_then_sends_on_agentcore(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    fake.rail = lab_run.MANAGED
    repo = _scratch_repo(tmp_path)
    commands = Commands()
    assert _finish(fake, 3, repo, commands) == 0
    assert commands.ran == [
        "uv run scripts/lab3_check.py --task 3A", DEPLOY_RUN.format(repo=repo),
        "psql -f labs/03-deploy/3B-row-ownership.sql",
        "uv run scripts/lab3_check.py --task 3B"]
    assert len(_turns(fake)) == 3


@pytest.mark.usefixtures("box")
def test_a_failed_deploy_stops_finish_before_anything_reaches_agentcore(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    fake.rail = lab_run.MANAGED
    repo = _scratch_repo(tmp_path)
    commands = Commands(failing="--mode participant")
    assert _finish(fake, 3, repo, commands) == 1
    assert commands.ran[-1] == DEPLOY_RUN.format(repo=repo)
    assert _turns(fake) == []


@pytest.mark.usefixtures("box")
def test_finish_lab_4_approves_executes_and_proves_the_same_key_replay(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    repo = _scratch_repo(tmp_path)
    commands = Commands()
    assert _finish(fake, 4, repo, commands) == 0
    assert commands.ran == [
        "psql -f labs/04-govern/4B-credit-writer.sql",
        DEPLOY_RUN.format(repo=repo), "uv run scripts/lab4_check.py --task 4A",
        "uv run scripts/lab4_check.py --task 4B",
        "psql -f workshop/lab-4-absence.sql"]
    assert len(_turns(fake)) == 1
    assert [r["path"] for r in _operator(fake)] == [
        "/api/operator/reviews", "/api/operator/clients/CUST-JESSICA/investigate",
        "/api/operator/reviews/41/confirm", "/api/operator/reviews/41/execute",
        "/api/operator/reviews/41/execute"]
    out = capsys.readouterr().out
    assert "Nadia's approval and execution are done for you" in out
    assert "replayed with the same key credit-41-abc: no new row" in out


@pytest.mark.usefixtures("box")
def test_a_repeated_finish_lab_4_only_replays_the_existing_credit(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    fake.rail = lab_run.MANAGED
    fake.credited = True
    fake.reviews = [_review("approved", "PERMITTED")]
    repo = _scratch_repo(tmp_path)
    assert _finish(fake, 4, repo, Commands()) == 0
    assert _turns(fake) == [], "Jessica's request is not sent again"
    assert [r["path"] for r in _operator(fake)] == [
        "/api/operator/reviews", "/api/operator/reviews/41/execute"]


@pytest.mark.usefixtures("box")
def test_finish_lab_4_uses_an_open_handoff_before_investigating(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake.rail = lab_run.MANAGED
    monkeypatch.setattr(lab_run, "jessicas_handoff", lambda turn=None, review_id=None: True)
    assert _finish(fake, 4, _scratch_repo(tmp_path), Commands()) == 0
    assert _turns(fake) == []
    assert any(r["path"].endswith("/investigate") for r in _operator(fake))


@pytest.mark.usefixtures("box")
def test_finish_lab_4_pays_the_existing_approved_review_without_another_shopper_turn(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    fake.rail = lab_run.MANAGED
    fake.reviews = [_review("approved", "BLOCKED")]
    assert _finish(fake, 4, _scratch_repo(tmp_path), Commands()) == 0
    assert _turns(fake) == []
    assert [r["path"] for r in _operator(fake)] == [
        "/api/operator/reviews", "/api/operator/reviews/41/execute",
        "/api/operator/reviews/41/execute"]


@pytest.mark.usefixtures("box")
def test_finish_lab_4_fails_when_the_replay_writes_a_second_time(
    fake: FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.replay_writes_again = True
    repo = _scratch_repo(tmp_path)
    commands = Commands()
    assert _finish(fake, 4, repo, commands) == 1
    assert "was not a replay" in capsys.readouterr().err
    assert "uv run scripts/lab4_check.py --task 4A" not in commands.ran


def test_finish_is_a_lab_run_action(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        lab_run.main(["finish", "--lab", "1", "--task", "1A"])
    assert "--task goes with solution or send, not finish" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# fast-track: both local labs, with finish still available for either one
# ---------------------------------------------------------------------------


@pytest.fixture
def recovery_repo(tmp_path: Path) -> Path:
    """Synthetic task files exercise recovery without depending on answer contents."""
    entries = []
    for task in lab_run.TASKS:
        entry = {"alias": f"labs/0{task[0]}-example/{task}-example.py",
                 "source": f"work/{task}.py", "solution": f"answers/{task}.py"}
        for key, contents in (("source", "participant"), ("solution", "provided")):
            target = tmp_path / entry[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{contents} {task}\n")
        entries.append(entry)
    (tmp_path / "workshop").mkdir()
    (tmp_path / "workshop/participant-files.json").write_text(json.dumps(entries))
    return tmp_path


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("lab", [1, 2])
def test_finish_one_local_lab_leaves_every_other_lab_untouched(
    lab: int, fake: FakeBackend, recovery_repo: Path,
) -> None:
    assert _finish(fake, lab, recovery_repo, Commands()) == 0
    for task in lab_run.TASKS:
        contents = "provided" if task.startswith(str(lab)) else "participant"
        assert (recovery_repo / f"work/{task}.py").read_text() == f"{contents} {task}\n"
    assert {turn["auth"] for turn in _turns(fake)} == {
        "Bearer token-anna" if lab == 1 else "Bearer token-marco"}


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("partly_finished", [False, True])
def test_fast_track_finishes_both_labs_and_can_repeat_without_losing_backups(
    partly_finished: bool, fake: FakeBackend, recovery_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if partly_finished:
        lab_run.install_task("1A", recovery_repo, next_line=False)
    commands = Commands()
    expected = [RESTART, "uv run scripts/lab1_check.py --task 1A",
                "uv run scripts/lab1_check.py --task 1B",
                "psql -f labs/02-ground/2B-check-stock.sql",
                RESTART, "uv run scripts/lab2_check.py --task 2A",
                "uv run scripts/lab2_check.py --task 2B"]
    for attempt in (1, 2):
        lab_run.fast_track(lab_run.Backend(fake.url), lambda user: f"token-{user}",
                           run=commands, repo=recovery_repo)
        assert commands.ran == expected * attempt
        assert [turn["auth"] for turn in _turns(fake)] == [
            "Bearer token-anna", "Bearer token-anna",
            "Bearer token-marco", "Bearer token-marco"] * attempt
        for task in lab_run.TASKS:
            contents = "provided" if task[0] in "12" else "participant"
            assert (recovery_repo / f"work/{task}.py").read_text() == f"{contents} {task}\n"
        for lab in (1, 2):
            for entry in lab_run.solution_files(lab, recovery_repo):
                task = Path(entry["source"]).stem
                backup = recovery_repo / (entry["alias"] + ".bak")
                assert backup.read_text() == f"participant {task}\n"
                assert not Path(str(backup) + ".2").exists()
        assert "Fast track complete: all four checks passed" in capsys.readouterr().out


@pytest.mark.usefixtures("box")
def test_the_fast_track_counts_both_labs_steps_as_one_run(
    fake: FakeBackend, recovery_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    lab_run.fast_track(lab_run.Backend(fake.url), lambda user: f"token-{user}",
                       run=Commands(), repo=recovery_repo)
    out = capsys.readouterr().out
    assert _started(out, "Fast track step") == FINISH_STEPS[1] + FINISH_STEPS[2]
    assert "  11 steps, usually about " in out
    assert out.index("Lab 1: finish") < out.index("Fast track step 1/11")
    assert out.index("Lab 2: finish") < out.index("Fast track step 6/11")
    assert out.count("  Done in ") == 1


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("failure,lab_2_started", [
    (RESTART, False), ("lab1_check.py --task 1B", False),
    ("lab2_check.py --task 2A", True),
])
def test_fast_track_stops_before_later_steps_or_labs_on_failure(
    failure: str, lab_2_started: bool, fake: FakeBackend, recovery_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    commands = Commands(failing=failure)
    with pytest.raises(lab_run.LabRunError):
        lab_run.fast_track(lab_run.Backend(fake.url), lambda user: f"token-{user}",
                           run=commands, repo=recovery_repo)
    assert commands.ran[-1].endswith(failure)
    assert "uv run scripts/lab2_check.py --task 2B" not in commands.ran
    if not lab_2_started:
        for task in ("2A", "2B"):
            assert (recovery_repo / f"work/{task}.py").read_text() == f"participant {task}\n"
        assert not any(turn["auth"] == "Bearer token-marco" for turn in _turns(fake))
    assert "Fast track complete" not in capsys.readouterr().out


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("lab", [1, 2])
def test_a_local_lab_will_not_start_while_a_deploy_moves_pellier_onto_agentcore(
    lab: int, fake: FakeBackend, recovery_repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run.deploy_lock, "running_message",
                        lambda repo: "A deploy is already running: a deploy of your changes.")
    commands = Commands()
    refused = "(?s)A deploy is already running.*Nothing was changed"
    with pytest.raises(lab_run.LabRunError, match=refused):
        lab_run.finish(lab, lab_run.Backend(fake.url), lambda user: f"token-{user}",
                       run=commands, repo=recovery_repo)
    assert commands.ran == [] and _turns(fake) == []
    for task in lab_run.TASKS:
        assert (recovery_repo / f"work/{task}.py").read_text() == f"participant {task}\n"


def _env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, on_agentcore: bool) -> None:
    env = tmp_path / ".env"
    env.write_text(f"DB_HOST=x\nUSE_AGENTCORE_RUNTIME={str(on_agentcore).lower()}\n",
                   encoding="utf-8")
    monkeypatch.setattr(lab_run, "ENV_FILE", env)


ON_AGENTCORE = "(?s)runs in process, but Pellier is set to run on AgentCore.*Nothing was changed"


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("lab", [1, 2])
def test_a_local_lab_will_not_start_once_pellier_runs_on_agentcore(
    lab: int, fake: FakeBackend, recovery_repo: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After Lab 3's deploy, finish installed the answers, ran the SQL file and restarted the
    backend, and only then refused at its send step. It refuses before it changes anything."""
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    commands = Commands()
    with pytest.raises(lab_run.LabRunError, match=ON_AGENTCORE):
        lab_run.finish(lab, lab_run.Backend(fake.url), lambda user: f"token-{user}",
                       run=commands, repo=recovery_repo)
    assert commands.ran == [] and _turns(fake) == []
    for task in lab_run.TASKS:
        assert (recovery_repo / f"work/{task}.py").read_text() == f"participant {task}\n"


@pytest.mark.usefixtures("box")
def test_the_fast_track_will_not_start_once_pellier_runs_on_agentcore(
    fake: FakeBackend, recovery_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    commands = Commands()
    with pytest.raises(lab_run.LabRunError, match=ON_AGENTCORE):
        lab_run.fast_track(lab_run.Backend(fake.url), lambda user: f"token-{user}",
                           run=commands, repo=recovery_repo)
    assert commands.ran == [] and _turns(fake) == []
    assert "steps, usually about" not in capsys.readouterr().out
    for task in lab_run.TASKS:
        assert (recovery_repo / f"work/{task}.py").read_text() == f"participant {task}\n"


@pytest.mark.usefixtures("box")
def test_lab_3_still_starts_its_catch_up_from_the_local_agents(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lab 3's catch-up begins on the local agents and deploys: only a local lab is refused."""
    _env_file(tmp_path, monkeypatch, on_agentcore=False)
    repo = _scratch_repo(tmp_path)
    commands = Commands(failing="--mode participant")
    assert _finish(fake, 3, repo, commands) == 1
    assert commands.ran[-1] == DEPLOY_RUN.format(repo=repo)


@pytest.mark.parametrize("arguments,expected", [
    (["fast-track"], [1, 2]), (["finish", "--lab", "1"], [1]),
    (["finish", "--lab", "2"], [2]),
])
def test_cli_can_finish_either_local_lab_or_both(
    arguments: List[str], expected: List[int], monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(lab_run, "finish", lambda lab, *args, **kwargs: calls.append(lab))
    assert lab_run.main(arguments) == 0
    assert calls == expected


def test_fast_track_cli_returns_failure_without_starting_lab_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def fail_first(lab: int, *args: Any, **kwargs: Any) -> None:
        calls.append(lab)
        raise lab_run.LabRunError("check failed")

    monkeypatch.setattr(lab_run, "finish", fail_first)
    assert lab_run.main(["fast-track"]) == 1
    assert calls == [1]
    output = capsys.readouterr()
    assert "check failed" in output.err
    assert "Fast track complete" not in output.out


@pytest.mark.parametrize("options", [["--lab", "1"], ["--task", "1A"],
                                     ["--shopper-only"], ["--quiet"]])
def test_fast_track_rejects_options_that_would_change_its_scope(options: List[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        lab_run.main(["fast-track", *options])
    assert exc.value.code == 2


@pytest.mark.parametrize("action", ["solution", "send", "diff", "reset", "finish"])
def test_individual_actions_still_require_a_lab(action: str) -> None:
    with pytest.raises(SystemExit) as exc:
        lab_run.main([action])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# The live trace: each turn's steps, printed as they stream
# ---------------------------------------------------------------------------
RANKING = {"available": True, "filters": {"kept": 64, "of": 100}, "rows": [
    {"name": "Stoneware Pour-Over Set", "fts_rank": None, "vec_rank": 1, "rrf_score": 0.0164},
    {"name": "Ceramic Tumblers", "fts_rank": 17, "vec_rank": 2, "rrf_score": 0.0291},
    {"name": "Linen Napkins, Set of 4", "fts_rank": 12, "vec_rank": 18, "rrf_score": 0.0267},
    {"name": "Wabi-Sabi Bowl", "fts_rank": 13, "vec_rank": 4, "rrf_score": 0.0293},
    {"name": "Olive Wood Cutting Board", "fts_rank": 14, "vec_rank": 11, "rrf_score": 0.0276},
    {"name": "Stoneware Mugs, Set of 2", "fts_rank": 20, "vec_rank": 3, "rrf_score": 0.0284},
]}
ROUTE = {"type": "step", "id": "route", "label": "Understanding your request", "status": "done",
         "finding": "Sent to the Catalog agent: gift", "builder": {}}
STEPS = [
    ROUTE,
    {"type": "step", "id": "step-1", "label": "Searching the catalog in Aurora", "status": "running",
     "builder": {"tool": "search_products"}},
    {"type": "step", "id": "step-1", "label": "Searching the catalog in Aurora", "status": "done",
     "finding": "5 found from 64 that fit under $100 and in stock, candles left out",
     "builder": {"tool": "search_products", "duration_ms": 731, "ranking": RANKING}},
    {"type": "step", "id": "step-2", "label": "Reading your tickets", "status": "failed",
     "finding": "The ticket read was refused", "builder": {"duration_ms": 12}},
    ROUTE,
]


def test_send_marks_every_request_as_sent_from_the_terminal(fake: FakeBackend) -> None:
    assert _run(fake, 1) == 0
    assert all(turn["body"]["source"] == "terminal" for turn in _turns(fake))


def test_send_prints_each_turns_trace_as_it_streams(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = STEPS
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    out = capsys.readouterr().out
    lines = out.splitlines()

    assert [line for line in lines if "Router" in line and "Path" not in line] == [
        "          1 Router  Sent to the Catalog agent: gift"]
    assert ("          Path      Anna \u2192 Router \u2192 Catalog agent \u2192 search_products "
            "\u2192 Aurora (words + meaning)") in lines
    done = lines.index("          2 done    search_products  Searching the catalog in Aurora (731 ms): 5 "
                       "found from 64 that fit under $100 and")
    assert lines[done + 1] == "                    in stock, candles left out"
    assert "                    How it ranked" in lines
    assert "                    Requirements: kept 64 of 100 products" in lines
    rows = [line.strip() for line in lines if line.strip().startswith("│")]
    assert [cell.strip() for cell in rows[0].strip("│").split("│")] == [
        "#", "Product", "Full text", "Vector", "Fused score", "Rerank"]
    assert len(rows) == 6
    assert [cell.strip() for cell in rows[1].strip("│").split("│")] == [
        "1", "Stoneware Pour-Over Set", "–", "#1", "0.0164", "–"]
    assert "Stoneware Mugs" not in out
    assert "          3 failed  Reading your tickets (12 ms): The ticket read was refused" in lines
    assert out.count("Searching the catalog in Aurora") == 1
    assert "  + OK    Answered by the local agents" in out and "(turn " not in out
    assert any(line.strip().startswith("Path") and "Catalog agent" in line for line in lines)
    assert all(len(line) <= 120 for line in lines)


def test_each_request_says_what_is_sent_as_whom_to_where_and_from_which_file(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    """Participants send requests long before they see the store, so the terminal shows what
    the request is: the shopper's sentence, sent signed in as them, as Ask Pellier sends it."""
    fake.steps = STEPS
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    lines = capsys.readouterr().out.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("          Message"))
    end = next(index for index, line in enumerate(lines) if line.startswith("          As"))
    shown = " ".join(line[20:] for line in lines[start:end])
    [sent] = [turn["body"]["message"] for turn in _turns(fake)]
    assert shown == f'"{sent}"'
    assert lines[end] == "          As        Anna, signed in"
    to = " ".join(line.strip() for line in lines[end + 1:end + 4])
    to = " ".join(to.split())
    assert to.startswith("To The same request Ask Pellier sends when Anna types it.")
    assert 'shows it as "Sent from the terminal"' in to
    assert "data/scenarios.json" not in "\n".join(lines) and "chat/stream" not in "\n".join(lines)
    assert any(line.startswith("          1 Router") for line in lines)


def test_the_terminal_ranking_uses_the_stores_column_names_and_chip_words() -> None:
    """A terminal turn and the same turn in the store's Builder view must read alike."""
    panel = (REPO / "pellier/frontend/src/components/turn/RankingPanel.tsx").read_text("utf-8")
    headings = re.search(r"\{\[(.*?)\]\.map\(head =>", panel).group(1)
    assert [name for name, _ in lab_run.RANKING_COLUMNS] == re.findall(r"'([^']+)'", headings)
    for reason, words in lab_run.REMOVED.items():
        assert f"{reason}: n => `${{formatCount(n)}} {words}`" in panel
    assert "How it ranked" in panel and "Kept " in panel
    store_note = re.search(r"export function merchandisingNote.*?return `(.*?)`", panel, re.S).group(1)
    assert re.sub(r"\$\{[^}]*\}", "X", store_note) == re.sub(r"\{\w+\}", "X",
                                                             lab_run.MERCHANDISING_NOTE)


def test_a_ranking_row_shows_how_far_rerank_moved_it_and_its_similarity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lab_run._ranking_key = lab_run.RANKING_KEY
    lab_run._trace_ranking({"available": True, "method": "hybrid+rerank", "rrf_k": 60,
                            "rerank_pool": 15, "arms": {"full_text": 20, "vector": 20},
                            "filters": {"kept": 828, "of": 1000,
                                        "removed": {"budget": 86, "stock": 82, "exclusions": 4},
                                        "excluded": [{"value": "candle", "count": 4,
                                                      "noun": "candles"}]},
                            "rows": [{"name": "Tall Stoneware Vase", "fts_rank": 7, "vec_rank": 9,
                                      "similarity": 0.552, "rrf_score": 0.0283,
                                      "rerank_score": 0.62, "before": 6, "after": 2,
                                      "moved": 4}]})
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert lines[0] == "How it ranked"
    assert lines[1] == ("Requirements: kept 828 of 1,000 products; left out 86 over budget, 82 sold out, "
                        "4 candles")
    assert lines[2] == ("Full text 20, Vector 20; fused with RRF (k=60), then Cohere Rerank 3.5 "
                        "on the top 15")
    row = next(line for line in lines if "Tall Stoneware Vase" in line)
    assert [cell.strip() for cell in row.strip("│").split("│")] == [
        "2 ↑4", "Tall Stoneware Vase", "#7", "#9  0.55", "0.0283", "0.62"]
    key = " ".join(lines[lines.index(next(line for line in lines if line.startswith("└"))) + 1:])
    assert key == lab_run.RANKING_KEY


def test_a_row_a_declared_rule_moved_is_starred_and_named(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Anna's vase is put first after rerank by a declared rule; without the note its low rerank
    score at #1 reads as a broken ranking."""
    lab_run._ranking_key = ""
    lab_run._trace_ranking({"available": True, "method": "hybrid+rerank", "rrf_k": 60,
                            "merchandising": [{"rule_id": "merch.milestone-home-gift.v1",
                                               "product": "Tall Stoneware Vase", "from": 4,
                                               "to": 1}],
                            "rows": [{"name": "Tall Stoneware Vase", "fts_rank": 7,
                                      "vec_rank": None, "rrf_score": 0.0274,
                                      "rerank_score": 0.10, "before": 4, "after": 1, "moved": 3,
                                      "rule": "merch.milestone-home-gift.v1"}]})
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    row = next(line for line in lines if "Tall Stoneware Vase" in line and "│" in line)
    assert row.strip("│").split("│")[0].strip() == "1 ↑3*"
    note = " ".join(lines[lines.index(next(line for line in lines if line.startswith("└"))) + 1:])
    assert note == ("* Tall Stoneware Vase: moved from 4 to 1 after rerank by the declared "
                    "merchandising rule merch.milestone-home-gift.v1")


def test_send_names_a_retry_and_what_it_dropped(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    retry = dict(STEPS[2], builder={**STEPS[2]["builder"],
                                    "relaxation": {"steps": ["drop_tags"],
                                                   "dropped": ["gift", "slow", "home"]}})
    fake.steps = [STEPS[0], STEPS[1], retry, *STEPS[3:]]
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    lines = capsys.readouterr().out.splitlines()

    retry_at = lines.index("                    Too few matches, so Pellier tried again without the "
                           "words gift, slow, home")
    assert lines[retry_at + 1].lstrip() == "How it ranked"


def test_a_first_attempt_prints_no_retry_line(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = STEPS
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    assert "tried again" not in capsys.readouterr().out


def test_limits_that_left_nothing_out_say_so(capsys: pytest.CaptureFixture[str]) -> None:
    lab_run._trace_ranking({"available": True, "filters": {"kept": 1000, "of": 1000},
                            "rows": [{"name": "Sunday Morning Candle", "fts_rank": 3}]})
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert lines[1] == "Requirements: kept 1,000 of 1,000 products; no requirement left any out"


def test_only_the_first_send_explains_the_local_agents_and_the_ranking_key(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = STEPS
    assert _run(fake, 1, None, "--task", "1A", "--details") == 0
    first = capsys.readouterr().out
    assert "They run inside the Pellier app on this machine; Lab 3 moves them to AgentCore." in first
    assert "Reading the table: # is the final order" in " ".join(first.split())
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    later = capsys.readouterr().out
    assert "Answered by the local agents" in later and "They run inside" not in later
    assert "Reading the table" not in later and lab_run.RANKING_SHORT_KEY.split(".")[0] in later


def test_quiet_keeps_the_one_line_output(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = STEPS
    assert _run(fake, 1, None, "--quiet") == 0
    out = capsys.readouterr().out
    assert "Router" not in out and "How it ranked" not in out
    assert '  + OK    Anna: "' in out and "Answered by the local agents" in out
    assert "(turn " not in out
    assert all(turn["body"]["source"] == "terminal" for turn in _turns(fake))


LONG_ANSWER = (
    "Your records show we received both returns, the Reed Diffuser and the Waffle Bath Robe in "
    "Sage, but the refund has not been issued yet. A person from the team will look at it today "
    "and reply to you by email with what they find.\n"
    "\n"
    "- The Reed Diffuser was received on 2 November.\n"
    "- The Waffle Bath Robe was received on 3 November."
)


def _answer_block(out: str) -> List[str]:
    """The first answer as printed: its labelled line and the lines hung under it."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith(lab_run.TRACE_INDENT + "Pellier: "))
    hang = lab_run.TRACE_INDENT + " " * len("Pellier: ")
    block = [lines[start]]
    for line in lines[start + 1:]:
        if not line.startswith(hang):
            break
        block.append(line)
    return block


def test_a_traced_send_prints_pelliers_whole_answer(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer used to be cut to one line ending "...", so the terminal hid what Pellier said."""
    fake.steps = STEPS
    fake.reply = LONG_ANSWER
    monkeypatch.setattr(lab_run.check, "terminal_width", lambda: 100)
    assert _run(fake, 1) == 0
    block = _answer_block(capsys.readouterr().out)
    assert all(len(line) <= 100 for line in block), block
    words = " ".join(line.strip() for line in block).removeprefix("Pellier: ")
    assert words.split() == LONG_ANSWER.split()
    assert not block[-1].endswith("...")
    hang = lab_run.TRACE_INDENT + " " * len("Pellier: ")
    assert hang + "- The Reed Diffuser was received on 2 November." in block
    assert hang + "- The Waffle Bath Robe was received on 3 November." in block


@pytest.mark.parametrize("quiet", [(), ("--quiet",)])
def test_a_send_prints_bold_words_as_the_shopper_reads_them(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    quiet: tuple,
) -> None:
    """Ask Pellier renders **bold**; the terminal printed the asterisks around it."""
    fake.steps = STEPS
    fake.reply = "The **Ceramic Tumblers** are my top pick at **$34**, 2 * 17 for the pair."
    monkeypatch.setattr(lab_run.check, "terminal_width", lambda: 100)
    assert _run(fake, 1, None, *quiet) == 0
    words = " ".join(line.strip() for line in _answer_block(capsys.readouterr().out))
    assert words == "Pellier: The Ceramic Tumblers are my top pick at $34, 2 * 17 for the pair."


@pytest.mark.parametrize("reply", ["A lone ** stays as written.", "2 ** 3 and 4 ** 5 are not bold.",
                                   "** spaced inside** is not bold either."])
def test_asterisks_markdown_does_not_render_as_bold_stay(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    reply: str,
) -> None:
    """Only a run Ask Pellier shows in bold loses its asterisks: CommonMark's flanking rule."""
    fake.steps = STEPS
    fake.reply = reply
    monkeypatch.setattr(lab_run.check, "terminal_width", lambda: 100)
    assert _run(fake, 1) == 0
    words = " ".join(line.strip() for line in _answer_block(capsys.readouterr().out))
    assert words == f"Pellier: {reply}"


def test_a_quiet_send_keeps_the_answer_to_one_line(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake.steps = STEPS
    fake.reply = LONG_ANSWER
    monkeypatch.setattr(lab_run.check, "terminal_width", lambda: 100)
    assert _run(fake, 1, None, "--quiet") == 0
    block = _answer_block(capsys.readouterr().out)
    assert len(block) == 1 and block[0].endswith("...") and len(block[0]) <= 100, block


def test_next_commands_print_whole_on_their_own_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """A terminal about 124 columns wide split "--mode participant" as "--mo" / "de participant".

    Each next command now sits whole on its own line, so a participant who copies it from the
    terminal gets the complete command.
    """
    repo = _scratch_repo(tmp_path)
    lab_run.install_task("3A", repo, restart=_restarts())
    lines = capsys.readouterr().out.splitlines()
    nexts = lines[[i for i, line in enumerate(lines) if line.startswith("  Next  ")][0]:]
    assert nexts[0] == '  Next  In the guide, open Task 3A and read "Prove the fix".'
    assert nexts[1] == "        Then run: uv run scripts/lab3_check.py --task 3A"
    assert nexts[2] == "        Then run: " + lab_run.DEPLOY
    assert all(len(line) <= 120 for line in nexts)


def test_a_managed_lab_refuses_before_sending_when_env_selects_in_process(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before the Lab 3 deploy, send --lab 3 used to run Theo's first request, then refuse.

    The rail is read from the .env the backend loads, so the refusal comes before any model call,
    and each command in it sits whole on its own line.
    """
    env = tmp_path / ".env"
    env.write_text("DB_HOST=x\nUSE_AGENTCORE_RUNTIME=false\n", encoding="utf-8")
    monkeypatch.setattr(lab_run, "ENV_FILE", env)
    assert _run(fake, 3) == 1
    err = capsys.readouterr().err
    assert _turns(fake) == []
    assert any(line.strip() == lab_run.DEPLOY for line in err.splitlines())
    assert any(line.strip() == "bash scripts/lab3-start.sh theo" for line in err.splitlines())
    assert all(len(line) <= 120 for line in err.splitlines())


def test_the_rail_precheck_is_skipped_when_env_cannot_be_read(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run, "ENV_FILE", tmp_path / "missing.env")
    fake.rail = lab_run.MANAGED
    assert _run(fake, 3) == 0


def test_a_catch_up_command_relays_its_output_through_this_process(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """finish draws a bar below its commands, so their lines must come through this process."""
    child = "import sys; print('Lab 1A check passed'); print('a warning', file=sys.stderr)"
    result = lab_run.relayed([sys.executable, "-c", child])
    out, err = capsys.readouterr()
    assert result.returncode == 0
    assert out == "Lab 1A check passed\n" and err == "a warning\n"
    assert lab_run.relayed([sys.executable, "-c", "raise SystemExit(3)"]).returncode == 3


# ---------------------------------------------------------------------------
# send restarts Pellier itself when a lab Python file was saved after it started
# ---------------------------------------------------------------------------

STARTED = datetime(2026, 11, 11, 1, 0, tzinfo=timezone.utc)


def _saved_at(path: Path, moment: datetime) -> None:
    os.utime(path, (moment.timestamp(), moment.timestamp()))


def _aged(repo: Path, moment: datetime) -> None:
    for entry in json.loads((repo / "workshop/participant-files.json").read_text("utf-8")):
        if (repo / entry["source"]).exists():
            _saved_at(repo / entry["source"], moment)


def test_a_backend_file_saved_after_the_start_is_named(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    _aged(repo, STARTED - timedelta(hours=1))
    _saved_at(repo / "pellier/backend/services/search_plan.py", STARTED + timedelta(seconds=5))
    assert lab_run.edited_after_start(STARTED, repo) == "1B-search-plan.py"


def test_nothing_is_named_when_every_file_is_older_or_the_start_is_unknown(
    tmp_path: Path,
) -> None:
    repo = _scratch_repo(tmp_path)
    _aged(repo, STARTED - timedelta(hours=1))
    assert lab_run.edited_after_start(STARTED, repo) is None
    _saved_at(repo / "pellier/backend/services/search_plan.py", STARTED + timedelta(seconds=5))
    assert lab_run.edited_after_start(None, repo) is None


def test_a_saved_sql_or_cedar_file_needs_no_restart(tmp_path: Path) -> None:
    """SQL takes effect when it commits and Cedar when it deploys; the app serves neither."""
    repo = _scratch_repo(tmp_path)
    _aged(repo, STARTED - timedelta(hours=1))
    for name in ("workshop/lab-2-check-stock.sql", "policies/credit_limit.cedar"):
        _saved_at(repo / name, STARTED + timedelta(seconds=5))
    assert lab_run.edited_after_start(STARTED, repo) is None


@pytest.fixture
def restarts(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """The service restart is systemd's; record each request for one and why."""
    calls: List[str] = []

    def restart(backend: Any, reason: str = "") -> None:
        calls.append(reason)

    monkeypatch.setattr(lab_run, "restart_backend", restart)
    monkeypatch.setattr(lab_run.check, "service_start_time", lambda: STARTED)
    return calls


def test_send_restarts_pellier_before_a_request_when_the_edit_is_newer(
    fake: FakeBackend, restarts: List[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run, "edited_after_start",
                        lambda started, repo=None: "1B-search-plan.py" if started else None)
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    assert len(restarts) == 1 and "1B-search-plan.py" in restarts[0]
    assert _turns(fake), "the request still goes out after the restart"


def test_send_does_not_restart_pellier_when_nothing_changed(
    fake: FakeBackend, restarts: List[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run, "edited_after_start", lambda started, repo=None: None)
    assert _run(fake, 1, None, "--task", "1B", "--details") == 0
    assert restarts == []


def test_a_lab_on_agentcore_never_restarts_the_local_app(
    fake: FakeBackend, restarts: List[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """From Lab 3 the agents run on AgentCore; a deploy, not a restart, ships an edit."""
    monkeypatch.setattr(lab_run, "edited_after_start",
                        lambda started, repo=None: "3A-2-bind-caller.py")
    fake.rail = lab_run.MANAGED
    assert _run(fake, 3) == 0
    assert restarts == []


@pytest.fixture
def stubbed_actions(monkeypatch) -> List[str]:
    """Every lab_run action as a stub: on a regression of the flag guards, the real ones would
    install solutions or reset labs in this checkout."""
    called: List[str] = []
    for name in ("finish", "send", "install_solution", "install_task", "show_diff",
                 "fast_track", "restart_backend"):
        monkeypatch.setattr(lab_run, name, lambda *a, _n=name, **k: called.append(_n) or 0)
    monkeypatch.setattr(lab_run.lab_reset, "reset_lab",
                        lambda *a, **k: called.append("reset_lab") or 0)
    return called


@pytest.mark.parametrize("argv", [
    ["finish", "--lab", "4", "--shopper-only"],
    ["solution", "--lab", "4", "--shopper-only"],
    ["reset", "--lab", "4", "--shopper-only"],
    ["diff", "--lab", "4", "--shopper-only"],
    ["send", "--lab", "3", "--shopper-only"],
])
def test_shopper_only_is_refused_outside_send_lab_4(argv, capsys, stubbed_actions) -> None:
    """finish --lab 4 would approve and execute Jessica's credit; the flag must not be ignored."""
    with pytest.raises(SystemExit):
        lab_run.main(argv)
    assert "--shopper-only goes with send --lab 4" in capsys.readouterr().err
    assert stubbed_actions == []


@pytest.mark.parametrize("action", ["finish", "solution", "reset", "diff"])
def test_quiet_is_refused_outside_send(action, capsys, stubbed_actions) -> None:
    with pytest.raises(SystemExit):
        lab_run.main([action, "--lab", "2", "--quiet"])
    assert "--quiet goes with send" in capsys.readouterr().err
    assert stubbed_actions == []


# ---------------------------------------------------------------------------
# local: the participant's own choice to go back to the local agents
# ---------------------------------------------------------------------------

class _SwitchCommands:
    """Records what `local` runs; the helper writes the setting as the real one does."""

    def __init__(self, env: Path, writes: bool = True, helper_status: int = 0,
                 helper_says: str = "  [PASS] Execution rail restored to in-process\n") -> None:
        self.env, self.writes, self.helper_status = env, writes, helper_status
        self.helper_says = helper_says
        self.ran: List[str] = []

    def __call__(self, argv: List[str], **kwargs: Any) -> Any:
        self.ran.append(" ".join(argv))
        status, said = 0, ""
        if argv[-2:-1] and argv[-2].endswith("reset-agentcore-lab.sh"):
            status, said = self.helper_status, self.helper_says
            if self.writes and status == 0:
                self.env.write_text("DB_HOST=x\nUSE_AGENTCORE_RUNTIME=false\n", encoding="utf-8")
        return lab_run.subprocess.CompletedProcess(argv, status, stdout=said, stderr="")


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("on_agentcore", [True, False])
def test_local_puts_pellier_on_the_local_agents_from_either_mode(
    on_agentcore: bool, fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One command writes the setting, restarts the backend and says where Pellier now runs."""
    _env_file(tmp_path, monkeypatch, on_agentcore=on_agentcore)
    fake.health_fields = {"use_agentcore_runtime": False}
    commands = _SwitchCommands(tmp_path / ".env")
    lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    helper = f"bash {tmp_path / 'scripts' / 'reset-agentcore-lab.sh'} 1"
    assert commands.ran == [helper, "sudo -n systemctl restart pellier"]
    assert [request["path"] for request in fake.requests] == ["/api/health"]
    assert lab_run._configured_rail() == lab_run.IN_PROCESS
    out = capsys.readouterr().out
    assert "Pellier is running on the local agents" in out
    assert "bash scripts/lab3-start.sh theo" in out  # the way back to AgentCore
    # The helper's reset wording stays out of what the participant reads.
    assert "rail" not in out and "USE_AGENTCORE_RUNTIME" not in out


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("health_fields", [
    {"use_agentcore_runtime": True}, {}, {"use_agentcore_runtime": "false"},
])
def test_local_requires_the_restarted_backend_to_confirm_local_mode(
    health_fields: Dict[str, Any], fake: FakeBackend, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    fake.health_fields = health_fields
    commands = _SwitchCommands(tmp_path / ".env")
    with pytest.raises(lab_run.LabRunError, match="did not confirm"):
        lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    assert lab_run._configured_rail() == lab_run.IN_PROCESS
    assert [request["path"] for request in fake.requests] == ["/api/health"]
    assert "Pellier is running on the local agents" not in capsys.readouterr().out


@pytest.mark.usefixtures("box")
def test_local_does_not_claim_the_switch_when_the_setting_did_not_change(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    commands = _SwitchCommands(tmp_path / ".env", writes=False)
    with pytest.raises(lab_run.LabRunError, match="still set to run on AgentCore"):
        lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    assert "sudo -n systemctl restart pellier" not in commands.ran
    assert "running on the local agents" not in capsys.readouterr().out


@pytest.mark.usefixtures("box")
def test_local_stops_when_the_setting_could_not_be_written(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    commands = _SwitchCommands(tmp_path / ".env", helper_status=1)
    with pytest.raises(lab_run.LabRunError, match="(?s)not changed.*Nothing was restarted"):
        lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    assert len(commands.ran) == 1


@pytest.mark.usefixtures("box")
def test_local_will_not_switch_while_a_deploy_is_moving_pellier_onto_agentcore(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    monkeypatch.setattr(lab_run.deploy_lock, "running_message",
                        lambda repo: "A deploy is already running: a deploy of your changes.")
    commands = _SwitchCommands(tmp_path / ".env")
    with pytest.raises(lab_run.LabRunError,
                       match="(?s)A deploy is already running.*Nothing was changed"):
        lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    assert commands.ran == []


@pytest.mark.usefixtures("box")
def test_local_checks_the_lab_files_before_it_writes_the_setting(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A syntax error stops the restart. Found after the write, it would leave Pellier set to
    the local agents and still answering from AgentCore."""
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    monkeypatch.setattr(lab_run, "python_edit_problem", lambda: "store_tools.py line 3: invalid")
    commands = _SwitchCommands(tmp_path / ".env")
    with pytest.raises(lab_run.LabRunError, match="(?s)line 3: invalid.*Nothing was changed"):
        lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    assert commands.ran == [] and lab_run._configured_rail() == lab_run.MANAGED


@pytest.mark.usefixtures("box")
def test_local_says_so_when_no_settings_file_was_found(
    fake: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _SwitchCommands(tmp_path / ".env", writes=False,
                               helper_says="  [WARN] No env file found at /etc/x or /repo/.env\n")
    with pytest.raises(lab_run.LabRunError, match="(?s)No settings file.*nothing was restarted"):
        lab_run.switch_to_local(lab_run.Backend(fake.url), run=commands, repo=tmp_path)
    assert len(commands.ran) == 1


def test_local_takes_no_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        lab_run.main(["local", "--lab", "1"])
    assert "local takes no options" in capsys.readouterr().err


@pytest.mark.usefixtures("box")
@pytest.mark.parametrize("lab", [1, 2])
def test_the_refusal_on_agentcore_names_the_one_command_and_no_file_edit(
    lab: int, fake: FakeBackend, recovery_repo: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A catch-up on AgentCore still stops before it changes anything; going back is one command."""
    _env_file(tmp_path, monkeypatch, on_agentcore=True)
    commands = Commands()
    with pytest.raises(lab_run.LabRunError) as refused:
        lab_run.finish(lab, lab_run.Backend(fake.url), lambda user: f"token-{user}",
                       run=commands, repo=recovery_repo)
    text = str(refused.value)
    assert "uv run scripts/lab_run.py local" in text and "Nothing was changed." in text
    assert "USE_AGENTCORE_RUNTIME" not in text and ".env" not in text
    assert commands.ran == [] and _turns(fake) == []


# ---------------------------------------------------------------------------
# Task 1A's first send: Anna's question and what each half of the search found
# ---------------------------------------------------------------------------
ARMS_STEP = {"type": "step", "id": "step-1", "label": "Searching the catalog in Aurora",
             "status": "done", "finding": "5 found",
             "builder": {"tool": "search_products", "duration_ms": 731,
                         "ranking": {**RANKING, "arms": {"full_text": 20, "vector": 0,
                                                         "fused": 20}}}}


def test_the_first_send_shows_only_the_question_the_counts_the_lookup_and_one_next_step(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [ROUTE, ARMS_STEP]
    assert _run(fake, 1, None, "--task", "1A") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[2:] == [
        "Anna: \u201cA housewarming gift for a friend who loves slow mornings.\u201d",
        "Full text (words)      20 top candidates",
        "Vector (meaning)        0 top candidates",
        "",
        "Storefront products closest to the Stoneware Pour-Over Set",
        "0 products returned.",
        "",
        'Next  In the guide, open Task 1A and read "Find the line and apply the provided fix".',
        "      Then run: uv run scripts/lab_run.py solution --lab 1 --task 1A"]
    shown = "\n".join(lines)
    for hidden in ("How it ranked", "Reading the table", "Router", "Path", "Pellier: ",
                   "the backend is healthy", "Sent from the terminal"):
        assert hidden not in shown, hidden


def test_a_count_the_turn_did_not_report_stays_unknown(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [ROUTE, {**ARMS_STEP, "builder": {**ARMS_STEP["builder"], "ranking": {
        **RANKING, "arms": {"full_text": 20}}}}]
    assert _run(fake, 1, None, "--task", "1A") == 0
    lines = capsys.readouterr().out.splitlines()
    assert "Full text (words)      20 top candidates" in lines
    assert "Vector (meaning)       unknown" in lines
    fake.steps = [ROUTE]
    assert _run(fake, 1, None, "--task", "1A") == 0
    lines = capsys.readouterr().out.splitlines()
    assert "Full text (words)      unknown" in lines and "Vector (meaning)       unknown" in lines


def test_details_prints_the_first_sends_whole_trace(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [ROUTE, ARMS_STEP]
    assert _run(fake, 1, None, "--task", "1A", "--details") == 0
    out = capsys.readouterr().out
    assert "How it ranked" in out and "Full text 20, Vector 0" in out
    assert "Full text (words)" not in out


def test_details_help_names_both_compact_sends(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        lab_run.main(["--help"])
    assert exc.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "full trace and ranking table for Task 1A or 1B" in help_text


def test_details_goes_with_send_only() -> None:
    with pytest.raises(SystemExit) as exc:
        lab_run.main(["solution", "--lab", "1", "--details"])
    assert exc.value.code == 2


def _search(arms: Optional[Dict[str, Any]], **builder: Any) -> Dict[str, Any]:
    ranking = {**RANKING, "arms": arms} if arms is not None else None
    return {**ARMS_STEP, "builder": {**ARMS_STEP["builder"], "ranking": ranking, **builder}}


def _counts(out: str) -> List[str]:
    return [" ".join(line.split()) for line in out.splitlines()
            if line.startswith(("Full text (words)", "Vector (meaning)"))]


def test_a_resend_shows_the_counts_of_the_attempt_that_answered(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed attempt's search found 19 by words; the resend that answered found 6."""
    fake.chat_failures = [([ROUTE, _search({"full_text": 19, "vector": 3})], "model busy")]
    fake.steps = [ROUTE, _search({"full_text": 6, "vector": 0})]
    assert _run(fake, 1, None, "--task", "1A") == 0
    assert _counts(capsys.readouterr().out) == ["Full text (words) 6 top candidates",
                                                "Vector (meaning) 0 top candidates"]
    assert len(_turns(fake)) == 2


@pytest.mark.parametrize("answered, shown", [
    ({"full_text": 6}, ["Full text (words) 6 top candidates", "Vector (meaning) unknown"]),
    (None, ["Full text (words) unknown", "Vector (meaning) unknown"]),
])
def test_a_resend_never_borrows_a_count_from_the_attempt_that_failed(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], answered: Any, shown: List[str],
) -> None:
    fake.chat_failures = [([ROUTE, _search({"full_text": 19, "vector": 3})], "model busy")]
    fake.steps = [ROUTE, _search(answered)]
    assert _run(fake, 1, None, "--task", "1A") == 0
    assert _counts(capsys.readouterr().out) == shown



# ---------------------------------------------------------------------------
# Task 1B's send: whether Pellier broadened Anna's search, and one next action
# ---------------------------------------------------------------------------
RETRY = {"steps": ["drop_soft_tags"], "dropped": ["gift", "slow", "home"]}
KEPT = {"applied": ["in stock", "$100 or less", "no candles"], "carried": []}


def _send_1b(fake: FakeBackend, capsys: pytest.CaptureFixture[str], *extra: str) -> List[str]:
    assert _run(fake, 1, None, "--task", "1B", *extra) == 0
    return capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("edited, told, command", [
    (False, "Pellier broadened Anna\u2019s search. Check which rules the retry kept.",
     "psql -f workshop/lab-1-receipt.sql"),
    (True, "Pellier broadened Anna\u2019s search. Check whether every gift still meets her "
     "rules.", "uv run scripts/lab1_check.py --task 1B"),
])
def test_a_retry_before_and_after_the_edit_names_the_next_proof(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    edited: bool, told: str, command: str,
) -> None:
    monkeypatch.setattr(lab_run.check, "region_state",
                        lambda *args: lab_run.check.EDITED if edited else lab_run.check.STARTER)
    fake.steps = [ROUTE, _search({"full_text": 20, "vector": 20}, relaxation=RETRY,
                                 requirements=None)]
    lines = _send_1b(fake, capsys)
    assert lines[-3:] == [
        "Anna: \u201cA housewarming gift for a friend who loves slow mornings. In stock, $100 or "
        "less, and no candles.\u201d", told, f"Next: {command}"]
    for hidden in ("How it ranked", "Router", "Pellier: ", "Too few matches"):
        assert hidden not in "\n".join(lines), hidden


@pytest.mark.parametrize("returned", [5, 0])
def test_a_confirmed_no_retry_reports_only_what_the_search_proves(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], returned: int,
) -> None:
    from services.turn_steps import TurnSteps

    plan = {"hard_constraints": {"price_max_usd": 100, "in_stock_only": True},
            "exclusions": ["candle"], "relaxations": []}
    result = {"status": "success", "count": returned, "products": [{"name": "Cup"}] * returned,
              "search_plan": plan}
    fake.steps = [ROUTE, TurnSteps().finished("search_products", result)]
    assert _send_1b(fake, capsys)[-2:] == [
        "No retry ran for this request. Send Anna\u2019s full request once more.",
        "Next: uv run scripts/lab_run.py send --lab 1 --task 1B"]


@pytest.mark.parametrize("unknown_first", [True, False])
@pytest.mark.parametrize("retry, expected", [
    (None, "Read Anna’s search receipt to see whether Pellier retried."),
    (RETRY, "Pellier broadened Anna’s search. Check which rules the retry kept."),
])
def test_1b_checks_all_searches_before_reporting_a_turn_outcome(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], unknown_first: bool,
    retry: Optional[Dict[str, Any]], expected: str,
) -> None:
    known = _search({"full_text": 5}, relaxation=retry, requirements=KEPT)
    unknown = _search(None)
    fake.steps = [ROUTE, unknown, known] if unknown_first else [ROUTE, known, unknown]
    assert _send_1b(fake, capsys)[-2:] == [expected, "Next: psql -f workshop/lab-1-receipt.sql"]


@pytest.mark.parametrize("steps", [
    [ROUTE],
    [ROUTE, {**ARMS_STEP, "builder": {"tool": "search_products", "relaxation": None,
                                      "requirements": None}}],
    [ROUTE, {**ARMS_STEP, "builder": {"tool": "search_products"}}],
])
def test_a_turn_that_cannot_say_whether_it_retried_sends_her_to_the_receipt(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], steps: List[Dict[str, Any]],
) -> None:
    """No search step, a step rebuilt from a managed turn, or a step without the field: a
    missing retry line alone cannot tell whether a retry ran."""
    fake.steps = steps
    assert _send_1b(fake, capsys)[-2:] == [
        "Read Anna\u2019s search receipt to see whether Pellier retried.",
        "Next: psql -f workshop/lab-1-receipt.sql"]


def test_the_1b_outcome_reads_only_the_attempt_that_answered(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.chat_failures = [([ROUTE, _search({"full_text": 20}, relaxation=RETRY)], "busy")]
    fake.steps = [ROUTE, _search({"full_text": 20}, relaxation=None, requirements=KEPT)]
    assert _send_1b(fake, capsys)[-2].startswith("No retry ran for this request.")


def test_details_prints_the_1b_trace_then_the_same_outcome(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [ROUTE, _search({"full_text": 20, "vector": 20}, relaxation=RETRY,
                                 requirements=None)]
    lines = _send_1b(fake, capsys, "--details")
    assert any("Too few matches, so Pellier tried again" in line for line in lines)
    assert any(line.strip() == "How it ranked" for line in lines)
    assert lines[-2].startswith("Pellier broadened Anna\u2019s search.")


def test_a_terminal_sees_red_for_none_green_for_some_and_orange_for_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run.check, "colour_enabled", lambda stream=None: True)
    evidence = lab_run.TurnEvidence()
    evidence.observe(_search({"full_text": 20, "vector": 0}))
    words, meaning = evidence.count_lines()
    assert "\033[32m" in words and "\033[31m" in meaning
    missing = lab_run.TurnEvidence()
    assert all("\033[38;5;208munknown" in line for line in missing.count_lines())
    told, _ = lab_run.after_1b_send(missing)
    assert told.startswith("\033[38;5;208m")


def test_a_quiet_1b_send_still_ends_with_its_outcome(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [ROUTE, _search({"full_text": 20}, relaxation=None, requirements=KEPT)]
    lines = _send_1b(fake, capsys, "--quiet")
    assert lines[-2].startswith("No retry ran for this request.")
    assert lines[-1] == "Next: uv run scripts/lab_run.py send --lab 1 --task 1B"


# ---------------------------------------------------------------------------
# Task 1A's send: Anna's counts, a blank line, then the separate reference lookup
# ---------------------------------------------------------------------------
lab1_vector = importlib.import_module("lab1_vector")


@pytest.mark.parametrize("found, shown", [
    (lab1_vector.Lookup(), ["0 products returned."]),
])
def test_one_1a_send_prints_the_counts_then_the_lookup_then_the_fix(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    found: Any, shown: List[str],
) -> None:
    monkeypatch.setattr(lab1_vector, "lookup", lambda: found)
    fake.steps = [ROUTE, ARMS_STEP]
    assert _run(fake, 1, None, "--task", "1A") == 0
    lines = capsys.readouterr().out.splitlines()
    start = lines.index("Anna: “A housewarming gift for a friend who loves slow mornings.”")
    assert lines[start + 1:start + 6 + len(shown)] == [
        "Full text (words)      20 top candidates",
        "Vector (meaning)        0 top candidates",
        "",
        "Storefront products closest to the Stoneware Pour-Over Set",
        *shown,
        ""]
    assert lines[start + 6 + len(shown)] == (
        'Next  In the guide, open Task 1A and read "Find the line and apply the provided fix".')
    assert "pgvector example" not in "\n".join(lines)
    [turn] = _turns(fake)
    assert turn["body"]["customer_id"] == "CUST-ANNA" and turn["body"]["source"] == "terminal"



def test_a_1a_send_whose_lookup_fails_exits_nonzero_and_sends_them_to_troubleshoot(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show the lookup failure and troubleshooting without guessing at the repair."""
    monkeypatch.setattr(lab1_vector, "lookup", lambda: lab1_vector.Lookup(
        error="the Stoneware Pour-Over Set has no stored embedding"))
    fake.steps = [ROUTE, ARMS_STEP]
    assert _run(fake, 1, None, "--task", "1A") == 1
    captured = capsys.readouterr()
    assert "Lookup failed: the Stoneware Pour-Over Set has no stored embedding" in captured.out
    told = " ".join(captured.err.split())
    assert "Troubleshoot with Claude Code or go deeper" in told and "Lookup failed line" in told
    assert "installing the fix cannot repair" not in told
    assert "Find the line and apply the provided fix" not in captured.out + captured.err


def test_the_1b_send_records_its_turn_for_the_check_and_the_receipt(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    record = tmp_path / "lab-1b-turn.json"
    fake.steps = [ROUTE]
    assert _run(fake, 1, None, "--task", "1B") == 0
    turn = _turns(fake)[-1]
    assert json.loads(record.read_text()) == {"session": turn["body"]["session_id"],
                                              "turn": f"turn-{len(fake.requests)}"}
    fake.chat_error = "unable to finish"
    assert _run(fake, 1, None, "--task", "1B") == 1
    assert record.read_text() == ""


def test_a_whole_lab_1_send_records_annas_full_request_not_her_first(
    fake: FakeBackend, tmp_path: Path,
) -> None:
    assert _run(fake, 1) == 0
    first, full = _turns(fake)
    assert json.loads((tmp_path / "lab-1b-turn.json").read_text())["session"] == (
        full["body"]["session_id"])
    assert "no candles" in full["body"]["message"] and "no candles" not in first["body"]["message"]


@pytest.mark.parametrize("stage", ["health", "sign-in", "switch shopper"])
def test_a_new_1b_send_supersedes_an_old_receipt_even_if_preparation_fails(
    fake: FakeBackend, stage: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = lab_run.check.lab1_retry_turn_path()
    path.write_text('{"turn":"old"}')

    def sign_in(user: str) -> str:
        if stage == "sign-in":
            raise lab_run.LabRunError("could not sign in")
        return f"token-{user}"

    if stage == "health":
        fake.health = "unhealthy"
    if stage == "switch shopper":
        def failed_switch(*args: Any) -> Any:
            raise lab_run.LabRunError("could not open the shopper session")
        monkeypatch.setattr(lab_run.Backend, "post_json", failed_switch)

    assert _run(fake, 1, sign_in, "--task", "1B") == 1
    assert path.read_text() == ""
    assert not _turns(fake)


def test_a_wrong_rail_refusal_preserves_the_previous_1b_record(fake: FakeBackend) -> None:
    path = lab_run.check.lab1_retry_turn_path()
    path.write_text('{"turn":"old"}')
    lab_run.ENV_FILE.write_text("USE_AGENTCORE_RUNTIME=true\n")
    assert _run(fake, 1, None, "--task", "1B") == 1
    assert path.read_text() == '{"turn":"old"}'
    assert not fake.requests


@pytest.mark.parametrize("extra", [("--task", "1B"), ()])
def test_a_slower_send_cannot_replace_a_newer_1b_record(
    fake: FakeBackend, extra: tuple[str, ...],
) -> None:
    """A second terminal finishes 1B while the first is still signing Anna in."""
    path = lab_run.check.lab1_retry_turn_path()
    newer = []

    def delayed_sign_in(user: str) -> str:
        assert _run(fake, 1, None, "--task", "1B") == 0
        newer.append(path.read_text())
        return f"token-{user}"

    assert _run(fake, 1, delayed_sign_in, *extra) == 0
    assert [path.read_text()] == newer



# ---------------------------------------------------------------------------
# An Apply install prints the changed lines as a diff reads: removed first, then added
# ---------------------------------------------------------------------------
def test_the_2a_install_lists_the_removed_tools_before_the_one_it_adds() -> None:
    [entry] = lab_run.task_files("2A")
    label, lines = lab_run.changed_code((REPO / entry["source"]).read_bytes(),
                                        (REPO / entry["solution"]).read_bytes())
    assert label == "Stock agent - definition"
    assert lines == ["    - _STOCK_TOOLS = [",
                     "    -     agent_tools.search_products,",
                     "    -     agent_tools.browse_department,",
                     "    -     agent_tools.compare_products,",
                     "    - ]",
                     "    + _STOCK_TOOLS = [agent_tools.check_stock]"]


# ---------------------------------------------------------------------------
# Task 2B's send: its own stock step decides what it says and what comes next
# ---------------------------------------------------------------------------
STOCK_ROUTE = {**ROUTE, "finding": "Sent to the Stock agent: in stock"}


def _stock(finding: str) -> Dict[str, Any]:
    return {"type": "step", "id": "step-1", "label": "Checking stock in three warehouses",
            "status": "done", "finding": finding, "builder": {"tool": "check_stock"}}


def _send_2b(fake: FakeBackend, capsys: pytest.CaptureFixture[str]) -> str:
    assert _run(fake, 2, None, "--task", "2B") == 0
    return capsys.readouterr().out


def test_a_corrected_cape_answer_shows_where_to_see_it_and_moves_on_to_lab_3(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [STOCK_ROUTE, _stock(lab_run.NOT_CARRIED)]
    out = _send_2b(fake, capsys)
    assert "The stock step now reads Not a piece Pellier carries." in out
    assert "Open the Pellier tab \u2192 Ask Pellier \u2192 Marco." in out
    assert 'open "From local agents to Amazon Bedrock AgentCore"' in out
    assert "lab2_check.py" not in out.split("Answered by the local agents")[-1]


@pytest.mark.parametrize("edited, told, command", [
    (False, "function still returns a row", "psql -f labs/02-ground/2B-check-stock.sql"),
    (True, "your saved file is not live yet", "psql -f labs/02-ground/2B-check-stock.sql"),
])
def test_a_sold_out_cape_points_to_the_build_or_to_running_the_saved_file(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    edited: bool, told: str, command: str,
) -> None:
    monkeypatch.setattr(lab_run.check, "region_state",
                        lambda *args: lab_run.check.EDITED if edited else lab_run.check.STARTER)
    fake.steps = [STOCK_ROUTE, _stock("Sold out in all three warehouses")]
    out = " ".join(_send_2b(fake, capsys).split())
    assert told in out and f"Then run: {command}" in out
    assert "See it in Pellier" not in out


def test_a_cape_answer_without_a_stock_step_asks_for_one_more_send(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = [STOCK_ROUTE]
    out = " ".join(_send_2b(fake, capsys).split())
    assert "answered without a stock step" in out
    assert "Then run: uv run scripts/lab_run.py send --lab 2 --task 2B" in out


@pytest.mark.parametrize("failure", ["resend", "tool failed"])
def test_the_answer_path_only_names_successful_tools_from_the_answering_attempt(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str], failure: str,
) -> None:
    fake.steps = [STOCK_ROUTE]
    if failure == "resend":
        fake.chat_failures = [([STOCK_ROUTE, _stock(lab_run.NOT_CARRIED)], "model busy")]
    else:
        fake.steps.append({**_stock("stock lookup failed"), "status": "failed"})

    out = _send_2b(fake, capsys)
    path = next(line for line in out.splitlines() if line.lstrip().startswith("Path "))
    assert path.split("Path", 1)[1].strip() == "Marco → Router → Stock agent"
    assert "answered without a stock step" in out
    if failure == "tool failed":
        assert "stock lookup failed" in out


def test_the_2b_ending_reads_only_the_attempt_that_answered(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.chat_failures = [([STOCK_ROUTE, _stock(lab_run.NOT_CARRIED)], "model busy")]
    fake.steps = [STOCK_ROUTE, _stock("Sold out in all three warehouses")]
    out = _send_2b(fake, capsys)
    assert "Not a piece Pellier carries." not in out.split("Answered by the local agents")[-1]
