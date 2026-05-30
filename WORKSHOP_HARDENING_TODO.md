# Builder's Session — Hardening TODO

Running list of everything flagged while optimizing the 60-min Level 400
Builder's Session. Check items off as they land.

## Active

- [ ] **Commit the embeddings cache** (40/40 embedded successfully):
  `git add data/embeddings_cache.json data/boutique_catalog_40.csv`
- [ ] **Verify Rerank v3.5 on-demand support.** Embed v4 required an inference
  profile (`us.cohere.embed-v4:0`); rerank (`cohere.rerank-v3-5:0`) is left as
  the bare ID. If the dry-run / runtime hits the same "on-demand not supported"
  error, switch rerank to `us.cohere.rerank-v3-5:0` in config.py + check_model_access.py + rerank path.
- [ ] **Run end-to-end dry run** against a test account: `scripts/dry-run-builders.sh`

  Expected once Rerank is confirmed: catalog seeds from cache, Marco Turn 4
  returns BK-01, tool_audit row appears.

## Resolved this session (model access)

- [x] Fixed invalid `cohere.embed-english-v4:0` → `cohere.embed-v4:0` across
  all scripts + bootstrap.
- [x] Embed v4 has no on-demand-by-bare-ID; switched to cross-region inference
  profile `us.cohere.embed-v4:0` in config.py (live backend), bootstrap `.env`
  default, seed script (region-derived, `BEDROCK_EMBED_MODEL_ID` overridable),
  and check_model_access.py.
- [x] Region default us-east-1 → us-west-2 in seed.

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
