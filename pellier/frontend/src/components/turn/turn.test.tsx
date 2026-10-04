/**
 * The small shared pieces: status tags, the status line, the Builder view
 * preferences, the evidence formatter and the prose parser.
 */
import { act, render, renderHook, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import StatusLine from './StatusLine'
import StatusTag from './StatusTag'
import RevealedProse from './RevealedProse'
import { identitySentence } from './evidence'
import { parseProse, sentenceEndAfter } from './prose'
import {
  BUILDER_VIEW_KEY,
  SKILL_MODE_KEY,
  readBuilderView,
  readSkillMode,
  useBuilderView,
  useSkillMode,
} from './preferences'
import { upsertStep } from './turnTypes'

describe('StatusTag', () => {
  it('maps the three roles to tones and keeps the word on the tag', () => {
    render(
      <>
        <StatusTag tone="good">In stock</StatusTag>
        <StatusTag tone="blocked">Sold out</StatusTag>
        <StatusTag tone="pending" pulse>Waiting for Nadia</StatusTag>
      </>,
    )
    const tags = screen.getAllByTestId('status-tag')
    expect(tags.map(tag => tag.getAttribute('data-tone'))).toEqual(['good', 'blocked', 'pending'])
    expect(tags.map(tag => tag.textContent)).toEqual(['In stock', 'Sold out', 'Waiting for Nadia'])
    expect(tags[2].querySelector('.tn-dot')).not.toBeNull()
    expect(tags[0].querySelector('.tn-dot')).toBeNull()
  })
})

describe('StatusLine', () => {
  it('names the step and carries its state for the pulse', () => {
    const { rerender } = render(<StatusLine label="Searching the catalog in Aurora" state="working" />)
    const line = screen.getByTestId('turn-status')
    expect(line).toHaveTextContent('Searching the catalog in Aurora')
    expect(line).toHaveAttribute('data-state', 'working')
    rerender(<StatusLine label="Stopped before an answer" state="failed" />)
    expect(line).toHaveAttribute('data-state', 'failed')
  })
})

describe('Builder view preferences', () => {
  beforeEach(() => localStorage.clear())

  it('is off by default and remembered per browser', () => {
    expect(readBuilderView()).toBe(false)
    const { result } = renderHook(() => useBuilderView())
    expect(result.current[0]).toBe(false)
    act(() => result.current[1](true))
    expect(result.current[0]).toBe(true)
    expect(localStorage.getItem(BUILDER_VIEW_KEY)).toBe('on')
    expect(renderHook(() => useBuilderView()).result.current[0]).toBe(true)
  })

  it('keeps the agent on fixed skills unless the flex is switched on', () => {
    expect(readSkillMode()).toBe('fixed')
    const { result } = renderHook(() => useSkillMode())
    act(() => result.current[1]('on_demand'))
    expect(localStorage.getItem(SKILL_MODE_KEY)).toBe('on_demand')
    expect(readSkillMode()).toBe('on_demand')
  })
})

describe('identitySentence', () => {
  it('states what the model asked for and what the server bound', () => {
    expect(identitySentence({ binding: 'overwritten', requested_customer: 'CUST-JESSICA', bound_customer: 'CUST-THEO', authorized_customer: 'CUST-THEO' }))
      .toBe('model asked for CUST-JESSICA, server bound CUST-THEO (overwritten)')
    expect(identitySentence({ binding: 'matched', requested_customer: 'CUST-THEO', bound_customer: 'CUST-THEO', authorized_customer: 'CUST-THEO' }))
      .toBe('bound CUST-THEO')
    expect(identitySentence({ binding: 'bound', requested_customer: null, bound_customer: 'CUST-THEO', authorized_customer: 'CUST-THEO' }))
      .toBe('bound CUST-THEO')
    expect(identitySentence({ binding: 'refused', requested_customer: 'CUST-JESSICA', bound_customer: null, authorized_customer: 'CUST-THEO' }))
      .toBe('model asked for CUST-JESSICA, server refused; signed in as CUST-THEO')
    expect(identitySentence({ binding: 'unbound', requested_customer: null, bound_customer: null, authorized_customer: null }))
      .toBe('no signed-in account, handoff ran unbound')
  })
})

describe('parseProse', () => {
  it('keeps paragraphs, bullets and bold with source indexes', () => {
    const blocks = parseProse('Start with the **Wabi-Sabi Bowl** at $24.\n\n- one\n- two')
    expect(blocks.map(block => block.kind)).toEqual(['p', 'li', 'li'])
    expect(blocks[0].runs.map(run => [run.bold, run.text])).toEqual([
      [false, 'Start with the '], [true, 'Wabi-Sabi Bowl'], [false, ' at $24.'],
    ])
    expect(blocks[0].runs[1].start).toBe('Start with the **'.length)
    expect(blocks[1].runs[0].text).toBe('one')
  })

  it('reads an unclosed bold during the reveal as bold', () => {
    const blocks = parseProse('Start with the **Wabi-Sa')
    expect(blocks[0].runs[1]).toMatchObject({ bold: true, text: 'Wabi-Sa' })
  })

  it('finds the end of the sentence that names a product', () => {
    const text = 'Start with the Wabi-Sabi Bowl at $24. The Ceramic Tumblers pair well.'
    expect(text.slice(0, sentenceEndAfter(text, 'Wabi-Sabi Bowl'))).toBe('Start with the Wabi-Sabi Bowl at $24.')
    expect(sentenceEndAfter(text, 'Linen Throw')).toBe(-1)
  })
})

describe('upsertStep', () => {
  it('merges a running step into its done event by id', () => {
    const running = { id: 'step-1', label: 'Searching', status: 'running' as const, tags: ['Aurora'] }
    const done = { ...running, status: 'done' as const, finding: '3 found' }
    expect(upsertStep(upsertStep([], running), done)).toEqual([done])
  })
})

describe('RevealedProse', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })
  afterEach(() => vi.useRealTimers())

  it('settles characters in one at a time and finishes within the bound', () => {
    const progress: Array<[number, boolean]> = []
    const { container, rerender } = render(
      <RevealedProse text="Start with the mugs." done={false} onProgress={(length, finished) => progress.push([length, finished])} />,
    )
    act(() => { vi.advanceTimersByTime(0) })
    expect(container.querySelectorAll('.tn-ch')).toHaveLength(1)
    act(() => { vi.advanceTimersByTime(24 * 4) })
    expect(container.querySelectorAll('.tn-ch')).toHaveLength(5)
    rerender(<RevealedProse text="Start with the mugs." done onProgress={(length, finished) => progress.push([length, finished])} />)
    act(() => { vi.advanceTimersByTime(1500) })
    expect(container.textContent).toBe('Start with the mugs.')
    expect(container.querySelectorAll('.tn-ch')).toHaveLength(0)
    expect(progress.at(-1)).toEqual(['Start with the mugs.'.length, true])
  })

  it('shows a message from history at once', () => {
    const { container } = render(<RevealedProse text="Already answered." done instant />)
    expect(container.textContent).toBe('Already answered.')
    expect(container.querySelector('.tn-prose-live')).toBeNull()
  })

  it('survives the StrictMode mount, unmount and mount again of development', () => {
    const { container } = render(
      <StrictMode>
        <RevealedProse text="Start with the mugs." done />
      </StrictMode>,
    )
    act(() => { vi.advanceTimersByTime(0) })
    expect(container.querySelectorAll('.tn-ch').length).toBeGreaterThan(0)
    act(() => { vi.advanceTimersByTime(1500) })
    expect(container.textContent).toBe('Start with the mugs.')
    expect(container.querySelector('.tn-prose-live')).toBeNull()
  })

  it('still reveals a live turn whose stream completed before its first paint', () => {
    const { container } = render(<RevealedProse text="Start with the mugs." done />)
    act(() => { vi.advanceTimersByTime(0) })
    expect(container.querySelectorAll('.tn-ch')).toHaveLength(1)
    act(() => { vi.advanceTimersByTime(1500) })
    expect(container.textContent).toBe('Start with the mugs.')
  })
})
