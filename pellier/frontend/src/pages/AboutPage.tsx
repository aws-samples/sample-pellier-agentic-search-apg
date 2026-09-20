/**
 * AboutPage — dedicated `/about` route.
 *
 * Renders just the Editorial Brief workshop-credit section, wrapped in
 * the standard Pellier chrome (Header + Footer). Keeps the Pellier
 * main page lean and gives "About" in the nav an honest destination.
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import EditorialBrief from '../components/EditorialBrief'
import Footer from '../components/Footer'
import Header, { type NavItem } from '../components/Header'
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

export default function AboutPage() {
  const navigate = useNavigate()
  const { openModal } = useUI()
  useEffect(() => {
    const previous = document.title
    document.title = 'About | Pellier'
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
      data-testid="about-page"
      className="pellier-page-surface min-h-dvh bg-cream-50"
    >
      <Header current="about" onNavigate={handleNavigate} />
      <main>
        <EditorialBrief />
      </main>
      <Footer />
    </div>
  )
}
