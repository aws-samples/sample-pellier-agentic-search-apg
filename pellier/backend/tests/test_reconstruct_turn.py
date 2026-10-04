"""Tests for `scripts/reconstruct_turn.py` — the turn-reconstruction CLI.

Two things are worth pinning here, and neither is about formatting.

**The query syntax.** CloudWatch Logs Insights rejects a backslash-escaped
dotted key (`attributes.pellier\\.turn_id`) with a MalformedQueryException,
even though escaping is the intuitive guess for a key that literally contains
dots. The bare dotted path is what resolves. That cost a live debugging cycle,
so a test pins it: the escape form must never come back.

**The identity report.** The CLI's job is to state what the spans say and
nothing more. "anonymous" and "anonymous with a simulated persona" are
different facts, and neither may be reported as a verified principal — that
inversion is exactly what `TurnIdentity` exists to prevent, so the read side
must not reintroduce it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_cli():
    module_name = "reconstruct_turn_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]

    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "reconstruct_turn.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def test_attribute_path_is_bare_dotted_not_backslash_escaped():
    """Regression: Insights rejects `attributes.pellier\\.turn_id`.

    The service returns MalformedQueryException, "token recognition error
    at: '\\'". The bare dotted path resolves the value. Verified against a
    live aws/spans log group.
    """
    cli = _load_cli()

    assert cli._ATTR.format("turn_id") == "attributes.pellier.turn_id"
    assert "\\" not in cli._ATTR


def test_turn_query_filters_on_turn_id_and_selects_the_evidence_legs():
    cli = _load_cli()

    query = cli._TURN_QUERY.format(
        turn=cli._ATTR.format("turn_id"),
        sub=cli._ATTR.format("principal_sub"),
        auth=cli._ATTR.format("authenticated"),
        simulated=cli._ATTR.format("persona_is_simulated"),
        caller=cli._ATTR.format("caller"),
        tool=cli._ATTR.format("execution_outcome"),
        outcome=cli._ATTR.format("execution_outcome"),
        mode=cli._ATTR.format("policy_mode"),
        verdict=cli._ATTR.format("policy_verdict"),
        turn_id="turn-abc123",
    )

    assert "filter attributes.pellier.turn_id = 'turn-abc123'" in query
    # All four evidence legs must be selectable from one query, or the CLI
    # cannot show identity, policy, and execution together.
    for attribute in ("principal_sub", "policy_verdict", "execution_outcome"):
        assert f"attributes.pellier.{attribute}" in query


# ---------------------------------------------------------------------------
# Bounded polling
# ---------------------------------------------------------------------------


class _FakeLogsClient:
    """Minimal CloudWatch Logs stand-in."""

    def __init__(self, statuses, results=None):
        self._statuses = list(statuses)
        self._results = results or []
        self.started = []

    def start_query(self, **kwargs):
        self.started.append(kwargs)
        return {"queryId": "q-1"}

    def get_query_results(self, queryId):  # noqa: N803 - boto3 casing
        status = self._statuses.pop(0) if self._statuses else "Running"
        return {"status": status, "results": self._results if status == "Complete" else []}


def test_run_query_returns_rows_without_the_ptr_field(monkeypatch):
    cli = _load_cli()
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)

    client = _FakeLogsClient(
        statuses=["Running", "Complete"],
        results=[[{"field": "name", "value": "routing"}, {"field": "@ptr", "value": "x"}]],
    )

    rows = cli.run_query(client, "aws/spans", "fields name", minutes=30)

    assert rows == [{"name": "routing"}]
    assert "@ptr" not in rows[0]


def test_run_query_gives_up_rather_than_hanging(monkeypatch):
    """An unbounded wait would read as a broken tool, not as absent evidence."""
    cli = _load_cli()
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)

    client = _FakeLogsClient(statuses=[])  # never completes

    with pytest.raises(TimeoutError):
        cli.run_query(client, "aws/spans", "fields name", minutes=30)


def test_run_query_surfaces_a_failed_query(monkeypatch):
    cli = _load_cli()
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)

    client = _FakeLogsClient(statuses=["Failed"])

    with pytest.raises(RuntimeError):
        cli.run_query(client, "aws/spans", "fields name", minutes=30)


def test_query_window_is_bounded_by_minutes(monkeypatch):
    cli = _load_cli()
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    client = _FakeLogsClient(statuses=["Complete"])

    cli.run_query(client, "aws/spans", "fields name", minutes=45)

    call = client.started[0]
    assert call["endTime"] - call["startTime"] == 45 * 60


# ---------------------------------------------------------------------------
# Identity reporting
# ---------------------------------------------------------------------------


def test_verified_principal_is_named():
    cli = _load_cli()

    line = cli._identity_line([{"principal": "sub-abc", "authenticated": "1"}])

    assert "sub-abc" in line
    assert "verified" in line


def test_simulated_persona_is_not_reported_as_a_principal():
    """A persona is scope, not identity. Saying otherwise teaches the bug."""
    cli = _load_cli()

    line = cli._identity_line(
        [{"authenticated": "0", "persona_simulated": "1"}]
    )

    assert "anonymous" in line
    assert "not valid for authorization" in line


def test_anonymous_without_persona_is_distinct_from_simulated():
    cli = _load_cli()

    line = cli._identity_line([{"authenticated": "0", "persona_simulated": "0"}])

    assert "anonymous" in line
    assert "persona" in line
    assert "not valid for authorization" not in line


def test_absent_identity_attributes_are_reported_as_absent():
    """No identity on any span is "not reported", never "anonymous"."""
    cli = _load_cli()

    line = cli._identity_line([{"name": "execute_tool search_products"}])

    assert "not reported" in line


# ---------------------------------------------------------------------------
# Row rendering
# ---------------------------------------------------------------------------


def test_detail_omits_fields_the_span_did_not_carry():
    cli = _load_cli()

    assert cli._detail({}) == ""
    assert cli._detail({"tool": "check_stock"}) == "tool=check_stock"
    assert "ENFORCE/DENY" in cli._detail(
        {"policy_mode": "ENFORCE", "policy_verdict": "DENY"}
    )


def test_verdict_without_mode_prints_no_placeholder():
    """Gateway mode is engine config and usually absent from the span.

    A `?/DENY` placeholder would read as "the turn failed to report its
    mode" rather than "mode is not turn data".
    """
    cli = _load_cli()

    assert cli._detail({"policy_verdict": "NOT_EVALUATED"}) == "NOT_EVALUATED"
    assert "?" not in cli._detail({"policy_verdict": "DENY"})


def test_duration_renders_millis_and_tolerates_absence():
    cli = _load_cli()

    assert cli._millis("2724000000") == "2724ms"
    assert cli._millis(None) == "-"
    assert cli._millis("not-a-number") == "-"


def test_region_defaults_to_the_app_export_region(monkeypatch):
    """Querying the wrong region returns zero rows and looks like a bug."""
    cli = _load_cli()
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    args = cli._parse_args(["--boundaries"])

    assert args.region == cli.DEFAULT_REGION == "us-east-1"


def test_turn_id_is_required_unless_listing_boundaries():
    cli = _load_cli()

    with pytest.raises(SystemExit):
        cli._parse_args([])


# ---------------------------------------------------------------------------
# The Aurora half
#
# `--aurora` was documented in the usage block and read in `main` while never
# being registered on the parser. Two failures followed and hid each other:
# passing the documented flag was an argparse error, and the default path
# raised AttributeError on `args.aurora` as soon as a span query returned rows
# — which it never did, because span export was separately inert.
# ---------------------------------------------------------------------------



def _stub_boto3(monkeypatch) -> None:
    """Stand in for boto3, which `main` imports at call time.

    The CloudWatch client is never used by these tests: `run_query` is stubbed
    too. This only keeps the import inside `main` from reaching the network or
    a credential chain.
    """
    import types

    stub = types.ModuleType("boto3")
    stub.client = lambda *a, **k: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", stub)


def test_the_documented_answer_key_flag_exists():
    cli = _load_cli()

    assert cli._parse_args(["turn-x", "--aurora"]).aurora is True
    assert cli._parse_args(["turn-x"]).aurora is False


def test_main_reads_no_attribute_the_parser_does_not_define():
    """Every `args.<name>` in main must come from an add_argument dest."""
    cli = _load_cli()
    import inspect
    import re

    source = inspect.getsource(cli.main)
    used = set(re.findall(r"args\.([a-z_]+)", source))
    defined = set(vars(cli._parse_args(["turn-x"])))

    assert used <= defined, f"main reads undefined args: {sorted(used - defined)}"


def test_aurora_artifacts_are_detected_only_when_rows_exist():
    """The exit code turns on this, so an empty read must not read as found."""
    cli = _load_cli()

    assert cli._has_aurora_artifacts({"available": False, "reason": "no settings"}) is False
    assert cli._has_aurora_artifacts({"available": True, "turn": [], "audit": []}) is False
    assert cli._has_aurora_artifacts({"available": True, "turn": [{"turn_id": "t"}]}) is True


def test_a_turn_with_no_spans_still_prints_the_authoritative_side(monkeypatch, capsys):
    """The seeded forensic turns exist only in Aurora, so this is their path."""
    cli = _load_cli()
    _stub_boto3(monkeypatch)
    monkeypatch.setattr(cli, "run_query", lambda *a, **k: [])
    monkeypatch.setattr(
        cli,
        "read_aurora_evidence",
        lambda turn_id, env: {"available": True, "turn": [{"turn_id": turn_id}]},
    )
    printed: list = []
    monkeypatch.setattr(cli, "print_aurora_evidence", lambda ev, t: printed.append(t))

    code = cli.main(["turn-forensic-allowed", "--aurora"])

    assert code == 0
    assert printed == ["turn-forensic-allowed"]
    assert "authoritative" in capsys.readouterr().out


def test_a_turn_absent_from_both_sides_exits_nonzero(monkeypatch):
    """Otherwise a typo in the turn_id reads as a clean reconstruction."""
    cli = _load_cli()
    _stub_boto3(monkeypatch)
    monkeypatch.setattr(cli, "run_query", lambda *a, **k: [])
    monkeypatch.setattr(
        cli, "read_aurora_evidence", lambda turn_id, env: {"available": True, "turn": []}
    )
    monkeypatch.setattr(cli, "print_aurora_evidence", lambda ev, t: None)

    assert cli.main(["turn-typo", "--aurora"]) == 2


def test_without_the_flag_a_missing_turn_does_not_touch_aurora(monkeypatch):
    cli = _load_cli()
    _stub_boto3(monkeypatch)
    monkeypatch.setattr(cli, "run_query", lambda *a, **k: [])

    def _fail(*_a, **_k):  # pragma: no cover - must not run
        raise AssertionError("span-only mode must not open a database connection")

    monkeypatch.setattr(cli, "read_aurora_evidence", _fail)

    assert cli.main(["turn-x"]) == 2
