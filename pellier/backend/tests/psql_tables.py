"""Read the bordered tables the lab SQL files print (``\\pset border 2``, unicode lines)."""

from typing import Dict, List


def tables(stdout: str) -> List[List[Dict[str, str]]]:
    """Each bordered table in ``stdout``, as rows of header -> cell.

    A value with a line break continues on the next row with the other cells empty; psql
    marks the break with ``↵`` at the cell's right edge, and the continuation is joined back
    with a newline.
    """
    found: List[List[Dict[str, str]]] = []
    header: List[str] = []
    rows: List[Dict[str, str]] = []
    for line in stdout.splitlines():
        text = line.strip()
        if text.startswith("┌"):
            header, rows = [], []
        elif text.startswith("│"):
            cells = [cell.strip().rstrip("↵").rstrip() for cell in text.strip("│").split("│")]
            if not header:
                header = cells
            elif rows and not cells[0]:
                for key, cell in zip(header, cells):
                    if cell:
                        rows[-1][key] += "\n" + cell
            else:
                rows.append(dict(zip(header, cells)))
        elif text.startswith("└") and header:
            found.append(rows)
            header = []
    return found


def table_with(stdout: str, column: str) -> List[Dict[str, str]]:
    """The first table that has ``column``, or no rows."""
    return next((rows for rows in tables(stdout) if rows and column in rows[0]), [])


def probes(stdout: str) -> Dict[str, List[str]]:
    """Each probe as name -> [expected, observed, source, verdict].

    The first table lists every probe with its result and what it observed, and in Lab 4B
    why; a failed run repeats each probe that differs with what was expected (and, in Lab 2B,
    the call that observed it).
    A matching probe's expected value is its observed one.
    """
    differs = {row["Differs"]: row for row in table_with(stdout, "Differs")}
    out: Dict[str, List[str]] = {}
    for row in table_with(stdout, "Probe"):
        name, observed = row["Probe"], row["Observed"]
        detail = differs.get(name, {})
        source = row.get("Source") or detail.get("Source", "")
        out[name] = [detail.get("Expected", observed), observed, source, row["Result"]]
    return out
