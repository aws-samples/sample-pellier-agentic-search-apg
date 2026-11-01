import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Toast from './Toast'

describe('Toast', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('keeps a polite live region mounted so the message is announced when it appears', () => {
    const { rerender } = render(<Toast message="Added to bag" show={false} onClose={vi.fn()} />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toBeEmptyDOMElement()

    rerender(<Toast message="Added to bag" show onClose={vi.fn()} />)
    expect(screen.getByRole('status')).toBe(region)
    expect(region).toHaveTextContent('Added to bag')
  })

  it('closes after the duration and the exit transition', () => {
    const onClose = vi.fn()
    render(<Toast message="Added to bag" show duration={1000} onClose={onClose} />)
    act(() => { vi.advanceTimersByTime(1000) })
    expect(onClose).not.toHaveBeenCalled()
    act(() => { vi.advanceTimersByTime(300) })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not call onClose after unmount', () => {
    const onClose = vi.fn()
    const { unmount } = render(<Toast message="Added to bag" show duration={1000} onClose={onClose} />)
    act(() => { vi.advanceTimersByTime(1000) })
    unmount()
    act(() => { vi.advanceTimersByTime(1000) })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not call onClose after unmount following a dismiss click', () => {
    const onClose = vi.fn()
    const { unmount } = render(<Toast message="Added to bag" show onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    unmount()
    act(() => { vi.advanceTimersByTime(1000) })
    expect(onClose).not.toHaveBeenCalled()
  })
})
