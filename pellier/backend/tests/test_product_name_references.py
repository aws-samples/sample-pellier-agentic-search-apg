"""Every product name quoted in migrations, skills, prompts and frontend data exists in the catalog."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
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


def _files():
    for root in SCANNED:
        for path in (REPO / root).rglob("*"):
            if path.is_file() and path.suffix in {".sql", ".md", ".py", ".ts", ".tsx", ".json"}:
                yield path


def test_no_old_product_or_brand_names_remain():
    offenders = []
    for path in _files():
        text = path.read_text(errors="ignore")
        for name in OLD_NAMES + OLD_BRANDS:
            if name in text:
                offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert offenders == []


def test_migrations_join_orders_by_product_id():
    for name in ("003_persona_seed.sql", "018_client_book.sql"):
        sql = (REPO / "scripts" / "migrations" / name).read_text()
        assert 'pc.name = os.product_name' not in sql, name
        assert 'pc."productId" = os.product_id' in sql, name
