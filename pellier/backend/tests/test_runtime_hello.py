"""The orientation Runtime hello, and the two claims it is allowed to make.

Participants used to meet AgentCore Runtime in Lab 3, about fifty minutes in.
`scripts/runtime_hello.sh` moves the first managed turn into orientation and
records the build id that answered, which is what Lab 3 later compares against.

Two failure modes this file locks down:

1. **Reading tool use from prose.** An answer naming a warehouse is not evidence
   a tool ran. The script must read tool names from the turn's execution events.
2. **Failing the room.** A box with no token helper or no deployed Runtime must
   still finish `workshop-start.sh`, because Labs 1 and 2 do not need Runtime.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
HELLO = REPO / "scripts" / "runtime_hello.sh"
START = REPO / "scripts" / "workshop-start.sh"


def _hello() -> str:
    return HELLO.read_text(encoding="utf-8")


def test_the_script_is_executable_and_syntactically_valid() -> None:
    assert HELLO.is_file(), f"{HELLO} is missing"
    assert HELLO.stat().st_mode & 0o111, "runtime_hello.sh must be executable"
    subprocess.run(["bash", "-n", str(HELLO)], check=True)


def test_it_invokes_the_pinned_cli_against_the_runtime() -> None:
    body = _hello()
    assert 'AGENTCORE_CLI_PINNED_VERSION:-0.29.0' in body
    assert '@aws/agentcore@${AGENTCORE_CLI_PINNED_VERSION}" invoke' in body
    assert '--runtime "$RUNTIME_NAME"' in body
    assert '--bearer-token "$PELLIER_TOKEN"' in body


def test_tool_names_come_from_execution_events_not_from_the_answer() -> None:
    """The one claim this step makes about tools has to be read, not inferred."""
    body = _hello()
    assert "$turn.tool_calls" in body
    assert "executedTools" in body
    # `.response` is the model's prose. Nothing may derive a tool name from it.
    assert "$turn.response | test" not in body
    assert "grep -o" not in body


def test_a_managed_turn_is_the_only_pass() -> None:
    body = _hello()
    assert '.rail == "gateway-mcp"' in body
    assert "managed: (.success and" in body
    assert 'jq -e \'.managed == true\'' in body


def test_the_evidence_file_is_labelled_so_two_runs_do_not_collide() -> None:
    body = _hello()
    assert 'EVIDENCE_FILE="$EVIDENCE_DIR/runtime-hello-$LABEL.json"' in body
    assert 'LABEL="baseline"' in body


def test_the_prompt_avoids_the_specialist_lab_2_has_not_built_yet() -> None:
    """At orientation the inventory specialist is a stub. Routing there would
    make provisioning look broken when it is the exercise."""
    body = _hello()
    prompt_line = next(
        line for line in body.splitlines() if line.startswith('PROMPT="')
    )
    lowered = prompt_line.lower()
    for stock_word in ("stock", "inventory", "warehouse", "restock"):
        assert stock_word not in lowered, prompt_line


def test_workshop_start_runs_it_without_letting_it_fail_the_run() -> None:
    start = START.read_text(encoding="utf-8")
    assert "runtime_hello.sh" in start
    assert "--label baseline" in start
    # The call sits in an if/else, so a non-zero status warns instead of exiting.
    hello_block = start[start.index("RUNTIME_HELLO="):]
    hello_block = hello_block[: hello_block.index('pass "Ready for Lab 1"')]
    assert "warn " in hello_block
    assert "exit 1" not in hello_block


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_the_jq_projection_reads_a_representative_runtime_payload(
    tmp_path: pathlib.Path,
) -> None:
    """The CLI hands back the entrypoint payload as a JSON string, and the
    Gateway qualifies every tool name with its target. Both have to survive."""
    body = _hello()
    start = body.index("  (if (.response | type)")
    end = body.index("' > \"$EVIDENCE_FILE\"")
    program = tmp_path / "filter.jq"
    program.write_text(body[start:end], encoding="utf-8")

    turn = {
        "response": "Two linen pieces suit warm weather.",
        "rail": "gateway-mcp",
        "specialist": "search",
        "build_fingerprint": "9f2c41a7be0312ab",
        "tool_calls": [
            {
                "tool": "pellier-discovery-search-target___search_products",
                "status": "success",
            }
        ],
        "gateway_tools": ["a", "b", "c"],
    }
    payload = tmp_path / "raw.json"
    payload.write_text(json.dumps({"success": True, "response": json.dumps(turn)}))

    out = subprocess.run(
        [
            "jq", "--arg", "label", "baseline", "--arg", "session", "s1",
            "--arg", "persona", "marco", "-f", str(program), str(payload),
        ],
        check=True, capture_output=True, text=True,
    )
    result = json.loads(out.stdout)
    assert result["managed"] is True
    assert result["executedTools"] == ["search_products"]
    assert result["buildFingerprint"] == "9f2c41a7be0312ab"
    assert result["publishedToolsOffered"] == 3


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_an_unauthenticated_turn_is_not_a_managed_turn(
    tmp_path: pathlib.Path,
) -> None:
    body = _hello()
    start = body.index("  (if (.response | type)")
    end = body.index("' > \"$EVIDENCE_FILE\"")
    program = tmp_path / "filter.jq"
    program.write_text(body[start:end], encoding="utf-8")

    turn = {"error": "authentication_required", "products": [], "rail": "runtime"}
    payload = tmp_path / "raw.json"
    payload.write_text(json.dumps({"success": True, "response": json.dumps(turn)}))

    out = subprocess.run(
        [
            "jq", "--arg", "label", "baseline", "--arg", "session", "s1",
            "--arg", "persona", "marco", "-f", str(program), str(payload),
        ],
        check=True, capture_output=True, text=True,
    )
    result = json.loads(out.stdout)
    assert result["managed"] is False
    assert result["executedTools"] == []


def _run_hello(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
               helper_body: str | None) -> tuple[subprocess.CompletedProcess, pathlib.Path]:
    """Run the real script beside a stub identity helper and a fake npx that records the bearer.

    The shell already holds PELLIER_TOKEN=left-in-the-shell. ``helper_body`` is the token
    helper's text, or None for a box that has no helper.
    """
    scripts = tmp_path / "repo" / "scripts"
    (scripts / "deploy").mkdir(parents=True)
    shutil.copy(HELLO, scripts / "runtime_hello.sh")
    (scripts / "deploy" / "resolve_agentcore_identity.py").write_text(
        f"print({str(tmp_path)!r})\n", encoding="utf-8")
    helper = tmp_path / "pellier-token.sh"
    if helper_body is not None:
        helper.write_text(helper_body, encoding="utf-8")
    turn = json.dumps({"rail": "gateway-mcp", "response": "Linen shirts.", "specialist": "catalog"})
    reply = json.dumps({"success": True, "response": turn})
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "npx").write_text(
        "#!/usr/bin/env bash\n"
        'while [ $# -gt 0 ]; do\n'
        '  [ "$1" = "--bearer-token" ] && echo "$2" > "$FAKE_BEARER"; shift\n'
        'done\n'
        f"cat <<'JSON'\n{reply}\nJSON\n", encoding="utf-8")
    (bin_dir / "npx").chmod(0o755)
    for key, value in {
        "PATH": f"{bin_dir}:{os.environ['PATH']}", "PELLIER_REPO": str(tmp_path / "repo"),
        "PELLIER_TOKEN_HELPER": str(helper), "PELLIER_TOKEN": "left-in-the-shell",
        "PELLIER_EVIDENCE_DIR": str(tmp_path / "evidence"), "FAKE_BEARER": str(tmp_path / "bearer"),
    }.items():
        monkeypatch.setenv(key, value)
    done = subprocess.run(["bash", str(scripts / "runtime_hello.sh"), "--persona", "theo"],
                          capture_output=True, text=True, timeout=60)
    return done, tmp_path / "bearer"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_a_token_left_in_the_shell_is_replaced_by_one_minted_for_the_persona(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The script's own comment: a stale token reads as a Runtime fault. It mints its own."""
    done, bearer = _run_hello(tmp_path, monkeypatch, 'export PELLIER_TOKEN="minted-for-$1"\n')
    assert done.returncode == 0, done.stdout + done.stderr
    assert bearer.read_text().strip() == "minted-for-theo"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_a_supplied_token_is_used_where_no_helper_exists(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    done, bearer = _run_hello(tmp_path, monkeypatch, None)
    assert done.returncode == 0, done.stdout + done.stderr
    assert bearer.read_text().strip() == "left-in-the-shell"


@pytest.mark.parametrize("minted", ["", "None"])
def test_a_helper_that_mints_nothing_skips_the_hello_instead_of_sending_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, minted: str,
) -> None:
    """A failed sign-in prints None through the AWS CLI's text output; neither is a token."""
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed")
    done, bearer = _run_hello(tmp_path, monkeypatch, f'export PELLIER_TOKEN="{minted}"\n')
    assert done.returncode == 1
    assert "Could not mint a token for 'theo'" in done.stdout + done.stderr
    assert not bearer.exists()
