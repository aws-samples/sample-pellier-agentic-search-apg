/**
 * Unit tests for Observatory shared UI components.
 *
 * Tests verify that each component renders the correct DOM output
 * with the expected inline styles, text content, and accessibility
 * attributes as defined by the design system.
 *
 * **Validates: Requirements 15.3, 15.4, 15.5**
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExpCard } from '../components/ExpCard';
import { StatusPill } from '../components/StatusPill';
import { StatusDot } from '../components/StatusDot';
import { Eyebrow } from '../components/Eyebrow';
import { CategoryBadge } from '../components/CategoryBadge';
import { BreadcrumbTrail } from '../components/BreadcrumbTrail';
import { ModeStrip } from '../components/ModeStrip';
import { SurfaceFilterBar } from '../components/SurfaceFilterBar';
import { TabNav } from '../components/TabNav';
import { EditorialTitle } from '../components/EditorialTitle';

// ---------------------------------------------------------------------------
// EditorialTitle
// ---------------------------------------------------------------------------
describe('EditorialTitle', () => {
  it('can return to the embedded workbench resources', () => {
    render(
      <MemoryRouter>
        <EditorialTitle
          eyebrow="Understand"
          title="State, with clear owners"
          backToReferences
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('link', {
        name: 'Back to lab references',
      }),
    ).toHaveAttribute('href', '/observatory#resources');
  });
});

// ---------------------------------------------------------------------------
// ExpCard
// ---------------------------------------------------------------------------
describe('ExpCard', () => {
  it('renders children inside the shared Observatory card primitive', () => {
    const { container } = render(
      <ExpCard>
        <span>Card content</span>
      </ExpCard>,
    );

    const card = container.firstElementChild as HTMLElement;
    expect(card).toBeTruthy();
    expect(card.textContent).toContain('Card content');

    expect(card.classList.contains('observatory-exp-card')).toBe(true);
    expect(card.querySelector('[aria-hidden="true"]')).toBeNull();
  });

  it('applies button role and tabIndex when onClick is provided', () => {
    const { container } = render(
      <ExpCard onClick={() => {}}>
        <span>Clickable</span>
      </ExpCard>,
    );

    const card = container.firstElementChild as HTMLElement;
    expect(card.getAttribute('role')).toBe('button');
    expect(card.getAttribute('tabindex')).toBe('0');
    expect(card.getAttribute('data-clickable')).toBe('true');
  });

  it('does not apply button role when onClick is absent', () => {
    const { container } = render(
      <ExpCard>
        <span>Static</span>
      </ExpCard>,
    );

    const card = container.firstElementChild as HTMLElement;
    expect(card.getAttribute('role')).toBeNull();
    expect(card.getAttribute('tabindex')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// StatusPill
// ---------------------------------------------------------------------------
describe('StatusPill', () => {
  it('renders "Shipped" with sage green styling', () => {
    render(<StatusPill status="shipped" />);

    const pill = screen.getByText('Shipped');
    expect(pill).toBeTruthy();
    expect(pill.style.backgroundColor).toBe('var(--obs-status-shipped-bg)');
    expect(pill.style.color).toBe('var(--obs-status-shipped-text)');
    expect(pill.style.fontFamily).toBe('var(--obs-heading)');
    expect(pill.style.fontWeight).toBe('600');
  });

  it('renders "Exercise" with burgundy styling', () => {
    render(<StatusPill status="exercise" />);

    const pill = screen.getByText('Exercise');
    expect(pill).toBeTruthy();
    expect(pill.style.backgroundColor).toBe('var(--obs-status-exercise-bg)');
    expect(pill.style.color).toBe('var(--obs-status-exercise-text)');
    expect(pill.style.fontFamily).toBe('var(--obs-heading)');
    expect(pill.style.fontWeight).toBe('600');
  });
});

// ---------------------------------------------------------------------------
// StatusDot
// ---------------------------------------------------------------------------
describe('StatusDot', () => {
  it('renders live variant with pulsing class and burgundy fill', () => {
    render(<StatusDot status="live" />);

    const dot = screen.getByRole('status', { name: 'Live' });
    expect(dot).toBeTruthy();
    expect(dot.className).toContain('at-pulse-live');
    expect(dot.style.backgroundColor).toBe('var(--obs-dot-live)');
    expect(dot.style.borderRadius).toBe('50%');
  });

  it('renders idle variant with muted fill and no pulsing', () => {
    render(<StatusDot status="idle" />);

    const dot = screen.getByRole('status', { name: 'Idle' });
    expect(dot).toBeTruthy();
    expect(dot.className).not.toContain('at-pulse-live');
    expect(dot.style.backgroundColor).toBe('var(--obs-dot-idle)');
    expect(dot.style.borderRadius).toBe('50%');
  });

  it('renders empty variant with outline border and transparent fill', () => {
    render(<StatusDot status="empty" />);

    const dot = screen.getByRole('status', { name: 'Empty' });
    expect(dot).toBeTruthy();
    expect(dot.className).not.toContain('at-pulse-live');
    expect(dot.style.backgroundColor).toBe('transparent');
    expect(dot.style.border).toBe('1.5px solid var(--obs-dot-empty-border)');
    expect(dot.style.borderRadius).toBe('50%');
  });

  it('respects custom size prop', () => {
    render(<StatusDot status="live" size={12} />);

    const dot = screen.getByRole('status', { name: 'Live' });
    expect(dot.style.width).toBe('12px');
    expect(dot.style.height).toBe('12px');
  });
});

// ---------------------------------------------------------------------------
// Eyebrow
// ---------------------------------------------------------------------------
// `Eyebrow` is an adapter over `shared/SectionEyebrow`, so what is worth
// pinning is that it resolves to the one shared register -- not the literal
// values it used to set itself. It carried 12px and a 6px dot against the
// primitive's 11px and 5px, which is the drift this convergence closed.
describe('Eyebrow', () => {
  it('renders the shared section-label register', () => {
    render(<Eyebrow label="SESSIONS" />);

    const eyebrow = screen.getByText('SESSIONS');
    expect(eyebrow.style.fontFamily).toBe('var(--obs-heading)');
    expect(eyebrow.style.textTransform).toBe('uppercase');
    expect(eyebrow.style.letterSpacing).toBe('0.08em');
    expect(eyebrow.style.fontSize).toBe('11px');
    expect(eyebrow.style.fontWeight).toBe('600');
  });

  it('opens a section in the brand tone with a leading dot', () => {
    const { container } = render(<Eyebrow label="OBSERVE" />);

    const eyebrow = screen.getByText('OBSERVE');
    expect(eyebrow).toHaveAttribute('data-tone', 'brand');
    expect(eyebrow.style.color).toBe('var(--pellier-burgundy)');

    const dot = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(dot).toBeTruthy();
    // The dot takes the label's own colour, so the two can never disagree.
    expect(dot.style.background).toBe('currentcolor');
  });

  it('renders muted variant with ink-4 color', () => {
    render(<Eyebrow label="MUTED" variant="muted" />);

    const label = screen.getByText('MUTED');
    expect(label).toHaveAttribute('data-tone', 'muted');
    expect(label.style.color).toBe('var(--obs-ink-4)');
  });
});

// ---------------------------------------------------------------------------
// CategoryBadge
// ---------------------------------------------------------------------------
describe('CategoryBadge', () => {
  it('renders "Live path" badge with burgundy color and red-soft background', () => {
    render(<CategoryBadge category="live" />);

    const badge = screen.getByText('Live path');
    expect(badge).toBeTruthy();
    expect(badge.style.color).toBe('var(--obs-cat-both)');
    expect(badge.style.backgroundColor).toBe('var(--obs-red-soft)');
    expect(badge.style.fontFamily).toBe('var(--obs-heading)');
    expect(badge.style.fontWeight).toBe('600');
  });

  it('renders "Optional infra" badge with green color and green-soft background', () => {
    render(<CategoryBadge category="optional" />);

    const badge = screen.getByText('Optional infra');
    expect(badge.style.color).toBe('var(--obs-cat-managed)');
    expect(badge.style.backgroundColor).toBe('var(--obs-green-soft)');
  });

  it('renders "Quality layer" badge with amber color', () => {
    render(<CategoryBadge category="quality" />);

    const badge = screen.getByText('Quality layer');
    expect(badge.style.color).toBe('var(--obs-cat-owned)');
    expect(badge.style.backgroundColor).toBe('rgba(184, 138, 58, 0.12)');
  });

  it('renders "Workshop lens" badge with muted ink color', () => {
    render(<CategoryBadge category="workshop" />);

    const badge = screen.getByText('Workshop lens');
    expect(badge.style.color).toBe('var(--obs-cat-teaching)');
    expect(badge.style.backgroundColor).toBe('rgba(31, 20, 16, 0.06)');
  });
});

// ---------------------------------------------------------------------------
// Operational UI typography
// ---------------------------------------------------------------------------
describe('operational UI typography', () => {
  it('uses the heading sans for tabs and mode controls', () => {
    render(
      <>
        <TabNav
          tabs={[
            { id: 'chat', label: 'Chat' },
            { id: 'telemetry', label: 'Telemetry' },
          ]}
          activeTab="chat"
        />
        <ModeStrip patterns={['Dispatcher', 'Graph']} active="Dispatcher" />
      </>,
    );

    expect(screen.getByRole('tab', { name: 'Chat' }).style.fontFamily).toBe(
      'var(--obs-heading)',
    );
    expect(screen.getByRole('radio', { name: 'Dispatcher' }).style.fontFamily).toBe(
      'var(--obs-heading)',
    );
  });

  it('uses the heading sans for filters and breadcrumbs', () => {
    render(
      <>
        <SurfaceFilterBar
          filter="all"
          counts={{ all: 4, live: 2 }}
          options={[
            { id: 'all', label: 'All' },
            { id: 'live', label: 'Live path' },
          ]}
          onChange={() => {}}
        />
        <BreadcrumbTrail segments={['Pellier Observatory', 'Tool Registry']} />
      </>,
    );

    expect(screen.getByRole('button', { name: 'All (4)' }).style.fontFamily).toBe(
      'var(--obs-heading)',
    );
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' }).style.fontFamily).toBe(
      'var(--obs-heading)',
    );
  });
});
