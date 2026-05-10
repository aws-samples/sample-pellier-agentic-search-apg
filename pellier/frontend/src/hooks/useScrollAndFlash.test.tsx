/**
 * useScrollAndFlash tests — cross-panel scroll + 800ms flash.
 *
 * Pure-DOM behavior — we stub scrollIntoView (jsdom doesn't implement
 * it) and assert the resolver finds the right target + stamps the
 * data-flash attribute.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useScrollAndFlash } from './useScrollAndFlash'

function mountContainerWithPanels(): HTMLDivElement {
  const container = document.createElement('div')
  container.innerHTML = `
    <div data-testid="plan-card">plan</div>
    <div data-testid="panel-card-TOOL · SEARCH">search</div>
    <div data-testid="panel-card-MEMORY · PROCEDURAL">memory</div>
    <div data-testid="panel-card-LLM · OPUS · SYNTHESIZE">llm</div>
  `
  document.body.appendChild(container)
  // jsdom lacks scrollIntoView by default.
  const scrollIntoViewMock = vi.fn()
  for (const el of container.querySelectorAll('div')) {
    ;(el as HTMLDivElement).scrollIntoView = scrollIntoViewMock
  }
  return container
}

describe('useScrollAndFlash', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    document.body.innerHTML = ''
    vi.useRealTimers()
  })

  it('resolves "plan" to the plan-card and stamps data-flash for 800ms', () => {
    const container = mountContainerWithPanels()
    const { result } = renderHook(() => useScrollAndFlash())
    act(() => {
      result.current.containerRef.current = container
    })
    act(() => {
      result.current.scrollToTrace('plan')
    })
    const plan = container.querySelector('[data-testid="plan-card"]')!
    expect(plan.getAttribute('data-flash')).toBe('true')
    act(() => {
      vi.advanceTimersByTime(800)
    })
    expect(plan.getAttribute('data-flash')).toBeNull()
  })

  it('resolves "trace N" to the Nth panel-card (1-based)', () => {
    const container = mountContainerWithPanels()
    const { result } = renderHook(() => useScrollAndFlash())
    act(() => {
      result.current.containerRef.current = container
    })
    act(() => {
      result.current.scrollToTrace('trace 2')
    })
    const second = container.querySelector(
      '[data-testid="panel-card-MEMORY · PROCEDURAL"]',
    )!
    expect(second.getAttribute('data-flash')).toBe('true')
  })

  it('resolves a panel tag string directly to the matching card', () => {
    const container = mountContainerWithPanels()
    const { result } = renderHook(() => useScrollAndFlash())
    act(() => {
      result.current.containerRef.current = container
    })
    act(() => {
      result.current.scrollToTrace('TOOL · SEARCH')
    })
    const tool = container.querySelector(
      '[data-testid="panel-card-TOOL · SEARCH"]',
    )!
    expect(tool.getAttribute('data-flash')).toBe('true')
  })

  it('no-ops silently when the reference does not resolve', () => {
    const container = mountContainerWithPanels()
    const { result } = renderHook(() => useScrollAndFlash())
    act(() => {
      result.current.containerRef.current = container
    })
    expect(() => {
      act(() => {
        result.current.scrollToTrace('NONEXISTENT TAG')
      })
    }).not.toThrow()
    const flashed = container.querySelector('[data-flash="true"]')
    expect(flashed).toBeNull()
  })

  it('no-ops when containerRef has not been attached', () => {
    const { result } = renderHook(() => useScrollAndFlash())
    expect(() => {
      act(() => {
        result.current.scrollToTrace('plan')
      })
    }).not.toThrow()
  })
})
