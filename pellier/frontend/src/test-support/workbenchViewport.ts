import { act } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import { WORKBENCH_COMPACT_QUERY } from '../observatory/surfaces/observe/workbenchView';

afterEach(() => vi.unstubAllGlobals());

/** Drive the actual responsive subscription, including a resize during a run. */
export function mockWorkbenchWidth(initial: number) {
  let width = initial;
  const listeners = new Set<() => void>();
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    get matches() { return query === WORKBENCH_COMPACT_QUERY && width <= 1100; },
    media: query,
    onchange: null,
    addEventListener: (_: string, listener: () => void) => {
      if (query === WORKBENCH_COMPACT_QUERY) listeners.add(listener);
    },
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })));
  return (next: number) => act(() => {
    width = next;
    listeners.forEach(listener => listener());
  });
}
