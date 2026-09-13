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


def test_the_prompt_avoids_the_specialist_lab_1_has_not_built_yet() -> None:
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
    hello_block = hello_block[: hello_block.index("PELLIER_RUN_ID=")]
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
