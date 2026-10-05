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
import { evidenceLine, identitySentence } from './evidence'
import { emphasisRanges, parseProse, sentenceEndAfter } from './prose'
import {
  BUILDER_VIEW_KEY,
  SKILL_MODE_KEY,
  readBuilderView,
  readSkillMode,
  useBuilderView,
  useSkillMode,
} from './preferences'
import { upsertStep, type TurnStep } from './turnTypes'

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

  it('names another customer when the managed rail withheld an id that was not one', () => {
    expect(identitySentence({ binding: 'overwritten', requested_customer: null, bound_customer: 'CUST-THEO', authorized_customer: 'CUST-THEO' }))
      .toBe('model asked for another customer, server bound CUST-THEO (overwritten)')
  })
})

describe('evidenceLine', () => {
  it('shows the limits kept from earlier in the conversation', () => {
    const line = evidenceLine({
      id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', tags: ['Aurora'],
      builder: {
        tool: 'search_products', rail: 'in-process', audit_id: 9040, receipt_id: 6,
        requirements: { applied: ['under $100', 'in stock', 'no candles'], carried: ['under $100', 'in stock', 'no candles'] },
      },
    })
    expect(line).toBe('kept from earlier: under $100, in stock, no candles; audit row 9040; receipt 6; rail in-process')
    const first = evidenceLine({
      id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', tags: ['Aurora'],
      builder: { tool: 'search_products', requirements: { applied: ['under $100'], carried: [] } },
    })
    expect(first).not.toContain('kept from earlier')
  })

  it('says when the answer was cut short, and nothing for a turn that ended normally', () => {
    const route = (stop_reason: string | null) => ({
      id: 'route', label: 'Understanding your request', status: 'done' as const, tags: ['Router'],
      builder: { tool: null, intent: 'shopping', model_id: 'global.anthropic.claude-opus-5', stop_reason },
    })
    expect(evidenceLine(route('max_tokens'))).toBe(
      'intent shopping; model global.anthropic.claude-opus-5; answer cut short (max_tokens)',
    )
    expect(evidenceLine(route('end_turn'))).toBe('intent shopping; model global.anthropic.claude-opus-5')
    expect(evidenceLine(route(null))).toBe('intent shopping; model global.anthropic.claude-opus-5')
    expect(evidenceLine(route('guardrail_intervened'))).toContain('stop guardrail_intervened')
  })

  it('names the AgentCore Memory record the prompt carried, apart from the Aurora record', () => {
    const route = {
      id: 'route', label: 'Understanding your request', status: 'done' as const, tags: ['Router', 'Memory'],
      builder: {
        tool: null, intent: 'shopping',
        memory: { facts: 1, orders: 4, source: 'Aurora PostgreSQL' },
        remembered: { source: 'agentcore-memory', strategy: 'USER_PREFERENCE', records: ['mem-theo-1'] },
      },
    }
    expect(evidenceLine(route)).toBe(
      'intent shopping; 1 facts, 4 orders from Aurora PostgreSQL; '
      + 'Remembered: AgentCore Memory record mem-theo-1 (user preference)',
    )
    const managed = { ...route, builder: { tool: null, remembered: { ...route.builder.remembered, records: ['mem-a', 'mem-b'] } } }
    expect(evidenceLine(managed)).toBe('Remembered: AgentCore Memory records mem-a, mem-b (user preference)')
    const none = { ...route, builder: { tool: null, intent: 'shopping', remembered: null } }
    expect(evidenceLine(none)).toBe('intent shopping')
    const failed = {
      ...route,
      builder: {
        tool: null, intent: 'shopping',
        remembered: { source: 'agentcore-memory', strategy: 'USER_PREFERENCE', records: [], error: 'managed_memory_unavailable' },
      },
    }
    expect(evidenceLine(failed)).toBe(
      'intent shopping; Remembered: AgentCore Memory read failed (managed_memory_unavailable); none given',
    )
  })

  it('names the tools the running Stock agent may call beside its prompt rule', () => {
    const route = (tools: string[]) => ({
      id: 'route', label: 'Understanding your request', status: 'done' as const, tags: ['Router'],
      builder: {
        tool: null, intent: 'stock', agent: 'Stock agent', model_id: 'global.anthropic.claude-sonnet-5',
        grant: { tools, rule: 'Every stock answer starts from check_stock' },
      },
    })
    expect(evidenceLine(route(['search_products', 'browse_department', 'compare_products', 'check_stock']))).toBe(
      'intent stock; model global.anthropic.claude-sonnet-5; '
      + 'Stock agent may call: search_products, browse_department, compare_products, check_stock; '
      + 'prompt rule: "Every stock answer starts from check_stock"',
    )
    expect(evidenceLine(route(['check_stock']))).toContain(
      'Stock agent may call: check_stock; prompt rule: "Every stock answer starts from check_stock"',
    )
    const shopping = { ...route([]), builder: { tool: null, agent: 'Shopping agent', grant: { tools: ['search_products'], rule: null } } }
    expect(evidenceLine(shopping)).toBe('Shopping agent may call: search_products')
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

  it('emphasizes product names and prices as ranges over the source, never by editing it', () => {
    const text = 'Start with the Wabi-Sabi Bowl at $24. The Ceramic Tumblers pair well.'
    const ranges = emphasisRanges(text, ['Wabi-Sabi Bowl', 'Ceramic Tumblers'])
    expect(ranges.map(range => text.slice(range.start, range.end))).toEqual(['Wabi-Sabi Bowl', '$24', 'Ceramic Tumblers'])
    const [first] = parseProse(text, ranges)
    expect(first.runs.map(run => [run.bold, run.text])).toEqual([
      [false, 'Start with the '], [true, 'Wabi-Sabi Bowl'], [false, ' at '], [true, '$24'],
      [false, '. The '], [true, 'Ceramic Tumblers'], [false, ' pair well.'],
    ])
    // A half-revealed name is bold from its first character, like an unclosed **.
    const partial = parseProse(text.slice(0, 'Start with the Wabi-Sa'.length), ranges)
    expect(partial[0].runs.at(-1)).toMatchObject({ bold: true, text: 'Wabi-Sa' })
    expect(emphasisRanges(text, [])).toEqual([])
  })
})

describe('upsertStep', () => {
  it('merges a running step into its done event by id', () => {
    const running = { id: 'step-1', label: 'Searching', status: 'running' as const, tags: ['Aurora'] }
    const done = { ...running, status: 'done' as const, finding: '3 found' }
    expect(upsertStep(upsertStep([], running), done)).toEqual([done])
  })

  it('keeps six tool uses of one tool as six steps, each with its own evidence', () => {
    const ids = [1, 2, 3, 4, 5, 6].map(index => `step-${index}`)
    const label = 'Searching the catalog in Aurora'
    const running = ids.map(id => ({ id, label, status: 'running' as const, tags: ['Aurora'] }))
    // The calls finish out of order, as parallel calls do.
    const done = [...running].reverse().map((step, index) => ({
      ...step,
      status: 'done' as const,
      finding: `${index + 1} found`,
      builder: { tool: 'search_products', receipt_id: 700 + Number(step.id.slice(5)) },
      results: { available: true, product_ids: [step.id] },
    }))
    const steps = [...running, ...done].reduce(upsertStep, [] as TurnStep[])
    expect(steps.map(step => step.id)).toEqual(ids)
    expect(steps.map(step => step.builder?.receipt_id)).toEqual([701, 702, 703, 704, 705, 706])
    expect(steps.map(step => step.results?.product_ids)).toEqual(ids.map(id => [id]))
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

  it('never shortens the revealed text when product names arrive mid-reveal', () => {
    const text = 'Start with the Stoneware Mugs, Set of 2 at $38. They are in stock.'
    const progress: number[] = []
    const onProgress = (length: number) => progress.push(length)
    const { container, rerender } = render(<RevealedProse text={text} done={false} onProgress={onProgress} />)
    act(() => { vi.advanceTimersByTime(24 * 30) })
    const revealedBefore = container.textContent ?? ''
    expect(revealedBefore.length).toBeGreaterThan('Start with the Stoneware'.length)
    expect(container.querySelector('strong')).toBeNull()

    // The product events land: the names are now emphasized.
    rerender(<RevealedProse text={text} done={false} emphasis={['Stoneware Mugs, Set of 2']} onProgress={onProgress} />)
    const revealedAfter = container.textContent ?? ''
    expect(revealedAfter.startsWith(revealedBefore)).toBe(true)
    expect(revealedAfter.length).toBeGreaterThanOrEqual(revealedBefore.length)
    expect(container.querySelector('strong')?.textContent).toBe('Stoneware Mugs, Set of 2'.slice(0, revealedAfter.length - 'Start with the '.length))
    expect(Math.min(...progress.slice(progress.indexOf(revealedBefore.length)))).toBe(revealedBefore.length)

    act(() => { vi.advanceTimersByTime(5000) })
    rerender(<RevealedProse text={text} done emphasis={['Stoneware Mugs, Set of 2']} onProgress={onProgress} />)
    act(() => { vi.advanceTimersByTime(1500) })
    expect(container.textContent).toBe(text)
    expect(Array.from(container.querySelectorAll('strong')).map(node => node.textContent)).toEqual(['Stoneware Mugs, Set of 2', '$38'])
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

  it('shows the full text at once when a revealing answer becomes history', () => {
    const progress: Array<[number, boolean]> = []
    const onProgress = (length: number, finished: boolean) => progress.push([length, finished])
    const { container, rerender } = render(<RevealedProse text="Start with the mugs." done onProgress={onProgress} />)
    act(() => { vi.advanceTimersByTime(24 * 3) })
    expect(container.textContent).toBe('Star')
    rerender(<RevealedProse text="Start with the mugs." done instant onProgress={onProgress} />)
    expect(container.textContent).toBe('Start with the mugs.')
    expect(container.querySelector('.tn-prose-live')).toBeNull()
    expect(progress.at(-1)).toEqual(['Start with the mugs.'.length, true])
  })
})
