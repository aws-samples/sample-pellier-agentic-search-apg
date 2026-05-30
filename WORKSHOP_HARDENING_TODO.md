# Builder's Session — Hardening TODO

Running list of everything flagged while optimizing the 60-min Level 400
Builder's Session. Check items off as they land.

## Active — the one thing left

- [ ] **Run end-to-end dry run** against a freshly-provisioned test account:
  `scripts/dry-run-builders.sh`. This is the last gate before the room.
  Expected: catalog seeds from cache, `health` reads READY, Marco Turn 4
  returns BK-01, Runtime invoke succeeds, `tool_audit` row appears.
  Watch specifically for a rerank "on-demand not supported" error — if it
  appears, the `us.cohere.rerank-v3-5:0` profile name is wrong for the
  account's region and needs the correct group prefix.

## Resolved this session (model access)

- [x] Committed embeddings cache (40/40 embedded) + pushed to GitHub.
- [x] Fixed invalid `cohere.embed-english-v4:0` → `cohere.embed-v4:0` across
  all scripts + bootstrap.
- [x] Embed v4 has no on-demand-by-bare-ID; switched to cross-region inference
  profile `us.cohere.embed-v4:0` in config.py (live backend), bootstrap `.env`
  default, seed script (region-derived, `BEDROCK_EMBED_MODEL_ID` overridable),
  and check_model_access.py.
- [x] Pre-empted the same fix for **Rerank v3.5** → `us.cohere.rerank-v3-5:0`
  in config.py, check_model_access.py, rerank docstring, the Gateway MCP
  search server (`scripts/deploy/pellier_search_server.py`),
  `seed_tool_registry.py`, and test_config assertions.
- [x] Region default us-east-1 → us-west-2 in seed.

## Resolved this session (model access)

- [x] Fixed invalid `cohere.embed-english-v4:0` → `cohere.embed-v4:0` across
  all scripts + bootstrap.
- [x] Embed v4 has no on-demand-by-bare-ID; switched to cross-region inference
  profile `us.cohere.embed-v4:0` in config.py (live backend), bootstrap `.env`
  default, seed script (region-derived, `BEDROCK_EMBED_MODEL_ID` overridable),
  and check_model_access.py.
- [x] Region default us-east-1 → us-west-2 in seed.

## Content polish pass (WS folder)

- [x] **Gap 1 — AWS references.** New `90-appendix/05-references/` (grouped:
  pgvector/Aurora, Bedrock, AgentCore, Strands, Cedar, MCP, Knowledge Bases,
  observability) + inline "Learn more" at the rerank-tuning moment + a
  takeaways box in `40-close`. **All URLs flagged for verification** (see the
  warning box on the references page).
- [x] **Gap 2 — tip taxonomy.** Promoted insider nuggets to `💡 Pro tip`
  boxes: NULL-result audit signal, per-specialist model latency budget,
  rerank-per-query-class. Box vocabulary now consistent: New to X (scaffold) /
  Pattern to borrow (portability) / Pro tip (400 nuance) / Learn more (refs).
- [x] **Gap 3 — calibration.** Added "New to agentic AI?" vocab box to
  00-introduction; fixed namespace colon→dash in the memory auth box;
  surfaced the regulated-domain human-review caveat at the Act II
  `process_return` mutation moment.

### Verify-later (content)

- [ ] **Verify the ~25 reference URLs** in `90-appendix/05-references/`
  resolve and reflect current service behavior (AgentCore GA paths, blog
  URLs, model-id doc anchors). Knowledge cutoff is May 2025 — some may have moved.

## Residual cleanup

- [x] Swept "Wire It Live" / "Lab N" docstrings from session code (config.py,
  models, auth.py, agentcore_memory.py, chat.py, app.py). auth.py
  verify_cognito_token confirmed fully implemented (demo mode dormant).
  test_agents.py left as-is (dev harness, not session code).
- [x] Formalized exercise taxonomy: 2 mandatory builds (floor_check Act I,
  tool_audit SELECT Act II) + optional skill-edit / observability seam.
  Removed the contradictory "only build moment in the session" claim;
  added an at-a-glance exercise table to the Act I index.

## Done

- [x] `--from-cache` embeddings preload path in seed + bootstrap switched to it
- [x] Bedrock model-access preflight in bootstrap (STEP 8b); Embed v4 optional
- [x] Post-boot health gate (`scripts/health-gate.sh`) + `health` alias
- [x] Confirmed bootstrap runs at instance launch (pre-event); documented
  AgentCore launch non-idempotency in facilitator notes
- [x] Stripped workshop-only TODOs / dead `/api/atelier/status` + `useWorkshopStatus`
- [x] Guardrails documented as inspect-only (code already implemented)
- [x] `escalate_to_stylist` (13th tool) in the cast reference + specialist rows
- [x] Consolidated start-backend to one canonical script
- [x] End-to-end dry-run script (`scripts/dry-run-builders.sh`)
