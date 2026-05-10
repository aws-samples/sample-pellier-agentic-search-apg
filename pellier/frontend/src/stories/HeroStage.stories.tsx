/**
 * HeroStage.stories — visual regression coverage for the 8 rotating intents.
 *
 * Owned by task 7.2 (`tests/visual-regression/README.md`). Each story pins
 * a single intent so Chromatic captures a deterministic image per intent
 * per viewport instead of a flaky rotating snapshot.
 *
 * Requirements: Req 1.3 (hero behavior), Req 5.2.1–5.2.3 (breakpoints),
 * Req 1.3.3 (productOverride rendering for intent 2).
 *
 * This file imports from `@storybook/react`, which is not installed yet.
 * See `tests/visual-regression/README.md` for setup.
 */
import type { Meta, StoryObj } from '@storybook/react'
import HeroStage from '../components/HeroStage'
import { INTENTS, type Intent } from '../copy'

/**
 * Helper that returns a one-intent array so HeroStage freezes on a
 * specific intent for the entire snapshot window. The component's
 * rotation logic still runs but has nothing to advance to, so the
 * captured frame is stable.
 */
const single = (id: number): Intent[] => {
  const match = INTENTS.find((intent) => intent.id === id)
  if (!match) {
    throw new Error(`Unknown intent id ${id}`)
  }
  return [match]
}

const meta: Meta<typeof HeroStage> = {
  title: 'Boutique/HeroStage',
  component: HeroStage,
  parameters: {
    // Hero stage is tall; full-screen layout matches production chrome.
    layout: 'fullscreen',
    chromatic: {
      viewports: [375, 768, 1280],
      // The Ken Burns slow-zoom is a 14s animation; pausing at end is
      // enough to get a deterministic frame without disabling the
      // animation entirely (which would hide timing regressions).
      pauseAnimationAtEnd: true,
      delay: 500,
    },
  },
}

export default meta

type Story = StoryObj<typeof HeroStage>

export const Intent1_SummerWalks: Story = {
  name: "Intent 1 — long summer walks",
  args: { intents: single(1) },
}

export const Intent2_RunnerGift: Story = {
  name: "Intent 2 — gift for someone who runs (productOverride)",
  args: { intents: single(2) },
  // Req 1.3.3: this intent renders the Featherweight Trail Runner
  // productOverride rather than a catalog lookup. Verified by pixel.
}

export const Intent3_WarmEvenings: Story = {
  name: "Intent 3 — warm evenings out",
  args: { intents: single(3) },
}

export const Intent4_TravelPieces: Story = {
  name: "Intent 4 — pieces that travel well",
  args: { intents: single(4) },
}

export const Intent5_SlowSundayMornings: Story = {
  name: "Intent 5 — slow Sunday mornings",
  args: { intents: single(5) },
}

export const Intent6_LinenGoldenHour: Story = {
  name: "Intent 6 — linen at golden hour",
  args: { intents: single(6) },
}

export const Intent7_CozyCoolNights: Story = {
  name: "Intent 7 — cozy layer for cool summer nights",
  args: { intents: single(7) },
}

export const Intent8_RelaxedMarkets: Story = {
  name: "Intent 8 — weekend markets",
  args: { intents: single(8) },
}
