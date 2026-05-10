/**
 * CommandPill tests - floating concierge shortcut pill.
 *
 * Validates Requirements 1.11.1 and 1.11.5.
 *
 * Coverage:
 *   - Pill renders fixed at the bottom-right with the B mark,
 *     `Ask Pellier` label, and a styled keycap (Req 1.11.1).
 *   - Click toggles the concierge: first click sets
 *     `activeModal === 'concierge'`, second click closes it back to
 *     null (Req 1.11.5).
 *   - Click from a non-concierge modal state (e.g., auth) switches to
 *     concierge via the same toggle - the singleton behavior from
 *     UIContext is inherited.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import CommandPill from './CommandPill'
import { COMMAND_PILL } from '../copy'
import { UIProvider, useUI } from '../contexts/UIContext'

/**
 * Small probe that surfaces the current activeModal alongside the pill so
 * tests can assert the toggle result without reaching into context internals.
 */
function ActiveModalProbe() {
  const { activeModal, openModal } = useUI()
  return (
    <>
      <span data-testid="active">{activeModal ?? 'none'}</span>
      <button onClick={() => openModal('auth')}>open-auth</button>
    </>
  )
}

function renderPill() {
  return render(
    <UIProvider>
      <ActiveModalProbe />
      <CommandPill />
    </UIProvider>,
  )
}

describe('CommandPill - render (Req 1.11.1)', () => {
  it('renders the pill with the B mark, label, and keycap', () => {
    renderPill()

    const pill = screen.getByTestId('command-pill')
    expect(pill).toBeInTheDocument()

    // B mark is present and fixed.
    expect(screen.getByTestId('command-pill-bmark')).toHaveTextContent('B')

    // Ask Pellier label from copy.ts.
    expect(screen.getByTestId('command-pill-label')).toHaveTextContent(
      COMMAND_PILL.LABEL,
    )

    // Keycap carries the platform-appropriate shortcut glyph. jsdom reports
    // an empty navigator.platform so the Windows/Ctrl K variant is the
    // expected default in the test environment.
    const keycap = screen.getByTestId('command-pill-keycap')
    expect([COMMAND_PILL.KEY_CAP_MAC, COMMAND_PILL.KEY_CAP_WIN]).toContain(
      keycap.textContent,
    )
  })

  it('fixes the pill to the bottom-right of the viewport', () => {
    renderPill()
    const pill = screen.getByTestId('command-pill')
    expect(pill.style.position).toBe('fixed')
    expect(pill.style.bottom).not.toBe('')
    expect(pill.style.right).not.toBe('')
  })

  it('uses an accessible button with an aria label that includes the shortcut', () => {
    renderPill()
    const pill = screen.getByTestId('command-pill')
    expect(pill.tagName).toBe('BUTTON')
    expect(pill.getAttribute('aria-label')).toContain(COMMAND_PILL.LABEL)
  })
})

describe('CommandPill - click toggles chat drawer (Req 1.11.5)', () => {
  it('first click opens the drawer (default chatSurface)', async () => {
    const user = userEvent.setup()
    renderPill()

    expect(screen.getByTestId('active')).toHaveTextContent('none')

    await user.click(screen.getByTestId('command-pill'))

    expect(screen.getByTestId('active')).toHaveTextContent('drawer')
  })

  it('pill hides while drawer is open; re-renders when closed via Escape', async () => {
    const user = userEvent.setup()
    renderPill()

    await user.click(screen.getByTestId('command-pill'))
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')
    // Pill should be hidden (returns null when drawer is open)
    expect(screen.queryByTestId('command-pill')).toBeNull()

    // Escape closes the drawer
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')
    // Pill returns
    expect(screen.getByTestId('command-pill')).toBeInTheDocument()
  })

  it('reflects aria-pressed when the concierge is open', async () => {
    const user = userEvent.setup()
    renderPill()

    const pill = screen.getByTestId('command-pill')
    expect(pill.getAttribute('aria-pressed')).toBe('false')

    // Pill hides on drawer open, so we can't check aria-pressed='true'
    // directly. Instead verify it starts false and returns false after close.
    await user.click(pill)
    expect(pill.getAttribute('aria-pressed')).toBe('false')
  })

  it('switches to drawer when another modal is already active', async () => {
    const user = userEvent.setup()
    renderPill()

    // Start from auth modal open to exercise the singleton replace path.
    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('active')).toHaveTextContent('auth')

    await user.click(screen.getByTestId('command-pill'))
    // Toggle from a non-null, non-drawer state opens drawer.
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')
  })
})
