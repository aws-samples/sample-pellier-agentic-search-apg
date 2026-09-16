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
            <h1>One request,<br /><em>from question to evidence.</em></h1>
            <p className="pellier-how-lead">Pellier answers from live product and customer records, checks them before it promises anything, and writes down what it did.</p>
            <p>Follow three recorded requests: Marco’s opening linen request, Jessica’s service investigation, and a cross-customer request Cedar refused. Each one connects the recorded steps to the source detail behind them and the matching workshop exercise.</p>
            <div className="pellier-how-links">
              <Link className="pellier-action pellier-action--primary" to="/observatory/workbench">Inspect a live request</Link>
              <Link className="pellier-action pellier-action--ghost" to="/#shop">Back to the collection</Link>
            </div>
            <p className="pellier-how-caption">Each example identifies when it was recorded. Prices, availability, and policy configuration may have changed since that request.</p>
          </div>
          <div className="pellier-how-demo">
            <TraceScenarioLoop showDetails />
          </div>
        </div>
        <section className="pellier-how-surfaces" aria-label="The three Pellier surfaces">
          <article>
            <span className="pellier-how-number">01</span>
            <h2>The storefront</h2>
            <p>A premium storefront you can ask questions in. Ask for a piece, compare options, and see the price and the stock count behind every recommendation before you buy.</p>
            <Link to="/">Visit the storefront <ArrowUpRight size={15} aria-hidden /></Link>
          </article>
          <article>
            <span className="pellier-how-number">02</span>
            <h2>The Operator desk</h2>
            <p>Where staff work a case. Open a client record, read the orders, tickets, and returns behind it, then approve or decline the action an investigation proposes. Every decision is recorded with the operator who made it.</p>
            <Link to="/operator">Open the Operator desk <ArrowUpRight size={15} aria-hidden /></Link>
          </article>
          <article>
            <span className="pellier-how-number">03</span>
            <h2>The Observatory</h2>
            <p>Where you inspect the work. See the route taken, the tool results, the caller identity, and the policy decision behind a request. Replay saved evidence or run a new request.</p>
            <Link to="/observatory">Open the Observatory <ArrowUpRight size={15} aria-hidden /></Link>
          </article>
        </section>
      </main>
      <Footer />
    </div>
  )
}
