/**
 * App — root component.
 *
 * Composition is intentionally minimal: provider chain, BrowserRouter,
 * root-level modal hosts (AuthModal, PreferencesModal, ComparisonHost), and
 * the final route table. The two product surfaces are the storefront
 * PellierPage (`/`) and Pellier Operator (`/operator/*`).
 *
 * Selecting a persona presents a scenario but does not authenticate (see
 * PRODUCT.md). Pellier Operator is the one authenticated boundary; `OperatorFrame` reads `useAuth` directly and
 * renders its own sign-in state rather than a shared route wrapper.
 */
import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
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
import RouteExperience from './shared/RouteExperience'
import AppErrorBoundary from './shared/AppErrorBoundary'
import SessionStatusNotice from './shared/SessionStatusNotice'
import './styles/navigation-polish.css'

const PellierPage = lazy(() => import('./pages/PellierPage'))
const OperatorFrame = lazy(() => import('./operator/shell/OperatorFrame'))
const ClientBook = lazy(() => import('./operator/surfaces/ClientBook'))
const ClientRecord = lazy(() => import('./operator/surfaces/ClientRecord'))
const ReviewQueue = lazy(() => import('./operator/surfaces/ReviewQueue'))
const ReviewRecord = lazy(() => import('./operator/surfaces/ReviewRecord'))
const ProductDetailPage = lazy(() => import('./pages/ProductDetailPage'))
const StoryboardPage = lazy(() => import('./pages/StoryboardPage'))
const AboutPage = lazy(() => import('./pages/AboutPage'))

// ---------------------------------------------------------------------------
// ModalRouteGuard — closes transient modals when the route changes.
//
// UIProvider sits above BrowserRouter so it can't call useLocation()
// directly. This tiny watcher mounts inside the router, subscribes
// to pathname changes, and keeps surface-specific interaction from leaking
// across product boundaries. The shopper drawer stays on storefront routes;
// Operator owns its scoped work area without an overlay
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
      pathname.startsWith('/operator')

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
 * its supporting editorial pages, but not to the Operator console.
 */
function ShopperChatSlot() {
  const { pathname } = useLocation()
  if (pathname.startsWith('/operator')) return null
  return <ChatDrawer />
}

function RouteLoading() {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      data-route-loading="true"
      className="min-h-[40vh] flex items-center justify-center gap-3"
    >
      <span aria-hidden="true" className="w-7 h-7 rounded-full border-2 border-line border-t-ink motion-safe:animate-spin" />
      <p role="status">Loading page…</p>
    </main>
  )
}

/**
 * Reset a failed route on navigation without remounting healthy parent routes
 * (such as a session shared by Replay, Evidence, and Brief). `SurfaceNavigation`,
 * `RouteExperience`, and the modal slots all render as siblings of this
 * component in `App()`, so they stay interactive even if the route inside
 * throws.
 */
function AppRouteBoundary() {
  const { pathname } = useLocation()
  return (
    <AppErrorBoundary resetKey={pathname}>
      <AppRoutes />
    </AppErrorBoundary>
  )
}

export function AppRoutes() {
  return (
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        {/*
         *   /           -> PellierPage (storefront shell)
         *   /product/:id -> ProductDetailPage (one piece, deep-linkable)
         *   retired editorial and browser-local inspection paths -> storefront
         *   *           -> redirect to /
        */}
        <Route path="/" element={<PellierPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/product/:productId" element={<ProductDetailPage />} />
        {/* Pellier Operator — one authorization boundary. Every route,
            including client and review reads, inherits require_operator from
            the backend router. */}
        <Route path="/operator" element={<OperatorFrame />}>
          <Route index element={<ClientBook />} />
          <Route path="clients" element={<Navigate to="/operator" replace />} />
          <Route path="chat" element={<Navigate to="/operator" replace />} />
          <Route path="clients/:customerId" element={<ClientRecord />} />
          {/* Every proposed credit waiting on a person, and the decided ones. */}
          <Route path="reviews" element={<ReviewQueue />} />
          <Route path="reviews/:reviewId" element={<ReviewRecord />} />
        </Route>
        {/* Stories and About are real destinations again: the header and
            footer link to them on every storefront page, and a nav item that
            sends a shopper back home is a dead end. Both render only editorial
            copy and the teaser grid, none of the browser-local catalog or
            localStorage evidence that retired /inspector and /discover. */}
        <Route path="/storyboard" element={<StoryboardPage />} />
        <Route path="/about" element={<AboutPage />} />
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
                {/* Rendered first so its "Skip to content" link (fixed
                    position, hidden until focus -- see
                    styles/navigation-polish.css) is the first focusable
                    element in Tab order. It used to render after
                    SurfaceNavigation, so a keyboard user tabbed through
                    the brand link and all three surface links before
                    ever reaching it. */}
                <RouteExperience />
                <SurfaceNavigation />
                <SessionStatusNotice />
                <ModalRouteGuard />
                <ShopperChatSlot />
              <ComparisonHost />
              {/* The routed page. While Ask Pellier is docked on a desktop
                  width, this wrapper pads its right edge by the panel's
                  width (see chat-drawer.css) so the store reflows beside it. */}
              <div className="pellier-stage">
                <AppRouteBoundary />
              </div>
            </BrowserRouter>
          </UIProvider>
        </CartProvider>
      </LayoutProvider>
      </PersonaProvider>
    </AuthProvider>
  )
}

export default App
