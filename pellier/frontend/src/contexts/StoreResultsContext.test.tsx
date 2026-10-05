/**
 * Which result the page shows when an agent runs more than one catalog call,
 * and how the answer's picks lead its grid.
 *
 * A live turn on 2026-10-04 ran two searches at once, then a search and a
 * browse at once: the browse had the pieces the answer named and the later
 * search came back empty. The page must show the pieces the answer came
 * from, never the later empty result. On 2026-10-05 the "For the trip"
 * answer named pieces in its own order, one of them from a second search:
 * the grid leads with exactly those picks, then the rest of the result.
 */
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TurnEvent } from '../hooks/useAgentChat'
import type { TurnStep } from '../components/turn/turnTypes'
import { StoreResultsProvider, useStoreResults, type StoreResultsValue } from './StoreResultsContext'

vi.mock('./PersonaContext', () => ({ usePersona: () => ({ persona: null }) }))

let current: StoreResultsValue | null = null
function Probe() {
  current = useStoreResults()
  return null
}

function send(...events: TurnEvent[]) {
  act(() => {
    for (const event of events) current!.onTurn(event)
  })
}

function step(tool: string, status: 'running' | 'done', ids?: string[], id?: string): TurnEvent {
  const event: TurnStep = {
    id: id ?? (tool === 'browse_department' ? 'step-2' : 'step-1'),
    label: tool,
    status,
    tags: [],
    builder: { tool },
  }
  if (ids) event.results = { available: true, product_ids: ids, count: ids.length, limits: [], filters: null }
  return { type: 'step', step: event }
}

/** A search's done step with its own ranking, as the backend streams it. */
function rankedSearch(id: string, ids: string[]): TurnEvent {
  const event = step('search_products', 'done', ids, id) as Extract<TurnEvent, { type: 'step' }>
  event.step.finding = `${ids.length} found`
  event.step.builder = { tool: 'search_products', ranking: { available: true, rows: [] } }
  return event
}

/** The result whose order the grid follows. */
function shownIds(): string[] | null {
  const view = current!.view
  if (view.kind !== 'results') return null
  return view.shown ? view.shown.results.product_ids ?? [] : null
}

/** The grid itself: the picks, then the result's own order. */
function gridIds(): string[] | null {
  const view = current!.view
  return view.kind === 'results' && view.shown ? view.shown.ids : null
}

describe('the result a turn shows', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200 })))
    render(<StoreResultsProvider><Probe /></StoreResultsProvider>)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the pieces from a browse when a parallel search comes back empty', () => {
    send(
      { type: 'start', query: 'a housewarming gift' },
      step('search_products', 'running'),
      step('search_products', 'running'),
      step('search_products', 'done', []),
      step('search_products', 'done'),
    )
    // Every search so far was empty: the empty result shows.
    expect(shownIds()).toEqual([])
    // A new call runs and nothing with pieces has landed: the skeleton again.
    send(step('search_products', 'running'), step('browse_department', 'running'))
    expect(shownIds()).toBeNull()
    send(step('browse_department', 'done', ['37', '31', '65']))
    expect(shownIds()).toEqual(['37', '31', '65'])
    send(step('search_products', 'done', []))
    expect(shownIds()).toEqual(['37', '31', '65'])
    send({ type: 'end', outcome: 'complete', picks: ['31', '65', '37'] })
    expect(shownIds()).toEqual(['37', '31', '65'])
  })

  it('ends on the result that holds the pieces the answer named', () => {
    send(
      { type: 'start', query: 'linen' },
      step('search_products', 'running'),
      step('search_products', 'done', ['2', '9']),
      step('search_products', 'running'),
      step('search_products', 'done', ['44', '45']),
    )
    expect(shownIds()).toEqual(['44', '45'])
    send({ type: 'end', outcome: 'complete', picks: ['9'] })
    expect(shownIds()).toEqual(['2', '9'])
  })

  it('ends on the later search when two hold the named pieces equally', () => {
    send(
      { type: 'start', query: 'linen' },
      step('search_products', 'running'),
      step('search_products', 'running'),
      step('search_products', 'done', ['2', '9']),
      step('search_products', 'done', ['9', '45']),
    )
    send({ type: 'end', outcome: 'complete', picks: ['9'] })
    expect(shownIds()).toEqual(['9', '45'])
  })

  it('shows a skeleton while the first catalog call runs, and the store again if none lands', () => {
    send({ type: 'start', query: 'anything' })
    expect(current!.view).toEqual({ kind: 'results', query: 'anything', shown: null })
    send(step('search_products', 'running'))
    expect(shownIds()).toBeNull()
    send({ type: 'end', outcome: 'stopped' })
    expect(current!.view).toEqual({ kind: 'store' })
    expect(current!.failed).toBe(false)
  })

  it('lets "Show the whole store" win over a search that lands after it', () => {
    send({ type: 'start', query: 'mugs' }, step('search_products', 'running'))
    act(() => current!.clear())
    send(step('search_products', 'done', ['65']), { type: 'end', outcome: 'complete', picks: ['65'] })
    expect(current!.view).toEqual({ kind: 'store' })
  })
})

describe("the answer's picks lead the grid", () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200 })))
    render(<StoreResultsProvider><Probe /></StoreResultsProvider>)
  })
  afterEach(() => vi.unstubAllGlobals())

  function shown() {
    const view = current!.view
    if (view.kind !== 'results' || !view.shown) throw new Error('no result shown')
    return view.shown
  }

  it('puts the picks first, in the answer order, then the rest of the result', () => {
    send(
      { type: 'start', query: 'for the trip' },
      step('search_products', 'running'),
      step('search_products', 'done', ['96', '95', '3', '14', '57', '11']),
    )
    // While the turn runs, the result's own order.
    expect(gridIds()).toEqual(['96', '95', '3', '14', '57', '11'])
    send({ type: 'end', outcome: 'complete', picks: ['11', '14', '3'] })
    expect(gridIds()).toEqual(['11', '14', '3', '96', '95', '57'])
    expect(shown().picks).toEqual(['11', '14', '3'])
  })

  it('includes a pick from a second search, and leads with it where the answer did', () => {
    send(
      { type: 'start', query: 'for the trip' },
      step('search_products', 'running', undefined, 'step-1'),
      step('search_products', 'running', undefined, 'step-2'),
      rankedSearch('step-1', ['96', '95', '3', '14', '11']),
      rankedSearch('step-2', ['97', '94']),
      { type: 'end', outcome: 'complete', picks: ['14', '97', '11'] },
    )
    // The first search holds two picks: its order follows the three picks.
    expect(shownIds()).toEqual(['96', '95', '3', '14', '11'])
    expect(gridIds()).toEqual(['14', '97', '11', '96', '95', '3'])
    expect(shown().results.count).toBe(5)
  })

  it('shows each piece once', () => {
    send(
      { type: 'start', query: 'linen' },
      step('search_products', 'running', undefined, 'step-1'),
      step('search_products', 'running', undefined, 'step-2'),
      rankedSearch('step-1', ['2', '11', '16']),
      rankedSearch('step-2', ['11', '2', '18']),
      { type: 'end', outcome: 'complete', picks: ['2', '11', '2'] },
    )
    const ids = gridIds()!
    expect(ids).toEqual(['2', '11', '18'])
    expect(new Set(ids).size).toBe(ids.length)
  })

  it("shows the result's ranked order when the answer has no picks", () => {
    send(
      { type: 'start', query: 'linen' },
      step('search_products', 'running'),
      step('search_products', 'done', ['2', '11', '16']),
      { type: 'end', outcome: 'complete', picks: [] },
    )
    expect(gridIds()).toEqual(['2', '11', '16'])
    expect(shown().picks).toEqual([])
  })

  it('leaves out a pick no result of the turn holds, so the page reads only the turn', () => {
    send(
      { type: 'start', query: 'linen' },
      step('search_products', 'running'),
      step('search_products', 'done', ['2', '11']),
      { type: 'end', outcome: 'complete', picks: ['50', '11'] },
    )
    expect(gridIds()).toEqual(['11', '2'])
    expect(shown().picks).toEqual(['11'])
  })

  it('keeps at most thirty ids, the bound the cards read accepts', () => {
    const first = Array.from({ length: 30 }, (_, index) => String(index + 1))
    send(
      { type: 'start', query: 'everything' },
      step('search_products', 'running', undefined, 'step-1'),
      step('search_products', 'running', undefined, 'step-2'),
      rankedSearch('step-1', first),
      rankedSearch('step-2', ['97']),
      { type: 'end', outcome: 'complete', picks: ['5', '6', '97'] },
    )
    // Three picks and the first search's 28 others: the last one waits out.
    const ids = gridIds()!
    expect(ids).toHaveLength(30)
    expect(ids.slice(0, 4)).toEqual(['5', '6', '97', '1'])
    expect(ids).not.toContain('30')
  })

  it('keeps every ranked call of the turn, in the order the calls started', () => {
    send(
      { type: 'start', query: 'two things' },
      step('search_products', 'running', undefined, 'step-1'),
      step('search_products', 'running', undefined, 'step-2'),
      // The second call finishes first.
      rankedSearch('step-2', ['31']),
      rankedSearch('step-1', ['2']),
      { type: 'end', outcome: 'complete', picks: ['2', '31'] },
    )
    expect(shown().rankings.map(call => call.stepId)).toEqual(['step-1', 'step-2'])
    expect(shown().rankings.map(call => call.finding)).toEqual(['1 found', '1 found'])
  })
})
