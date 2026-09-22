"""The doctor names the prerequisite a stuck participant has not met, per lab.

Every check is a pure function over injected inputs (a fake evidence surface,
a scratch repository, a scratch env file), so the whole contract runs offline.
The last class pins the two shell entry points that sit beside the doctor:
they must parse under bash 3.2 and read configuration through the shared
dotenv parser rather than sourcing a secret as shell.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "workshop_doctor.py"
RUN_ID = "run-0123456789ab"


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


_NAMED_PARAM = re.compile(r"%\((\w+)\)s")


class SqlEvidence:
    """Runs the doctor's real SQL over fixture rows, in SQLite.

    ``FakeEvidence`` answers by SQL fragment, so it cannot catch a predicate no
    row a real writer produces can satisfy. The Lab 3 query is ordinary SQL plus
    the JSON ``->>`` operator, and SQLite understands both once the ``pellier``
    schema is attached as a database and psycopg's ``%(name)s`` is rewritten to
    ``:name``. The columns below are the ones the real writers populate
    (``services/tool_audit_writer.py``, ``scripts/deploy/common/dataapi.py``,
    ``services/governed_turn_receipt.py``) plus migration 049's ``run_id``.
    """

    def __init__(self) -> None:
        self.reason = ""
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("ATTACH DATABASE ':memory:' AS pellier")
        self._conn.execute(
            "CREATE TABLE pellier.tool_audit ("
            "audit_id INTEGER PRIMARY KEY, session_id TEXT, tool TEXT, caller TEXT, "
            "args TEXT, result TEXT, latency_ms INTEGER, run_id TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE pellier.governed_turn_receipts ("
            "turn_id TEXT PRIMARY KEY, session_id TEXT, principal_sub TEXT, rail TEXT, "
            "terminal_status TEXT, created_at TEXT, run_id TEXT)"
        )

    @property
    def available(self) -> bool:
        return True

    def turn(
        self,
        *,
        turn_id: str,
        run_id: Optional[str],
        rail: str = "gateway-mcp",
        created_at: str = "2026-09-04T10:00:00Z",
    ) -> None:
        """Record the turn receipt the application pool writes for one turn."""
        self._conn.execute(
            "INSERT INTO pellier.governed_turn_receipts "
            "(turn_id, session_id, principal_sub, rail, terminal_status, created_at, "
            "run_id) "
            "VALUES (?, 'lab3-start-1', 'sub-theo', ?, 'complete', ?, ?)",
            (turn_id, rail, created_at, run_id),
        )

    def audit(
        self,
        *,
        audit_id: int,
        caller: str,
        turn_id: str,
        run_id: Optional[str] = None,
        tool: str = "initiate_return",
    ) -> None:
        """Record one tool_audit row. ``run_id`` defaults to the Lambda's NULL."""
        self._conn.execute(
            "INSERT INTO pellier.tool_audit "
            "(audit_id, session_id, tool, caller, args, result, latency_ms, run_id) "
            "VALUES (?, 'gateway-CUST-THEO', ?, ?, ?, '{}', 412, ?)",
            (audit_id, tool, caller, json.dumps({"turn_id": turn_id}), run_id),
        )

    def one(
        self, sql: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute(_NAMED_PARAM.sub(r":\1", sql), dict(params or {}))
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqlEvidence":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False



WIRED_TOOL = (
    "    # === WORKSHOP · Inventory Agent · check_inventory: START ===\n"
    "    if _db_service is None:\n"
    "        return json.dumps({'error': 'db unavailable'})\n"
    "    from services.business_logic import BusinessLogic\n"
    "    logic = BusinessLogic(_db_service)\n"
    "    result = _run_async(logic.check_inventory(product_query.strip() or None))\n"
    "    return json.dumps(result, indent=2)\n"
    "    # === WORKSHOP · Inventory Agent · check_inventory: END ===\n"
)


def _scratch_backend(tmp_path: Path, *, tool_source: str, agent_stubbed: bool) -> Path:
    backend = tmp_path / "backend"
    (backend / "services").mkdir(parents=True)
    (backend / "agents").mkdir()
    (backend / "services" / "agent_tools.py").write_text(tool_source, encoding="utf-8")
    flag = "True" if agent_stubbed else "False"
    (backend / "agents" / "inventory_agent.py").write_text(
        f"_INVENTORY_AGENT_STUBBED = {flag}\n", encoding="utf-8"
    )
    return backend


class TestLab1:
    def test_unreachable_database_fails_with_the_reason(self) -> None:
        checks = doctor.lab1_checks(FakeEvidence(reason="connection refused"))
        db = _by_name(checks)["database reachable"]
        assert db.passed is False
        assert "connection refused" in db.detail

    def test_this_checkout_still_ships_both_lab_one_stubs(self) -> None:
        checks = _by_name(doctor.lab1_checks(FakeEvidence({"SELECT 1": {"ok": 1}})))
        assert checks["database reachable"].passed is True
        assert checks["check_inventory wired"].passed is False
        assert checks["Inventory Agent defined"].passed is False

    def test_a_wired_tool_and_agent_pass(self, tmp_path: Path) -> None:
        backend = _scratch_backend(tmp_path, tool_source=WIRED_TOOL, agent_stubbed=False)
        checks = _by_name(
            doctor.lab1_checks(FakeEvidence({"SELECT 1": {"ok": 1}}), backend=backend)
        )
        assert checks["check_inventory wired"].passed is True
        assert checks["Inventory Agent defined"].passed is True

    def test_a_block_that_dropped_the_stub_but_queries_nothing_is_not_wired(
        self, tmp_path: Path
    ) -> None:
        hollow = WIRED_TOOL.replace(
            "    result = _run_async(logic.check_inventory(product_query.strip() or None))\n"
            "    return json.dumps(result, indent=2)\n",
            "    return json.dumps({})\n",
        )
        backend = _scratch_backend(tmp_path, tool_source=hollow, agent_stubbed=False)
        checks = _by_name(doctor.lab1_checks(FakeEvidence(), backend=backend))
        assert checks["check_inventory wired"].passed is False
        assert "no query" in checks["check_inventory wired"].detail

    def test_prose_containing_the_word_selected_is_not_a_query(
        self, tmp_path: Path
    ) -> None:
        """`selected` and `selection` are not SELECT, and a stub may say either."""
        prose = WIRED_TOOL.replace(
            "    from services.business_logic import BusinessLogic\n"
            "    logic = BusinessLogic(_db_service)\n"
            "    result = _run_async(logic.check_inventory(product_query.strip() or None))\n"
            "    return json.dumps(result, indent=2)\n",
            "    return json.dumps({'note': 'selected nothing', 'selection': []})\n",
        )
        backend = _scratch_backend(tmp_path, tool_source=prose, agent_stubbed=False)
        checks = _by_name(doctor.lab1_checks(FakeEvidence(), backend=backend))
        assert checks["check_inventory wired"].passed is False
        assert "no query" in checks["check_inventory wired"].detail

    def test_missing_markers_fail_rather_than_pass(self, tmp_path: Path) -> None:
        backend = _scratch_backend(tmp_path, tool_source="def x(): pass\n", agent_stubbed=False)
        checks = _by_name(doctor.lab1_checks(FakeEvidence(), backend=backend))
        assert checks["check_inventory wired"].passed is False
        assert "marker" in checks["check_inventory wired"].detail


class TestLab2:
    def test_prerequisites_do_not_require_a_completed_run(self) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 2}})
        checks = doctor.run_lab(2, evidence, None, phase="prerequisites")
        assert len(checks) == 1
        assert checks[0].name == "migration 046 columns present"
        assert checks[0].passed is True

    def test_no_run_id_names_the_start_script(self) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 2}})
        checks = _by_name(doctor.lab2_checks(evidence, None))
        assert checks["retrieval receipt for this run"].passed is False
        assert "workshop-start" in checks["retrieval receipt for this run"].detail

    def test_migration_046_and_a_receipt_pass(self) -> None:
        evidence = FakeEvidence(
            {"information_schema": {"n": 2}, "FROM pellier.retrieval_receipts": {"receipt_id": 12}}
        )
        checks = _by_name(doctor.lab2_checks(evidence, RUN_ID))
        assert checks["migration 046 columns present"].passed is True
        assert checks["retrieval receipt for this run"].passed is True
        assert "12" in checks["retrieval receipt for this run"].detail
        # The receipt query is scoped to the run, never to whatever is newest.
        receipt_query = next(
            q for q in evidence.queries if "FROM pellier.retrieval_receipts" in q[0]
        )
        assert "run_id = %(run)s" in receipt_query[0]
        assert receipt_query[1] == {"run": RUN_ID}

    def test_a_partial_046_fails(self) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 1}})
        checks = _by_name(doctor.lab2_checks(evidence, RUN_ID))
        assert checks["migration 046 columns present"].passed is False


RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/pellier-abc"


class TestLab3:
    """The rail check asserts the settings ``resolve_rail`` actually reads."""

    def test_the_two_settings_the_backend_reads_pass(self, tmp_path: Path) -> None:
        run_env = tmp_path / "run.env"
        run_env.write_text(
            "PELLIER_RUN_ID=run-0123456789ab\nUSE_AGENTCORE_RUNTIME=true\n",
            encoding="utf-8",
        )
        env_file = tmp_path / ".env"
        env_file.write_text(f"AGENTCORE_RUNTIME_ENDPOINT={RUNTIME_ARN}\n", encoding="utf-8")
        evidence = FakeEvidence(
            {
                "rail = 'gateway-mcp'": {"turn_id": "turn-theo-ceramics"},
                "memory_record_ids_used": {"receipt_id": 9},
            }
        )
        checks = _by_name(
            doctor.lab3_checks(
                evidence, RUN_ID, run_env=run_env, env_path=env_file, environ={}
            )
        )
        assert checks["service env selects the managed rail"].passed is True
        assert checks["managed-rail turn receipt for this run"].passed is True
        assert checks["memory informed a turn in this run"].passed is True

    def test_the_switch_alone_without_an_endpoint_fails(self, tmp_path: Path) -> None:
        """USE_AGENTCORE_RUNTIME=true with no ARN is the degrade-to-in-process case."""
        run_env = tmp_path / "run.env"
        run_env.write_text("USE_AGENTCORE_RUNTIME=true\n", encoding="utf-8")
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                RUN_ID,
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
                RUN_ID,
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
                RUN_ID,
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
                RUN_ID,
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
                FakeEvidence(), RUN_ID, run_env=run_env, env_path=env_file, environ={}
            )
        )
        assert checks["service env selects the managed rail"].passed is True

    def test_missing_managed_turn_names_lab3_start(self, tmp_path: Path) -> None:
        checks = _by_name(
            doctor.lab3_checks(
                FakeEvidence(),
                RUN_ID,
                run_env=tmp_path / "absent",
                env_path=tmp_path / "absent.env",
                environ={},
            )
        )
        assert checks["managed-rail turn receipt for this run"].passed is False
        assert "lab3-start" in checks["managed-rail turn receipt for this run"].detail


class TestLab3GatewayEvidenceShape:
    """The Lab 3 check must match the rows Lab 3 as designed actually leaves.

    Lab 3 is the managed rail, and Theo's journey ends at a pending review
    (``tests/golden/journeys.json``: ``endsAt: proposal``). It performs no
    mutation, and only the three mutation tools leave a ``caller = 'gateway'``
    row -- the MCP Lambda audits them in
    ``scripts/deploy/common/dataapi.py``, while Gateway reads leave no
    ``tool_audit`` row at all. A Lab 3 check that demanded that row could not be
    satisfied by completing Lab 3.

    What the managed rail does leave is the turn receipt itself.
    ``governed_turn_receipts`` is written through the application pool
    (``services/governed_turn_receipt.py::persist_turn_receipt``), so migration
    049's DEFAULT stamps the run on it, and its ``rail`` column records the rail
    that served the turn. That row is the rail proof. When a mutation happens to
    have run as well, its Lambda-written ``tool_audit`` row carries a NULL
    ``run_id`` and is reported as detail, never required.
    """

    RAIL_CHECK = "managed-rail turn receipt for this run"

    def _checks(self, evidence: Any, tmp_path: Path) -> Dict[str, Any]:
        return _by_name(
            doctor.lab3_checks(
                evidence,
                RUN_ID,
                run_env=tmp_path / "absent",
                env_path=tmp_path / "absent.env",
                environ={},
            )
        )

    def test_lab3_as_designed_passes_with_no_mutation_anywhere(
        self, tmp_path: Path
    ) -> None:
        """Theo's journey ends at a proposal, so the run has no gateway row."""
        with SqlEvidence() as evidence:
            evidence.turn(turn_id="turn-theo-ceramics", run_id=RUN_ID)
            check = self._checks(evidence, tmp_path)[self.RAIL_CHECK]
        assert check.passed is True, check.detail
        assert check.detail == "turn_id=turn-theo-ceramics"

    def test_a_managed_turn_passes_though_the_lambda_row_carries_no_run_id(
        self, tmp_path: Path
    ) -> None:
        with SqlEvidence() as evidence:
            evidence.turn(turn_id="turn-theo-return", run_id=RUN_ID)
            evidence.audit(audit_id=4127, caller="gateway", turn_id="turn-theo-return")
            check = self._checks(evidence, tmp_path)[self.RAIL_CHECK]
        assert check.passed is True, check.detail
        assert check.detail == "turn_id=turn-theo-return"

    def test_a_managed_turn_from_another_run_does_not_count(self, tmp_path: Path) -> None:
        with SqlEvidence() as evidence:
            evidence.turn(turn_id="turn-someone-else", run_id="run-ffffffffffff")
            evidence.audit(audit_id=99, caller="gateway", turn_id="turn-someone-else")
            check = self._checks(evidence, tmp_path)[self.RAIL_CHECK]
        assert check.passed is False

    def test_an_in_process_turn_in_this_run_does_not_count(self, tmp_path: Path) -> None:
        """The check cannot pass vacuously: an unswitched run still fails it."""
        with SqlEvidence() as evidence:
            evidence.turn(turn_id="turn-in-process", run_id=RUN_ID, rail="in-process")
            evidence.audit(
                audit_id=7,
                caller="agent",
                turn_id="turn-in-process",
                run_id=RUN_ID,
            )
            check = self._checks(evidence, tmp_path)[self.RAIL_CHECK]
        assert check.passed is False
        assert "lab3-start" in check.detail

    def test_the_hint_names_an_action_a_participant_can_take(
        self, tmp_path: Path
    ) -> None:
        """No Theo turn performs a return, so the hint must not send them to one."""
        with SqlEvidence() as evidence:
            check = self._checks(evidence, tmp_path)[self.RAIL_CHECK]
        assert check.passed is False
        assert "lab3-start.sh" in check.detail
        assert "return" not in check.detail


class TestLab4:
    def test_this_checkout_has_the_pair_but_the_rule_is_unauthored(self) -> None:
        checks = _by_name(doctor.lab4_checks(FakeEvidence(), RUN_ID))
        assert checks["Cedar policy pair present in policies/"].passed is True
        assert checks["identity rule authored"].passed is False
        assert "starter" in checks["identity rule authored"].detail

    def test_an_authored_rule_passes(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        for relative in doctor.POLICY_FILES + (doctor.CEDAR_STARTER,):
            source = REPO / relative
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        policy = repo / doctor.CEDAR_POLICY
        policy.write_text(
            policy.read_text(encoding="utf-8").replace(
                "unless {\n  false\n};",
                'unless {\n  principal.hasTag("username") &&\n'
                '  principal.getTag("username") == context.input.customer_id\n};',
            ),
            encoding="utf-8",
        )
        checks = _by_name(doctor.lab4_checks(FakeEvidence(), RUN_ID, repo=repo))
        assert checks["identity rule authored"].passed is True

    def test_rls_on_orders_and_returns(self) -> None:
        both = FakeEvidence({"relrowsecurity": {"enabled": True, "n": 2}})
        rls_name = "RLS enabled on orders and returns"
        assert _by_name(doctor.lab4_checks(both, RUN_ID))[rls_name].passed
        partial = FakeEvidence({"relrowsecurity": {"enabled": False, "n": 2}})
        check = _by_name(doctor.lab4_checks(partial, RUN_ID))[rls_name]
        assert check.passed is False

    def test_operator_execution_is_not_a_lab_four_requirement(self) -> None:
        evidence = FakeEvidence({"execution_receipts": {"receipt_id": 3}})
        checks = _by_name(doctor.lab4_checks(evidence, RUN_ID))
        check = checks["Jessica Gateway decision chain for this run"]
        assert check.passed is False
        assert "pending human checkpoint" in check.detail
        assert all("execution_receipts" not in sql for sql, _ in evidence.queries)

    def test_keyed_gateway_evidence_satisfies_lab_four(self) -> None:
        rows = [
            {"principal_label": name, "decision": "DENY", "args": {"customer_id": "CUST-JESSICA"},
             "declared_key": f"deny-{name}", "audit_id": None, "policy_name": "ownership"}
            for name in ("marco",)
        ]
        rows.append({"principal_label": "jessica", "decision": "ALLOW",
                     "args": {"customer_id": "CUST-JESSICA"}, "audit_id": 5,
                     "completed_at": "2026-09-06", "idempotency_key": "allow-jessica", "policy_name": "ownership"})
        evidence = FakeEvidence({
            "WITH decisions": {"rows": rows},
            "AS execution_rows": {"execution_rows": 0, "write_rows": 0, "completed_writes": 0, "ledger_rows": 0},
        })
        assert doctor._governance_chain(evidence, RUN_ID).passed
        rows[0]["declared_key"] = ""
        assert not doctor._governance_chain(evidence, RUN_ID).passed

    @pytest.mark.parametrize(
        ("denied_principal", "allowed_principal", "customer"),
        [
            ("anna", "jessica", "CUST-JESSICA"),
            ("marco", "theo", "CUST-JESSICA"),
            ("marco", "jessica", "CUST-THEO"),
        ],
    )
    def test_other_principals_or_customers_cannot_replace_the_lab_four_cases(
        self, denied_principal: str, allowed_principal: str, customer: str
    ) -> None:
        rows = [
            {"principal_label": denied_principal, "decision": "DENY",
             "args": {"customer_id": customer}, "declared_key": "denied",
             "audit_id": None, "policy_name": "ownership"},
            {"principal_label": allowed_principal, "decision": "ALLOW",
             "args": {"customer_id": customer}, "audit_id": 5,
             "completed_at": "2026-09-10", "idempotency_key": "allowed",
             "policy_name": "ownership"},
        ]
        evidence = FakeEvidence({
            "WITH decisions": {"rows": rows},
            "AS execution_rows": {
                "execution_rows": 0, "write_rows": 0,
                "completed_writes": 0, "ledger_rows": 0,
            },
        })
        assert not doctor._governance_chain(evidence, RUN_ID).passed



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
        monkeypatch.setattr(
            doctor.build_receipt, "psycopg_connector", lambda: (lambda dsn: conn)
        )
        with doctor.open_evidence(env_file) as evidence:
            assert evidence.available is True
        assert conn.closed is True

    def test_main_returns_the_connection_before_printing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        evidence = FakeEvidence({"information_schema": {"n": 2}})
        monkeypatch.setattr(doctor, "open_evidence", lambda env_path: evidence)
        doctor.main(["--lab", "2", "--run-id", RUN_ID, "--run-env", str(tmp_path / "x")])
        assert evidence.closed is True


class TestMain:
    def test_exit_one_on_any_fail_and_every_line_is_pass_or_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            doctor, "open_evidence", lambda env_path: FakeEvidence({"information_schema": {"n": 2}})
        )
        code = doctor.main(["--lab", "2", "--run-id", RUN_ID, "--run-env", str(tmp_path / "x")])
        out = capsys.readouterr().out
        assert code == 1
        lines = [line for line in out.splitlines() if line.startswith(("PASS", "FAIL"))]
        assert len(lines) == 2
        assert any(line.startswith("FAIL") for line in lines)
        assert RUN_ID in out

    def test_exit_zero_when_everything_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows = {
            "information_schema": {"n": 2},
            "FROM pellier.retrieval_receipts": {"receipt_id": 1},
        }
        monkeypatch.setattr(doctor, "open_evidence", lambda env_path: FakeEvidence(rows))
        code = doctor.main(["--lab", "2", "--run-id", RUN_ID, "--run-env", str(tmp_path / "x")])
        assert code == 0
        assert "FAIL" not in capsys.readouterr().out

    def test_malformed_run_id_is_refused_before_any_query(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert doctor.main(["--lab", "2", "--run-id", "run-nope"]) == 2
        assert "run-<12 hex>" in capsys.readouterr().err


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
        # No mintable run id and no managed resources, so both scripts stop
        # early. The dotenv load happens first either way.
        (repo / "pellier" / "backend" / "services" / "workshop_run.py").write_text(
            "import sys\nsys.exit(1)\n", encoding="utf-8"
        )
        result = subprocess.run(
            [BASH, str(REPO / relative)],
            capture_output=True,
            text=True,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                PELLIER_RUN_ENV=str(tmp_path / "run.env"),
                PELLIER_PYTHON=sys.executable,
                PATH=_stub_path(tmp_path),
            ),
        )
        assert not canary.exists(), f"{relative} executed a dotenv value"
        assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.skipif(BASH is None, reason="bash not available")
class TestEnvUpsert:
    """Rewriting an env file must not widen its mode or lose its other keys."""

    SCRIPTS = ("scripts/workshop-start.sh", "scripts/lab3-start.sh")

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_a_six_hundred_target_stays_six_hundred(
        self, relative: str, tmp_path: Path
    ) -> None:
        """bootstrap-labs.sh creates the repo .env 0600; it holds DB_PASSWORD."""
        target = tmp_path / ".env"
        target.write_text("DB_PASSWORD=s3cret\nCOGNITO_CLIENT_SECRET=shh\n", encoding="utf-8")
        target.chmod(0o600)
        assert _run_upsert(tmp_path, REPO / relative, target, "PELLIER_RUN_ID", "run-a") == 0
        assert oct(target.stat().st_mode & 0o777) == "0o600"
        body = target.read_text(encoding="utf-8")
        assert "DB_PASSWORD=s3cret" in body
        assert "COGNITO_CLIENT_SECRET=shh" in body
        assert "PELLIER_RUN_ID=run-a" in body

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_a_new_file_is_owner_only(self, relative: str, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "run.env"
        assert _run_upsert(tmp_path, REPO / relative, target, "PELLIER_RUN_ID", "run-a") == 0
        assert oct(target.stat().st_mode & 0o777) == "0o600"

    @pytest.mark.parametrize("relative", SCRIPTS)
    def test_an_existing_mode_is_preserved(self, relative: str, tmp_path: Path) -> None:
        target = tmp_path / "run.env"
        target.write_text("KEEP=1\n", encoding="utf-8")
        target.chmod(0o640)
        assert _run_upsert(tmp_path, REPO / relative, target, "PELLIER_RUN_ID", "run-a") == 0
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
    """One command mints, records idempotently, and exports the run id."""

    FAKE_RUN_ID = "run-0123456789ab"

    def _repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        services = repo / "pellier" / "backend" / "services"
        services.mkdir(parents=True)
        (repo / ".env").write_text(
            "DB_HOST=h\nDB_NAME=n\nDB_USER=u\nDB_PASSWORD=p\n", encoding="utf-8"
        )
        state = tmp_path / "minted"
        (services / "workshop_run.py").write_text(
            "import pathlib, sys\n"
            f"state = pathlib.Path({str(state)!r})\n"
            f"run_id = {self.FAKE_RUN_ID!r}\n"
            "if sys.argv[1] == 'current':\n"
            "    if not state.exists():\n"
            "        sys.exit(1)\n"
            "    print(state.read_text().strip())\n"
            "else:\n"
            "    state.write_text(run_id)\n"
            "    print(run_id)\n",
            encoding="utf-8",
        )
        return repo

    def _run(self, tmp_path: Path, repo: Path, run_env: Path, psql_log: Path) -> Any:
        health = tmp_path / "health.json"
        health.write_text('{"status": "healthy"}', encoding="utf-8")
        return subprocess.run(
            [BASH, str(REPO / "scripts/workshop-start.sh"), "anna"],
            capture_output=True,
            text=True,
            timeout=120,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                PELLIER_RUN_ENV=str(run_env),
                PELLIER_PYTHON=sys.executable,
                HEALTH_URL=health.as_uri(),
                PSQL_LOG=str(psql_log),
                PATH=_stub_path(tmp_path),
            ),
        )

    def test_it_mints_records_and_exports_the_run(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        run_env = tmp_path / "run.env"
        psql_log = tmp_path / "psql.log"
        first = self._run(tmp_path, repo, run_env, psql_log)
        assert first.returncode == 0, first.stdout + first.stderr
        assert self.FAKE_RUN_ID in first.stdout
        recorded = psql_log.read_text(encoding="utf-8")
        assert "INSERT INTO pellier.workshop_runs" in recorded
        assert "ON CONFLICT (run_id) DO NOTHING" in recorded
        assert self.FAKE_RUN_ID in recorded
        assert f"PELLIER_RUN_ID={self.FAKE_RUN_ID}" in run_env.read_text(encoding="utf-8")

    def test_a_second_run_reuses_the_same_id(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        run_env = tmp_path / "run.env"
        psql_log = tmp_path / "psql.log"
        self._run(tmp_path, repo, run_env, psql_log)
        second = self._run(tmp_path, repo, run_env, psql_log)
        assert second.returncode == 0, second.stdout + second.stderr
        assert "Reusing run id" in second.stdout
        assert second.stdout.count(self.FAKE_RUN_ID) >= 1
        assert run_env.read_text(encoding="utf-8").count("PELLIER_RUN_ID=") == 1

    def test_an_unrecordable_run_fails_loudly(self, tmp_path: Path) -> None:
        """A psql that cannot write is not a run the labs may proceed from."""
        repo = self._repo(tmp_path)
        stubs = tmp_path / "stubs"
        path = _stub_path(tmp_path)
        (stubs / "psql").write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
        (stubs / "psql").chmod(0o755)
        health = tmp_path / "health.json"
        health.write_text('{"status": "healthy"}', encoding="utf-8")
        result = subprocess.run(
            [BASH, str(REPO / "scripts/workshop-start.sh")],
            capture_output=True,
            text=True,
            timeout=120,
            env=_clean_env(
                PELLIER_REPO=str(repo),
                PELLIER_RUN_ENV=str(tmp_path / "run.env"),
                PELLIER_PYTHON=sys.executable,
                HEALTH_URL=health.as_uri(),
                PATH=path,
            ),
        )
        assert result.returncode == 1
        assert "049" in result.stderr


class TestManagedCataloguesAgree:
    """Lab 3's two builds, checked from source before anything is deployed.

    The mismatch this catches does not look like a failure in the room. The
    managed dispatcher raises `Gateway is missing support tools`, the turn
    comes back as an apology, and the receipt the participant is waiting for
    never arrives. Naming the outstanding step beats letting them read a trace.
    """

    def _check(self, monkeypatch, *, published, managed, bound):
        import types

        schemas = types.ModuleType("gateway_tool_schemas")
        schemas.workshop_published_tools = lambda: frozenset(published)
        monkeypatch.setitem(sys.modules, "gateway_tool_schemas", schemas)

        gateway = types.ModuleType("services.agentcore_gateway")
        gateway.SUPPORT_MANAGED_TOOLS = tuple(managed)
        gateway.SUPPORT_CALLER_BOUND_TOOLS = frozenset(bound)
        gateway.STAFF_ONLY_GATEWAY_TOOLS = frozenset({"issue_credit"})
        monkeypatch.setitem(sys.modules, "services.agentcore_gateway", gateway)

        return doctor._managed_catalogues_agree()

    def test_neither_build_done_names_both_steps(self, monkeypatch):
        check = self._check(
            monkeypatch,
            published={"get_return_policy"},
            managed=("get_return_policy", "get_ticket_history", "issue_credit"),
            bound=set(),
        )
        assert not check.passed
        assert "Lab 3a" in check.detail
        assert "Task 3a" in check.detail

    def test_publishing_the_read_leaves_only_the_second_step(self, monkeypatch):
        """A participant who finished 3a must not be sent back to redo it."""
        check = self._check(
            monkeypatch,
            published={"get_return_policy", "get_ticket_history"},
            managed=("get_return_policy", "get_ticket_history", "issue_credit"),
            bound={"get_ticket_history"},
        )
        assert not check.passed
        assert "Task 3a" in check.detail
        assert "Lab 3a" not in check.detail

    def test_an_unbound_read_is_its_own_failure(self, monkeypatch):
        """Published and reachable is not enough: the caller must be bound."""
        check = self._check(
            monkeypatch,
            published={"get_return_policy", "get_ticket_history"},
            managed=("get_return_policy", "get_ticket_history"),
            bound=set(),
        )
        assert not check.passed
        assert "not bound to the" in check.detail
        assert "Task 3a" in check.detail

    def test_both_builds_done_passes(self, monkeypatch):
        check = self._check(
            monkeypatch,
            published={"get_return_policy", "get_ticket_history"},
            managed=("get_return_policy", "get_ticket_history"),
            bound={"get_ticket_history"},
        )
        assert check.passed
        assert "support serveable" in check.detail

    def test_an_unreadable_catalogue_fails_rather_than_crashes(self, monkeypatch):
        """The doctor runs when things are broken. It must not be one of them."""
        import builtins

        real_import = builtins.__import__

        def boom(name, *args, **kwargs):
            if name == "gateway_tool_schemas":
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "gateway_tool_schemas", raising=False)
        monkeypatch.setattr(builtins, "__import__", boom)
        check = doctor._managed_catalogues_agree()
        assert not check.passed
        assert "could not read the catalogues" in check.detail
