# Fresh-account probe checklist

The authoritative gate before the Pellier workshop is participant-ready. Run this
**on a freshly-provisioned Workshop Studio box, as the participant user**, after
CloudFormation → bootstrap has completed. Everything here is **read-only / safe**
(one optional `dry-run` is non-destructive and self-restoring).

Why this exists: most of the recent work is statically green but carries
"confirm on-box" markers — the dev sandbox has no AWS creds, no npm registry, and
no provisioned stack. This run is where "believed fixed" becomes "proven," and
where content `> probe note:` markers get reconciled to real captured output.

> **Capture + sanitize as you go.** Where a step says CAPTURE, copy the real
> output into the matching content `> probe note`, and **replace any ARN /
> account id / gateway id with `<placeholder>`** before it lands in published
> content.

---

> **Region: us-east-1.** The workshop's default region moved from us-west-2 to
> **us-east-1** (us-west-2 had a Bedrock model-access outage). Confirm the stack
> launched in us-east-1 and that `.env` reads `AWS_REGION=us-east-1` before you
> start. The commands below are region-agnostic (they read `$AWS_REGION` / `.env`),
> so no region is hardcoded here — but the *Bedrock access* gate (step 1) and the
> *AgentCore availability* assumption are both now being tested in us-east-1.

## 0. Prereqs (fail fast here)

```bash
cd /workshop/sample-pellier-agentic-search-apg

node --version                 # MUST be >= v20  (Gate #1: Node-20 robustness fix)
type agentcore                 # should print the shell FUNCTION (not "not found", not an alias)
which -a agentcore             # confirm no stale Python starter-toolkit binary shadows it

# Region + which managed pieces provisioned. AWS_REGION must read us-east-1;
# empty endpoint values = that optional beat degrades (expected, not a fault).
grep -E 'AWS_REGION|USE_AGENTCORE_RUNTIME|AGENTCORE_RUNTIME_ENDPOINT|AGENTCORE_GATEWAY_URL|MCP_GATEWAY_URL|AGENTCORE_POLICY_ENGINE_ID|AGENTCORE_MEMORY_ID' \
  pellier/backend/.env
```

**Pass:** Node ≥ 20; `agentcore` is a function; `AWS_REGION=us-east-1`; `.env` has
the runtime endpoint + gateway URL (+ ideally policy-engine id). If Node < 20 →
the NodeSource fix regressed; stop and fix bootstrap before anything else.

---

## 1. Provisioning health (Gate #1: the 4 fresh-account fixes + model access)

```bash
python3 scripts/check_model_access.py        # Gate #5: Bedrock access (Opus/Sonnet, Haiku, Embed v4, Rerank v3.5)
bash scripts/health-gate.sh                  # 6 checks; READY only if catalog=40, warehouse seeded, memory+runtime set
cat /var/log/pellier-agentcore.log           # the STEP-16 provisioning transcript
```

What each fix is being confirmed against (these were the bugs from the *last*
fresh-account run):
- **Cedar action self-correct** — grep the log for `accepted action identifier:` →
  **CAPTURE which candidate won** (`pellier-concierge-experience-target___process_return`
  triple-underscore is the dat403-verified guess; the engine's `did you mean` hint
  wins if different). This tells us the real GA action format.
- **Node 20** — provisioning didn't die on `SyntaxError: Invalid regular expression flags`.
- **CDK `s3:PutLifecycleConfiguration`** — no `CDKToolkit StagingBucket CREATE_FAILED`.
- **`deploy_all.sh` env self-resolve** — only relevant if you hand-re-run it; it
  should resolve CFN outputs from `STACKNAME` or print a clean export list (no
  `PGHOSTARN: unbound variable` crash).

**Pass:** `check_model_access` all-green (or clean Sonnet fallback); health-gate
`READY`; `AGENTCORE_POLICY_ENGINE_ID` non-empty in `.env` (Gate #2: Policy ENFORCE
landed ACTIVE). If model access flaps "still processing," wait ~15 min and re-run —
external, not a bug.

---

## 2. agentcore CLI surface @ 0.18 (Gate #3: resolve the version-pinned verbs)

```bash
agentcore --help               # CAPTURE: do status / logs / traces / invoke exist on 0.18?
agentcore status --help        # CAPTURE exact flags; any required --name/--runtime?
agentcore invoke --help        # CRITICAL: does 0.18 invoke accept --bearer-token? (dat403 uses it)
                               #   confirm --bearer-token / --session-id / --stream surface.
                               #   If NO bearer flag -> Movement B falls back to the app-side curl.
agentcore logs --help          # confirm NO --tail; note --since / -n / --json (non-interactive)
agentcore traces --help        # confirm `list` / `get` exist (else drop from Movement C + the take-home)
```

**Reconcile:** Act II `02-agentcore-runtime` §5 (`agentcore status`, `agentcore invoke
--bearer-token` as Movement B's primary, `agentcore logs`) and the traces/evals
take-home. Content uses ONLY verbs/flags confirmed here. Known from a cached 0.16.0:
`logs` needs non-interactive flags, no `--tail`, `--json` exists — and dat403's
deploy module uses `agentcore invoke --bearer-token "$TOKEN" --stream`, so the flag
is expected; **verify it exists on the pinned 0.18.0** before making it primary.

---

## 3. Cloud Runtime beat — Act II §5 (Gate #3 cont.)

```bash
# Project dir readable by participant? (repo-level chown in bootstrap-labs.sh covers it)
ls -la .agentcore-project/pellier/agentcore/.cli/deployed-state.json

agentcore status --json        # RESOLVED 2026-06-13 (box-captured, reconciled into §5): top-level
                               # {success, projectName, targetName, targetRegion, resources[],
                               # deployedState{}, logPath}; the agent resource carries
                               # deploymentState:"deployed" + detail:"READY" + identifier (runtime
                               # ARN) + invocationUrl (URL-encoded ARN — same data plane the raw
                               # curl uses). NOTE: CUSTOM_JWT does NOT appear in status output —
                               # it's in agentcore/agentcore.json; §5 "Expected" no longer claims it.
agentcore status               # run again from ~ : `cd ~ && agentcore status` confirms the function's cd works anywhere

source ~/pellier-token.sh marco   # must print "✅ … minted for Marco" + set non-empty $PELLIER_TOKEN
#   CAPTURE: confirm the print names "Marco" (not a UUID / email). Then confirm the
#   token literally CARRIES that identity — decode the access-token payload:
echo "$PELLIER_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool | grep -E 'username|client_id|token_use'
#   KEY CLAIM (Act II §5 identity-passthrough expand + Act III §2a): RESOLVED
#   on-box 2026-06-12 — the access token's field is `username` (NOT
#   `cognito:username`, that's the ID token) and the value is LOWERCASED
#   ("marco"/"anna" — Cognito normalizes case-insensitive usernames). Content
#   reconciled. Also try: `source ~/pellier-token.sh anna` -> payload
#   username == "anna" (proves the persona arg selects the user).
#   DO NOT paste a real token anywhere.

# PRIMARY (Movement B): the dat403-style CLI invoke — IF step-2 probe confirmed the flag.
agentcore invoke --bearer-token "$PELLIER_TOKEN" \
  "Find linen travel pieces for a warm-weather trip."
#   CAPTURE the streamed output VERBATIM -> reconcile §5 Movement B "Expected".
#   Answer should use the managed Gateway catalog/search path and return rail
#   "gateway-mcp". Marco's Brooklyn warehouse prompt belongs to the in-process
#   Act I floor_check path, not this Runtime smoke test. (CLI cd's to the deploy
#   dir via the agentcore function, so it finds deployed-state.json automatically.)

# FALLBACK (also valid; primary if 0.18 invoke lacks --bearer-token): app-side curl.
SESSION="probe-$(date +%s)"
curl -sN -X POST http://localhost:8000/api/agent/chat \
  -H "Authorization: Bearer ${PELLIER_TOKEN}" -H 'Content-Type: application/json' \
  -d "{\"message\":\"Find linen travel pieces for a warm-weather trip.\",\"session_id\":\"${SESSION}\"}"
#   CAPTURE the token'd SSE sequence (session->chunk->done was observed on the
#   in-process fallback; the Runtime branch may differ) -> reconcile the curl block.

# OPTIONAL: run only if the Code Editor role has logs:FilterLogEvents.
agentcore logs -n 20 --since 30m   # CAPTURE: does the platform-side record show the invoke?

# DEGRADATION (the "by design" runbook row): the curl with NO Authorization header
curl -sN -X POST http://localhost:8000/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d "{\"message\":\"Is the Hadley shirt at the Brooklyn warehouse?\",\"session_id\":\"anon-probe\"}"
#   MUST still answer in-process: no 401, no stack trace.
```

**Pass:** `agentcore status` shows a cloud ARN; `agentcore invoke --bearer-token`
(or the curl fallback) returns a catalog/search answer on the Gateway rail;
`agentcore logs` shows a platform-side record if permissions allow it; anonymous
curl falls back cleanly. If 0.18's `invoke` has no bearer flag, the curl is
primary and the content's `agentcore invoke` block should be demoted to the
alternative.

---

## 4. MCP on the wire — Act III §2a (Gate #4: the two scripts)

```bash
# Movement A — local stdio baseline (no token, always works)
python3 solutions/the-concierge/mcp_handshake.py
#   CAPTURE local tools/list + the chosen read-only call result -> reconcile Movement A "Expected"

# Movement B — custom tools through the managed Gateway ($PELLIER_TOKEN already set in step 3)
python3 solutions/the-concierge/gateway_tools_list.py
#   KEY UNKNOWN: did `initialize` succeed against AGENTCORE_GATEWAY_URL AS-IS?
#   If it FAILS, retry once with a trailing '/mcp' appended to the URL and note which form worked:
#     AGENTCORE_GATEWAY_URL="${AGENTCORE_GATEWAY_URL%/}/mcp" python3 solutions/the-concierge/gateway_tools_list.py
#   CAPTURE the real Gateway tool names (pellier-*-target__*) + read-call result;
#   confirm the by-pattern tool picker matched one -> reconcile Movement B "Expected".

# DEGRADATION: unset the token -> must exit 0 with "source ~/pellier-token.sh" guidance (Card 7 fallback)
( unset PELLIER_TOKEN; python3 solutions/the-concierge/gateway_tools_list.py )
```

**Pass:** both scripts complete the handshake and return data; the Gateway URL
form (`/mcp` or not) is recorded; the tool-pick patterns matched the real names.
If the picker missed (Gateway tools are prefixed `pellier-discovery-search-target__…`),
note the actual names so the substring patterns can be tightened.

---

## 5. End-to-end participant path (optional but recommended)

```bash
bash scripts/dry-run-builders.sh     # non-destructive: wires floor_check, fires Marco T4, checks tool_audit, restores stub
```

**Pass:** PASS exit; Marco T4 names Brooklyn/BK-01; the `tool_audit` row is present
(this also confirms Gate #6 — the in-process audit hook writes the ledger on the
default rail).

---

## After the probe: reconcile + publish

1. Replace every content `> probe note:` with the real captured command/output (ARNs sanitized).
2. If the Cedar action format differed from the triple-underscore guess, the
   self-correct already handled provisioning — just record the winning token in
   `scripts/deploy/deploy_policy.py`'s comment for the next maintainer.
3. If the Gateway needed `/mcp`, note it in `gateway_tools_list.py` and the §2a probe note.

## Still open (not gated by this probe)
- **Landing `architecture.png` / `.svg`** — still shows Cedar inside the Runtime
  boundary + "working and semantic" memory. Alt text is fixed; the rendered image
  needs regeneration (image work, owned separately). Highest-leverage remaining artifact.
- **`act2-arc.svg/.png`** — new card-02 caption supplied out-of-band; confirm the
  swap lands at 1188×446.
