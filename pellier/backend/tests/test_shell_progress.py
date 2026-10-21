"""The shell scripts' progress bar: scripts/lib/progress.sh, which lab3-start.sh draws during its
restart wait and its proof turn. Off a terminal it must draw nothing, so logs stay clean."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "scripts" / "lib" / "progress.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def _bash(body: str, lang: str = "en_US.UTF-8") -> subprocess.CompletedProcess[str]:
    return subprocess.run([BASH, "-c", f'. "{LIB}"; {body}'], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "LANG": lang, "TERM": "xterm"})


def test_the_line_fills_toward_the_usual_time_and_says_when_it_runs_long() -> None:
    assert _bash('pellier_progress_line "Waiting for Pellier to restart" 15 6').stdout == (
        "  Waiting for Pellier to restart  " + "█" * 7 + "░" * 13 + "  0:06, usually about 0:15")
    assert _bash('pellier_progress_line "Waiting" 15 40').stdout == (
        "  Waiting  " + "█" * 19 + "░" + "  0:40, still working")


def test_a_terminal_without_utf8_gets_ascii_blocks() -> None:
    assert _bash('pellier_progress_line "Waiting" 10 5', lang="C").stdout == (
        "  Waiting  " + "#" * 9 + "-" * 11 + "  0:05, usually about 0:10")


def test_off_a_terminal_nothing_is_drawn_and_the_waited_status_comes_back() -> None:
    result = _bash('pellier_progress_draw "x" 5 0; pellier_progress_clear; '
                   '(exit 3) & pellier_progress_wait_for $! "x" 5; echo "status $?"')
    assert result.stdout == "status 3\n"


def test_lab3_start_draws_through_the_library() -> None:
    source = (REPO / "scripts" / "lab3-start.sh").read_text(encoding="utf-8")
    assert '. "${SCRIPT_DIR}/lib/progress.sh"' in source
    assert 'pellier_progress_wait_for "$!" "Restarting Pellier"' in source
    assert 'pellier_progress_draw "Waiting for Pellier to restart"' in source
    assert 'pellier_progress_wait_for "$!" "Running one turn on AgentCore"' in source
