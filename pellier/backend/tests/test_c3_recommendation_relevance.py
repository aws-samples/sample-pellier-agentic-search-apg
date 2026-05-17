"""Relevance test for the Challenge 3 `recommendation` agent.

Validates Requirement 2.4.3-2.4.5 from
`.kiro/specs/pellier-storefront/requirements.md`:

  2.4.3  The specialist is a Strands `Agent` wrapping `BedrockModel` with
         `temperature=0.2` and the four tools
         `[find_pieces, whats_trending, side_by_side,
         explore_collection]`.
  2.4.4  The system prompt emphasizes warm, editorial, catalog-style
         reasoning grounded in specific product attributes.
  2.4.5  Calling the agent with `something for warm evenings out` returns
         a response that names a specific product AND that product's
         `tags` intersect the evening/warm set
         `{evening, warm, dresses, outerwear}`. Sundress in Washed Linen
         or Cashmere-Blend Cardigan pass; Signature Straw Tote fails.

Bedrock is stubbed - no live model call. The test swaps the `Agent` symbol
imported into `agents.curator` for a stub that returns a
canned answer mentioning `Sundress in Washed Linen`. The test then parses
that response, looks up the product's tags from the 9-showcase-product
table captured from `.kiro/steering/storefront.md`, and asserts the
required overlap.

Runnable from the repo root per `pytest.ini`:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_c3_recommendation_relevance.py -v
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

import pytest


# ---------------------------------------------------------------------------
# Showcase tag table (storefront.md "The 9 showcase products")
# ---------------------------------------------------------------------------

SHOWCASE_TAGS: dict[str, set[str]] = {
    "Italian Linen Camp Shirt": {
        "minimal", "serene", "classic", "warm", "neutral",
        "everyday", "slow", "linen",
    },
    "Wide-Leg Linen Trousers": {
        "creative", "bold", "warm", "earth", "everyday", "travel", "linen",
    },
    "Signature Straw Tote": {
        "classic", "serene", "neutral", "soft", "travel",
        "everyday", "accessories",
    },
    "Relaxed Oxford Shirt": {
        "classic", "minimal", "neutral", "soft", "everyday", "work", "linen",
    },
    "Sundress in Washed Linen": {
        "creative", "bold", "warm", "earth", "evening", "dresses", "linen",
    },
    "Leather Slide Sandal": {
        "minimal", "classic", "earth", "warm", "everyday", "travel", "footwear",
    },
    "Cashmere-Blend Cardigan": {
        "minimal", "serene", "classic", "neutral", "earth", "slow",
        "evening", "outerwear",
    },
    "Ceramic Tumbler Set": {
        "minimal", "serene", "creative", "neutral", "soft", "slow", "home",
    },
    "Linen Utility Jacket": {
        "adventurous", "creative", "earth", "neutral", "outdoor",
        "travel", "outerwear",
    },
}

# The evening/warm set the specialist should hit for "warm evenings out".
EVENING_WARM_TAGS = {"evening", "warm", "dresses", "outerwear"}


def _lookup_product_in_text(text: str) -> tuple[str, set[str]] | None:
    """Find the first showcase product name that appears in `text`.

    Returns (product_name, tags) or None if nothing matches. Longest names
    are checked first so, for example, `Relaxed Oxford Shirt` doesn't mask
    a sibling whose name shares a prefix.
    """
    ordered = sorted(SHOWCASE_TAGS.keys(), key=len, reverse=True)
    for name in ordered:
        if name in text:
            return name, SHOWCASE_TAGS[name]
    return None


# ---------------------------------------------------------------------------
# Stub Bedrock Agent (no network call)
# ---------------------------------------------------------------------------


class _StubBedrockModel:
    """Swap for `BedrockModel`. Captures kwargs so the test can assert them."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _StubAgent:
    """Swap for `strands.Agent`. Captures construction kwargs and returns
    a canned response when called. Construction kwargs are exposed on the
    class so the test can inspect model choice, tools, and system prompt
    after the wrapped specialist builds the agent."""

    # Class-level capture - reset by the fixture so the parallel tests
    # don't share state.
    last_kwargs: dict[str, Any] = {}
    canned_reply: str = ""

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs

    def add_hook(self, _hook: Callable[[Any], None]) -> None:
        # Real Strands Agent accepts hooks; the stub accepts but ignores.
        pass

    def __call__(self, _query: str) -> str:
        return type(self).canned_reply


@pytest.fixture(autouse=True)
def _reset_stub_state() -> Iterable[None]:
    _StubAgent.last_kwargs = {}
    _StubAgent.canned_reply = ""
    yield
    _StubAgent.last_kwargs = {}
    _StubAgent.canned_reply = ""


@pytest.fixture
def stubbed_specialist(monkeypatch: pytest.MonkeyPatch):
    """Return the `recommendation` agent's underlying callable with
    Strands `Agent` + `BedrockModel` swapped for the stubs above."""
    import agents.curator as rec

    monkeypatch.setattr(rec, "Agent", _StubAgent)
    monkeypatch.setattr(rec, "BedrockModel", _StubBedrockModel)

    # Reach past the @tool decorator to the original function so we can
    # call it directly in a test. Same pattern as test_agent_tools.py.
    fn = getattr(
        rec.recommendation,
        "__wrapped__",
        rec.recommendation,
    )
    return fn


# ---------------------------------------------------------------------------
# Req 2.4.3 - construction wiring
# ---------------------------------------------------------------------------


def test_curator_is_constructed_with_per_agent_model_mix_and_four_tools(
    stubbed_specialist,
) -> None:
    """Building the Curator SHALL match the per-agent model mix from
    ``lab-content/shared/model-mix-sidebar.en.md``:

      - Claude Opus 4.6 (BEDROCK_OPUS_MODEL)
      - temperature 0.4 (warm — recommendations carry "taste")
      - exactly four tools: find_pieces_hybrid + whats_trending +
        side_by_side + explore_collection.

    ``find_pieces_hybrid`` is the Curator's anchor capability (Anna's
    pgvector + Postgres FTS + Cohere Rerank pipeline). Other specialists keep
    plain ``find_pieces``.
    """
    _StubAgent.canned_reply = "A canned response - ignored by this test."

    stubbed_specialist(query="anything")

    kwargs = _StubAgent.last_kwargs
    assert "model" in kwargs, "Agent SHALL be constructed with a model= kwarg"
    assert isinstance(kwargs["model"], _StubBedrockModel)
    assert kwargs["model"].kwargs.get("temperature") == 0.4

    tool_names = [getattr(t, "__name__", repr(t)) for t in kwargs.get("tools", [])]
    # Strands @tool produces a DecoratedFunctionTool; unwrap to expose the
    # original function name. Fall back to whatever was captured.
    unwrapped = []
    for t in kwargs.get("tools", []):
        inner = getattr(t, "__wrapped__", t)
        unwrapped.append(getattr(inner, "__name__", repr(inner)))

    assert set(unwrapped) == {
        "find_pieces_hybrid",
        "whats_trending",
        "side_by_side",
        "explore_collection",
    }, f"expected the four Curator tools, got {unwrapped!r} / {tool_names!r}"


def test_agent_system_prompt_references_recommendation_voice(
    stubbed_specialist,
) -> None:
    """System prompt SHALL come from copy.RECOMMENDATION_SYSTEM_PROMPT and
    SHALL include the warm / editorial / catalog-style framing from Req 2.4.4."""
    _StubAgent.canned_reply = "stub"
    stubbed_specialist(query="anything")

    prompt = _StubAgent.last_kwargs.get("system_prompt", "")
    assert isinstance(prompt, str) and prompt, "system_prompt SHALL be a non-empty str"
    lowered = prompt.lower()
    assert "curator" in lowered or "recommendation specialist" in lowered
    assert "warm" in lowered
    assert "editorial" in lowered
    assert "catalog" in lowered


# ---------------------------------------------------------------------------
# Req 2.4.5 - relevance check on warm evenings out
# ---------------------------------------------------------------------------


def test_warm_evenings_recommendation_tags_overlap_evening_set(
    stubbed_specialist,
) -> None:
    """A recommendation for `something for warm evenings out` that names
    `Sundress in Washed Linen` SHALL have tags intersecting the evening /
    warm set `{evening, warm, dresses, outerwear}`."""
    _StubAgent.canned_reply = (
        "Try the Sundress in Washed Linen by Pellier Editions in Golden Ochre "
        "at $148. Linen that catches the late light, cut for still-warm "
        "evenings out."
    )

    response = stubbed_specialist(query="something for warm evenings out")

    # The specialist wraps the agent's response; the canned reply should
    # survive into the final returned text (possibly with a trailing JSON
    # products block appended by _ensure_products_in_output).
    assert isinstance(response, str)
    assert "Sundress in Washed Linen" in response

    matched = _lookup_product_in_text(response)
    assert matched is not None, (
        "specialist response SHALL name a specific showcase product"
    )
    name, tags = matched
    overlap = tags & EVENING_WARM_TAGS
    assert overlap, (
        f"{name} tags {sorted(tags)} SHALL overlap the evening/warm set "
        f"{sorted(EVENING_WARM_TAGS)}; got empty intersection"
    )


def test_irrelevant_straw_tote_recommendation_fails_the_evening_check() -> None:
    """The Signature Straw Tote tags SHALL NOT intersect the evening/warm
    set, so a specialist that recommends it for `warm evenings out` SHALL
    fail the Req 2.4.5 verification. This test fixes the negative case:
    if this assertion ever flips, the relevance oracle itself is broken."""
    tote_tags = SHOWCASE_TAGS["Signature Straw Tote"]
    assert not (tote_tags & EVENING_WARM_TAGS), (
        "Signature Straw Tote SHALL NOT intersect the evening/warm set; "
        "the Req 2.4.5 oracle would be toothless if it did"
    )


def test_sundress_passes_the_evening_check() -> None:
    """Positive anchor: the Sundress in Washed Linen SHALL intersect the
    evening/warm set, confirming the specialist's preferred pick is a
    real match for `warm evenings out`."""
    sundress_tags = SHOWCASE_TAGS["Sundress in Washed Linen"]
    overlap = sundress_tags & EVENING_WARM_TAGS
    assert {"evening", "warm"}.issubset(overlap), (
        f"Sundress in Washed Linen tags {sorted(sundress_tags)} SHALL "
        f"cover at least {{'evening', 'warm'}}; got overlap {sorted(overlap)}"
    )
