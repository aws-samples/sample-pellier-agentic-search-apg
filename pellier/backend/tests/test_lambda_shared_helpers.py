"""The Gateway surface Lambdas must share their transport, not copy it.

Four Lambda servers reach Aurora through the RDS Data API. Each had grown its
own copy of the same plumbing, and the copies had drifted: one transaction
helper silently dropped `booleanValue` and `isNull`, and the two embedding
helpers stated the same vector-space warning in different words.

Neither drift raises. A dropped boolean reads as missing data; a diverged
embedding model ranks wrongly while returning a full result set. So the guard
has to be structural, not behavioral.

The packaging test is the one that protects a fresh deploy. `deploy_lambda.py`
builds each zip from an explicit file map, so importing a new shared module
without adding it there produces a `ModuleNotFoundError` on the first Gateway
call, long after the deploy reported success.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
SURFACES = sorted(DEPLOY.glob("pellier_*_server.py"))
DEPLOY_LAMBDA = DEPLOY / "deploy_lambda.py"

# Handlers are legitimately per-surface: each dispatches a different slice of
# the 15-tool contract, so their bodies differ by design.
_PER_SURFACE = {"lambda_handler"}


def test_the_surfaces_were_found() -> None:
    """Guards against a rename turning every assertion below vacuous."""
    assert len(SURFACES) == 4, [p.name for p in SURFACES]


def _functions(path: Path) -> Dict[str, Tuple[str, int]]:
    """Return {name: (normalized-body hash, line count)} for top-level defs."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    found: Dict[str, Tuple[str, int]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
        normalized = "\n".join(l.strip() for l in segment.splitlines() if l.strip())
        found[node.name] = (
            hashlib.sha256(normalized.encode()).hexdigest(),
            node.end_lineno - node.lineno + 1,
        )
    return found


def test_no_helper_body_is_copied_between_surfaces() -> None:
    """An identical body in two files is a copy waiting to diverge."""
    seen: Dict[Tuple[str, str], List[str]] = {}
    for path in SURFACES:
        for name, (digest, _) in _functions(path).items():
            if name in _PER_SURFACE:
                continue
            seen.setdefault((name, digest), []).append(path.name)

    copies = {key: files for key, files in seen.items() if len(files) > 1}

    assert not copies, "identical bodies in multiple surfaces; move to common/: " + ", ".join(
        f"{name} in {files}" for (name, _), files in sorted(copies.items())
    )


def test_transport_helpers_live_in_the_shared_module_only() -> None:
    """These specific helpers are transport, so no surface may redefine one.

    Listed by name rather than inferred: a near-copy that differs by a comment
    would slip past the identical-body test above, which is exactly how the
    boolean-dropping converter survived.
    """
    shared = {
        "_execute_sql",
        "_execute_in_transaction",
        "_row_to_dict",
        "_get_embedding",
    }
    offenders = {
        path.name: sorted(shared & set(_functions(path)))
        for path in SURFACES
        if shared & set(_functions(path))
    }

    assert not offenders, f"transport redefined locally: {offenders}"


def _shared_imports(path: Path) -> Set[str]:
    """Return the `common/<module>.py` paths a surface file imports."""
    modules: Set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("common."):
            modules.add(node.module.replace(".", "/") + ".py")
    return modules


def test_every_shared_import_is_packaged_into_the_zip() -> None:
    """A shared import missing from the file map fails only on a live call."""
    packaged = set(re.findall(r"'(common/[a-z_]+\.py)'", DEPLOY_LAMBDA.read_text()))
    assert packaged, "deploy_lambda.py no longer names its shared modules"

    for path in SURFACES:
        missing = _shared_imports(path) - packaged
        assert not missing, (
            f"{path.name} imports {sorted(missing)}, which deploy_lambda.py does "
            "not package; the Lambda would raise ModuleNotFoundError on its "
            "first Gateway call"
        )


def test_the_packaged_shared_modules_exist_on_disk() -> None:
    for module in re.findall(r"'(common/[a-z_]+\.py)'", DEPLOY_LAMBDA.read_text()):
        assert (DEPLOY / module).is_file(), f"{module} is packaged but absent"


def test_every_standalone_boto3_client_in_deploy_lambda_pins_region() -> None:
    """A `boto3.client(...)` built outside the `--region`-bound session must

    still name a region explicitly, or it silently falls back to whatever
    region the calling host happens to have configured (or none at all,
    raising ``NoRegionError``). ``main()`` binds one ``boto3.Session(region_
    name=args.region)`` and calls ``session.client(...)`` from it, which is
    exempt; every bare ``boto3.client(...)`` elsewhere in the module must pass
    ``region_name`` itself, since it cannot inherit the session's region.
    """
    tree = ast.parse(DEPLOY_LAMBDA.read_text(encoding="utf-8"))
    unpinned: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "client"
            and isinstance(func.value, ast.Name)
            and func.value.id == "boto3"
        ):
            continue
        has_region = any(kw.arg == "region_name" for kw in node.keywords)
        if not has_region:
            unpinned.append(f"line {node.lineno}: boto3.client({ast.dump(node.args[0]) if node.args else ''})")
    assert not unpinned, (
        "boto3.client(...) call(s) in deploy_lambda.py do not pin region_name "
        f"and will use the ambient default region instead of --region: {unpinned}"
    )


# ---------------------------------------------------------------------------
# The converter that had drifted
# ---------------------------------------------------------------------------


def _dataapi():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pellier_dataapi_under_test", DEPLOY / "common" / "dataapi.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_false_and_null_are_not_the_same_value() -> None:
    """The dropped case. `false` coerced to None reads as missing data."""
    dataapi = _dataapi()
    columns = ["is_active", "archived_at", "name"]
    record = [{"booleanValue": False}, {"isNull": True}, {"stringValue": "linen"}]

    row = dataapi.row_to_dict(record, columns)

    assert row["is_active"] is False, "a boolean false must survive as False"
    assert row["archived_at"] is None
    assert row["name"] == "linen"


def test_true_survives_as_well() -> None:
    dataapi = _dataapi()

    assert dataapi.row_to_dict([{"booleanValue": True}], ["ok"])["ok"] is True


def test_numeric_shapes_keep_their_types() -> None:
    dataapi = _dataapi()
    row = dataapi.row_to_dict(
        [{"longValue": 7}, {"doubleValue": 4.5}], ["quantity", "price"]
    )

    assert row == {"quantity": 7, "price": 4.5}


def test_an_unknown_field_shape_is_visible_rather_than_null() -> None:
    """A new Data API type must not masquerade as SQL NULL."""
    dataapi = _dataapi()

    value = dataapi.row_to_dict([{"arrayValue": {"longValues": [1, 2]}}], ["ids"])["ids"]

    assert value is not None and "arrayValue" in value


def test_more_fields_than_columns_does_not_raise() -> None:
    """Metadata and records disagreeing must not take the Lambda down."""
    dataapi = _dataapi()

    assert dataapi.row_to_dict([{"longValue": 1}, {"longValue": 2}], ["only"]) == {
        "only": 1
    }


def test_result_metadata_is_always_requested() -> None:
    """Without it columnMetadata is absent and the first row IndexErrors."""
    dataapi = _dataapi()

    assert dataapi._statement_args("SELECT 1", None)["includeResultMetadata"] is True


def test_parameters_are_omitted_when_absent_rather_than_sent_empty() -> None:
    dataapi = _dataapi()

    assert "parameters" not in dataapi._statement_args("SELECT 1", None)
    assert "parameters" in dataapi._statement_args("SELECT 1", [{"name": "x"}])


# ---------------------------------------------------------------------------
# The audit row
# ---------------------------------------------------------------------------


def test_the_audit_writer_demands_an_explicit_session_handle() -> None:
    """The two callers key differently, so a default would silently mislabel.

    A customer-scoped tool keys on `gateway-<customer_id>`; an operator tool
    like `restock_inventory` has no customer in its arguments and keys on a role
    handle. A default here would write one of those onto the other's rows.
    """
    import inspect

    signature = inspect.signature(_dataapi().write_tool_audit)
    session = signature.parameters["session_id"]

    assert session.default is inspect.Parameter.empty
    assert session.kind is inspect.Parameter.KEYWORD_ONLY


def test_each_surface_keys_its_audit_rows_deliberately() -> None:
    """Both wrappers must state their session handle at the call site."""
    # Two writers, deliberately. `restock_inventory` keeps the in-transaction
    # receipt; the reviewable actions write independently so an Aurora denial
    # still leaves an attempt receipt behind.
    handles = {
        "pellier_search_server.py": ("gateway-stock-keeper", "write_tool_audit("),
        "pellier_experience_server.py": (
            "gateway-{customer_id}",
            "_write_tool_audit_independently(",
        ),
    }
    for filename, (expected, writer) in handles.items():
        body = (DEPLOY / filename).read_text()
        assert writer in body, f"{filename} no longer audits via {writer}"
        assert expected in body, f"{filename} lost its session handle {expected!r}"


def test_the_audit_row_is_written_inside_the_caller_s_transaction() -> None:
    """A row that commits separately can outlive a rolled-back mutation."""
    import inspect

    source = inspect.getsource(_dataapi().write_tool_audit)

    assert "transactionId=transaction_id" in source
    assert "caller" in source and "gateway" in source
