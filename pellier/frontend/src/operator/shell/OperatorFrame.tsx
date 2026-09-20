/**
 * Pellier Operator shell.
 *
 * A compact work-area rail beneath the shared three-surface navigation.
 * An open review keeps the authenticated queue beside the case, so inspecting
 * one request does not lose the rest of the desk.
 *
 * Mounted on `.operator-root`, which is intentionally not nested inside
 * `.pellier-page-surface` or `.observatory-root`. Both of those force headings
 * to sans, one of them with `!important`, so an editorial serif heading is
 * only reachable from a scope outside them. All tokens live on `:root`, so
 * nothing is lost by sitting outside.
 */

import React, {
  createContext,
  useContext,
  useEffect,
} from 'react'
import { ClipboardCheck, MessageCircle, User } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import ReviewQueuePanel from '../components/ReviewQueuePanel'
import ClientBookNavigation from '../components/ClientBookNavigation'
import { useAuth } from '../../contexts/AuthContext'
import { ReviewQueueContext, useQueueResource, useReviewQueue } from '../hooks/useReviewQueue'
import { ClientBookContext, useClientBookResource } from '../hooks/useClientBook'
import { redirectToSignIn } from '../../utils/auth'
import '../styles/operator.css'
import '../styles/operator-desk.css'

const OperatorQueueRefreshContext = createContext<() => void>(() => undefined)

/**
 * Tab, history and bookmark titles for each desk route. Every route used to
 * inherit the storefront's title from index.html, so an operator with the
 * storefront, the desk and the Observatory open could not tell the tabs apart.
 */
const ROUTE_TITLES: ReadonlyArray<[prefix: string, title: string]> = [
  ['/operator/chat', 'Operator chat'],
  ['/operator/clients/', 'Client'],
  ['/operator/reviews/', 'Review'],
  ['/operator/reviews', 'Action Queue'],
]

export function operatorTitleForPath(pathname: string): string {
  const match = ROUTE_TITLES.find(([prefix]) => pathname.startsWith(prefix))
  return `${match ? match[1] : 'Clients'} · Pellier Operator`
}

/**
 * Invalidates the shell's queue count after a nested route changes a review.
 *
 * The default no-op keeps ReviewRecord independently renderable in focused
 * tests and Storybook-style surfaces that do not mount the operator shell.
 */
export function useOperatorQueueRefresh(): () => void {
  return useContext(OperatorQueueRefreshContext)
}

/**
 * The count of prepared requests waiting on a person.
 *
 * Always shows a real state once the queue has been read, including zero. A
 * failed read stays visibly distinct from an empty queue: the status names
 * the problem rather than using a symbol that could be mistaken for a control.
 */
const PendingReviewLink: React.FC = () => {
  const { queue, error } = useReviewQueue()
  const pending = queue?.pendingCount ?? null
  const signInRequired = Boolean(error && ['authentication_required', 'invalid_credentials', 'operator_sign_in_required', 'operator_group_required'].includes(error))
  const unreachable = Boolean(error && !signInRequired)

  return (
    <NavLink
      to="/operator/reviews"
      className={({ isActive }) =>
        `operator-topbar-link${isActive ? ' operator-topbar-link-active' : ''}`
      }
      data-testid="operator-reviews-link"
      title="Action Queue"
    >
      <ClipboardCheck className="operator-topbar-icon" aria-hidden />
      <span className="operator-topbar-label">Action Queue</span>
      {signInRequired ? (
        <span
          className="operator-topbar-count"
          data-count="sign-in"
          data-testid="operator-reviews-count"
          title="Sign in as an operator to read the action queue"
        >
          {/* The slot carries queue state. Spelling out the instruction here
              made it the third "sign in" on a gated screen, beside the topbar
              control and the page's own primary action, so it states the
              state and leaves the asking to them. The title attribute keeps
              the full explanation for anyone who needs it. */}
          Locked
        </span>
      ) : unreachable ? (
        <span
          className="operator-topbar-count"
          data-count="unavailable"
          data-testid="operator-reviews-count"
          title="The action queue could not be read"
        >
          Queue unavailable
        </span>
      ) : pending === null ? null : (
        <span
          className="operator-topbar-count"
          data-count={pending > 0 ? 'waiting' : 'clear'}
          data-testid="operator-reviews-count"
          title={
            pending > 0
              ? `${pending} prepared request${pending === 1 ? '' : 's'} waiting on a person`
              : 'No prepared request is waiting'
          }
        >
          {pending}<span className="sr-only"> pending</span>
        </span>
      )}
    </NavLink>
  )
}

const OperatorAuthControl: React.FC = () => {
  const { user, isAuthenticated, loading, authUnavailable, logout } = useAuth()

  if (loading) {
    return (
      <span
        className="pellier-account-pill operator-auth-control operator-auth-loading"
        aria-label="Checking operator sign-in"
      />
    )
  }

  if (authUnavailable) {
    return <span className="operator-auth-identity">Session unavailable</span>
  }

  if (isAuthenticated && user) {
    return (
      <div className="operator-auth-account">
        <span
          className="operator-auth-identity"
          title={`Signed in as ${user.email}`}
        >
          {presentIdentity(user.givenName || user.email)}
        </span>
        <button
          type="button"
          className="pellier-account-pill operator-auth-control"
          onClick={logout}
        >
          Sign out
        </button>
      </div>
    )
  }

  return (
    <button
      type="button"
      className="pellier-account-pill operator-auth-signin"
      onClick={() => redirectToSignIn('email')}
      data-testid="operator-sign-in"
    >
      <User className="operator-topbar-icon" aria-hidden />
      <span>Sign in</span>
    </button>
  )
}

/**
 * Present a bare Cognito username with a capital.
 *
 * The workshop's operator signs in as `operator`, and the personas as `marco`,
 * `anna` and `theo`, so `given_name` falls back to the username and the desk
 * rendered it lowercase beside a capitalised "Sign out". Only a single bare
 * word is touched: an address keeps its case, because capitalising the local
 * part of an email is wrong, and anything with a space is a real name whose
 * capitalisation is not ours to guess.
 */
function presentIdentity(value: string): string {
  if (!/^[a-z][a-z0-9._-]*$/.test(value)) return value
  return value.charAt(0).toUpperCase() + value.slice(1)
}

const OperatorFrame: React.FC = () => {
  const { pathname, hash } = useLocation()
  const onClient = pathname.startsWith('/operator/clients/')
  const chatActive = pathname === '/operator/chat' || (onClient && hash.startsWith('#operator-concierge'))
  const resource = useQueueResource()
  const clientBook = useClientBookResource()
  useEffect(() => {
    const previous = document.title
    document.title = operatorTitleForPath(pathname)
    return () => {
      document.title = previous
    }
  }, [pathname])

  return (
    <ClientBookContext.Provider value={clientBook}>
    <ReviewQueueContext.Provider value={resource}>
    <OperatorQueueRefreshContext.Provider value={resource.refresh}>
      <div className="operator-root" data-testid="operator-root">
        <div className="operator-workspace-layout">
          <aside className="operator-sidebar">
            <p className="operator-sidebar-label">Operator workspace</p>
              <nav className="operator-topbar-nav" aria-label="Operator sections">
                <ClientBookNavigation />
                <Link
                  to={onClient ? `${pathname}#operator-concierge` : '/operator/chat?membership=all'}
                  className={`operator-topbar-link operator-chat-nav-link${chatActive ? ' operator-topbar-link-active' : ''}`}
                  aria-current={chatActive ? 'page' : undefined}
                  data-testid="operator-chat-link"
                >
                  <MessageCircle className="operator-topbar-icon" aria-hidden />
                  <span className="operator-topbar-label">Operator chat</span>
                </Link>
                <PendingReviewLink />
              </nav>
            <p className="operator-sidebar-note">The client, the request, and the evidence for a considered decision.</p>
          </aside>
          <div className="operator-workspace-content">
        <header className="operator-topbar" data-testid="operator-topbar">
          <div className="operator-topbar-inner">
            <div className="operator-topbar-start">
              <Link to="/operator" className="operator-wordmark">
                Pellier Operator
              </Link>
              <span className="operator-topbar-context">
                Clienteling and service recovery
              </span>
            </div>
            <div className="operator-topbar-end">
              <OperatorAuthControl />
            </div>
          </div>
        </header>
        <main className="operator-shell">
          {pathname.startsWith('/operator/reviews/') ? (
            <div className="operator-desk-layout">
              <ReviewQueuePanel />
              <div className="operator-desk-case"><Outlet /></div>
            </div>
          ) : <Outlet />}
        </main>
          </div>
        </div>
      </div>
    </OperatorQueueRefreshContext.Provider>
    </ReviewQueueContext.Provider>
    </ClientBookContext.Provider>
  )
}

export default OperatorFrame
