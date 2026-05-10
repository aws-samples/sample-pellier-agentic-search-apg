"""test_backend_copy_hardcoded.py - PR copy-compliance lint (Task 6.3).

Validates Req 1.12.1 through 1.12.4 on the backend side: every
user-facing string a FastAPI route surfaces to the storefront UI must
live in ``pellier/backend/boutique_copy.py``. This test is the CI tripwire:
it scans the ``routes/`` package for string literals in response bodies
and raised-detail positions that look like customer-facing English
sentences AND do not come from ``copy.py``.

Scanner contract
----------------

Scope. The scanner targets every ``routes/*.py`` module where a
response body or error envelope can surface to the storefront UI. It
does NOT scan service modules, models, or agents - those layers either
never surface text to the shopper directly (service-internal
exceptions bubble up as machine codes) or have their own compliance
test (``tests/test_copy_compliance.py`` for ``boutique_copy.py``).

Detection heuristic (mirrors the frontend scanner in
``frontend/src/__tests__/copy_hardcoded_strings.test.ts``):

  * a flagged candidate must appear as the value of one of the
    following "surfaces":

        - ``HTTPException(... detail="...")``
        - ``JSONResponse(... content={... : "..."})``
        - ``return "..."`` at the tail of a handler function
        - a bare ``{"message": "..."}`` / ``{"error": "..."}`` /
          ``{"detail": "..."}`` dict literal

  * looks like a customer-facing English sentence: length > 15,
    starts with an uppercase ASCII letter, contains at least one
    space, and every character is a letter, digit, space, apostrophe,
    comma, period, question mark, exclamation mark, or hyphen.

Allowed strings. A flagged string is cleared when it is imported from
the ``boutique_copy`` module (``from boutique_copy import ...``
pattern) in the same file. In practice the routes we ship today emit
only machine codes like ``"auth_failed"`` and ``"invalid_state"`` - so
the expected state is zero violations.

Per-line suppression. A ``# copy-allow: <reason>`` comment on the same
line as a hit suppresses it. Use sparingly (test fixtures, strings that
happen to look like sentences but are internal log messages).

Self-verification. The scanner is exercised twice:

  1. On a synthetic source string containing a known-bad ``"Sign in
     and ..."`` hardcoded sentence inside a ``JSONResponse`` body: the
     test asserts the scanner surfaces it.
  2. On the real ``routes/*.py`` files: the test asserts zero
     violations. Moving any such string into ``boutique_copy.py`` clears it.

Both assertions must pass for CI to go green.
"""

from __future__ import annotations

import re
import sys
import tokenize
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Tuple

ROUTES_DIR = Path(__file__).resolve().parents[1] / "routes"

# Legacy strings present in existing route files that are internal-only
# (log messages, scope values, redirect URLs) but happen to look like
# English sentences. Keep empty; new entries need justification in the
# PR description.
LEGACY_ALLOWLIST: set[str] = set()

SUPPRESS_MARKER = "copy-allow:"

# Python-literal surfaces we treat as "user-facing response body".
# Each pattern pulls a string literal out of the right-hand side of a
# known response-building call. The patterns are deliberately narrow
# so internal strings (log messages, SQL, URL paths) are ignored.
#
# 1. ``HTTPException(... detail="...")`` - FastAPI's canonical error
#    body uses ``detail``. If ``detail`` happens to be a sentence, the
#    shopper sees it verbatim.
# 2. ``JSONResponse(... content={... : "..."})`` - any string value
#    nested inside a content dict literal.
# 3. ``return "..."`` at the start of a line (ignoring leading
#    whitespace) - catches simple ``return "Message"`` handlers.
# 4. ``{"message" | "error" | "detail": "..."}`` - bare dicts returned
#    directly or piped through a response helper.


def _strip_comments_and_docstrings(source: str) -> str:
    """Return source with comments and triple-quoted docstrings blanked
    to spaces while preserving line/column positions.

    The frontend scanner has to deal with JSX attribute strings; the
    Python scanner's analog is docstrings + comments. Module-level and
    function-level docstrings are natural prose so they routinely
    contain sentences like "Return the verified shopper's profile"
    which the heuristic would otherwise trip on.

    We detect docstrings structurally: any ``STRING`` token whose
    prior meaningful token is ``NEWLINE``, ``INDENT``, ``DEDENT``,
    ``ENCODING``, or the start of the file. That captures module,
    class, and function docstrings while leaving regular string
    literals (the ones we actually want to scan) untouched.
    """
    tokens = list(tokenize.tokenize(BytesIO(source.encode("utf-8")).readline))
    drop_ranges: List[Tuple[int, int, int, int]] = []

    # Iterate with a simple state machine. A STRING is a docstring iff
    # the most recent non-whitespace token was NEWLINE / INDENT / DEDENT
    # / ENCODING (the sequence of tokens that opens a new logical
    # statement at module-, class-, or function-body scope). Any other
    # preceding token (NAME, OP, STRING-concat, etc.) means the STRING
    # is an expression and must be scanned.
    prev_meaningful = tokenize.ENCODING  # start-of-file acts like a newline
    inside_docstring_chain = False
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            drop_ranges.append(
                (tok.start[0], tok.start[1], tok.end[0], tok.end[1])
            )
            # Comments do not change the "opens a new logical statement"
            # state - a docstring can still immediately follow.
            continue
        if tok.type in (tokenize.NL, tokenize.NEWLINE):
            # Reset the docstring-concat chain when a real NEWLINE ends
            # the statement. (NL is a no-op logical newline inside an
            # expression.)
            if tok.type == tokenize.NEWLINE:
                inside_docstring_chain = False
            prev_meaningful = tok.type
            continue
        if tok.type in (tokenize.INDENT, tokenize.DEDENT):
            prev_meaningful = tok.type
            continue
        if tok.type == tokenize.STRING:
            if inside_docstring_chain or prev_meaningful in (
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENCODING,
            ):
                drop_ranges.append(
                    (tok.start[0], tok.start[1], tok.end[0], tok.end[1])
                )
                inside_docstring_chain = True
            prev_meaningful = tokenize.STRING
            continue
        # Any other token (NAME like `return`, OP like `=`, NUMBER, ...)
        # means the current statement is no longer a candidate docstring.
        inside_docstring_chain = False
        prev_meaningful = tok.type

    lines = source.splitlines(keepends=True)

    def blank_out(line: str, start_col: int, end_col: int) -> str:
        newline = ""
        if line.endswith("\r\n"):
            newline = "\r\n"
            body = line[:-2]
        elif line.endswith(("\n", "\r")):
            newline = line[-1]
            body = line[:-1]
        else:
            body = line
        start = max(0, start_col)
        end = min(len(body), end_col)
        return body[:start] + (" " * (end - start)) + body[end:] + newline

    for sr, sc, er, ec in drop_ranges:
        if sr == er:
            idx = sr - 1
            if 0 <= idx < len(lines):
                lines[idx] = blank_out(lines[idx], sc, ec)
        else:
            if 0 <= sr - 1 < len(lines):
                lines[sr - 1] = blank_out(
                    lines[sr - 1], sc, len(lines[sr - 1])
                )
            for mid in range(sr, er - 1):
                if 0 <= mid < len(lines):
                    lines[mid] = blank_out(lines[mid], 0, len(lines[mid]))
            if 0 <= er - 1 < len(lines):
                lines[er - 1] = blank_out(lines[er - 1], 0, ec)

    return "".join(lines)


_SENTENCE_CHARSET = re.compile(r"^[A-Za-z0-9 ,.!?'\-]+$")


def looks_like_user_facing_sentence(s: str) -> bool:
    """Return True when ``s`` looks like a customer-facing English sentence.

    Rules: length > 15, starts with uppercase ASCII letter, contains at
    least one space, every character fits the sentence charset.
    """
    if len(s) <= 15:
        return False
    if not ("A" <= s[0] <= "Z"):
        return False
    if " " not in s:
        return False
    if not _SENTENCE_CHARSET.match(s):
        return False
    return True


def _iter_string_literals(scrubbed_source: str) -> Iterable[Tuple[int, int, str]]:
    """Yield ``(line_index, col_index, literal)`` for each plain string
    literal in ``scrubbed_source``.

    Only non-f, non-b, non-raw string literals are yielded. ``f"..."``
    strings are the province of logger calls and URL builders, not
    user-visible copy; excluding them avoids false positives on the
    Cognito URL helpers.
    """
    try:
        tokens = tokenize.tokenize(
            BytesIO(scrubbed_source.encode("utf-8")).readline
        )
    except tokenize.TokenizeError:
        return

    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        prefix_end = 0
        s = tok.string
        while prefix_end < len(s) and s[prefix_end] not in ("'", '"'):
            prefix_end += 1
        prefix = s[:prefix_end].lower()
        if any(p in prefix for p in ("f", "b", "r")):
            continue
        # Strip one or three quote marks.
        body = s[prefix_end:]
        if body.startswith(("'''", '"""')):
            continue  # treat triple-quoted as docstrings (already dropped)
        if not body or body[0] not in ("'", '"'):
            continue
        quote = body[0]
        inner = body[1:-1] if body.endswith(quote) else body[1:]
        yield (tok.start[0] - 1, tok.start[1], inner)


# A string literal is only a "user-facing surface" when it appears in a
# response-building position. We look backwards from the literal's
# location for one of the surface keywords on the same line OR up to
# two lines earlier, mirroring the handful of multi-line call
# patterns FastAPI code tends to use (``JSONResponse(\n  content={...``).
#
# Matching on keywords instead of AST parsing keeps the scanner fast
# and avoids pulling in ``ast.parse`` (which would also need to handle
# forward references and unclosed blocks during edits).

_SURFACE_TOKENS = (
    re.compile(r"\bHTTPException\s*\("),
    re.compile(r"\bJSONResponse\s*\("),
    re.compile(r"\bdetail\s*="),
    re.compile(r"\bcontent\s*="),
    re.compile(r'"(?:message|error|detail|description)"\s*:'),
    re.compile(r"'(?:message|error|detail|description)'\s*:"),
    re.compile(r"^\s*return\s+['\"]", re.MULTILINE),
)


def _is_surface(context_window: str) -> bool:
    for pat in _SURFACE_TOKENS:
        if pat.search(context_window):
            return True
    return False


def scan_source(file_name: str, raw_source: str) -> List[str]:
    """Return a list of human-readable violation messages for ``raw_source``."""
    scrubbed = _strip_comments_and_docstrings(raw_source)
    scrubbed_lines = scrubbed.splitlines()
    raw_lines = raw_source.splitlines()

    violations: List[str] = []

    for (lineno, col, literal) in _iter_string_literals(scrubbed):
        if not looks_like_user_facing_sentence(literal):
            continue
        if literal in LEGACY_ALLOWLIST:
            continue

        raw_line = raw_lines[lineno] if lineno < len(raw_lines) else ""
        if SUPPRESS_MARKER in raw_line:
            continue

        start = max(0, lineno - 2)
        window = "\n".join(scrubbed_lines[start : lineno + 1])
        if not _is_surface(window):
            continue

        violations.append(
            f"{file_name}:{lineno + 1}:{col + 1}: hardcoded user-facing "
            f"string {literal!r} (move to boutique_copy.py and import "
            f"it, or add "
            f"a '# {SUPPRESS_MARKER} <reason>' suppression on the same line)"
        )

    return violations


def _route_files() -> List[Path]:
    """Return the list of backend route modules to scan."""
    if not ROUTES_DIR.exists():
        return []
    return sorted(
        p for p in ROUTES_DIR.glob("*.py") if p.name != "__init__.py"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scanner_detects_hardcoded_json_response_sentence() -> None:
    """The canonical bad sample: a hardcoded `Sign in and ...` string
    slipped into a ``JSONResponse`` body. The scanner must flag it."""
    bad_source = (
        "from fastapi import APIRouter\n"
        "from fastapi.responses import JSONResponse\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.get('/bad')\n"
        "async def bad():\n"
        "    return JSONResponse(\n"
        "        status_code=200,\n"
        "        content={'message': 'Sign in and watch Pellier tailor the storefront to you.'},\n"
        "    )\n"
    )
    violations = scan_source("bad.py", bad_source)
    assert len(violations) == 1, (
        f"expected exactly one violation, got {violations}"
    )
    assert "Sign in and watch Pellier" in violations[0]


def test_scanner_detects_hardcoded_http_exception_detail() -> None:
    """``HTTPException(detail="Some sentence")`` surfaces directly to
    the shopper via the FastAPI error envelope."""
    bad_source = (
        "from fastapi import HTTPException\n"
        "\n"
        "def raise_it():\n"
        "    raise HTTPException(\n"
        "        status_code=400,\n"
        "        detail='Sign in and watch Pellier tailor the storefront to you.',\n"
        "    )\n"
    )
    violations = scan_source("raise.py", bad_source)
    assert len(violations) == 1, (
        f"expected exactly one violation, got {violations}"
    )
    assert "Sign in and watch Pellier" in violations[0]


def test_scanner_detects_bare_return_sentence() -> None:
    """A handler that ``return "..."``s a sentence surfaces it to the
    caller via FastAPI's default response encoder."""
    bad_source = (
        "async def handler():\n"
        "    return 'Sign in and watch Pellier tailor the storefront to you.'\n"
    )
    violations = scan_source("handler.py", bad_source)
    assert len(violations) == 1
    assert "Sign in and watch Pellier" in violations[0]


def test_scanner_ignores_machine_codes_and_short_strings() -> None:
    """Machine-code error envelopes like ``{"error": "auth_failed"}``
    must not trip the scanner. Short labels and identifier-shaped
    strings are below the length/uppercase threshold."""
    good_source = (
        "from fastapi import HTTPException\n"
        "from fastapi.responses import JSONResponse\n"
        "\n"
        "def a():\n"
        "    raise HTTPException(status_code=401, detail='auth_failed')\n"
        "\n"
        "def b():\n"
        "    return JSONResponse(\n"
        "        status_code=400,\n"
        "        content={'error': 'invalid_state'},\n"
        "    )\n"
        "\n"
        "def c():\n"
        "    return 'SELECT * FROM product_catalog WHERE tags && %s'\n"
    )
    violations = scan_source("good.py", good_source)
    assert violations == []


def test_scanner_ignores_docstrings_and_comments() -> None:
    """Docstrings and ``#`` comments are prose that happens to look
    like sentences; the scanner must not flag them."""
    source = (
        '"""Module docstring - this looks like a sentence and must be ignored."""\n'
        "\n"
        "def f():\n"
        '    """Return the verified shopper\'s profile."""\n'
        "    # Sign in and watch Pellier tailor the storefront to you.\n"
        "    return {'ok': True}\n"
    )
    violations = scan_source("mod.py", source)
    assert violations == []


def test_scanner_honors_per_line_suppression() -> None:
    """A ``# copy-allow: <reason>`` comment on the same line as a hit
    suppresses it. Useful for test fixtures or log messages that must
    stay inline for a clear reason."""
    source = (
        "from fastapi.responses import JSONResponse\n"
        "\n"
        "def f():\n"
        "    return JSONResponse(\n"
        "        content={'message': 'Sign in and watch Pellier tailor the storefront to you.'},  # copy-allow: test-fixture\n"
        "    )\n"
    )
    violations = scan_source("sup.py", source)
    assert violations == []


def test_scanner_skips_log_messages_and_sql() -> None:
    """Log arguments and SQL strings are not response bodies. They
    must not be flagged even when the sentence heuristic matches."""
    source = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "\n"
        "def f():\n"
        "    logger.info('Storefront search query=%r results=%d', 'q', 7)\n"
        "    sql = 'SELECT id FROM pellier.product_catalog WHERE tags && %s'\n"
        "    return {'ok': True}\n"
    )
    violations = scan_source("logs.py", source)
    assert violations == []


def test_real_route_files_are_clean() -> None:
    """Every ``pellier/backend/routes/*.py`` module must emit
    zero user-facing hardcoded sentences. This is the CI guard: when a
    PR introduces a ``"Sign in and ..."``-shaped string in a route, the
    test fails until the string is moved into ``copy.py``."""
    files = _route_files()
    assert len(files) > 0, (
        "No route files found - scanner has nothing to check. "
        "Expected pellier/backend/routes/*.py to exist."
    )

    all_violations: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROUTES_DIR.parent).as_posix()
        all_violations.extend(scan_source(rel, source))

    if all_violations:
        raise AssertionError(
            "Found hardcoded user-facing strings in backend routes:\n  "
            + "\n  ".join(all_violations)
        )


def main() -> int:
    """CLI entry point mirroring ``tests/test_copy_compliance.py``."""
    files = _route_files()
    if not files:
        print("No route files found.", file=sys.stderr)
        return 1
    violations: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROUTES_DIR.parent).as_posix()
        violations.extend(scan_source(rel, source))
    if violations:
        print("Hardcoded user-facing strings found:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"{len(files)} route files: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
