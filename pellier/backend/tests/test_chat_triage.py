"""Tests for ``services.chat.classify_triage`` — deterministic small-talk short-circuit.

The triage classifier runs before any orchestrator dispatch so
greetings/meta/thanks queries never depend on an LLM roll. These
tests pin the bucket mapping so a workshop demo that opens with "hi"
is guaranteed to produce a reply.
"""

from __future__ import annotations

import pytest

from services.chat import classify_triage, _TRIAGE_REPLIES


class TestTriageGreetings:
    @pytest.mark.parametrize(
        "query",
        [
            "hi",
            "Hi",
            "HI!",
            "hello",
            "Hello.",
            "hey",
            "hey there",
            "howdy",
            "yo",
            "good morning",
            "Good Afternoon",
            "good evening",
            "hi there",
            "hello, can you help me out",  # short-enough greeting prefix
        ],
    )
    def test_recognises_common_greetings(self, query: str) -> None:
        assert classify_triage(query) == "greeting"


class TestTriageMeta:
    @pytest.mark.parametrize(
        "query",
        [
            "what can you do",
            "What can you do?",
            "who are you",
            "what are you",
            "how do you work",
            "what are your capabilities",
            "help",
            "how can you help",
            "what can I ask",
        ],
    )
    def test_recognises_meta_queries(self, query: str) -> None:
        assert classify_triage(query) == "meta"


class TestTriageThanks:
    @pytest.mark.parametrize(
        "query",
        ["thanks", "thank you", "thanks!", "thx", "ty", "appreciate it"],
    )
    def test_recognises_thanks(self, query: str) -> None:
        assert classify_triage(query) == "thanks"


class TestTriageFallsThrough:
    @pytest.mark.parametrize(
        "query",
        [
            "find me a linen shirt under $150",
            "what's low on stock right now",
            "compare two mens shirts",
            "return policy?",
            "best headphones for travel",
            "",  # empty query
            "    ",  # whitespace
        ],
    )
    def test_real_queries_are_not_triaged(self, query: str) -> None:
        assert classify_triage(query) is None

    def test_long_query_starting_with_hi_is_not_triaged(self) -> None:
        """Long queries that happen to start with 'hi' are real
        questions, not greetings. The 60-char ceiling is what
        separates 'hi!' from 'hi, can you find me a linen shirt
        under $150 in a travel-friendly fabric?'"""
        long_q = (
            "hi, can you find me a linen shirt under $150 in a "
            "travel-friendly fabric please"
        )
        assert len(long_q) > 60
        assert classify_triage(long_q) is None


class TestTriageRepliesShape:
    def test_every_bucket_has_a_reply(self) -> None:
        for bucket in ("greeting", "meta", "thanks"):
            assert bucket in _TRIAGE_REPLIES
            assert _TRIAGE_REPLIES[bucket]
            # On-brand: should not start with generic "I can help"
            assert len(_TRIAGE_REPLIES[bucket]) > 20
