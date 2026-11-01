/**
 * The focus trap has to survive an unstable `onClose`.
 *
 * Every caller passes an inline arrow, so `onClose` is a new function on each
 * parent render. With that identity in the effect's dependency array the
 * whole effect tears down and sets up again on every render: the cleanup
 * refocuses the opener, so focus jumps out of the dialog mid-interaction, and
 * the setup re-reads `document.activeElement` as the opener, so the thing the
 * trap promises to restore drifts to whatever happened to be focused.
 *
 * A dialog claiming `aria-modal` also has to hold focus in the first place,
 * including when nothing inside it is focusable yet: PersonaModal's list
 * arrives from the network, so "no focusable children" is a real state a
 * participant can Tab through.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useFocusTrap } from './useFocusTrap'

interface HarnessProps {
  /** Rendered inside the dialog. Empty means "nothing focusable yet". */
  withControls?: boolean
  onClose?: () => void
}

/**
 * A dialog whose parent re-renders on demand and whose `onClose` is a fresh
 * arrow every time, exactly like Header and DetailPageShell.
 */
function Harness({ withControls = true, onClose }: HarnessProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const [, setTick] = useState(0)
  useFocusTrap({
    containerRef: dialogRef,
    active: true,
    onClose: () => onClose?.(),
  })
  return (
    <>
      <button type="button" data-testid="opener">
        Opener
      </button>
      <button
        type="button"
        data-testid="rerender"
        onClick={() => setTick((value) => value + 1)}
      >
        Re-render parent
      </button>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Chooser">
        {withControls ? (
          <>
            <button type="button" data-testid="first">
              First
            </button>
            <button type="button" data-testid="last">
              Last
            </button>
          </>
        ) : null}
      </div>
    </>
  )
}

describe('useFocusTrap', () => {
  it('keeps focus inside the dialog when the parent re-renders', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    const inside = screen.getByTestId('last')
    inside.focus()
    expect(document.activeElement).toBe(inside)

    // The parent re-renders. Nothing about the dialog changed, so nothing
    // about the focus position should either.
    await user.click(screen.getByTestId('rerender'))
    inside.focus()
    fireEvent.click(screen.getByTestId('rerender'))

    expect(document.activeElement).toBe(inside)
  })

  it('calls the latest onClose without re-running the trap', () => {
    // Holding a callback in a ref only works if the ref is kept current.
    // Escape must reach the newest handler, and the swap must not disturb
    // focus on the way.
    const stale = vi.fn()
    const current = vi.fn()
    const { rerender } = render(<Harness onClose={stale} />)

    const inside = screen.getByTestId('first')
    inside.focus()
    rerender(<Harness onClose={current} />)

    expect(document.activeElement).toBe(inside)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(current).toHaveBeenCalledTimes(1)
    expect(stale).not.toHaveBeenCalled()
  })

  it('marks Escape as handled so global shortcuts do not act on it too', () => {
    render(<Harness />)
    const notCancelled = fireEvent.keyDown(document, { key: 'Escape' })
    expect(notCancelled).toBe(false)
  })

  it('moves focus into the dialog when it opens', () => {
    render(<Harness />)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toContainElement(document.activeElement as HTMLElement)
  })

  it('holds Tab inside a dialog with nothing focusable in it yet', () => {
    render(<Harness withControls={false} />)

    const dialog = screen.getByRole('dialog')
    expect(document.activeElement).toBe(dialog)

    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(dialog)

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(dialog)
  })

  it('wraps Tab and Shift+Tab across the dialog edges', () => {
    render(<Harness />)

    const first = screen.getByTestId('first')
    const last = screen.getByTestId('last')

    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(first)

    first.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  it('sends Shift+Tab from the dialog itself to the last control', () => {
    render(<Harness />)

    const dialog = screen.getByRole('dialog')
    dialog.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })

    expect(document.activeElement).toBe(screen.getByTestId('last'))
  })
})
