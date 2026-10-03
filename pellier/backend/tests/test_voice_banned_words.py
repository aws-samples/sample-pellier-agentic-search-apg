"""VOICE.md names the words Pellier no longer uses, and the voice says store, not boutique."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BANNED_WORDS = ("boutique", "luxury", "investment piece", "curated", "exclusive")


def test_voice_lists_the_banned_words():
    voice = (REPO / "VOICE.md").read_text().lower()
    for word in BANNED_WORDS:
        assert word in voice, f"VOICE.md must name '{word}' as banned"


def test_voice_describes_a_store_not_a_boutique_outside_the_ban_list():
    voice = (REPO / "VOICE.md").read_text()
    body, _, _ = voice.partition("## Words we do not use")
    assert "boutique" not in body.lower()
