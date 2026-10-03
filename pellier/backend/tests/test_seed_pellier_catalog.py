"""The seeder loads one catalog file and has no generated rows."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _seed():
    spec = importlib.util.spec_from_file_location(
        "seed_catalog", REPO / "scripts" / "seed_pellier_catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_catalog"] = module
    spec.loader.exec_module(module)
    return module


def test_catalog_loads_from_the_json_file():
    seed = _seed()
    products = seed.load_catalog()
    assert [p.productId for p in products] == list(range(1, len(products) + 1))


def test_seeder_has_no_generated_rows():
    seed = _seed()
    for symbol in ("generate_distractor_products", "derive_distractor_embeddings",
                   "DEFAULT_DISTRACTOR_COUNT", "build_catalog"):
        assert not hasattr(seed, symbol), symbol


def test_search_text_carries_no_shopper_persona_sentence():
    seed = _seed()
    for p in seed.load_catalog():
        text = p.search_text.lower()
        assert "for a traveler" not in text and "for a gift-giver" not in text
        assert "client book" not in text and "investment piece" not in text


def test_every_department_is_one_of_the_eight():
    seed = _seed()
    assert len(seed.DEPARTMENTS) == 8
    assert {p.department for p in seed.load_catalog()} <= set(seed.DEPARTMENTS)


def test_database_dsn_honors_configured_port(monkeypatch):
    seed = _seed()
    for key, value in {"DB_HOST": "h", "DB_PORT": "6543", "DB_NAME": "n",
                       "DB_USER": "u", "DB_PASSWORD": "p"}.items():
        monkeypatch.setenv(key, value)
    assert "port=6543" in seed._database_dsn()
