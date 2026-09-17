import { describe, expect, it } from 'vitest';

import {
  interactionForPath,
  modeCopyForPath,
} from './observatoryInteraction';

describe('observatory interaction routing', () => {
  it.each([
    ['/observatory', 'Labs & Workbench'],
    ['/observatory/labs/grounded-inventory', 'Lab workspace'],
    ['/observatory/workbench', 'Labs & Workbench'],
  ])('treats %s as an interactive %s surface', (path, label) => {
    expect(interactionForPath(path)).toBe('interactive');
    expect(modeCopyForPath(path).label).toBe(label);
  });

  it('keeps proof and implementation destinations as reference views', () => {
    expect(interactionForPath('/observatory/proof-board')).toBe('reference');
    expect(modeCopyForPath('/observatory/proof-board').label).toBe(
      'Reference view',
    );
  });
});
