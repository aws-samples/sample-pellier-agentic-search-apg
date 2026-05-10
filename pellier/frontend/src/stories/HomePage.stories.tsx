/**
 * HomePage.stories — visual regression coverage for the storefront home.
 *
 * Owned by task 7.2. Snapshots the home page composition at mobile (375px),
 * tablet (768px), and desktop (1280px) viewports per Req 5.2.1–5.2.3.
 *
 * Per the component tree in `design.md` ("Frontend Component Tree"), the
 * home page is a composition of storefront pieces rather than a single
 * exported component. We assemble that composition here so Chromatic can
 * snapshot the page-level layout (section ordering, breakpoints, scroll
 * reveal start state) without relying on the legacy `App.tsx` chrome.
 *
 * This file imports from `@storybook/react`, which is not installed yet.
 * See `tests/visual-regression/README.md` for setup.
 */
import type { Meta, StoryObj } from '@storybook/react'
import AnnouncementBar from '../components/AnnouncementBar'
import AuthStateBand from '../components/AuthStateBand'
import CategoryChips from '../components/CategoryChips'
import CommandPill from '../components/CommandPill'
import Footer from '../components/Footer'
import Header from '../components/Header'
import HeroStage from '../components/HeroStage'
import LiveStatusStrip from '../components/LiveStatusStrip'
import ProductGrid from '../components/ProductGrid'
import RefinementPanel from '../components/RefinementPanel'
import StoryboardTeaser from '../components/StoryboardTeaser'

const CREAM = '#fbf4e8'

/**
 * Minimal home-page composition matching the design's Frontend
 * Component Tree. Kept local to the stories file so the production
 * chrome in `App.tsx` (workshop panels, debug overlays) does not leak
 * into the snapshot.
 */
function HomePageComposition() {
  return (
    <div style={{ minHeight: '100vh', background: CREAM }}>
      <AnnouncementBar />
      <Header current="home" />
      <main>
        <HeroStage />
        <AuthStateBand />
        <LiveStatusStrip />
        <CategoryChips />
        <ProductGrid />
        <RefinementPanel />
        <StoryboardTeaser />
      </main>
      <Footer />
      <CommandPill />
    </div>
  )
}

const meta: Meta<typeof HomePageComposition> = {
  title: 'Boutique/HomePage',
  component: HomePageComposition,
  parameters: {
    layout: 'fullscreen',
    route: '/',
    chromatic: {
      viewports: [375, 768, 1280],
      pauseAnimationAtEnd: true,
      // Give the parallax reveal a beat to settle so snapshots don't
      // catch cards mid-fade.
      delay: 1500,
    },
  },
}

export default meta

type Story = StoryObj<typeof HomePageComposition>

/** Signed-out visitor — the default band is the sign-in strip. */
export const SignedOut: Story = {
  name: 'Signed out (default)',
  parameters: {
    authState: { user: null, preferences: null },
  },
}

/**
 * Signed in with saved preferences — the curated banner replaces the
 * sign-in strip (mutually exclusive per Req 1.4).
 */
export const SignedInWithPreferences: Story = {
  name: 'Signed in with preferences',
  parameters: {
    authState: {
      user: {
        sub: 'cognito-sub-storybook',
        email: 'ava@example.com',
        givenName: 'Ava',
      },
      preferences: {
        vibe: ['minimal', 'serene'],
        colors: ['warm', 'neutral'],
        occasions: ['everyday', 'slow'],
        categories: ['linen'],
      },
    },
  },
}
