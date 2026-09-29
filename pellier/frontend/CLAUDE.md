# Pellier frontend guidance

This directory owns the React/Vite Pellier and Pellier Observatory experiences.
Read the repository `CLAUDE.md` and `VOICE.md` before editing.

## Product boundaries

- Pellier is a fast, editorial shopping experience.
- Pellier Observatory is a core participant surface for labs and evidence. **It has no
  sidebar.** Its top bar has two places: the Lab Collection and the Workbench. Every
  other view belongs to a lab and is reached from the lab guide or from the page that
  needs it. Routing, Workshop map and Settings were retired and redirect to the Lab
  Collection. A `Sidebar` component with its own group names once rendered nowhere for
  six days while its tests passed against a directly-mounted copy; it was deleted. Do
  not reintroduce a second navigation for the same destinations.
- `LabJourneyBar` (components/) is the lab guide: one sticky row under the shared
  surface navigation on the Storefront, Operator and Observatory while a lab is open.
  `shared/labJourney.ts` holds each lab's steps, copied from the Workshop Studio
  guide's required path in its order and words, and the current step per lab in
  localStorage. Code Editor and terminal steps carry no in-app link and are never
  marked done: a step behind the current one was visited, and the guide's terminal
  checks remain the proof. `labJourney.test.ts` fails if a step names a file or script
  missing from the repository, or links to a route the app does not serve; when the
  guide's steps change, change them here too. Its height joins
  `--pellier-chrome-height`; pin or size anything below the shared navigation from
  that token, not `--pellier-surface-bar-height`.
- `referenceCatalog.ts` is the one source for lab groups (`LAB_REFERENCE_GROUPS`) and
  each view's teaching question, evidence boundary, and implementation links. The Lab
  Collection keeps the full `WorkbenchResources` index; the Workbench keeps only the
  after-the-labs extensions. A reference inside a lab returns from its page title to
  the Workbench of the lab being followed; an extension offers "Return to Lab N in
  Workbench". New references must explain their lab purpose and belong to exactly one
  lab group or to the extensions.
- Each lab states its `lesson` (the transferable idea, two sentences) first: on the
  Workbench under the lab title and on its Lab Collection card. Keep it aligned with
  `workshop/story-arc.json` and the lab guide's "You will learn" line.
- Typography: Instrument Sans for every heading and title on the Observatory and the
  Operator desk. Fraunces is the storefront's voice; `observatory/styles/base.css` remaps
  the display tokens inside `.observatory-root` so an inline `var(--display)` cannot
  bring it back.
- Observatory connects Storefront conversations, Operator decisions, and system
  evidence. Do not label the whole surface optional or invent completion from
  visiting it. Individual extension exercises can be optional in the lab guide.
  Code Editor, curl, and SQL remain the canonical workshop proof.
- The one real build-state number (shipped tools, e.g. `16/17`) belongs beside
  the Tool Registry entry, where it is a fact that changes when the guided
  exercise lands. Never hardcode it: show an em dash when build state is
  unavailable, because a stale literal reads as a confident "not wired yet".
- The user made Observatory part of the core participant experience on
  September 12, 2026. Its top bar and global navigation carry no `Optional`
  badge. Mode labels distinguish running a request from reading evidence.
- **Application copy is self-paced; the lab guide is not.** No copy shipped in
  this app may route a participant through a facilitator, because the app also
  runs for anyone who clones the repo with no room around them. The Workshop
  Studio lab guide is the opposite case: it runs on a clock in a staffed room,
  so its escape hatches legitimately say "raise a hand" and name a table lead.
  Keep the boundary at the repository edge — never copy an app string that
  assumes a facilitator, and never strip a facilitator escape hatch out of the
  lab guide to match this rule.
- Code Editor, curl, and SQL remain the canonical proof surfaces.
- Pellier Observatory may summarize live evidence but must not invent or replace proof.
- Do not reintroduce the old Act I/II/III navigation.

## Interaction rules

- Preserve real SSE streaming. Do not simulate completion with a spinner or a
  client-only timeout.
- Keep thinking concise and answer quickly. Editorial typewriter treatment
  applies to answer text, not long internal narration.
- Keep catalog follow-ups grounded in returned products and actual variants.
- Use distinct visual states for policy denial, authentication setup,
  backend unavailability, and invalid requests.
- Human handoff is an explicit outcome, not a fallback for an ordinary
  partial catalog match.
- Use the existing icon library and design tokens.
- Keep SQL, code, IDs, and telemetry in JetBrains Mono; use the Pellier Observatory
  sans/display typography for labels and prose.
- Keep proof data backend-driven. Browser state is not evidence.

## Responsive and accessibility rules

- Check desktop and workshop-width layouts.
- Prevent overlapping controls, clipped labels, and unexpected layout shifts.
- Give icon-only controls accessible names and tooltips.
- Preserve visible focus states and semantic headings.
- Do not encode status by color alone.

## Frontend validation

From `pellier/frontend`:

```bash
npm test -- --run
npm run type-check
npm run lint
npm run build
npm audit --omit=dev --audit-level=high
```

For user-facing workflow changes, verify the live route in Chrome at both a
desktop viewport and a narrower workshop viewport. Check the console for
errors and confirm the referenced backend evidence is present.
