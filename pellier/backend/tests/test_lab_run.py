"""The catch-up command installs a lab's answers and makes its requests on the right path.

``scripts/lab_run.py`` backs each guide's "Short on time?" block. These tests
run it against a fake backend over real HTTP, so the SSE parsing, the persona
sessions, the rail check and the Operator sequence are exercised end to end
without AWS. The live behaviour is proved on a workshop box.
"""
from __future__ import annotations

import importlib
import json
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab_run = importlib.import_module("lab_run")
lab1_retry = importlib.import_module("lab1_retry")

PROPOSAL = {"reviewId": 41, "amount": "100.00", "orderIds": [7, 9], "actionHash": "a" * 64,
            "status": "pending"}


class FakeBackend:
    """What the fake server answers, and every request it received."""

    def __init__(self) -> None:
        self.rail = lab_run.IN_PROCESS
        self.health = "healthy"
        self.chat_error = ""
        self.proposal: Dict[str, Any] = dict(PROPOSAL)
        self.policies: List[str] = ["ALLOW"]
        self.requests: List[Dict[str, Any]] = []
        self.sessions = 0
        self.steps: List[Dict[str, Any]] = []

    def answer(self, path: str, body: Dict[str, Any]) -> Any:
        if path == "/api/health":
            return {"status": self.health}
        if path == "/api/persona/switch":
            self.sessions += 1
            return {"session_id": f"persona-{body['persona_id']}-{self.sessions:032x}"}
        if path == "/api/chat/stream":
            return self._turn(body)
        if path.endswith("/investigate"):
            answer = {"type": "answer", "proposal": self.proposal, "planner": "no basis"}
            return [("status", {"type": "status"}), ("step", {"type": "step"}),
                    ("answer", answer), ("complete", {**answer, "type": "complete"})]
        if path.endswith("/confirm"):
            return {"status": "approved"}
        if path.endswith("/execute"):
            policy = self.policies.pop(0) if len(self.policies) > 1 else self.policies[0]
            if policy == "502":
                return 502, {"detail": "gateway_unavailable:ReadTimeout"}
            return {"assurance": {"policy": policy}, "idempotencyKey": "credit-41-abc",
                    "notes": {"policy": "engine state unreadable"},
                    "record": {"creditRows": 1 if policy == "ALLOW" else 0}}
        raise AssertionError(f"unexpected path {path}")

    def _turn(self, body: Dict[str, Any]) -> List[Any]:
        if self.chat_error:
            return [(None, {"type": "turn_start"}),
                    (None, {"type": "error", "error": self.chat_error})]
        response = {"response": f"Answer to {body['message']}", "rail": self.rail,
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
                events = "".join(
                    (f"event: {name}\n" if name else "") + f"data: {json.dumps(data)}\n\n"
                    for name, data in result)
                self._send(200, "text/event-stream", events)
            else:
                self._send(200, "application/json", json.dumps(result))

        def _send(self, status: int, kind: str, text: str) -> None:
            payload = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

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
    backend = FakeBackend()
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


def test_annas_request_is_the_one_the_lab_1_check_asks_for() -> None:
    assert lab_run.required_requests("anna", ("establish",)) == [lab1_retry.ANNA_REQUEST]


def test_an_unknown_stage_names_what_is_missing() -> None:
    with pytest.raises(lab_run.LabRunError, match="no required anna request for encore"):
        lab_run.required_requests("anna", ("establish", "encore"))


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
        "1A-vector-branch.py", "1B-search-plan.py"]
    repo = _scratch_repo(tmp_path)
    (repo / "workshop/lab-1-fusion.sql").write_text("my fusion attempt\n")
    lab_run.install_solution(1, repo)
    assert (repo / "workshop/lab-1-fusion.sql").read_text() == "my fusion attempt\n"


def _scratch_repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "workshop", tmp_path / "workshop")
    for entry in json.loads((REPO / "workshop/participant-files.json").read_text("utf-8")):
        for key in ("source", "solution"):
            target = tmp_path / entry[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / entry[key], target)
    return tmp_path


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
    assert "sudo systemctl restart pellier" in first

    lab_run.install_solution(1, repo)
    assert "1B-search-plan.py already holds the solution" in capsys.readouterr().out


def test_solution_leaves_other_labs_untouched(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    marco = repo / "pellier/backend/services/agent_tools.py"
    marco.write_text("starter\n")
    lab_run.install_solution(1, repo)
    assert marco.read_text() == "starter\n"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def test_diff_shows_the_finished_lines_as_minus_and_the_participants_as_plus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _scratch_repo(tmp_path)
    lab_run.install_solution(2, repo)
    capsys.readouterr()
    entry = next(e for e in lab_run.solution_files(2, repo) if e["alias"].endswith("2B-stock-agent.py"))
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
    assert "2A-check-stock.py matches the solution" in out
    assert "python3 scripts/lab_run.py solution --lab 2" in out
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
    assert "4A-credit-policy.cedar matches the solution" in out
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


def test_lab_1_sends_annas_request_signed_in_on_her_persona_session(fake: FakeBackend) -> None:
    assert _run(fake, 1) == 0
    (turn,) = _turns(fake)
    assert turn["auth"] == "Bearer token-anna"
    assert turn["body"]["session_id"].startswith("persona-anna-")
    assert turn["body"]["customer_id"] == "CUST-ANNA"
    assert turn["body"]["message"] == lab1_retry.ANNA_REQUEST


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
    assert "USE_AGENTCORE_RUNTIME=false" in err


def test_a_managed_lab_refuses_an_in_process_turn(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(fake, 3) == 1
    assert "Run bash scripts/lab3-start.sh" in capsys.readouterr().err
    assert len(_turns(fake)) == 1


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


def test_an_http_error_names_the_path_and_the_detail(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(fake, 1, token_for=lambda user: "expired") == 1
    assert "/api/chat/stream answered HTTP 401: token_expired" in capsys.readouterr().err


def test_an_unhealthy_backend_stops_before_any_turn(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.health = "starting"
    assert _run(fake, 1) == 1
    assert "not healthy" in capsys.readouterr().err
    assert not _turns(fake)


def test_lab_4_has_nadia_approve_and_execute_the_proposed_credit(fake: FakeBackend) -> None:
    fake.rail = lab_run.MANAGED
    assert _run(fake, 4) == 0
    (jessica,) = _turns(fake)
    assert jessica["auth"] == "Bearer token-jessica"
    operator = [r for r in fake.requests if r["path"].startswith("/api/operator/")]
    assert [r["path"] for r in operator] == [
        "/api/operator/clients/CUST-JESSICA/investigate",
        "/api/operator/reviews/41/confirm",
        "/api/operator/reviews/41/execute"]
    assert operator[1]["body"] == {"actionHash": "a" * 64}
    assert {r["auth"] for r in operator} == {"Bearer token-nadia"}


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


def test_lab_4_reports_a_planner_that_proposed_nothing(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.proposal = None
    assert _run(fake, 4) == 1
    assert "the Planner proposed no credit for Jessica: no basis" in capsys.readouterr().err


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
         "finding": "Sent to the Shopping agent", "builder": {}}
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
    assert _run(fake, 1) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()

    assert '          Anna: "' in out
    assert [line for line in lines if "Router" in line] == [
        "          Router    Sent to the Shopping agent"]
    done = lines.index("          done      Searching the catalog in Aurora (731 ms): 5 found from 64 that "
                       "fit under $100 and in stock, candles")
    assert lines[done + 1] == "                    left out"
    assert "                    How it ranked, kept 64 of 100: full text, vector, fused" in lines
    rows = [line for line in lines if line.startswith("                    ") and "  #" in line]
    assert len(rows) == 5
    assert rows[0].split() == ["1", "Stoneware", "Pour-Over", "Set", "-", "#1", "0.0164"]
    assert "Stoneware Mugs" not in out
    assert "          failed    Reading your tickets (12 ms): The ticket read was refused" in lines
    assert out.count("Searching the catalog in Aurora") == 1
    assert "  + OK    ran in process (turn " in out
    assert all(len(line) <= 120 for line in lines)


def test_quiet_keeps_the_one_line_output(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.steps = STEPS
    assert _run(fake, 1, None, "--quiet") == 0
    out = capsys.readouterr().out
    assert "Router" not in out and "How it ranked" not in out
    assert '  + OK    Anna: "' in out and '" ran in process (turn ' in out
    assert all(turn["body"]["source"] == "terminal" for turn in _turns(fake))
