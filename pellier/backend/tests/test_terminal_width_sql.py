"""The lab SQL files and the Cedar file must read in an 85-column terminal.

Participants run ``psql -f <file>`` in Code Editor's terminal on a laptop: about 85
columns on a 1280-pixel window at 150% scaling. A longer line breaks mid-word, so every
``\\echo`` prints at most 84 columns. A result table that is too wide switches by itself to
psql's record layout, one field per line; only the files named in WRAPPED_FILES ask for the
wrapped format.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAX_COLUMNS = 84
SQL_FILES = sorted(
    [*ROOT.glob("workshop/*.sql"), *ROOT.glob("workshop/starters/*.sql"),
     *ROOT.glob("solutions/*/sql/*.sql")])
CEDAR_FILES = (ROOT / "policies" / "credit_limit.cedar",
               ROOT / "solutions" / "lab-4-govern" / "policies" / "credit_limit.cedar")

# Allowance for a ``:name`` psql variable, in printed columns. A key is at most 50
# characters and a count a few digits. A variable that holds a line the file builds
# itself gets the width of its longest case, set in VARIABLE_COLUMNS.
KEY_COLUMNS = 50
COUNT_COLUMNS = 6
VARIABLE_COLUMNS = {
    "stamp_short": 12,                # left(sha256, 12)
    "lab_1_session": 40,              # a 36-character session id, or "none"
    "lab_1_query": 72,                # left(query_preview, 72), printed in quotes
    "lab_1_scope": 31,              # "Photographed storefront subset"
    "lab_1_line_1": 73,               # format(...) with a 6-digit product count
    "lab_1_line_2": 56,
    "lab_1_line_3": 56,
    "lab_1_line_3b": 30,              # "the exact 20 in the same order"
    "lab_1_line_4": 74,               # 2-digit row counts, recall at most "100.0"
    "lab_3_login": 40,
    "lab_3_state": 52,                # "installed but not loaded (shared_preload_libraries)"
    "lab_3_agent_summary": 56,        # "distinct statements N, calls N, rows N", 6-digit counts
    "lab_3_writer_summary": 56,
    "lab_3_tools_summary": 56,
    "lab_3_login_summary": 56,
    "lab_4_attempts": 56,             # "999 other attempts for the allowed key did not apply;"
    "lab_4_kept": 4,                  # "it" or "them"
    "lab_4_observed": 30,             # four counts joined as "N, N, N and N"
    "credits_rows": 46,               # "store_credits rows before N, after N", 6-digit counts
    "owner_names": 48,                # "jessica -> CUST-JESSICA, theo -> CUST-THEO"
    "wrap_attempts": 56,
    "wrap_kept": 4,                   # "it" or "them"
    "wrap_missing": 64,               # the longest reason, with a 6-digit count
}
COUNT_SUFFIXES = ("_matched", "_probes", "_products", "_one_list", "_receipt", "_eligible",
                  "_total_products", "_photographed_products", "_tool_reads", "_probe")
KEY_SUFFIXES = ("_key",)

TOKEN = re.compile(r"'((?:[^']|'')*)'|:'(\w+)'|:(\w+)|(\s+)")


def variable_columns(name: str, constants: dict[str, int]) -> int:
    """Return the most columns the value of psql variable ``name`` can print."""
    if name in constants:
        return constants[name]
    if name in VARIABLE_COLUMNS:
        return VARIABLE_COLUMNS[name]
    if name.endswith(KEY_SUFFIXES):
        return KEY_COLUMNS
    if name.endswith(COUNT_SUFFIXES):
        return COUNT_COLUMNS
    raise AssertionError(f"no width allowance for the psql variable :{name}; add one")


def printed_columns(arguments: str, constants: dict[str, int]) -> int:
    """Width of what ``\\echo <arguments>`` prints: psql joins arguments with a space."""
    width, position, pending_space = 0, 0, False
    while position < len(arguments):
        match = TOKEN.match(arguments, position)
        assert match, f"cannot read the \\echo arguments at {arguments[position:]!r}"
        position = match.end()
        if match.group(4):
            pending_space = True
            continue
        if pending_space and width > 0:
            width += 1
        pending_space = False
        if match.group(2):
            # :'name' prints the value as a quoted literal: two more columns for the quotes.
            width += variable_columns(match.group(2), constants) + 2
        elif match.group(3):
            width += variable_columns(match.group(3), constants)
        else:
            width += len(match.group(1).replace("''", "'"))
    return width


def file_constants(path: Path) -> dict[str, int]:
    """Widths of the variables the file sets itself with ``\\set name 'literal'``."""
    found = re.findall(r"^\\set (\w+) '((?:[^']|'')*)'\s*$", path.read_text(), re.MULTILINE)
    return {name: len(value.replace("''", "'")) for name, value in found}


def echo_lines(path: Path) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("\\echo ") and "`" not in stripped:
            found.append((number, stripped[len("\\echo "):]))
    return found


def test_the_three_folders_hold_sql_files() -> None:
    assert len(SQL_FILES) >= 15


def test_every_echo_prints_at_most_84_columns() -> None:
    too_wide = []
    for path in SQL_FILES:
        constants = file_constants(path)
        for number, arguments in echo_lines(path):
            columns = printed_columns(arguments, constants)
            if columns > MAX_COLUMNS:
                too_wide.append(f"{path.relative_to(ROOT)}:{number} prints {columns}")
    assert not too_wide, "\\echo lines wider than 84 columns:\n" + "\n".join(too_wide)


def test_the_workload_tables_fit_the_terminal() -> None:
    text = (ROOT / "workshop" / "lab-3-agent-workload.sql").read_text()
    shown = [int(n) for n in re.findall(r"left\(s\.statement, (\d+)\)", text)]
    assert len(shown) == 4, "each statement table shows a shortened statement"
    # Widest row: 7-digit counts, a 7-character mean, and the table's separators.
    # psql's wrapped format breaks the widest cell to the terminal, so the table needs only
    # the shortened statement to be bounded; the 100-column bound is the cap before wrapping.
    assert all(7 + 7 + 7 + 9 + width <= 99 for width in shown)


def _header(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    return lines[: lines.index("forbid(")]


@pytest.mark.parametrize("path", CEDAR_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_cedar_header_is_true_in_both_states(path: Path) -> None:
    lines = path.read_text().splitlines()
    assert lines[18] == "forbid(", "forbid( stays on line 19"
    assert "give_store_credit" in lines[20]
    assert lines[23] == "unless {"
    assert "as written" not in "\n".join(lines[:18])
    assert all(line.startswith("//") for line in lines[:18])
    prose = [line for line in lines[:18] if not line.startswith("//   ")]
    assert all(len(line) <= 80 for line in prose)


def test_the_two_cedar_headers_are_identical() -> None:
    first, second = (_header(path) for path in CEDAR_FILES)
    assert first == second


def test_a_query_plan_is_printed_in_the_wrapped_format() -> None:
    """EXPLAIN prints each plan line as long as it is, and one column never switches to the
    record layout, so a plan ran 102 columns wide in a 100-column terminal. psql's wrapped
    format breaks a long cell to the terminal's width and leaves narrower tables alone."""
    seen = 0
    for path in sorted(ROOT.glob("workshop/*.sql")):
        layout = "aligned"
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            found = re.search(r"\\pset\s+format\s+(\w+)", line)
            if found:
                layout = found.group(1)
            if line.lstrip().startswith("EXPLAIN"):
                seen += 1
                assert layout == "wrapped", f"{path.name}:{number} prints a plan as {layout}"
    assert seen >= 5


# psql's wrapped format fits a too-wide table by cutting cells mid-word, and it stops psql
# from switching that table to the record layout, one field per line, which is what keeps the
# labs' test tables readable on a laptop. So only the files that need it set it: the two that
# print query plans (one column, which never switches to records) and the receipt, a single
# record whose JSON values can run past a narrow terminal.
WRAPPED_FILES = {"lab-1-index.sql", "lab-3-agent-workload.sql", "lab-1-receipt.sql"}


def test_only_the_files_that_need_it_set_the_wrapped_format() -> None:
    found = {path.name for path in SQL_FILES if "\\pset format wrapped" in path.read_text()}
    assert found == WRAPPED_FILES


def test_the_receipts_constraints_print_compact() -> None:
    """With JSON's spaces the record of the lab's own request is 89 columns wide; psql then
    cut the values mid-number on an 85-column terminal. Without them it is 84. Anna's lab
    request names no category; a receipt that names one is wider and psql continues it."""
    text = (ROOT / "workshop" / "lab-1-receipt.sql").read_text()
    compact = "'\": ', '\":'), ', \"', ',\"')"
    assert text.count(compact) == 2
    for the_labs_own in ('{"categories":[],"in_stock_only":true,"price_max_usd":100.0}',
                         '{"categories":[],"in_stock_only":false,"price_max_usd":null}'):
        assert 2 + len("asked_constraints") + 3 + len(the_labs_own) + 2 <= MAX_COLUMNS


def test_the_index_definition_and_its_options_print_as_two_fields() -> None:
    """As one field the definition made Lab 1's meaning record 87 columns wide."""
    text = (ROOT / "workshop" / "lab-1-meaning.sql").read_text()
    assert " AS definition," in text and " AS options" in text
