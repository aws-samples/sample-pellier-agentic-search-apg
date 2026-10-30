"""The own-account page keeps the shape the three workshops share and quotes measured figures."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PAGE = REPO_ROOT / "docs" / "run-in-your-own-account.md"
EVIDENCE = REPO_ROOT / "docs" / "evidence"
HEADINGS = (
    "## 1. What you get and what it costs",
    "## 2. Before you start",
    "## 3. Prepare the data",
    "## 4. Deploy",
    "## 5. Use the workshop guide",
    "## 6. Tear down",
    "## 7. Adapt it to your own data",
)


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_the_page_has_the_seven_sections_in_order() -> None:
    text = _page()
    assert text.startswith("# Run Pellier in your own account\n")
    positions = [text.index(heading) for heading in HEADINGS]
    assert positions == sorted(positions)
    assert len(re.findall(r"(?m)^## ", text)) == len(HEADINGS)


def test_every_command_block_is_one_copyable_command() -> None:
    blocks = re.findall(r"```bash\n(.*?)```", _page(), re.S)
    assert blocks, "the page gives its commands in bash blocks"
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        assert len(lines) == 1, block


def test_the_page_names_the_scripts_and_links_the_evidence() -> None:
    text = _page()
    assert "deploy/own-account/deploy.py deploy --region" in text
    assert "deploy/own-account/deploy.py teardown --region" in text
    assert "scripts/check_model_access.py" in text
    assert "(evidence/)" in text
    assert ":image" not in text and "![" not in text


def test_the_page_quotes_the_newest_measured_deploy_time_when_a_record_exists() -> None:
    records = sorted(EVIDENCE.glob("own-account-proof-*.md"))
    if not records:
        return
    newest = records[-1].read_text(encoding="utf-8")
    match = re.search(r"Stack ready in (\d+ min \d+ s)", newest)
    assert match, f"{records[-1].name} must quote the deploy command's 'Stack ready in' line"
    assert match.group(1) in _page(), "the page quotes the newest record's deploy time"


def test_the_readme_and_workshop_doc_link_the_page() -> None:
    for name in ("README.md", "WORKSHOP.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "docs/run-in-your-own-account.md" in text, name
