"""Parity: the Gateway search Lambda must behave like the in-process search.

Both sides are checked from source, the way ``test_rrf_parity`` pins the RRF
constant, so the alarm fires on the file a participant deploys rather than on a
fake that happens to agree.
"""

from __future__ import annotations

import ast
from typing import Any
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LAMBDA_PATH = _REPO_ROOT / "scripts" / "deploy" / "pellier_search_server.py"


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            assert segment, f"{path.name}::{name} has no source segment"
            return segment
    raise AssertionError(f"{path.name} defines no function named {name}")


# ---------------------------------------------------------------------------
# Lexical branch and post-rerank recheck: one behaviour on both rails
# ---------------------------------------------------------------------------

_PARITY_QUERIES = (
    "a thoughtful gift for someone who loves morning rituals",
    "linen shirt under 150 for the summer",
    "Pour-over set!",
    "the and for",
    "",
    "hand-thrown stoneware bowls, wabi-sabi",
    "a grey crewneck, not too heavy",
)


def test_grey_and_gray_search_the_same_catalog_word() -> None:
    from services.hybrid_search import HybridSearch

    assert HybridSearch._build_or_tsquery("a grey crewneck") == "gray | crewneck"
    assert HybridSearch._build_or_tsquery("a gray crewneck") == "gray | crewneck"


def _load_lambda(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Load the Lambda module with inert AWS clients."""
    import importlib.util

    import boto3

    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(boto3, "client", lambda *_args, **_kwargs: object())
    # The Lambda imports its packaged `common` modules from beside it.
    monkeypatch.syspath_prepend(str(_LAMBDA_PATH.parent))
    spec = importlib.util.spec_from_file_location("pellier_parity_search_server", _LAMBDA_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("query", _PARITY_QUERIES)
def test_gateway_lambda_builds_the_same_lexical_query(
    monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    from services.hybrid_search import HybridSearch

    module = _load_lambda(monkeypatch)
    assert module._build_or_tsquery(query) == HybridSearch._build_or_tsquery(query)


def test_gateway_lambda_lexical_branch_uses_the_or_joined_query() -> None:
    source = _function_source(_LAMBDA_PATH, "search_products_hybrid")
    assert "to_tsquery('english', :ts_query)" in source
    assert "plainto_tsquery" not in source, (
        "plainto_tsquery ANDs every stem; the in-process rail OR-joins tokens"
    )


def test_gateway_lambda_rechecks_eligibility_after_the_reranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row past the SQL predicates is dropped after reranking, as in process."""
    module = _load_lambda(monkeypatch)
    rows = [
        {"productId": 1, "name": "Linen Shirt", "price": 120, "stars": 4.5,
         "category_name": "Clothing", "quantity": 3, "product_description": "linen"},
        {"productId": 2, "name": "Cashmere Coat", "price": 900, "stars": 4.9,
         "category_name": "Clothing", "quantity": 3, "product_description": "wool"},
        {"productId": 3, "name": "Linen Tunic", "price": 80, "stars": 4.1,
         "category_name": "Clothing", "quantity": 0, "product_description": "linen"},
    ]
    monkeypatch.setattr(module, "_get_embedding", lambda _q: [0.0, 0.0])
    monkeypatch.setattr(module, "_execute_sql", lambda _sql, _params: [dict(r) for r in rows])
    monkeypatch.setattr(
        module, "_bedrock_rerank",
        lambda _q, docs, top_n: [{"index": i, "relevance_score": 1.0 - i / 10} for i in range(len(docs))],
    )
    result = module.search_products_hybrid("linen", max_price=150, limit=5)
    assert [p["productId"] for p in result["products"]] == [1]
    config = result["_receipt_evidence"]["retrieval_config"]
    assert config["eligibility_recheck"] is True
    assert config["eligibility_dropped"] == 2


def test_gateway_lambda_search_products_filters_category_in_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The category filter is a predicate, so the limit applies after it."""
    module = _load_lambda(monkeypatch)
    captured: dict[str, Any] = {}

    def _execute(sql: str, params: list) -> list:
        captured["sql"], captured["params"] = sql, params
        return []

    monkeypatch.setattr(module, "_get_embedding", lambda _q: [0.0, 0.0])
    monkeypatch.setattr(module, "_execute_sql", _execute)
    module.search_products("bowls", category="Kitchen and table", limit=5)
    assert "lower(category) LIKE :category" in captured["sql"]
    bound = {p["name"]: p["value"] for p in captured["params"]}
    assert bound["category"] == {"stringValue": module._prepare_like_pattern("Kitchen and table")}
    assert "category.lower() in" not in _function_source(_LAMBDA_PATH, "search_products")


def test_gateway_lambda_browse_category_escapes_like_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``browse_category``'s own argument must not act as a LIKE wildcard.

    This function built its category predicate with a raw f-string while
    ``semantic_search``/``search_products_hybrid`` in the same module used
    ``_prepare_like_pattern``; an untrusted ``%`` in ``category`` silently
    widened the filter to match every category instead of a literal
    substring.
    """
    module = _load_lambda(monkeypatch)
    captured: dict[str, Any] = {}

    def _execute(sql: str, params: list) -> list:
        captured["sql"], captured["params"] = sql, params
        return []

    monkeypatch.setattr(module, "_execute_sql", _execute)
    module.browse_category(category=r"Home_100% \ Decor")
    bound = {p["name"]: p["value"] for p in captured["params"]}
    assert bound["category"] == {
        "stringValue": module._prepare_like_pattern(r"Home_100% \ Decor")
    }
    assert bound["category"] == {"stringValue": r"%home\_100\% \\ decor%"}


def test_gateway_lambda_check_inventory_escapes_like_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``check_inventory``'s product-name tokens must not act as LIKE wildcards."""
    module = _load_lambda(monkeypatch)
    captured: dict[str, Any] = {}

    def _execute(sql: str, params: list) -> list:
        captured["sql"], captured["params"] = sql, params
        return []

    monkeypatch.setattr(module, "_execute_sql", _execute)
    module.check_inventory(product_query=r"100%_deal")
    bound = {p["name"]: p["value"] for p in captured["params"]}
    assert bound["token0"] == {"stringValue": module._prepare_like_pattern(r"100%_deal")}
    assert bound["token0"] == {"stringValue": r"%100\%\_deal%"}
