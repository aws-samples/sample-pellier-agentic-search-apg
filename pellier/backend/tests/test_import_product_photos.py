"""Photo intake respects explicit ownership and does not invent missing images."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def importer(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "photo_import", REPO / "scripts/import_product_photos.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_dimensions", lambda path: (1122, 1402))
    return module


def _catalog():
    return json.loads((REPO / "data/pellier_catalog.json").read_text())


def test_partial_delivery_maps_both_sizes_and_skips_rows_without_photos(importer, tmp_path):
    catalog = _catalog()
    (tmp_path / catalog[100]["image"]).touch()
    mappings = importer.plan(catalog, tmp_path, only_supplied=True)
    assert [m.product_id for m in mappings] == [101, 102]
    assert len({m.master for m in mappings}) == 1
    assert catalog[1000]["image"] is None


def test_full_delivery_rejects_missing_masters_before_encoding(importer, tmp_path):
    catalog = _catalog()
    (tmp_path / catalog[100]["image"]).touch()
    with pytest.raises(SystemExit, match="no master"):
        importer.plan(catalog, tmp_path)


@pytest.mark.parametrize("change", ["wrong_owner", "wrong_color", "wrong_design", "traversal"])
def test_delivery_rejects_misassigned_photos(importer, tmp_path, change):
    catalog = _catalog()
    (tmp_path / catalog[100]["image"]).touch()
    if change == "wrong_owner":
        catalog[102]["image"] = catalog[100]["image"]
    elif change == "wrong_color":
        catalog[101]["color"] = "Navy"
    elif change == "wrong_design":
        catalog[101]["name"] = "Unrelated item, Sage, L"
    else:
        catalog[101]["image"] = "../outside.png"
    with pytest.raises(SystemExit, match="mapping failed"):
        importer.plan(catalog, tmp_path, only_supplied=True)


def test_partial_delivery_still_rejects_unknown_masters(importer, tmp_path):
    (tmp_path / "unmapped.png").touch()
    with pytest.raises(SystemExit, match="maps to no product"):
        importer.plan(_catalog(), tmp_path, only_supplied=True)


def test_shared_master_is_encoded_once_per_format_and_width(importer, tmp_path, monkeypatch):
    catalog = _catalog()
    (tmp_path / catalog[100]["image"]).touch()
    mappings = importer.plan(catalog, tmp_path, only_supplied=True)
    calls = []
    monkeypatch.setattr(importer, "_encode", lambda *args, **kwargs: calls.append(args))
    assert importer.derive_all(mappings) == 6
    assert len(calls) == len(set(calls)) == 6
