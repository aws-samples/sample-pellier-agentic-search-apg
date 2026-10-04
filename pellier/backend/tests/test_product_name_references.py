"""Every product name quoted in migrations, skills, prompts and frontend data exists in the catalog.

Skills get two stricter rules, because they are procedural memory: a skill
says how to answer, never what is true. A dollar amount anywhere under
``skills/`` fails, and so does a product-like name the catalog does not carry.
The old scan only checked a fixed list of retired names, which is how a
"Sage Overshirt" that never existed slipped past it.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CATALOG = REPO / "data" / "pellier_catalog.json"
SKILLS = REPO / "skills"
OLD_NAMES = (
    "Olive Branch Vessel", "Nocturne Leather Weekender", "Heritage Rectangular Watch",
    "Neroli Apothecary Bottle", "Solstice Woven Mat Set", "Alba Linen Lounge Set",
    "Cloudform Studio Runner", "Luxury Bath Robe, Sage", "Vetiver Quietude",
    "Cognac Market Tote", "Silk Charmeuse Slip Dress", "Hand-Knotted Wool Rug",
)
OLD_BRANDS = ("Pellier Editions", "Pellier Everyday", "Pellier Active", "Pellier Travel",
              "Pellier Apothecary", "Pellier Gifting", "Pellier Parfum", "Pellier Atelier",
              "Pellier Maison")
SCANNED = ("scripts/migrations", "skills", "pellier/backend/agents", "pellier/backend/services",
           "pellier/backend/routes", "pellier/frontend/src/data", "pellier/frontend/src/observatory/fixtures", "solutions")

# Capitalized phrases of two or more words read as product names. These are
# the ones in skills that are not products: skill titles, services, places.
SKILL_PROPER_NOUNS = {
    "The Gift Table", "The Maker's Shelf", "The Packing List", "The Proof Counter",
    "The Care Card", "AgentCore Memory", "Anchor Examples", "When To Apply",
    "Voice And Curation Rules", "Voice And Proof Rules", "Voice And Handling Rules",
    "Tool Discipline", "Pellier",
}
_PRODUCT_LIKE = re.compile(r"\b(?:[A-Z][A-Za-z'&-]+(?:[ -][A-Z][A-Za-z'&-]+)+)\b")
_DOLLAR = re.compile(r"\$\s?\d")


def _files():
    for root in SCANNED:
        for path in (REPO / root).rglob("*"):
            if path.is_file() and path.suffix in {".sql", ".md", ".py", ".ts", ".tsx", ".json"}:
                yield path


def _catalog_names() -> set[str]:
    return {product["name"] for product in json.loads(CATALOG.read_text())}


def _skill_bodies():
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        text = path.read_text()
        yield path, text.split("---", 2)[2] if text.startswith("---") else text


def test_no_old_product_or_brand_names_remain():
    offenders = []
    for path in _files():
        text = path.read_text(errors="ignore")
        for name in OLD_NAMES + OLD_BRANDS:
            if name in text:
                offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert offenders == []


def test_skills_carry_no_prices():
    offenders = [
        f"{path.relative_to(REPO)}: {line.strip()}"
        for path, body in _skill_bodies()
        for line in body.splitlines()
        if _DOLLAR.search(line)
    ]
    assert offenders == [], "prices come from tools, never from a skill"


def test_every_product_like_name_in_a_skill_exists_in_the_catalog():
    names = _catalog_names()
    offenders = []
    for path, body in _skill_bodies():
        for phrase in _PRODUCT_LIKE.findall(body):
            bare = phrase[4:] if phrase.startswith("The ") else phrase
            if bare in names or phrase.title() in SKILL_PROPER_NOUNS or phrase in SKILL_PROPER_NOUNS:
                continue
            offenders.append(f"{path.relative_to(REPO)}: {phrase}")
    assert offenders == [], "a skill may only name pieces the catalog carries"


def test_migrations_join_orders_by_product_id():
    for name in ("003_persona_seed.sql", "018_client_book.sql"):
        sql = (REPO / "scripts" / "migrations" / name).read_text()
        assert 'pc.name = os.product_name' not in sql, name
        assert 'pc."productId" = os.product_id' in sql, name
