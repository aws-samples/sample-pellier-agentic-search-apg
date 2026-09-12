import { UsersRound } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { MEMBERSHIP, MEMBERSHIP_RUNGS } from '../../data/membership'
import { useClientBook } from '../hooks/useClientBook'

export default function ClientBookNavigation() {
  const { pathname, search, hash } = useLocation()
  const { book, error } = useClientBook()
  const membership = new URLSearchParams(search).get('membership')
  const atBook = pathname === '/operator' || pathname === '/operator/'
  const atChat = pathname === '/operator/chat'
  const atClient = pathname.startsWith('/operator/clients/') && !hash.startsWith('#operator-concierge')
  const all = atBook && (!membership || membership === 'all')

  return (
    <div className="operator-book-navigation">
      <Link
        to="/operator?membership=all"
        className={`operator-topbar-link${all || atClient ? ' operator-topbar-link-active' : ''}`}
        aria-current={all ? 'page' : undefined}
        title="All clients"
      >
        <UsersRound className="operator-topbar-icon" aria-hidden />
        <span className="operator-topbar-label">Client book</span>
        {book ? <span className="operator-book-nav-count">{book.total}</span> : null}
      </Link>
      <nav className="operator-membership-nav" aria-label="Client tiers">
        <p>Membership</p>
        {[...MEMBERSHIP_RUNGS].reverse().map(rung => (
          <Link
            key={rung}
            to={`${atChat ? '/operator/chat' : '/operator'}?membership=${rung}`}
            aria-current={(atBook || atChat) && membership === rung ? 'page' : undefined}
            title={`${MEMBERSHIP[rung].descriptor}. ${MEMBERSHIP[rung].earns}.`}
          >
            <span className="operator-membership-dot" data-rung={rung} aria-hidden="true" />
            <span>{MEMBERSHIP[rung].label}</span>
            {book ? <span className="operator-book-nav-count">{book.byMembership[rung] ?? 0}</span> : null}
          </Link>
        ))}
      </nav>
      {error ? <p className="operator-membership-note">
        {['authentication_required', 'invalid_credentials', 'operator_sign_in_required', 'operator_group_required'].includes(error)
          ? 'Counts available after operator sign-in.'
          : 'Client counts unavailable.'}
      </p> : null}
    </div>
  )
}
