"""The seeder loads one catalog file and has no generated rows."""
import importlib.util
import sys
from pathlib import Path

import pytest

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
    assert not hasattr(seed, "build_catalog")
    generated = [name for name in dir(seed) if "distract" in name.lower()]
    assert generated == []


def test_search_text_carries_no_shopper_persona_sentence():
    seed = _seed()
    for p in seed.load_catalog():
        text = p.search_text.lower()
        assert "for a traveler" not in text and "for a gift-giver" not in text
        assert "client book" not in text and "investment piece" not in text


def test_search_text_names_department_and_tags():
    seed = _seed()
    for p in seed.load_catalog():
        assert f"Category: {p.department}." in p.search_text
        assert f"Tags: {', '.join(p.tags)}." in p.search_text


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


def _embedded(seed, count):
    products = seed.load_catalog()[:count]
    for p in products:
        p.embedding = [0.1] * seed.EMBED_DIM
    return products


def test_cache_rejects_vectors_for_changed_text(tmp_path):
    seed = _seed()
    cache = tmp_path / "cache.json"
    seed.write_embeddings_cache(_embedded(seed, 2), str(cache))
    fresh = seed.load_catalog()[:2]
    fresh[0].description += " Changed."
    with pytest.raises(SystemExit, match=r"text changed for products \[1\]"):
        seed.load_embeddings_cache(fresh, str(cache))


def test_cache_rejects_a_product_without_a_vector(tmp_path):
    seed = _seed()
    cache = tmp_path / "cache.json"
    seed.write_embeddings_cache(_embedded(seed, 2), str(cache))
    with pytest.raises(SystemExit, match=r"no cached vector for products \[3\]"):
        seed.load_embeddings_cache(seed.load_catalog()[:3], str(cache))


def test_cache_round_trips_unchanged_text(tmp_path):
    seed = _seed()
    cache = tmp_path / "cache.json"
    seed.write_embeddings_cache(_embedded(seed, 2), str(cache))
    fresh = seed.load_catalog()[:2]
    assert seed.load_embeddings_cache(fresh, str(cache)) == 2
    assert all(len(p.embedding) == seed.EMBED_DIM for p in fresh)


def test_committed_cache_matches_the_catalog_text():
    seed = _seed()
    products = seed.load_catalog()
    assert seed.load_embeddings_cache(products, seed.EMBED_CACHE) == len(products)
