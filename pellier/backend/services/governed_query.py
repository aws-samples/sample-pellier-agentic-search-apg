"""
Governed natural-language access to business records.

A model turns a shopper's question into SQL, and this module decides whether
that SQL may touch the database at all. The capability is deliberately named
for the business question it answers rather than for the substrate: the same
PostgreSQL primitives apply on Amazon RDS for PostgreSQL, so no identifier
here encodes Aurora.

What is and is not the security boundary
---------------------------------------

Schema-scoped prompting, temperature 0, and an instruction to write read-only
SQL all improve behavior. **None of them is a boundary.** A model can be
argued out of any instruction. The boundary is:

* ``pellier_query`` — a role with SELECT on a scoped set, no write grants
  anywhere, and no access to ``pellier.tool_audit``, so generated SQL can
  neither read the evidence ledger nor manufacture evidence;
* a ``READ ONLY`` transaction, so the server refuses writes whatever the
  statement asks for;
* ``statement_timeout``;
* Row-Level Security, bound to the same principal a curated tool would use.

Everything below is defense in depth layered on top of that.

Structural validation
---------------------

The generated statement is wrapped as a subquery before it reaches the
planner::

    EXPLAIN (FORMAT JSON, VERBOSE) SELECT * FROM (
    <generated sql>
    ) AS governed_query LIMIT <max>

The lexical check first requires one statement with balanced parentheses
outside comments and quoted values. One trailing terminator is accepted and
removed. Both planning and execution explicitly use the prepared protocol,
which independently refuses multiple commands. The wrapper then enforces:

* only a read-only ``SELECT`` can *be* a subquery, so ``DELETE``, ``UPDATE``,
  ``INSERT``, DDL, ``GRANT``, ``SET``, ``BEGIN`` and ``COMMIT`` are syntax
  errors rather than permission errors;
* a data-modifying CTE is rejected by PostgreSQL itself — "WITH clause
  containing a data-modifying statement must be at the top level";
* the **outer** ``LIMIT`` is ours, so the row cap does not depend on the
  generated SQL omitting, inflating, or nesting a limit.

PostgreSQL still supplies the structural parser. The bounded lexical check
does not try to establish that a statement is a valid read-only query.

Two things the wrap does not cover, handled explicitly:

* **Schema escape.** ``SELECT rolname FROM pg_roles`` is a perfectly valid
  subquery. The EXPLAIN plan reports the ``(schema, relation)`` of every scan,
  resolved through views to the underlying tables, and anything outside the
  allowlist is rejected. ``VERBOSE`` is required for this: plain
  ``FORMAT JSON`` omits ``Schema``, and without it every relation looks
  schema-less and the allowlist checks nothing.
* **Function calls.** Direct ``set_config`` and known SQL-in-string helpers
  are refused before planning: read-only transactions do not stop a function
  from changing the role, principal setting, or session settings. This check
  is defense in depth, not a complete function sandbox. EXECUTE grants,
  installed extensions, operators and casts still need review. Migration 017
  restricts application functions, not every function in ``pg_catalog``.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# The implementation owns the row cap, not the model.
MAX_ROWS = 50

# Wall-clock ceiling for one generated statement.
STATEMENT_TIMEOUT = "3s"

# Schemas a generated statement may read. `pg_catalog` is absent on purpose:
# a question about the business does not need the role table.
ALLOWED_SCHEMAS: Set[str] = {"pellier"}

# Bounds the SQL a model may hand over. Not a security control — a sanity
# guard so an unbounded generation cannot become an unbounded parse.
MAX_SQL_LENGTH = 4000

_SUBQUERY_ALIAS = "governed_query"

_SQL_SPACE = " \t\n\r\f\v"
_DOLLAR_QUOTE = re.compile(
    r"\$(?:[A-Za-z_\x80-\U0010ffff][A-Za-z_0-9\x80-\U0010ffff]*)?\$"
)
# These functions can alter the session or execute SQL hidden inside a value,
# where neither the lexical check nor the outer EXPLAIN can inspect it.
_UNSAFE_QUERY_FUNCTIONS = frozenset({
    "set_config",
    "query_to_xml", "query_to_xmlschema", "query_to_xml_and_xmlschema",
    "cursor_to_xml", "cursor_to_xmlschema",
    "table_to_xml", "table_to_xmlschema", "table_to_xml_and_xmlschema",
    "schema_to_xml", "schema_to_xmlschema", "schema_to_xml_and_xmlschema",
    "database_to_xml", "database_to_xmlschema", "database_to_xml_and_xmlschema",
    "ts_stat", "crosstab", "crosstab2", "crosstab3", "crosstab4",
    "connectby", "xpath_table",
})


def _identifier_start(char: str) -> bool:
    return char == "_" or "a" <= char <= "z" or "A" <= char <= "Z" or ord(char) >= 128


def _sql_gap(sql: str, start: int, *, block_comments: bool = True) -> Tuple[int, bool]:
    """Skip PostgreSQL whitespace and comments, including nested block comments."""
    i = start
    while i < len(sql):
        if sql[i] in _SQL_SPACE:
            i += 1
        elif sql.startswith("--", i):
            i += 2
            while i < len(sql) and sql[i] not in "\r\n":
                i += 1
        elif block_comments and sql.startswith("/*", i):
            depth = 1
            i += 2
            while i < len(sql) and depth:
                if sql.startswith("/*", i):
                    depth += 1
                    i += 2
                elif sql.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            if depth:
                raise ValueError("unterminated block comment")
        else:
            break
    return i, "\n" in sql[start:i] or "\r" in sql[start:i]


def _quoted_sql(sql: str, start: int, *, escape: bool = False) -> Tuple[int, str]:
    """Consume one quoted token; decode doubled quotes for function names."""
    quote = sql[start]
    chars: List[str] = []
    i = start + 1
    while i < len(sql):
        char = sql[i]
        if escape and char == "\\":
            i += 2
        elif char == quote:
            if i + 1 < len(sql) and sql[i + 1] == quote:
                chars.append(quote)
                i += 2
            else:
                return i + 1, "".join(chars)
        else:
            chars.append(char)
            i += 1
    raise ValueError("unterminated quoted value or identifier")


def _statement_body(sql: str) -> str:
    """Bound the statement without interpreting SQL grammar.

    Ordinary strings use standard_conforming_strings=on, pinned on the query
    connection before planning. E strings, doubled quotes, dollar quotes and
    nested comments are recognized so their separators remain data. Unicode
    escape *identifiers* are explicitly unsupported: they could otherwise
    encode a prohibited function name. UTF-8 and ordinary quoted names work.
    """
    if not sql or not sql.strip():
        raise ValueError("empty statement")
    if len(sql) > MAX_SQL_LENGTH:
        raise ValueError(f"statement exceeds {MAX_SQL_LENGTH} characters")
    if "\x00" in sql:
        raise ValueError("statement contains a null byte")

    tokens: List[Tuple[str, str, int]] = []
    parentheses = 0
    i = 0
    while i < len(sql):
        i, _ = _sql_gap(sql, i)
        if i == len(sql):
            break
        start = i
        char = sql[i]
        escape = char in "eE" and sql[i:i + 2].lower() == "e'"
        if char == "'" or escape:
            i, _ = _quoted_sql(sql, i + int(escape), escape=escape)
            # PostgreSQL concatenates string pieces separated by a newline;
            # an E string retains its escape rules across those pieces.
            while True:
                # Block comments do not participate in PostgreSQL's quoted
                # string continuation rule; whitespace and -- comments do.
                following, newline = _sql_gap(sql, i, block_comments=False)
                if not newline or following == len(sql) or sql[following] != "'":
                    break
                i, _ = _quoted_sql(sql, following, escape=escape)
            tokens.append(("literal", "", start))
        elif sql[i:i + 3].lower() == 'u&"':
            raise ValueError(
                "Unicode escape identifiers are not supported; use UTF-8 or ordinary quoted identifiers"
            )
        elif char == '"':
            i, name = _quoted_sql(sql, i)
            tokens.append(("identifier", name.lower(), start))
        elif char == "$" and (delimiter := _DOLLAR_QUOTE.match(sql, i)):
            tag = delimiter.group()
            end = sql.find(tag, delimiter.end())
            if end < 0:
                raise ValueError("unterminated dollar-quoted value")
            i = end + len(tag)
            tokens.append(("literal", "", start))
        elif _identifier_start(char):
            i += 1
            while i < len(sql) and (
                _identifier_start(sql[i]) or sql[i] in "0123456789$"
            ):
                i += 1
            tokens.append(("identifier", sql[start:i].lower(), start))
        else:
            if char == "(":
                parentheses += 1
            elif char == ")":
                parentheses -= 1
                if parentheses < 0:
                    raise ValueError("unbalanced parentheses")
            tokens.append(("symbol", char, start))
            i += 1

    if parentheses:
        raise ValueError("unbalanced parentheses")
    if not tokens:
        raise ValueError("empty statement")
    separators = [index for index, token in enumerate(tokens) if token[:2] == ("symbol", ";")]
    if separators and (len(separators) != 1 or separators[0] != len(tokens) - 1):
        raise ValueError("exactly one SQL statement is required")
    if separators and len(tokens) == 1:
        raise ValueError("empty statement")
    for token, following in zip(tokens, tokens[1:]):
        kind, name, _ = token
        if kind == "identifier" and following[:2] == ("symbol", "(") and (
            name in _UNSAFE_QUERY_FUNCTIONS or name.startswith("dblink")
        ):
            raise ValueError(f"function {name} is not allowed in a governed query")
    if separators:
        terminator = tokens[-1][2]
        sql = sql[:terminator] + sql[terminator + 1:]
    return sql.strip()


@dataclass
class GovernedQueryResult:
    """Everything the evidence surface needs about one governed query.

    Mirrors the design's required evidence set. Absent fields stay ``None``
    rather than being filled with a plausible default: "we did not record
    this" and "this was zero" are different claims.
    """

    accepted: bool
    turn_id: Optional[str] = None
    principal_sub: Optional[str] = None
    caller: Optional[str] = None
    sql: Optional[str] = None
    rejection_reason: Optional[str] = None
    validation: str = "not_run"
    role_used: str = "pellier_query"
    statement_timeout: str = STATEMENT_TIMEOUT
    result_limit: int = MAX_ROWS
    row_count: Optional[int] = None
    execution_outcome: str = "not_executed"
    latency_ms: Optional[int] = None
    schemas_read: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    receipt_id: Optional[int] = None

    def evidence(self) -> Dict[str, Any]:
        """Serialize the evidence fields, excluding the result rows.

        Rows are the shopper's answer; they are not evidence about how the
        query was governed, and copying them into a receipt would put
        customer data in a second place.
        """
        return {
            "turn_id": self.turn_id,
            "principal_sub": self.principal_sub,
            "caller": self.caller,
            "accepted": self.accepted,
            "validation": self.validation,
            "rejection_reason": self.rejection_reason,
            "role_used": self.role_used,
            "statement_timeout": self.statement_timeout,
            "result_limit": self.result_limit,
            "row_count": self.row_count,
            "execution_outcome": self.execution_outcome,
            "latency_ms": self.latency_ms,
            "schemas_read": sorted(self.schemas_read),
            "sql": self.sql,
            "receipt_id": self.receipt_id,
        }


def wrap_statement(sql: str, *, max_rows: int = MAX_ROWS) -> str:
    """Return the generated SQL wrapped as a bounded read-only subquery.

    The newline before the closing paren matters: a generated statement ending
    in a ``--`` line comment would otherwise comment out the paren and change
    what the wrap means.
    """
    return (
        f"SELECT * FROM (\n{_statement_body(sql)}\n) AS {_SUBQUERY_ALIAS} "
        f"LIMIT {int(max_rows)}"
    )


def precheck(sql: str) -> Optional[str]:
    """Cheap deterministic rejections, before the database is involved.

    Returns a reason, or ``None`` when the statement is worth planning.
    Lexical checks protect the wrapper and session controls; PostgreSQL still
    decides whether the wrapped statement is structurally valid.
    """
    try:
        _statement_body(sql)
    except ValueError as exc:
        return str(exc)
    return None


def _plan_relations(plan: Any) -> List[Tuple[Optional[str], str]]:
    """Collect every ``(schema, relation)`` the plan scans.

    Walks the whole plan tree rather than the top node: a subplan, CTE, or
    InitPlan can reach a relation the outer node never mentions. Reading the
    plan rather than the SQL text also resolves views to their underlying
    tables, so ``pg_roles`` is reported as ``pg_catalog.pg_authid``.
    """
    found: List[Tuple[Optional[str], str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            relation = node.get("Relation Name")
            if relation:
                found.append((node.get("Schema"), str(relation)))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(plan)
    return found


def _plan_modifies(plan: Any) -> bool:
    """True when the plan contains a write node.

    The subquery wrap should make this unreachable. It is checked anyway
    because a silent write would be the one failure worth catching twice.
    """
    return "ModifyTable" in json.dumps(plan)


def check_plan(plan: Any) -> Tuple[Optional[str], List[str]]:
    """Validate a plan against the schema allowlist and write prohibition.

    Returns ``(rejection_reason, schemas_read)``; the reason is ``None`` when
    the plan is acceptable.
    """
    if _plan_modifies(plan):
        return "plan contains a data-modifying node", []

    relations = _plan_relations(plan)
    schemas = sorted({schema for schema, _ in relations if schema})

    # A relation whose schema the plan did not report is a rejection, not a
    # pass. Treating unknown as acceptable is how `SELECT rolname FROM
    # pg_roles` slipped through during implementation: without VERBOSE the
    # plan omits `Schema`, every relation looked schema-less, and the
    # allowlist filtered itself into an empty check.
    unresolved = sorted({relation for schema, relation in relations if not schema})
    if unresolved:
        return (
            "could not determine the schema of "
            f"{', '.join(unresolved)}; refusing rather than assuming it is allowed"
        ), schemas

    outside = sorted(
        {
            f"{schema}.{relation}"
            for schema, relation in relations
            if schema not in ALLOWED_SCHEMAS
        }
    )
    if outside:
        allowed = ", ".join(sorted(ALLOWED_SCHEMAS))
        return (
            f"statement reads outside the allowed schemas ({allowed}): "
            f"{', '.join(outside)}"
        ), schemas
    return None, schemas


async def run_governed_query(
    db: Any,
    sql: str,
    *,
    turn_id: Optional[str] = None,
    principal_sub: Optional[str] = None,
    caller: str = "agent",
    max_rows: int = MAX_ROWS,
    session_id: Optional[str] = None,
) -> GovernedQueryResult:
    """Validate and run one generated statement, returning rows and evidence.

    Never raises for a rejected or failing statement: a refusal is an outcome
    the evidence surface has to be able to show, not an exception the caller
    has to interpret.

    Writes the receipt itself rather than leaving that to the caller. An
    earlier revision left `persist_receipt` for each caller to invoke, one
    caller did and `scripts/compare_query_lanes.py` did not, and that script
    printed "durable receipt: pellier.governed_query_receipts" as a property
    of this lane while running three queries that left none. A receipt a
    caller can forget is not evidence, so the write moved in here and callers
    no longer have the option.

    Args:
        db: ``DatabaseService``.
        sql: Model-generated SQL.
        turn_id: Correlation key shared with spans and the audit ledger.
        principal_sub: Verified subject; bound so RLS applies to generated
            SQL exactly as to a curated tool.
        caller: Who asked, for the receipt.
        max_rows: Row cap. Enforced by the wrapper, not by the statement.
        session_id: Session the attempt belongs to, recorded on the receipt.

    Returns:
        A :class:`GovernedQueryResult`. ``accepted`` False means nothing ran.
    """
    result = await _attempt(
        db,
        sql,
        turn_id=turn_id,
        principal_sub=principal_sub,
        caller=caller,
        max_rows=max_rows,
    )
    # Every outcome is receipted, refusals included. Those are the ones an
    # operator most needs later: a rejected statement leaves no trace anywhere
    # else, because by definition it never reached the database.
    await persist_receipt(db, result, session_id=session_id)
    return result


async def _attempt(
    db: Any,
    sql: str,
    *,
    turn_id: Optional[str],
    principal_sub: Optional[str],
    caller: str,
    max_rows: int,
) -> GovernedQueryResult:
    """Run the validation and execution stages, returning the outcome.

    Separate from `run_governed_query` only so the receipt has a single write
    site. The early returns below are why: with the write inlined here, a
    precheck or plan rejection would return before it.
    """
    result = GovernedQueryResult(
        accepted=False,
        turn_id=turn_id,
        principal_sub=principal_sub,
        caller=caller,
        sql=sql,
        result_limit=max_rows,
    )

    reason = precheck(sql)
    if reason:
        result.validation = "rejected_precheck"
        result.rejection_reason = reason
        return result

    wrapped = wrap_statement(sql, max_rows=max_rows)
    started = time.perf_counter()

    try:
        async with db.query_session(
            principal_sub, statement_timeout=STATEMENT_TIMEOUT
        ) as conn:
            # Psycopg treats prepare_threshold=None as disabling preparation,
            # even when execute(..., prepare=True) is requested. Refuse that
            # connection configuration instead of falling back to simple SQL.
            if conn.prepare_threshold is None:
                raise RuntimeError("governed query connection has prepared statements disabled")
            async with conn.cursor() as cur:
                # Match the lexer's ordinary-string rules even if an earlier
                # pool user changed this setting. This is trusted control SQL,
                # never text supplied by the model.
                await cur.execute(
                    "SELECT set_config('standard_conforming_strings', 'on', true)",
                    prepare=True,
                )
                # Structural gate: the planner parses the wrapped statement.
                # Force prepared protocol on BOTH calls: PostgreSQL's Parse
                # message refuses multiple commands independently of the
                # lexical check and the connection's prepare threshold.
                await cur.execute(
                    f"EXPLAIN (FORMAT JSON, VERBOSE) {wrapped}", prepare=True
                )
                plan_row = await cur.fetchone()
                plan = _extract_plan(plan_row)

                reason, schemas = check_plan(plan)
                result.schemas_read = schemas
                if reason:
                    result.validation = "rejected_plan"
                    result.rejection_reason = reason
                    return result

                result.validation = "accepted"
                result.accepted = True

                await cur.execute(wrapped, prepare=True)
                rows = await cur.fetchall()

        result.rows = [dict(row) for row in rows][:max_rows]
        result.row_count = len(result.rows)
        result.execution_outcome = "success"
    except Exception as exc:
        # A syntax error from the wrap is a structural rejection, not an
        # execution failure, and the two must not be reported alike.
        message = str(exc).splitlines()[0][:300]
        if result.validation in {"not_run", "rejected_plan"}:
            result.validation = "rejected_structure"
            result.accepted = False
            result.rejection_reason = message
            result.execution_outcome = "not_executed"
        else:
            result.execution_outcome = "error"
            result.rejection_reason = message
        logger.info("governed query refused or failed: %s", message)

    result.latency_ms = int((time.perf_counter() - started) * 1000)
    return result


_RECEIPT_SQL = """
INSERT INTO pellier.governed_query_receipts
    (turn_id, session_id, principal_sub, caller, accepted, validation,
     rejection_reason, role_used, statement_timeout, result_limit, row_count,
     execution_outcome, latency_ms, schemas_read, generated_sql)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
RETURNING receipt_id
"""


async def persist_receipt(
    db: Any,
    result: GovernedQueryResult,
    *,
    session_id: Optional[str] = None,
) -> Optional[int]:
    """Write the durable receipt and return its id.

    Runs on the ordinary connection, not inside the read-only session that
    produced the result: the receipt has to survive a refusal, and the
    transaction that refused is read-only by construction and could not write
    it. This is the same independence the tool-audit ledger relies on.

    A failed receipt write returns ``None`` and is logged. Evidence collection
    must not turn a refusal the shopper already saw into an exception.
    """
    if db is None:
        return None
    try:
        row = await db.fetch_one(
            _RECEIPT_SQL,
            result.turn_id,
            session_id,
            result.principal_sub,
            result.caller,
            result.accepted,
            result.validation,
            result.rejection_reason,
            result.role_used,
            result.statement_timeout,
            result.result_limit,
            result.row_count,
            result.execution_outcome,
            result.latency_ms,
            json.dumps(sorted(result.schemas_read)),
            result.sql,
        )
    except Exception as exc:
        logger.warning("governed query receipt write failed: %s", exc)
        return None

    receipt_id = row.get("receipt_id") if row else None
    result.receipt_id = receipt_id
    return receipt_id


def _extract_plan(plan_row: Any) -> Any:
    """Pull the plan document out of an ``EXPLAIN (FORMAT JSON)`` row."""
    if plan_row is None:
        return {}
    value = (
        next(iter(plan_row.values()))
        if isinstance(plan_row, dict)
        else plan_row[0]
    )
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value
