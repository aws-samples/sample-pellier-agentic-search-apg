"""Scan backend/boutique_copy.py for copy compliance violations.

Rules enforced (Requirement 1.12):
  1. No emoji (any Unicode codepoint outside ASCII-plus-common-punctuation,
     excluding the en dash U+2013 which is allowed, and excluding curly quotes
     and middle dots used as typographic separators).
  2. No em dashes (U+2014).
  3. No forbidden words (case-insensitive whole-word match) from the
     boutique conventions: AI, intelligent, smart, agent, LLM, vector,
     embedding, and 'search' used as a standalone noun.

The scanner strips comments and the module-level docstring before matching
forbidden words so this very file's docstring does not cause false positives.

Runnable two ways:
  python pellier/backend/tests/test_copy_compliance.py
  pytest pellier/backend/tests/test_copy_compliance.py

Exits 0 when clean. Exits 1 with a per-violation message when not.
"""

from __future__ import annotations

import re
import sys
import tokenize
from io import BytesIO
from pathlib import Path


COPY_PATH = Path(__file__).resolve().parents[1] / "boutique_copy.py"

# Allow these Unicode codepoints even though they are non-ASCII. They are
# typographic punctuation used in our copy and are not emoji.
#   U+00A0 non-breaking space
#   U+00A9 copyright sign
#   U+00B7 middle dot
#   U+2013 en dash
#   U+2018 U+2019 U+201C U+201D curly quotes
#   U+2022 bullet
#   U+2026 ellipsis
#   U+2039 U+203A single angle quotes (used in 'Read the full vision >' link)
#   U+2318 command key symbol (in COMMAND_PILL keycap)
ALLOWED_NON_ASCII = {
    0x00A0, 0x00A9, 0x00B7, 0x2013,
    0x2018, 0x2019, 0x201C, 0x201D,
    0x2022, 0x2026, 0x2039, 0x203A,
    0x2318,
}

EM_DASH = "\u2014"

FORBIDDEN_WORDS = [
    "AI",
    "intelligent",
    "smart",
    "agent",
    "LLM",
    "vector",
    "embedding",
]

SEARCH_SUPPRESS_MARKER = "copy-allow: search-as-verb"


def _strip_comments_and_module_docstring(source: str) -> str:
    """Return source text with comments and the module-level docstring removed.

    Uses the tokenize module to identify comments and detects the module-level
    docstring as the first STRING token at the start of the file (skipping
    leading NEWLINE/ENCODING tokens).
    """
    tokens = list(tokenize.tokenize(BytesIO(source.encode("utf-8")).readline))
    drop_ranges: list[tuple[int, int, int, int]] = []

    # Find the module-level docstring.
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.NL, tokenize.NEWLINE,
                        tokenize.COMMENT):
            continue
        if tok.type == tokenize.STRING:
            drop_ranges.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
        break

    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            drop_ranges.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))

    lines = source.splitlines(keepends=True)

    def blank_out(line: str, start_col: int, end_col: int) -> str:
        # Preserve newline at end of line; blank out selected columns.
        newline = ""
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith("\n") or line.endswith("\r"):
            newline = line[-1]
            body = line[:-1]
        else:
            body = line
        start = max(0, start_col)
        end = min(len(body), end_col)
        return body[:start] + (" " * (end - start)) + body[end:] + newline

    for (sr, sc, er, ec) in drop_ranges:
        if sr == er:
            idx = sr - 1
            lines[idx] = blank_out(lines[idx], sc, ec)
        else:
            # first line: blank from sc to end
            lines[sr - 1] = blank_out(lines[sr - 1], sc, len(lines[sr - 1]))
            # middle lines: blank entirely
            for mid in range(sr, er - 1):
                lines[mid] = blank_out(lines[mid], 0, len(lines[mid]))
            # last line: blank 0..ec
            lines[er - 1] = blank_out(lines[er - 1], 0, ec)

    return "".join(lines)


def scan(source: str) -> list[str]:
    violations: list[str] = []
    raw_lines = source.splitlines()
    scrubbed = _strip_comments_and_module_docstring(source)
    scrubbed_lines = scrubbed.splitlines()

    # 1. Emoji / disallowed non-ASCII. Check raw source so we also cover
    #    strings and docstrings. Docstrings are allowed text but must still
    #    follow the no-emoji rule.
    for lineno, line in enumerate(raw_lines, start=1):
        for col, ch in enumerate(line):
            cp = ord(ch)
            if cp < 128:
                continue
            if cp in ALLOWED_NON_ASCII:
                continue
            # Flag anything else - emoji ranges and stray symbols alike.
            violations.append(
                f"{COPY_PATH.name}:{lineno}:{col + 1}: disallowed non-ASCII "
                f"character U+{cp:04X} ({ch!r})"
            )

    # 2. Em dash. Also checked on raw source so docstring uses are caught.
    for lineno, line in enumerate(raw_lines, start=1):
        col = line.find(EM_DASH)
        while col != -1:
            violations.append(
                f"{COPY_PATH.name}:{lineno}:{col + 1}: em dash (U+2014) is "
                "not allowed in user-facing copy; use a regular hyphen"
            )
            col = line.find(EM_DASH, col + 1)

    # 3. Forbidden words - case-insensitive whole-word match, scanned on the
    #    scrubbed source so the module docstring and comments describing the
    #    rule itself do not trip the scanner.
    word_patterns = [(w, re.compile(rf"(?<![A-Za-z0-9_])({re.escape(w)})(?![A-Za-z0-9_])",
                                     re.IGNORECASE)) for w in FORBIDDEN_WORDS]
    search_pattern = re.compile(r"(?<![A-Za-z0-9_])(search)(?![A-Za-z0-9_])", re.IGNORECASE)

    for lineno, line in enumerate(scrubbed_lines, start=1):
        raw_line = raw_lines[lineno - 1] if lineno - 1 < len(raw_lines) else ""
        for word, pat in word_patterns:
            for m in pat.finditer(line):
                violations.append(
                    f"{COPY_PATH.name}:{lineno}:{m.start() + 1}: forbidden "
                    f"word {m.group(0)!r} (matches rule: {word})"
                )
        if SEARCH_SUPPRESS_MARKER in raw_line:
            continue
        for m in search_pattern.finditer(line):
            violations.append(
                f"{COPY_PATH.name}:{lineno}:{m.start() + 1}: 'search' used "
                "as a standalone noun is forbidden (suppress with "
                f"'# {SEARCH_SUPPRESS_MARKER}' on the same line if it is a verb)"
            )

    return violations


def test_copy_compliance() -> None:
    """Pytest entry point. Raises AssertionError with all violations."""
    source = COPY_PATH.read_text(encoding="utf-8")
    violations = scan(source)
    assert not violations, "copy.py contains compliance violations:\n  " + "\n  ".join(violations)


def main() -> int:
    source = COPY_PATH.read_text(encoding="utf-8")
    violations = scan(source)
    if violations:
        print("copy.py contains compliance violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"{COPY_PATH.name}: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
