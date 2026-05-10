/**
 * Shared test utilities.
 *
 * ``TEST_ROUTER_FUTURE_FLAGS`` mirrors the future-flag object the
 * production BrowserRouter in App.tsx already opts into. MemoryRouter
 * in test files needs the same object so React Router doesn't emit v7
 * migration warnings on every render.
 *
 * When react-router-v7 ships and these flags become the default, this
 * constant can be deleted in one sweep.
 */
import type { FutureConfig } from 'react-router-dom'

export const TEST_ROUTER_FUTURE_FLAGS: Partial<FutureConfig> = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
}
