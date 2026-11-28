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


_MARKS = {"✓": "matches", "✗": "does not match"}


def probes(stdout: str) -> Dict[str, List[str]]:
    """Each test as name -> [expected, observed, source, verdict], from the one results table.

    The table has Test, Should return or Should be, Is now and OK columns. A test that passes
    shows the same short answer in both columns, or leaves Is now empty in the files that still
    do, so its observed value is its expected one; a failing test shows both whole. ``source`` is always empty. The verdict reads ``matches`` or ``does not match``.
    """
    main = next((rows for rows in tables(stdout) if rows and "OK" in rows[0]), [])
    out: Dict[str, List[str]] = {}
    for row in main:
        expected = row.get("Should return") or row.get("Should be", "")
        observed = row["Is now"] or expected
        out[row["Test"]] = [expected, observed, "", _MARKS[row["OK"]]]
    return out
