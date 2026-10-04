"""Guards for the membership ladder and the operator client book.

Migration 018 seeds client order history by joining on product *ID*:

    JOIN pellier.product_catalog pc ON pc."productId" = os.product_id

That join is silent when it fails. A renamed or missing SKU does not raise;
it produces zero rows, and the failure surfaces much later as an operator
console full of empty client records. The migration has a runtime guard for
this, but a runtime guard only fires on a machine with a database. These tests
catch the same drift in CI, before anyone deploys.

They also keep the four places that carry a membership rung in agreement:
the migration (authoritative), the backend persona config, the frontend
persona fallback, and the frontend membership module.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "scripts" / "migrations" / "018_client_book.sql"
LIVE_PERSONAS = REPO / "scripts" / "migrations" / "029_live_surface_data.sql"
FRONTEND_MEMBERSHIP = REPO / "pellier" / "frontend" / "src" / "data" / "membership.ts"
DATABASE_SETUP = REPO / "scripts" / "setup" / "database-setup.sh"
DATABASE_RESET = REPO / "scripts" / "setup" / "database-reset.sh"

RUNGS = ("registered", "circle", "maison")

def _load_seed_module():
    module_name = "seed_pellier_catalog_for_client_book_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]
    script_path = REPO / "scripts" / "seed_pellier_catalog.py"
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


def _migration_sql() -> str:
    return MIGRATION.read_text()


def _ordered_product_ids() -> list[str]:
    """Every product_id in the migration's order_seed VALUES list."""
    sql = _migration_sql()
    start = sql.index("WITH order_seed(")
    end = sql.index("INSERT INTO pellier.orders", start)
    block = sql[start:end]
    # ('CUST-JESSICA', '41', 34, 3900),
    rows = re.findall(r"\(\s*'([^']+)'\s*,\s*'((?:[^']|'')+)'\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", block)
    assert rows, "no order_seed rows parsed from migration 018"
    return [product_id for _cust, product_id, _days, _cents in rows]


def _seeded_memberships() -> dict[str, str]:
    """customer_id -> membership for every row 018 writes."""
    sql = _migration_sql()
    out: dict[str, str] = {}

    # Hero personas are set with UPDATE statements.
    for m in re.finditer(
        r"UPDATE pellier\.customers SET membership = '(\w+)'\s+WHERE id = '([^']+)'",
        sql,
    ):
        out[m.group(2)] = m.group(1)

    # Client book rows come from the INSERT ... VALUES list.
    start = sql.index("INSERT INTO pellier.customers (id, name, preferences_summary, membership)")
    end = sql.index("ON CONFLICT (id) DO UPDATE", start)
    block = sql[start:end]
    for m in re.finditer(
        r"\('(CUST-[A-Z]+)',\s*'[^']+',\s*\n\s*'(?:[^']|'')+',\s*\n\s*'(\w+)'\)",
        block,
    ):
        out[m.group(1)] = m.group(2)

    assert out, "no membership assignments parsed from migration 018"
    return out


# ---------------------------------------------------------------------------
# The silent-join guard. This is the test that matters most.
# ---------------------------------------------------------------------------

def test_every_seeded_order_names_a_real_catalog_product():
    """A typo here yields zero rows, not an error. Catch it in CI."""
    seed = _load_seed_module()
    catalog_ids = {str(p.productId) for p in seed.load_catalog()}

    ordered = _ordered_product_ids()
    missing = sorted({i for i in ordered if i not in catalog_ids})

    assert not missing, (
        f"Migration 018 orders {len(missing)} product ID(s) that do not exist "
        f"in data/pellier_catalog.json: {missing}. The ID JOIN would "
        "silently produce zero order rows."
    )


def test_jessica_owns_both_items_the_return_dispute_names():
    """The operator walkthrough asks about exactly these two SKUs."""
    sql = _migration_sql()
    start = sql.index("WITH order_seed(")
    end = sql.index("INSERT INTO pellier.orders", start)
    block = sql[start:end]

    jessica = re.findall(r"\('CUST-JESSICA',\s*'((?:[^']|'')+)'", block)
    assert "41" in jessica
    assert "42" in jessica

    seed = _load_seed_module()
    catalog_names = {str(p.productId): p.name for p in seed.load_catalog()}
    assert catalog_names["41"] == "Coral Lacquer Catchall"
    assert catalog_names["42"] == "Waffle Bath Robe, Sage"


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------

def test_membership_check_constraint_lists_exactly_the_three_rungs():
    sql = _migration_sql()
    m = re.search(r"CHECK \(membership IN \(([^)]+)\)\)", sql)
    assert m, "no membership CHECK constraint found in migration 018"
    listed = tuple(re.findall(r"'(\w+)'", m.group(1)))
    assert listed == RUNGS, f"CHECK lists {listed}, expected {RUNGS}"


def test_the_column_is_membership_and_never_tier():
    """`tier` already means editorial rank and Gateway tool capability."""
    sql = _migration_sql()
    assert "ADD COLUMN IF NOT EXISTS membership TEXT" in sql
    offending = [
        line
        for line in sql.splitlines()
        if re.search(r"\btier\b", line) and not line.lstrip().startswith("--")
    ]
    assert not offending, (
        "Migration 018 uses the word 'tier' outside a comment: "
        f"{offending}. product_catalog.tier is editorial rank 1/2/3 and "
        "agentcore_gateway.py uses TIER_* for tool capability."
    )


def test_all_three_rungs_are_seeded():
    """The storefront demonstrates the ladder through the hero personas."""
    rungs = set(_seeded_memberships().values())
    assert set(RUNGS) <= rungs, f"only {sorted(rungs)} seeded, expected all of {RUNGS}"


def test_client_book_has_four_customers():
    seeded = _seeded_memberships()
    book = {c for c in seeded if c.startswith("CUST-") and c != "CUST-FRESH"}
    assert book == {"CUST-MARCO", "CUST-ANNA", "CUST-THEO", "CUST-JESSICA"}


def test_spend_is_not_stored_by_the_migration():
    sql = _migration_sql()
    assert "DROP COLUMN IF EXISTS spend_12mo" in sql
    assert "ADD COLUMN IF NOT EXISTS spend_12mo" not in sql


# ---------------------------------------------------------------------------
# Cross-file agreement: migration is authoritative
# ---------------------------------------------------------------------------

def test_live_persona_profiles_match_the_membership_seed():
    seeded = _seeded_memberships()
    sql = LIVE_PERSONAS.read_text()
    expected = {
        "marco": ("CUST-MARCO", "maison"),
        "anna": ("CUST-ANNA", "circle"),
        "theo": ("CUST-THEO", "registered"),
    }
    for persona_id, (customer_id, membership) in expected.items():
        assert customer_id in seeded
        assert f"'{persona_id}', '{customer_id}'" in sql
        assert f"'{membership}'" in sql
        assert seeded[customer_id] == membership


def test_frontend_membership_module_lists_exactly_the_three_rungs():
    ts = FRONTEND_MEMBERSHIP.read_text()
    m = re.search(r"MEMBERSHIP_RUNGS = \[([^\]]+)\]", ts)
    assert m, "MEMBERSHIP_RUNGS not found in membership.ts"
    listed = tuple(re.findall(r"'(\w+)'", m.group(1)))
    assert listed == RUNGS, f"membership.ts lists {listed}, expected {RUNGS}"
    for rung in RUNGS:
        assert re.search(rf"\b{rung}: \{{", ts), f"membership.ts has no detail for {rung}"


# ---------------------------------------------------------------------------
# The migration has to actually run
# ---------------------------------------------------------------------------

def test_migration_is_registered_in_both_runners():
    assert "018_client_book.sql" in DATABASE_SETUP.read_text(), (
        "018_client_book.sql is not applied by scripts/setup/database-setup.sh, so a "
        "fresh account would have no client book."
    )
    assert "018_client_book.sql" in DATABASE_RESET.read_text(), (
        "018_client_book.sql is not applied by scripts/setup/database-reset.sh, "
        "so a reset would drop the client book."
    )


def test_migration_is_transactional_and_idempotent_in_shape():
    sql = _migration_sql()
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "ADD COLUMN IF NOT EXISTS" in sql
    assert "ON CONFLICT (id) DO UPDATE" in sql
    # Orders are refreshed rather than duplicated on re-run.
    assert "DELETE FROM pellier.orders" in sql


# ---------------------------------------------------------------------------
# The new catalog buckets
# ---------------------------------------------------------------------------

def test_new_buckets_have_real_cached_embeddings():
    """Not derived blends. These are genuine Cohere Embed v4 output."""
    seed = _load_seed_module()
    cache = json.loads((REPO / "data" / "embeddings_cache.json").read_text())

    assert cache["dim"] == seed.EMBED_DIM
    assert cache["model"] == "us.cohere.embed-v4:0"

    for pid in range(41, 61):
        vector = cache["embeddings"].get(str(pid))
        assert vector, f"product {pid} has no committed embedding"
        assert len(vector) == seed.EMBED_DIM, f"product {pid} vector is {len(vector)}-dim"
        assert any(abs(v) > 1e-9 for v in vector), f"product {pid} vector is all zeros"


def test_every_curated_product_has_a_committed_embedding():
    seed = _load_seed_module()
    cache = json.loads((REPO / "data" / "embeddings_cache.json").read_text())
    curated_ids = {p.productId for p in seed.load_catalog()}

    missing = sorted(pid for pid in curated_ids if str(pid) not in cache["embeddings"])
    assert not missing, f"curated products with no committed embedding: {missing}"
    assert len(cache["embeddings"]) == len(curated_ids)


def test_photographed_house_and_signature_images_follow_the_slug_convention():
    """Products 1 to 60 have photos; 61 to 100 use the placeholder until theirs land."""
    seed = _load_seed_module()
    for p in seed.load_catalog():
        if p.persona not in ("house", "signature") or p.productId > 60:
            continue
        assert p.imgPath.startswith(f"{p.persona}-"), (
            f"product {p.productId} image '{p.imgPath}' does not start with "
            f"'{p.persona}-'"
        )
        assert p.imgPath.endswith(".png"), p.imgPath


def test_catalog_prices_stay_everyday():
    """Pellier is an everyday-price store: nothing costs more than $450."""
    seed = _load_seed_module()
    ceiling = max(p.price for p in seed.load_catalog())
    assert ceiling <= 450, f"catalog ceiling is {ceiling}"


def test_every_rung_pairs_a_label_with_a_functional_descriptor() -> None:
    """Premium branding plus instant comprehension, not one without the other.

    "Gold" tells an advisor the rung; "private client"
    tells them what it means. Wherever the tier matters operationally both are
    shown, so both must exist.
    """
    ts = FRONTEND_MEMBERSHIP.read_text()
    expected = {
        "registered": "standard client",
        "circle": "priority client",
        "maison": "private client",
    }
    for rung, descriptor in expected.items():
        block = re.search(rf"{rung}: \{{(.*?)\}}", ts, re.S)
        assert block, f"{rung} block not found in membership.ts"
        assert f"descriptor: '{descriptor}'" in block.group(1), (
            f"{rung} should describe itself as '{descriptor}'"
        )

    # The short labels read cleanly in the ladder: Member / Silver / Gold.
    for label in ("Member", "Silver", "Gold"):
        assert f"label: '{label}'" in ts


def test_the_console_states_that_standing_is_not_authorization() -> None:
    """Tier, Cedar, and RLS are three independent questions.

    A rung may qualify a client for an expedited replacement or a larger
    courtesy allowance. It decides nothing about whether the action is
    permitted. The operator is told this on the surface where they act, so the
    copy is asserted rather than trusted to survive edits.
    """
    raw = (
        REPO / "pellier" / "frontend" / "src" / "operator" / "surfaces"
        / "ClientRecord.tsx"
    ).read_text()
    # Whitespace is collapsed because JSX wraps prose across lines. Asserting
    # the literal source substring would make this a formatting test that any
    # re-wrap breaks.
    record = " ".join(raw.split())

    assert "Standing is business context" in record
    assert "For tools exposed through Gateway, AgentCore Policy decides whether the action is permitted" in record
    assert "Aurora still decides whether the data may be changed" in record
