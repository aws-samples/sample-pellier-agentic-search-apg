/**
 * Which result the page shows when an agent runs more than one catalog call.
 *
 * A live turn on 2026-10-04 ran two searches at once, then a search and a
 * browse at once: the browse had the pieces the answer named and the later
 * search came back empty. The page must show the pieces the answer came
 * from, never the later empty result.
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

function step(tool: string, status: 'running' | 'done', ids?: string[]): TurnEvent {
  const event: TurnStep = {
    id: tool === 'browse_department' ? 'step-2' : 'step-1',
    label: tool,
    status,
    tags: [],
    builder: { tool },
  }
  if (ids) event.results = { available: true, product_ids: ids, limits: [], filters: null }
  return { type: 'step', step: event }
}

function shownIds(): string[] | null {
  const view = current!.view
  if (view.kind !== 'results') return null
  return view.shown ? view.shown.results.product_ids ?? [] : null
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
    send({ type: 'end', outcome: 'complete', productIds: ['31', '65', '37'] })
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
    send({ type: 'end', outcome: 'complete', productIds: ['9'] })
    expect(shownIds()).toEqual(['2', '9'])
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
    send(step('search_products', 'done', ['65']), { type: 'end', outcome: 'complete', productIds: ['65'] })
    expect(current!.view).toEqual({ kind: 'store' })
  })
})
