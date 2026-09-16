import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import Header, { type NavItem } from '../components/Header'
import Footer from '../components/Footer'
import { useUI } from '../contexts/UIContext'
import TraceScenarioLoop from '../shared/trace/TraceScenarioLoop'
import '../styles/how-pellier-works.css'

const NAV_ROUTES: Record<NavItem, string> = {
  home: '/', shop: '/#shop', storyboard: '/storyboard', stories: '/storyboard',
  discover: '/discover', about: '/about', account: '/', 'ask-pellier': '/',
  'how-it-works': '/how-pellier-works',
}

export default function HowPellierWorksPage() {
  const navigate = useNavigate()
  const { openModal } = useUI()
  useEffect(() => {
    const previous = document.title
    document.title = 'How Pellier works'
    return () => { document.title = previous }
  }, [])
  function handleNavigate(item: NavItem) {
    if (item === 'ask-pellier') return openModal('drawer')
    if (item === 'account') return openModal('auth')
    navigate(NAV_ROUTES[item])
  }
  return (
    <div className="pellier-page-surface min-h-dvh bg-cream-50">
      <Header current="how-it-works" onNavigate={handleNavigate} />
      <main className="pellier-how">
        <div className="pellier-how-intro">
          <div className="pellier-how-copy">
            <p className="pellier-how-eyebrow">How Pellier works</p>
            <h1>A considered answer.<br /><em>A clear record.</em></h1>
            <p className="pellier-how-lead">A good recommendation begins with what is actually on the shelf. Follow one request from the question to the evidence behind the answer.</p>
            <p>Three recorded requests show the boutique, the Operator desk, and a Cedar policy boundary at work. Open a numbered step to inspect its evidence, then try a request of your own.</p>
            <div className="pellier-how-links">
              <Link to="/observatory/workbench">Inspect a live request <ArrowUpRight size={16} aria-hidden /></Link>
              <Link to="/#shop">Back to the collection <ArrowUpRight size={16} aria-hidden /></Link>
            </div>
            <p className="pellier-how-caption">Each example identifies when it was recorded. Prices, availability, and policy configuration may have changed since that request.</p>
          </div>
          <div className="pellier-how-demo">
            <TraceScenarioLoop />
          </div>
        </div>
        <section className="pellier-how-surfaces" aria-label="Three ways to explore Pellier">
          <article>
            <span className="pellier-how-number">01</span>
            <h2>The boutique</h2>
            <p>Ask about a piece, compare options, or check availability. The conversation stays focused on the decision in front of you.</p>
            <Link to="/">Visit the storefront <ArrowUpRight size={15} aria-hidden /></Link>
          </article>
          <article>
            <span className="pellier-how-number">02</span>
            <h2>The Operator desk</h2>
            <p>Follow an investigation as its evidence arrives. Review a proposed action separately, with the person approving it and its eventual result kept on record.</p>
            <Link to="/operator">Open Operator <ArrowUpRight size={15} aria-hidden /></Link>
          </article>
          <article>
            <span className="pellier-how-number">03</span>
            <h2>The Observatory</h2>
            <p>Inspect the route, tool results, identity, and policy boundary behind a request. Replay saved evidence or run a new turn to see the application at work.</p>
            <Link to="/observatory">Explore the Observatory <ArrowUpRight size={15} aria-hidden /></Link>
          </article>
        </section>
      </main>
      <Footer />
    </div>
  )
}
