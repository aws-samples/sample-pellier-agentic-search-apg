/**
 * App — root component.
 *
 * Composition is intentionally minimal: provider chain, BrowserRouter,
 * root-level modal hosts (AuthModal, PreferencesModal, ComparisonHost), and
 * the final route table. The three product surfaces are
 * PellierPage (`/`) and the Pellier Observatory frame (`/observatory/*`).
 *
 * AuthGate is exported so the Pellier Observatory surface can be gated when Cognito
 * is configured.
 */
import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { CartProvider, useCart } from './contexts/CartContext'
import { UIProvider, useUI } from './contexts/UIContext'
import { LayoutProvider } from './contexts/LayoutContext'
import { PersonaProvider } from './contexts/PersonaContext'
import AuthModal from './components/AuthModal'
import CartPanel from './components/CartPanel'
import Toast from './components/Toast'
import PersonaTransitionOverlay from './components/PersonaTransitionOverlay'
import PreferencesModal from './components/PreferencesModal'
import ChatDrawer from './components/ChatDrawer'
import ComparisonHost from './components/ComparisonHost'
import SignInPage from './components/SignInPage'
import SurfaceNavigation from './components/SurfaceNavigation'
import { routerBasename } from './utils/assetPath'
import './styles/premium-heading-styles.css'
import RouteExperience from './shared/RouteExperience'
import './styles/navigation-polish.css'

const PellierPage = lazy(() => import('./pages/PellierPage'))
const ObservatoryFrame = lazy(() => import('./observatory/shell/ObservatoryFrame'))
const OperatorFrame = lazy(() => import('./operator/shell/OperatorFrame'))
const ClientBook = lazy(() => import('./operator/surfaces/ClientBook'))
const ClientRecord = lazy(() => import('./operator/surfaces/ClientRecord'))
const ReviewQueue = lazy(() => import('./operator/surfaces/ReviewQueue'))
const ReviewRecord = lazy(() => import('./operator/surfaces/ReviewRecord'))
const SessionsList = lazy(() => import('./observatory/surfaces/observe/SessionsList'))
const SessionView = lazy(() => import('./observatory/surfaces/observe/SessionView'))
const ChatTab = lazy(() => import('./observatory/surfaces/observe/ChatTab'))
const TelemetryTab = lazy(() => import('./observatory/surfaces/observe/TelemetryTab'))
const BriefTab = lazy(() => import('./observatory/surfaces/observe/BriefTab'))
const WorkshopMap = lazy(() => import('./observatory/surfaces/observe/WorkshopMap'))
const ProofBoard = lazy(() => import('./observatory/surfaces/observe/ProofBoard'))
const OperatorLineage = lazy(
  () => import('./observatory/surfaces/observe/OperatorLineage'),
)
const OperatorTurnEvidence = lazy(
  () => import('./observatory/surfaces/observe/OperatorTurnEvidence'),
)
const ReplacementEvidence = lazy(
  () => import('./observatory/surfaces/observe/ReplacementEvidence'),
)
const ObservatoryWorkbench = lazy(
  () => import('./observatory/surfaces/observe/ObservatoryWorkbench'),
)
const LabsCatalog = lazy(
  () => import('./observatory/surfaces/labs/LabsCatalog'),
)
const LabDetail = lazy(
  () => import('./observatory/surfaces/labs/LabDetail'),
)
const ArchitectureIndex = lazy(
  () => import('./observatory/surfaces/understand/ArchitectureIndex'),
)
const ArchitectureDetail = lazy(
  () => import('./observatory/surfaces/understand/ArchitectureDetail'),
)
const Tools = lazy(() => import('./observatory/surfaces/understand/Tools'))
const Search = lazy(() => import('./observatory/surfaces/understand/Search'))
const Skills = lazy(() => import('./observatory/surfaces/understand/Skills'))
const Routing = lazy(() => import('./observatory/surfaces/understand/Routing'))
const MemoryDashboard = lazy(
  () => import('./observatory/surfaces/understand/MemoryDashboard'),
)
const Govern = lazy(() => import('./observatory/surfaces/govern/Govern'))
const Performance = lazy(() => import('./observatory/surfaces/measure/Performance'))
const Evaluations = lazy(() => import('./observatory/surfaces/measure/Evaluations'))
const ProductionPatterns = lazy(
  () => import('./observatory/surfaces/measure/ProductionPatterns'),
)
const ObservatorySettings = lazy(() => import('./observatory/surfaces/Settings'))
const ProductDetailPage = lazy(() => import('./pages/ProductDetailPage'))
const StoryboardPage = lazy(() => import('./pages/StoryboardPage'))
const AboutPage = lazy(() => import('./pages/AboutPage'))
const HowPellierWorksPage = lazy(() => import('./pages/HowPellierWorksPage'))

// ---------------------------------------------------------------------------
// AuthGate — Cognito-aware auth wrapper. Gates the Pellier Observatory surface when
// Cognito is configured. When Cognito is not configured (local dev without
// env vars), children pass through directly.
// ---------------------------------------------------------------------------
export function AuthGate({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  const cognitoConfigured = !!(
    import.meta.env.VITE_COGNITO_DOMAIN && import.meta.env.VITE_COGNITO_CLIENT_ID
  )

  if (!cognitoConfigured) return <>{children}</>

  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: 'var(--cream)' }}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-black/10 border-t-black/40 rounded-full animate-spin" />
          <p className="text-sm" style={{ color: 'rgba(0,0,0,0.45)' }}>
            Loading...
          </p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) return <SignInPage />
  return <>{children}</>
}

// ---------------------------------------------------------------------------
// ModalRouteGuard — closes transient modals when the route changes.
//
// UIProvider sits above BrowserRouter so it can't call useLocation()
// directly. This tiny watcher mounts inside the router, subscribes
// to pathname changes, and keeps surface-specific interaction from leaking
// across product boundaries. The shopper drawer stays on storefront routes;
// Operator and Observatory own their scoped work areas without an overlay
// chat from a different surface. Auth, preferences, and cart also close
// because they are context-bound to a specific page.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// CartPanelSlot — bridges CartContext's open/close to CartPanel props.
// Mounted at the App root so it survives route changes (same as AuthModal).
// ---------------------------------------------------------------------------
function CartPanelSlot() {
  const { cartOpen, setCartOpen } = useCart()
  return <CartPanel isOpen={cartOpen} onClose={() => setCartOpen(false)} />
}

// ---------------------------------------------------------------------------
// ToastSlot — bridges CartContext's toast state to the Toast component.
// ---------------------------------------------------------------------------
function ToastSlot() {
  const { showToast, toastMessage, dismissToast } = useCart()
  return <Toast message={toastMessage} show={showToast} onClose={dismissToast} />
}

const TRANSIENT_MODALS = new Set([
  'auth',
  'preferences',
  'cart',
  'checkout',
])

function ModalRouteGuard() {
  const { pathname } = useLocation()
  const { activeModal, closeModal, setChatSurface } = useUI()
  useEffect(() => {
    const isDedicatedSurface =
      pathname.startsWith('/operator') || pathname.startsWith('/observatory')

    setChatSurface(isDedicatedSurface ? 'none' : 'drawer')

    if (
      activeModal &&
      (TRANSIENT_MODALS.has(activeModal) || isDedicatedSurface)
    ) {
      closeModal({ restoreDrawer: false })
    }
    // intentionally only run on pathname changes — activeModal in the
    // dep array would close the modal the instant it opened.
  }, [pathname])
  return null
}

/**
 * The shopper's Ask Pellier drawer, and the surfaces it does not belong on.
 *
 * `ChatDrawer` was mounted for every route, so its "Continue chat" pill floated over
 * Pellier Operator whenever the browser held a storefront thread — the shopper
 * conversation following an operator around their own console. It is a surface-boundary
 * leak rather than a bug in the drawer: Operator is a different product with its own
 * Concierge, and offering a shopper thread there invites clicking into the wrong one.
 *
 * Gated on the route rather than removed: it belongs to the storefront and
 * its supporting editorial pages, but not to the Observatory evidence view
 * or the Operator console.
 */
function ShopperChatSlot() {
  const { pathname } = useLocation()
  if (pathname.startsWith('/operator') || pathname.startsWith('/observatory')) return null
  return <ChatDrawer />
}

/**
 * Every path the inspection surface has ever lived at, newest last.
 *
 * The surface has been renamed twice: Observatory, then Pellier Labs, now the
 * Observatory. Workshop screenshots, the lab guide, and browser history all
 * still point at the old paths, and a participant following a screenshot into
 * a 404 has no way to know the page was renamed rather than removed.
 *
 * Order matters only in that no entry may be a prefix of `/observatory`, or the
 * redirect would resolve to itself.
 */
const LEGACY_SURFACE_PREFIXES = ['/agent-trace', '/pellier-labs', '/labs'] as const

function LegacyPathRedirect() {
  const { pathname, search, hash } = useLocation()
  const legacyPrefix = LEGACY_SURFACE_PREFIXES.find((prefix) =>
    pathname.startsWith(prefix),
  )
  // Nothing matched, which means this component was mounted on a route it does
  // not own. Send the visitor to the surface root rather than to a path built
  // from a prefix that was never there.
  const suffix = legacyPrefix ? pathname.slice(legacyPrefix.length) : ''
  return <Navigate to={`/observatory${suffix}${search}${hash}`} replace />
}

function RouteLoading() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="min-h-[40vh] flex items-center justify-center"
    >
      <span className="w-7 h-7 rounded-full border-2 border-black/10 border-t-black/50 animate-spin" />
    </div>
  )
}

export function AppRoutes() {
  return (
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        {/*
         *   /           -> PellierPage (storefront shell)
         *   /product/:id -> ProductDetailPage (one piece, deep-linkable)
         *   /observatory/* -> Pellier Observatory
         *   retired editorial and browser-local inspection paths -> storefront
         *   *           -> redirect to /
        */}
        <Route path="/" element={<PellierPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/product/:productId" element={<ProductDetailPage />} />
        {/* Legacy surface paths. `/observatory/*` is deliberately absent: it
            would shadow the real surface below and redirect to itself. */}
        <Route path="/agent-trace/*" element={<LegacyPathRedirect />} />
        <Route path="/pellier-labs/*" element={<LegacyPathRedirect />} />
        <Route path="/labs/*" element={<LegacyPathRedirect />} />
        {/* Pellier Operator — one authorization boundary. Every route,
            including client and review reads, inherits require_operator from
            the backend router. */}
        <Route path="/operator" element={<OperatorFrame />}>
          <Route index element={<ClientBook key="records" />} />
          <Route path="chat" element={<ClientBook key="chat" intent="chat" />} />
          <Route path="clients/:customerId" element={<ClientRecord />} />
          {/* Prepared requests handed off from Pellier. The queue is the desk's
              entry point for storefront work, so an operator finds a waiting
              client without already knowing to search for them. */}
          <Route path="reviews" element={<ReviewQueue />} />
          <Route path="reviews/:reviewId" element={<ReviewRecord />} />
        </Route>
        <Route path="/observatory" element={<ObservatoryFrame />}>
          <Route index element={<LabsCatalog />} />
          {/* Old navigation and screenshots used the collection noun as an
              index route. Preserve that deep link instead of falling through
              to the Storefront wildcard. */}
          <Route path="labs" element={<Navigate to="/observatory" replace />} />
          <Route path="labs/:exerciseId" element={<LabDetail />} />
          <Route path="guide/:guideId" element={<LabDetail />} />
          <Route path="workbench" element={<ObservatoryWorkbench />} />
          <Route
            path="references"
            element={<Navigate to="/observatory/workbench#resources" replace />}
          />
          <Route path="proof-board" element={<ProofBoard />} />
          <Route path="operator-lineage" element={<OperatorLineage />} />
          <Route path="operator-turn" element={<OperatorTurnEvidence />} />
          <Route path="replacement" element={<ReplacementEvidence />} />
          <Route
            path="audit-proof"
            element={<ProofBoard focusCardId="audit-ledger" />}
          />
          <Route path="sessions" element={<SessionsList />} />
          <Route path="sessions/:id" element={<SessionView />}>
            <Route index element={<Navigate to="chat" replace />} />
            <Route path="chat" element={<ChatTab />} />
            <Route path="telemetry" element={<TelemetryTab />} />
            <Route path="brief" element={<BriefTab />} />
          </Route>
          <Route path="architecture" element={<ArchitectureIndex />} />
          <Route path="architecture/:concept" element={<ArchitectureDetail />} />
          <Route
            path="agents"
            element={<Navigate to="/observatory/tools" replace />}
          />
          <Route path="tools" element={<Tools />} />
          <Route path="search" element={<Search />} />
          <Route path="skills" element={<Skills />} />
          <Route path="routing" element={<Routing />} />
          <Route path="memory" element={<MemoryDashboard />} />
          <Route path="govern" element={<Govern />} />
          <Route path="govern/:section" element={<Govern />} />
          <Route path="write-path" element={<Navigate to="/observatory/govern/policies" replace />} />
          <Route path="performance" element={<Performance />} />
          <Route path="evaluations" element={<Evaluations />} />
          <Route path="production-patterns" element={<ProductionPatterns />} />
          <Route path="workshop-map" element={<WorkshopMap />} />
          {/* The page was routed at `observatory` while the navigation
              called it "Workshop Map". The shell now owns that name, so the
              old path redirects rather than 404s for anyone holding a link
              or a screenshot of it. */}
          <Route
            path="observatory"
            element={<Navigate to="/observatory/workshop-map" replace />}
          />
          <Route
            path="persona-journeys"
            element={<Navigate to="/observatory/sessions" replace />}
          />
          <Route path="settings" element={<ObservatorySettings />} />
        </Route>
        {/* Stories and About are real destinations again: the header and
            footer link to them on every storefront page, and a nav item that
            sends a shopper back home is a dead end. Both render only editorial
            copy and the teaser grid, none of the browser-local catalog or
            localStorage evidence that retired /inspector and /discover. */}
        <Route path="/storyboard" element={<StoryboardPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/how-pellier-works" element={<HowPellierWorksPage />} />
        <Route path="/inspector" element={<Navigate to="/" replace />} />
        <Route path="/discover" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

// ---------------------------------------------------------------------------
// App — provider chain + routes.
// ---------------------------------------------------------------------------
function App() {
  return (
    <AuthProvider>
      <PersonaProvider>
      <LayoutProvider>
        <CartProvider>
          <UIProvider>
            {/*
             * Modal singleton slots. Mounting here puts them above every
             * route; they read `UIContext.activeModal` to decide whether
             * to render. AuthModal + PreferencesModal are route-independent;
             * the surface-scoped drawer and comparison host live inside
             * BrowserRouter so route boundaries can close them safely.
            */}
            <AuthModal />
            <PreferencesModal />
            <PersonaTransitionOverlay />
            <CartPanelSlot />
            <ToastSlot />
              <BrowserRouter basename={routerBasename()}>
                <SurfaceNavigation />
                <RouteExperience />
                <ModalRouteGuard />
                <ShopperChatSlot />
              <ComparisonHost />
              <AppRoutes />
            </BrowserRouter>
          </UIProvider>
        </CartProvider>
      </LayoutProvider>
      </PersonaProvider>
    </AuthProvider>
  )
}

export default App
