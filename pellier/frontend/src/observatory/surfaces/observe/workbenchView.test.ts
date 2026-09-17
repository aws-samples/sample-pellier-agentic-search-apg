import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockWorkbenchWidth } from '../../../test-support/workbenchViewport';
import { focusStepIndex, useCompactWorkbench } from './workbenchView';

describe('responsive Workbench', () => {
  it('follows viewport changes and ignores the retired expertise preference', () => {
    localStorage.setItem('pellier-observatory-view', 'focus');
    const resize = mockWorkbenchWidth(1440);
    const { result } = renderHook(useCompactWorkbench);
    expect(result.current).toBe(false);
    resize(900);
    expect(result.current).toBe(true);
    resize(1280);
    expect(result.current).toBe(false);
  });

  it('keeps addressable panel navigation and handles invalid bookmarks', () => {
    expect(focusStepIndex('run')).toBe(0);
    expect(focusStepIndex('inspect')).toBe(1);
    expect(focusStepIndex('reconcile')).toBe(2);
    expect(focusStepIndex('unknown')).toBe(0);
  });
});
