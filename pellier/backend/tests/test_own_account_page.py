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


def test_the_readme_cost_summary_quotes_the_page() -> None:
    """The README's cost figures, their pairings and their date come from the page's tables.

    Figures are compared whole, so a README "$0.5" cannot pass against the page's "$0.52", and
    each cost cell's phrase ("$0.52 an hour, about $379", "$0.51 to $0.52") must appear on the
    page as written, so two figures cannot swap rows unnoticed.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "### What it costs" in readme, "README lost its cost summary"
    summary = readme.split("### What it costs", 1)[1].split("\n## ", 1)[0]
    page = " ".join(_page().split())
    amount = r"\$\d+(?:\.\d+)?"
    figures = re.findall(amount, summary)
    assert figures, "README's cost summary quotes no figures"
    on_page = set(re.findall(amount, page))
    missing = [figure for figure in figures if figure not in on_page]
    assert not missing, f"README quotes {missing}, which the own-account page does not"
    phrase = re.compile(rf"(?:about )?{amount}(?:(?: an hour, about | to ){amount})?")
    cells = [row.rstrip(" |").rsplit("|", 1)[-1] for row in summary.splitlines()
             if row.startswith("| ") and "$" in row]
    assert len(cells) == 3, f"expected three cost rows, found {len(cells)}"
    for cell in cells:
        quoted = phrase.search(cell).group(0)
        assert quoted in page, f"README's {quoted!r} is not on the own-account page as written"
    dated = re.search(r"\d{1,2} (?:January|February|March|April|May|June|July|August|"
                      r"September|October|November|December) 20\d\d", summary)
    assert dated and dated.group(0) in page, "README's price date must match the page's"
    assert "docs/run-in-your-own-account.md#1-what-you-get-and-what-it-costs" in summary
    assert HEADINGS[0] == "## 1. What you get and what it costs", "the summary's link anchor moved"
    if "5 cents a request" in summary:
        assert "5 cents a request" in page, "README's per-request average is not on the page"


OBSERVABILITY = REPO_ROOT / "scripts" / "teardown_agentcore_observability.py"


def _bullet(heading: str) -> str:
    """The list item of section 6 that starts with this bold heading."""
    match = re.search(rf"(?ms)^- \*\*{re.escape(heading)}.*?(?=^- \*\*|^To confirm)", _page())
    assert match, f"section 6 lost its {heading!r} item"
    return " ".join(match.group(0).split())


def test_the_manual_xray_fallback_follows_the_receipt_not_a_blanket_delete() -> None:
    """The account-wide policy may predate Pellier, so it is deleted only when Pellier made it."""
    item = _bullet("Account-wide X-Ray settings")
    script = OBSERVABILITY.read_text(encoding="utf-8")
    for field in ("resource_policy_created", "previous_resource_policy_document"):
        assert field in script, f"{field} is no longer a receipt field the teardown reads"
        assert field in item, f"the fallback does not say what {field} decides"
    assert "managed-receipt.json" in item
    assert "put-resource-policy" in item and "delete-resource-policy" in item
    assert item.index("resource_policy_created") < item.index("delete-resource-policy")
    assert "no receipt" in item.lower() and "leave" in item.lower()
    assert "Search back to the values you had" not in item


def _commands() -> list[str]:
    return re.findall(r"```bash\n(.*?)```", _page(), re.S)


def test_the_reader_clones_before_running_any_repository_script() -> None:
    text = _page()
    clone = text.index("git clone")
    for script in ("deploy/own-account/deploy.py check", "scripts/check_model_access.py"):
        assert clone < text.index(script), f"{script} is run before the clone"
    assert "cd sample-pellier-agentic-search-apg" in _commands()[0]
    assert "git checkout governed" not in text


def test_a_studio_visitor_checks_out_the_commit_the_link_names() -> None:
    text = " ".join(_page().split())
    assert any(block.startswith("git checkout ") for block in _commands())
    assert "link that brought you here" in text and "commit" in text
    assert "newest commit on `governed`" in text


def test_one_region_is_chosen_once_and_every_command_uses_it() -> None:
    text = _page()
    blocks = _commands()
    export = next(i for i, block in enumerate(blocks) if block.startswith("export AWS_REGION="))
    assert text.index("export AWS_REGION=") < text.index("deploy/own-account/deploy.py check")
    for block in blocks[export + 1 :]:
        if "check_model_access" in block or "own-account/deploy.py" in block:
            assert '--region "$AWS_REGION"' in block, block
            assert "us-east-1" not in block and "us-west-2" not in block, block
