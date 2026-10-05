"""
RDS Data API transport for the store-tools Lambda.

Everything here is transport. Nothing in this module knows a tool name: the
tools live in ``services/store_tools.py`` and take a ``run(sql, params)``
callable, which ``run_store_sql`` provides for this rail. Two Bedrock calls
that the search tool needs on this rail, the query embedding and Cohere
Rerank, live here too because this module owns the Bedrock clients.

`deploy_lambda.py` packages this file into the function's zip next to
`common/types.py` and `common/handler.py`.

A customer's own reads (``get_orders``, ``get_tickets``) run through
``run_as_customer``: one Data API transaction that switches to
``pellier_agent`` and names the customer, so row-level security holds on this
rail exactly as it does in process.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

import boto3

logger = logging.getLogger(__name__)

REGION = os.environ.get("REGION", "us-east-1")
DB_REGION = os.environ.get("DB_REGION", REGION)
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
SCHEMA = "pellier"

# The application role from scripts/migrations/001_schema.sql. It is
# NOBYPASSRLS and not the table owner, which is what makes the policies bind.
CUSTOMER_ROLE = "pellier_agent"

# Cohere Embed v4. MUST match the catalog seed and the in-process path
# (`pellier/backend/services/embeddings.py`): the catalog was seeded with
# Cohere Embed v4 at output_dimension=1024, so the managed Gateway path has to
# embed in the SAME vector space. Titan v2 vectors are a different space and
# would make pgvector cosine search return wrong rankings even though the
# dimension (1024) happens to match. Stated once here, on purpose: this is the
# constant that must never diverge between rails.
EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "us.cohere.embed-v4:0")
EMBED_DIMENSION = 1024
RERANK_MODEL_ID = os.environ.get("BEDROCK_RERANK_MODEL_ID", "cohere.rerank-v3-5:0")

# Module-level clients for Lambda warm-start reuse.
rds_client = boto3.client("rds-data", region_name=DB_REGION)
bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=REGION)


def row_to_dict(record: List[Dict[str, Any]], columns: List[str]) -> Dict[str, Any]:
    """Convert one Data API record into a dict keyed by column name.

    Handles every field shape the Data API returns. `booleanValue` and `isNull`
    are load-bearing: a converter that omits them coerces `false` and SQL NULL
    to the same `None`, which reads as missing data rather than as an error.

    Args:
        record: One entry from a response's ``records`` list.
        columns: Column names from ``columnMetadata``, in order.

    Returns:
        The row as a dict. Unrecognized field shapes stringify rather than
        vanish, so a new Data API type is visible instead of silently null.
    """
    row: Dict[str, Any] = {}
    for index, field in enumerate(record):
        if index >= len(columns):
            break
        if "stringValue" in field:
            row[columns[index]] = field["stringValue"]
        elif "longValue" in field:
            row[columns[index]] = field["longValue"]
        elif "doubleValue" in field:
            row[columns[index]] = field["doubleValue"]
        elif "booleanValue" in field:
            row[columns[index]] = field["booleanValue"]
        elif "isNull" in field:
            row[columns[index]] = None
        else:
            row[columns[index]] = str(field)
    return row


def _statement_args(sql: str, parameters: Optional[list]) -> Dict[str, Any]:
    """Build the common ``execute_statement`` keyword arguments."""
    args: Dict[str, Any] = {
        "resourceArn": DB_CLUSTER_ARN,
        "secretArn": SECRET_ARN,
        "database": DATABASE,
        "sql": sql,
        # Without this the Data API omits columnMetadata entirely, so columns
        # is [] and the first returned row IndexErrors (box-verified
        # 2026-06-12 — "list index out of range" on every successful SELECT).
        "includeResultMetadata": True,
    }
    if parameters:
        args["parameters"] = parameters
    return args


def execute_sql(sql: str, parameters: Optional[list] = None) -> List[Dict[str, Any]]:
    """Execute one statement via the Data API and return rows as dicts.

    Args:
        sql: A single statement. The Data API does not accept more than one
            ("Multistatements aren't supported"), which is why session settings
            need `execute_in_transaction` instead of a prepended ``SET``.
        parameters: Data API parameter dicts, or None.

    Returns:
        The result rows.
    """
    response = rds_client.execute_statement(**_statement_args(sql, parameters))
    columns = [column["name"] for column in response.get("columnMetadata", [])]
    return [row_to_dict(record, columns) for record in response.get("records", [])]


_POSITIONAL = re.compile(r"%s")


def _parameter(name: str, value: Any) -> Dict[str, Any]:
    """One Data API parameter, typed from the Python value.

    Integers travel as ``longValue``, which arrives as bigint, so a store tool
    that calls a function with an ``integer`` parameter casts at the call site
    (``%s::integer``); PostgreSQL does not narrow bigint implicitly when it
    resolves an overload. A list binds as ``text[]``.
    """
    if value is None:
        field: Dict[str, Any] = {"isNull": True}
    elif isinstance(value, bool):
        field = {"booleanValue": value}
    elif isinstance(value, int):
        field = {"longValue": value}
    elif isinstance(value, float):
        field = {"doubleValue": value}
    elif isinstance(value, (list, tuple)):
        field = {"arrayValue": {"stringValues": [str(item) for item in value]}}
    else:
        field = {"stringValue": str(value)}
    return {"name": name, "value": field}


def _named(sql: str, params: Sequence[Any]) -> tuple[str, List[Dict[str, Any]]]:
    """Rewrite positional ``%s`` placeholders as ``:pN`` and type the values.

    The Data API reads a backslash inside a quoted literal as an escape and then
    treats the rest of the statement as one string, leaving later placeholders
    unbound (``syntax error at or near ":"``). Such SQL is refused here, before
    it reaches AWS; write ``chr(92)`` for a literal backslash.
    """
    if "\\" in sql:
        raise ValueError(
            "store SQL contains a backslash, which the RDS Data API misreads inside a "
            "quoted literal; write chr(92) instead"
        )
    values = list(params)
    seen = 0

    def placeholder(_match: "re.Match[str]") -> str:
        nonlocal seen
        seen += 1
        return f":p{seen - 1}"

    named = _POSITIONAL.sub(placeholder, sql)
    if seen != len(values):
        raise ValueError(
            f"store SQL declares {seen} %s placeholders but binds {len(values)} parameters"
        )
    return named, [_parameter(f"p{index}", value) for index, value in enumerate(values)]


def run_store_sql(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    """The ``store_tools`` runner for this rail.

    ``store_tools`` writes SQL with positional ``%s`` placeholders so psycopg can
    bind it directly. The Data API takes named parameters, so each placeholder
    becomes ``:pN`` in order and the values are typed by ``_parameter``. Rows
    come back as dicts keyed by column name; numeric and timestamp columns are
    strings or numbers here where psycopg would return ``Decimal`` and
    ``datetime``, which the tools' shaping helpers accept.
    """
    return execute_sql(*_named(sql, params))


def execute_write(sql: str, parameters: Optional[list] = None) -> None:
    """Execute a statement whose rows are not the point.

    Distinct from `execute_sql` so a write and a read are different calls at
    this seam. Collapsing them would make an evidence INSERT indistinguishable
    from a catalog SELECT to anything observing the transport, including tests
    that stub reads while capturing writes.

    Args:
        sql: A single INSERT, UPDATE, or DELETE.
        parameters: Data API parameter dicts, or None.
    """
    rds_client.execute_statement(**_statement_args(sql, parameters))


def begin_transaction() -> str:
    """Open a Data API transaction and return its id.

    Transport, like everything else here, so it belongs to the module that owns
    the client. A surface server holding its own client would give the process
    two of them, and then a mutation and its audit row could be issued through
    different clients while looking like one transaction in the code.

    Returns:
        The transaction id to pass to `execute_in_transaction`, `commit`, or
        `rollback`.
    """
    return rds_client.begin_transaction(
        resourceArn=DB_CLUSTER_ARN, secretArn=SECRET_ARN, database=DATABASE
    )["transactionId"]


def commit_transaction(transaction_id: str) -> None:
    """Commit a Data API transaction."""
    rds_client.commit_transaction(
        resourceArn=DB_CLUSTER_ARN, secretArn=SECRET_ARN, transactionId=transaction_id
    )


def rollback_transaction(transaction_id: str) -> None:
    """Roll back a Data API transaction, swallowing a secondary failure.

    Called from an exception handler. Raising here would replace the error the
    caller is already reporting with a less useful one.
    """
    try:
        rds_client.rollback_transaction(
            resourceArn=DB_CLUSTER_ARN,
            secretArn=SECRET_ARN,
            transactionId=transaction_id,
        )
    except Exception:  # pragma: no cover - best effort during failure handling
        logger.warning("rollback failed for transaction %s", transaction_id)


def execute_in_transaction(
    transaction_id: str, sql: str, parameters: Optional[list] = None
) -> List[Dict[str, Any]]:
    """Execute one statement inside an existing Data API transaction.

    Statements sharing a ``transactionId`` share a server-side transaction, so
    transaction-scoped settings established by an earlier call still apply.

    Args:
        transaction_id: From ``begin_transaction``.
        sql: A single statement.
        parameters: Data API parameter dicts, or None.

    Returns:
        The result rows.
    """
    args = _statement_args(sql, parameters)
    args["transactionId"] = transaction_id
    response = rds_client.execute_statement(**args)
    columns = [column["name"] for column in response.get("columnMetadata", [])]
    return [row_to_dict(record, columns) for record in response.get("records", [])]


def bind_runtime_principal(transaction_id: str, *, customer_id: str) -> None:
    """Switch this transaction to ``pellier_agent`` and name the customer.

    The one place this rail binds row-level security. The policies show a row
    only when its customer's ``cognito_username`` equals
    ``pellier.principal_username``, so the setting is that customer's sign-in
    name. The customer is the one the call carries, which the Gateway's
    owner-only Cedar permit has already matched to the caller's token: the
    Gateway hands a Lambda no other verified identity. An unknown customer
    binds an empty name, which matches no rows.

    Both settings are transaction-local, and statements sharing a
    ``transactionId`` share one server-side transaction, so they hold for the
    reads that follow and end with it.
    """
    execute_in_transaction(transaction_id, f"SET LOCAL ROLE {CUSTOMER_ROLE};")
    execute_in_transaction(
        transaction_id,
        "SELECT set_config('pellier.principal_username', coalesce("
        "(SELECT cognito_username FROM pellier.customers WHERE id = :customer), ''), true);",
        [{"name": "customer", "value": {"stringValue": str(customer_id or "")}}],
    )


Result = TypeVar("Result")


def run_as_customer(customer_id: str, work: Callable[..., Result]) -> Result:
    """Run ``work(run)`` as ``pellier_agent`` with ``customer_id`` named.

    ``run`` is a ``store_tools`` runner whose statements share one transaction
    with the binding, so row-level security applies to every one of them. The
    transaction is read-only work and is committed; any failure rolls it back.
    """
    transaction_id = begin_transaction()
    try:
        bind_runtime_principal(transaction_id, customer_id=customer_id)

        def run(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
            return execute_in_transaction(transaction_id, *_named(sql, params))

        result = work(run)
    except Exception:
        rollback_transaction(transaction_id)
        raise
    commit_transaction(transaction_id)
    return result


def write_tool_audit_independently(
    *,
    tool: str,
    args: Dict[str, Any],
    result: Dict[str, Any],
    latency_ms: float,
    session_id: str,
    build_fingerprint: Optional[str] = None,
) -> None:
    """Write the execution receipt in its OWN transaction, so it survives.

    The audit row used to be written inside the mutation's transaction, which
    meant a rolled-back business write took its receipt with it. That makes the
    most important governance outcome unprovable: an action that Cedar allowed,
    that entered the tool, and that Aurora then refused would leave no trace at
    all, and "nothing happened" would be indistinguishable from "nothing was ever
    attempted".

    So the receipt commits independently. The ordering guarantee that matters is
    preserved by the caller: nothing writes a receipt unless the tool was
    actually entered, and a Cedar denial never reaches this module.

    This writer can only INSERT into ``pellier.tool_audit``. It cannot alter
    business state, by construction, so an audit failure can never corrupt a
    mutation and vice versa.
    """
    try:
        execute_write(
            f"INSERT INTO {SCHEMA}.tool_audit "
            "(session_id, tool, caller, args, result, latency_ms, build_fingerprint) "
            "VALUES (:session_id, :tool, 'gateway', :args::jsonb, :result::jsonb, "
            ":latency_ms, :build_fingerprint);",
            [
                {"name": "session_id", "value": {"stringValue": session_id}},
                {"name": "tool", "value": {"stringValue": tool}},
                {"name": "args", "value": {"stringValue": json.dumps(args, default=str)}},
                {
                    "name": "result",
                    "value": {"stringValue": json.dumps(result, default=str)},
                },
                {"name": "latency_ms", "value": {"longValue": int(latency_ms)}},
                _parameter("build_fingerprint", build_fingerprint or None),
            ],
        )
    except Exception as exc:  # noqa: BLE001 - evidence must not break the write
        logger.error("independent tool_audit write failed for %s: %s", tool, exc)


def query_embedding(text: str) -> List[float]:
    """Embed a live shopper query in the catalog's vector space.

    ``input_type`` is ``search_query`` because these are queries, not catalog
    documents. See `EMBED_MODEL_ID` for why the model must not diverge from the
    in-process rail.

    Args:
        text: The shopper's query text.

    Returns:
        A 1024-dimension embedding.
    """
    response = bedrock_client.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=json.dumps(
            {
                "texts": [text],
                "input_type": "search_query",
                "output_dimension": EMBED_DIMENSION,
            }
        ),
    )
    return json.loads(response["body"].read())["embeddings"]["float"][0]


def rerank_documents(*, query: str, documents: Sequence[str], top_n: int) -> List[Dict[str, Any]]:
    """Cohere Rerank 3.5 on Bedrock; ``[]`` on any failure.

    Returning ``[]`` instead of raising matches the in-process service, so the
    search tool falls back to RRF order and says so in ``search_method``.
    """
    if not documents:
        return []
    sources = [
        {"type": "INLINE", "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": doc}}}
        for doc in documents
    ]
    try:
        response = bedrock_agent_runtime_client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            sources=sources,
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": f"arn:aws:bedrock:{REGION}::foundation-model/{RERANK_MODEL_ID}"
                    },
                    "numberOfResults": min(int(top_n), len(sources)),
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - rerank is optional on this rail
        logger.warning("Cohere rerank failed: %s", exc)
        return []
    return [
        {"index": item.get("index"), "relevance_score": item.get("relevanceScore", 0.0)}
        for item in response.get("results", [])
    ]
