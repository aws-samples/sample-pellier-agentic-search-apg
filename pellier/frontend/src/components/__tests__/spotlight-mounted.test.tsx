/**
 * Pellier orientation shows a short welcome at most once per browser: a
 * dismissal in one tab holds in every other tab.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import PellierSpotlight from '../PellierSpotlight';
import { UIProvider, useUI } from '../../contexts/UIContext';

const SRC = resolve(__dirname, '../..');

function read(relativePath: string): string {
  return readFileSync(resolve(SRC, relativePath), 'utf8');
}

describe('first-visit orientation', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it('PellierPage renders PellierSpotlight', () => {
    const page = read('pages/PellierPage.tsx');

    expect(page).toContain("import PellierSpotlight from '../components/PellierSpotlight'");
    expect(page).toContain('<PellierSpotlight />');
  });

  it('the Pellier spotlight is remembered per browser so it shows at most once', () => {
    expect(read('components/PellierSpotlight.tsx')).toContain('localStorage');
  });

  it('the Pellier spotlight is dismissible', () => {
    const source = read('components/PellierSpotlight.tsx');
    // Escape key handling is the skip affordance.
    expect(source).toContain('Escape');
  });

  it('moves through every step with keyboard navigation', () => {
    render(<PellierSpotlight />);

    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('heading', { name: 'Begin with the edit.' })).toBeInTheDocument();
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      // The 16:9 hero. The 4:5 product frame it replaced was cropped to a
      // hard zoom by this band's aspect ratio.
      expect.stringContaining('landing-hero-weekender-1600.webp'),
    );
    // The welcome remains a deliberately short arrival sequence.
    const dots = screen.getAllByRole('button', { name: /Show / });
    expect(dots).toHaveLength(3);

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(
      screen.getByRole('button', { name: 'Show Ask, step 2 of 3' }),
    ).toHaveAttribute('aria-current', 'step');

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(
      screen.getByRole('button', { name: 'Show Choose, step 1 of 3' }),
    ).toHaveAttribute('aria-current', 'step');
  });

  it('closes on the separate governed evidence surfaces rather than a feature tour', async () => {
    render(<PellierSpotlight />);

    fireEvent.click(
      screen.getByRole('button', { name: 'Show Trace, step 3 of 3' }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole('heading', {
          name: 'Follow the evidence.',
        }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Turn on the Builder view to see the steps behind each answer.',
    );
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'it waits on the Operator desk until someone on the team approves or declines it.',
    );
    // The four people the evidence is followed for, not a screenshot of the
    // surface that follows it. One accessible name covers the strip, and each
    // portrait comes from LAB_EXERCISES so the names cannot drift from the
    // Governed Lab Collection.
    const strip = await screen.findByRole('img', {
      name: /The four people each lab follows/i,
    });
    for (const anchor of ['Marco', 'Anna', 'Theo', 'Jessica']) {
      expect(strip).toHaveAccessibleName(new RegExp(anchor));
      expect(strip).toHaveTextContent(new RegExp(anchor, 'i'));
    }
    expect(strip.querySelectorAll('img')).toHaveLength(4);
  });

  it('contains keyboard focus and restores it after dismissal', () => {
    const opener = document.createElement('button');
    opener.textContent = 'Open storefront';
    document.body.appendChild(opener);
    opener.focus();

    try {
      render(<PellierSpotlight />);

      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveFocus();

      const focusable = within(dialog).getAllByRole('button');
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      last.focus();
      fireEvent.keyDown(window, { key: 'Tab' });
      expect(first).toHaveFocus();

      first.focus();
      fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
      expect(last).toHaveFocus();

      fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
      expect(opener).toHaveFocus();
    } finally {
      opener.remove();
    }
  });
});

function DockProbe() {
  const { activeModal } = useUI();
  return <span data-testid="dock">{activeModal ?? 'none'}</span>;
}

describe('Escape on the welcome tour', () => {
  const width = window.innerWidth;

  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    // A laptop width, where the store opens with Ask Pellier docked.
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1440 });
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width });
  });

  it('closes the tour and leaves Ask Pellier docked', () => {
    render(
      <UIProvider>
        <DockProbe />
        <PellierSpotlight />
      </UIProvider>,
    );
    expect(screen.getByTestId('dock')).toHaveTextContent('drawer');

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('dock')).toHaveTextContent('drawer');

    // With the tour gone, Escape belongs to the store again.
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(screen.getByTestId('dock')).toHaveTextContent('none');
  });
});

describe('spotlight session gate', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it('a dismissed spotlight stays dismissed within the session', () => {
    // Seed the gate as already-seen, mirroring a prior dismissal.
    const source = read('components/PellierSpotlight.tsx');
    const keyMatch = source.match(/SPOTLIGHT_SEEN_KEY\s*=\s*['"]([^'"]+)['"]/);
    expect(keyMatch).not.toBeNull();
    window.sessionStorage.setItem(keyMatch![1], 'true');

    const { container } = render(<PellierSpotlight />);

    // Nothing rendered: the gate held.
    expect(container.textContent).toBe('');
  });
});

describe('spotlight in a second tab', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it('a tour dismissed in one tab stays closed in a new tab', () => {
    // Lab 4 opens PellierURL in Tab 2; a reopened tour covered the Operator link.
    const first = render(<PellierSpotlight />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    first.unmount();

    // A new tab starts with empty sessionStorage and the same localStorage.
    window.sessionStorage.clear();
    const { container } = render(<PellierSpotlight />);
    expect(container.textContent).toBe('');
  });
});
