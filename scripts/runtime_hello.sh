#!/usr/bin/env bash
# =============================================================================
# runtime_hello.sh -- invoke the deployed AgentCore Runtime once and record it
# =============================================================================
# Called twice in a workshop run, and the pair is the point:
#
#   1. From workshop-start.sh, during orientation. The Runtime that answers is
#      the one provisioning deployed, so its build id is the predeployed
#      baseline. A participant sees managed execution inside the first ten
#      minutes instead of at minute fifty.
#   2. Again after the Lab 3 deploy, when the build id must be theirs.
#
# The prompt is a catalog search on purpose. It routes to the search
# specialist, which is fully built at orientation; the inventory specialist is
# Lab 1's exercise and is meant to be missing.
#
# Tool names come from the turn's own execution events, never from the model's
# prose. An answer that names a warehouse is not evidence a tool ran.
#
# Usage:
#   scripts/runtime_hello.sh [--persona marco] [--label baseline]
#                            [--prompt "..."] [--runtime pellier_orchestrator]
#
# Exit status: 0 when the Runtime answered on the managed rail. 1 when it did
# not, or when the token, project, or CLI is missing. Callers that must not
# fail the room ignore the status and read the printed lines.
# bash 3.2 syntax only.
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
AGENTCORE_CLI_PINNED_VERSION="${AGENTCORE_CLI_PINNED_VERSION:-0.29.0}"
EVIDENCE_DIR="${PELLIER_EVIDENCE_DIR:-/tmp/pellier-evidence}"

PERSONA="marco"
LABEL="baseline"
RUNTIME_NAME="pellier_orchestrator"
PROMPT="What linen pieces do you have for warm weather?"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}+ OK${NC}    %s\n" "$1"; }
fail() { printf "  ${RED}x FAIL${NC}  %s\n" "$1" >&2; }
warn() { printf "  ${YEL}- WARN${NC}  %s\n" "$1"; }
info() { printf "  %s\n" "$1"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --persona) PERSONA="${2:-}"; shift 2 ;;
    --label) LABEL="${2:-}"; shift 2 ;;
    --prompt) PROMPT="${2:-}"; shift 2 ;;
    --runtime) RUNTIME_NAME="${2:-}"; shift 2 ;;
    *) fail "unknown argument '$1'"; exit 1 ;;
  esac
done
if ! [[ "$PERSONA" =~ ^[a-z][a-z0-9-]{0,31}$ ]]; then
  fail "persona must be a short lowercase slug; got '$PERSONA'"
  exit 1
fi
if ! [[ "$LABEL" =~ ^[a-z][a-z0-9-]{0,31}$ ]]; then
  fail "label must be a short lowercase slug; got '$LABEL'"
  exit 1
fi

PROJECT_DIR="$REPO/.agentcore-project/pellier"
EVIDENCE_FILE="$EVIDENCE_DIR/runtime-hello-$LABEL.json"

if [ ! -d "$PROJECT_DIR" ]; then
  warn "No AgentCore project at $PROJECT_DIR; skipping the Runtime hello"
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  warn "jq is not installed; skipping the Runtime hello"
  exit 1
fi

# The token helper is written by bootstrap and mints a fresh Cognito token,
# because they expire in about an hour and a stale one reads as a Runtime fault.
if [ -z "${PELLIER_TOKEN:-}" ]; then
  TOKEN_HELPER="${PELLIER_TOKEN_HELPER:-$HOME/pellier-token.sh}"
  if [ ! -r "$TOKEN_HELPER" ]; then
    warn "No token helper at $TOKEN_HELPER; skipping the Runtime hello"
    exit 1
  fi
  # shellcheck disable=SC1090
  . "$TOKEN_HELPER" "$PERSONA" >/dev/null 2>&1
fi
if [ -z "${PELLIER_TOKEN:-}" ]; then
  warn "Could not mint a token for '$PERSONA'; skipping the Runtime hello"
  exit 1
fi

mkdir -p "$EVIDENCE_DIR"
SESSION_ID="hello-$LABEL-$(date +%s)-$$-0000000000000001"

RAW="$(cd "$PROJECT_DIR" && npx -y "@aws/agentcore@${AGENTCORE_CLI_PINNED_VERSION}" invoke \
  --runtime "$RUNTIME_NAME" \
  --session-id "$SESSION_ID" \
  --bearer-token "$PELLIER_TOKEN" \
  --prompt "$PROMPT" \
  --json 2>/dev/null)"
if [ -z "$RAW" ]; then
  fail "The AgentCore CLI returned nothing for runtime '$RUNTIME_NAME'"
  exit 1
fi

# The CLI wraps the entrypoint's payload as a JSON string, so the turn has to be
# parsed out of it before anything can be asserted about the run.
printf '%s' "$RAW" | jq --arg label "$LABEL" --arg session "$SESSION_ID" --arg persona "$PERSONA" '
  (if (.response | type) == "string" then (.response | fromjson) else (.response // {}) end) as $turn
  | {
      label: $label,
      persona: $persona,
      sessionId: $session,
      success: (.success == true),
      rail: ($turn.rail // ""),
      specialist: ($turn.specialist // ""),
      buildFingerprint: ($turn.build_fingerprint // ""),
      executedTools: [
        ($turn.tool_calls // [])[]
        | (.tool // .name // .tool_name // empty)
        | sub(".*___"; "")
      ],
      executedToolStatuses: [($turn.tool_calls // [])[] | (.status // "unknown")],
      publishedToolsOffered: ($turn.gateway_tools // [] | length),
      answered: ((($turn.response // "") | length) > 0)
    }
  | . + { managed: (.success and .rail == "gateway-mcp" and .answered) }
' > "$EVIDENCE_FILE" 2>/dev/null

if ! jq -e '.managed == true' "$EVIDENCE_FILE" >/dev/null 2>&1; then
  fail "Runtime did not answer on the managed rail; see $EVIDENCE_FILE"
  printf '%s' "$RAW" | head -c 400 >&2; echo >&2
  exit 1
fi

RAIL="$(jq -r '.rail' "$EVIDENCE_FILE")"
BUILD="$(jq -r '.buildFingerprint' "$EVIDENCE_FILE")"
SPECIALIST="$(jq -r '.specialist' "$EVIDENCE_FILE")"
TOOLS="$(jq -r 'if (.executedTools | length) > 0 then (.executedTools | unique | join(", ")) else "none recorded" end' "$EVIDENCE_FILE")"

pass "AgentCore Runtime answered as $PERSONA on rail $RAIL"
pass "Specialist $SPECIALIST executed: $TOOLS"
if [ -n "$BUILD" ] && [ "$BUILD" != "null" ]; then
  pass "Packaged build ${BUILD:0:12} ($LABEL)"
else
  warn "The Runtime reported no build id; it was deployed before that existed"
fi
info "Saved $EVIDENCE_FILE"
exit 0
