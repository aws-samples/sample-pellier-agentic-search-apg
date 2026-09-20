/**
 * AppErrorBoundary — the top-level React Error Boundary for the route tree.
 *
 * `App.tsx` mounts `SurfaceNavigation`, `RouteExperience`, and the modal
 * slots as siblings of `<AppRoutes />`, not children of it, specifically so
 * a crash inside one route's render does not take the whole app down. That
 * intent had no error boundary behind it: every route (Pellier, Operator,
 * every lazy chunk) rendered with only a `<Suspense>` loading fallback and
 * no `componentDidCatch`, so a render throw, or a stale chunk hash 404 after
 * a redeploy, produced a blank white page with the navigation gone too.
 * `ObservatoryFrame` already wraps its own `<Outlet />` in
 * `ObservatoryErrorBoundary` for exactly this reason; this component gives
 * every surface -- Pellier, Operator, and Observatory itself if the frame
 * chunk fails to load -- the same protection at the point where the
 * persistent top bar must survive the failure.
 *
 * React Error Boundaries must be class components -- there is no hook
 * equivalent for componentDidCatch / getDerivedStateFromError.
 */

import React from 'react'
import { Link } from 'react-router-dom'

interface AppErrorBoundaryProps {
  children: React.ReactNode
}

interface AppErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class AppErrorBoundary extends React.Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  constructor(props: AppErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('[AppErrorBoundary]', error, errorInfo)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            padding: '48px 24px',
            textAlign: 'center',
            fontFamily: 'var(--sans, "Instrument Sans", system-ui, sans-serif)',
          }}
        >
          <h1
            style={{
              fontFamily: 'var(--display, "Fraunces Variable", Georgia, serif)',
              fontSize: 'clamp(24px, 3vw, 32px)',
              margin: '0 0 16px',
              color: 'var(--ink, #1f1410)',
            }}
          >
            This page did not load
          </h1>
          <p
            style={{
              fontSize: '15px',
              lineHeight: 1.6,
              color: 'var(--ink-soft, #3a3833)',
              maxWidth: '480px',
              margin: '0 0 24px',
            }}
          >
            Reload the page to try again, or return to Pellier.
          </p>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={this.handleReload}
              style={{
                fontFamily: 'inherit',
                fontSize: '14px',
                fontWeight: 500,
                padding: '10px 18px',
                borderRadius: '10px',
                border: 'none',
                background: 'var(--ink, #1f1410)',
                color: 'var(--cream, #f7f3ec)',
                cursor: 'pointer',
                minHeight: '44px',
              }}
            >
              Reload
            </button>
            <Link
              to="/"
              onClick={() => this.setState({ hasError: false, error: null })}
              style={{
                fontSize: '14px',
                fontWeight: 500,
                color: 'var(--ink-soft, #3a3833)',
                textDecoration: 'underline',
              }}
            >
              Return to Pellier
            </Link>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default AppErrorBoundary
