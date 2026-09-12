# Pellier frontend guidance

This directory owns the React/Vite Pellier and Pellier Observatory experiences.
Read the repository `CLAUDE.md` and `VOICE.md` before editing.

## Product boundaries

- Pellier is a fast, editorial shopping experience.
- Pellier Observatory is a core participant surface for labs and evidence. **It has no
  sidebar.** `ObservatoryFrame` renders the top bar and an outlet, so the whole
  navigation is two tabs (Lab Collection, Workbench) plus the
  `ReferencesIndex` directory. A `Sidebar` component with its own group names
  and its own labels for the same routes rendered nowhere for six days while
  its tests passed against a directly-mounted copy; it has been deleted. Do not
  reintroduce a second navigation without deleting this one.
- `ReferencesIndex` is that navigation, grouped by task: Proof views, Replay a
  turn, Inspect the build, Measure. One label per destination, title case. A new
  surface needs an entry here or it is unreachable.
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
