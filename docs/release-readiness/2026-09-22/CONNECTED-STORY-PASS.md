# Connected governed L400 story pass

Reviewed 22 September 2026. Local implementation and presentation review are complete
for this pass. This is not a source-release, Studio-publication, or fresh-account
readiness certificate.

## Scope and state

- Source worktree: `.worktrees/governed-product-pass`, branch `governed`, based on
  `1f9fe29b584891f6d2aad680c48afb1990de0496`.
- Prior CLI-agent edits were retained. Source and Studio changes remain uncommitted;
  this pass did not push, deploy to AWS, or publish Workshop Studio.
- Studio package: `build-governed-agentic-ai-search-with-aurora-rds-bedrock-agentcore`.
- Studio source pin remains `894b04a8a25529560f9f3706feb96488200b1b9b`.

## Teaching contract

**Know the facts → respect the requirements → establish the caller → govern the action.**

Four different customers introduce accumulating responsibilities for one concierge.
The canonical map is [WORKSHOP-STORY-ARC.md](../../WORKSHOP-STORY-ARC.md) and
`workshop/story-arc.json`. The application orients participants and displays evidence;
Workshop Studio owns the exercises. Storefront serves shoppers, Observatory inspects
execution, and Operator supports a staff decision.

| Lab | Task A | Task B | Target |
|---|---|---|---|
| Marco | Implement the inventory result contract | Connect the specialist and prove a real turn | 15 min |
| Anna | Reconstruct recorded RRF | Preserve requirements across fallback | 15 min |
| Theo | Reconcile publication, tool access and caller binding | Deploy, challenge scope and identify the executed build | 20 min |
| Jessica | Author Cedar ownership and distinguish five outcomes | Author RLS and keyed evidence, then investigate as staff | 25 min |

There are eight participant tasks and nine bounded source regions. Task 3A contains
two regions, 3B is operational, and 4B contains two SQL regions. Marker state does
not prove execution. The 15-minute presenter introduction is outside the participant
guides; 75 minutes of labs plus five recovery and five closing minutes follow it.
These are planning targets, not measured completion times.

## Material implementation changes

- Inventory model/prompt boilerplate is supplied; the authored work is the business
  result contract and actual tool use. Unknown product and zero stock remain distinct.
- Anna's old pool-size edit is replaced by the hard/soft search-plan contract. The
  unfinished fallback refuses to broaden a request. Strict retrieval runs first and
  only constructs fallback attempts if its result is short.
- The local plan checker rejects lost constraints, lost exclusions, mutation of the
  original request and unrecorded relaxation. The guide separately requires the exact
  live comparison and database assertions; a Python pass cannot stand in for SQL proof.
- Theo's publication and caller-binding edits are one task. The UI marks deployment
  evidence as required instead of inferring deployment from edited source.
- Jessica authors one ownership predicate used by USING and WITH CHECK. The supplied
  worksheet checks owned, foreign, missing and unmapped identities under runtime roles
  and rolls back policy changes and writes. Keyed absence requires an allowed control.
- The five governance outcomes preserve the difference between identity, permission,
  business rejection, commit and suppressed output. RLS trusts application-established
  context; it does not independently verify Cognito tokens. Operator stops at review.
- Guides, source markers, reset manifest, build-state reporting, learning notes,
  workbench connections and the Lab Collection now use the same A/B sequence.

## Validation evidence

Logs are preserved in this directory's `evidence/` folder.

| Check | Result | Boundary |
|---|---|---|
| Focused source suite | PASS: 366 passed, 12 skipped | Before final lazy-fallback fix |
| Affected retrieval/receipt suite after that fix | PASS: 71 passed | Includes strict-satisfied request regression; overlaps the source suite |
| Frontend interaction checks | PASS: 44 tests | Four affected test files |
| Frontend production build | PASS | TypeScript and Vite |
| Studio automated checks | PASS: 109 tests | Includes real local PostgreSQL RLS fixtures and wrong-implementation rejection |
| Exercise reset check | PASS: nine regions | Source reset shape, not deployed completion |
| Required-path size | PASS: 5,377 prose words and 27 Bash blocks | Excludes optional expanders and code from prose; not a timing proof |
| Studio content validator | BLOCKED: three old-pin references | New source files are absent from the currently pinned commit |
| Native PowerPoint review | PASS: all 14 physical slides | Normal opening, progressive reveals and hidden-reference skipping checked |
| Browser orientation | PASS for inspected routes | Lab Collection, Lab 2/4 workbench details and Jessica Operator link |
| Managed execution and authenticated Operator investigation | NOT RUN | Browser correctly reached Operator sign-in requirement |
| Timed fresh-account rehearsal | NOT RUN | Required before event-readiness claims |

The three source-pin findings are `workshop/learning-notes.md`,
`scripts/lab2_plan_contract_check.py`, and `workshop/README.md`. They exist in the
working tree but not in the pinned revision. No validator rule was weakened to
hide this release dependency.

## Presentation and captures

Use the Studio file
`static/presentations/pellier-governed-introduction-riv26-2026-09-21-v4.pptx`.
Its SHA-256 is
`2f23b25e970c61b9aec024779854baef6257e6dc22e8b0874de4b37abc40fd19`.
The undated introduction alias contains the same bytes.

One deck contains 12 core slides and two hidden references. The workshop access
slide is physically last. Current Lab Collection portraits, real product photos,
blue/purple AgentCore line icons, black re:Invent styling and slow click reveals
are retained. All 14 slides were reviewed in native PowerPoint Slide Show on
22 September. The rejected merge that required repair was not used as the final
artifact. Captures and manifests are in Studio's `docs/intro-captures/2026-09-22-v4/`;
the corresponding lab-guide architecture images were updated.

Replace `EVENT ACCESS CODE` before presenting. No video has been recorded or embedded.

## Release continuation

Review and publish the intended source changes, verify the exact remote commit,
then set the Studio source revision to that full SHA and rerun release validation.
Studio synchronization, commit/push and publication remain owner-managed. Run the
timed fresh-account workshop, including managed deployment, the live evidence checks,
Operator authentication, cleanup and recovery cut points. Earlier infrastructure or
hosted-release findings are not closed by this local curriculum pass.


## Presenter and participant focus follow-up

The 22 September v5 introduction is now in the owner’s DAT416 event folder, outside Workshop Studio static assets. The opening matches the agentic-retail premise and uses actual Storefront, Observatory and Operator screenshots with provenance. It has 13 core slides, two hidden references and workshop access last. Earlier decks were relocated with checksums; same-named differing versions were preserved in the event archive.

Participant guides no longer expose facilitator duties, pre-event Memory preparation, internal timing-readiness status or presentation downloads. They retain all eight tasks and task-specific acceptance checks. Fifty-one Studio validator tests pass; the content validator still reports only the same three files absent from the existing source pin. No source commit, push, re-pin or Studio publication was performed in this follow-up.
