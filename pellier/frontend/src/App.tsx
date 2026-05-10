/**
 * App — root component.
 *
 * Composition is intentionally minimal: provider chain, BrowserRouter,
 * root-level modal hosts (AuthModal, PreferencesModal, ConciergeModal,
 * ComparisonHost), and the final route table. The workshop chrome that
 * used to live here moved into `/workshop` (WorkshopPage).
 *
 * AuthGate is exported because WorkshopPage wraps its own content in it
 * to preserve the Cognito-configured / not-configured branching.
 *
 * useTheme / ThemeContext remain exported for a small set of orphan
 * components (DemoChatCarousel, RecentlyViewed, ProactiveSuggestions,
 * AgentWorkflowVisualizer). Those components are no longer reachable
 * from any route after AppContent's removal, so no ThemeProvider is
 * mounted. The export exists solely to keep `tsc` green until the
 * orphans are deleted in a follow-up cleanup.
 */
import { createContext, useContext, useEffect, type ReactNode } from 'react'
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
import ConciergeModal from './components/ConciergeModal'
import ChatDrawer from './components/ChatDrawer'
import ComparisonHost from './components/ComparisonHost'
import SignInPage from './components/SignInPage'
import BoutiquePage from './pages/BoutiquePage'
// WorkshopPage removed — Atelier is now served by AtelierFrame
import AtelierFrame from './atelier/shell/AtelierFrame'
import SessionsList from './atelier/surfaces/observe/SessionsList'
import SessionView from './atelier/surfaces/observe/SessionView'
import ChatTab from './atelier/surfaces/observe/ChatTab'
import TelemetryTab from './atelier/surfaces/observe/TelemetryTab'
import BriefTab from './atelier/surfaces/observe/BriefTab'
import Observatory from './atelier/surfaces/observe/Observatory'
import ArchitectureIndex from './atelier/surfaces/understand/ArchitectureIndex'
import ArchitectureDetail from './atelier/surfaces/understand/ArchitectureDetail'
import Agents from './atelier/surfaces/understand/Agents'
import Tools from './atelier/surfaces/understand/Tools'
import Skills from './atelier/surfaces/understand/Skills'
import Routing from './atelier/surfaces/understand/Routing'
import MemoryDashboard from './atelier/surfaces/understand/MemoryDashboard'
import Performance from './atelier/surfaces/measure/Performance'
import Evaluations from './atelier/surfaces/measure/Evaluations'
import AtelierSettings from './atelier/surfaces/Settings'
import InspectorPage from './pages/InspectorPage'
import StoryboardPage from './pages/StoryboardPage'
import DiscoverPage from './pages/DiscoverPage'
import AboutPage from './pages/AboutPage'
import AtelierComponentsPreview from './pages/AtelierComponentsPreview'
import DesignSystemPreview from './pages/DesignSystemPreview'
import './styles/premium-heading-styles.css'

// ---------------------------------------------------------------------------
// ThemeContext — legacy. See header comment. No Provider is mounted; `useTheme`
// will throw if called, which is intentional: the only remaining callers live
// in orphan components that no route renders.
// ---------------------------------------------------------------------------
type Theme = 'dark' | 'light'
interface ThemeContextType {
  theme: Theme
  toggleTheme: () => void
}
const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within ThemeProvider')
  return context
}

// ---------------------------------------------------------------------------
// AuthGate — Cognito-aware auth wrapper. Used by WorkshopPage so the
// instrumentation surface remains gated when Cognito is configured.
// When Cognito is not configured (local dev without env vars), children
// pass through directly.
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
        style={{ background: '#fbf4e8' }}
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
// to pathname changes, and closes anything non-persistent. Chat
// surfaces (drawer / concierge) and the comparison modal are
// intentional leave-open cases — a user who opens the chat on `/`
// and navigates to `/atelier` should keep talking to Pellier. The
// auth, preferences, and cart modals close because they're
// context-bound to a specific page.
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

const TRANSIENT_MODALS = new Set(['auth', 'preferences', 'cart', 'checkout'])

function ModalRouteGuard() {
  const { pathname } = useLocation()
  const { activeModal, closeModal } = useUI()
  useEffect(() => {
    if (activeModal && TRANSIENT_MODALS.has(activeModal)) {
      closeModal()
    }
    // intentionally only run on pathname changes — activeModal in the
    // dep array would close the modal the instant it opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname])
  return null
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
             * to render, so a route change never interrupts an open modal.
             * AuthModal + PreferencesModal are route-independent; Concierge
             * and Comparison live inside BrowserRouter because the
             * concierge reads useLocation() for route-mode selection.
             */}
            <AuthModal />
            <PreferencesModal />
            <PersonaTransitionOverlay />
            <CartPanelSlot />
            <ToastSlot />
            <BrowserRouter
              future={{
                v7_startTransition: true,
                v7_relativeSplatPath: true,
              }}
            >
              <ModalRouteGuard />
              <ConciergeModal />
              <ChatDrawer />
              <ComparisonHost />
              <Routes>
                {/*
                 *   /           → BoutiquePage (storefront shell)
                 *   /atelier    → WorkshopPage (instrumentation, gated by AuthGate)
                 *   /inspector  → InspectorPage (frozen session-scoped trace view)
                 *   /storyboard → StoryboardPage
                 *   /discover   → DiscoverPage
                 *   *           → redirect to /
                 */}
                <Route path="/" element={<BoutiquePage />} />
                {/* Atelier Observatory — nested routes under AtelierFrame shell.
                    The frame renders the 240px sidebar + canvas grid with
                    React Router <Outlet /> for surface rendering. */}
                <Route path="/atelier" element={<AtelierFrame />}>
                  <Route index element={<Navigate to="observatory" replace />} />
                  <Route path="sessions" element={<SessionsList />} />
                  <Route path="sessions/:id" element={<SessionView />}>
                    <Route index element={<Navigate to="chat" replace />} />
                    <Route path="chat" element={<ChatTab />} />
                    <Route path="telemetry" element={<TelemetryTab />} />
                    <Route path="brief" element={<BriefTab />} />
                  </Route>
                  <Route path="architecture" element={<ArchitectureIndex />} />
                  <Route path="architecture/:concept" element={<ArchitectureDetail />} />
                  <Route path="agents" element={<Agents />} />
                  <Route path="tools" element={<Tools />} />
                  <Route path="skills" element={<Skills />} />
                  <Route path="routing" element={<Routing />} />
                  <Route path="memory" element={<MemoryDashboard />} />
                  <Route path="performance" element={<Performance />} />
                  <Route path="evaluations" element={<Evaluations />} />
                  <Route path="observatory" element={<Observatory />} />
                  <Route path="settings" element={<AtelierSettings />} />
                </Route>
                {/* Legacy WorkshopPage route removed — Atelier is now
                    served exclusively by AtelierFrame with nested routes. */}
                {/* Dev-only: preview gallery for shared atelier/ primitives.
                    Guarded by import.meta.env.DEV so production bundles
                    never include it. */}
                {import.meta.env.DEV && (
                  <Route
                    path="/atelier/_components"
                    element={<AtelierComponentsPreview />}
                  />
                )}
                {import.meta.env.DEV && (
                  <Route
                    path="/dev/design-system"
                    element={<DesignSystemPreview />}
                  />
                )}
                <Route path="/inspector" element={<InspectorPage />} />
                <Route path="/storyboard" element={<StoryboardPage />} />
                <Route path="/discover" element={<DiscoverPage />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </UIProvider>
        </CartProvider>
      </LayoutProvider>
      </PersonaProvider>
    </AuthProvider>
  )
}

export default App
