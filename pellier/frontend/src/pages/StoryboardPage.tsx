/**
 * Stories pairs three shopper introductions with their FieldNotes essays.
 * Shared storefront chrome stays visible; the floating command pill stays
 * off the editorial pages so it does not overlap the prose.
 */
import { useEffect } from 'react'
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
  useEffect(() => {
    const previous = document.title
    document.title = 'Stories | Pellier'
    return () => { document.title = previous }
  }, [])
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
