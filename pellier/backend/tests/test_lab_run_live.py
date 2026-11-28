"""The live turn on a terminal, end to end through ``lab_run send``.

A send writes the live region many times over: each frame erases the last and draws the next.
These tests replay the raw bytes through a small screen (carriage return, cursor up, clear
down) and check what is left on it, which is what a participant sees once the turn ends.
"""
import contextlib
import io
import pathlib
import re
import subprocess
import sys
from typing import List

import pytest

# The stand-in Pellier and the send tests' own set-up: no .env, a fresh retry budget and the
# starter catalog lookup. Imported fixtures apply here as they do there.
from tests.test_lab_run import (  # noqa: F401
    STEPS, _fresh_retry_budget, _no_env_file, _run, _starter_catalog_lookup, fake)

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import lab_run  # noqa: E402
import live_view  # noqa: E402

_ESCAPE = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


class Terminal(io.StringIO):
    """Standard output that says it is a terminal."""

    def isatty(self) -> bool:
        return True


def screen(raw: str) -> List[str]:
    """The lines a terminal shows after ``raw``, colours dropped."""
    rows, row, col, at = [""], 0, 0, 0
    while at < len(raw):
        code = _ESCAPE.match(raw, at)
        if code:
            count, command = code.groups()
            if command == "A":
                row = max(0, row - int(count or 1))
            elif command == "J":
                rows[row] = rows[row][:col]
                del rows[row + 1:]
            at = code.end()
            continue
        char = raw[at]
        if char == "\r":
            col = 0
        elif char == "\n":
            row, col = row + 1, 0
            rows.extend([""] * (row + 1 - len(rows)))
        else:
            line = rows[row].ljust(col)
            rows[row] = line[:col] + char + line[col + 1:]
            col += 1
        at += 1
    return rows


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> Terminal:
    """A terminal for the send to write to, live view on, as on a workshop box. The send runs
    inside ``on`` below: pytest puts its own capture back between set-up and the test."""
    monkeypatch.delenv(live_view.OFF_ENV, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    return Terminal()


def on(terminal: Terminal, fake, *args: str) -> int:
    with contextlib.redirect_stdout(terminal):
        return _run(fake, 1, None, *args)


def test_a_full_trace_send_leaves_each_step_once_and_the_answer_once(
    fake, terminal: Terminal,
) -> None:
    fake.steps = STEPS
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    shown = screen(terminal.getvalue())
    assert sum("1 Router" in line for line in shown) == 1
    assert sum("2 done    search_products  Searching the catalog" in line for line in shown) == 1
    assert not any(live_view.RING in line or live_view.DOT in line for line in shown), (
        "the rings and the status line are gone once the turn ends")
    answers = [line for line in shown if line.lstrip().startswith("Pellier:")]
    assert len(answers) == 1, "the revealed answer stays and is not printed a second time"
    assert any("+ OK    Answered by the local agents" in line for line in shown)


def test_the_tool_calls_and_the_rail_words_are_lavender_on_the_local_agents(
    fake, terminal: Terminal,
) -> None:
    fake.steps = STEPS
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    raw = terminal.getvalue()
    lavender = lab_run.check.LOCAL_COLOUR
    assert f"{lavender}search_products\x1b[0m  Searching the catalog" in raw
    assert f"Answered by the {lavender}local agents\x1b[0m" in raw
    assert lab_run.check.AGENTCORE_COLOUR not in raw, "nothing ran on AgentCore in Lab 1"


def test_pellier_s_reply_is_white_not_the_terminal_s_grey(fake, terminal: Terminal) -> None:
    fake.steps = STEPS
    fake.reply = "For slow mornings, the Stoneware Mugs make a warm gift."
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    raw = terminal.getvalue()
    assert f"{lab_run.check.ANSWER_COLOUR}For slow mornings, the Stoneware Mugs" in raw
    assert f"{lab_run.check.LOCAL_COLOUR}search_products" in raw, "the trace keeps its colours"


def test_lab_1_folds_the_live_turn_to_one_line_above_the_counts(
    fake, terminal: Terminal,
) -> None:
    fake.steps = STEPS
    on(terminal, fake, "--task", "1A")
    shown = screen(terminal.getvalue())
    question = next(i for i, line in enumerate(shown) if line.startswith("Anna: "))
    fold = shown[question + 1]
    assert fold == "✓ Router → local Catalog agent (gift), answered in 2 steps", (
        "the stand-in's Router finding, then the agent's own steps: its search and its "
        "ticket read, not the Router step")
    assert shown[question + 2].startswith("Full text (words)")
    assert not any(line.lstrip().startswith("Pellier:") for line in shown), (
        "Lab 1's compact send keeps the approved block: the answer folds away")


def test_the_off_switch_prints_what_a_log_gets(
    fake, terminal: Terminal, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake.steps = STEPS
    monkeypatch.setenv(live_view.OFF_ENV, "off")
    monkeypatch.setenv("NO_COLOR", "1")
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    raw = terminal.getvalue()
    assert "2 done    search_products  Searching the catalog" in raw
    assert "\x1b[" not in raw, "no region, no redraws and, with NO_COLOR, no colour"
    assert screen(raw) == raw.split("\n")


def test_no_shipped_file_turns_the_live_view_off() -> None:
    """The live view is on by default (owner, 28 Nov); off is a hand-set escape hatch."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split()
    allowed = {"scripts/live_view.py", "pellier/backend/tests/test_live_view.py",
               "pellier/backend/tests/test_lab_run_live.py"}
    setting = re.compile(rf"{live_view.OFF_ENV}\s*[=:]")
    offenders = []
    for name in tracked:
        path = REPO / name
        if name in allowed or not path.is_file() or path.suffix in (".png", ".jpg", ".gif"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if setting.search(text):
            offenders.append(name)
    assert offenders == []


def test_only_the_tool_call_takes_the_rail_colour_not_the_same_word_in_a_path(
    fake, terminal: Terminal,
) -> None:
    fake.steps = [{"type": "step", "id": "skills", "label": "Opening evidence", "status": "done",
                   "finding": "Loaded Evidence from skills/evidence/SKILL.md",
                   "builder": {"tool": "skills", "duration_ms": 38, "rail": "in-process"}}]
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    raw = terminal.getvalue()
    lavender = lab_run.check.LOCAL_COLOUR
    assert f"{lavender}skills\x1b[0m  Opening evidence" in raw
    assert "from skills/evidence/SKILL.md" in raw


@pytest.mark.parametrize("finding, folded", [
    ("Sent to the Catalog agent: housewarming, gift",
     "✓ Router → local Catalog agent (housewarming, gift), answered in 2 steps"),
    ("Sent to the Catalog agent (default)",
     "✓ Router → local Catalog agent (default), answered in 2 steps"),
    ("Sent to the Catalog agent", "✓ Router → local Catalog agent, answered in 2 steps"),
    ("Answered by the Router, no agent needed", "✓ Answered by the Router, no agent needed"),
    ("", "✓ Answered by the local agents"),
])
def test_the_fold_reads_every_form_of_the_router_s_finding(
    finding: str, folded: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    live = lab_run.live_turn(fold=True, rail=lab_run.IN_PROCESS) or live_view.LiveTurn(
        answer_lines=lambda text: [text], width=lambda: 100, step_line=lambda *a: "",
        done_line=lambda *a: "", fold=True, stream=Terminal())
    live.route, live.steps_done = finding, (3 if finding else 2)
    assert lab_run._fold_line(live, lab_run.IN_PROCESS) == folded


# -- the live view can never cost a lab command ------------------------------------------------


def test_this_checkout_loads_the_live_view() -> None:
    """The fallback below keeps a box running; here, a failed import must fail the suite."""
    assert lab_run.LIVE_VIEW_UNAVAILABLE == ""
    assert lab_run.live_view is live_view


def test_every_lab_command_still_loads_without_the_live_view_file() -> None:
    code = (
        "import sys\n"
        "sys.modules['live_view'] = None\n"  # importing it now raises, as a missing file would
        "sys.path.insert(0, 'scripts')\n"
        "import lab_run\n"
        "assert lab_run.live_view is None and lab_run.LIVE_VIEW_UNAVAILABLE\n"
        "assert lab_run.live_turn(fold=True, rail=lab_run.IN_PROCESS) is None\n"
        "try:\n"
        "    lab_run.main(['--help'])\n"
        "except SystemExit as stop:\n"
        "    assert stop.code == 0, stop.code\n"
        "print('lab_run runs without the live view')\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                          env={**__import__("os").environ, "PELLIER_DISABLE_DOTENV": "1"})
    assert done.returncode == 0, done.stderr[-2000:]
    assert "lab_run runs without the live view" in done.stdout


def test_a_send_without_the_live_view_prints_the_plain_trace(
    fake, terminal: Terminal, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lab_run, "live_view", None)
    fake.steps = STEPS
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    shown = screen(terminal.getvalue())
    assert sum(line.lstrip().startswith("Pellier:") for line in shown) == 1
    assert any("+ OK    Answered by the local agents" in line for line in shown)


def test_a_fault_in_the_live_view_costs_the_view_not_the_turn(
    fake, terminal: Terminal, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = live_view.LiveTurn._observe

    def faulty(self, event):
        if event.get("type") == "step" and event.get("status") == "done" \
                and event.get("id") == "step-1":
            raise RuntimeError("a fault in the view")
        return original(self, event)

    monkeypatch.setattr(live_view.LiveTurn, "_observe", faulty)
    fake.steps = STEPS
    assert on(terminal, fake, "--task", "1B", "--details") == 0
    shown = screen(terminal.getvalue())
    assert sum("2 done    search_products  Searching the catalog" in line for line in shown) == 1
    assert sum(line.lstrip().startswith("Pellier:") for line in shown) == 1, (
        "the answer prints as a log would")
    assert any("+ OK    Answered by the local agents" in line for line in shown)
    assert not any(live_view.RING in line or live_view.DOT in line for line in shown)
    assert not isinstance(sys.stdout, live_view._Guard), "the terminal's streams are back"


def test_every_sibling_module_a_script_imports_is_tracked() -> None:
    """A commit or a patch that leaves out a module a lab script imports breaks every command
    on a box. This fails until the module is added to git (``git ls-files`` reads the index)."""
    import ast

    empty_blob = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    tracked = set()
    for entry in subprocess.run(["git", "ls-files", "-s"], cwd=REPO, capture_output=True,
                                text=True, check=True).stdout.splitlines():
        meta, path = entry.split("\t", 1)
        on_disk = REPO / path
        if meta.split()[1] == empty_blob and on_disk.is_file() and on_disk.stat().st_size:
            continue  # intent-to-add only: a commit would not carry its content
        tracked.add(path)
    missing = []
    for name in sorted(tracked):
        if not (name.startswith("scripts/") and name.endswith(".py")):
            continue
        tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module.split(".")[0]]
            else:
                continue
            for module in modules:
                sibling = str(pathlib.PurePosixPath(name).parent / f"{module}.py")
                if (REPO / sibling).is_file() and sibling not in tracked:
                    missing.append(f"{name} imports {sibling}, which git does not track")
    assert missing == []
