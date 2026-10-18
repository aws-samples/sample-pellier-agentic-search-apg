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


@pytest.mark.parametrize("flags", [[], ["--from-cache"], ["--csv-only"]])
def test_ordinary_seed_and_export_never_generate_embeddings(monkeypatch, flags):
    seed = _seed()
    products = seed.load_catalog()[:1]
    calls = []
    monkeypatch.setattr(sys, "argv", ["seed", *flags])
    monkeypatch.setattr(seed, "load_catalog", lambda: products)
    monkeypatch.setattr(seed, "generate_embeddings", lambda *a: pytest.fail("paid embedding generation"))
    monkeypatch.setattr(seed, "load_embeddings_cache", lambda *a: calls.append("cache"))
    monkeypatch.setattr(seed, "seed_database", lambda *a: calls.append("database"))
    monkeypatch.setattr(seed, "write_csv", lambda *a: calls.append("csv"))
    seed.main()
    assert calls == ["cache", "csv" if "--csv-only" in flags else "database"]


def test_missing_cache_stops_before_any_embedding_or_database_work(monkeypatch):
    seed = _seed()
    monkeypatch.setattr(sys, "argv", ["seed"])
    monkeypatch.setattr(seed, "load_catalog", lambda: [])
    def missing(*args):
        raise FileNotFoundError("cache missing")
    monkeypatch.setattr(seed, "load_embeddings_cache", missing)
    monkeypatch.setattr(seed, "generate_embeddings", lambda *a: pytest.fail("paid embedding fallback"))
    monkeypatch.setattr(seed, "seed_database", lambda *a: pytest.fail("database changed"))
    with pytest.raises(FileNotFoundError, match="cache missing"):
        seed.main()


def _embedded(seed, count):
    products = seed.load_catalog()[:count]
    for p in products:
        p.embedding = [0.1] * seed.EMBED_DIM
    return products


def test_cache_rejects_a_product_without_a_vector(tmp_path):
    seed = _seed()
    cache = tmp_path / "manifest.json"
    seed.write_sharded_embeddings_cache(_embedded(seed, 2), str(cache))
    with pytest.raises(SystemExit, match=r"no cached vector for products \[3\]"):
        seed.load_embeddings_cache(seed.load_catalog()[:3], str(cache))


def test_cache_refuses_a_format_it_does_not_shard(tmp_path):
    seed = _seed()
    cache = tmp_path / "cache.json"
    cache.write_text('{"model": "us.cohere.embed-v4:0", "dim": 1024, "embeddings": {}}')
    with pytest.raises(SystemExit, match="not the sharded float32-gzip-v1 format"):
        seed.load_embeddings_cache(seed.load_catalog()[:1], str(cache))


def test_committed_cache_matches_the_catalog_text():
    seed = _seed()
    products = seed.load_catalog()
    assert seed.load_embeddings_cache(products, seed.EMBED_CACHE) == len(products)


def test_seeder_materials_match_the_planner_vocabulary():
    from services.structured_extract import KNOWN_MATERIALS

    assert tuple(_seed().MATERIALS) == tuple(KNOWN_MATERIALS)


def test_sharded_cache_round_trip_and_subset(tmp_path):
    seed = _seed()
    cache = tmp_path / 'manifest.json'
    products = _embedded(seed, 3)
    products[1].embedding[7] = -0.75
    seed.write_sharded_embeddings_cache(products, str(cache), shard_size=2)
    fresh = seed.load_catalog()[:3]
    assert seed.load_embeddings_cache(fresh, str(cache)) == 3
    assert fresh[1].embedding[7] == -0.75
    assert fresh[0].embedding[0] == pytest.approx(0.1)
    assert seed.load_embeddings_cache(fresh[2:], str(cache)) == 1


def test_sharded_cache_rejects_corruption_and_changed_text(tmp_path):
    import json
    seed = _seed()
    cache = tmp_path / 'manifest.json'
    seed.write_sharded_embeddings_cache(_embedded(seed, 2), str(cache))
    fresh = seed.load_catalog()[:2]
    fresh[0].description += ' Changed.'
    with pytest.raises(SystemExit, match='text changed'):
        seed.load_embeddings_cache(fresh, str(cache))
    shard = tmp_path / json.loads(cache.read_text())['shards'][0]['file']
    shard.write_bytes(shard.read_bytes()[:-3])
    with pytest.raises(SystemExit, match='checksum mismatch'):
        seed.load_embeddings_cache(seed.load_catalog()[:2], str(cache))


@pytest.mark.parametrize('bad_value', [float('nan'), float('inf')])
def test_sharded_cache_refuses_nonfinite_vectors_without_replacing_manifest(tmp_path, bad_value):
    seed = _seed()
    cache = tmp_path / 'manifest.json'
    products = _embedded(seed, 2)
    seed.write_sharded_embeddings_cache(products, str(cache))
    before = cache.read_bytes()
    products[1].embedding[3] = bad_value
    with pytest.raises(ValueError, match='Invalid embeddings'):
        seed.write_sharded_embeddings_cache(products, str(cache))
    assert cache.read_bytes() == before


def test_no_photo_has_no_fabricated_path():
    seed = _seed()
    p = seed.load_catalog()[0]
    p.imgPath = None
    assert p.public_image_path is None
    assert p.to_csv_row()['imgurl'] == ''


def test_unknown_material_is_rejected(tmp_path):
    import json

    seed = _seed()
    rows = json.loads(Path(seed.CATALOG_JSON).read_text())[:1]
    rows[0]["materials"] = ["plastic"]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(rows))
    with pytest.raises(SystemExit, match=r"unknown materials \['plastic'\]"):
        seed.load_catalog(str(path))


def test_embedding_requests_are_bounded_and_preserve_product_order(monkeypatch):
    import io
    import json
    from types import SimpleNamespace
    import boto3

    seed = _seed()
    products = seed.load_catalog()[:194]
    requests = []

    def invoke_model(**kwargs):
        payload = json.loads(kwargs['body'])
        start = sum(len(request['texts']) for request in requests)
        requests.append(payload)
        vectors = [[(start + i + 1) / 256] * seed.EMBED_DIM
                   for i in range(len(payload['texts']))]
        return {'body': io.BytesIO(json.dumps({'embeddings': {'float': vectors}}).encode())}

    monkeypatch.setattr(boto3, 'client', lambda *a, **kw: SimpleNamespace(invoke_model=invoke_model))
    seed.generate_embeddings(products, 'us-east-1')
    assert [len(request['texts']) for request in requests] == [96, 96, 2]
    assert [text for request in requests for text in request['texts']] == [p.search_text for p in products]
    assert all(request['input_type'] == 'search_document' for request in requests)
    assert [p.embedding[0] for p in products] == [(i + 1) / 256 for i in range(194)]


def test_incomplete_live_embedding_batch_fails_before_assigning_vectors(monkeypatch):
    import io
    import json
    from types import SimpleNamespace
    import boto3

    seed = _seed()
    products = seed.load_catalog()[:2]
    client = SimpleNamespace(invoke_model=lambda **kw: {
        'body': io.BytesIO(json.dumps({'embeddings': {'float': [[0.1] * seed.EMBED_DIM]}}).encode())})
    monkeypatch.setattr(boto3, 'client', lambda *a, **kw: client)
    with pytest.raises(ValueError, match='Invalid embedding response'):
        seed.generate_embeddings(products, 'us-east-1')
    assert all(p.embedding is None for p in products)
