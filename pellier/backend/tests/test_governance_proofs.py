"""Contracts for the two governance-proof scripts.

`prove_governance_windows.py` compares the ENFORCE and LOG_ONLY windows against
a live Gateway. `score_governance_evidence.py` scores the same evidence a
participant reads by hand. Neither can run in the hermetic suite, so what is
pinned here is their *logic* and their safety properties.

Three safety properties carry real risk:

  1. **Mode is restored on every exit path.** A crashed run must not leave the
     account in monitor mode, where Cedar denies nothing.
  2. **A non-deployable project changes nothing.** `agentcore deploy` is a
     whole-project CDK deploy, so a template render cannot be deployed. The
     check has to happen *before* the declaration is edited, or a blocked run
     leaves the project declaring a mode that was never applied — which the
     next successful deploy would then apply by surprise.
  3. **The scorer must fail on a real violation.** A scorer that always passes
     is worse than none, because it certifies broken evidence.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str, filename: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _windows():
    return _load("prove_governance_windows_t", "prove_governance_windows.py")


def _scorer():
    return _load("score_governance_evidence_t", "score_governance_evidence.py")


# ---------------------------------------------------------------------------
# The two windows are asserted differently, on purpose
# ---------------------------------------------------------------------------


def _policy_call() -> Dict[str, Any]:
    return {
        "outcome": "policy_denied",
        "policy_source": "gateway-exception",
        "policy_evidence": "Tool call not allowed due to policy enforcement",
    }


def _rls_call() -> Dict[str, Any]:
    return {
        "outcome": "returned",
        "is_error": False,
        "result": {"status": "error", "denied_by": "database_row_level_security"},
    }


def _result(window: str, executions: int, returns: int = 0, ledger: int = 0) -> Dict[str, Any]:
    return {
        "window": window,
        "call": _policy_call() if window == "ENFORCE" else _rls_call(),
        "executions": executions,
        "business_change": {"returns": returns, "ledger": ledger},
    }


def test_enforce_window_requires_no_execution():
    """Cedar denies before the target runs, so the absence is the proof."""
    windows = _windows()

    assert windows._report(_result("ENFORCE", executions=0)) == []
    failures = windows._report(_result("ENFORCE", executions=1))
    assert failures and "expected no execution row" in failures[0]


def test_log_only_window_requires_execution():
    """Zero executions here means Cedar still blocked it.

    That is the failure mode worth catching: the mode change silently not
    taking effect looks identical to enforcement working.
    """
    windows = _windows()

    assert windows._report(_result("LOG_ONLY", executions=1)) == []
    failures = windows._report(_result("LOG_ONLY", executions=0))
    assert failures and "Cedar may still be enforcing" in failures[0]


def test_both_windows_require_zero_business_change():
    windows = _windows()

    for window in ("ENFORCE", "LOG_ONLY"):
        executions = 0 if window == "ENFORCE" else 1
        failures = windows._report(_result(window, executions, returns=1))
        assert any("committed a return row" in f for f in failures), window
        failures = windows._report(_result(window, executions, ledger=1))
        assert any("moved inventory" in f for f in failures), window


def test_a_missing_tool_is_reported_rather_than_scored():
    windows = _windows()
    result = _result("ENFORCE", 0)
    result["call"] = {"outcome": "tool_absent"}

    failures = windows._report(result)

    assert failures and "not published on the Gateway" in failures[0]


def test_the_request_targets_a_reason_the_policy_forbids():
    """A permitted reason would make both windows behave identically."""
    windows = _windows()

    assert windows.FORBIDDEN_REASON != "damaged"
    assert windows.GATING_POLICY == "initiate_return_damaged_only"


def test_mode_is_restored_on_every_exit_path():
    """A crashed run must not leave the account in monitor mode."""
    source = (_SCRIPTS / "prove_governance_windows.py").read_text()

    assert "finally:" in source
    restore_index = source.index("_restore_shipped")
    finally_index = source.index("finally:")
    assert finally_index < restore_index, "the restore must sit in a finally block"


_OBSERVATION_DB = {
    "DB_HOST": "database.invalid",
    "DB_NAME": "synthetic",
    "DB_USER": "synthetic",
    "DB_PASSWORD": "synthetic-test-only",
}


@pytest.mark.parametrize(
    "observation,returncode,stdout",
    [
        ("business", 1, ""),
        ("business", 1, "0|0\n"),
        ("business", 0, ""),
        ("business", 0, "0"),
        ("business", 0, "|0"),
        ("business", 0, "0|"),
        ("business", 0, "0|0|0"),
        ("business", 0, "-1|0"),
        ("business", 0, "0|0\n0|0"),
        ("business", 0, "0|unknown"),
        ("business", 0, "０|0"),
        ("business", 0, "9223372036854775808|0"),
        ("audit", 1, ""),
        ("audit", 1, "0\n"),
        ("audit", 0, ""),
        ("audit", 0, "-1"),
        ("audit", 0, "0|0"),
        ("audit", 0, "0\n0"),
        ("audit", 0, "unknown"),
        ("audit", 0, "0.0"),
        ("audit", 0, "True"),
        ("audit", 0, "0" * 20),
    ],
)
def test_unavailable_counts_never_become_zero(
    monkeypatch, observation, returncode, stdout,
):
    windows = _windows()
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=returncode, stdout=stdout,
            stderr="synthetic-sensitive-diagnostic",
        ),
    )

    with pytest.raises(windows.ObservationUnavailable) as error:
        if observation == "business":
            windows._business_state(_OBSERVATION_DB)
        else:
            windows._audit_rows(_OBSERVATION_DB, "synthetic-attempt")

    assert "synthetic-sensitive-diagnostic" not in str(error.value)


@pytest.mark.parametrize(
    "observation,stdout,expected",
    [
        ("business", "0|0\n", {"returns": 0, "ledger": 0}),
        ("business", "12|34\n", {"returns": 12, "ledger": 34}),
        ("audit", "0\n", 0),
        ("audit", "2\n", 2),
    ],
)
def test_successful_observations_preserve_real_zero_and_nonzero_counts(
    monkeypatch, observation, stdout, expected,
):
    windows = _windows()
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=stdout),
    )

    result = (
        windows._business_state(_OBSERVATION_DB)
        if observation == "business"
        else windows._audit_rows(_OBSERVATION_DB, "synthetic-attempt")
    )

    assert result == expected


@pytest.mark.parametrize(
    "failed_window,failed_stage",
    [
        ("ENFORCE", "before"),
        ("ENFORCE", "after"),
        ("ENFORCE", "audit"),
        ("LOG_ONLY", "before"),
        ("LOG_ONLY", "after"),
        ("LOG_ONLY", "audit"),
        (None, None),
    ],
)
def test_observation_failure_aborts_proof_and_restores_mode(
    monkeypatch, capsys, failed_window, failed_stage,
):
    """Exercise main and both real window collectors with only inert transports."""
    windows = _windows()
    events = []
    observations = []
    for window in ("ENFORCE", "LOG_ONLY"):
        for stage in ("before", "after", "audit"):
            observations.append(
                (
                    window, stage,
                    SimpleNamespace(
                        returncode=1 if (window, stage) == (
                            failed_window, failed_stage
                        ) else 0,
                        stdout=(
                            ("0\n" if window == "ENFORCE" else "1\n")
                            if stage == "audit" else "3|4\n"
                        ),
                        stderr="synthetic-sensitive-diagnostic",
                    ),
                )
            )
    pending = iter(observations)

    def observe(*args, **kwargs):
        window, stage, result = next(pending)
        events.append(("observe", window, stage))
        return result

    async def invoke(*args, **kwargs):
        events.append(("invoke",))
        return _policy_call() if events.count(("invoke",)) == 1 else _rls_call()

    policy = SimpleNamespace(
        gateway_id_from_arn=lambda arn: "synthetic-gateway",
        _apply=lambda *args, **kwargs: (
            events.append(("apply", kwargs["label"])) or 0
        ),
        _restore_shipped=lambda *args: events.append(("restore",)) or 0,
    )
    cfg = {
        **_OBSERVATION_DB,
        "AGENTCORE_GATEWAY_URL": "https://gateway.invalid",
        "AGENTCORE_POLICY_ENGINE_ID": "synthetic-engine",
        "COGNITO_POOL_ID": "synthetic-pool",
        "COGNITO_CLIENT_ID": "synthetic-client",
    }
    monkeypatch.setattr(windows, "_load_env", lambda: cfg)
    monkeypatch.setattr(windows, "_policy_tool", lambda: policy)
    monkeypatch.setattr(
        windows, "_import_tools",
        lambda: (
            SimpleNamespace(get_cognito_token=lambda **kwargs: "synthetic-token"),
            None,
        ),
    )
    monkeypatch.setitem(
        sys.modules, "boto3",
        SimpleNamespace(client=lambda *args, **kwargs: object()),
    )
    monkeypatch.setattr(subprocess, "run", observe)
    monkeypatch.setattr(windows, "_call_initiate_return", invoke)

    result = windows.main([])

    captured = capsys.readouterr()
    assert events[-1] == ("restore",)
    assert events.count(("restore",)) == 1
    assert "synthetic-sensitive-diagnostic" not in captured.out + captured.err
    if failed_window is None:
        assert result == 0
        assert "both windows behaved as designed" in captured.out
        assert sum(event[0] == "observe" for event in events) == 6
        assert events.count(("invoke",)) == 2
    else:
        assert result == 1
        assert "governance evidence unavailable" in captured.err
        assert "both windows behaved as designed" not in captured.out
        assert "Reading the pair" not in captured.out
        failure_index = next(
            i for i, (window, stage, _) in enumerate(observations)
            if (window, stage) == (failed_window, failed_stage)
        )
        assert sum(event[0] == "observe" for event in events) == failure_index + 1
        assert events.count(("invoke",)) == (
            (failed_window == "LOG_ONLY") + (failed_stage != "before")
        )


@pytest.mark.parametrize(
    "call",
    [
        {"outcome": "refused", "detail": "401 Unauthorized"},
        {"outcome": "refused", "detail": "connection reset"},
        {"outcome": "returned", "is_error": True, "text": ""},
        {"outcome": "returned", "is_error": True, "text": "Unknown tool"},
        {"outcome": "error", "error_kind": "transport_error"},
        {"outcome": "policy_denied"},
        {**_policy_call(), "policy_source": "inferred"},
        {**_policy_call(), "policy_evidence": "403 Forbidden"},
        {**_policy_call(), "policy_evidence": "Output blocked by policy: suppressed"},
    ],
)
def test_zero_counts_do_not_prove_a_cedar_denial(call):
    result = _result("ENFORCE", 0)
    result["call"] = call

    assert any("no explicit Gateway/Cedar denial" in failure
               for failure in _windows()._report(result))


@pytest.mark.parametrize(
    "envelope",
    [
        None,
        {"status": "error", "message": "Unauthorized"},
        {"status": "error", "sqlstate": "42601", "message": "syntax error"},
        {"status": "policy_blocked", "message": "reason not allowed"},
        {"status": "error", "denied_by": "database_approval_guard"},
        {"status": "output_suppressed", "denied_by": "database_row_level_security"},
        {"status": "success", "denied_by": "database_row_level_security"},
    ],
)
def test_an_attempt_receipt_does_not_prove_rls_enforcement(envelope):
    result = _result("LOG_ONLY", 1)
    result["call"]["result"] = envelope

    assert any("no explicit Aurora Row-Level Security" in failure
               for failure in _windows()._report(result))


@pytest.mark.parametrize("observation", ["business", "audit"])
@pytest.mark.parametrize("error_kind", ["timeout", "launch"])
def test_sql_observations_have_a_deadline_and_sanitized_failures(
    monkeypatch, observation, error_kind,
):
    windows = _windows()

    def unavailable(command, **kwargs):
        assert 0 < kwargs["timeout"] <= 30
        if error_kind == "timeout":
            raise subprocess.TimeoutExpired(
                command, kwargs["timeout"],
                output="synthetic-sensitive-output", stderr="synthetic-sensitive-error",
            )
        raise OSError("synthetic-sensitive-launch-error")

    monkeypatch.setattr(subprocess, "run", unavailable)
    with pytest.raises(windows.ObservationUnavailable) as failure:
        if observation == "business":
            windows._business_state(_OBSERVATION_DB)
        else:
            windows._audit_rows(_OBSERVATION_DB, "synthetic-attempt")
    assert "observation unavailable" in str(failure.value)
    assert "synthetic-sensitive" not in str(failure.value)
    assert _OBSERVATION_DB["DB_PASSWORD"] not in str(failure.value)


def _stub_gateway(monkeypatch, *, error=None, response=None, stage="call"):
    import mcp
    import mcp.client.streamable_http as transport

    observed = {}

    @asynccontextmanager
    async def connect(url, *, http_client):
        observed["redirects"] = http_client.follow_redirects
        observed["response_hooks"] = http_client.event_hooks["response"]
        yield object(), object(), None

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            if error is not None and stage == "initialize":
                raise error

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="target___initiate_return")])

        async def call_tool(self, *args):
            if error is not None:
                raise error
            return response

    monkeypatch.setattr(transport, "streamable_http_client", connect)
    monkeypatch.setattr(mcp, "ClientSession", Session)
    return observed


@pytest.mark.parametrize(
    "case,expected",
    [
        ("explicit", "policy_denied"),
        ("nested_explicit", "policy_denied"),
        ("mixed_exception_group", "error"),
        ("bare401", "error"),
        ("401_with_policy_text", "error"),
        ("bare403", "error"),
        ("explicit403", "policy_denied"),
        ("503_with_policy_text", "error"),
        ("transport", "error"),
        ("transport_with_policy_text", "error"),
        ("suppressed", "error"),
        ("unknown_tool", "error"),
        ("denial_before_invocation", "error"),
    ],
)
def test_gateway_failures_require_explicit_invocation_denial_evidence(
    monkeypatch, case, expected,
):
    import httpx

    marker = "Tool call not allowed due to policy enforcement"
    if case in {"bare401", "401_with_policy_text", "bare403", "explicit403", "503_with_policy_text"}:
        status = 401 if "401" in case else 503 if "503" in case else 403
        message = marker if "policy_text" in case or case == "explicit403" else "Forbidden"
        request = httpx.Request("POST", "https://gateway.invalid/mcp")
        response = httpx.Response(status, request=request, json={"error": {"message": message}})
        error = httpx.HTTPStatusError("synthetic-sensitive-request", request=request, response=response)
    elif case == "nested_explicit":
        error = ExceptionGroup("task group", [RuntimeError(marker)])
    elif case == "mixed_exception_group":
        error = ExceptionGroup("task group", [RuntimeError(marker), RuntimeError("Unauthorized")])
    elif case.startswith("transport"):
        error = httpx.ConnectTimeout(marker if "policy_text" in case else "synthetic-sensitive-request")
    else:
        error = RuntimeError(
            "Output blocked by policy: response suppressed" if case == "suppressed"
            else "Unknown tool" if case == "unknown_tool" else marker
        )
    observed = _stub_gateway(
        monkeypatch, error=error,
        stage="initialize" if case == "denial_before_invocation" else "call",
    )
    windows = _windows()

    result = asyncio.run(windows._call_initiate_return(
        "https://gateway.invalid/mcp", "synthetic-token",
        reason="changed_mind", idempotency_key="synthetic-attempt",
    ))

    assert result["outcome"] == expected
    assert observed["redirects"] is False
    assert windows.read_gateway_error_response in observed["response_hooks"]
    proof = _result("ENFORCE", 0)
    proof["call"] = result
    assert bool(windows._report(proof)) is (expected != "policy_denied")
    assert "synthetic-sensitive-request" not in json.dumps(result)


@pytest.mark.parametrize(
    "text,is_error,expected",
    [
        ("Unknown tool", True, "returned"),
        ("401 Unauthorized", True, "returned"),
        ("Tool call not allowed due to policy enforcement", True, "policy_denied"),
        ("Output blocked by policy: response suppressed", True, "error"),
        (json.dumps(_rls_call()["result"]), False, "returned"),
    ],
)
def test_returned_tool_errors_are_classified_from_explicit_evidence(
    monkeypatch, text, is_error, expected,
):
    _stub_gateway(
        monkeypatch,
        response=SimpleNamespace(isError=is_error, content=[SimpleNamespace(text=text)]),
    )
    result = asyncio.run(_windows()._call_initiate_return(
        "https://gateway.invalid/mcp", "synthetic-token",
        reason="changed_mind", idempotency_key="synthetic-attempt",
    ))

    assert result["outcome"] == expected
    if text == json.dumps(_rls_call()["result"]):
        proof = _result("LOG_ONLY", 1)
        proof["call"] = result
        assert _windows()._report(proof) == []


def _stub_main(monkeypatch, *, results=None, restore=0, apply=0):
    windows = _windows()
    events = []
    results = results or {"ENFORCE": _result("ENFORCE", 0), "LOG_ONLY": _result("LOG_ONLY", 1)}

    def restore_mode(*args):
        events.append("restore")
        if isinstance(restore, Exception):
            raise restore
        return restore

    policy = SimpleNamespace(
        gateway_id_from_arn=lambda arn: "synthetic-gateway",
        _apply=lambda *args, **kwargs: events.append(kwargs["label"]) or apply,
        _restore_shipped=restore_mode,
    )
    cfg = {**_OBSERVATION_DB, **{key: "synthetic" for key in (
        "AGENTCORE_GATEWAY_URL", "AGENTCORE_POLICY_ENGINE_ID",
        "COGNITO_POOL_ID", "COGNITO_CLIENT_ID",
    )}}
    monkeypatch.setattr(windows, "_load_env", lambda: cfg)
    monkeypatch.setattr(windows, "_policy_tool", lambda: policy)
    monkeypatch.setattr(windows, "_import_tools", lambda: (
        SimpleNamespace(get_cognito_token=lambda **kwargs: "synthetic-token"), None,
    ))
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: object()))
    monkeypatch.setattr(windows, "_run_window", lambda label, *args: results[label])
    return windows, events


@pytest.mark.parametrize("restore", [1, 3, None, False, RuntimeError("synthetic-sensitive-restore")])
def test_restoration_failure_prevents_the_success_reading(monkeypatch, capsys, restore):
    windows, events = _stub_main(monkeypatch, restore=restore)

    assert windows.main([]) == 1
    captured = capsys.readouterr()
    assert "restoration" in captured.err
    assert "Reading the pair" not in captured.out
    assert "both windows behaved as designed" not in captured.out
    assert "synthetic-sensitive" not in captured.out + captured.err
    assert events[-1] == "restore"


@pytest.mark.parametrize("window", ["ENFORCE", "LOG_ONLY"])
def test_outcome_failure_prevents_any_success_interpretation(monkeypatch, capsys, window):
    results = {"ENFORCE": _result("ENFORCE", 0), "LOG_ONLY": _result("LOG_ONLY", 1)}
    results[window]["call"] = {"outcome": "refused", "detail": "synthetic-sensitive-401"}
    windows, events = _stub_main(monkeypatch, results=results)

    assert windows.main([]) == 1
    captured = capsys.readouterr()
    assert "no explicit" in captured.err
    assert "Reading the pair" not in captured.out
    assert "both windows behaved as designed" not in captured.out
    assert "synthetic-sensitive" not in captured.out + captured.err
    assert events[-1] == "restore"
    if window == "ENFORCE":
        assert "LOG_ONLY window" not in events


@pytest.mark.parametrize("apply,expected", [(1, 1), (3, 2), (None, 1), (False, 1)])
def test_unestablished_mode_cannot_yield_success(monkeypatch, capsys, apply, expected):
    windows, events = _stub_main(monkeypatch, apply=apply)

    assert windows.main([]) == expected
    captured = capsys.readouterr()
    assert "Reading the pair" not in captured.out
    assert "both windows behaved as designed" not in captured.out
    assert events[-1] == "restore"


# ---------------------------------------------------------------------------
# A non-deployable project must change nothing
# ---------------------------------------------------------------------------


def test_deployability_rejects_a_template_render(tmp_path):
    tool = _load("policy_mode_proofs_t", "policy_mode.py")
    project = tmp_path / "p"
    (project / "agentcore").mkdir(parents=True)
    (project / "agentcore" / "agentcore.json").write_text(
        '{"agentCoreGateways": [{"roleArn": "arn:aws:iam::123456789012:role/x"}]}'
    )

    blocker = tool.deployability(project, "444455556666")

    assert blocker and "template render" in blocker


def test_deployability_rejects_a_cross_account_project(tmp_path):
    tool = _load("policy_mode_proofs_t", "policy_mode.py")
    project = tmp_path / "p"
    (project / "agentcore").mkdir(parents=True)
    (project / "agentcore" / "agentcore.json").write_text(
        '{"agentCoreGateways": [{"roleArn": "arn:aws:iam::111122223333:role/x"}]}'
    )

    blocker = tool.deployability(project, "444455556666")

    assert blocker and "111122223333" in blocker


def test_deployability_accepts_a_matching_project(tmp_path):
    tool = _load("policy_mode_proofs_t", "policy_mode.py")
    project = tmp_path / "p"
    (project / "agentcore").mkdir(parents=True)
    (project / "agentcore" / "agentcore.json").write_text(
        '{"agentCoreGateways": [{"roleArn": "arn:aws:iam::444455556666:role/x"}]}'
    )

    assert tool.deployability(project, "444455556666") is None


def test_a_blocked_change_is_checked_before_the_declaration_is_edited():
    """Editing first would leave a declared mode that was never applied."""
    source = (_SCRIPTS / "policy_mode.py").read_text()
    apply_body = source[source.index("def _apply("):source.index("def main(")]

    assert apply_body.index("deployability(") < apply_body.index("declare_modes(")


# ---------------------------------------------------------------------------
# The scorer must fail on a real violation
# ---------------------------------------------------------------------------


def _turn(**overrides: Any) -> Dict[str, Any]:
    turn = {
        "turn_id": "turn-x",
        "principal_sub": "sub-a",
        "principal_verified": True,
        "rail": "gateway-mcp",
        "terminal_status": "complete",
        "decision": "ALLOW",
        "decision_source": "governed_receipts",
        "executions": 1,
        "policy_receipts": 1,
        "successful_executions": 1,
    }
    turn.update(overrides)
    return turn


def _failed(findings: List[Dict[str, str]]) -> List[str]:
    return [f["invariant"] for f in findings if f["result"] == "FAIL"]


def test_a_clean_allowed_turn_passes():
    scorer = _scorer()

    assert _failed(scorer.score_turn(_turn())) == []


def test_a_denied_turn_with_an_execution_row_fails():
    """The tool ran after being refused, which the design forbids."""
    scorer = _scorer()

    failed = _failed(
        scorer.score_turn(
            _turn(decision="DENY", executions=1, successful_executions=1,
                  terminal_status="denied-before-execution", policy_receipts=0)
        )
    )

    assert "denial means non-execution" in failed
    assert "denial changed nothing" in failed


def test_a_clean_denied_turn_passes():
    scorer = _scorer()

    failed = _failed(
        scorer.score_turn(
            _turn(decision="DENY", executions=0, successful_executions=0,
                  policy_receipts=0, terminal_status="denied-before-execution")
        )
    )

    assert failed == []


def test_a_monitor_turn_that_never_executed_fails():
    """Zero executions means the mode change never took effect."""
    scorer = _scorer()

    failed = _failed(
        scorer.score_turn(
            _turn(decision="WOULD_DENY", executions=0, successful_executions=0,
                  policy_receipts=0)
        )
    )

    assert "monitor mode still executed" in failed


def test_a_monitor_turn_that_succeeded_fails():
    """A would-deny that changed state means nothing refused it."""
    scorer = _scorer()

    failed = _failed(
        scorer.score_turn(
            _turn(decision="WOULD_DENY", executions=1, successful_executions=1,
                  policy_receipts=0)
        )
    )

    assert "monitor mode changed nothing" in failed


def test_a_clean_monitor_turn_passes():
    scorer = _scorer()

    failed = _failed(
        scorer.score_turn(
            _turn(decision="WOULD_DENY", executions=1, successful_executions=0,
                  policy_receipts=0)
        )
    )

    assert failed == []


def test_a_turn_with_no_identity_fails():
    scorer = _scorer()

    failed = _failed(_scorer().score_turn(_turn(principal_sub=None, principal_verified=True)))

    assert "identity recorded" in failed


def test_an_anonymous_turn_is_not_an_identity_failure():
    """Anonymous is a legitimate state; unrecorded is not."""
    scorer = _scorer()

    failed = _failed(scorer.score_turn(_turn(principal_sub=None, principal_verified=False)))

    assert "identity recorded" not in failed


def test_more_policy_receipts_than_executions_fails_correlation():
    """A receipt joins through audit_id, so it cannot outnumber executions."""
    scorer = _scorer()

    failed = _failed(scorer.score_turn(_turn(executions=1, policy_receipts=2)))

    assert "correlation holds" in failed


def test_a_turn_with_no_decision_is_reported():
    scorer = _scorer()

    failed = _failed(scorer.score_turn(_turn(decision=None, decision_source=None)))

    assert "policy decision recorded" in failed


def test_the_scorer_needs_no_model_or_managed_service():
    """Section 19.7 keeps evaluations out of required lab completion."""
    source = (_SCRIPTS / "score_governance_evidence.py").read_text()

    for forbidden in ("bedrock", "converse(", "invoke_model", "StartBatchEvaluation"):
        assert forbidden not in source, forbidden
