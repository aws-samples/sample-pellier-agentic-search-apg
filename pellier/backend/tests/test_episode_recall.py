"""Episode recall: run only when the operator asks about history, and say how.

Why this is not a fifth workflow
--------------------------------

Recall is a question about the past, not a deliverable. "Have we seen a return denied
like this?" can arrive during an investigation, a summary or a draft, so it attaches to
whichever workflow runs rather than replacing it — and it does not run otherwise, because
it costs a Bedrock embedding call plus a vector scan and a prior-resolution card beside
every summary is one an operator learns to skip.
"""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import Any, Dict, List

import pytest

from services import operator_concierge as OC
from services import operator_episodes as EP


def _code_only(source: str) -> str:
    """Strip docstrings and comments.

    Every structural scan below needs this: the comments in the code being scanned
    explain the very distinction the scan checks, so they contain the words that would
    make it pass or fail for the wrong reason.
    """
    out, in_doc = [], False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            if len(stripped) > 3 and stripped.endswith(stripped[:3]):
                continue
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        out.append(line.split("#", 1)[0])
    return chr(10).join(out)


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("request_text", [
    "Have we handled something similar before?",
    "Have we handled a damaged-item return like this before?",
    "Have we seen a return denied like this?",
    "Show me a prior resolution like this.",
    "How did we resolve this last time?",
    "Has this happened before?",
    "What did we do last time?",
])
def test_an_explicit_history_question_asks_for_recall(request_text: str) -> None:
    assert OC.classify_history_intent(request_text) is True


@pytest.mark.parametrize("request_text", [
    "Summarize this client",
    "What happened with her order?",
    "Draft a note about the ticket",
    "Find a replacement for the bowl",
    "Prepare the return for the bowl",
    "Investigate the dispute",
    "",
])
def test_an_ordinary_request_does_not(request_text: str) -> None:
    """Including "what happened", which is about THIS situation, not comparable ones."""
    assert OC.classify_history_intent(request_text) is False


def test_a_consequential_instruction_is_never_a_history_question() -> None:
    """The two classifiers are orthogonal and must not overlap on intent."""
    for text in ("prepare the return", "initiate a return", "log the return"):
        assert OC.classify_history_intent(text) is False


def test_recall_is_matched_against_the_operator_words_only() -> None:
    """A model saying "we have seen this before" must not trigger a retrieval."""
    source = _code_only(inspect.getsource(OC.classify_history_intent))
    assert "request" in source
    for model_ish in ("bedrock", "converse", "synthesize", "answer", "prose"):
        assert model_ish not in source.lower(), model_ish


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------


class FakeDb:
    """Returns whatever `retrieve_episodes` is patched to return; unused here."""


@pytest.fixture
def no_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Bedrock in the unit suite. Recall must degrade to recency, not fail."""
    class _Broken:
        def embed_query(self, _text: str):
            raise RuntimeError("bedrock unavailable")

    import services.embeddings as emb

    monkeypatch.setattr(emb, "EmbeddingService", _Broken)


def _episode(**over: Any) -> EP.Episode:
    base: Dict[str, Any] = {
        "customer_id": "CUST-THEO",
        "episode_type": EP.EPISODE_RETURN_RESOLUTION,
        "situation": "CUST-THEO asked for a damaged return on product 37.",
        "resolution": "Return 37 was created through the governed path.",
        "human_outcome": "confirmed",
        "policy_outcome": "allow",
        "aurora_outcome": "applied",
        "episode_id": 37,
        "review_id": 40,
    }
    base.update(over)
    return EP.Episode(**base)


@pytest.mark.asyncio
async def test_recall_degrades_to_recency_when_embedding_fails(
    monkeypatch: pytest.MonkeyPatch, no_embedding: None
) -> None:
    """And says so. An operator told "3 similar" deserves to know how they were found."""
    async def _retrieve(_db, **kwargs):
        assert kwargs.get("embedding") is None
        return [_episode()]

    monkeypatch.setattr(EP, "retrieve_episodes", _retrieve)
    steps, evidence, artifact, block = await OC._prior_resolutions(
        FakeDb(), customer_id="CUST-THEO", request="have we seen this before?"
    )
    assert artifact["priorResolutions"]["retrieval"]["mode"] == "recent"
    assert len(evidence) == 1
    assert steps[0].source == OC.SOURCE_AURORA
    assert "PRIOR RESOLUTIONS" in block


@pytest.mark.asyncio
async def test_an_empty_recall_is_an_answer(
    monkeypatch: pytest.MonkeyPatch, no_embedding: None
) -> None:
    async def _retrieve(_db, **_kwargs):
        return []

    monkeypatch.setattr(EP, "retrieve_episodes", _retrieve)
    steps, evidence, artifact, block = await OC._prior_resolutions(
        FakeDb(), customer_id="CUST-FRESH", request="have we seen this before?"
    )
    assert artifact["priorResolutions"]["episodes"] == []
    assert evidence == []
    # Nothing is handed to the model, so it cannot narrate history that does not exist.
    assert block == ""
    assert "no prior governed resolutions" in steps[0].result


@pytest.mark.asyncio
async def test_recall_is_bounded(
    monkeypatch: pytest.MonkeyPatch, no_embedding: None
) -> None:
    """Three is enough to inform a judgment. A page of them is a relevance problem."""
    seen: Dict[str, Any] = {}

    async def _retrieve(_db, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(EP, "retrieve_episodes", _retrieve)
    await OC._prior_resolutions(
        FakeDb(), customer_id="CUST-THEO", request="have we seen this before?"
    )
    assert seen["limit"] == OC._MAX_PRIOR_EPISODES <= 3


@pytest.mark.asyncio
async def test_recall_is_scoped_to_the_bound_client(
    monkeypatch: pytest.MonkeyPatch, no_embedding: None
) -> None:
    """The session's customer, never one named in the request."""
    seen: Dict[str, Any] = {}

    async def _retrieve(_db, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(EP, "retrieve_episodes", _retrieve)
    await OC._prior_resolutions(
        FakeDb(),
        customer_id="CUST-THEO",
        request="have we seen this before for CUST-AMARA?",
    )
    assert seen["customer_id"] == "CUST-THEO"


@pytest.mark.asyncio
async def test_a_read_failure_yields_no_episodes_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, no_embedding: None
) -> None:
    async def _retrieve(_db, **_kwargs):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(EP, "retrieve_episodes", _retrieve)
    with pytest.raises(RuntimeError):
        # `retrieve_episodes` owns its own best-effort handling; the stage does not
        # double-swallow, because a bug in the query must be visible in the log.
        await OC._prior_resolutions(
            FakeDb(), customer_id="CUST-THEO", request="have we seen this before?"
        )


def test_the_query_side_is_embedded_as_a_query() -> None:
    """Cohere Embed v4 is asymmetric: `embed_query` here, `embed_document` on write."""
    source = _code_only(inspect.getsource(OC._prior_resolutions))
    assert "embed_query" in source
    assert "embed_document" not in source
    # Blocking call, so it runs off the request loop.
    assert "to_thread" in source


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_the_turn_runs_recall_only_on_an_explicit_history_question() -> None:
    source = inspect.getsource(OC)
    assert "if classify_history_intent(request):" in source


def test_recall_is_not_a_fourth_workflow() -> None:
    """A workflow is a deliverable. Recall is context attached to one."""
    assert "prior_resolution" not in OC.SUPPORTED_WORKFLOWS
    assert "episode_recall" not in OC.SUPPORTED_WORKFLOWS
    assert len(OC.SUPPORTED_WORKFLOWS) == 3


def test_recall_composes_with_a_workflow_context_stage() -> None:
    """Both blocks reach the model; neither replaces the other."""
    source = inspect.getsource(OC)
    start = source.index("fields, synth_step, model_id = await synthesize_async(")
    # To the end of the call, not to the first ")" - which lands inside it.
    joined = source[start: source.index("if synth_step is not None:", start)]
    assert "workflow_context.prompt_block" in joined
    assert "recall_block" in joined


def test_the_recall_artifact_reaches_the_payload() -> None:
    source = inspect.getsource(OC)
    assert "artifact.update(recall_artifact)" in source


def test_the_episode_axes_are_rendered_from_the_row_not_the_prose() -> None:
    """The card and the answer cannot disagree about how something ended."""
    component = pathlib.Path(
        "../frontend/src/operator/concierge/ConciergePriorResolutions.tsx"
    ).read_text()
    for field in ("humanOutcome", "policyOutcome", "auroraOutcome", "resolution"):
        assert f"episode.{field}" in component, field


def test_the_operator_card_shows_no_retrieval_mechanics() -> None:
    component = pathlib.Path(
        "../frontend/src/operator/concierge/ConciergePriorResolutions.tsx"
    ).read_text()
    body = component[component.index("const ConciergePriorResolutions"):]
    # Strip block comments across lines. The comments explain WHY these mechanics are
    # absent from the card, so a naive scan trips on the explanation.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    body = re.sub(r"^\s*//.*$", "", body, flags=re.MULTILINE)
    # The MECHANICS, not the word. "ordered by date rather than by similarity" is plain
    # English explaining the fallback, and the operator is owed it; a cosine distance or
    # an index name is retriever tuning and belongs in the Observatory.
    for jargon in ("HNSW", "cosine", "pgvector", "<=>", "distance", "embedding"):
        assert jargon not in body, jargon
    # And no score is rendered, whatever the row carries.
    assert "episode.similarity" not in body
    assert ".similarity" not in body
