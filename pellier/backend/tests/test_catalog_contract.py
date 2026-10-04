"""The catalog matches the approved table. These expectations are written out here on
purpose: they must never be regenerated from data/pellier_catalog.json."""
import importlib.util
import re
import sys
from pathlib import Path

from services.structured_extract import KNOWN_MATERIALS, KNOWN_TAGS
from tests.test_voice_banned_words import BANNED_WORDS

REPO = Path(__file__).resolve().parents[3]

# id: (name, department, moment, brand, price, quantity)
EXPECTED_CATALOG = {
    1: ('Tall Stoneware Vase', 'Home', 'fresh', 'Pellier', 42.0, 24),
    2: ('Hadley Linen Shirt', 'Clothing', 'fresh', 'Hadley', 78.0, 20),
    3: ('Leather Weekender', 'Bags and travel', 'fresh', 'Pellier', 249.0, 24),
    4: ('Santal & Fig Candle', 'Home', 'fresh', 'Pellier', 38.0, 24),
    5: ('Rectangular Leather Watch', 'Accessories', 'fresh', 'Pellier', 149.0, 24),
    6: ('Neroli Oil', 'Bath and body', 'fresh', 'Pellier', 26.0, 24),
    7: ('Jute Placemats, Set of 4', 'Kitchen and table', 'fresh', 'Pellier', 68.0, 24),
    8: ('Linen Lounge Set', 'Clothing', 'fresh', 'Pellier', 128.0, 24),
    9: ('Everyday Runner', 'Shoes', 'fresh', 'ZenMove', 110.0, 24),
    10: ('Washed Canvas Tote', 'Bags and travel', 'fresh', 'Pellier', 34.0, 24),
    11: ('Italian Linen Camp Shirt', 'Clothing', 'marco', 'Pellier', 68.0, 24),
    12: ('Canvas Dopp Kit', 'Bags and travel', 'marco', 'Pellier', 36.0, 8),
    13: ('Leather Card Wallet', 'Accessories', 'marco', 'Pellier', 42.0, 24),
    14: ('Linen Drawstring Trousers', 'Clothing', 'marco', 'Pellier', 78.0, 5),
    15: ('Espadrille Slides', 'Shoes', 'marco', 'Pellier', 52.0, 24),
    16: ('Linen Overshirt', 'Clothing', 'marco', 'Pellier', 88.0, 24),
    17: ('Leather Weekend Holdall', 'Bags and travel', 'marco', 'Pellier', 219.0, 24),
    18: ('Cotton-Linen Crew Tee', 'Clothing', 'marco', 'Pellier', 26.0, 24),
    19: ('Straw Panama Hat', 'Accessories', 'marco', 'Pellier', 54.0, 24),
    20: ('Merino Travel Socks', 'Clothing', 'marco', 'Pellier', 16.0, 6),
    21: ('Beeswax Taper Candles', 'Home', 'anna', 'Pellier', 18.0, 24),
    22: ('Linen Napkins, Set of 4', 'Kitchen and table', 'anna', 'Pellier', 44.0, 24),
    23: ('Ceramic Ring Dish', 'Home', 'anna', 'Pellier', 14.0, 24),
    24: ('Botanical Print Scarf', 'Accessories', 'anna', 'Pellier', 48.0, 24),
    25: ('Reed Diffuser', 'Home', 'anna', 'Pellier', 36.0, 24),
    26: ('Handmade Soap Set', 'Bath and body', 'anna', 'Pellier', 32.0, 24),
    27: ('Ceramic Bud Vase', 'Home', 'anna', 'Pellier', 22.0, 24),
    28: ('Leather Journal', 'Stationery and gifts', 'anna', 'Pellier', 42.0, 24),
    29: ('Brass Photo Frame', 'Home', 'anna', 'Pellier', 38.0, 24),
    30: ('Gift Wrapping Kit', 'Stationery and gifts', 'anna', 'Pellier', 12.0, 24),
    31: ('Stoneware Pour-Over Set', 'Kitchen and table', 'theo', 'Pellier', 58.0, 24),
    32: ('Raw Linen Throw', 'Home', 'theo', 'EcoThread', 118.0, 24),
    33: ('Olive Wood Cutting Board', 'Kitchen and table', 'theo', 'Pellier', 42.0, 24),
    34: ('Terracotta Planter', 'Home', 'theo', 'Pellier', 22.0, 24),
    35: ('Brass Incense Holder', 'Home', 'theo', 'Pellier', 16.0, 24),
    36: ('Ceramic Tumblers', 'Kitchen and table', 'theo', 'Pellier', 34.0, 24),
    37: ('Wabi-Sabi Bowl', 'Kitchen and table', 'theo', 'Pellier', 24.0, 24),
    38: ('Beeswax Pillar Candle', 'Home', 'theo', 'Pellier', 22.0, 24),
    39: ('Linen Table Runner', 'Kitchen and table', 'theo', 'EcoThread', 42.0, 24),
    40: ('Charcoal Soap Bar', 'Bath and body', 'theo', 'Pellier', 9.0, 24),
    41: ('Coral Lacquer Catchall', 'Home', 'house', 'Pellier', 48.0, 24),
    42: ('Waffle Bath Robe, Sage', 'Bath and body', 'house', 'NestWell', 64.0, 24),
    43: ('Quilted Silk Vest', 'Clothing', 'house', 'Pellier', 129.0, 0),
    44: ('Travertine Wall Clock', 'Home', 'house', 'Pellier', 72.0, 24),
    45: ('Tailored Wool Blazer', 'Clothing', 'house', 'Pellier', 239.0, 24),
    46: ('Ivory Cashmere Throw', 'Home', 'house', 'Pellier', 229.0, 24),
    47: ('Vetiver Eau de Parfum', 'Bath and body', 'house', 'Pellier', 110.0, 24),
    48: ('Leather Market Tote', 'Bags and travel', 'house', 'Pellier', 189.0, 24),
    49: ('Stonewashed Linen Set', 'Home', 'house', 'EcoThread', 219.0, 24),
    50: ('Oat Merino Crew', 'Clothing', 'house', 'ZenMove', 108.0, 24),
    51: ('Camel Wool Overcoat', 'Clothing', 'signature', 'Pellier', 329.0, 24),
    52: ('Silk Slip Dress', 'Clothing', 'signature', 'Pellier', 169.0, 24),
    53: ('Double-Pleat Wool Trouser', 'Clothing', 'signature', 'Pellier', 139.0, 24),
    54: ('Suede Chelsea Boot', 'Shoes', 'signature', 'Pellier', 259.0, 24),
    55: ('Fig and Cedar Eau de Parfum', 'Bath and body', 'signature', 'Pellier', 128.0, 24),
    56: ('Rose Absolute Body Oil', 'Bath and body', 'signature', 'Pellier', 64.0, 24),
    57: ('Cashmere Travel Wrap', 'Accessories', 'signature', 'Pellier', 189.0, 24),
    58: ('Signet Ring, Brushed Gold', 'Accessories', 'signature', 'Pellier', 149.0, 24),
    59: ('Wool Rug', 'Home', 'signature', 'Pellier', 429.0, 24),
    60: ('Blown Glass Decanter', 'Kitchen and table', 'signature', 'Pellier', 118.0, 24),
    61: ('Field Watch, Canvas Strap', 'Accessories', 'fresh', 'Pellier', 179.0, 24),
    62: ('Leather Watch Roll', 'Accessories', 'anna', 'Pellier', 48.0, 24),
    63: ('Wool Beanie', 'Accessories', 'fresh', 'Pellier', 24.0, 24),
    64: ('Sunglasses', 'Accessories', 'marco', 'Pellier', 68.0, 24),
    65: ('Stoneware Mugs, Set of 2', 'Kitchen and table', 'theo', 'Pellier', 38.0, 24),
    66: ('Glass Carafe', 'Kitchen and table', 'theo', 'Pellier', 34.0, 24),
    67: ('Salt Cellar with Spoon', 'Kitchen and table', 'theo', 'Pellier', 18.0, 24),
    68: ('Enamel Dutch Oven', 'Kitchen and table', 'theo', 'Pellier', 139.0, 24),
    69: ('8-Quart Stock Pot', 'Kitchen and table', 'fresh', 'Pellier', 64.0, 24),
    70: ('100% Linen Apron', 'Kitchen and table', 'fresh', 'EcoThread', 44.0, 24),
    71: ('Wooden Salad Servers', 'Kitchen and table', 'theo', 'Pellier', 22.0, 24),
    72: ('Espresso Cups, Set of 4', 'Kitchen and table', 'theo', 'Pellier', 44.0, 24),
    73: ('Dot-Grid Notebook Set', 'Stationery and gifts', 'anna', 'Pellier', 18.0, 24),
    74: ('Brass Pen', 'Stationery and gifts', 'anna', 'Pellier', 52.0, 24),
    75: ('Leather Desk Tray', 'Stationery and gifts', 'anna', 'Pellier', 58.0, 24),
    76: ('Greeting Card Set', 'Stationery and gifts', 'anna', 'Pellier', 14.0, 24),
    77: ('Recycled Wrapping Paper', 'Stationery and gifts', 'anna', 'Pellier', 9.0, 24),
    78: ('Linen Photo Album', 'Stationery and gifts', 'anna', 'Pellier', 56.0, 24),
    79: ('Housewarming Gift Box', 'Stationery and gifts', 'anna', 'Pellier', 68.0, 0),
    80: ('Sunday Morning Candle', 'Home', 'anna', 'Pellier', 28.0, 24),
    81: ('Ceramic Table Lamp', 'Home', 'house', 'Pellier', 148.0, 24),
    82: ('Linen Cushion Covers, Set of 2', 'Home', 'house', 'EcoThread', 52.0, 24),
    83: ('Woven Storage Baskets', 'Home', 'fresh', 'Pellier', 44.0, 24),
    84: ('Wool Throw', 'Home', 'house', 'Pellier', 149.0, 24),
    85: ('Chore Jacket', 'Clothing', 'fresh', 'Pellier', 138.0, 24),
    86: ('Crewneck Sweatshirt', 'Clothing', 'fresh', 'ZenMove', 58.0, 24),
    87: ('Cotton Cardigan', 'Clothing', 'fresh', 'Pellier', 88.0, 24),
    88: ('Everyday Chinos', 'Clothing', 'fresh', 'Pellier', 78.0, 24),
    89: ('Packable Rain Jacket', 'Clothing', 'marco', 'Pellier', 128.0, 24),
    90: ('Morning Run Shorts', 'Clothing', 'fresh', 'ZenMove', 34.0, 24),
    91: ('Canvas Sneakers', 'Shoes', 'fresh', 'Pellier', 64.0, 24),
    92: ('Suede Loafers', 'Shoes', 'fresh', 'Pellier', 148.0, 24),
    93: ('Rain Boots', 'Shoes', 'fresh', 'Pellier', 104.0, 24),
    94: ('Packing Cubes, Set of 3', 'Bags and travel', 'marco', 'Pellier', 34.0, 24),
    95: ('Canvas Crossbody Bag', 'Bags and travel', 'marco', 'Pellier', 54.0, 24),
    96: ('Everyday Backpack', 'Bags and travel', 'marco', 'Pellier', 118.0, 24),
    97: ('Travel Bottles, Set of 4', 'Bags and travel', 'marco', 'Pellier', 16.0, 24),
    98: ('Passport Wallet', 'Bags and travel', 'marco', 'Pellier', 36.0, 24),
    99: ('Cotton Bath Towel Set', 'Bath and body', 'house', 'NestWell', 68.0, 24),
    100: ('Waffle Bath Mat', 'Bath and body', 'house', 'NestWell', 28.0, 24),
}
RENAMED = {
    1: ('Tall Stoneware Vase', 'Tall Stoneware Vase'),
    3: ('Leather Weekender', 'Leather Weekender'),
    5: ('Rectangular Leather Watch', 'Rectangular Leather Watch'),
    6: ('Neroli Oil', 'Neroli Oil'),
    7: ('Jute Placemats, Set of 4', 'Jute Placemats, Set of 4'),
    8: ('Linen Lounge Set', 'Linen Lounge Set'),
    9: ('Everyday Runner', 'Everyday Runner'),
    22: ('Monogrammed Linen Napkins', 'Linen Napkins, Set of 4'),
    42: ('Waffle Bath Robe, Sage', 'Waffle Bath Robe, Sage'),
    47: ('Vetiver Eau de Parfum', 'Vetiver Eau de Parfum'),
    48: ('Leather Market Tote', 'Leather Market Tote'),
    52: ('Silk Slip Dress', 'Silk Slip Dress'),
    59: ('Wool Rug', 'Wool Rug'),
}
# id: every material the product contains, components and blends included. Exclusions
# check this list, so it must be complete for the materials the store vocabulary knows.
EXPECTED_MATERIALS = {
    1: ('ceramic',),
    2: ('linen',),
    3: ('brass', 'canvas', 'leather'),
    4: ('glass', 'soy wax'),
    5: ('leather', 'steel'),
    6: ('glass',),
    7: ('jute',),
    8: ('linen',),
    9: ('foam',),
    10: ('canvas', 'leather'),
    11: ('linen',),
    12: ('brass', 'canvas'),
    13: ('leather',),
    14: ('linen',),
    15: ('jute', 'leather'),
    16: ('cotton', 'linen'),
    17: ('brass', 'canvas', 'leather'),
    18: ('cotton', 'linen'),
    19: ('straw',),
    20: ('merino', 'wool'),
    21: ('beeswax', 'cotton'),
    22: ('linen',),
    23: ('ceramic',),
    24: ('silk',),
    25: ('glass', 'rattan'),
    26: ('wood',),
    27: ('ceramic',),
    28: ('leather', 'paper'),
    29: ('brass',),
    30: ('cotton', 'paper'),
    31: ('ceramic',),
    32: ('linen',),
    33: ('wood',),
    34: ('ceramic',),
    35: ('brass',),
    36: ('ceramic',),
    37: ('ceramic',),
    38: ('beeswax',),
    39: ('linen',),
    40: (),
    41: ('ceramic',),
    42: ('cotton',),
    43: ('silk',),
    44: ('brass', 'stone'),
    45: ('wool',),
    46: ('cashmere', 'wool'),
    47: ('glass',),
    48: ('leather',),
    49: ('linen',),
    50: ('merino', 'wool'),
    51: ('wool',),
    52: ('silk',),
    53: ('wool',),
    54: ('leather',),
    55: ('glass',),
    56: ('glass',),
    57: ('cashmere', 'linen', 'wool'),
    58: ('gold', 'silver'),
    59: ('wool',),
    60: ('glass',),
    61: ('canvas', 'steel'),
    62: ('leather',),
    63: ('wool',),
    64: ('acetate', 'glass'),
    65: ('ceramic',),
    66: ('glass',),
    67: ('ceramic', 'wood'),
    68: ('iron',),
    69: ('glass', 'steel'),
    70: ('linen',),
    71: ('wood',),
    72: ('ceramic',),
    73: ('paper',),
    74: ('brass',),
    75: ('leather',),
    76: ('paper',),
    77: ('paper',),
    78: ('linen', 'paper'),
    79: ('ceramic', 'linen', 'paper', 'wood'),
    80: ('glass', 'soy wax'),
    81: ('ceramic', 'linen'),
    82: ('linen',),
    83: ('seagrass',),
    84: ('wool',),
    85: ('canvas', 'cotton'),
    86: ('cotton',),
    87: ('cotton', 'wood'),
    88: ('cotton',),
    89: ('nylon',),
    90: ('polyester',),
    91: ('canvas', 'cotton', 'rubber'),
    92: ('leather',),
    93: ('rubber',),
    94: ('nylon',),
    95: ('canvas', 'leather'),
    96: ('canvas', 'leather'),
    97: ('silicone',),
    98: ('leather',),
    99: ('cotton',),
    100: ('cotton',),
}
SEMANTIC_CANDIDATES = {31, 33, 36, 65, 66, 67}
HOUSEWARMING = {79, 83, 84}
WATCHES = {5, 61}
CANDLES = {4, 21, 38, 80}


def _catalog():
    spec = importlib.util.spec_from_file_location("seed_catalog", REPO / "scripts" / "seed_pellier_catalog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_catalog"] = module
    spec.loader.exec_module(module)
    return {p.productId: p for p in module.load_catalog()}


def _matches(query: str, name: str) -> bool:
    """store_tools.check_stock's rule: every word appears in the name."""
    return all(token in name.lower() for token in query.lower().split())


def test_catalog_is_exactly_the_approved_table():
    catalog = _catalog()
    assert set(catalog) == set(EXPECTED_CATALOG)
    for pid, (name, department, moment, brand, price, quantity) in EXPECTED_CATALOG.items():
        p = catalog[pid]
        assert (p.name, p.department, p.persona, p.brand, p.price, p.quantity) == \
            (name, department, moment, brand, price, quantity), pid


def test_prices_fit_the_approved_spread():
    prices = sorted(p.price for p in _catalog().values())
    assert max(prices) <= 450
    assert (prices[49] + prices[50]) / 2 == 55
    assert sum(price <= 100 for price in prices) == 69


def test_tags_come_from_the_planner_vocabulary():
    for p in _catalog().values():
        assert 2 <= len(p.tags) <= 5, p.productId
        assert set(p.tags) <= set(KNOWN_TAGS), (p.productId, set(p.tags) - set(KNOWN_TAGS))


def test_watch_and_candle_tags_are_exact():
    catalog = _catalog()
    assert {pid for pid, p in catalog.items() if "watch" in p.tags} == WATCHES
    assert {pid for pid, p in catalog.items() if "candle" in p.tags} == CANDLES
    assert all("Candle" in catalog[pid].name for pid in CANDLES)
    assert all(catalog[pid].price > 100 for pid in WATCHES)
    assert "watch" not in catalog[62].tags and {"leather", "gift"} <= set(catalog[62].tags)


def test_housewarming_appears_only_in_its_three_fixtures():
    catalog = _catalog()
    found = {pid for pid, p in catalog.items()
             if "housewarming" in f"{p.name} {p.description}".lower()}
    assert found == HOUSEWARMING
    assert catalog[83].price <= 100 and catalog[83].quantity > 0
    assert catalog[84].price > 100
    assert catalog[79].quantity == 0


def test_semantic_candidates_never_say_gift():
    catalog = _catalog()
    for pid in SEMANTIC_CANDIDATES:
        p = catalog[pid]
        text = f"{p.name} {p.description}".lower()
        assert "gift" not in text and "housewarming" not in text and "gift" not in p.tags, pid


def test_marco_test_inputs_classify_as_designed():
    names = {pid: p.name for pid, p in _catalog().items()}
    assert {pid for pid, n in names.items() if _matches("Linen shirt", n)} == {2, 11, 16}
    assert {pid for pid, n in names.items() if _matches("Hadley", n)} == {2}
    assert {pid for pid, n in names.items() if _matches("Hadley cashmere scarf", n)} == set()
    assert {pid for pid, n in names.items() if _matches("Quilted Silk Vest", n)} == {43}


def test_lab_quoted_names_never_change():
    catalog = _catalog()
    assert catalog[2].name == "Hadley Linen Shirt"
    assert catalog[37].name == "Wabi-Sabi Bowl"
    assert catalog[41].name == "Coral Lacquer Catchall"
    assert catalog[43].name == "Quilted Silk Vest"
    assert "Sage" in catalog[42].name


def test_copy_uses_the_store_voice():
    for p in _catalog().values():
        text = f"{p.name} {p.description}".lower()
        for word in BANNED_WORDS:
            assert word not in text, (p.productId, word)
        assert "\u00b7" not in text  # middle dot
        assert 12 <= len(p.description.split()) <= 45, p.productId


def test_images_keep_their_filenames_or_use_the_placeholder():
    catalog = _catalog()
    for pid, p in catalog.items():
        if pid <= 60:
            assert p.imgPath != "placeholder-product.png", pid
        else:
            assert p.imgPath == "placeholder-product.png", pid


def test_renamed_products_list_matches_the_table():
    catalog = _catalog()
    assert {pid: catalog[pid].name for pid in RENAMED} == {pid: new for pid, (old, new) in RENAMED.items()}


def test_nothing_in_source_mentions_archive_rows():
    import subprocess

    pattern = (
        r"tags \? 'archive'|distractor|DISTRACTOR"
        r"|archive (row|rows|product|products|status|distractor|distractors|variant|variants)"
    )
    hits = subprocess.run(
        ["git", "grep", "-n", "-I", "-i", "-E", pattern,
         "--", "pellier", "scripts", "README.md", "VOICE.md", "data", "solutions", "docs",
         ":!*node_modules*", ":!docs/release-readiness",
         ":!pellier/backend/tests/test_catalog_contract.py"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    assert hits == "", hits


def test_materials_are_exactly_the_approved_composition():
    catalog = _catalog()
    assert {pid: tuple(sorted(p.materials)) for pid, p in catalog.items()} == EXPECTED_MATERIALS


def test_materials_come_from_the_material_vocabulary():
    for p in _catalog().values():
        assert set(p.materials) <= set(KNOWN_MATERIALS), (p.productId, p.materials)


def test_merino_and_cashmere_also_count_as_wool():
    for p in _catalog().values():
        if {"merino", "cashmere"} & set(p.materials):
            assert "wool" in p.materials, p.productId


# Words in the copy that name a material, and the material each one requires.
MATERIAL_WORDS = {
    r"\bleather\b|\bsuede\b": "leather", r"\blinen\b": "linen", r"\bwool\b|\bmerino\b": "wool",
    r"\bcashmere\b": "cashmere", r"\bsilk\b": "silk", r"\bcotton\b": "cotton",
    r"\bcanvas\b": "canvas", r"\bjute\b": "jute", r"\bbrass\b": "brass",
    r"\bglass\b": "glass", r"\bstoneware\b|\bceramic\b|\bterracotta\b": "ceramic",
    r"\bbeeswax\b": "beeswax", r"\bsoy\b": "soy wax", r"\bwood(en)?\b|\bwalnut\b": "wood",
    r"\bsteel\b": "steel", r"\bsilver\b": "silver", r"\brubber\b": "rubber",
    r"\bnylon\b": "nylon", r"\bpaper\b|\bkraft\b": "paper",
}
# Mentions that are not part of the product: the table it sits on, or a color name.
NOT_THE_PRODUCT = {(7, "wood"), (24, "ceramic"), (77, "ceramic")}


def test_every_material_named_in_the_copy_is_listed():
    missing = []
    for pid, p in _catalog().items():
        text = f"{p.name} {p.description}".lower()
        for pattern, material in MATERIAL_WORDS.items():
            if re.search(pattern, text) and material not in p.materials:
                if (pid, material) not in NOT_THE_PRODUCT:
                    missing.append((pid, material))
    assert missing == []


def test_review_examples_list_their_components():
    catalog = _catalog()
    for pid in (10, 15, 95, 96):
        assert "leather" in catalog[pid].materials and "leather" not in catalog[pid].tags, pid
    assert {"linen", "ceramic", "wood"} <= set(catalog[79].materials)


UNVERIFIED_PROMISES = (
    "cold-pressed", "upf", "rolls without creasing", "lasts through", "softening chemicals",
    "absorbs without residue", "monogram", "ykk",
)


def test_copy_makes_no_unverified_promises():
    for p in _catalog().values():
        text = f"{p.name} {p.description}".lower()
        for phrase in UNVERIFIED_PROMISES:
            assert phrase not in text, (p.productId, phrase)
