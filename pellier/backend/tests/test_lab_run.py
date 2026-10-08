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
lab1_compare = importlib.import_module("lab1_compare")

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
            return {"assurance": {"policy": policy}, "idempotencyKey": "credit-41-abc",
                    "record": {"creditRows": 1 if policy == "ALLOW" else 0}}
        raise AssertionError(f"unexpected path {path}")

    def _turn(self, body: Dict[str, Any]) -> List[Any]:
        if self.chat_error:
            return [(None, {"type": "turn_start"}),
                    (None, {"type": "error", "error": self.chat_error})]
        response = {"response": f"Answer to {body['message']}", "rail": self.rail,
                    "turn_id": f"turn-{len(self.requests)}",
                    "railDecision": {"reason": "managed rail selected"}}
        return [(None, {"type": "turn_start"}), (None, {"type": "text", "text": "Ans"}),
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
            if isinstance(result, list):
                events = "".join((f"event: {name}\n" if name else "") + f"data: {json.dumps(data)}\n\n"
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


def _run(fake: FakeBackend, lab: int, token_for: Any = None) -> int:
    return lab_run.main(["send", "--lab", str(lab)], base_url=fake.url,
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
    assert lab_run.required_requests("anna", ("establish",)) == [lab1_compare.ANNA_REQUEST]


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
    assert len(lab_run.solution_files(3)) == 2


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
    assert turn["body"]["message"] == lab1_compare.ANNA_REQUEST


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
    assert "Cedar still denies review 41" in capsys.readouterr().err


def test_lab_4_reports_a_planner_that_proposed_nothing(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str],
) -> None:
    fake.rail = lab_run.MANAGED
    fake.proposal = None
    assert _run(fake, 4) == 1
    assert "the Planner proposed no credit for Jessica: no basis" in capsys.readouterr().err
