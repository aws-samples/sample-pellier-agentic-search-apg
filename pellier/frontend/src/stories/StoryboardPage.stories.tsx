/**
 * StoryboardPage.stories — visual regression for the /storyboard route.
 *
 * Owned by task 7.2. Snapshots both auth states at mobile / tablet /
 * desktop per Req 5.2.1–5.2.3.
 *
 * The Storyboard route itself (Req 1.13.1) does not render different
 * content for signed-in vs signed-out visitors — it always shows the
 * 3-card teaser grid and the ComingSoonLine. The two stories below
 * capture both states anyway so that any future divergence (e.g. a
 * "saved for you" ribbon) lands in the snapshot without needing a
 * new story file.
 *
 * This file imports from `@storybook/react`, which is not installed
 * yet. See `tests/visual-regression/README.md` for setup.
 */
import type { Meta, StoryObj } from '@storybook/react'
import StoryboardPage from '../pages/StoryboardPage'

const meta: Meta<typeof StoryboardPage> = {
  title: 'Boutique/StoryboardPage',
  component: StoryboardPage,
  parameters: {
    layout: 'fullscreen',
    route: '/storyboard',
    chromatic: {
      viewports: [375, 768, 1280],
      pauseAnimationAtEnd: true,
      // StoryboardTeaser fades in on scroll reveal; wait for it.
      delay: 1200,
    },
  },
}

export default meta

type Story = StoryObj<typeof StoryboardPage>

export const SignedOut: Story = {
  name: 'Signed out',
  parameters: {
    authState: { user: null, preferences: null },
  },
}

export const SignedIn: Story = {
  name: 'Signed in',
  parameters: {
    authState: {
      user: {
        sub: 'cognito-sub-storybook',
        email: 'ava@example.com',
        givenName: 'Ava',
      },
      preferences: {
        vibe: ['serene'],
        colors: ['warm'],
        occasions: ['slow'],
        categories: ['linen'],
      },
    },
  },
}
