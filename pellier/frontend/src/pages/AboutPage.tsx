/**
 * AboutPage — dedicated `/about` route.
 *
 * Renders just the Editorial Brief workshop-credit section, wrapped in
 * the standard Boutique chrome (Header + Footer). Keeps the Boutique
 * main page lean and gives "About" in the nav an honest destination.
 */
import { useNavigate } from 'react-router-dom'
import EditorialBrief from '../components/EditorialBrief'
import Footer from '../components/Footer'
import Header, { type NavItem } from '../components/Header'
import { useUI } from '../contexts/UIContext'
import { cssVar as c } from '../design/cssVars'

const NAV_ROUTES: Record<NavItem, string> = {
  home: '/',
  shop: '/#shop',
  storyboard: '/storyboard',
  stories: '/storyboard',
  discover: '/discover',
  about: '/about',
  account: '/',
  'ask-pellier': '/',
}

export default function AboutPage() {
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
      data-testid="about-page"
      style={{ minHeight: '100vh', background: c.bg }}
    >
      <Header current="about" onNavigate={handleNavigate} />
      <main>
        <EditorialBrief />
      </main>
      <Footer />
    </div>
  )
}
