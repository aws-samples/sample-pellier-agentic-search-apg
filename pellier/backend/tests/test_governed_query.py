"""Unit contract for the governed natural-language query boundary.

These cover the parts that are decidable without a database: the wrapping that
makes structure the gate, the plan-inspection rules, and the evidence shape.
The rejection list itself is exercised against a real planner in
`test_governed_query_live.py`, because "PostgreSQL refuses this" is a claim
only PostgreSQL can settle.

Two bugs found during implementation are pinned here, both of the same shape —
a control that appears to work because it refuses too much or checks too
little:

  1. `SET LOCAL statement_timeout = %s` fails (`SET` takes no parameters), and
     because that error aborts every query the module looked like a perfect
     boundary while refusing legitimate questions too. Only a control case
     exposed it.
  2. Plain `EXPLAIN (FORMAT JSON)` omits `Schema`, so every relation looked
     schema-less and the allowlist filtered itself into an empty check. A
     relation with no resolvable schema must now be a rejection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List

import pytest

from services import governed_query as gq


# ---------------------------------------------------------------------------
# The wrap is what makes structure the gate
# ---------------------------------------------------------------------------


def test_wrap_makes_the_statement_a_subquery():
    wrapped = gq.wrap_statement("SELECT 1")

    assert wrapped.startswith("SELECT * FROM (")
    assert "AS governed_query" in wrapped


def test_wrap_owns_the_row_limit():
    """The cap must not depend on the generated SQL's own LIMIT."""
    wrapped = gq.wrap_statement("SELECT name FROM product_catalog LIMIT 100000")

    # The generated limit survives inside the subquery, but ours is outer and
    # therefore decides.
    assert wrapped.rstrip().endswith(f"LIMIT {gq.MAX_ROWS}")


def test_wrap_respects_an_explicit_lower_cap():
    assert gq.wrap_statement("SELECT 1", max_rows=5).rstrip().endswith("LIMIT 5")


def test_wrap_puts_a_newline_before_the_closing_paren():
    """A trailing line comment would otherwise comment out the paren.

    `SELECT 1 --` followed immediately by `)` changes the statement's meaning;
    the newline keeps the wrap intact.
    """
    wrapped = gq.wrap_statement("SELECT 1 -- trailing comment")

    assert "\n) AS governed_query" in wrapped


def test_wrap_is_not_a_string_prefix_check():
    """Guard against regressing to `startswith('select')`.

    The module must not gain a naive textual gate; the planner is the gate.
    """
    source = (
        __import__("pathlib")
        .Path(gq.__file__)
        .read_text()
        .lower()
    )
    assert 'startswith("select")' not in source
    assert "startswith('select')" not in source


# ---------------------------------------------------------------------------
# Plan inspection
# ---------------------------------------------------------------------------


def _scan(schema: Any, relation: str) -> Dict[str, Any]:
    return {"Node Type": "Seq Scan", "Schema": schema, "Relation Name": relation}


def _plan(*nodes: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"Plan": {"Node Type": "Limit", "Plans": list(nodes)}}]


def test_allowed_schema_passes():
    reason, schemas = gq.check_plan(_plan(_scan("pellier", "product_catalog")))

    assert reason is None
    assert schemas == ["pellier"]


def test_schema_outside_the_allowlist_is_rejected():
    reason, _schemas = gq.check_plan(_plan(_scan("pg_catalog", "pg_authid")))

    assert reason is not None
    assert "outside the allowed schemas" in reason
    assert "pg_catalog.pg_authid" in reason


def test_relation_with_no_resolvable_schema_is_rejected():
    """Regression: unknown schema must deny, not permit.

    Without `VERBOSE` the plan omits `Schema`, and treating that as acceptable
    let `SELECT rolname FROM pg_roles` through during implementation.
    """
    reason, _schemas = gq.check_plan(_plan(_scan(None, "pg_authid")))

    assert reason is not None
    assert "could not determine the schema" in reason


def test_nested_plans_are_inspected():
    """A subplan can reach a relation the outer node never mentions."""
    nested = _plan(
        {
            "Node Type": "Nested Loop",
            "Plans": [
                _scan("pellier", "orders"),
                {"Node Type": "SubPlan", "Plans": [_scan("pg_catalog", "pg_authid")]},
            ],
        }
    )

    reason, _schemas = gq.check_plan(nested)

    assert reason is not None
    assert "pg_catalog.pg_authid" in reason


def test_write_node_is_rejected_even_though_the_wrap_should_prevent_it():
    """Belt and braces: a silent write is the one failure worth catching twice."""
    reason, _schemas = gq.check_plan(
        _plan({"Node Type": "ModifyTable", "Operation": "Delete"})
    )

    assert reason == "plan contains a data-modifying node"


def test_a_relationless_plan_is_acceptable():
    """`SELECT 1` scans nothing and is harmless."""
    reason, schemas = gq.check_plan(_plan({"Node Type": "Result"}))

    assert reason is None
    assert schemas == []


# ---------------------------------------------------------------------------
# Precheck
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("", "empty statement"),
        ("   ", "empty statement"),
        ("SELECT 1" + "\x00", "statement contains a null byte"),
    ],
)
def test_precheck_rejections(sql, expected):
    assert gq.precheck(sql) == expected


def test_precheck_bounds_statement_length():
    reason = gq.precheck("SELECT " + "a" * gq.MAX_SQL_LENGTH)

    assert reason is not None and "exceeds" in reason


def test_precheck_passes_a_normal_statement():
    assert gq.precheck("SELECT name FROM product_catalog") is None


@pytest.mark.parametrize(
    "sql,body",
    [
        ("SELECT 1;", "SELECT 1"),
        ("SELECT 1; -- terminal ;", "SELECT 1 -- terminal ;"),
        ("SELECT 1; /* terminal ; */", "SELECT 1 /* terminal ; */"),
        ("SELECT ';' AS value;", "SELECT ';' AS value"),
        ("SELECT 'it''s; safe' AS value;", "SELECT 'it''s; safe' AS value"),
        (r"SELECT E'a\';b' AS value;", r"SELECT E'a\';b' AS value"),
        (r"SELECT E'\\' AS value;", r"SELECT E'\\' AS value"),
        (r"SELECT '\' AS value;", r"SELECT '\' AS value"),
        (r"SELECT U&'d\0061t;a' AS value;", r"SELECT U&'d\0061t;a' AS value"),
        ("SELECT N'value;' AS value;", "SELECT N'value;' AS value"),
        ("SELECT B'0101' AS value;", "SELECT B'0101' AS value"),
        ('SELECT 1 AS "column;""quoted";', 'SELECT 1 AS "column;""quoted"'),
        ("SELECT $$; -- ( ) /* */$$ AS value;", "SELECT $$; -- ( ) /* */$$ AS value"),
        ("SELECT $tag$; $other$'$tag$ AS value;", "SELECT $tag$; $other$'$tag$ AS value"),
        ("SELECT $é9$x;y$é9$ AS value;", "SELECT $é9$x;y$é9$ AS value"),
        ("SELECT 1 AS foo$tag$;", "SELECT 1 AS foo$tag$"),
        (
            "/* outer ; /* inner ) ; */ */ SELECT (1) -- ; )\r\n;",
            "/* outer ; /* inner ) ; */ */ SELECT (1) -- ; )",
        ),
        ("SELECT 'first;'\n'second;' AS value;", "SELECT 'first;'\n'second;' AS value"),
        (
            "SELECT E'first'\n" + r"'\';second' AS value;",
            "SELECT E'first'\n" + r"'\';second' AS value",
        ),
        (
            "SELECT E'first' -- continued ;\r\n" + r"'\';second' AS value;",
            "SELECT E'first' -- continued ;\r\n" + r"'\';second' AS value",
        ),
        (
            "SELECT 'set_config(' AS value /* set_config('role', 'none', true); */;",
            "SELECT 'set_config(' AS value /* set_config('role', 'none', true); */",
        ),
        ("SELECT 1 AS set_config;", "SELECT 1 AS set_config"),
        ("WITH a AS (SELECT 1 AS n) SELECT sum(n) FROM a;", "WITH a AS (SELECT 1 AS n) SELECT sum(n) FROM a"),
        ("VALUES (1), (2);", "VALUES (1), (2)"),
    ],
)
def test_one_statement_preserves_quoted_data_and_a_trailing_terminator(sql, body):
    assert gq.precheck(sql) is None
    assert gq.wrap_statement(sql) == (
        f"SELECT * FROM (\n{body}\n) AS governed_query LIMIT {gq.MAX_ROWS}"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1;;",
        "; SELECT 1",
        "SELECT 1; /* nested /* ; */ */ SELECT 2",
        "SELECT 1 -- a comment\r; SELECT 2",
        "SELECT 1) AS escaped; RESET ROLE; SELECT * FROM (SELECT 1",
        "SELECT 1) AS escaped; COMMIT; SELECT * FROM (SELECT 1",
        "SELECT 1) AS escaped UNION ALL SELECT * FROM (SELECT 2",
        r"SELECT '\'; SELECT 2",
        "SELECT $$safe;$$; SELECT 2",
        "SELECT $a$safe$a$; SELECT 2",
        "SELECT 1 /* unterminated",
        "SELECT 1 /* outer /* inner */",
        "SELECT 'unterminated",
        "SELECT E'ending\\",
        'SELECT "unterminated',
        "SELECT $tag$unterminated",
        "SELECT (1",
        "SELECT 1)",
        "-- nothing but a comment",
        "/* nothing /* nested */ else */",
        ";",
    ],
)
def test_statement_escape_or_incomplete_token_is_refused_before_wrapping(sql):
    assert gq.precheck(sql) is not None
    with pytest.raises(ValueError):
        gq.wrap_statement(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT set_config('role', 'none', true)",
        "SELECT pg_catalog.set_config('role', 'none', false)",
        'SELECT "pg_catalog"."set_config"(\'role\', \'none\', true)',
        "SELECT SeT_CoNfIg /* split /* nested */ */ ('role', 'none', true)",
        "SELECT set_config('pellier.principal_sub', 'other-principal', true)",
        "SELECT set_config('statement_timeout', '0', false)",
        "SELECT set_config('search_path', 'pg_catalog', true)",
        "SELECT set_config('standard_conforming_strings', 'off', false)",
        r"""SELECT U&"set_\0063onfig"('role', 'none', true)""",
        """SELECT U&"set_!0063onfig" UESCAPE '!' ('role', 'none', true)""",
        """SELECT query_to_xml($$SELECT set_config('role','none',true)$$, false, false, '')""",
        """SELECT pg_catalog."query_to_xml"('SELECT 1', false, false, '')""",
        """SELECT ts_stat('SELECT set_config(''role'',''none'',true)')""",
        """SELECT crosstab2('SELECT set_config(''role'',''none'',true)')""",
        """SELECT dblink_exec('dbname=unused', 'RESET ROLE')""",
        """SELECT database_to_xml(true, false, '')""",
    ],
)
def test_session_mutators_and_hidden_sql_helpers_are_refused(sql):
    assert gq.precheck(sql) is not None


class _RecordingCursor:
    """An inert connection: records exactly what would be sent to Psycopg."""

    def __init__(self, *, plan=None, failure=None):
        self.calls = []
        self.plan = plan if plan is not None else _plan(_scan("pellier", "orders"))
        self.failure = failure

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, sql, **kwargs):
        self.calls.append((sql, kwargs))
        if self.failure == len(self.calls):
            raise RuntimeError("inert driver refusal")

    async def fetchone(self):
        return {"QUERY PLAN": self.plan}

    async def fetchall(self):
        return [{"n": n} for n in range(6)]


class _RecordingDatabase:
    def __init__(self, **kwargs):
        self.recording_cursor = _RecordingCursor(**kwargs)
        self.prepare_threshold = 5
        self.sessions = []
        self.receipts = []

    @asynccontextmanager
    async def query_session(self, principal_sub, **kwargs):
        self.sessions.append((principal_sub, kwargs))
        yield self

    def cursor(self):
        return self.recording_cursor

    async def fetch_one(self, sql, *params):
        self.receipts.append((sql, params))
        return {"receipt_id": 7}


@pytest.mark.asyncio
@pytest.mark.parametrize("prepare_threshold", [0, 5, 100])
async def test_planner_and_execution_force_preparation_with_the_same_bounded_sql(
    prepare_threshold,
):
    db = _RecordingDatabase()
    db.prepare_threshold = prepare_threshold
    result = await gq.run_governed_query(
        db, "SELECT quantity AS n FROM orders; -- a terminal ;",
        principal_sub="unit-principal", max_rows=2,
    )

    assert result.accepted and result.execution_outcome == "success"
    assert result.rows == [{"n": 0}, {"n": 1}]
    assert result.row_count == result.result_limit == 2
    assert result.role_used == "pellier_query"
    assert result.schemas_read == ["pellier"]
    assert db.sessions == [("unit-principal", {"statement_timeout": gq.STATEMENT_TIMEOUT})]
    control, planner, execution = db.recording_cursor.calls
    assert control == (
        "SELECT set_config('standard_conforming_strings', 'on', true)",
        {"prepare": True},
    )
    assert planner[0] == f"EXPLAIN (FORMAT JSON, VERBOSE) {execution[0]}"
    assert planner[1] == execution[1] == {"prepare": True}
    assert execution[0].endswith(") AS governed_query LIMIT 2")
    assert result.receipt_id == 7 and len(db.receipts) == 1


@pytest.mark.asyncio
async def test_a_connection_that_disables_preparation_cannot_send_generated_sql():
    db = _RecordingDatabase()
    db.prepare_threshold = None
    result = await gq.run_governed_query(db, "SELECT 1")

    assert not result.accepted
    assert result.validation == "rejected_structure"
    assert result.execution_outcome == "not_executed"
    assert "prepared statements disabled" in result.rejection_reason
    assert db.recording_cursor.calls == []
    assert result.receipt_id == 7 and len(db.receipts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1) AS escaped; RESET ROLE; SELECT * FROM (SELECT 1",
        "SELECT set_config('pellier.principal_sub', 'other-principal', true)",
        "SELECT query_to_xml('SELECT 1', false, false, '')",
    ],
)
async def test_early_refusal_opens_no_query_session_but_keeps_its_receipt(sql):
    db = _RecordingDatabase()
    result = await gq.run_governed_query(db, sql, principal_sub="unit-principal")

    assert not result.accepted
    assert result.validation == "rejected_precheck"
    assert result.execution_outcome == "not_executed"
    assert result.sql == sql
    assert db.sessions == [] and db.recording_cursor.calls == []
    assert result.receipt_id == 7 and len(db.receipts) == 1
    assert db.receipts[0][1][-1] == sql


@pytest.mark.asyncio
async def test_a_scope_rejection_never_sends_the_execution_statement():
    db = _RecordingDatabase(plan=_plan(_scan("pg_catalog", "pg_authid")))
    result = await gq.run_governed_query(db, "SELECT * FROM pg_catalog.pg_authid")

    assert not result.accepted and result.validation == "rejected_plan"
    assert result.execution_outcome == "not_executed"
    assert len(db.recording_cursor.calls) == 2
    assert all(kwargs == {"prepare": True} for _, kwargs in db.recording_cursor.calls)
    assert len(db.receipts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [1, 2, 3])
async def test_driver_failure_stops_further_commands_and_preserves_the_outcome(failure):
    db = _RecordingDatabase(failure=failure)
    result = await gq.run_governed_query(db, "SELECT 1")

    assert len(db.recording_cursor.calls) == failure
    assert result.accepted is (failure == 3)
    assert result.validation == ("accepted" if failure == 3 else "rejected_structure")
    assert result.execution_outcome == ("error" if failure == 3 else "not_executed")
    assert result.receipt_id == 7 and len(db.receipts) == 1


# ---------------------------------------------------------------------------
# Evidence shape
# ---------------------------------------------------------------------------


def test_evidence_carries_every_required_field():
    """The design's required evidence set for a governed query."""
    result = gq.GovernedQueryResult(
        accepted=True,
        turn_id="turn-1",
        principal_sub="sub-a",
        caller="agent",
        sql="SELECT 1",
        row_count=3,
        execution_outcome="success",
        latency_ms=12,
        schemas_read=["pellier"],
        receipt_id=9,
    )

    evidence = result.evidence()

    for field in (
        "turn_id",
        "principal_sub",
        "caller",
        "accepted",
        "validation",
        "role_used",
        "statement_timeout",
        "result_limit",
        "row_count",
        "execution_outcome",
        "receipt_id",
        "sql",
    ):
        assert field in evidence, field


def test_evidence_excludes_result_rows():
    """Rows are the answer, not evidence about how the query was governed."""
    result = gq.GovernedQueryResult(
        accepted=True, rows=[{"name": "Linen Shirt"}], row_count=1
    )

    evidence = result.evidence()

    assert "rows" not in evidence
    assert evidence["row_count"] == 1


def test_a_rejected_result_reports_no_execution():
    result = gq.GovernedQueryResult(accepted=False, rejection_reason="nope")

    assert result.execution_outcome == "not_executed"
    assert result.row_count is None


def test_role_and_limits_are_reported_not_assumed():
    """An operator reads the enforced values rather than trusting a default."""
    evidence = gq.GovernedQueryResult(accepted=False).evidence()

    assert evidence["role_used"] == "pellier_query"
    assert evidence["statement_timeout"] == gq.STATEMENT_TIMEOUT
    assert evidence["result_limit"] == gq.MAX_ROWS


# ---------------------------------------------------------------------------
# Session containment
# ---------------------------------------------------------------------------


def test_read_only_session_never_uses_a_set_statement_for_the_timeout():
    """Regression: `SET LOCAL statement_timeout = %s` is a syntax error.

    `SET` takes no parameters. The failure aborted every query, so the module
    looked like a boundary that refused everything — including legitimate
    questions. `set_config(..., true)` is the parameterizable form.
    """
    import pathlib

    source = pathlib.Path(
        __import__("services.database", fromlist=["x"]).__file__
    ).read_text()
    session = source.split("async def query_session", 1)[1].split("async def", 1)[0]

    assert "SET LOCAL statement_timeout = %s" not in session
    assert "set_config('statement_timeout'" in session


def test_read_only_session_sets_every_containment():
    """All four containments, in one transaction, on one connection."""
    import pathlib

    source = pathlib.Path(
        __import__("services.database", fromlist=["x"]).__file__
    ).read_text()
    session = source.split("async def query_session", 1)[1].split("async def", 1)[0]

    assert "SET TRANSACTION READ ONLY" in session
    assert "SET LOCAL ROLE pellier_query" in session
    assert "set_config('statement_timeout'" in session
    assert "set_config('search_path'" in session
    assert "set_config('pellier.principal_sub'" in session


def test_read_only_precedes_the_role_switch():
    """`SET TRANSACTION` must come before the first query in the transaction."""
    import pathlib

    source = pathlib.Path(
        __import__("services.database", fromlist=["x"]).__file__
    ).read_text()
    session = source.split("async def query_session", 1)[1].split("async def", 1)[0]

    assert session.index("SET TRANSACTION READ ONLY") < session.index(
        "SET LOCAL ROLE pellier_query"
    )
