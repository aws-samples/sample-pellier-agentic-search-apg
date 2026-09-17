/**
 * StoryboardPage - minimal `/storyboard` index route.
 *
 * Validates Requirements 1.13.1, 1.13.3, 1.13.4.
 *
 * Composition:
 *   - Header (sticky) with `current="stories"` so the Stories nav
 *     item takes the ink-highlighted current-page state (Req 1.13.4).
 *   - The 3-card StoryboardTeaser grid from the home page (Req 1.9 /
 *     4.8), reused as-is.
 *   - A single ComingSoonLine (`Coming soon - the full editorial hub
 *     arrives with the next Edit.`) in italic Fraunces (Req 1.13.1).
 *   - Footer, so the chrome matches the About page; the floating command
 *     pill stays off the editorial pages where it overlapped the prose.
 *     page (Req 1.13.1).
 *
 * The route is intentionally small - the full editorial hub lands in
 * a later Edit. Copy from copy.ts; Req 1.12 rules enforced there.
 */
import { useNavigate } from 'react-router-dom'
import FieldNotes from '../components/FieldNotes'
import Footer from '../components/Footer'
import Header, { type NavItem } from '../components/Header'
import StoryboardTeaser from '../components/StoryboardTeaser'
import { useUI } from '../contexts/UIContext'

const NAV_ROUTES: Record<NavItem, string> = {
  home: '/',
  shop: '/#shop',
  storyboard: '/storyboard',
  stories: '/storyboard',
  discover: '/discover',
  about: '/about',
  'how-it-works': '/how-pellier-works',
  account: '/',
  'ask-pellier': '/',
}

export default function StoryboardPage() {
  const navigate = useNavigate()
  const { openModal } = useUI()
  const handleNavigate = (item: NavItem) => {
    if (item === 'account') {
      openModal('auth')
      return
    }
    if (item === 'ask-pellier') {
      openModal('drawer')
      return
    }
    const target = NAV_ROUTES[item]
    if (target) navigate(target)
  }
  return (
    <div
      data-testid="storyboard-page"
      className="pellier-page-surface min-h-dvh bg-cream-50"
    >
      <Header current="stories" onNavigate={handleNavigate} />
      <main>
        <StoryboardTeaser headingLevel={1} />
        <FieldNotes />
      </main>
      <Footer />
    </div>
  )
}
