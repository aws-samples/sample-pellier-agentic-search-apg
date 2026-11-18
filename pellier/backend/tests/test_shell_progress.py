"""The shell scripts' progress bar: scripts/lib/progress.sh, which lab3-start.sh draws during its
restart wait and its proof turn. Off a terminal it must draw nothing, so logs stay clean."""
from __future__ import annotations

import re
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


RESET = REPO / "scripts" / "reset-governed-workshop.sh"
AGENTCORE_RESET = REPO / "scripts" / "lib" / "agentcore-reset.sh"


def _backgrounded_under_a_bar(source: str, command: str, label: str) -> bool:
    """The command's statement ends with ``&`` and the bar waits on it with this label."""
    start = source.index(command)
    statement_end = source.index("\n", source.index("2>&1", start))
    waited = source[statement_end:statement_end + 200]
    return (source[start:statement_end].rstrip().endswith("&")
            and f'pellier_progress_wait_for "$!" "{label}"' in waited)


def test_the_whole_reset_shows_a_bar_over_every_long_step() -> None:
    """Event of 2026-11-17: the reset printed nothing for about six of its nine minutes while it
    rebuilt the database, cleared Memory and redeployed AgentCore. A participant saw a frozen
    terminal. Each of those steps now runs under the bar, with its usual time."""
    reset = RESET.read_text(encoding="utf-8")
    agentcore = AGENTCORE_RESET.read_text(encoding="utf-8")
    assert _backgrounded_under_a_bar(reset, 'bash "$REPO/scripts/setup/database-reset.sh"',
                                     "Rebuilding Pellier's database")
    assert _backgrounded_under_a_bar(reset, 'scripts/reset_memory_runtime.py" --apply',
                                     "Clearing AgentCore Memory")
    assert _backgrounded_under_a_bar(agentcore, "--reset-to-starters",
                                     "Redeploying AgentCore from the starter code")
    assert _backgrounded_under_a_bar(agentcore, "_agentcore deploy --yes --json",
                                     "Restoring the Lab 4 policy")
    assert 'pellier_progress_draw "Waiting for Pellier to restart"' in reset


def test_the_reset_says_how_long_it_takes_before_it_starts() -> None:
    reset = RESET.read_text(encoding="utf-8")
    assert "This takes about 9 minutes" in reset
    assert reset.index("This takes about 9 minutes") < reset.index("_assert_no_running_deploy\n")


@pytest.mark.parametrize("code, expected", [(0, "rc=0 step="), (5, "rc=1 step=starter-deploy")])
def test_a_redeploy_under_the_bar_still_reports_its_failure(tmp_path: Path, code: int,
                                                            expected: str) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    fake = tmp_path / "python"
    fake.write_text(f"#!/bin/sh\nsleep 1\nexit {code}\n")
    fake.chmod(0o755)
    body = (f'pass() {{ :; }}; fail() {{ :; }}; warn() {{ :; }}; REPO="{tmp_path}"; '
            f'PYTHON="{fake}"; AGENTCORE_PARTICIPANT_OUTPUT_JSON="{receipt}"; '
            f'. "{AGENTCORE_RESET}"; rc=0; pellier_restore_lab3_agentcore || rc=$?; '
            'echo "rc=$rc step=$PELLIER_RESET_FAILED_STEP"')
    result = subprocess.run([BASH, "-c", body], capture_output=True, text=True,
                            env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TERM": "xterm"})
    assert result.stdout.strip().endswith(expected), result.stdout + result.stderr


def test_ctrl_c_during_a_bar_stops_the_step_it_waits_for() -> None:
    """Review, 2026-11-17: a script without job control starts background jobs with SIGINT
    ignored, so Ctrl-C during the reset's bar left the database rebuild or the redeploy running
    on its own. The bar now stops its step and returns the step's status."""
    import os
    import signal
    import time

    body = (f'. "{LIB}"; sleep 30 & child=$!; echo "child $child"; '
            'pellier_progress_wait_for "$child" "x" 5; echo "status $?"; '
            'kill -0 "$child" 2>/dev/null && echo alive || echo stopped')
    proc = subprocess.Popen([BASH, "-c", body], stdout=subprocess.PIPE, text=True,
                            env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TERM": "xterm"})
    assert proc.stdout is not None
    child = int(proc.stdout.readline().split()[1])
    time.sleep(1)
    os.kill(proc.pid, signal.SIGINT)
    out, _ = proc.communicate(timeout=10)
    assert "stopped" in out, out
    try:
        os.kill(child, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    assert not alive, "the waited step outlived Ctrl-C"


def test_a_line_wider_than_the_terminal_is_cut_to_fit() -> None:
    """Event of 2026-11-17: the Memory step's bar line was about 108 columns in a 100-column
    terminal, so every redraw wrapped and the carriage return could not reach its start: the
    terminal filled with one copy per redraw. A line never reaches the terminal's last column."""
    fit = _bash('pellier_progress_fit "$(printf "%0.sx" $(seq 1 130))" 100').stdout
    assert len(fit) == 99
    assert _bash('pellier_progress_fit "short line" 100').stdout == "short line"
    assert _bash('pellier_progress_fit "short line" 0').stdout == "short line"


def test_every_reset_bar_fits_a_hundred_column_terminal() -> None:
    reset = RESET.read_text(encoding="utf-8") + AGENTCORE_RESET.read_text(encoding="utf-8")
    labels = re.findall(r'pellier_progress_(?:wait_for "\$!"|draw) "([^"]+)" (\d+)', reset)
    assert labels, "no bars found"
    for label, typical in labels:
        line = _bash(f'pellier_progress_line "{label}" {typical} {int(typical) + 30}').stdout
        assert len(line) < 100, (label, len(line))


def test_ctrl_c_also_stops_what_the_waited_step_started() -> None:
    """Review, 2026-11-17: the starter redeploy runs as ( cd ... && python ... ) &, so the waited pid
    is a subshell and the deploy is its child. Ctrl-C must stop the child too, not only the subshell."""
    import os
    import signal
    import time

    body = (f'. "{LIB}"; ( sleep 30; : ) & child=$!; sleep 1; '
            'echo "grandchild $(pgrep -P "$child")"; '
            'pellier_progress_wait_for "$child" "x" 5; echo "status $?"')
    proc = subprocess.Popen([BASH, "-c", body], stdout=subprocess.PIPE, text=True,
                            env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "TERM": "xterm"})
    assert proc.stdout is not None
    grandchild = int(proc.stdout.readline().split()[1])
    time.sleep(1)
    os.kill(proc.pid, signal.SIGINT)
    proc.communicate(timeout=10)
    time.sleep(0.5)
    try:
        os.kill(grandchild, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    assert not alive, "the step's own child outlived Ctrl-C"
