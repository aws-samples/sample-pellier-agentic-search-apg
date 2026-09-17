import { describe, expect, it } from 'vitest';

import {
  INTERACTIVE_PATHS,
  interactionForPath,
  isInteractivePath,
  modeCopyForPath,
} from '../shell/observatoryInteraction';

describe('governed Labs interaction contract', () => {
  it('treats every declared interactive path as interactive', () => {
    for (const path of INTERACTIVE_PATHS) {
      expect(interactionForPath(path), path).toBe('interactive');
      expect(isInteractivePath(path), path).toBe(true);
    }
  });

  it('normalizes a trailing slash on the lab workbench', () => {
    expect(interactionForPath('/observatory/')).toBe('interactive');
    expect(modeCopyForPath('/observatory/').label).toBe('Labs & Workbench');
    expect(modeCopyForPath('/observatory/').detail).toBe(
      'Follow the four labs in order, then use Workbench to inspect the evidence for each change.',
    );
  });

  it('keeps governed supporting surfaces optional', () => {
    for (const path of [
      '/observatory/tools',
      '/observatory/search',
      '/observatory/skills',
      '/observatory/memory',
      '/observatory/proof-board',
      '/observatory/audit-proof',
      '/observatory/architecture',
      '/observatory/govern/policies',
      '/observatory/performance',
      '/observatory/production-patterns',
    ]) {
      expect(interactionForPath(path), path).toBe('reference');
      expect(modeCopyForPath(path).label, path).toBe('Reference view');
      // Optionality is the top-bar badge's job. When this banner said it too,
      // and the page intro said it a third time, the screen argued with itself.
      expect(modeCopyForPath(path).detail, path).not.toMatch(/optional/i);
    }
    expect(modeCopyForPath('/observatory/references').detail).toBe(
      'Inspect system evidence and implementation detail without starting a new shopper turn.',
    );
  });

  it('does not let an interactive path match a similarly named sibling', () => {
    expect(isInteractivePath('/observatory/toolsmith')).toBe(false);
    expect(isInteractivePath('/observatory/searchable')).toBe(false);
  });

  it('keeps nested supporting routes optional', () => {
    expect(interactionForPath('/observatory/tools/search_products')).toBe(
      'reference',
    );
    expect(interactionForPath('/observatory/architecture/runtime')).toBe(
      'reference',
    );
  });
});
