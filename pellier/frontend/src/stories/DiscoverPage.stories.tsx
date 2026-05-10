/**
 * DiscoverPage.stories — visual regression for the /discover route.
 *
 * Owned by task 7.2. Captures the two distinct auth variants at mobile,
 * tablet, and desktop per Req 5.2.1–5.2.3:
 *
 *   - Signed out → centered sign-in CTA (Req 1.13.2 signed-out branch).
 *   - Signed in  → personalized ProductGrid + ComingSoonLine
 *                  (Req 1.13.2 signed-in branch).
 *
 * This file imports from `@storybook/react`, which is not installed
 * yet. See `tests/visual-regression/README.md` for setup.
 */
import type { Meta, StoryObj } from '@storybook/react'
import DiscoverPage from '../pages/DiscoverPage'

const meta: Meta<typeof DiscoverPage> = {
  title: 'Boutique/DiscoverPage',
  component: DiscoverPage,
  parameters: {
    layout: 'fullscreen',
    route: '/discover',
    chromatic: {
      viewports: [375, 768, 1280],
      pauseAnimationAtEnd: true,
      delay: 1200,
    },
  },
}

export default meta

type Story = StoryObj<typeof DiscoverPage>

/** Signed out — centered sign-in CTA variant. */
export const SignedOut: Story = {
  name: 'Signed out (sign-in CTA)',
  parameters: {
    authState: { user: null, preferences: null },
  },
}

/** Signed in with preferences — personalized product grid variant. */
export const SignedIn: Story = {
  name: 'Signed in (personalized grid)',
  parameters: {
    authState: {
      user: {
        sub: 'cognito-sub-storybook',
        email: 'ava@example.com',
        givenName: 'Ava',
      },
      preferences: {
        vibe: ['creative', 'bold'],
        colors: ['warm', 'earth'],
        occasions: ['evening'],
        categories: ['linen', 'dresses'],
      },
    },
  },
}
