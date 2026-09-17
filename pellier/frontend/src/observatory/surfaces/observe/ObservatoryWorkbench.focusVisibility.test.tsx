/**
 * Focus mode must actually hide the panels it steps back.
 *
 * The workbench sets the `hidden` attribute on the two panels that are not
 * the current step. That attribute hides nothing on its own: some rule has to
 * win the cascade, and the two in play are evenly matched.
 *
 *   Tailwind preflight   `[hidden]:where(:not([hidden="until-found"]))`
 *                        `:where()` contributes zero, so (0,1,0)
 *   workbench stylesheet `.observatory-input-panel` and its two siblings
 *                        `display: flex`, also (0,1,0)
 *
 * The build emits the workbench stylesheet as a lazy chunk loaded after
 * index.css, so on a tie the later `display: flex` wins and every panel stays
 * on screen: three stacked panels and a stepper that appears to do nothing.
 * A real browser's UA rule for `[hidden]` loses to any author rule, so it
 * does not save the feature either.
 *
 * The rest of the suite runs with `css: false`, so an assertion on
 * `data-focus-active` passes whether or not anything is hidden. This file
 * splits the claim in two and asserts both halves:
 *
 *   1. the component marks the right panels `hidden`, read off a real render;
 *   2. the shipped stylesheets, loaded in shipped order, resolve a marked
 *      panel to `display: none`.
 *
 * Both are needed. Delete the hiding rule from the stylesheet and (2) reads
 * `flex`. Rename or drop the `hidden` attribute and (1) fails. The class
 * names in (2) are the ones (1) reads off the live DOM, so a rename cannot
 * leave the cascade assertions quietly testing selectors nothing renders.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { mockWorkbenchWidth } from '../../../test-support/workbenchViewport';

const mocks = vi.hoisted(() => ({
  sendChatMessageStreaming: vi.fn(),
}));

vi.mock('../../../services/chat', () => ({
  sendChatMessageStreaming: mocks.sendChatMessageStreaming,
}));

// One stable object: a fresh persona object per render re-runs the reset
// effect, which is a separate defect with its own test.
const MARCO = { id: 'marco', display_name: 'Marco', customer_id: 'CUST-MARCO' };

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: MARCO,
    switchPersona: vi.fn(),
    switching: false,
    switchError: null,
  }),
}));

import ObservatoryWorkbench from './ObservatoryWorkbench';

const HERE = dirname(fileURLToPath(import.meta.url));

/**
 * Tailwind 3.4 preflight, verbatim from
 * `node_modules/tailwindcss/src/css/preflight.css`. Copied rather than
 * imported because the built index.css is a compile artefact; this is the one
 * rule in it that competes with the panels.
 */
const PREFLIGHT_HIDDEN =
  '[hidden]:where(:not([hidden="until-found"])) { display: none; }';

const WORKBENCH_CSS = readFileSync(
  join(HERE, 'ObservatoryWorkbench.css'),
  'utf8',
);

const PANEL_CLASSES = [
  'observatory-input-panel',
  'observatory-trace-panel',
  'observatory-results-panel',
] as const;

function scenariosResponse(): Response {
  return new Response(
    JSON.stringify({
      persona: 'marco',
      scenarios: [
        {
          id: 1,
          ordinal: 1,
          prompt: 'First guided turn',
          productName: null,
          imageUrl: null,
        },
      ],
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

function renderWorkbench() {
  return render(
    <MemoryRouter
      initialEntries={['/observatory/workbench?lab=grounded-inventory']}
    >
      <ObservatoryWorkbench />
    </MemoryRouter>,
  );
}

/** Every grid panel, as `[panel class, hidden?]`, read off the live DOM. */
function panelState(): Array<[string, boolean]> {
  const grid = document.querySelector('.observatory-workbench-grid');
  if (!grid) throw new Error('grid not rendered');
  return Array.from(grid.children).map((node) => [
    PANEL_CLASSES.find((name) => node.classList.contains(name)) ??
      `unrecognised: ${node.className}`,
    node.hasAttribute('hidden'),
  ]);
}

let sheets: HTMLStyleElement[] = [];

/**
 * Load preflight and the workbench stylesheet in the order the build emits
 * them: index.css carries preflight, the workbench chunk loads after it.
 * Reversing these lets preflight win on source order and masks exactly the
 * bug this file exists to catch.
 */
function loadShippedCss(): void {
  sheets = [PREFLIGHT_HIDDEN, WORKBENCH_CSS].map((text) => {
    const style = document.createElement('style');
    style.textContent = text;
    document.head.appendChild(style);
    return style;
  });
}

function unloadShippedCss(): void {
  sheets.forEach((style) => style.remove());
  sheets = [];
}

/**
 * Computed `display` for one panel under the loaded stylesheets.
 *
 * A bare grid rather than the rendered workbench: the cascade question is
 * about three selectors, and jsdom recomputes styles for every node in the
 * document, so the real tree would only make this slow. The class names come
 * from the render assertion above, which is what keeps the two in step.
 */
function displayUnderShippedCss(
  panelClass: string,
  { hidden }: { hidden: boolean },
): string {
  const grid = document.createElement('div');
  grid.className = 'observatory-workbench-grid';
  grid.setAttribute('data-view', 'focus');
  const panel = document.createElement('div');
  panel.className = panelClass;
  if (hidden) panel.setAttribute('hidden', '');
  grid.appendChild(panel);
  document.body.appendChild(grid);
  try {
    return window.getComputedStyle(panel).display;
  } finally {
    grid.remove();
  }
}

describe('Narrow Workbench layout really hides the other panels', () => {
  let resize: (width: number) => void;
  beforeEach(() => {
    localStorage.clear();
    resize = mockWorkbenchWidth(900);
    mocks.sendChatMessageStreaming.mockReset();
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'A grounded answer.',
      products: [],
      suggestions: [],
    });
    vi.stubGlobal('fetch', vi.fn(async () => scenariosResponse()));
  });

  it('marks every panel but the current step hidden, and moves the mark', async () => {
    const user = userEvent.setup();
    renderWorkbench();

    expect(panelState()).toEqual([
      ['observatory-input-panel', false],
      ['observatory-trace-panel', true],
      ['observatory-results-panel', true],
    ]);

    await user.click(screen.getByRole('button', { name: /Reconcile answer/ }));

    expect(panelState()).toEqual([
      ['observatory-input-panel', true],
      ['observatory-trace-panel', true],
      ['observatory-results-panel', false],
    ]);

    resize(1440);

    expect(panelState()).toEqual([
      ['observatory-input-panel', false],
      ['observatory-trace-panel', false],
      ['observatory-results-panel', false],
    ]);
  });

});

describe('Observatory workbench panel cascade', () => {
  beforeAll(loadShippedCss);
  afterAll(unloadShippedCss);

  it('resolves a marked panel to display:none under the shipped stylesheets', () => {
    PANEL_CLASSES.forEach((panelClass) => {
      expect(
        displayUnderShippedCss(panelClass, { hidden: true }),
        `${panelClass} stays visible with the hidden attribute set`,
      ).toBe('none');
    });
  });

  it('leaves an unmarked panel laid out as a flex column', () => {
    PANEL_CLASSES.forEach((panelClass) => {
      expect(displayUnderShippedCss(panelClass, { hidden: false })).toBe('flex');
    });
  });
});
