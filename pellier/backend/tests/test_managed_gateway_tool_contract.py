"""Guard the canonical tool vocabulary across every managed deployment copy.

Two different numbers live in this repository and confusing them is a documented
mistake, so they are named here once:

  * **9** tools in the canonical vocabulary. The one Gateway Lambda and the one schema
    in ``gateway_tool_schemas.TOOL_SCHEMAS["store"]`` cover all of them.
  * **8** tools this workshop iteration PUBLISHES at the start (9 after Lab 3a),
    because ``get_tickets`` is deferred. That subset is asserted in
    ``test_fresh_policy_set.py``, which owns the publication contract.

This file asserts the vocabulary, not the publication subset.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "scripts" / "deploy"

CANONICAL_TOOLS = {
    "search_products",
    "browse_department",
    "compare_products",
    "check_stock",
    "get_orders",
    "get_return_policy",
    "get_tickets",
    "give_store_credit",
    "ask_a_person",
}


SURFACE_FILES = {
    "store": DEPLOY / "pellier_store_tools.py",
}


def _assignment(path: Path, name: str) -> ast.expr:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return node.value
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return node.value
    raise AssertionError(f"{name} not found in {path}")


def _dict_items(node: ast.expr) -> dict[str, ast.expr]:
    assert isinstance(node, ast.Dict)
    return {
        key.value: value
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _dict_keys(node: ast.expr) -> set[str]:
    return set(_dict_items(node))


def _gateway_schema_names() -> dict[str, set[str]]:
    surfaces = _dict_items(
        _assignment(DEPLOY / "gateway_tool_schemas.py", "TOOL_SCHEMAS")
    )
    result: dict[str, set[str]] = {}
    for surface, config_node in surfaces.items():
        tools_node = _dict_items(config_node)["tools"]
        assert isinstance(tools_node, ast.List)
        result[surface] = {
            _dict_items(tool_node)["name"].value
            for tool_node in tools_node.elts
        }
    return result


def _lambda_names() -> dict[str, set[str]]:
    return {
        surface: _dict_keys(_assignment(path, "TOOLS"))
        for surface, path in SURFACE_FILES.items()
    }


def _imports_from_schemas(source: str) -> set[str]:
    """Names a module imports from `gateway_tool_schemas`, in either import form.

    Asserted by name rather than as a literal import line: the renderer grew a
    parenthesised multi-line import when the publication helpers were added, and a
    string match on the single-line form failed while the derivation it was protecting
    was still intact. The property that matters is that both deployment paths take
    their schemas from the one module instead of re-declaring them.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "gateway_tool_schemas":
            names.update(alias.name for alias in node.names)
    return names


def test_every_managed_surface_covers_the_canonical_vocabulary() -> None:
    lambda_names = _lambda_names()
    gateway_names = _gateway_schema_names()

    assert lambda_names == gateway_names
    published = set().union(*lambda_names.values())
    assert len(published) == 9
    assert published == CANONICAL_TOOLS


def test_both_deployment_paths_derive_schemas_from_one_module() -> None:
    provisioner = (
        REPO / "scripts" / "provision_agentcore_end_to_end.py"
    ).read_text(encoding="utf-8")
    renderer = (DEPLOY / "render_agentcore_project.py").read_text(encoding="utf-8")
    for label, source in (("provisioner", provisioner), ("renderer", renderer)):
        imported = _imports_from_schemas(source)
        assert "TOOL_SCHEMAS" in imported, f"{label} no longer imports TOOL_SCHEMAS"
        assert "schema_for" in imported, f"{label} no longer imports schema_for"


def test_in_process_and_recovery_files_match_the_managed_contract() -> None:
    paths = [
        REPO / "pellier" / "backend" / "services" / "agent_tools.py",
        REPO / "solutions" / "closing-marcos-gap" / "services"
        / "agent_tools_builders_preapply.py",
        REPO / "solutions" / "closing-marcos-gap" / "services"
        / "agent_tools_check_stock_solution.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        decorated = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(decorator, ast.Name) and decorator.id == "tool"
                for decorator in node.decorator_list
            )
        }
        assert decorated == CANONICAL_TOOLS, path


def test_the_store_tools_module_names_the_same_nine_tools() -> None:
    from services import store_tools

    assert set(store_tools.TOOL_NAMES) == CANONICAL_TOOLS
    assert len(store_tools.TOOL_NAMES) == len(set(store_tools.TOOL_NAMES))


def test_gateway_targets_are_owned_by_agentcore_cli_project() -> None:
    source = (DEPLOY / "render_agentcore_project.py").read_text(encoding="utf-8")
    assert '"targetType": "lambdaFunctionArn"' in source
    assert '"lambdaArn": lambda_arns[surface]' in source
    assert '"toolSchemaFile"' in source
    assert "deploy_gateway.py" not in source


def test_workshop_dependencies_are_immutable() -> None:
    backend_lock = REPO / "pellier" / "backend" / "requirements.lock"
    uv_lock = REPO / "pellier" / "backend" / "uv.lock"
    assert backend_lock.is_file()
    assert uv_lock.is_file()
    locked = backend_lock.read_text(encoding="utf-8")
    assert "--generate-hashes" in locked
    assert "--hash=sha256:" in locked
    for package in ("bedrock-agentcore", "boto3", "mcp", "strands-agents"):
        assert re_search_exact_pin(locked, package), package

    deploy_requirements = (
        DEPLOY / "requirements.txt"
    ).read_text(encoding="utf-8").splitlines()
    for line in deploy_requirements:
        clean = line.strip()
        if clean and not clean.startswith("#"):
            assert "==" in clean, clean
    deploy_lambda = (DEPLOY / "deploy_lambda.py").read_text(encoding="utf-8")
    assert "'mcp==1.28.1'" in deploy_lambda
    assert '"bedrock:Rerank"' in deploy_lambda


def re_search_exact_pin(requirements: str, package: str) -> bool:
    import re

    return re.search(
        rf"(?m)^{re.escape(package)}(?:\[[^]]+\])?==[^\s\\]+",
        requirements,
    ) is not None


def test_imperative_resources_receive_workshop_ownership_tags() -> None:
    paths = [
        DEPLOY / "render_agentcore_project.py",
        DEPLOY / "deploy_lambda.py",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "PellierWorkshopId" in source, path
