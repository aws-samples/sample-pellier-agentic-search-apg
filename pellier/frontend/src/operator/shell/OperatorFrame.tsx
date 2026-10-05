/**
 * The Operator desk: the staff surface where Jessica's case is decided.
 *
 * A three-column desk under the shared header (which carries the wordmark
 * and the theme control for every surface): the rail with the clients or the
 * reviews, the record, and the investigation or the decision. The desk's own
 * bar carries the two sections and the signed-in staff member, Nadia, who
 * signs in with her password; there is no one-click staff sign-in.
 *
 * The desk reads the staff session through its own `AuthProvider`, so a
 * shopper signed in on the storefront in another tab of the same browser never
 * replaces Nadia here, and signing either one out leaves the other.
 *
 * Mounted on `.operator-root`, in direction A's tokens, so both themes apply
 * with nothing to restyle.
 */
import React, { createContext, useContext, useEffect } from 'react'
import { LogOut, User } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from '../../contexts/AuthContext'
import { ClientBookContext, useClientBookResource } from '../hooks/useClientBook'
import { ReviewQueueContext, useQueueResource, useReviewQueue } from '../hooks/useReviewQueue'
import { redirectToSignIn } from '../../utils/auth'
import ClientAvatar from '../components/ClientAvatar'
import { presentIdentity } from '../components/ProposedCreditCard'
import { ClientList } from '../surfaces/ClientBook'
import { ReviewList } from '../surfaces/ReviewQueue'
import '../styles/operator.css'

const OperatorQueueRefreshContext = createContext<() => void>(() => undefined)

/** Tab, history and bookmark titles for each desk route. */
export function operatorTitleForPath(pathname: string): string {
  if (pathname.startsWith('/operator/clients/')) return 'Client, Pellier Operator'
  if (pathname.startsWith('/operator/reviews/')) return 'Review, Pellier Operator'
  if (pathname.startsWith('/operator/reviews')) return 'Reviews, Pellier Operator'
  return 'Clients, Pellier Operator'
}

export function useOperatorQueueRefresh(): () => void {
  return useContext(OperatorQueueRefreshContext)
}

const PendingCount: React.FC = () => {
  const { queue, error } = useReviewQueue()
  if (error || !queue) return null
  return (
    <span className="op-bar-count" data-count={queue.pendingCount > 0 ? 'waiting' : 'clear'} data-testid="operator-reviews-link-count">
      {queue.pendingCount}
    </span>
  )
}

/** The signed-in staff member, or the way in. */
const StaffIdentity: React.FC = () => {
  const { user, isAuthenticated, loading, authUnavailable, logout } = useAuth()
  if (loading) return <span className="op-bar-identity" aria-label="Checking staff sign-in" />
  if (authUnavailable) return <span className="op-bar-identity">Session unavailable</span>
  if (isAuthenticated && user) {
    const name = presentIdentity(user.username || user.givenName || user.email)
    return (
      <div className="op-bar-staff" data-testid="operator-staff">
        <ClientAvatar personaId={(user.username || '').toLowerCase()} name={name} />
        <span className="op-bar-identity">{name}</span>
        <button type="button" className="op-button op-button-quiet" onClick={logout} title={`Sign out ${name}`} aria-label={`Sign out ${name}`}>
          <LogOut size={14} aria-hidden />
          <span>Sign out</span>
        </button>
      </div>
    )
  }
  return (
    <button type="button" className="op-button" onClick={() => redirectToSignIn('email')} data-testid="operator-sign-in">
      <User size={14} aria-hidden />
      <span>Staff sign-in</span>
    </button>
  )
}

const OperatorDesk: React.FC = () => {
  const { pathname } = useLocation()
  const reviews = pathname.startsWith('/operator/reviews')
  const queue = useQueueResource()
  const clients = useClientBookResource()

  useEffect(() => {
    const previous = document.title
    document.title = operatorTitleForPath(pathname)
    return () => { document.title = previous }
  }, [pathname])

  return (
    <ClientBookContext.Provider value={clients}>
      <ReviewQueueContext.Provider value={queue}>
        <OperatorQueueRefreshContext.Provider value={queue.refresh}>
          <div className="operator-root" data-testid="operator-root">
            <div className="op-bar">
              <nav className="op-bar-sections" aria-label="Operator sections">
                <NavLink to="/operator" end={false} className={({ isActive }) => `op-bar-link${isActive && !reviews ? ' op-bar-link-active' : ''}`} aria-current={!reviews ? 'page' : undefined}>
                  Clients
                </NavLink>
                <NavLink to="/operator/reviews" className={({ isActive }) => `op-bar-link${isActive ? ' op-bar-link-active' : ''}`} data-testid="operator-reviews-link">
                  Reviews
                  <PendingCount />
                </NavLink>
              </nav>
              <StaffIdentity />
            </div>
            <div className="op-desk" data-section={reviews ? 'reviews' : 'clients'}>
              <aside className="op-rail" aria-label={reviews ? 'Reviews' : 'Clients'}>
                {reviews ? <ReviewList /> : <ClientList />}
              </aside>
              <main className="op-main" id="main-content" tabIndex={-1}>
                <Outlet />
              </main>
            </div>
          </div>
        </OperatorQueueRefreshContext.Provider>
      </ReviewQueueContext.Provider>
    </ClientBookContext.Provider>
  )
}

/** The desk, on the staff session. */
const OperatorFrame: React.FC = () => (
  <AuthProvider surface="staff">
    <OperatorDesk />
  </AuthProvider>
)

export default OperatorFrame
