/**
 * E2E: Persona modal portal regression gate.
 *
 * Guards against the containing-block bug where a parent with
 * ``backdrop-filter`` (the sticky storefront header) traps the modal's
 * ``position: fixed`` descendant. The fix was ``createPortal`` onto
 * ``document.body``; this test catches regressions if any future
 * ancestor introduces another containing-block creator (transform,
 * filter, contain, etc.) that re-traps the modal.
 *
 * The assertion is cheap: the modal backdrop's bounding rect must
 * equal the viewport's bounding rect. If that holds, the portal is
 * working and the CSS is being interpreted in the correct stacking
 * context.
 *
 * Runs against the production build on port 8000 (same pattern as
 * workshop-smoke.spec.ts). Requires backend + prod build served; see
 * playwright.config.ts for how the dev server is spawned.
 */

import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8000';

test.describe('Persona modal — portal + viewport coverage', () => {
  test('backdrop fills the viewport when opened from the storefront', async ({
    page,
  }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // The storefront header "Sign in" pill opens the modal.
    await page.getByTestId('persona-pill').click();

    const backdrop = page.getByTestId('persona-modal-backdrop');
    await expect(backdrop).toBeVisible();

    // Assert the backdrop's bounding rect matches the viewport. If
    // any ancestor creates a containing block, the rect will be
    // smaller — this is the bug we're guarding against.
    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();

    const box = await backdrop.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBe(0);
    expect(box!.y).toBe(0);
    expect(box!.width).toBe(viewport!.width);
    expect(box!.height).toBe(viewport!.height);

    // The backdrop's DOM parent must be <body> — the portal target.
    // If a future change rendered the modal inline, this would fail.
    const parentTag = await backdrop.evaluate(
      (el) => el.parentElement?.tagName ?? '',
    );
    expect(parentTag).toBe('BODY');

    // All three persona cards should be reachable (not clipped).
    await expect(page.getByTestId('persona-card-marco')).toBeVisible();
    await expect(page.getByTestId('persona-card-anna')).toBeVisible();
    await expect(page.getByTestId('persona-card-fresh')).toBeVisible();
  });

  test('backdrop click dismisses the modal', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    await page.getByTestId('persona-pill').click();
    const backdrop = page.getByTestId('persona-modal-backdrop');
    await expect(backdrop).toBeVisible();

    // Click the backdrop corner (not the card).
    await backdrop.click({ position: { x: 10, y: 10 } });
    await expect(backdrop).toBeHidden();
  });
});
