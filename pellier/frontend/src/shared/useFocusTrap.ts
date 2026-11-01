/**
 * Focus containment for a modal dialog.
 *
 * A dialog that does not trap focus is a dialog a keyboard user can tab
 * behind: the page underneath is still reachable, still clickable, and still
 * announced, while the dialog claims `aria-modal`. This hook moves focus into
 * the container when it opens, keeps Tab and Shift+Tab inside it, closes on
 * Escape, and returns focus to whatever opened the dialog.
 */
import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

/**
 * Focusable descendants in DOM order.
 *
 * Visibility is judged by the `hidden` attribute and `aria-hidden`, not by
 * layout: `offsetParent` is always null under jsdom, so a layout-based filter
 * silently collapses the list to one element and the wrap stops working in
 * exactly the environment that tests it.
 */
function focusableWithin(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (node) => !node.closest('[hidden], [aria-hidden="true"]'),
  )
}

/**
 * Make the container itself able to hold focus.
 *
 * The dialog carries the accessible name, so it is the right first stop, and
 * it is where focus parks when the contents have not arrived yet.
 */
function focusContainer(container: HTMLElement): void {
  if (!container.hasAttribute('tabindex')) {
    container.setAttribute('tabindex', '-1')
  }
  container.focus()
}

export interface FocusTrapOptions {
  /** The dialog element. Nothing is trapped until it exists. */
  containerRef: RefObject<HTMLElement | null>
  /** Whether the dialog is open. */
  active: boolean
  /** Called on Escape. May be a new function on every render. */
  onClose: () => void
  /**
   * Whether this hook owns focus placement: moving it into the container on
   * open and returning it to the opener on close. Pass false when the caller
   * already does both, so the two do not fight over `document.activeElement`.
   */
  manageFocus?: boolean
}

/** Trap Tab within `containerRef`, close on Escape, restore focus on exit. */
export function useFocusTrap({
  containerRef,
  active,
  onClose,
  manageFocus = true,
}: FocusTrapOptions): void {
  /**
   * `onClose` is read at keystroke time, never at effect time.
   *
   * Every caller passes an inline arrow, so listing it as a dependency would
   * tear the trap down and set it up again on every parent render: the
   * cleanup would pull focus back to the opener mid-interaction, and the
   * setup would re-read the opener as whatever was focused inside the dialog.
   */
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!active) return
    const opener =
      manageFocus && document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null

    const container = containerRef.current
    if (manageFocus && container) focusContainer(container)

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const node = containerRef.current
      if (!node) return
      const focusable = focusableWithin(node)
      const activeElement = document.activeElement

      // Nothing inside can hold focus yet: PersonaModal's list arrives from
      // the network. Letting Tab through here hands the next stop to the page
      // behind a dialog that claims to be modal.
      if (focusable.length === 0) {
        event.preventDefault()
        focusContainer(node)
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      // Focus on the container itself is the state the dialog opens in.
      // Forward Tab would reach `first` anyway; Shift+Tab would leave.
      if (!node.contains(activeElement) || activeElement === node) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
        return
      }
      if (event.shiftKey && activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true)
      opener?.focus()
    }
  }, [active, containerRef, manageFocus])
}
