#!/usr/bin/env python3
"""Catch up on a lab: install its solution files, then send its requests.

The guide's "Short on time?" block chains these two commands with the lab's
restart or deployment and its checks:

    python3 scripts/lab_run.py solution --lab 1
    python3 scripts/lab_run.py send --lab 1

``solution`` copies the lab's supplied answers over the files its tasks edit,
using the map in ``workshop/participant-files.json`` (the files the
``labs/0N-*/solution/`` folders link to). It neither restarts the backend nor
deploys; the block's next command does that.

``send`` makes the lab's requests through the local backend, the way Ask
Pellier does: each shopper signs in as their Cognito test user and starts a
new conversation, and the requests are that lab's required ones in
``data/scenarios.json``. Every turn must run on the lab's path, in process for
Labs 1 and 2 and through AgentCore Runtime and Gateway for Labs 3 and 4. Lab 4
then does Nadia's part in the Operator: investigate Jessica's case, approve
the credit the Planner proposes, and execute it. A Cedar deployment takes a
few minutes to apply, so an execution that Cedar still denies, or that the
Gateway cannot yet answer, is retried.

Each step prints ``+ OK`` or ``x FAIL``. The first failure stops the command
with exit status 1.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

IN_PROCESS, MANAGED = "in-process", "gateway-mcp"
RAIL_NAMES = {IN_PROCESS: "in process", MANAGED: "AgentCore Runtime and Gateway"}
LAB_RAIL = {1: IN_PROCESS, 2: IN_PROCESS, 3: MANAGED, 4: MANAGED}

# Each lab's conversations, in order: the shopper and the journey stages of the
# required requests they send. Theo's ticket and household requests share one
# conversation because the second refers to the first.
CONVERSATIONS = {
    1: [("anna", ("establish",))],
    2: [("marco", ("exercise", "prove"))],
    3: [("theo", ("establish",)), ("theo", ("exercise", "prove"))],
    4: [("jessica", ("establish",))],
}
DEPLOY = 'python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant'
NEXT_AFTER_SOLUTION = {
    1: "restart the backend (sudo systemctl restart pellier), then send the lab's request.",
    2: "restart the backend (sudo systemctl restart pellier), then send the lab's requests.",
    3: f"deploy the Task 3A files ({DEPLOY}), then send the lab's requests.",
    4: f"deploy the Cedar rule ({DEPLOY}), then send the lab's requests.",
}

OPERATOR = "nadia"
CREDIT_CLIENT = "CUST-JESSICA"
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
    """The participant-file entries whose editor alias sits in this lab's folder."""
    entries = json.loads((repo / "workshop" / "participant-files.json").read_text("utf-8"))
    mine = [entry for entry in entries if entry["alias"].startswith(f"labs/0{lab}-")]
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

    def get_json(self, path: str) -> Dict[str, Any]:
        with self._open(path, None, None, 10) as response:
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


def send_turn(backend: Backend, token: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """One Ask Pellier turn; returns the complete event's response."""
    for name, event in backend.stream("/api/chat/stream", body, token):
        if name == "error" or event.get("type") == "error":
            reason = event.get("error") or event.get("message") or json.dumps(event)
            raise LabRunError(f"the turn failed: {reason}")
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
        return (f"Lab {lab} runs in process, but {observed}. Lab 3's start has moved the "
                "storefront to AgentCore, so this turn did not run the code you edited. To "
                "rerun it, set USE_AGENTCORE_RUNTIME=false in .env, restart the backend and "
                "rerun this command; bash scripts/lab3-start.sh switches back.")
    return (f"Lab {lab} runs on AgentCore Runtime and Gateway, but {observed}. "
            "Run bash scripts/lab3-start.sh, then rerun this command.")


def _one_line(text: str, width: int = 140) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 3].rstrip() + "..."


def converse(backend: Backend, lab: int, token: str, persona: str,
             requests: Sequence[str]) -> None:
    """Start a new conversation as this shopper and send the requests in order."""
    session = backend.post_json("/api/persona/switch", {"persona_id": persona})["session_id"]
    history: List[Dict[str, str]] = []
    for message in requests:
        response = send_turn(backend, token, {
            "message": message,
            "session_id": session,
            "customer_id": f"CUST-{persona.upper()}",
            "conversation_history": history,
        })
        served = str(response.get("rail") or "")
        if served != LAB_RAIL[lab]:
            raise LabRunError(_rail_problem(lab, served, response))
        answer = str(response.get("response") or "")
        ok(f'{persona.title()}: "{message}" ran {RAIL_NAMES[served]} '
           f"(turn {response.get('turn_id') or '?'})")
        print(f"          Pellier: {_one_line(answer)}", flush=True)
        history += [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]


# ---------------------------------------------------------------------------
# send, Lab 4: Nadia's part in the Operator
# ---------------------------------------------------------------------------


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
                "scripts/lab4_policy_check.py, deploy it, and rerun.")
        wait(f"{why}. Retrying in {RETRY_SECONDS} s.")
        time.sleep(RETRY_SECONDS)


def approve_credit(backend: Backend, token: str) -> None:
    """Nadia investigates Jessica's case, approves the proposal and executes it."""
    proposal = investigate(backend, token, CREDIT_CLIENT)
    review = int(proposal["reviewId"])
    ok(f"Nadia investigated Jessica's case: review {review} proposes "
       f"${proposal.get('amount')} for orders {proposal.get('orderIds')}")
    approve(backend, token, proposal)
    payload = execute_until_allowed(backend, token, review)
    credits = (payload.get("record") or {}).get("creditRows")
    if credits != 1:
        raise LabRunError(f"review {review} executed with Policy ALLOW but Aurora holds "
                          f"{credits} credit rows for its key, not 1")
    ok(f"Policy ALLOW; Aurora holds one credit for key {payload.get('idempotencyKey')}")


def mint_token(username: str) -> str:
    """A Cognito access token for one workshop test user."""
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    from gateway_client import _load_env, _token_from_cognito

    _load_env()
    try:
        return _token_from_cognito(username)
    except Exception as exc:  # noqa: BLE001 - boto3 and Cognito errors, reported with the user
        raise LabRunError(f"could not sign in as {username}: {exc}") from exc


def send(lab: int, backend: Backend, token_for: Callable[[str], str] = mint_token) -> None:
    """Make the lab's requests on the lab's path, and for Lab 4 do Nadia's part."""
    wait_until_healthy(backend)
    tokens: Dict[str, str] = {}
    for persona, stages in CONVERSATIONS[lab]:
        if persona not in tokens:
            tokens[persona] = token_for(persona)
        converse(backend, lab, tokens[persona], persona, required_requests(persona, stages))
    if lab == 4:
        approve_credit(backend, token_for(OPERATOR))


def main(argv: Optional[Sequence[str]] = None, base_url: str = BASE_URL,
         token_for: Callable[[str], str] = mint_token) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("action", choices=("solution", "send"))
    parser.add_argument("--lab", type=int, choices=(1, 2, 3, 4), required=True)
    args = parser.parse_args(argv)
    title = "install the solution" if args.action == "solution" else "send the requests"
    print(f"Lab {args.lab}: {title}", flush=True)
    try:
        if args.action == "solution":
            install_solution(args.lab)
        else:
            send(args.lab, Backend(base_url), token_for)
    except (LabRunError, SystemExit) as exc:
        fail(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
