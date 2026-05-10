/**
 * Unit tests for Atelier shared UI components.
 *
 * Tests verify that each component renders the correct DOM output
 * with the expected inline styles, text content, and accessibility
 * attributes as defined by the design system.
 *
 * **Validates: Requirements 15.3, 15.4, 15.5**
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExpCard } from '../components/ExpCard';
import { StatusPill } from '../components/StatusPill';
import { StatusDot } from '../components/StatusDot';
import { Eyebrow } from '../components/Eyebrow';
import { CategoryBadge } from '../components/CategoryBadge';

// ---------------------------------------------------------------------------
// ExpCard
// ---------------------------------------------------------------------------
describe('ExpCard', () => {
  it('renders children inside a card with cream-elev bg, rule-1 border, 14px radius', () => {
    const { container } = render(
      <ExpCard>
        <span>Card content</span>
      </ExpCard>,
    );

    const card = container.firstElementChild as HTMLElement;
    expect(card).toBeTruthy();
    expect(card.textContent).toContain('Card content');

    // Verify design-system inline styles
    expect(card.style.background).toBe('var(--at-card-bg)');
    expect(card.style.border).toBe('1px solid var(--at-card-border)');
    expect(card.style.borderRadius).toBe('var(--at-card-radius)');
  });

  it('renders a burgundy accent line at top-left', () => {
    const { container } = render(
      <ExpCard>
        <span>Content</span>
      </ExpCard>,
    );

    // The accent line is the first child span with aria-hidden
    const accent = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(accent).toBeTruthy();
    expect(accent.style.backgroundColor).toBe('var(--at-card-accent-color)');
    expect(accent.style.width).toBe('var(--at-card-accent-width)');
    expect(accent.style.position).toBe('absolute');
    expect(accent.style.top).toBe('0px');
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
    expect(card.style.cursor).toBe('pointer');
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
    expect(pill.style.backgroundColor).toBe('var(--at-status-shipped-bg)');
    expect(pill.style.color).toBe('var(--at-status-shipped-text)');
    expect(pill.style.textTransform).toBe('uppercase');
    expect(pill.style.fontFamily).toBe('var(--at-mono)');
  });

  it('renders "Exercise" with burgundy styling', () => {
    render(<StatusPill status="exercise" />);

    const pill = screen.getByText('Exercise');
    expect(pill).toBeTruthy();
    expect(pill.style.backgroundColor).toBe('var(--at-status-exercise-bg)');
    expect(pill.style.color).toBe('var(--at-status-exercise-text)');
    expect(pill.style.textTransform).toBe('uppercase');
    expect(pill.style.fontFamily).toBe('var(--at-mono)');
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
    expect(dot.style.backgroundColor).toBe('var(--at-dot-live)');
    expect(dot.style.borderRadius).toBe('50%');
  });

  it('renders idle variant with muted fill and no pulsing', () => {
    render(<StatusDot status="idle" />);

    const dot = screen.getByRole('status', { name: 'Idle' });
    expect(dot).toBeTruthy();
    expect(dot.className).not.toContain('at-pulse-live');
    expect(dot.style.backgroundColor).toBe('var(--at-dot-idle)');
    expect(dot.style.borderRadius).toBe('50%');
  });

  it('renders empty variant with outline border and transparent fill', () => {
    render(<StatusDot status="empty" />);

    const dot = screen.getByRole('status', { name: 'Empty' });
    expect(dot).toBeTruthy();
    expect(dot.className).not.toContain('at-pulse-live');
    expect(dot.style.backgroundColor).toBe('transparent');
    expect(dot.style.border).toBe('1.5px solid var(--at-dot-empty-border)');
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
describe('Eyebrow', () => {
  it('renders monospace uppercase label with burgundy dot', () => {
    render(<Eyebrow label="SESSIONS" />);

    const eyebrow = screen.getByText('SESSIONS');
    expect(eyebrow).toBeTruthy();

    // Verify monospace font and uppercase transform
    expect(eyebrow.style.fontFamily).toBe('var(--at-mono)');
    expect(eyebrow.style.textTransform).toBe('uppercase');
    expect(eyebrow.style.letterSpacing).toBe('var(--at-eyebrow-tracking)');
    expect(eyebrow.style.fontSize).toBe('var(--at-eyebrow-size)');
  });

  it('renders a burgundy dot before the label (default variant)', () => {
    const { container } = render(<Eyebrow label="OBSERVE" />);

    const dot = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(dot).toBeTruthy();
    expect(dot.style.backgroundColor).toBe('var(--at-red-1)');
    expect(dot.style.borderRadius).toBe('50%');
    expect(dot.style.width).toBe('6px');
    expect(dot.style.height).toBe('6px');
  });

  it('renders muted variant with ink-4 color', () => {
    const { container } = render(<Eyebrow label="MUTED" variant="muted" />);

    const dot = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(dot.style.backgroundColor).toBe('var(--at-ink-4)');

    const label = screen.getByText('MUTED');
    expect(label.style.color).toBe('var(--at-ink-4)');
  });
});

// ---------------------------------------------------------------------------
// CategoryBadge
// ---------------------------------------------------------------------------
describe('CategoryBadge', () => {
  it('renders "Both" badge with burgundy color and red-soft background', () => {
    render(<CategoryBadge category="both" />);

    const badge = screen.getByText('Both');
    expect(badge).toBeTruthy();
    expect(badge.style.color).toBe('var(--at-cat-both)');
    expect(badge.style.backgroundColor).toBe('var(--at-red-soft)');
    expect(badge.style.textTransform).toBe('uppercase');
    expect(badge.style.fontFamily).toBe('var(--at-mono)');
  });

  it('renders "Managed" badge with green color and green-soft background', () => {
    render(<CategoryBadge category="managed" />);

    const badge = screen.getByText('Managed');
    expect(badge.style.color).toBe('var(--at-cat-managed)');
    expect(badge.style.backgroundColor).toBe('var(--at-green-soft)');
  });

  it('renders "Owned" badge with amber color', () => {
    render(<CategoryBadge category="owned" />);

    const badge = screen.getByText('Owned');
    expect(badge.style.color).toBe('var(--at-cat-owned)');
    expect(badge.style.backgroundColor).toBe('rgba(184, 138, 58, 0.12)');
  });

  it('renders "Teaching" badge with muted ink color', () => {
    render(<CategoryBadge category="teaching" />);

    const badge = screen.getByText('Teaching');
    expect(badge.style.color).toBe('var(--at-cat-teaching)');
    expect(badge.style.backgroundColor).toBe('rgba(31, 20, 16, 0.06)');
  });
});
