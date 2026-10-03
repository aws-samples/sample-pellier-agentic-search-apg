"""One department vocabulary across seed, planner, return policies and the storefront."""
from pathlib import Path

from services.structured_extract import KNOWN_CATEGORIES

REPO = Path(__file__).resolve().parents[3]
DEPARTMENTS = ("Clothing", "Shoes", "Bags and travel", "Accessories",
               "Home", "Kitchen and table", "Bath and body", "Stationery and gifts")
OLD = ("Home Decor", "Apparel", "Footwear", "Beauty", "Gifts")


def test_planner_knows_exactly_the_departments():
    assert tuple(KNOWN_CATEGORIES) == DEPARTMENTS


def test_return_policies_cover_every_department():
    sql = (REPO / "scripts" / "migrations" / "009_return_policies.sql").read_text()
    for department in DEPARTMENTS:
        assert f"'{department}'" in sql, department


def test_no_old_category_literals_remain():
    import subprocess
    pattern = "|".join(f"'{c}'|\"{c}\"" for c in OLD)
    hits = subprocess.run(
        ["git", "grep", "-n", "-I", "-E", pattern, "--", "pellier", "scripts",
         ":!*node_modules*", ":!*tests/test_departments.py"],
        cwd=REPO, capture_output=True, text=True).stdout.strip()
    assert hits == "", hits


def test_seed_storefront_and_keyword_map_share_the_departments():
    import ast
    from typing import get_args

    from models.search import StorefrontCategory
    from services.agent_tools import _CATEGORY_MAP

    seeder = ast.parse((REPO / "scripts" / "seed_pellier_catalog.py").read_text())
    seeded = next(ast.literal_eval(node.value) for node in seeder.body
                  if isinstance(node, ast.Assign)
                  and getattr(node.targets[0], "id", "") == "DEPARTMENTS")
    assert seeded == DEPARTMENTS
    assert get_args(StorefrontCategory) == DEPARTMENTS
    assert set(_CATEGORY_MAP.values()) <= set(DEPARTMENTS)


def test_recommendation_prompt_browse_departments_are_known():
    import re

    from pellier_copy import RECOMMENDATION_SYSTEM_PROMPT

    line = next(
        entry for entry in RECOMMENDATION_SYSTEM_PROMPT.split("\n- ")
        if entry.lstrip("- ").startswith("browse_category")
    )
    listed = re.search(r"named department \((.+?)\)", line, re.S).group(1)
    names = {name.strip() for name in listed.split(",")}
    assert names == set(KNOWN_CATEGORIES)


def test_backend_prompts_do_not_name_retired_categories():
    from pellier_copy import RECOMMENDATION_SYSTEM_PROMPT

    backend = REPO / "pellier" / "backend"
    texts = {"RECOMMENDATION_SYSTEM_PROMPT": RECOMMENDATION_SYSTEM_PROMPT}
    for path in [*(backend / "agents").glob("*.py"), backend / "services" / "chat.py"]:
        texts[path.name] = path.read_text()
    for name, text in texts.items():
        for retired in ("home decor", "footwear"):
            assert retired not in text.lower(), f"{name} names retired category {retired!r}"
