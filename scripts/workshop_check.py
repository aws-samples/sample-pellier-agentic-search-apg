"""What every workshop check shares: how it reaches Aurora, and how it reports.

Every check prints three things: what was expected, what was observed, and the
evidence behind it (the row, the decision, the key). A check that did not pass
also says what to look at next. The lab checks and the evidence export render
through :func:`render` and :func:`table`, bordered boxes that wrap inside their
columns, so a participant reads one shape everywhere.

A finding is in one of four states, never two:

    PASSED           a durable row exists and satisfies the claim
    NOT YET PASSED   the lab has not left its evidence
    COULD NOT CHECK  the check could not look (no database, no psql, no settings)
    FAILED           the check looked and found evidence against the claim

The database settings are the backend's own, read from its ``.env`` as data and
never sourced, so a password holding ``$(...)`` stays a password. A variable in
the environment overrides the file.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import reset_participant_exercises as _exercises  # noqa: E402  (sibling module)

REPO = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ENV = REPO / "pellier" / "backend" / ".env"

PASSED = "PASSED"
NOT_YET = "NOT YET PASSED"
COULD_NOT_CHECK = "COULD NOT CHECK"
FAILED = "FAILED"
STATES = (PASSED, NOT_YET, COULD_NOT_CHECK, FAILED)

_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
_REQUIRED = ("DB_HOST", "DB_NAME", "DB_USER")


def refuse_missing_lab_file(lab: int) -> bool:
    """Print the FILE MISSING line and return True when a file Lab ``lab`` reads is gone."""
    return _exercises.refuse_if_gap(lab, REPO)


@dataclass
class Finding:
    """One task's verdict, with the three things every check prints.

    Attributes:
        task: The task label, for example ``1B``.
        title: The claim, in a few plain words.
        state: One of :data:`STATES`.
        expected: What must be true for the claim to hold.
        observed: What the check saw.
        evidence: The rows, decisions or keys behind the observation.
        next_step: What to look at next; empty when the claim is proved.
        label: The word before ``task`` in the box; ``Task`` for the eight lab tasks.
    """

    task: str
    title: str
    state: str
    expected: str
    observed: str
    evidence: List[str] = field(default_factory=list)
    next_step: str = ""
    label: str = "Task"


# A laptop-size Code Editor terminal is about 124 columns wide; beside the guide it is narrower,
# so every box and table is sized to the terminal it prints in, never wider than WIDTH.
WIDTH = 120
_NARROWEST = 40
# A command a participant may copy stays on one line: from its first word to the next
# clause break or the end of the sentence.
_COMMAND = re.compile(r"\b(?:uv run|psql|python3|bash|sudo) .*?(?=, |; |\. |\.?$)")
# The narrowest a wrapped column may get before a table gives each row its own box.
_MIN_COLUMN = 8


# A command that relays a child's output to a person's terminal (lab_run.py finish and reset)
# tells the child how wide that terminal is: the child writes to a pipe and cannot measure it.
RELAYED_COLUMNS_ENV = "PELLIER_TERMINAL_COLUMNS"


def relayed_columns() -> Optional[int]:
    """The width of the terminal a parent command relays this output to, when it has said."""
    value = os.environ.get(RELAYED_COLUMNS_ENV, "")
    # isascii first: isdigit alone accepts characters such as a superscript two, which int refuses.
    return int(value) if value.isascii() and value.isdigit() and int(value) > 0 else None


def terminal_width() -> int:
    """The width to print at, in columns, at most WIDTH: the terminal's, or the one a relaying
    parent passed down; WIDTH when the output goes to neither."""
    columns = relayed_columns() or shutil.get_terminal_size((WIDTH + 1, 24)).columns
    return max(_NARROWEST, min(WIDTH, columns - 1))


def _lines(text: str, width: int) -> List[str]:
    """A cell's text wrapped to its column; a copyable command stays on one line."""
    kept = _COMMAND.sub(lambda match: match.group(0).replace(" ", "\0"), text)
    lines = textwrap.wrap(kept, width=width, break_long_words=False,
                          break_on_hyphens=False) or [""]
    return [line.replace("\0", " ") for line in lines]


def wrapped(prefix: str, text: str, width: Optional[int] = None) -> str:
    """``prefix`` then ``text``, broken at words to the terminal (or ``width``), with later
    lines indented under where the text starts. A word longer than the room, such as a key,
    stays whole, and so does a command a participant copies."""
    room = max(_NARROWEST, width or terminal_width()) - len(prefix)
    lines = _lines(text, max(room, _MIN_COLUMN))
    return "\n".join([prefix + lines[0]] + [" " * len(prefix) + line for line in lines[1:]])


def _longest_word(text: str) -> int:
    kept = _COMMAND.sub(lambda match: match.group(0).replace(" ", "\0"), text)
    return max((len(word) for word in kept.split()), default=0)


def _fit(widths: Sequence[int], floors: Sequence[int], room: int) -> Optional[List[int]]:
    """Narrow the widest columns until the bordered rows fit ``room``; None when they cannot."""
    widths = list(widths)
    while sum(widths) + 3 * len(widths) + 1 > room:
        index = max(range(len(widths)), key=lambda i: widths[i] - floors[i])
        if widths[index] <= floors[index]:
            return None
        widths[index] -= 1
    return widths


def _grid(rows: Sequence[Sequence[str]], widths: Sequence[int], rules: Iterable[int],
          align: Sequence[str]) -> str:
    """Rows of cells inside box-drawing borders, with a rule after each row in ``rules``."""
    rules = set(rules)

    def border(left: str, middle: str, right: str) -> str:
        return left + middle.join("\u2500" * (width + 2) for width in widths) + right

    out = [border("\u250c", "\u252c", "\u2510")]
    for number, row in enumerate(rows):
        cells = [_lines(value, widths[i]) for i, value in enumerate(row)]
        for depth in range(max(len(cell) for cell in cells)):
            parts = [f"{(cell[depth] if depth < len(cell) else ''):{align[i]}{widths[i]}}"
                     for i, cell in enumerate(cells)]
            out.append("\u2502 " + " \u2502 ".join(parts) + " \u2502")
        if number in rules:
            out.append(border("\u251c", "\u253c", "\u2524"))
    out.append(border("\u2514", "\u2534", "\u2518"))
    return "\n".join(out)


def _pairs(rows: Sequence[Sequence[str]], separators: Iterable[int], room: int) -> str:
    """Label and value rows in a two-column box, the value wrapped to whatever room is left."""
    label = max(len(row[0]) for row in rows)
    floor = max(_MIN_COLUMN, max(_longest_word(row[1]) for row in rows))
    value = max(len(row[1]) for row in rows)
    widths = _fit([label, value], [label, floor], room) or [label, floor]
    return _grid(rows, widths, separators, "<<")


def table(header: Sequence[str], rows: Sequence[Sequence[Any]],
          align: Optional[Sequence[str]] = None, width: Optional[int] = None) -> str:
    """A bordered table that fits the terminal: wide cells wrap, and when even that is too
    wide, each row gets its own box of header and value, as psql's expanded display does.

    Args:
        header: The column names.
        rows: The cells, one sequence per row.
        align: ``<`` or ``>`` per column; left-aligned when omitted.
        width: The columns available; the terminal's width when omitted.
    """
    cells = [[str(value) for value in header]] + [[str(value) for value in row] for row in rows]
    room = width or terminal_width()
    align = align or ["<"] * len(header)
    natural = [max(len(row[i]) for row in cells) for i in range(len(header))]
    floors = [max(min(natural[i], _MIN_COLUMN), max(_longest_word(row[i]) for row in cells))
              for i in range(len(header))]
    widths = _fit(natural, floors, room)
    if widths:
        return _grid(cells, widths, {0}, align)
    records = [[name, value] for row in cells[1:] for name, value in zip(cells[0], row)]
    ends = {len(header) * (n + 1) - 1 for n in range(len(cells) - 2)}
    return _pairs(records, ends, room)


# Green is good, red is bad and orange is waiting or not yet, on a terminal only: a pipe, a file
# and NO_COLOR get the same words without the escape codes, so nothing that reads the output
# has to strip them. Only a state word, a status label or one verdict line is painted.
_GREEN, _RED, _ORANGE = "\033[32m", "\033[31m", "\033[38;5;208m"
_COLOURS = {PASSED: _GREEN, FAILED: _RED, NOT_YET: _ORANGE, COULD_NOT_CHECK: _ORANGE}
_COLOUR_OFF = "\033[0m"
_COLOUR_CODE = re.compile(r"\033\[[0-9;]*m")


# The palette beyond the verdict colours, one meaning each: something to run, a detail that is
# not the point, Pellier at work, and where a turn ran: the local agents or AgentCore.
COMMAND_COLOUR, DETAIL_COLOUR, BRAND_COLOUR = "\033[1m", "\033[2m", "\033[38;5;173m"
LOCAL_COLOUR, AGENTCORE_COLOUR = "\033[38;5;183m", "\033[38;5;75m"
# Pellier's reply in pure white, above the terminal's grey default: the words the shopper reads.
ANSWER_COLOUR = "\033[38;5;231m"


def tint(text: str, colour: str, stream: Any = None) -> str:
    """``text`` in ``colour`` on a terminal that takes colour; unchanged otherwise."""
    return f"{colour}{text}{_COLOUR_OFF}" if colour_enabled(stream) else text


def colour_enabled(stream: Any = None) -> bool:
    """Whether ``stream`` (stdout when omitted) is a terminal that should get colour."""
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    return _is_terminal(sys.stdout if stream is None else stream)


def _is_terminal(stream: Any) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)())


def relay_environment(stream: Any = None) -> Dict[str, str]:
    """The environment for a child whose output this command relays: its own, plus the
    terminal's width when ``stream`` (stdout when omitted) is a terminal."""
    env = dict(os.environ)
    if _is_terminal(sys.stdout if stream is None else stream):
        env[RELAYED_COLUMNS_ENV] = str(shutil.get_terminal_size().columns)
    return env


def paint(text: str, state: str, stream: Any = None) -> str:
    """``text`` in the colour of ``state`` when the stream takes colour; unchanged otherwise."""
    colour = _COLOURS.get(state)
    if not colour or not colour_enabled(stream):
        return text
    return f"{colour}{text}{_COLOUR_OFF}"


def overall(states: Iterable[str]) -> str:
    """One state for several findings: FAILED when any failed, PASSED when all passed, and
    NOT_YET otherwise. Work that is only unfinished is not a failure and is not painted as one."""
    found = list(states)
    if FAILED in found:
        return FAILED
    return PASSED if all(state == PASSED for state in found) else NOT_YET


def plain(text: str) -> str:
    """``text`` without colour codes: what a saved file keeps of a report painted for a terminal."""
    return _COLOUR_CODE.sub("", text)


# What a participant does after a task's check passes: a few words, then each command whole on
# its own line so it copies as one command. The guide's steps follow the same order.
_DEPLOY = 'uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant'
# Task 1A's pass line is its last line; the guide's Next button leads on to Task 1B.
NEXT_AFTER_PASS: Dict[str, List[str]] = {
    "1B": ['In the guide, open Lab 2 and read "Send Marco\'s question" in Task 2A.',
           "uv run scripts/lab_run.py send --lab 2 --task 2A"],
    "2A": ['In the guide, open Task 2B and read "Ask about a product Pellier does not carry".',
           "uv run scripts/lab_run.py send --lab 2 --task 2B"],
    "2B": ['In the guide, open Task 2B and read "Prove the fix", step 2. Then continue to '
           '"From local agents to Amazon Bedrock AgentCore".',
           "uv run scripts/lab_run.py send --lab 2 --task 2B"],
    "3A": ['In the guide, open Task 3B and read "Start the deploy".', _DEPLOY],
    "3B": ['In the guide, open Lab 4, Task 4A and read "Send Jessica\'s request".',
           "uv run scripts/lab_run.py send --lab 4 --shopper-only"],
    "4A": ['In the guide, open "Pay the credit once and check the records" and read '
           '"Prove one credit was written".',
           "psql -f workshop/lab-4-absence.sql"],
    "4B": ['In the guide, open "Pay the credit once and check the records" and read '
           '"Execute again and replay as Nadia". Then check the deployed rule.',
           "uv run scripts/lab4_check.py --task 4A"],
}


# A catch-up (lab_run.py finish, fast-track) runs each next step itself and sets this for the
# commands it runs, so they do not tell the participant to do what is already under way.
NO_NEXT_ENV = "PELLIER_NO_NEXT"


def says_next() -> bool:
    """False inside a catch-up, which runs the next step itself."""
    return not os.environ.get(NO_NEXT_ENV)


def next_lines(steps: Sequence[str], width: Optional[int] = None) -> str:
    """``Next`` and what to read in the guide, then each command indented under it.

    The first step names the guide page to read; each later step is a command, printed whole
    on its own line after ``Then run:`` so it copies as one command. The sentence wraps at
    word breaks to ``width`` (the terminal's when omitted).
    """
    if not steps:
        return ""
    first, *commands = steps
    room = max(_NARROWEST, width or terminal_width()) - len("Next  ")
    told = textwrap.wrap(first, width=room, break_long_words=False, break_on_hyphens=False)
    lines = [f"Next  {told[0]}"] + [f"      {line}" for line in told[1:]]
    return "\n".join(lines + [f"      Then run: {tint(command, COMMAND_COLOUR)}"
                              for command in commands])


def closing(label: str, passed: bool, task: str = "") -> str:
    """A check's last lines: ``<label> passed`` in green or ``<label> failed`` in red, and
    after a pass, what to do next when ``task`` names one of the eight tasks."""
    line = paint(f"{label} {'passed' if passed else 'failed'}", PASSED if passed else FAILED)
    following = next_lines(NEXT_AFTER_PASS.get(task, [])) if passed and says_next() else ""
    # A blank line sets the next step apart from the verdict above it.
    return f"{line}\n\n{following}" if following else line


def render(finding: Finding) -> str:
    """The finding as one bordered box sized to the terminal: the task and its state, then
    each field on its own row. The state word is green, red or orange on a terminal."""
    rows = [[f"{finding.label} {finding.task}", f"{finding.state}  {finding.title}"],
            ["Expected", finding.expected], ["Observed", finding.observed]]
    for index, line in enumerate(finding.evidence or ["(none)"]):
        rows.append(["Evidence" if index == 0 else "", line])
    if finding.state != PASSED and finding.next_step:
        rows.append(["Next", finding.next_step])
    box = _pairs(rows, {0}, terminal_width())
    # Painted after the box is laid out, so the escape codes never count as columns.
    return box.replace(f" {finding.state}  ", f" {paint(finding.state, finding.state)}  ", 1)


# ---------------------------------------------------------------------------
# The compact view: what the live checks print. render() above stays the full box that the
# take-home export and --details print.
# ---------------------------------------------------------------------------
DETAILS_FLAG = "--details"
TICK, CROSS, UNKNOWN = "\u2713", "\u2717", "?"
_LABEL_MAX = 44


@dataclass
class Rule:
    """One thing a check tested, in plain words.

    Attributes:
        label: The rule, for example ``Request names Jessica``.
        result: What happened, for example ``sent as CUST-THEO``.
        ok: True passed, False failed, None could not be checked.
        expected: A failing rule's expectation, in a few words.
        observed: What the check saw instead.
        next_step: The diagnosis for this run: at most two short lines, newline-separated.
        notes: Lines printed under a passed rule, for example the preferences Memory held.
        status: A short status word between the label and the result, as the Operator's
            credit card shows ``Policy   DENY   The Gateway answered: denied.``
    """

    label: str
    result: str = ""
    ok: Optional[bool] = True
    expected: str = ""
    observed: str = ""
    next_step: str = ""
    notes: List[str] = field(default_factory=list)
    status: str = ""


@dataclass
class MatrixRow:
    """One tested rule of a :class:`Matrix`, with what each path did.

    Attributes:
        label: The rule in plain words.
        cells: One ``(ok, text)`` per column; ``ok`` is None where the path could not be read.
        expected: What a failing cell should have said.
        next_step: The diagnosis printed under the table when a cell fails.
    """

    label: str
    cells: List[Any]
    expected: str = ""
    next_step: str = ""


@dataclass
class Matrix:
    """The same rules proved on several paths: one table, one column per path."""

    columns: List[str]
    rows: List[MatrixRow]
    first: str = "Test"


@dataclass
class Verdict(Finding):
    """A :class:`Finding` that also carries the compact view's headline and rules.

    :func:`render` ignores the extra fields, so the export and ``--details`` print what they
    always printed.
    """

    headline: str = ""
    intro: str = ""
    rules: List[Rule] = field(default_factory=list)
    matrix: Optional[Matrix] = None
    data: Dict[str, Any] = field(default_factory=dict)
    # A pass told in a few plain sentences instead of a headline and ticks (Lab 1's checks).
    summary: List[str] = field(default_factory=list)


def with_rules(finding: Finding, headline: str, rules: Sequence[Rule],
               intro: str = "") -> Verdict:
    """``finding`` with the compact view's headline, optional first-visit sentence and rules."""
    return Verdict(task=finding.task, title=finding.title, state=finding.state,
                   expected=finding.expected, observed=finding.observed,
                   evidence=list(finding.evidence), next_step=finding.next_step,
                   label=finding.label, headline=headline, intro=intro, rules=list(rules))


def combine(task: str, headline: str, findings: Sequence[Finding], intro: str = "",
            label: str = "Task", matrix: Optional[Matrix] = None,
            covered: Sequence[Finding] = ()) -> Verdict:
    """One verdict for several findings: each finding's rules, or one rule made from the
    finding when it has none, under one headline. The state is the worst of theirs.

    ``covered`` are findings a ``matrix`` already shows cell by cell: their state counts, but
    they add no rules of their own.
    """
    rules: List[Rule] = []
    everyone = [*findings, *covered]
    for finding in findings:
        mine = list(getattr(finding, "rules", []) or [])
        if finding.state == PASSED:
            rules += mine or [Rule(finding.title, finding.observed)]
            continue
        bad = [rule for rule in mine if rule.ok is not True]
        rules += bad or [Rule(finding.title, ok=None if finding.state == COULD_NOT_CHECK
                              else False, expected=finding.expected,
                              observed=finding.observed, next_step=finding.next_step)]
    state = overall(finding.state for finding in everyone)
    if COULD_NOT_CHECK in {finding.state for finding in everyone} and state != FAILED:
        state = COULD_NOT_CHECK
    first = everyone[0].title if everyone else ""
    return Verdict(task=task, title=first, state=state, expected="", observed="",
                   evidence=[], label=label, headline=headline, intro=intro, rules=rules,
                   matrix=matrix)


def details_requested(argv: Optional[Sequence[str]]) -> bool:
    """True when ``--details`` is among ``argv``: the one switch that prints the full box."""
    return DETAILS_FLAG in (sys.argv[1:] if argv is None else argv)


def _mark(rule: Rule) -> str:
    if rule.ok is None:
        return paint(UNKNOWN, NOT_YET)
    return paint(TICK, PASSED) if rule.ok else paint(CROSS, FAILED)


def _tick_lines(rules: Sequence[Rule], width: int) -> List[str]:
    """Passed rules, label and result in two columns when they fit."""
    label = min(max((len(rule.label) for rule in rules), default=0), _LABEL_MAX)
    status = max((len(rule.status) for rule in rules), default=0)
    lines: List[str] = []
    for rule in rules:
        mark = f"  {_mark(rule)}  "
        if rule.status:
            rule = Rule(rule.label, f"{rule.status:<{status}}   {rule.result}".rstrip(),
                        rule.ok, notes=rule.notes)
        room = width - 5 - label - 3
        if len(rule.label) > label or room < _MIN_COLUMN * 2:
            text = wrapped("", f"{rule.label}   {rule.result}".rstrip(), width - 5)
            body = text.splitlines()
        else:
            told = _lines(rule.result, room) if rule.result else [""]
            body = [f"{rule.label:<{label}}   {told[0]}".rstrip()]
            body += [f"{'':<{label}}   {line}" for line in told[1:]]
        lines.append(mark + body[0])
        lines += [" " * 5 + line for line in body[1:]]
        lines += [" " * 7 + note for note in rule.notes]
    return lines


def _failure_lines(rule: Rule, width: int) -> List[str]:
    lines = [f"  {_mark(rule)}  " + rule.label]
    for word, text in (("Expected", rule.expected), ("Observed", rule.observed)):
        if text:
            lines.append(wrapped(f"       {word:<9}", text, width))
    steps = [line for line in rule.next_step.splitlines() if line.strip()]
    for index, step in enumerate(steps):
        lines.append(wrapped(f"       {'Next' if index == 0 else '':<9}", step, width))
    return lines


def _cell_text(ok: Optional[bool], text: str) -> str:
    return text if ok is not False else f"{text} {CROSS}"


def _matrix_mark(row: MatrixRow) -> str:
    oks = [cell[0] for cell in row.cells]
    if any(ok is False for ok in oks):
        return paint(CROSS, FAILED)
    return paint(UNKNOWN, NOT_YET) if any(ok is None for ok in oks) else paint(TICK, PASSED)


def render_matrix(matrix: Matrix) -> str:
    """One table, a column per path: each rule's mark and label, then what each path did."""
    texts = [[_cell_text(*cell) for cell in row.cells] for row in matrix.rows]
    first = max([len(matrix.first), *(len(row.label) for row in matrix.rows)]) + 4
    widths = [max([len(name), *(len(line[i]) for line in texts)])
              for i, name in enumerate(matrix.columns)]
    gap = "   "
    head = f"  {matrix.first:<{first}}" + gap.join(
        f"{name:<{widths[i]}}" for i, name in enumerate(matrix.columns))
    lines = [head.rstrip()]
    for row, cells in zip(matrix.rows, texts):
        lines.append((f"  {_matrix_mark(row)} {row.label:<{first - 2}}" + gap.join(
            f"{cell:<{widths[i]}}" for i, cell in enumerate(cells))).rstrip())
    return "\n".join(lines)


def _matrix_failures(matrix: Matrix, width: int) -> List[str]:
    """Under the table: what each failing rule expected, what a path did and what to do next."""
    lines: List[str] = []
    for row in matrix.rows:
        seen = [(matrix.columns[i], cell[1]) for i, cell in enumerate(row.cells)
                if cell[0] is False]
        if not seen:
            continue
        lines.append(f"  {paint(CROSS, FAILED)}  {row.label}")
        if row.expected:
            lines.append(wrapped(f"       {'Expected':<9}", row.expected, width))
        lines.append(wrapped(f"       {'Observed':<9}",
                             "; ".join(f"{name}: {text}" for name, text in seen), width))
        for index, step in enumerate(line for line in row.next_step.splitlines() if line.strip()):
            lines.append(wrapped(f"       {'Next' if index == 0 else '':<9}", step, width))
        lines.append("")
    return lines[:-1]


def render_rules(verdict: Verdict, width: Optional[int] = None) -> str:
    """The PASS view: a headline, an optional one-time explanation, then one line per rule."""
    room = width or terminal_width()
    if verdict.summary:
        return "\n".join(_summary_lines(verdict, room))
    body = [wrapped("", verdict.headline, room)] if verdict.headline else []
    if verdict.intro:
        body += ["", wrapped("", verdict.intro, room)]
    rules = verdict.rules or ([] if verdict.matrix else [Rule(verdict.title, verdict.observed)])
    lines = body + [""] + _tick_lines(rules, room)
    if verdict.matrix:
        lines += ["", render_matrix(verdict.matrix)]
    return "\n".join(lines)


def _summary_lines(verdict: Verdict, room: int) -> List[str]:
    """A verdict's summary lines, each as written when it fits, so a table keeps its columns."""
    return [line if len(line) <= room else wrapped("", line, room) for line in verdict.summary]


def render_failures(verdict: Verdict, width: Optional[int] = None) -> str:
    """The FAIL view: only the rules that did not pass, each with Expected, Observed and Next.

    A verdict with no failing rule of its own prints one rule made from the finding, so a
    check that could not look or has no evidence yet still says what it expected and saw.
    """
    room = width or terminal_width()
    bad = [rule for rule in verdict.rules if rule.ok is not True]
    table = verdict.matrix
    broken = table is not None and any(cell[0] is not True for row in table.rows
                                       for cell in row.cells)
    if table is not None and broken:
        lines = [render_matrix(table), ""]
        for rule in bad:
            lines += _failure_lines(rule, room) + [""]
        return "\n".join(lines + _matrix_failures(table, room))
    if not bad:
        mark_ok = None if verdict.state == COULD_NOT_CHECK else False
        bad = [Rule(verdict.title, ok=mark_ok, expected=verdict.expected,
                    observed=verdict.observed, next_step=verdict.next_step)]
    # A summary that holds on a failure too, such as Lab 1A's reference lookup, comes first.
    lines: List[str] = _summary_lines(verdict, room) + [""] if verdict.summary else []
    for rule in bad:
        lines += _failure_lines(rule, room) + [""]
    return "\n".join(lines[:-1])


def compact(finding: Finding, width: Optional[int] = None) -> str:
    """The compact view of a finding: ticks when it passed, only what failed when it did not."""
    verdict = finding if isinstance(finding, Verdict) else with_rules(finding, "", [])
    if finding.state == PASSED:
        return render_rules(verdict, width)
    return render_failures(verdict, width)


def report(finding: Finding, argv: Optional[Sequence[str]] = None,
           width: Optional[int] = None) -> str:
    """What a live check prints for ``finding``: the compact view, or the full box with
    ``--details`` among ``argv``."""
    return render(finding) if details_requested(argv) else compact(finding, width)


def emit(finding: Finding, argv: Optional[Sequence[str]], label: str, task: str = "",
         tables: Sequence[str] = (), boxes: Optional[Sequence[Finding]] = None,
         closing_line: str = "", after: Sequence[str] = ()) -> bool:
    """Print a live check's result and its closing line; True when it passed.

    The compact view comes first. With ``--details`` among ``argv`` the ``tables`` the check
    built and the full box print instead, as they did before the compact view existed.
    ``boxes`` are the findings behind a combined verdict; ``closing_line`` replaces the
    pass or fail line when a check has a third ending of its own. ``after`` prints right
    under a pass line, before the next step.
    """
    passed = finding.state == PASSED
    if details_requested(argv):
        print("\n".join([*tables, *(render(box) for box in (boxes or [finding]))]))
    else:
        print(compact(finding))
    print()
    if passed and task and says_next() and not details_requested(argv):
        import pellier_map  # imported here: pellier_map reads this module

        extras = pellier_map.passed_extras(task)
        if extras:
            print("\n".join(extras))
    shown_after = passed and bool(after)
    print(closing_line or closing(label, passed, "" if shown_after else task))
    if shown_after:
        print("\n".join(after))
        following = next_lines(NEXT_AFTER_PASS.get(task, [])) if says_next() else ""
        if following:
            print(f"\n{following}")
    if passed and task and says_next():
        import pellier_map

        line = pellier_map.arc(task)
        if line:
            print(f"\n{line}")
    return passed


def parse_dotenv(env_path: pathlib.Path) -> Dict[str, str]:
    """Read KEY=value lines from a dotenv file without shell interpolation."""
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            values[key] = value.strip().strip('"').strip("'")
    return values


def db_config(env_path: pathlib.Path = DEFAULT_ENV) -> Optional[Dict[str, str]]:
    """The database settings, or None when the host, name or user is missing.

    The password may be empty: a local cluster can trust its socket, and a box
    can keep it in ``~/.pgpass``.
    """
    cfg = parse_dotenv(env_path)
    for key in _KEYS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    if not all(cfg.get(key) for key in _REQUIRED):
        return None
    return cfg


def missing_settings_reason(env_path: pathlib.Path = DEFAULT_ENV) -> str:
    """The sentence a check prints when :func:`db_config` found nothing."""
    return f"no database settings ({', '.join(_REQUIRED)}) in {env_path} or the environment"


def connect(cfg: Dict[str, str], *, timeout: int = 15) -> Any:
    """Open one dict-row connection to the database ``cfg`` names.

    Raises:
        RuntimeError: psycopg is not installed for this interpreter.
        psycopg.Error: the database refused or could not be reached.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is not installed for this Python") from exc
    return psycopg.connect(
        host=cfg["DB_HOST"],
        port=int(cfg.get("DB_PORT") or 5432),
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg.get("DB_PASSWORD") or None,
        connect_timeout=timeout,
        row_factory=dict_row,
    )


def psql_environment(cfg: Dict[str, str]) -> Dict[str, str]:
    """The environment that points ``psql`` at the same database."""
    env = dict(os.environ)
    env.update(
        PGHOST=cfg["DB_HOST"],
        PGPORT=str(cfg.get("DB_PORT") or 5432),
        PGDATABASE=cfg["DB_NAME"],
        PGUSER=cfg["DB_USER"],
    )
    if cfg.get("DB_PASSWORD"):
        env["PGPASSWORD"] = cfg["DB_PASSWORD"]
    return env


# ---------------------------------------------------------------------------
# Reset points: evidence from before a lab was reset no longer counts
# ---------------------------------------------------------------------------
# tool_audit and retrieval_receipts are append-only, so a reset cannot delete the turns a
# lab left behind. `uv run scripts/lab_run.py reset --lab N` instead records the
# database's own clock in a small file, and each lab's checks read only the evidence
# created at or after it. The file lives under .local/, which a repair never touches and
# the full reset removes (it empties the tables anyway).
RESET_POINTS_ENV = "PELLIER_LAB_RESET_POINTS"
RESET_POINTS_FILE = REPO / ".local" / "lab-reset-points.json"
# Bind this as ``since``: no reset point (None) admits every row.
SINCE_SQL = "coalesce(%(since)s::timestamptz, '-infinity'::timestamptz)"


@dataclass(frozen=True)
class Timeline:
    """When a task's file last changed and when the backend last started; None if unknown."""

    edited_at: Optional[datetime]
    started_at: Optional[datetime]


def service_started(value: str) -> Optional[datetime]:
    """systemd's ActiveEnterTimestamp (``Wed 2026-10-14 14:46:19.479163 UTC``, or without the
    microseconds) as UTC; None otherwise."""
    if not value.endswith((" UTC", " GMT")):
        return None
    shape = "%a %Y-%m-%d %H:%M:%S.%f" if "." in value else "%a %Y-%m-%d %H:%M:%S"
    try:
        return datetime.strptime(value[:-4], shape).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def service_start_time() -> Optional[datetime]:
    """When systemd last started pellier, in UTC; None without systemd or a started service."""
    # Microseconds: the solution command writes the file and restarts within one second, and
    # whole seconds would date that restart before the edit.
    try:
        shown = subprocess.run(
            ["systemctl", "show", "pellier", "-p", "ActiveEnterTimestamp", "--value",
             "--timestamp=us+utc"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        shown = ""
    return service_started(shown)


def edit_timeline(edited_file: pathlib.Path) -> Timeline:
    """This box's timeline: the task file's modification time and pellier's systemd start."""
    try:
        edited: Optional[datetime] = datetime.fromtimestamp(edited_file.stat().st_mtime,
                                                            tz=timezone.utc)
    except OSError:
        edited = None
    return Timeline(edited, service_start_time())


def clock(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%H:%M:%S UTC")


def reset_points_path() -> pathlib.Path:
    """Where the reset points live; the environment overrides it for tests."""
    override = os.environ.get(RESET_POINTS_ENV)
    return pathlib.Path(override) if override else RESET_POINTS_FILE


def lab2_shirt_turn_path() -> pathlib.Path:
    """The terminal turn to inspect for Marco's Brooklyn question."""
    return reset_points_path().with_name("lab-2a-turn.json")


def lab1_retry_turn_path() -> pathlib.Path:
    """The terminal turn to inspect for Anna's full request (Task 1B). The receipt SQL reads
    it as ``.local/lab-1b-turn.json`` from the repository root, where the guide runs psql."""
    return reset_points_path().with_name("lab-1b-turn.json")


def _read_points(path: pathlib.Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def reset_point(lab: int) -> Optional[datetime]:
    """When the lab was last reset (timezone-aware), or None if it never was."""
    raw = _read_points(reset_points_path()).get(str(lab))
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def record_reset_point(lab: int, moment: datetime) -> None:
    """Remember that the lab was reset at ``moment``, keeping the other labs' points."""
    path = reset_points_path()
    points = _read_points(path)
    points[str(lab)] = moment.astimezone(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(points, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clear_reset_points() -> None:
    """Forget every reset point, as a full reset does when it empties the tables."""
    reset_points_path().unlink(missing_ok=True)


def since_note(lab: int, send_again: str) -> str:
    """The sentence a NOT YET PASSED finding adds when the lab was reset, else an empty string."""
    moment = reset_point(lab)
    if moment is None:
        return ""
    clock = moment.strftime("%H:%M:%S UTC")
    return (f" You reset Lab {lab} at {clock}, so turns from before that no longer count: "
            f"send the requests again since your reset ({send_again}).")


def region_body(text: str, label: str) -> Optional[str]:
    """The lines between one ``WORKSHOP - <label>`` marker pair, or None without one.

    Works for both comment styles the starters use (``#`` and ``--``).
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if f"WORKSHOP - {label}: START ===" in line]
    ends = [i for i, line in enumerate(lines) if f"WORKSHOP - {label}: END ===" in line]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        return None
    return "\n".join(lines[starts[0] + 1:ends[0]]).rstrip()


STARTER = "starter"
EDITED = "edited"
MISSING = "missing"


def region_state(path: pathlib.Path, label: str, starter: pathlib.Path) -> str:
    """Whether a marked region still holds the starter, was edited, or is gone.

    ``starter`` is either the starter fragment itself or a whole starter file
    carrying the same markers.
    """
    try:
        body = region_body(path.read_text(encoding="utf-8"), label)
        starter_text = starter.read_text(encoding="utf-8")
    except OSError:
        return MISSING
    if body is None:
        return MISSING
    expected = region_body(starter_text, label)
    if expected is None:
        expected = starter_text.rstrip()
    return STARTER if body == expected else EDITED


def counted(count: int, noun: str) -> str:
    """A count with its noun in the right number: "1 tool_audit row", "2 tool_audit rows"."""
    return f"{count} {noun}" + ("" if count == 1 else "s")


def short(value: Any, width: int = 12) -> str:
    """A long identifier cut to a readable prefix."""
    text = str(value or "")
    return text if len(text) <= width + 3 else text[:width] + "..."
