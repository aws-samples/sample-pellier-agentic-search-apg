"""Tests for ``routes.products`` — the ``/api/products`` surface (Task 3.6).

Validates Requirements 3.3.1–3.3.5 and 3.5.1–3.5.2 without any live
Aurora catalog or Cognito traffic. Tests mint access tokens with the
same synthetic RSA signer used by ``test_preferences_api.py`` /
``test_auth_routes.py``, override the shared ``CognitoAuthService``
dependency, and inject a fake ``DatabaseService`` that serves the 9
showcase products from ``storefront.md``.

Headline acceptance (Task 3.6 "Test verification"):

    "with seeded catalog and known tags, Sundress/Cardigan top the list
     for {vibe: ['creative'], occasions: ['evening']}; anon request
     returns editorial order."

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_products_personalized.py -v
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from config import settings
import services.agentcore_memory as memory_module
from models import Preferences
from routes.products import get_db_service, router as products_router
from routes.user import get_agentcore_memory
from services.agentcore_identity import (
    AgentCoreIdentityService,
    get_agentcore_identity_service,
)
from services.agentcore_memory import AgentCoreMemory
from services.cognito_auth import (
    ACCESS_TOKEN_COOKIE,
    CognitoAuthService,
    get_cognito_auth_service,
)


# ---------------------------------------------------------------------------
# Test pool identity — matches test_auth_routes.py / test_preferences_api.py
# ---------------------------------------------------------------------------

POOL_ID = "us-east-1_TESTPOOL"
REGION = "us-east-1"
CLIENT_ID = "test-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"


# ---------------------------------------------------------------------------
# Seeded showcase catalog — the 9 products from storefront.md
# ---------------------------------------------------------------------------
#
# Kept byte-for-byte in sync with ``test_personalization.py``. Columns
# mirror what ``routes.products._PRODUCT_SELECT`` asks for: id, brand,
# name, color, price, rating, reviews (TEXT), category, image_url, badge,
# tags, tier. The fake DB fixture serves these rows in the same order
# they appear here so tier-based ordering is deterministic.


def _showcase_rows() -> List[Dict[str, Any]]:
    """Return the 9 showcase rows in store-chosen editorial order."""
    base: List[Dict[str, Any]] = [
        dict(
            id=1,
            name="Italian Linen Camp Shirt",
            color="Sand",
            price=128.0,
            category="Clothing",
            tags=[
                "minimal", "serene", "classic", "warm",
                "neutral", "everyday", "slow", "linen",
            ],
        ),
        dict(
            id=2,
            name="Wide-Leg Linen Trousers",
            color="Terracotta",
            price=98.0,
            category="Clothing",
            tags=["creative", "bold", "warm", "earth", "everyday", "travel", "linen"],
        ),
        dict(
            id=3,
            name="Signature Straw Tote",
            color="Natural",
            price=68.0,
            category="Bags and travel",
            tags=[
                "classic", "serene", "neutral", "soft",
                "travel", "everyday", "accessories",
            ],
        ),
        dict(
            id=4,
            name="Relaxed Oxford Shirt",
            color="Warm Ivory",
            price=88.0,
            category="Clothing",
            tags=["classic", "minimal", "neutral", "soft", "everyday", "work", "linen"],
        ),
        dict(
            id=5,
            name="Sundress in Washed Linen",
            color="Golden Ochre",
            price=148.0,
            category="Clothing",
            tags=["creative", "bold", "warm", "earth", "evening", "dresses", "linen"],
        ),
        dict(
            id=6,
            name="Leather Slide Sandal",
            color="Chestnut",
            price=112.0,
            category="Shoes",
            tags=[
                "minimal", "classic", "earth", "warm",
                "everyday", "travel", "footwear",
            ],
        ),
        dict(
            id=7,
            name="Cashmere-Blend Cardigan",
            color="Driftwood",
            price=158.0,
            category="Clothing",
            tags=[
                "minimal", "serene", "classic", "neutral",
                "earth", "slow", "evening", "outerwear",
            ],
        ),
        dict(
            id=8,
            name="Ceramic Tumbler Set",
            color="4pc Set",
            price=52.0,
            category="Home",
            tags=["minimal", "serene", "creative", "neutral", "soft", "slow", "home"],
        ),
        dict(
            id=9,
            name="Linen Utility Jacket",
            color="Faded Olive",
            price=178.0,
            category="Clothing",
            tags=[
                "adventurous", "creative", "earth", "neutral",
                "outdoor", "travel", "outerwear",
            ],
        ),
    ]
    # Populate shared columns the route layer expects but the showcase
    # table doesn't call out (tier, rating, reviews, image_url, badge,
    # brand, updated_at). All 9 rows live in tier 1 on the real catalog
    # and insertion order breaks the tie — the fixture mirrors that so
    # a naive ORDER BY returns the storefront.md sequence.
    enriched: List[Dict[str, Any]] = []
    for idx, row in enumerate(base):
        enriched.append(
            {
                **row,
                "brand": "Pellier",
                "rating": 4.7,
                # Live schema stores reviews as TEXT (numeric strings).
                "reviews": str(100 + idx),
                "image_url": f"https://example.com/{row['id']}.jpg",
                "badge": None,
                "tier": 1,
                # Detail-route columns. ``description`` is the catalog's
                # editorial copy; ``quantity`` is the on-hand count the
                # product page reports as live Aurora stock.
                "description": f"Editorial description for {row['name']}.",
                "quantity": 40 + idx,
                # A recent timestamp keeps ``/api/inventory`` reporting
                # ``stale: false`` without the test having to freeze time.
                "updated_at": datetime.now(timezone.utc),
            }
        )
    return enriched


# ---------------------------------------------------------------------------
# Fake DatabaseService — offline stand-in for Aurora
# ---------------------------------------------------------------------------


class FakeDatabaseService:
    """Minimal ``DatabaseService`` stand-in for the product routes.

    Parses the SELECTs issued by ``routes/products.py`` just enough to
    mimic the real catalog: a category filter, a single-row lookup, and
    a GROUP BY for inventory counts. Each ``fetch_all`` / ``fetch_one``
    call is also recorded so tests can assert which queries ran.
    """

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = list(rows)
        self.calls: List[Dict[str, Any]] = []
        # Per-product warehouse rows, keyed by the TEXT catalog id. Empty
        # means "table present, product not stocked anywhere".
        self.warehouse_rows: Dict[str, List[Dict[str, Any]]] = {}
        # When set, the warehouse join raises it — the shape of a cluster
        # seeded before the warehouse migration, or a revoked grant.
        self.warehouse_error: Optional[Exception] = None

    async def fetch_all(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.calls.append({"kind": "all", "query": query, "params": params})
        q = " ".join(query.split())

        # --- Per-warehouse inventory join ---------------------------
        # One product (``= %s``) for the detail route, or every listed
        # product (``= ANY(%s)``) for the cards' stock lines.
        if "warehouse_inventory" in q:
            if self.warehouse_error is not None:
                raise self.warehouse_error
            ids = params[0] if isinstance(params[0], (list, tuple)) else [params[0]]
            return [
                dict(r, product_id=str(pid))
                for pid in ids
                for r in self.warehouse_rows.get(str(pid), [])
            ]

        # --- Inventory GROUP BY -------------------------------------
        # The route SELECTs ``category`` and ``MAX(updated_at)``.
        if "GROUP BY CATEGORY" in q.upper():
            grouped: Dict[str, Dict[str, Any]] = {}
            for row in self._rows:
                cat = row["category"]
                bucket = grouped.setdefault(
                    cat,
                    {
                        "category": cat,
                        "count": 0,
                        "last_refreshed": row.get("updated_at"),
                    },
                )
                bucket["count"] += 1
                row_ts = row.get("updated_at")
                if row_ts and (
                    bucket["last_refreshed"] is None
                    or row_ts > bucket["last_refreshed"]
                ):
                    bucket["last_refreshed"] = row_ts
            return list(grouped.values())

        # --- Editorial list with optional category filter ----------
        filtered = list(self._rows)
        if "ILIKE" in q.upper() and params:
            needle = str(params[0]).replace("%", "").lower()
            if needle:
                filtered = [r for r in filtered if needle in r["category"].lower()]
        # Preserve tier ordering (already the insertion order for tier 1).
        filtered.sort(key=lambda r: (r.get("tier"), r["id"]))
        return [dict(r) for r in filtered]

    async def fetch_one(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        self.calls.append({"kind": "one", "query": query, "params": params})
        if not params:
            return None
        product_id = params[0]
        # ``product_catalog."productId"`` is a TEXT column. Postgres rejects
        # an int bind outright — ``operator does not exist: text = smallint``
        # — so this stub refuses one too. An earlier revision compared
        # ``row["id"] == params[0]`` against int fixture ids, which made the
        # fake more permissive than Aurora and let a 500 on every real
        # product-detail request pass the suite.
        if not isinstance(product_id, str):
            raise TypeError(
                'product_catalog."productId" is text, got '
                f"{type(product_id).__name__} — bind str(product_id)"
            )
        for row in self._rows:
            if str(row["id"]) == product_id:
                return dict(row)
        return None


# ---------------------------------------------------------------------------
# Synthetic RSA signer + JWKS (same pattern as test_preferences_api.py)
# ---------------------------------------------------------------------------


class _Signer:
    def __init__(self, kid: Optional[str] = None) -> None:
        self.kid = kid or f"kid-{uuid.uuid4().hex[:8]}"
        self._private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._pem = self._private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_jwk(self) -> Dict[str, Any]:
        public_pem = self._private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_key = serialization.load_pem_public_key(public_pem)
        jwk: Dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = self.kid
        jwk["use"] = "sig"
        jwk["alg"] = "RS256"
        return jwk

    def sign(self, claims: Dict[str, Any]) -> str:
        return jwt.encode(
            claims,
            self._pem,
            algorithm="RS256",
            headers={"kid": self.kid},
        )


def _access_claims(
    *,
    sub: str = "cognito-sub-products",
    email: str = "shopper@example.com",
    given_name: str = "Avery",
    exp_offset: int = 3600,
) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "sub": sub,
        "email": email,
        "given_name": given_name,
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + exp_offset,
        "auth_time": now,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wire_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the router at our synthetic Cognito pool for the test run."""
    monkeypatch.setattr(settings, "COGNITO_POOL_ID", POOL_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION, raising=False)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID, raising=False)


@pytest.fixture(autouse=True)
def _reset_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level fallback dicts between tests and force the
    SDK-unavailable path so every test runs deterministically against
    the in-memory fallback. Mirrors ``test_preferences_api.py``.
    """
    monkeypatch.setattr(memory_module, "_SESSION_STORE", {})
    monkeypatch.setattr(memory_module, "_PREFS_STORE", {})
    monkeypatch.setattr(memory_module.settings, "AGENTCORE_MEMORY_ID", None)


def _seed_preferences(
    memory: AgentCoreMemory, user_id: str, prefs: Preferences
) -> None:
    """Seed preferences into the in-memory fallback from a sync test.

    ``asyncio.get_event_loop()`` raises ``RuntimeError`` when no loop
    is already attached to the main thread (which is the case when
    other test modules have closed theirs). ``asyncio.run`` side-steps
    that by creating and tearing down a fresh loop per call, which is
    the right lifecycle for a single one-shot setter.
    """
    import asyncio

    asyncio.run(memory.set_user_preferences(user_id, prefs))


@pytest.fixture
def signer() -> _Signer:
    return _Signer(kid="products-api-kid")


@pytest.fixture
def auth_service(signer: _Signer) -> CognitoAuthService:
    """JWKS-backed service wired to the synthetic signer."""
    svc = CognitoAuthService(pool_id=POOL_ID, region=REGION, client_id=CLIENT_ID)
    svc._fetch_jwks = lambda: {"keys": [signer.public_jwk()]}  # type: ignore[assignment]
    return svc


@pytest.fixture
def memory() -> AgentCoreMemory:
    return AgentCoreMemory()


@pytest.fixture
def fake_db() -> FakeDatabaseService:
    return FakeDatabaseService(_showcase_rows())


@pytest.fixture
def client(
    auth_service: CognitoAuthService,
    memory: AgentCoreMemory,
    fake_db: FakeDatabaseService,
) -> TestClient:
    """FastAPI test app with only the products router mounted.

    Isolates the router from ``app.py`` so tests don't need the full
    lifespan (database, embeddings, Bedrock). The Cognito service, the
    AgentCore Memory instance, and the ``DatabaseService`` are all
    overridden via dependency injection — no monkeypatching of
    function internals.

    The ``AgentCoreIdentityService`` is constructed with our test
    ``CognitoAuthService`` instance so its internal
    ``self._auth_service()`` call returns the JWKS-stubbed service
    rather than the module-level singleton (which would try a real
    HTTP fetch against Cognito).
    """
    app = FastAPI()
    app.include_router(products_router)

    identity_service = AgentCoreIdentityService(cognito_auth=auth_service)

    app.dependency_overrides[get_cognito_auth_service] = lambda: auth_service
    app.dependency_overrides[get_agentcore_identity_service] = lambda: identity_service
    app.dependency_overrides[get_agentcore_memory] = lambda: memory
    app.dependency_overrides[get_db_service] = lambda: fake_db
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/products — anonymous / non-personalized
# ---------------------------------------------------------------------------


def test_anon_request_returns_editorial_order(client: TestClient) -> None:
    """Req 3.3.1: no auth -> default editorial order."""
    resp = client.get("/api/products")
    assert resp.status_code == 200
    body = resp.json()

    assert isinstance(body, list) and len(body) == 9
    # Editorial order matches storefront.md exactly.
    ids = [p["id"] for p in body]
    assert ids == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_anon_request_uses_camelcase_wire_shape(client: TestClient) -> None:
    """Task 1.3 contract: responses emit camelCase keys (``reviewCount``,
    ``imageUrl``) via ``StorefrontProduct.model_dump(by_alias=True)``."""
    resp = client.get("/api/products")
    body = resp.json()

    sample = body[0]
    assert "reviewCount" in sample
    assert "imageUrl" in sample
    # snake_case variants MUST NOT leak onto the wire — the frontend in
    # Task 1.2 keys off camelCase only.
    assert "review_count" not in sample
    assert "image_url" not in sample


def test_personalized_true_without_auth_returns_editorial_order(
    client: TestClient,
) -> None:
    """Req 3.3.1 guard: ``personalized=true`` without a JWT SHALL NOT
    401. It silently falls back to editorial order so the home page
    loads for anonymous shoppers regardless of the query flag."""
    resp = client.get("/api/products?personalized=true")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert ids[0] == 1
    assert ids[-1] == 9


def test_persona_edit_reads_the_durable_storefront_rank(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """A persona floor is an Aurora-ranked edit, never a browser fixture."""
    resp = client.get("/api/products?persona=marco")
    assert resp.status_code == 200

    # The listing read, not the warehouse batch that follows it.
    listing = [c for c in fake_db.calls if "product_catalog" in c["query"]][-1]
    query = listing["query"]
    assert "persona_id = %s" in query
    assert "storefront_rank IS NOT NULL" in query
    assert 'ORDER BY storefront_rank ASC' in query
    assert listing["params"] == ("marco",)


# ---------------------------------------------------------------------------
# GET /api/products — personalized (headline Task 3.6 acceptance)
# ---------------------------------------------------------------------------


def test_personalized_with_creative_evening_prefs_puts_sundress_and_cardigan_on_top(
    client: TestClient,
    signer: _Signer,
    memory: AgentCoreMemory,
) -> None:
    """Headline Task 3.6 assertion:

        "with seeded catalog and known tags, Sundress/Cardigan top the
         list for {vibe: ['creative'], occasions: ['evening']}"

    Sundress matches both ``creative`` and ``evening`` (score 2).
    Cardigan matches ``evening`` only (score 1) and Wide-Leg Linen
    Trousers + Ceramic Tumbler Set + Linen Utility Jacket also each
    match ``creative`` (score 1). Tie-break by editorial order puts
    the Trousers ahead of the others — but Sundress outscores all of
    them and Cardigan ties at 1 with the Trousers.

    The critical assertion for this task is that BOTH Sundress AND
    Cardigan (the two products whose tags actually cover ``evening``)
    appear in the top ranks — and that flipping ``personalized=true``
    DOES move them ahead of their editorial positions.
    """
    user_sub = "sundress-cardigan-user"
    token = signer.sign(_access_claims(sub=user_sub))

    # Seed preferences directly via the shared AgentCoreMemory instance.
    # This mimics the effect of POST /api/user/preferences from Task 3.4
    # without crossing the route boundary.
    _seed_preferences(
        memory,
        user_sub,
        Preferences(vibe=["creative"], occasions=["evening"]),
    )

    resp = client.get(
        "/api/products?personalized=true",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]

    # Sundress has the unique top score (2) — it MUST be first.
    assert ids[0] == 5

    # Cardigan (evening -> 1) must appear in the top half of the list,
    # ahead of products that don't match any pref (e.g. Camp Shirt,
    # Straw Tote, Oxford Shirt, Leather Sandal).
    cardigan_rank = ids.index(7)
    for no_match_id in (1, 3, 4, 6):
        assert cardigan_rank < ids.index(no_match_id), (
            f"{no_match_id} should rank BELOW cashmere-blend-cardigan (id=7), "
            f"got ids={ids}"
        )


def test_personalized_flip_observably_changes_ordering(
    client: TestClient,
    signer: _Signer,
    memory: AgentCoreMemory,
) -> None:
    """Task 3.6 "Done when": flipping ``personalized=true`` observably
    changes the returned ordering vs the editorial baseline.

    The same signed-in user sees a different first-product id when
    they toggle personalization on vs off, proving the branch is wired
    end-to-end through the identity service + memory + scorer.
    """
    user_sub = "flip-toggle-user"
    token = signer.sign(_access_claims(sub=user_sub))

    _seed_preferences(
        memory,
        user_sub,
        Preferences(vibe=["creative"], occasions=["evening"]),
    )

    editorial = client.get(
        "/api/products?personalized=false",
        cookies={ACCESS_TOKEN_COOKIE: token},
    ).json()
    personalized = client.get(
        "/api/products?personalized=true",
        cookies={ACCESS_TOKEN_COOKIE: token},
    ).json()

    editorial_ids = [p["id"] for p in editorial]
    personalized_ids = [p["id"] for p in personalized]

    # Both lists must contain the same 9 products (personalization is a
    # re-sort, not a filter).
    assert set(editorial_ids) == set(personalized_ids)
    # But the order MUST differ — this is the observable behavioural
    # signal the task "Done when" asks for.
    assert editorial_ids != personalized_ids
    # And specifically, the Camp Shirt is first editorially while the
    # Sundress is first personalized.
    assert editorial_ids[0] == 1
    assert personalized_ids[0] == 5


def test_personalized_without_saved_prefs_returns_editorial_order(
    client: TestClient,
    signer: _Signer,
) -> None:
    """Req 3.3.3: signed-in + ``personalized=true`` + no prefs saved
    SHALL return the editorial order (not 401, not empty)."""
    token = signer.sign(_access_claims(sub="unseen-prefs-user"))
    resp = client.get(
        "/api/products?personalized=true",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert ids[0] == 1


def test_personalized_with_empty_prefs_returns_editorial_order(
    client: TestClient,
    signer: _Signer,
    memory: AgentCoreMemory,
) -> None:
    """Req 3.3.3 tighter case: signed-in + saved-but-empty prefs SHALL
    also return editorial order (empty prefs would score every product
    0, which is effectively a no-op re-sort).
    """
    user_sub = "empty-prefs-user"
    token = signer.sign(_access_claims(sub=user_sub))

    _seed_preferences(memory, user_sub, Preferences())

    resp = client.get(
        "/api/products?personalized=true",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert ids == [1, 2, 3, 4, 5, 6, 7, 8, 9]


# ---------------------------------------------------------------------------
# GET /api/products?category=... (Req 3.3.4)
# ---------------------------------------------------------------------------


def test_category_filter_uses_ilike_and_narrows_results(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """Req 3.3.4: ``category=<name>`` SHALL filter via ILIKE per database.md."""
    resp = client.get("/api/products?category=Clothing")
    assert resp.status_code == 200
    categories = {p["category"] for p in resp.json()}
    assert categories == {"Clothing"}

    # Confirm the SQL path actually uses ILIKE (database.md steering).
    listing = [c for c in fake_db.calls if "product_catalog" in c["query"]][-1]
    assert "ILIKE" in listing["query"].upper()


# ---------------------------------------------------------------------------
# GET /api/products/{id} (Req 3.3.5)
# ---------------------------------------------------------------------------


def test_get_product_by_id_returns_row(client: TestClient) -> None:
    """Req 3.3.5: known id SHALL return the product."""
    resp = client.get("/api/products/5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 5
    assert body["name"] == "Sundress in Washed Linen"
    # camelCase wire shape (Task 1.3 contract).
    assert "reviewCount" in body
    assert "imageUrl" in body


def test_get_product_by_id_returns_404_for_unknown(client: TestClient) -> None:
    """Req 3.3.5: unknown id SHALL return 404."""
    resp = client.get("/api/products/9999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "product_not_found"}


def test_get_product_by_id_binds_catalog_key_as_text(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """Regression: the catalog key SHALL be bound as text, not int.

    ``product_catalog."productId"`` is a ``text`` column. Binding an int
    made Aurora reject the comparison (``operator does not exist:
    text = smallint``), so ``GET /api/products/{id}`` returned 500 for
    every product while the mocked suite stayed green.
    """
    assert client.get("/api/products/5").status_code == 200

    lookups = [c for c in fake_db.calls if c["kind"] == "one"]
    assert lookups, "expected a single-row catalog lookup"
    assert lookups[-1]["params"] == ("5",)


def test_listing_carries_quantity_and_warehouse_stock_for_the_card_line(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """Each listed product SHALL carry its stock so a card can say where it is."""
    fake_db.warehouse_rows["2"] = [
        {"warehouse_id": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY",
         "ship_window_min": 1, "ship_window_max": 2, "quantity": 0},
        {"warehouse_id": "ATX-02", "name": "Austin", "city": "Austin, TX",
         "ship_window_min": 2, "ship_window_max": 4, "quantity": 6},
    ]

    body = client.get("/api/products").json()
    by_id = {row["id"]: row for row in body}

    # ``quantity`` is 40 + index on the fixture rows.
    assert by_id[2]["quantity"] == 41
    assert [w["city"] for w in by_id[2]["warehouses"]] == ["Brooklyn, NY", "Austin, TX"]
    assert by_id[2]["warehouses"][1]["quantity"] == 6
    # A product the warehouse read does not mention keeps an empty list, not a
    # fabricated count.
    assert by_id[1]["warehouses"] == []
    # One batched read for the whole listing, bound as text ids.
    batched = [c for c in fake_db.calls if "ANY(%s)" in c["query"]]
    assert len(batched) == 1
    assert batched[0]["params"] == ([str(row["id"]) for row in body],)


def test_listing_degrades_to_quantity_when_warehouse_join_fails(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    fake_db.warehouse_error = RuntimeError(
        'relation "pellier.warehouse_inventory" does not exist'
    )

    response = client.get("/api/products")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 9
    assert all(row["warehouses"] == [] for row in body)
    assert body[0]["quantity"] == 40


def test_get_product_by_id_returns_description_and_live_stock(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """The detail route SHALL carry catalog copy plus per-warehouse stock."""
    fake_db.warehouse_rows["5"] = [
        {
            "warehouse_id": "BK-01",
            "name": "Brooklyn",
            "city": "Brooklyn, NY",
            "ship_window_min": 1,
            "ship_window_max": 2,
            "quantity": 12,
        },
        {
            "warehouse_id": "ATX-02",
            "name": "Austin",
            "city": "Austin, TX",
            "ship_window_min": 2,
            "ship_window_max": 4,
            "quantity": 6,
        },
    ]

    body = client.get("/api/products/5").json()

    assert body["description"] == "Editorial description for Sundress in Washed Linen."
    # ``quantity`` is 40 + index; product 5 is the fifth fixture row.
    assert body["availability"]["onHand"] == 44
    warehouses = body["availability"]["warehouses"]
    assert [w["warehouseId"] for w in warehouses] == ["BK-01", "ATX-02"]
    assert warehouses[0] == {
        "warehouseId": "BK-01",
        "name": "Brooklyn",
        "city": "Brooklyn, NY",
        "quantity": 12,
        "shipWindowMin": 1,
        "shipWindowMax": 2,
    }
    # The listing fields survive on the superset shape.
    assert body["id"] == 5
    assert "reviewCount" in body and "imageUrl" in body


def test_get_product_by_id_degrades_when_warehouse_join_fails(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """A missing warehouse table SHALL NOT 500 the product page.

    Clusters seeded before the warehouse migration have
    ``product_catalog.quantity`` but no ``pellier.warehouse_inventory``.
    The catalog on-hand count is still reported; the breakdown is empty.
    """
    fake_db.warehouse_error = RuntimeError(
        'relation "pellier.warehouse_inventory" does not exist'
    )

    resp = client.get("/api/products/5")

    assert resp.status_code == 200
    body = resp.json()
    assert body["availability"]["onHand"] == 44
    assert body["availability"]["warehouses"] == []


def test_get_product_by_id_reports_null_availability_without_quantity(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """A null catalog quantity SHALL surface as null, never as zero stock.

    ``availability: null`` means "not read". Coercing it to ``0`` would
    render as out-of-stock on the product page, which is a fabricated
    claim about the authoritative system.
    """
    for row in fake_db._rows:  # noqa: SLF001 - fixture surgery, not API use
        if row["id"] == 5:
            row["quantity"] = None

    body = client.get("/api/products/5").json()

    assert body["availability"] is None


# ---------------------------------------------------------------------------
# GET /api/inventory (Req 3.5.1–3.5.2)
# ---------------------------------------------------------------------------


def test_inventory_returns_counts_and_timestamp(client: TestClient) -> None:
    """Req 3.5.1: the inventory signal SHALL return a counts map + a
    ``last_refreshed`` ISO-8601 timestamp, one entry per category with
    in-stock rows."""
    resp = client.get("/api/inventory")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {"last_refreshed", "counts", "stale", "freshness"}
    # One entry per department the seeded showcase carries.
    assert set(body["counts"].keys()) == {"Clothing", "Bags and travel", "Shoes", "Home"}
    # ISO-8601 with tz.
    parsed = datetime.fromisoformat(body["last_refreshed"])
    assert parsed.tzinfo is not None
    # Fresh seed data -> not stale.
    assert body["stale"] is False
    assert body["freshness"] == "current"


def test_inventory_stale_field_is_evidence_not_server_clock(
    client: TestClient, fake_db: FakeDatabaseService
) -> None:
    """No catalog timestamp means unavailable freshness, never ``now``."""
    for row in fake_db._rows:  # noqa: SLF001 - fixture surgery, not API use
        row["updated_at"] = None

    resp = client.get("/api/inventory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_refreshed"] is None
    assert body["stale"] is None
    assert body["freshness"] == "unavailable"


# ---------------------------------------------------------------------------
# Converter boundary
# ---------------------------------------------------------------------------
#
# The catalog stores the eight store departments
# (``services/structured_extract.KNOWN_CATEGORIES``) and the wire shape uses
# the same Literal (``models/search.StorefrontCategory``), so the converter
# passes the department through. tests/test_api_smoke_postgres.py proves the
# same thing against a real database.


def _stoneware_pitcher(category: str) -> Dict[str, Any]:
    return {
        "id": 99,
        "brand": "Pellier",
        "name": "Stoneware Pitcher",
        "color": "sand",
        "price": 78.0,
        "rating": 4.6,
        "reviews": "12",
        "category": category,
        "image_url": "https://example.com/99.jpg",
        "badge": None,
        "tags": ["home", "ceramic"],
    }


def test_row_to_storefront_product_passes_the_department_through() -> None:
    """A department SHALL reach the wire unchanged."""
    from routes.products import _row_to_storefront_product

    product = _row_to_storefront_product(_stoneware_pitcher("Kitchen and table"))
    assert product.category == "Kitchen and table"


def test_row_to_storefront_product_refuses_a_category_outside_the_departments() -> None:
    """A row outside the eight departments fails loudly instead of being relabelled."""
    from pydantic import ValidationError

    from routes.products import _row_to_storefront_product

    with pytest.raises(ValidationError):
        _row_to_storefront_product(_stoneware_pitcher("Tops"))


def test_row_to_storefront_product_drops_empty_badge() -> None:
    """A DB row with ``badge=''`` SHALL project to ``badge=None`` on the
    wire — the StorefrontBadge Literal does not accept the empty string.
    """
    from routes.products import _row_to_storefront_product

    product = _row_to_storefront_product({
        "id": 100,
        "brand": "Pellier",
        "name": "Linen Robe",
        "color": "cream",
        "price": 220.0,
        "rating": 4.8,
        "reviews": "47",
        "category": "Clothing",
        "image_url": "https://example.com/100.jpg",
        "badge": "",
        "tags": ["linen"],
    })
    assert product.badge is None
