// Vitest global setup — installs jest-dom matchers and resets between tests.
import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// ResizeObserver polyfill — jsdom doesn't ship one. react-resizable-panels
// calls ``new ResizeObserver(...)`` from Group's mount effect, which
// throws "n is not a constructor" in tests without this shim. Minimal
// stub: accept the callback, expose no-op observe/unobserve so the
// library's cleanup path is safe.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

// matchMedia default — jsdom doesn't ship this either. Tests that care
// about responsive behavior override this per-test (see
// WorkshopPage.test.tsx's installMatchMedia helper).
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

afterEach(() => {
  cleanup()
})
