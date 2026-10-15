#!/usr/bin/env python3
"""Catch up on a lab: install its solution files, then send its requests.

The guide's "Running behind?" block chains these two commands with the lab's
restart or deployment and its checks:

    python3 scripts/lab_run.py solution --lab 1
    python3 scripts/lab_run.py send --lab 1

A task that opens with its own request sends just that one with ``--task``:

    python3 scripts/lab_run.py send --lab 1 --task 1A

``solution --task`` installs one task's answer and nothing else. It prints the change
from your file to the answer, keeps your file beside its editor link as ``.bak`` (a later,
different attempt as ``.bak.2`` and on, so none is overwritten), restarts the backend when a
backend file changed, and names the next command. A SQL or Cedar answer is only installed;
running the exercise or deploying is that next command:

    python3 scripts/lab_run.py solution --lab 1 --task 1A

``finish`` is a lab's "Running behind?" sequence as one command. It keeps your files as
``.bak`` (as ``solution --task`` does), puts the lab's answers in place, runs the lab's
exercise, restart or deploy, sends its requests and runs every check, stopping at the
first failure. Lab 4's finish also does Nadia's approval and execution in the Operator,
then proves the same-key replay. Run again, it never opens a second credit: an approved
review is finished rather than reopened, and a credited one is only replayed:

    python3 scripts/lab_run.py finish --lab 3

``reset`` puts one lab back to its as-shipped start, leaving the other labs alone: its
files, its database piece, its AgentCore state and the backend. It records a reset point so
the lab's checks ignore turns from before it (scripts/lab_reset.py has the detail):

    python3 scripts/lab_run.py reset --lab 2

A third action is for whoever is helping a stuck participant, and the guide
does not show it. ``diff`` prints what ``solution`` would change, without
changing it: a unified diff per task file, the finished version as '-' lines
and the participant's file as '+' lines.

    python3 scripts/lab_run.py diff --lab 2

``solution`` copies the lab's supplied answers over the files its tasks edit,
using the map in ``workshop/participant-files.json`` (the files the
``labs/0N-*/solution/`` folders link to). An entry marked ``optional`` is a Go
deeper exercise, not a task, so ``solution`` and ``diff`` leave it alone. It
neither restarts the backend nor deploys; the block's next command does that.

``send`` makes the lab's requests through the local backend, the way Ask
Pellier does: each shopper signs in as their Cognito test user and starts a
new conversation, and the requests are that lab's required ones in
``data/scenarios.json``. Every turn must run on the lab's path, in process for
Labs 1 and 2 and through AgentCore Runtime and Gateway for Labs 3 and 4. Lab 4
then does Nadia's part in the Operator: investigate Jessica's case, approve
the credit the Planner proposes, and execute it. A Cedar deployment takes a
few minutes to apply, so an execution that Cedar still denies, or that the
Gateway cannot yet answer, is retried. ``--shopper-only`` stops before
Nadia's part, so the participant makes that decision in the Operator; its last line is
Nadia's sign-in, read from the workshop's test-credentials file:

    python3 scripts/lab_run.py send --lab 4 --shopper-only

Each step prints ``+ OK`` or ``x FAIL``. The first failure stops the command
with exit status 1.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lab_reset  # noqa: E402  (sibling module)

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

IN_PROCESS, MANAGED = "in-process", "gateway-mcp"
RAIL_NAMES = {IN_PROCESS: "in process", MANAGED: "on AgentCore Runtime and Gateway"}
LAB_RAIL = {1: IN_PROCESS, 2: IN_PROCESS, 3: MANAGED, 4: MANAGED}

# Each lab's conversations, in order: the shopper and the journey stages of the
# required requests they send. Theo's ticket and household requests share one
# conversation because the second refers to the first.
CONVERSATIONS = {
    1: [("anna", ("establish",)), ("anna", ("exercise",))],
    2: [("marco", ("exercise", "prove"))],
    3: [("theo", ("establish",)), ("theo", ("exercise", "prove"))],
    4: [("jessica", ("establish",))],
}
# A task can open with its own request, sent alone with ``--task``; each builds on the one
# before. 1A is Anna's first sentence, whose ranking shows the vector branch, and 1B the same
# sentence with her limits, which needs the fallback. 2A is Marco's Brooklyn count, which
# only check_stock can answer, and 2B the cape Pellier never carried, which check_stock
# misreads once 2A connects it. 3A is Theo's ticket question on the managed starter, which
# cannot read tickets until get_tickets is published. Without ``--task`` a lab sends all of
# its requests, so the newest turn is still the one each check judges.
TASK_CONVERSATIONS = {
    "1A": [("anna", ("establish",))],
    "1B": [("anna", ("exercise",))],
    "2A": [("marco", ("prove",))],
    "2B": [("marco", ("exercise",))],
    "3A": [("theo", ("exercise",))],
}
DEPLOY = 'python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant'
TASKS = ("1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B")
PSQL = "psql -X -v ON_ERROR_STOP=1 -P pager=off -f"
# What proves each task once its answer is in place, naming files by their editor link.
NEXT_AFTER_TASK = {
    "1A": ["python3 scripts/lab1_check.py --task 1A"],
    "1B": ["python3 scripts/lab_run.py send --lab 1 --task 1B",
           "python3 scripts/lab1_check.py --task 1B"],
    "2A": ["python3 scripts/lab_run.py send --lab 2 --task 2A",
           "python3 scripts/lab2_check.py --task 2A"],
    "2B": [f"{PSQL} labs/02-ground/2B-check-stock.sql", "python3 scripts/lab2_check.py --task 2B"],
    "3A": ["python3 scripts/lab3_check.py --task 3A", DEPLOY],
    "3B": [f"{PSQL} labs/03-deploy/3B-row-ownership.sql"],
    "4A": ["python3 scripts/lab4_check.py --task 4A", DEPLOY],
    "4B": [f"{PSQL} labs/04-govern/4B-credit-writer.sql",
           "python3 scripts/lab4_check.py --task 4B"],
}
BACKEND_DIR = "pellier/backend/"
NEXT_AFTER_SOLUTION = {
    1: "restart the backend (sudo systemctl restart pellier), then send the lab's request.",
    2: ("run the Task 2B exercise (psql -X -v ON_ERROR_STOP=1 -P pager=off -f "
        "labs/02-ground/2B-check-stock.sql), restart the backend (sudo systemctl restart "
        "pellier), then send the lab's requests."),
    3: f"deploy the Task 3A files ({DEPLOY}), then send the lab's requests.",
    4: f"deploy the Cedar rule ({DEPLOY}), then send the lab's requests.",
}

OPERATOR = "nadia"
CREDIT_CLIENT = "CUST-JESSICA"
# Bootstrap writes each workshop user's throwaway sign-in here as "Username:" then "Password:".
CREDENTIALS_FILE = pathlib.Path(
    os.environ.get("PELLIER_TEST_CREDENTIALS", "/workshop/test-credentials.txt"))
POLICY_ALLOW, POLICY_DENY, POLICY_INCOMPLETE = "ALLOW", "DENY", "EVALUATION_INCOMPLETE"
HEALTH_WAIT_SECONDS = 120
POLICY_WAIT_SECONDS = 420
RETRY_SECONDS = 30
TURN_TIMEOUT_SECONDS = 300


class LabRunError(Exception):
    """A step failed. The message says what happened and what to do next."""


class BackendError(LabRunError):
    """The backend answered with an HTTP error."""

    def __init__(self, status: int, detail: str, path: str) -> None:
        super().__init__(f"{path} answered HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def ok(message: str) -> None:
    print(f"  + OK    {message}", flush=True)


def wait(message: str) -> None:
    print(f"  - WAIT  {message}", flush=True)


def fail(message: str) -> None:
    print(f"  x FAIL  {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# solution
# ---------------------------------------------------------------------------


def solution_files(lab: int, repo: pathlib.Path = REPO) -> List[Dict[str, str]]:
    """The task files whose editor alias sits in this lab's folder; Go deeper files are left out."""
    entries = json.loads((repo / "workshop" / "participant-files.json").read_text("utf-8"))
    mine = [entry for entry in entries
            if entry["alias"].startswith(f"labs/0{lab}-") and not entry.get("optional")]
    if not mine:
        raise LabRunError(f"workshop/participant-files.json lists no files for Lab {lab}")
    return mine


def install_solution(lab: int, repo: pathlib.Path = REPO) -> None:
    """Copy each of the lab's solution files over the file its task edits."""
    for entry in solution_files(lab, repo):
        target, answer = repo / entry["source"], repo / entry["solution"]
        if target.read_bytes() == answer.read_bytes():
            ok(f"{entry['alias']} already holds the solution")
            continue
        shutil.copyfile(answer, target)
        ok(f"{entry['alias']} now holds the solution ({entry['source']})")
    print(f"  Next: {NEXT_AFTER_SOLUTION[lab]}", flush=True)


def task_files(task: str, repo: pathlib.Path = REPO) -> List[Dict[str, str]]:
    """The files one task edits: its lab's entries whose editor link starts with the task."""
    mine = [entry for entry in solution_files(int(task[0]), repo)
            if pathlib.PurePosixPath(entry["alias"]).name.startswith(task)]
    if not mine:
        raise LabRunError(f"workshop/participant-files.json lists no file for Task {task}")
    return mine


def _print_change(alias: str, yours: bytes, answer: bytes) -> None:
    """The change the answer makes to the participant's file: their lines '-', the answer's '+'."""
    lines = difflib.unified_diff(
        yours.decode("utf-8", "replace").splitlines(keepends=True),
        answer.decode("utf-8", "replace").splitlines(keepends=True),
        fromfile=f"yours ({alias})", tofile=f"answer ({alias})")
    for line in lines:
        print(line.rstrip("\n"), flush=True)


def install_task(task: str, repo: pathlib.Path = REPO,
                 restart: Optional[Callable[[], None]] = None, next_line: bool = True) -> None:
    """Put one task's answer in place and keep every version it replaces beside it.

    Only the task's own files change, so a later task's work and evidence stay as they
    are. The first version is kept next to the editor link as ``<link>.bak``; a later,
    different attempt goes to ``<link>.bak.2`` and on, so no attempt is ever overwritten.
    ``restart`` runs when a backend file changed, because the app serves what it loaded.
    """
    backend_changed = False
    for entry in task_files(task, repo):
        alias = entry["alias"]
        target, answer = repo / entry["source"], repo / entry["solution"]
        yours, finished = target.read_bytes(), answer.read_bytes()
        if yours == finished:
            ok(f"{alias} already holds the answer")
            continue
        _print_change(alias, yours, finished)
        ok(_keep(repo, alias, yours))
        shutil.copyfile(answer, target)
        ok(f"{alias} now holds the answer")
        backend_changed = backend_changed or entry["source"].startswith(BACKEND_DIR)
    if backend_changed and restart is not None:
        restart()
    if next_line:
        print("  Next: " + ", then ".join(NEXT_AFTER_TASK[task]), flush=True)


def _keep(repo: pathlib.Path, alias: str, yours: bytes) -> str:
    """Save the participant's version beside the link unless a backup already holds it."""
    number = 1
    while True:
        name = f"{alias}.bak" if number == 1 else f"{alias}.bak.{number}"
        backup = repo / name
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(yours)
            return f"your version is kept in {name}"
        if backup.read_bytes() == yours:
            return f"your version is already kept in {name}"
        number += 1


def restart_backend(backend: "Backend", run: Callable[..., Any] = subprocess.run) -> None:
    """Restart the Pellier service the way the guide does, then wait until it is healthy."""
    if shutil.which("systemctl") is None:
        raise LabRunError("systemctl is not on this machine, so the backend was not restarted. "
                          "Restart it yourself, then run the next command.")
    command = (["systemctl", "restart", "pellier"] if os.geteuid() == 0
               else ["sudo", "-n", "systemctl", "restart", "pellier"])
    wait("restarting the backend so it serves the new code")
    if run(command, check=False).returncode != 0:
        raise LabRunError(f"{shlex.join(command)} failed. Restart the backend yourself "
                          "(sudo systemctl restart pellier), then run the next command.")
    wait_until_healthy(backend)


# ---------------------------------------------------------------------------
# diff: what `solution` would change, without changing it
# ---------------------------------------------------------------------------

DIFF_COLORS = {"---": "1", "+++": "1", "@@": "36", "-": "31", "+": "32"}


def _paint(line: str, color: bool) -> str:
    if not color:
        return line
    code = next((c for prefix, c in DIFF_COLORS.items() if line.startswith(prefix)), "")
    return f"\x1b[{code}m{line}\x1b[0m" if code else line


def show_diff(lab: int, repo: pathlib.Path = REPO, color: bool = False) -> int:
    """Print each task file's unified diff against its solution; return 1 if any differ.

    '-' lines are the finished version, the lines ``solution`` would write.
    '+' lines are the participant's file as it is now. Nothing is written.
    """
    differs = 0
    for entry in solution_files(lab, repo):
        expected = (repo / entry["solution"]).read_text("utf-8").splitlines(keepends=True)
        yours = (repo / entry["source"]).read_text("utf-8").splitlines(keepends=True)
        if expected == yours:
            ok(f"{entry['alias']} matches the solution")
            continue
        differs = 1
        lines = difflib.unified_diff(
            expected, yours,
            fromfile=f"expected (Lab {lab} solution: {entry['source']})",
            tofile=f"yours ({entry['source']})")
        for line in lines:
            print(_paint(line.rstrip("\n"), color), flush=True)
    if differs:
        print(f"'-' lines are the finished version: what 'python3 scripts/lab_run.py solution "
              f"--lab {lab}' would write.\n'+' lines are your file as it is now.", flush=True)
    return differs


# ---------------------------------------------------------------------------
# send: the backend, as the Storefront and the Operator call it
# ---------------------------------------------------------------------------


def _error_detail(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", "replace")
    try:
        detail = json.loads(body).get("detail", body)
    except (ValueError, AttributeError):
        return body.strip()[:300] or exc.reason
    return detail if isinstance(detail, str) else json.dumps(detail)


def sse_events(lines: Iterable[bytes]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Each server-sent event as (event name, data). Unnamed events are ``message``."""
    name, data = "message", []
    for raw in lines:
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("event:"):
            name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:"):].strip())
        elif not line:
            if data:
                yield name, _event_data(data)
            name, data = "message", []
    if data:
        yield name, _event_data(data)


def _event_data(data: List[str]) -> Dict[str, Any]:
    text = "\n".join(data)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise LabRunError(f"the backend sent an event that is not JSON: {text[:200]}") from exc


class Backend:
    """The local Pellier backend."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _open(self, path: str, body: Optional[Dict[str, Any]], token: Optional[str],
              timeout: float) -> Any:
        headers = {"Accept": "application/json, text/event-stream"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers)
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raise BackendError(exc.code, _error_detail(exc), path) from exc
        except OSError as exc:
            raise LabRunError(
                f"cannot reach {self.base_url}{path} ({exc}). Is the backend running? "
                "Check with: sudo systemctl status pellier") from exc

    def get_json(self, path: str, token: Optional[str] = None) -> Dict[str, Any]:
        with self._open(path, None, token, 10) as response:
            return json.loads(response.read())

    def post_json(self, path: str, body: Dict[str, Any], token: Optional[str] = None,
                  ) -> Dict[str, Any]:
        with self._open(path, body, token, TURN_TIMEOUT_SECONDS) as response:
            return json.loads(response.read())

    def stream(self, path: str, body: Dict[str, Any], token: str,
               ) -> Iterator[Tuple[str, Dict[str, Any]]]:
        with self._open(path, body, token, TURN_TIMEOUT_SECONDS) as response:
            yield from sse_events(response)


def wait_until_healthy(backend: Backend) -> None:
    """Wait for /api/health to report healthy, as after a restart."""
    deadline = time.monotonic() + HEALTH_WAIT_SECONDS
    last = ""
    while True:
        try:
            status = str(backend.get_json("/api/health").get("status") or "")
        except LabRunError as exc:
            status, last = "", str(exc)
        if status == "healthy":
            ok("the backend is healthy")
            return
        last = f"status {status!r}" if status else last
        if time.monotonic() >= deadline:
            raise LabRunError(f"the backend is not healthy after {HEALTH_WAIT_SECONDS} s "
                              f"({last}). Check with: journalctl -u pellier -n 50")
        time.sleep(2)


def required_requests(persona: str, stages: Sequence[str],
                      repo: pathlib.Path = REPO) -> List[str]:
    """The shopper's required requests for these journey stages, in this order."""
    scenarios = json.loads((repo / "data" / "scenarios.json").read_text("utf-8"))
    by_stage = {s["journey_stage"]: s["prompt"] for s in scenarios
                if s["persona"] == persona and s["journey_role"] == "required"}
    missing = [stage for stage in stages if stage not in by_stage]
    if missing:
        raise LabRunError(f"data/scenarios.json has no required {persona} request for "
                          f"{', '.join(missing)}")
    return [by_stage[stage] for stage in stages]


# The live trace: each step as Builder view shows it, printed as the turn streams.
TRACE_WIDTH = 120
TRACE_INDENT = " " * 10
TRACE_LABEL = 10
RANKING_ROWS = 5


def _trace_line(label: str, text: str) -> None:
    room = TRACE_WIDTH - len(TRACE_INDENT) - TRACE_LABEL
    lines = textwrap.wrap(text, width=room) or [""]
    print(f"{TRACE_INDENT}{label:<{TRACE_LABEL}}{lines[0]}", flush=True)
    for line in lines[1:]:
        print(f"{TRACE_INDENT}{'':<{TRACE_LABEL}}{line}", flush=True)


def _rank(value: Any) -> str:
    return "-" if value in (None, "") else f"#{value}"


def _trace_ranking(ranking: Dict[str, Any]) -> None:
    rows = ranking.get("rows") if ranking.get("available") else None
    if not rows:
        return
    filters = ranking.get("filters") or {}
    kept = (f", kept {filters['kept']} of {filters['of']}"
            if filters.get("kept") is not None and filters.get("of") is not None else "")
    pad = f"{TRACE_INDENT}{'':<{TRACE_LABEL}}"
    print(f"{pad}How it ranked{kept}: full text, vector, fused", flush=True)
    for index, row in enumerate(rows[:RANKING_ROWS], 1):
        name = _one_line(str(row.get("name") or row.get("product_id") or "?"), 34)
        score = float(row.get("rrf_score") or 0)
        print(f"{pad}{index:<3}{name:<35}{_rank(row.get('fts_rank')):>4}  "
              f"{_rank(row.get('vec_rank')):>4}  {score:.4f}", flush=True)


def trace_event(event: Dict[str, Any], shown: set) -> None:
    """Print a finished step once, in Builder view's words; running steps print nothing."""
    if event.get("type") != "step" or event.get("status") == "running":
        return
    step_id, status = str(event.get("id") or ""), str(event.get("status") or "done")
    if (step_id, status) in shown:
        return
    shown.add((step_id, status))
    label = str(event.get("label") or "")
    finding = str(event.get("finding") or "")
    builder = event.get("builder") or {}
    if step_id == "route":
        _trace_line("Router", finding or label)
        return
    ms = builder.get("duration_ms")
    timing = f" ({ms} ms)" if isinstance(ms, (int, float)) else ""
    _trace_line("failed" if status == "failed" else "done",
                f"{label}{timing}" + (f": {finding}" if finding else ""))
    _trace_ranking(builder.get("ranking") or {})


def send_turn(backend: Backend, token: str, body: Dict[str, Any],
              trace: bool = False) -> Dict[str, Any]:
    """One Ask Pellier turn; returns the complete event's response, printing its trace."""
    shown: set = set()
    for name, event in backend.stream("/api/chat/stream", body, token):
        if name == "error" or event.get("type") == "error":
            reason = event.get("error") or event.get("message") or json.dumps(event)
            raise LabRunError(f"the turn failed: {reason}")
        if trace:
            trace_event(event, shown)
        if event.get("type") == "complete":
            return event.get("response") or {}
    raise LabRunError("the turn ended without a complete event")


def _rail_problem(lab: int, served: str, response: Dict[str, Any]) -> str:
    wanted = LAB_RAIL[lab]
    decision = response.get("railDecision") or {}
    reason = decision.get("reason") or (response.get("degradation") or {}).get("reason")
    observed = f"this turn ran on {served or 'no reported path'}"
    observed += f" ({reason})" if reason else ""
    if wanted == IN_PROCESS:
        return (f"Lab {lab} runs in process, but {observed}. Lab 3's deploy has moved "
                "Pellier onto AgentCore, so this turn did not run the code you edited. To "
                "rerun it, set USE_AGENTCORE_RUNTIME=false in .env, restart the backend and "
                "rerun this command; bash scripts/lab3-start.sh theo moves it back.")
    return (f"Lab {lab} runs on AgentCore Runtime and Gateway, but {observed}. Lab 3's "
            f"deploy moves Pellier onto AgentCore: run {DEPLOY}. If that deploy already "
            "reported ready, run bash scripts/lab3-start.sh theo, then rerun this command.")


def _one_line(text: str, width: int = 140) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 3].rstrip() + "..."


def converse(backend: Backend, lab: int, token: str, persona: str,
             requests: Sequence[str], trace: bool = True) -> None:
    """Start a new conversation as this shopper and send the requests in order.

    Each request is marked as sent from the terminal, so the shopper's own Ask
    Pellier panel shows it live; with ``trace`` the steps print as they stream.
    """
    session = backend.post_json("/api/persona/switch", {"persona_id": persona})["session_id"]
    history: List[Dict[str, str]] = []
    for message in requests:
        if trace:
            print(f'{TRACE_INDENT}{persona.title()}: "{message}"', flush=True)
        response = send_turn(backend, token, {
            "message": message,
            "session_id": session,
            "customer_id": f"CUST-{persona.upper()}",
            "conversation_history": history,
            "source": "terminal",
        }, trace=trace)
        served = str(response.get("rail") or "")
        if served != LAB_RAIL[lab]:
            raise LabRunError(_rail_problem(lab, served, response))
        answer = str(response.get("response") or "")
        turn = f"(turn {response.get('turn_id') or '?'})"
        if trace:
            ok(f"ran {RAIL_NAMES[served]} {turn}")
        else:
            ok(f'{persona.title()}: "{message}" ran {RAIL_NAMES[served]} {turn}')
        print(f"{TRACE_INDENT}Pellier: {_one_line(answer, TRACE_WIDTH - 19)}", flush=True)
        history += [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]


# ---------------------------------------------------------------------------
# send, Lab 4: Nadia's part in the Operator
# ---------------------------------------------------------------------------


def nadias_sign_in(path: Optional[pathlib.Path] = None) -> str:
    """Nadia's Operator sign-in from the workshop credentials file, or where to get it."""
    path = path or CREDENTIALS_FILE
    try:
        lines = [line.strip() for line in path.read_text("utf-8").splitlines()]
    except OSError:
        return f"Nadia's sign-in: {path} is missing, so ask a facilitator for her password."
    for index, line in enumerate(lines[:-1]):
        password = lines[index + 1]
        if line.lower() == f"username: {OPERATOR}" and password.lower().startswith("password:"):
            return (f"Nadia's sign-in for the Operator: username {OPERATOR}, "
                    f"password {password.split(':', 1)[1].strip()}")
    return (f"Nadia's sign-in: {path} has no entry for {OPERATOR}, so ask a facilitator "
            "for her password.")


def investigate(backend: Backend, token: str, client: str) -> Dict[str, Any]:
    """Run the Operator's investigation; returns the Planner's proposal."""
    for name, event in backend.stream(f"/api/operator/clients/{client}/investigate", {}, token):
        if name == "error":
            raise LabRunError(f"the investigation failed: {event.get('detail') or event}")
        if name == "answer":
            proposal = event.get("proposal")
            if not proposal:
                raise LabRunError("the Planner proposed no credit for Jessica: "
                                  f"{event.get('planner') or event.get('status')}. Rerun this "
                                  "command, or investigate in the Operator to read the brief.")
            return proposal
    raise LabRunError("the investigation ended without an answer")


def approve(backend: Backend, token: str, proposal: Dict[str, Any]) -> None:
    """Approve the proposed credit, unless a person already has."""
    review, status = proposal["reviewId"], proposal.get("status")
    if status == "approved":
        ok(f"review {review} was already approved")
        return
    if status != "pending":
        raise LabRunError(f"review {review} is {status}; only a pending review can be approved")
    backend.post_json(f"/api/operator/reviews/{review}/confirm",
                      {"actionHash": proposal["actionHash"]}, token)
    ok(f"Nadia approved review {review}")


def _execute_once(backend: Backend, token: str, review: int,
                  ) -> Tuple[Optional[Dict[str, Any]], str]:
    """One execution: the payload when Policy allowed it, else why to try again."""
    try:
        payload = backend.post_json(f"/api/operator/reviews/{review}/execute", {}, token)
    except BackendError as exc:
        if exc.status == 502 and exc.detail.startswith("gateway_unavailable"):
            return None, f"the Gateway did not answer ({exc.detail})"
        raise
    policy = (payload.get("assurance") or {}).get("policy")
    if policy == POLICY_ALLOW:
        return payload, ""
    if policy == POLICY_DENY:
        return None, "Policy DENY; the deployed Cedar rule may still be applying"
    if policy == POLICY_INCOMPLETE:
        notes = json.dumps(payload.get("notes") or {})[:200]
        return None, f"Policy could not confirm enforcement yet ({notes})"
    raise LabRunError(f"Policy reported {policy} for review {review}: "
                      f"{json.dumps(payload.get('notes') or {})}")


def execute_until_allowed(backend: Backend, token: str, review: int) -> Dict[str, Any]:
    """Execute the approved credit, retrying while a new deployment settles.

    Each retry carries the review's idempotency key, so it cannot write a
    second credit.
    """
    deadline = time.monotonic() + POLICY_WAIT_SECONDS
    while True:
        payload, why = _execute_once(backend, token, review)
        if payload is not None:
            return payload
        if time.monotonic() >= deadline:
            raise LabRunError(
                f"review {review} has no Policy ALLOW after {POLICY_WAIT_SECONDS // 60} "
                f"minutes; last: {why}. Check Task 4A with python3 "
                "scripts/lab4_check.py --task 4A, deploy it, and rerun.")
        wait(f"{why}. Retrying in {RETRY_SECONDS} s.")
        time.sleep(RETRY_SECONDS)


def jessicas_reviews(backend: Backend, token: str) -> List[Dict[str, Any]]:
    """Jessica's credit reviews, newest first. The Lab 4 check's probe reviews are not hers."""
    reviews = backend.get_json("/api/operator/reviews", token).get("reviews") or []
    mine = [r for r in reviews
            if r.get("customerId") == CREDIT_CLIENT and not r.get("policyCheckProbe")]
    return sorted(mine, key=lambda r: int(r.get("reviewId") or 0), reverse=True)


def credited(review: Dict[str, Any]) -> bool:
    """An approved review whose key already holds a credit in Aurora."""
    return (review.get("status") == "approved"
            and (review.get("assurance") or {}).get("aurora") == "PERMITTED")


def settle_credit(backend: Backend, token: str,
                  reviews: Optional[List[Dict[str, Any]]] = None) -> int:
    """Nadia's part, at most once: return the review that holds Jessica's credit.

    A credited review is left as it is: nothing is investigated, approved or written. A
    live review is finished rather than reopened, an approved one before a pending one, so a
    person's own approval stands. A review a person rejected is not overruled. Only when
    Jessica has no review at all does Nadia investigate.
    """
    if reviews is None:
        reviews = jessicas_reviews(backend, token)
    done = next((r for r in reviews if credited(r)), None)
    if done is not None:
        ok(f"review {done['reviewId']} already credited Jessica; nothing is investigated, "
           "approved or written again")
        return int(done["reviewId"])
    live = (next((r for r in reviews if r.get("status") == "approved"), None)
            or next((r for r in reviews if r.get("status") == "pending"), None))
    if live is None and reviews:
        raise LabRunError(f"review {reviews[0]['reviewId']} was rejected, and this command does "
                          "not overrule a person's decision. To credit Jessica, investigate "
                          "Jessica's case in the Operator to open a new review, then run this "
                          "again.")
    proposal = live or investigate(backend, token, CREDIT_CLIENT)
    review = int(proposal["reviewId"])
    if live is not None:
        ok(f"review {review} is Jessica's open review; it is finished, not reopened")
    else:
        ok(f"Nadia investigated Jessica's case: review {review} proposes "
           f"${proposal.get('amount')} for orders {proposal.get('orderIds')}")
    approve(backend, token, proposal)
    payload = execute_until_allowed(backend, token, review)
    credits = (payload.get("record") or {}).get("creditRows")
    if credits != 1:
        raise LabRunError(f"review {review} executed with Policy ALLOW but Aurora holds "
                          f"{credits} credit rows for its key, not 1")
    ok(f"Policy ALLOW; Aurora holds one credit for key {payload.get('idempotencyKey')}")
    return review


def prove_replay(backend: Backend, token: str, review: int) -> None:
    """Execute the credited review again: the same key must find the first credit."""
    payload = execute_until_allowed(backend, token, review)
    replayed = bool((payload.get("result") or {}).get("idempotent_replay"))
    credits = (payload.get("record") or {}).get("creditRows")
    key = payload.get("idempotencyKey")
    if not replayed or credits != 1:
        raise LabRunError(f"executing review {review} again was not a replay: Aurora holds "
                          f"{credits} credit rows for key {key}. A same-key retry must find "
                          "the first credit and write nothing; check Task 4B.")
    ok(f"replayed with the same key {key}: no new row; Aurora still holds one credit")


def mint_token(username: str) -> str:
    """A Cognito access token for one workshop test user."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    from gateway_client import _load_env, _token_from_cognito

    _load_env()
    try:
        return _token_from_cognito(username)
    except Exception as exc:  # noqa: BLE001 - boto3 and Cognito errors, reported with the user
        raise LabRunError(f"could not sign in as {username}: {exc}") from exc


def send(lab: int, backend: Backend, token_for: Callable[[str], str] = mint_token,
         shopper_only: bool = False, trace: bool = True, task: Optional[str] = None) -> None:
    """Make the lab's requests on the lab's path, or one task's with ``task``, and for Lab 4
    do Nadia's part unless ``shopper_only``."""
    wait_until_healthy(backend)
    tokens: Dict[str, str] = {}
    for persona, stages in (TASK_CONVERSATIONS[task] if task else CONVERSATIONS[lab]):
        if persona not in tokens:
            tokens[persona] = token_for(persona)
        converse(backend, lab, tokens[persona], persona, required_requests(persona, stages),
                 trace=trace)
    if lab == 4 and shopper_only:
        print("  Next: as Nadia in the Operator, investigate Jessica's case, approve the "
              "proposed credit and select Execute.", flush=True)
        print(f"  {nadias_sign_in()}", flush=True)
    elif lab == 4:
        settle_credit(backend, token_for(OPERATOR))


# ---------------------------------------------------------------------------
# finish: the lab's "Running behind?" sequence as one command
# ---------------------------------------------------------------------------

EXERCISES = {2: "labs/02-ground/2B-check-stock.sql", 3: "labs/03-deploy/3B-row-ownership.sql",
             4: "labs/04-govern/4B-credit-writer.sql"}
ABSENCE_QUERY = "workshop/lab-4-absence.sql"


def _psql(path: str) -> List[str]:
    return ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-P", "pager=off", "-f", path]


def _check(task: str) -> List[str]:
    return ["python3", f"scripts/lab{task[0]}_check.py", "--task", task]


def _deploy(repo: pathlib.Path) -> List[str]:
    return ["python3", "scripts/provision_agentcore_end_to_end.py", "--repo-path", str(repo),
            "--mode", "participant"]


class Finish:
    """One lab's catch-up: every command is printed as typed, and the first failure stops it."""

    def __init__(self, lab: int, backend: Backend, token_for: Callable[[str], str],
                 run: Callable[..., Any], repo: pathlib.Path) -> None:
        self.lab, self.backend, self.token_for = lab, backend, token_for
        self.run, self.repo = run, repo

    def command(self, argv: List[str]) -> None:
        shown = shlex.join(argv)
        print(f"  $ {shown}", flush=True)
        executable = [sys.executable, *argv[1:]] if argv[0] == "python3" else argv
        code = self.run(executable, cwd=str(self.repo), check=False).returncode
        if code:
            raise LabRunError(f"{shown} exited {code}; the lines above say why. Fix it, then run "
                              f"python3 scripts/lab_run.py finish --lab {self.lab} again.")

    def restart(self) -> None:
        restart_backend(self.backend, run=self.run)

    def credit(self) -> None:
        """Jessica's request and Nadia's part, once, then the same-key replay proof."""
        print("  Nadia's approval and execution are done for you here; in the lab you make "
              "that decision yourself in the Operator.", flush=True)
        wait_until_healthy(self.backend)
        nadia = self.token_for(OPERATOR)
        reviews = jessicas_reviews(self.backend, nadia)
        if not any(credited(r) for r in reviews):
            for persona, stages in CONVERSATIONS[4]:
                converse(self.backend, 4, self.token_for(persona), persona,
                         required_requests(persona, stages))
        review = settle_credit(self.backend, nadia, reviews)
        prove_replay(self.backend, nadia, review)


def _finish_in_process(job: Finish) -> None:
    if job.lab == 2:
        job.command(_psql(EXERCISES[2]))
    job.restart()
    send(job.lab, job.backend, job.token_for)
    job.command(_check(f"{job.lab}A"))
    job.command(_check(f"{job.lab}B"))


def _finish_lab_3(job: Finish) -> None:
    job.command(_check("3A"))
    job.command(_deploy(job.repo))
    job.command(_psql(EXERCISES[3]))
    send(3, job.backend, job.token_for)
    job.command(_check("3B"))


def _finish_lab_4(job: Finish) -> None:
    job.command(_psql(EXERCISES[4]))
    job.command(_deploy(job.repo))
    job.credit()
    job.command(_check("4A"))
    job.command(_check("4B"))
    job.command(_psql(ABSENCE_QUERY))


def finish(lab: int, backend: Backend, token_for: Callable[[str], str] = mint_token,
           run: Callable[..., Any] = subprocess.run, repo: pathlib.Path = REPO) -> None:
    """Back up the lab's files, put its answers in place, then run what proves them."""
    for task in (t for t in TASKS if t.startswith(str(lab))):
        install_task(task, repo, next_line=False)
    job = Finish(lab, backend, token_for, run, repo)
    {1: _finish_in_process, 2: _finish_in_process, 3: _finish_lab_3, 4: _finish_lab_4}[lab](job)
    ok(f"Lab {lab} is finished: every check above passed")


def main(argv: Optional[Sequence[str]] = None, base_url: str = BASE_URL,
         token_for: Callable[[str], str] = mint_token) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("action", choices=("solution", "send", "diff", "reset", "finish"))
    parser.add_argument("--lab", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--shopper-only", action="store_true",
                        help="send: stop before Nadia's part in the Operator (Lab 4)")
    parser.add_argument("--quiet", action="store_true",
                        help="send: one line per request, without each turn's trace")
    parser.add_argument("--task", choices=TASKS,
                        help="solution: only that task's answer; send: only that task's request")
    args = parser.parse_args(argv)
    if args.task:
        if args.action not in ("solution", "send"):
            parser.error(f"--task goes with solution or send, not {args.action}")
        if not args.task.startswith(str(args.lab)):
            parser.error(f"--task {args.task} goes with {args.action} --lab {args.task[0]}")
        if args.action == "send" and args.task not in TASK_CONVERSATIONS:
            parser.error(f"send --task takes one of {', '.join(sorted(TASK_CONVERSATIONS))}; "
                         f"Task {args.task} has no request of its own")
    titles = {"solution": "install the solution", "send": "send the requests",
              "diff": "compare your files with the solution",
              "reset": "start over from the as-shipped lab",
              "finish": "finish the lab with its answers and prove it"}
    print(f"Lab {args.lab}: {titles[args.action]}", flush=True)
    try:
        if args.action == "diff":
            show_diff(args.lab, color=sys.stdout.isatty() and "NO_COLOR" not in os.environ)
        elif args.action == "solution" and args.task:
            backend = Backend(base_url)
            install_task(args.task, restart=lambda: restart_backend(backend))
        elif args.action == "solution":
            install_solution(args.lab)
        elif args.action == "finish":
            finish(args.lab, Backend(base_url), token_for)
        elif args.action == "reset":
            lab_reset.reset_lab(args.lab, wait_healthy=lambda: wait_until_healthy(
                Backend(base_url)))
        else:
            send(args.lab, Backend(base_url), token_for, shopper_only=args.shopper_only,
                 trace=not args.quiet, task=args.task)
    except (LabRunError, lab_reset.LabResetError, SystemExit) as exc:
        fail(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
