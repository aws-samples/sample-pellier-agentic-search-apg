"""The doctor names the prerequisite a stuck participant has not met, per lab.

Every check is a pure function over injected inputs (a fake evidence surface,
a scratch repository, a scratch env file), so the whole contract runs offline.
The last class pins the two shell entry points that sit beside the doctor:
they must parse under bash 3.2 and read configuration through the shared
dotenv parser rather than sourcing a secret as shell.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "workshop_doctor.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pellier_workshop_doctor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pellier_workshop_doctor"] = module
    spec.loader.exec_module(module)
    return module


doctor = _load()


class FakeEvidence:
    """Answers each query by the first registered SQL fragment it contains."""

    def __init__(
        self, rows: Optional[Dict[str, Optional[Dict[str, Any]]]] = None, reason: str = ""
    ) -> None:
        self.rows = rows or {}
        self.reason = reason
        self.queries: list = []
        self.closed = False

    @property
    def available(self) -> bool:
        return not self.reason

    def one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        self.queries.append((sql, params))
        for fragment, row in self.rows.items():
            if fragment in sql:
                return row
        return None

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeEvidence":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False


def _by_name(checks: list) -> Dict[str, Any]:
    return {check.name: check for check in checks}


STARTERS = REPO / "workshop" / "starters" / "lab-2"
GRANT = "Stock agent granted check_stock alone"
TOOL_MARKER = "    # === WORKSHOP - Stock agent - check_stock: {} ===\n"
AGENT_MARKER = "# === WORKSHOP - Stock agent - definition: {} ===\n"


def _scratch_backend(tmp_path: Path, *, tool_body: str, agent_body: str) -> Path:
    backend = tmp_path / "backend"
    (backend / "services").mkdir(parents=True)
    (backend / "agents").mkdir()
    (backend / "services" / "agent_tools.py").write_text(
        TOOL_MARKER.format("START") + tool_body + TOOL_MARKER.format("END"), encoding="utf-8")
    (backend / "agents" / "stock_agent.py").write_text(
        AGENT_MARKER.format("START") + agent_body + AGENT_MARKER.format("END"), encoding="utf-8")
    return backend


def _starter(name: str) -> str:
    return (STARTERS / name).read_text(encoding="utf-8")


class TestLab2:
    def test_unreachable_database_fails_with_the_reason(self) -> None:
        checks = doctor.lab2_checks(FakeEvidence(reason="connection refused"))
        db = _by_name(checks)["database reachable"]
        assert db.passed is False
        assert "connection refused" in db.detail

    def test_the_starters_are_named_as_unfinished(self, tmp_path: Path) -> None:
        backend = _scratch_backend(
            tmp_path, tool_body=_starter("check-stock-tool.pyfrag"),
            agent_body=_starter("stock-agent-definition.pyfrag"))
        evidence = FakeEvidence({"SELECT 1": {"ok": 1}})
        checks = _by_name(doctor.lab2_checks(evidence, backend=backend))
        assert checks["database reachable"].passed is True
        assert checks["check_stock written"].passed is False
        assert "still holds its starter" in checks["check_stock written"].detail
        grant = checks[GRANT]
        assert grant.passed is False
        assert grant.detail == ("stock_agent.py grants search_products, browse_department, "
                                "compare_products, check_stock; Task 2B grants check_stock alone")

    @pytest.mark.parametrize("body", [
        "_STOCK_TOOLS = [agent_tools.check_stock]\n",
        "_STOCK_TOOLS = [check_stock]\n",
    ])
    def test_edited_blocks_pass(self, tmp_path: Path, body: str) -> None:
        backend = _scratch_backend(
            tmp_path,
            tool_body="    return _reply(store_tools.check_stock(_run_sql, product_query=q))\n",
            agent_body=body)
        evidence = FakeEvidence({"SELECT 1": {"ok": 1}})
        checks = _by_name(doctor.lab2_checks(evidence, backend=backend))
        assert checks["check_stock written"].passed is True
        assert checks[GRANT].passed is True
        assert checks[GRANT].detail == "stock_agent.py grants check_stock alone"

    @pytest.mark.parametrize("body", [
        "_STOCK_TOOLS = [agent_tools.check_stock, agent_tools.search_products]\n",
        "_STOCK_TOOLS = []\n",
        "pass\n",
    ])
    def test_an_edit_that_is_not_check_stock_alone_fails_and_names_the_grant(
        self, tmp_path: Path, body: str,
    ) -> None:
        backend = _scratch_backend(tmp_path, tool_body="    pass\n", agent_body=body)
        check = _by_name(doctor.lab2_checks(FakeEvidence(), backend=backend))[GRANT]
        assert check.passed is False
        assert check.detail.startswith("stock_agent.py grants ")
        assert check.detail.endswith("Task 2B grants check_stock alone")

    def test_an_edit_the_running_agent_has_not_loaded_says_restart(self, tmp_path: Path) -> None:
        backend = _scratch_backend(tmp_path, tool_body="    pass\n",
                                   agent_body="_STOCK_TOOLS = [agent_tools.check_stock]\n")
        evidence = FakeEvidence({"args->>'agent' = 'stock'": {
            "audit_id": 41, "grant": ["search_products", "browse_department",
                                      "compare_products", "check_stock"]}})
        check = _by_name(doctor.lab2_checks(evidence, backend=backend))[GRANT]
        assert check.passed is False
        assert "(audit 41) held search_products" in check.detail
        assert check.detail.endswith("restart the backend, then ask again")
        loaded = FakeEvidence({"args->>'agent' = 'stock'": {"audit_id": 42,
                                                            "grant": ["check_stock"]}})
        assert _by_name(doctor.lab2_checks(loaded, backend=backend))[GRANT].passed is True

    def test_missing_markers_fail_rather_than_pass(self, tmp_path: Path) -> None:
        backend = _scratch_backend(tmp_path, tool_body="", agent_body="")
        (backend / "services" / "agent_tools.py").write_text("def x(): pass\n", encoding="utf-8")
        checks = _by_name(doctor.lab2_checks(FakeEvidence(), backend=backend))
        assert checks["check_stock written"].passed is False
        assert "markers are missing" in checks["check_stock written"].detail
        (backend / "agents" / "stock_agent.py").write_text("x = 1\n", encoding="utf-8")
        checks = _by_name(doctor.lab2_checks(FakeEvidence(), backend=backend))
        assert "markers are missing" in checks[GRANT].detail


class TestLab1:
    def test_prerequisites_need_no_completed_turn(self) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 2}})
        checks = doctor.run_lab(1, evidence, phase="prerequisites")
        assert len(checks) == 1
        assert checks[0].name == "retrieval receipts record citation snapshots"
        assert checks[0].passed is True

    def test_the_columns_and_a_hybrid_receipt_pass(self) -> None:
        evidence = FakeEvidence(
            {"information_schema": {"n": 2}, "FROM pellier.retrieval_receipts": {"receipt_id": 12}}
        )
        checks = _by_name(doctor.lab1_checks(evidence))
        assert checks["retrieval receipts record citation snapshots"].passed is True
        assert checks["Anna's search receipt"].passed is True
        assert "12" in checks["Anna's search receipt"].detail

    def test_a_missing_receipt_names_anna(self) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 2}})
        check = _by_name(doctor.lab1_checks(evidence))["Anna's search receipt"]
        assert check.passed is False
        assert "choose Anna under Signed in as" in check.detail
        assert "persona-anna-" in evidence.queries[-1][0]

    def test_missing_citation_columns_fail(self) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 1}})
        checks = _by_name(doctor.lab1_checks(evidence))
        assert checks["retrieval receipts record citation snapshots"].passed is False


RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/pellier-abc"


class TestLab3:
    """The rail check asserts the settings ``resolve_rail`` actually reads."""

    def test_the_two_settings_the_backend_reads_pass(self, tmp_path: Path) -> None:
        run_env = tmp_path / "run.env"
        run_env.write_text("USE_AGENTCORE_RUNTIME=true\n", encoding="utf-8")
        env_file = tmp_path / ".env"
        env_file.write_text(f"AGENTCORE_RUNTIME_ENDPOINT={RUNTIME_ARN}\n", encoding="utf-8")
        evidence = FakeEvidence(
            {"caller = 'gateway'": {"turn_id": "turn-theo-ceramics",
                                    "deployed_fingerprint": "a" * 64}}
        )
        checks = _by_name(
            doctor.lab3_checks(
                evidence, run_env=run_env, env_path=env_file, environ={}
            )
        )
        assert checks["service env selects the managed rail"].passed is True
        assert checks["managed tool call recorded with its build"].passed is True

    def test_the_switch_alone_without_an_endpoint_fails(self, tmp_path: Path) -> None:
        """USE_AGENTCORE_RUNTIME=true with no ARN is the degrade-to-in-process case."""
        run_env = tmp_path / "run.env"
        run_env.write_text("USE_AGENTCORE_RUNTIME=true\n", encoding="utf-8")
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                run_env=run_env,
                env_path=tmp_path / "absent.env",
                environ={},
            )
        )
        rail = checks["service env selects the managed rail"]
        assert rail.passed is False
        assert "AGENTCORE_RUNTIME_ENDPOINT" in rail.detail

    def test_an_endpoint_without_the_switch_fails(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(f"AGENTCORE_RUNTIME_ENDPOINT={RUNTIME_ARN}\n", encoding="utf-8")
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                run_env=tmp_path / "absent",
                env_path=env_file,
                environ={},
            )
        )
        rail = checks["service env selects the managed rail"]
        assert rail.passed is False
        assert "USE_AGENTCORE_RUNTIME" in rail.detail

    def test_no_rail_name_variable_can_stand_in_for_the_real_settings(
        self, tmp_path: Path
    ) -> None:
        """Nothing under pellier/backend reads a rail-name key, so it proves nothing."""
        run_env = tmp_path / "run.env"
        run_env.write_text("PELLIER_EXECUTION_RAIL=gateway-mcp\n", encoding="utf-8")
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                run_env=run_env,
                env_path=tmp_path / "absent.env",
                environ={"PELLIER_EXECUTION_RAIL": "gateway-mcp"},
            )
        )
        assert checks["service env selects the managed rail"].passed is False

    def test_process_environment_is_the_fallback(self, tmp_path: Path) -> None:
        environ = {
            "USE_AGENTCORE_RUNTIME": "true",
            "AGENTCORE_RUNTIME_ENDPOINT": RUNTIME_ARN,
        }
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                run_env=tmp_path / "absent",
                env_path=tmp_path / "absent.env",
                environ=environ,
            )
        )
        assert checks["service env selects the managed rail"].passed is True

    def test_run_env_overrides_a_stale_backend_dotenv(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            f"USE_AGENTCORE_RUNTIME=false\nAGENTCORE_RUNTIME_ENDPOINT={RUNTIME_ARN}\n",
            encoding="utf-8",
        )
        run_env = tmp_path / "run.env"
        run_env.write_text("USE_AGENTCORE_RUNTIME=true\n", encoding="utf-8")
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(), run_env=run_env, env_path=env_file, environ={}
            )
        )
        assert checks["service env selects the managed rail"].passed is True

    def test_the_pass_names_the_file_that_set_the_switch(self, tmp_path: Path) -> None:
        """Workshop hosts have no run.env; the PASS must not credit a missing file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            f"USE_AGENTCORE_RUNTIME=true\nAGENTCORE_RUNTIME_ENDPOINT={RUNTIME_ARN}\n",
            encoding="utf-8",
        )
        absent = tmp_path / "etc" / "run.env"
        checks = _by_name(
            doctor.lab3_checks(FakeEvidence(), run_env=absent, env_path=env_file, environ={})
        )
        rail = checks["service env selects the managed rail"]
        assert rail.passed is True
        assert rail.detail == str(env_file)

    def test_the_pass_names_run_env_when_run_env_set_the_switch(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(f"AGENTCORE_RUNTIME_ENDPOINT={RUNTIME_ARN}\n", encoding="utf-8")
        run_env = tmp_path / "run.env"
        run_env.write_text("USE_AGENTCORE_RUNTIME=true\n", encoding="utf-8")
        checks = _by_name(
            doctor.lab3_checks(FakeEvidence(), run_env=run_env, env_path=env_file, environ={})
        )
        assert checks["service env selects the managed rail"].detail == str(run_env)

    def test_the_pass_names_the_process_environment_when_no_file_did(
        self, tmp_path: Path
    ) -> None:
        environ = {"USE_AGENTCORE_RUNTIME": "true", "AGENTCORE_RUNTIME_ENDPOINT": RUNTIME_ARN}
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                run_env=tmp_path / "absent",
                env_path=tmp_path / "absent.env",
                environ=environ,
            )
        )
        assert checks["service env selects the managed rail"].detail == "process environment"

    def test_missing_managed_turn_names_lab3_start(self, tmp_path: Path) -> None:
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                run_env=tmp_path / "absent",
                env_path=tmp_path / "absent.env",
                environ={},
            )
        )
        assert checks["managed tool call recorded with its build"].passed is False
        assert "lab3-start" in checks["managed tool call recorded with its build"].detail


class TestLab3ManagedBuild:
    """Lab 3's proof is the Gateway's own tool_audit row, stamped with the build.

    The Lambda writes a shopper turn's read with the turn id as its session and
    the build the Runtime reported. That row says the managed rail ran and which
    deployed build ran it.
    """

    CHECK = "managed tool call recorded with its build"

    def test_a_stamped_gateway_row_passes(self) -> None:
        evidence = FakeEvidence({"caller = 'gateway'": {
            "turn_id": "turn-theo-ticket", "deployed_fingerprint": "f" * 64}})
        check = doctor._managed_build(evidence)
        assert check.passed is True
        assert check.detail == f"turn turn-theo-ticket ran build {'f' * 12}"

    def test_a_row_without_a_build_names_the_deploy(self) -> None:
        evidence = FakeEvidence({"caller = 'gateway'": {
            "turn_id": "turn-theo-ticket", "deployed_fingerprint": None}})
        check = doctor._managed_build(evidence)
        assert check.passed is False
        assert "deploy your Task 3A change" in check.detail

    def test_no_gateway_row_names_lab3_start(self) -> None:
        check = doctor._managed_build(FakeEvidence())
        assert check.passed is False
        assert "lab3-start.sh" in check.detail

    def test_the_query_reads_only_shopper_turns(self) -> None:
        evidence = FakeEvidence()
        doctor._managed_build(evidence)
        sql = evidence.queries[0][0]
        assert "FROM pellier.tool_audit" in sql
        assert "session_id LIKE 'turn-%'" in sql


class TestLab4:
    NAME = "credit limit passes the Cedar check"

    def test_this_checkout_has_the_policy_but_the_rule_is_unauthored(self) -> None:
        checks = _by_name(doctor.lab4_checks(FakeEvidence()))
        assert checks["Cedar policy present in policies/"].passed is True
        assert checks[self.NAME].passed is False
        assert "starter" in checks[self.NAME].detail

    def _repo_with_rule(self, tmp_path: Path, body: str) -> Path:
        repo = tmp_path / "repo"
        for relative in doctor.POLICY_FILES + (doctor.CEDAR_STARTER,):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        policy = repo / doctor.CEDAR_POLICY
        policy.write_text(policy.read_text(encoding="utf-8").replace(
            "unless {\n  false\n};", f"unless {{\n  {body}\n}};"), encoding="utf-8")
        return repo

    def test_a_rule_that_passes_the_matrix_passes(self, tmp_path: Path) -> None:
        repo = self._repo_with_rule(
            tmp_path, "context.input has amount_cents &&\n  context.input.amount_cents <= 10000")
        checks = _by_name(doctor.lab4_checks(FakeEvidence(), repo=repo))
        assert checks[self.NAME].passed is True
        assert "12 of 12 decisions match" in checks[self.NAME].detail

    def test_an_exclusive_limit_fails_and_says_why(self, tmp_path: Path) -> None:
        repo = self._repo_with_rule(
            tmp_path, "context.input has amount_cents && context.input.amount_cents < 10000")
        check = _by_name(doctor.lab4_checks(FakeEvidence(), repo=repo))[self.NAME]
        assert check.passed is False
        assert "excludes the limit" in check.detail

    def test_row_level_security_on_orders_and_tickets(self) -> None:
        name = "row-level security on orders and support tickets"
        both = FakeEvidence({"relrowsecurity": {"enabled": 2, "n": 2, "policies": 2}})
        assert _by_name(doctor.lab4_checks(both))[name].passed
        partial = FakeEvidence({"relrowsecurity": {"enabled": 1, "n": 2, "policies": 2}})
        assert not _by_name(doctor.lab4_checks(partial))[name].passed
        no_policy = FakeEvidence({"relrowsecurity": {"enabled": 2, "n": 2, "policies": 1}})
        assert not _by_name(doctor.lab4_checks(no_policy))[name].passed

    CREDIT = {
        "credit_id": 1, "approval_id": 3, "customer_id": "CUST-JESSICA",
        "amount_cents": 10000, "approved_cents": 10000,
        "idempotency_key": "operator-review:3:" + "a" * 32,
        "credit_rows": 1, "audit_rows": 1,
    }

    def test_one_credit_and_one_audit_row_for_the_key_pass(self) -> None:
        evidence = FakeEvidence({"FROM pellier.store_credits sc": dict(self.CREDIT)})
        check = doctor._credit_recorded_once(evidence)
        assert check.passed is True
        assert "operator-review:3:" in check.detail

    @pytest.mark.parametrize("change", [
        {"credit_rows": 2}, {"audit_rows": 0}, {"audit_rows": 2}, {"amount_cents": 10001},
    ])
    def test_anything_but_once_for_the_approved_amount_fails(self, change) -> None:
        evidence = FakeEvidence({"FROM pellier.store_credits sc": {**self.CREDIT, **change}})
        check = doctor._credit_recorded_once(evidence)
        assert check.passed is False
        assert "credit row" in check.detail

    def test_no_credit_yet_names_the_operator_step(self) -> None:
        check = doctor._credit_recorded_once(FakeEvidence())
        assert check.passed is False
        assert "Operator" in check.detail


class TestEvidenceLifecycle:
    """The doctor borrows one connection from a shared cluster and gives it back."""

    class _Conn:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def test_leaving_the_context_closes_the_connection(self) -> None:
        conn = self._Conn()
        with doctor.Evidence(conn=conn) as evidence:
            assert evidence.available is True
        assert conn.closed is True

    def test_closing_twice_is_harmless(self) -> None:
        conn = self._Conn()
        evidence = doctor.Evidence(conn=conn)
        evidence.close()
        evidence.close()
        assert conn.closed is True
        assert evidence.available is False

    def test_open_evidence_uses_the_public_connector(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DB_HOST=h\nDB_NAME=n\nDB_USER=u\nDB_PASSWORD=p\n", encoding="utf-8"
        )
        conn = self._Conn()
        monkeypatch.setattr(doctor.workshop_check, "connect", lambda cfg, timeout: conn)
        with doctor.open_evidence(env_file) as evidence:
            assert evidence.available is True
        assert conn.closed is True

    def test_main_returns_the_connection_before_printing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 2}})
        monkeypatch.setattr(doctor, "open_evidence", lambda env_path: evidence)
        doctor.main(["--lab", "1", "--run-env", str(tmp_path / "x")])
        assert evidence.closed is True


class TestMain:
    def test_exit_one_on_any_fail_and_every_line_is_pass_or_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            doctor, "open_evidence", lambda env_path: FakeEvidence({"information_schema": {"n": 2}})
        )
        code = doctor.main(["--lab", "1", "--run-env", str(tmp_path / "x")])
        out = capsys.readouterr().out
        assert code == 1
        lines = [line for line in out.splitlines() if line.startswith(("PASS", "FAIL"))]
        assert len(lines) == 2
        assert any(line.startswith("FAIL") for line in lines)
        assert "Pellier doctor: Lab 1" in out

    def test_exit_zero_when_everything_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows = {
            "information_schema": {"n": 2},
            "FROM pellier.retrieval_receipts": {"receipt_id": 1},
        }
        monkeypatch.setattr(doctor, "open_evidence", lambda env_path: FakeEvidence(rows))
        code = doctor.main(["--lab", "1", "--run-env", str(tmp_path / "x")])
        assert code == 0
        assert "FAIL" not in capsys.readouterr().out


BASH = shutil.which("bash")
CURL = shutil.which("curl")

# A value that executes if the file is sourced instead of parsed. The canary
# path is substituted per test.
CANARY_LINE = "DB_PASSWORD=p$(touch {canary})a(b)`true`"


def _extract_shell_functions(script: Path, *names: str) -> str:
    """Return the named shell functions verbatim, so tests run the real code."""
    source = script.read_text(encoding="utf-8")
    out = []
    for name in names:
        start = source.index(f"{name}() {{")
        end = source.index("\n}\n", start) + len("\n}\n")
        out.append(source[start:end])
    return "\n".join(out)


def _run_upsert(tmp_path: Path, script: Path, target: Path, key: str, value: str) -> int:
    """Run the script's own ``_upsert_env`` against ``target``."""
    body = _extract_shell_functions(script, "_env_target_mode", "_upsert_env")
    program = f'set -uo pipefail\n{body}\n_upsert_env "$1" "$2" "$3"\n'
    result = subprocess.run(
        [BASH, "-c", program, "--", str(target), key, value],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    return result.returncode


# A run of these scripts must depend only on the scratch repo it is pointed at.
# Another test in the same session can leave an AGENTCORE_* or PELLIER_* value
# in os.environ, and the scripts read the process environment.
_SCRUBBED_PREFIXES = ("AGENTCORE_", "PELLIER_", "USE_AGENTCORE", "DB_", "COGNITO_")


def _clean_env(**overrides: str) -> Dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_SCRUBBED_PREFIXES)
    }
    env.update(overrides)
    return env


def _stub_path(tmp_path: Path) -> str:
    """A PATH prefix with inert systemctl, sudo, and psql stubs."""
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    (stubs / "systemctl").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (stubs / "sudo").write_text(
        '#!/bin/sh\nwhile [ "${1#-}" != "$1" ]; do shift; done\nexec "$@"\n', encoding="utf-8"
    )
    # POSIX sh only: the log line must not depend on a bash-only expansion.
    (stubs / "psql").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$PSQL_LOG"\nexit 0\n',
        encoding="utf-8",
    )
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    return f"{stubs}:{os.environ.get('PATH', '')}"


@pytest.mark.skipif(BASH is None, reason="bash not available")
class TestLabEntryPoints:
    """The scripts WP1 aliases as workshop-start, lab3-start, and doctor."""

    SCRIPTS = ("scripts/workshop-start.sh", "scripts/lab3-start.sh")
    BASH4_ONLY = re.compile(r"\$\{[A-Za-z_]+(,,|\^\^|@Q)\}|declare -A|mapfile|readarray")

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_parses_under_the_room_bash(self, relative: str) -> None:
        result = subprocess.run([BASH, "-n", str(REPO / relative)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_uses_no_bash_four_only_expansions(self, relative: str) -> None:
        source = (REPO / relative).read_text(encoding="utf-8")
        assert not self.BASH4_ONLY.search(source)

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_a_dotenv_value_is_data_and_never_executed(
        self, relative: str, tmp_path: Path
    ) -> None:
        """A password with `$(...)` in it must not run when the script loads it."""
        repo = tmp_path / "repo"
        (repo / "pellier" / "backend" / "services").mkdir(parents=True)
        canary = tmp_path / "canary"
        (repo / ".env").write_text(
            "DB_HOST=h\nDB_NAME=n\nDB_USER=u\n"
            + CANARY_LINE.format(canary=canary)
            + "\n",
            encoding="utf-8",
        )
        # No healthy backend and no managed resources, so both scripts stop
        # early. The dotenv load happens first either way.
        result = subprocess.run(
            [BASH, str(REPO / relative)],
            capture_output=True,
            text=True,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                PELLIER_RUN_ENV=str(tmp_path / "run.env"),
                HEALTH_URL=(tmp_path / "absent.json").as_uri(),
                PATH=_stub_path(tmp_path),
            ),
        )
        assert not canary.exists(), f"{relative} executed a dotenv value"
        assert result.returncode == 1, result.stdout + result.stderr


def _rail_target(script: Path, run_env: Path, env_file: Path, explicit: str) -> str:
    """Run lab3-start.sh's own ``_rail_target``."""
    body = _extract_shell_functions(script, "_rail_target")
    program = f'set -uo pipefail\n{body}\n_rail_target "$1" "$2" "$3"\n'
    result = subprocess.run(
        [BASH, "-c", program, "--", str(run_env), str(env_file), explicit],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.skipif(BASH is None, reason="bash not available")
class TestRailTarget:
    """Where lab3-start.sh writes USE_AGENTCORE_RUNTIME=true."""

    SCRIPT = REPO / "scripts" / "lab3-start.sh"

    def test_a_host_without_etc_pellier_writes_the_repo_env(self, tmp_path: Path) -> None:
        """Workshop Studio hosts: no /etc/pellier, so no warning and no fallback."""
        env_file = tmp_path / ".env"
        run_env = tmp_path / "etc" / "pellier" / "run.env"
        assert _rail_target(self.SCRIPT, run_env, env_file, "") == str(env_file)

    def test_a_host_with_etc_pellier_keeps_run_env(self, tmp_path: Path) -> None:
        (tmp_path / "etc" / "pellier").mkdir(parents=True)
        run_env = tmp_path / "etc" / "pellier" / "run.env"
        assert _rail_target(self.SCRIPT, run_env, tmp_path / ".env", "") == str(run_env)

    def test_an_explicit_run_env_is_honoured(self, tmp_path: Path) -> None:
        run_env = tmp_path / "missing" / "run.env"
        assert _rail_target(self.SCRIPT, run_env, tmp_path / ".env", str(run_env)) == str(
            run_env
        )


@pytest.mark.skipif(BASH is None, reason="bash not available")
class TestEnvUpsert:
    """Rewriting an env file must not widen its mode or lose its other keys."""

    SCRIPTS = ("scripts/lab3-start.sh",)

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_a_six_hundred_target_stays_six_hundred(
        self, relative: str, tmp_path: Path
    ) -> None:
        """bootstrap-labs.sh creates the repo .env 0600; it holds DB_PASSWORD."""
        target = tmp_path / ".env"
        target.write_text("DB_PASSWORD=s3cret\nCOGNITO_CLIENT_SECRET=shh\n", encoding="utf-8")
        target.chmod(0o600)
        assert _run_upsert(tmp_path, REPO / relative, target, "PELLIER_EXAMPLE", "run-a") == 0
        assert oct(target.stat().st_mode & 0o777) == "0o600"
        body = target.read_text(encoding="utf-8")
        assert "DB_PASSWORD=s3cret" in body
        assert "COGNITO_CLIENT_SECRET=shh" in body
        assert "PELLIER_EXAMPLE=run-a" in body

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_a_new_file_is_owner_only(self, relative: str, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "run.env"
        assert _run_upsert(tmp_path, REPO / relative, target, "PELLIER_EXAMPLE", "run-a") == 0
        assert oct(target.stat().st_mode & 0o777) == "0o600"

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_an_existing_mode_is_preserved(self, relative: str, tmp_path: Path) -> None:
        target = tmp_path / "run.env"
        target.write_text("KEEP=1\n", encoding="utf-8")
        target.chmod(0o640)
        assert _run_upsert(tmp_path, REPO / relative, target, "PELLIER_EXAMPLE", "run-a") == 0
        assert oct(target.stat().st_mode & 0o777) == "0o640"

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_the_export_form_of_the_key_is_replaced_too(
        self, relative: str, tmp_path: Path
    ) -> None:
        """The shared dotenv parser accepts `export KEY=`, so a stale one wins."""
        target = tmp_path / "run.env"
        target.write_text(
            "export USE_AGENTCORE_RUNTIME=false\nOTHER=keep\n", encoding="utf-8"
        )
        assert (
            _run_upsert(tmp_path, REPO / relative, target, "USE_AGENTCORE_RUNTIME", "true") == 0
        )
        body = target.read_text(encoding="utf-8")
        assert "false" not in body
        assert body.count("USE_AGENTCORE_RUNTIME") == 1
        assert "OTHER=keep" in body

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_an_unreadable_target_fails_instead_of_truncating(
        self, relative: str, tmp_path: Path
    ) -> None:
        if os.geteuid() == 0:
            pytest.skip("root reads every file")
        target = tmp_path / ".env"
        target.write_text("DB_PASSWORD=s3cret\n", encoding="utf-8")
        target.chmod(0o000)
        try:
            assert _run_upsert(tmp_path, REPO / relative, target, "K", "v") != 0
            target.chmod(0o600)
            assert target.read_text(encoding="utf-8") == "DB_PASSWORD=s3cret\n"
        finally:
            target.chmod(0o600)


@pytest.mark.skipif(BASH is None, reason="bash not available")
class TestLab3Start:
    def test_it_refuses_without_both_managed_resources(self, tmp_path: Path) -> None:
        """No Gateway and no Runtime ARN: the switch must not be written at all."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("DB_HOST=h\n", encoding="utf-8")
        run_env = tmp_path / "run.env"
        result = subprocess.run(
            [BASH, str(REPO / "scripts/lab3-start.sh")],
            capture_output=True,
            text=True,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                PELLIER_RUN_ENV=str(run_env),
                PATH=_stub_path(tmp_path),
            ),
        )
        assert result.returncode == 1
        assert "AGENTCORE_GATEWAY_URL" in result.stderr
        assert "AGENTCORE_RUNTIME_ENDPOINT" in result.stderr
        assert "Refusing to switch rails" in result.stderr
        assert not run_env.exists(), "the rail switch was written despite the refusal"

    def test_an_unvalidated_receipt_stops_before_the_switch(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text(
            "AGENTCORE_GATEWAY_URL=https://gw.example/mcp\n"
            "AGENTCORE_RUNTIME_ENDPOINT=arn:aws:bedrock-agentcore:us-east-1:1:runtime/x\n",
            encoding="utf-8",
        )
        run_env = tmp_path / "run.env"
        result = subprocess.run(
            [BASH, str(REPO / "scripts/lab3-start.sh")],
            capture_output=True,
            text=True,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                PELLIER_RUN_ENV=str(run_env),
                AGENTCORE_MANAGED_OUTPUT_JSON=str(tmp_path / "absent.json"),
                PATH=_stub_path(tmp_path),
            ),
        )
        assert result.returncode == 1
        assert "receipt" in result.stderr.lower()
        assert not run_env.exists()

    def test_it_names_no_variable_the_backend_does_not_read(self) -> None:
        """resolve_rail reads USE_AGENTCORE_RUNTIME; no key names a rail."""
        source = (REPO / "scripts/lab3-start.sh").read_text(encoding="utf-8")
        assert "PELLIER_EXECUTION_RAIL" not in source
        assert "USE_AGENTCORE_RUNTIME" in source

    def test_a_failed_proof_names_what_was_written_and_how_to_revert(self) -> None:
        """Minor 4 is accepted, so the message must carry the participant out."""
        source = (REPO / "scripts/lab3-start.sh").read_text(encoding="utf-8")
        marker = source.index("_revert_hint()")
        body = source[marker : source.index("\n}\n", marker)]
        assert "USE_AGENTCORE_RUNTIME=false" in body
        assert "systemctl restart pellier" in body


@pytest.mark.skipif(BASH is None or CURL is None, reason="bash and curl required")
class TestWorkshopStart:
    """One command checks the box before Lab 1 and touches no table."""

    def _run(self, tmp_path: Path, health_body: Optional[str]) -> Any:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("DB_HOST=h\nDB_NAME=n\nDB_USER=u\n", encoding="utf-8")
        health = tmp_path / "health.json"
        if health_body is not None:
            health.write_text(health_body, encoding="utf-8")
        psql_log = tmp_path / "psql.log"
        result = subprocess.run(
            [BASH, str(REPO / "scripts/workshop-start.sh"), "anna"],
            capture_output=True,
            text=True,
            timeout=120,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                HEALTH_URL=health.as_uri(),
                PSQL_LOG=str(psql_log),
                PATH=_stub_path(tmp_path),
            ),
        )
        return result, psql_log

    def test_a_healthy_backend_is_ready_for_lab_one(self, tmp_path: Path) -> None:
        result, psql_log = self._run(tmp_path, '{"status": "healthy"}')
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Ready for Lab 1" in result.stdout
        assert not psql_log.exists(), "workshop-start wrote to the database"

    def test_an_unhealthy_backend_fails_loudly(self, tmp_path: Path) -> None:
        result, _ = self._run(tmp_path, None)
        assert result.returncode == 1
        assert "start-backend" in result.stderr


class TestManagedCataloguesAgree:
    """Lab 3A, checked from source before anything is deployed.

    The mismatch this catches does not look like a failure in the room. An
    unpublished read is left out of the Support agent, which tells Theo it
    can't look up his tickets here: a turn that works and answers nothing.
    Naming the outstanding step beats letting them read a trace.
    """

    def _check(self, monkeypatch, *, published, managed, bound):
        monkeypatch.setattr(doctor.lab3_check, "source_catalogue",
                            lambda: (frozenset(published), tuple(managed), frozenset(bound)))
        return doctor._managed_catalogues_agree()

    def test_an_unpublished_read_names_the_publication_step(self, monkeypatch):
        check = self._check(
            monkeypatch,
            published={"get_return_policy"},
            managed=("get_return_policy", "get_tickets"),
            bound=set(),
        )
        assert not check.passed
        assert "get_tickets, which is not published on the Gateway" in check.detail
        assert "Gateway catalogue - published tools" in check.detail

    def test_a_staff_only_tool_on_the_support_agent_fails(self, monkeypatch):
        check = self._check(
            monkeypatch,
            published={"get_return_policy", "get_tickets", "give_store_credit"},
            managed=("get_return_policy", "get_tickets", "give_store_credit"),
            bound={"get_tickets"},
        )
        assert not check.passed
        assert "staff-only tool give_store_credit" in check.detail

    def test_an_unbound_read_is_its_own_failure(self, monkeypatch):
        """Published and reachable is not enough: the caller must be bound."""
        check = self._check(
            monkeypatch,
            published={"get_return_policy", "get_tickets"},
            managed=("get_return_policy", "get_tickets"),
            bound=set(),
        )
        assert not check.passed
        assert "not bound to the signed-in caller" in check.detail
        assert "SUPPORT_CALLER_BOUND_TOOLS" in check.detail

    def test_both_builds_done_passes_with_the_published_count(self, monkeypatch):
        published = {"search_products", "browse_department", "compare_products", "check_stock",
                     "get_orders", "get_return_policy", "get_tickets", "give_store_credit",
                     "ask_a_person"}
        check = self._check(
            monkeypatch,
            published=published,
            managed=("get_orders", "get_return_policy", "get_tickets", "ask_a_person"),
            bound={"get_tickets"},
        )
        assert check.passed
        assert check.detail == "9 tools published, get_tickets bound to the signed-in caller"

    def test_an_unreadable_catalogue_fails_rather_than_crashes(self, monkeypatch):
        """The doctor runs when things are broken. It must not be one of them."""
        def boom():
            raise ModuleNotFoundError("gateway_tool_schemas")

        monkeypatch.setattr(doctor.lab3_check, "source_catalogue", boom)
        check = doctor._managed_catalogues_agree()
        assert not check.passed
        assert "could not read the catalogues" in check.detail
