# Pellier frontend guidance

This directory owns the React and Vite app: the Storefront with Ask Pellier,
and the Operator. Read the repository `CLAUDE.md` and `VOICE.md` before
editing.

## Product boundaries

- Pellier has two surfaces. The **Storefront** (`/`, plus product pages and
  Stories) is a fast, editorial shopping experience with **Ask Pellier**, the
  chat panel docked beside the page on desktop; on phones it opens over the
  page. Shoppers are chosen in the panel or from the header; choosing one
  performs the workshop sign-in, and Pellier trusts the signed token, not the
  choice. The **Operator** (`/operator`) is the staff desk: clients, the
  Investigator and Planner's investigation, and the review queue where a
  person approves, declines or executes a credit.
- The **Builder view** is one global switch in the shared header
  (`components/turn/BuilderViewSwitch.tsx`). It shows "How it ranked" over the
  grid, each turn's Router step and tool calls in the dock, and the Operator's
  investigation steps. Off by default. It shows evidence the backend sent; it
  never invents proof, and Code Editor, curl and SQL remain the canonical
  workshop proof.
- There is no inspection surface and no lab navigation in the app. The lab
  guide lives in Workshop Studio. Old paths land on the Storefront
  (`src/App.routes.test.tsx`).
- Typography: Instrument Sans for every heading and title on every surface.
  Fraunces sets the pellier. wordmark and its square p. mark in
  `components/Wordmark.tsx` and nowhere else.
- Colors come from tokens only. `src/__tests__/token_guard.test.ts` fails on a
  hard-coded color, and on a Fraunces, display-token or serif reference outside
  the wordmark. Dark grounds are true black.
- `src/__tests__/copy_scanner.test.ts` runs the copy rules over `copy.ts` and
  the copy files in `data/`.
- **Application copy is self-paced; the lab guide is not.** No copy shipped in
  this app may route a participant through a facilitator, because the app also
  runs for anyone who clones the repo with no room around them. The Workshop
  Studio lab guide is the opposite case: it runs on a clock in a staffed room,
  so its escape hatches legitimately say "raise a hand" and name a table lead.
  Keep the boundary at the repository edge: never copy an app string that
  assumes a facilitator, and never strip a facilitator escape hatch out of the
  lab guide to match this rule.
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
- Keep SQL, code, IDs, and telemetry in JetBrains Mono; use Instrument Sans
  for labels and prose.
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
