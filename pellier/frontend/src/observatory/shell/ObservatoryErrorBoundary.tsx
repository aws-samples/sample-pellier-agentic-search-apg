/**
 * ObservatoryErrorBoundary — React Error Boundary for the Observatory canvas.
 *
 * Wraps the <Outlet /> in ObservatoryFrame so that if any surface component
 * throws during render, the sidebar and top bar remain functional while
 * the canvas shows an editorial error page.
 *
 * React Error Boundaries must be class components — there is no hook
 * equivalent for componentDidCatch / getDerivedStateFromError.
 *
 * Requirements: 19.2, 19.4
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { Eyebrow } from '../components/Eyebrow';

interface ObservatoryErrorBoundaryProps {
  children: React.ReactNode;
}

interface ObservatoryErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ObservatoryErrorBoundary extends React.Component<
  ObservatoryErrorBoundaryProps,
  ObservatoryErrorBoundaryState
> {
  constructor(props: ObservatoryErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ObservatoryErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // Log for debugging — could wire to telemetry in a future phase
    console.error('[ObservatoryErrorBoundary]', error, errorInfo);
  }

  private handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            padding: '48px 24px',
            textAlign: 'center',
          }}
        >
          <Eyebrow label="Something went wrong" variant="burgundy" />

          {/* An error message names the problem and the recovery. It does not
              make a joke about it: a participant who hits this needs to know
              whether their lab progress is affected. The Observatory is a
              core participant surface (not optional -- see
              pellier/frontend/CLAUDE.md), so this copy names the recovery
              without also downgrading the surface. */}
          <h1
            className="observatory-page-title font-display text-espresso"
            style={{ margin: '20px 0 16px' }}
          >
            This view failed to render
          </h1>
          <p
            style={{
              fontFamily: 'var(--obs-sans)',
              fontSize: 'var(--obs-body-size)',
              lineHeight: 'var(--obs-body-leading)',
              color: 'var(--obs-ink-2)',
              maxWidth: '520px',
              margin: '0 0 20px',
            }}
          >
            Your lab progress is unaffected: it lives in Aurora, not in this
            view. Reload to try again, or read the same evidence with{' '}
            <code>psql</code> in the Code Editor.
          </p>

          {this.state.error?.message && (
            <p
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: 'var(--obs-mono-size)',
                lineHeight: 'var(--obs-mono-leading)',
                color: 'var(--obs-ink-1)',
                backgroundColor: 'var(--obs-cream-2)',
                padding: '12px 20px',
                borderRadius: '8px',
                maxWidth: '520px',
                wordBreak: 'break-word',
                margin: '0 0 32px',
              }}
            >
              {this.state.error.message}
            </p>
          )}

          <Link
            to="/observatory/sessions"
            onClick={this.handleReset}
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: 'var(--obs-eyebrow-size)',
              fontWeight: 500,
              letterSpacing: 'var(--obs-eyebrow-tracking)',
              textTransform: 'uppercase',
              color: 'var(--obs-red-1)',
              textDecoration: 'none',
              borderBottom: '1px solid var(--obs-red-1)',
              paddingBottom: '2px',
            }}
          >
            Return to Sessions
          </Link>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ObservatoryErrorBoundary;
