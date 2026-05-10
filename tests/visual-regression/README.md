# Visual Regression — Scaffolding

This directory documents the visual regression strategy for the Pellier
storefront. Task 7.2 in `.kiro/specs/pellier-storefront/tasks.md` owns
this scope and ties back to Requirements 5.2.1–5.2.3 and 1.6.2 (parallax
timing fidelity) in `requirements.md`.

The files in this repo are **scaffolding only**. A team picking this up can
wire the tooling by following the setup steps below; CI will fail on
unapproved pixel diffs once the `CHROMATIC_PROJECT_TOKEN` secret is set.

## Decision: Chromatic (not Percy)

Both Chromatic and Percy snapshot hosted components and block PRs on
unapproved pixel diffs. We picked Chromatic for three reasons:

1. **First-class Storybook integration.** Chromatic was built by the
   Storybook team. `npx chromatic` reads `.storybook/` directly, so the
   story files in `pellier/frontend/src/stories/` double as both
   documentation and the snapshot source. No second "what to snapshot"
   config.
2. **Viewport coverage via Storybook parameters.** We already need to
   prove Req 5.2.1–5.2.3 at mobile (375px), tablet (768px), desktop
   (1280px). Chromatic snapshots each viewport listed in a story's
   `parameters.chromatic.viewports`, so one story renders three
   breakpoints without any runtime fork.
3. **Free tier fits workshop cadence.** 5,000 snapshots/month is plenty
   for a workshop repo; Percy's free tier is tighter and its per-seat
   pricing is heavier for an open-source-adjacent project.

Record this choice in the PR description so reviewers see the rationale
without opening this file.

## What gets snapshotted

Per task 7.2:

- **Home page** — mobile (375px), tablet (768px), desktop (1280px).
- **Hero stage** — each of the 8 rotating intents, at all three viewports.
- **Storyboard route** — signed-out and signed-in.
- **Discover route** — signed-out (sign-in CTA variant) and signed-in
  (personalized grid variant).

The story files in `pellier/frontend/src/stories/` enumerate these
variants:

- `HomePage.stories.tsx`
- `HeroStage.stories.tsx` (8 intent variants)
- `StoryboardPage.stories.tsx` (signed-in, signed-out)
- `DiscoverPage.stories.tsx` (signed-in, signed-out)

Each story pins its snapshot viewports via
`parameters.chromatic.viewports = [375, 768, 1280]`.

## Files in this scaffolding

```
.github/workflows/chromatic.yml                       # CI workflow (requires CHROMATIC_PROJECT_TOKEN)
pellier/frontend/.storybook/main.ts             # Storybook config (framework, stories glob)
pellier/frontend/.storybook/preview.tsx         # Global decorators (AuthContext mock, fonts, BG)
pellier/frontend/src/stories/HomePage.stories.tsx
pellier/frontend/src/stories/HeroStage.stories.tsx
pellier/frontend/src/stories/StoryboardPage.stories.tsx
pellier/frontend/src/stories/DiscoverPage.stories.tsx
tests/visual-regression/README.md                     # This file
```

None of these files run today. The stories import from `@storybook/react`
and `@storybook/react-vite`, which are not yet installed. Storybook is a
heavy dependency surface (100+ transitive packages) so we intentionally
did not add it to `package.json`. Follow the setup steps below when the
team is ready to turn this on.

## Setup (when turning this on)

One-time, run from `pellier/frontend/`:

```bash
npx storybook@latest init --builder vite --type react --yes
# then add the viewport addon if the init didn't pull it:
npm install --save-dev @storybook/addon-viewport @storybook/react @storybook/react-vite
npm install --save-dev chromatic
```

Storybook's init script writes its own `.storybook/main.ts` and
`preview.tsx`. Replace those with the versions in this repo so the glob
matches `src/stories/**/*.stories.tsx` and so the AuthContext decorator
applies globally.

Add two scripts to `pellier/frontend/package.json`:

```json
{
  "scripts": {
    "storybook": "storybook dev -p 6006",
    "build-storybook": "storybook build",
    "chromatic": "chromatic --exit-zero-on-changes"
  }
}
```

In the GitHub repo settings, add a secret named `CHROMATIC_PROJECT_TOKEN`
(get it from <https://www.chromatic.com/start> after linking the project).
The workflow at `.github/workflows/chromatic.yml` reads this secret.

Verify locally:

```bash
cd pellier/frontend
npm run storybook   # open http://localhost:6006 and confirm every story renders
npm run build-storybook
npx chromatic --project-token=$CHROMATIC_PROJECT_TOKEN
```

The first Chromatic run accepts every snapshot as the baseline. Subsequent
PRs surface a "Review changes" link in the PR status; unapproved diffs
keep the check red.

## What "done" looks like

Task 7.2's Done-When: **CI fails on unapproved pixel diffs.** After the
setup steps above:

- PR opens → `chromatic` workflow runs `npm run build-storybook` and
  uploads the build to Chromatic.
- Chromatic compares snapshots against the accepted baseline.
- Any unapproved diff keeps the required `UI Tests` check red.
- A reviewer clicks through to Chromatic, accepts (or rejects) each
  diff, and the check flips green.

Approval state is tracked per-story-per-viewport in Chromatic, not in the
repo — that is intentional, so UI tweaks don't require pushing image
fixtures.

## Relationship to other tests

- Unit tests (`*.test.tsx`) cover behavior and structure; they do not
  see pixels.
- E2E tests (`tests/e2e/`) cover full Cognito + API integration; they
  run Chromium but don't snapshot.
- **Chromatic** is the only layer that catches regressions like
  "someone changed a border-radius", "the hero image dropped to 400px",
  or "the parallax card starting opacity drifted".

Req 1.6.2 calls out specific opacity/transform start values and a
cubic-bezier easing curve for the product card parallax reveal. Those
are verifiable only as pixels, not as DOM assertions, which is why this
task sits alongside the unit tests rather than replacing them.
