/**
 * The storefront's results view: the page grid follows the Ask Pellier turn.
 *
 * One source of truth. The page shows the agent's own search result for the
 * turn, from the `results` its search or browse step carried on the stream;
 * the browser never runs a search of its own, so the page and the answer
 * cannot disagree. The dock's chat hook reports each turn here (`onTurn`):
 *
 *   - a turn starts: the page shows "Results for <query>" with a skeleton
 *     grid when it was showing the store, and keeps a result already on
 *     screen until a new search starts;
 *   - a search or browse starts: the grid becomes a skeleton;
 *   - its step finishes with `results`: the grid shows exactly those ids, in
 *     that order, read in one bounded request (`/api/products?ids=`);
 *   - an agent may search more than once in a turn, two calls at a time:
 *     each call is its own step with its own result (the backend keys the
 *     evidence by tool use, so no call carries another's); the page shows
 *     the latest result with pieces while the turn runs, and at the end the
 *     result holding the most of the pieces the answer named, the later one
 *     on a tie;
 *   - the turn ends without a search: the page is as it was before the turn;
 *   - the turn fails: the page is as it was, with a calm notice.
 *
 * "Show the whole store" returns to the store grid and leaves the
 * conversation alone. A new shopper starts clean.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useState,
  type ReactNode,
} from 'react'
import { RESULTS } from '../copy'
import { apiFetch } from '../services/apiBase'
import type { PellierProduct } from '../services/types'
import type { TurnEvent } from '../hooks/useAgentChat'
import type { RankingPayload, StepResults, TurnStep } from '../components/turn/turnTypes'
import { usePersona } from './PersonaContext'

const CATALOG_TOOLS = new Set(['search_products', 'browse_department'])
// Only the Shopping agent holds the catalog tools.
const SHOPPING_INTENT = 'shopping'

/** The page's panel id; the dock's summary scrolls to it. */
export const PAGE_RANKING_ID = 'how-it-ranked'

export interface ShownResult {
  results: StepResults
  ranking: RankingPayload | null
}

export type ResultsView =
  | { kind: 'store' }
  /** `shown` is null while the turn's search runs: the grid is a skeleton. */
  | { kind: 'results'; query: string; shown: ShownResult | null }

interface RunningTurn {
  query: string
  /** What the page showed before the turn, restored when it shows no result. */
  previous: ResultsView
  /** Every search or browse result the turn produced, in arrival order. */
  candidates: ShownResult[]
  /** Catalog calls still running; an agent may run two at once. */
  running: number
  /** "Show the whole store" was pressed: the turn no longer drives the page. */
  dismissed: boolean
}

interface State {
  view: ResultsView
  turn: RunningTurn | null
  /** The turn's status line, from the stream, while it runs. */
  status: string | null
  /** The last turn failed: the page is as it was, with a calm notice. */
  failed: boolean
}

type Action =
  | { type: 'event'; event: TurnEvent }
  | { type: 'clear' }
  | { type: 'reset' }

const INITIAL: State = { view: { kind: 'store' }, turn: null, status: null, failed: false }

function isCatalogStep(step: TurnStep): boolean {
  return CATALOG_TOOLS.has(step.builder?.tool ?? '')
}

function hasPieces(candidate: ShownResult): boolean {
  return (candidate.results.product_ids ?? []).length > 0
}

/**
 * Which of a turn's results the page shows while it runs: the latest one with
 * pieces, so a later empty search never hides the pieces an answer can name;
 * a skeleton while a catalog call runs and nothing with pieces has landed;
 * an empty result only when every result was empty.
 */
function streamingChoice(turn: RunningTurn): ShownResult | null | undefined {
  const withPieces = turn.candidates.filter(hasPieces)
  if (withPieces.length > 0) return withPieces[withPieces.length - 1]
  if (turn.running > 0) return null
  if (turn.candidates.length > 0) return turn.candidates[turn.candidates.length - 1]
  return undefined
}

/**
 * At the end, the result that holds the most of the pieces the answer named,
 * so the page and the answer agree; a tie goes to the later result. With no
 * named piece in any result, the streaming choice stands.
 */
function finalChoice(turn: RunningTurn, named: readonly string[]): ShownResult | null | undefined {
  const fallback = streamingChoice({ ...turn, running: 0 })
  if (named.length === 0) return fallback
  let best: ShownResult | undefined
  let bestOverlap = 0
  for (const candidate of turn.candidates) {
    const ids = new Set(candidate.results.product_ids ?? [])
    const overlap = named.filter(id => ids.has(id)).length
    if (overlap > 0 && overlap >= bestOverlap) {
      best = candidate
      bestOverlap = overlap
    }
  }
  return best ?? fallback
}

function withTurn(state: State, turn: RunningTurn, choice: ShownResult | null | undefined): State {
  if (turn.dismissed || choice === undefined) return { ...state, turn }
  return { ...state, turn, view: { kind: 'results', query: turn.query, shown: choice } }
}

/** The Router sent the turn to an agent with no catalog tool: it cannot search. */
function routedAwayFromTheCatalog(step: TurnStep): boolean {
  const builder = step.builder
  return Boolean(builder && builder.tool === null && builder.intent && builder.intent !== SHOPPING_INTENT)
}

function onStep(state: State, step: TurnStep): State {
  const turn = state.turn
  if (!turn) return state
  // The page's status line names what runs now, as the dock's steps do.
  const status = step.status === 'running' && step.label ? step.label : state.status
  if (routedAwayFromTheCatalog(step) && turn.candidates.length === 0 && turn.running === 0) {
    return turn.dismissed ? state : { ...state, view: turn.previous }
  }
  if (!isCatalogStep(step)) return { ...state, status }
  return onCatalogStep({ ...state, status }, turn, step)
}

function onCatalogStep(state: State, turn: RunningTurn, step: TurnStep): State {
  if (step.status === 'running') {
    const next = { ...turn, running: turn.running + 1 }
    return withTurn(state, next, streamingChoice(next))
  }
  const results = step.results
  const finished = { ...turn, running: Math.max(0, turn.running - 1) }
  if (step.status !== 'done' || !results?.available || !Array.isArray(results.product_ids)) {
    return withTurn(state, finished, streamingChoice(finished))
  }
  const next = {
    ...finished,
    candidates: [...finished.candidates, { results, ranking: step.builder?.ranking ?? null }],
  }
  return withTurn(state, next, streamingChoice(next))
}

function onEnd(state: State, outcome: 'complete' | 'failed' | 'stopped', named: readonly string[]): State {
  const turn = state.turn
  if (!turn) return state
  const ended = { ...state, turn: null, status: null }
  if (turn.dismissed) return ended
  if (outcome === 'failed') return { ...ended, view: turn.previous, failed: true }
  const choice = finalChoice(turn, outcome === 'complete' ? named : [])
  if (!choice) return { ...ended, view: turn.previous }
  return { ...ended, view: { kind: 'results', query: turn.query, shown: choice } }
}

function reducer(state: State, action: Action): State {
  if (action.type === 'reset') return INITIAL
  if (action.type === 'clear') {
    const turn = state.turn ? { ...state.turn, dismissed: true } : null
    return { ...state, view: { kind: 'store' }, turn, failed: false }
  }
  const { event } = action
  switch (event.type) {
    case 'start': {
      const view: ResultsView = state.view.kind === 'store'
        ? { kind: 'results', query: event.query, shown: null }
        : state.view
      return {
        view,
        turn: {
          query: event.query,
          previous: state.view,
          candidates: [],
          running: 0,
          dismissed: false,
        },
        status: RESULTS.STARTING,
        failed: false,
      }
    }
    case 'status':
      return state.turn ? { ...state, status: event.label } : state
    case 'step':
      return onStep(state, event.step)
    case 'end':
      return onEnd(state, event.outcome, event.productIds ?? [])
    default:
      return state
  }
}

export interface ResultCards {
  /** The ids these cards were read for, joined; matches the view's result. */
  key: string
  status: 'loading' | 'ready' | 'failed'
  products: PellierProduct[]
}

export interface StoreResultsValue {
  view: ResultsView
  /** The running turn's status line, or null between turns. */
  status: string | null
  failed: boolean
  cards: ResultCards | null
  onTurn: (event: TurnEvent) => void
  clear: () => void
  retryCards: () => void
  /** The ranking the page's panel shows, while the page shows it. */
  pageRanking: RankingPayload | null
  setPagePanelShown: (shown: boolean) => void
}

const StoreResultsContext = createContext<StoreResultsValue | null>(null)

/** The results view, or null outside its provider (a surface with no store page). */
export function useStoreResults(): StoreResultsValue | null {
  return useContext(StoreResultsContext)
}

function idsKey(view: ResultsView): string | null {
  if (view.kind !== 'results' || !view.shown) return null
  return (view.shown.results.product_ids ?? []).join(',')
}

async function readCards(key: string, signal: AbortSignal): Promise<PellierProduct[]> {
  if (!key) return []
  const response = await apiFetch(`/api/products?ids=${encodeURIComponent(key)}`, {
    credentials: 'include',
    signal,
  })
  if (!response.ok) throw new Error(`Result cards request failed: ${response.status}`)
  const cards = await response.json()
  if (!Array.isArray(cards)) throw new Error('Result cards returned an invalid payload.')
  return cards as PellierProduct[]
}

export function StoreResultsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const [cards, setCards] = useState<ResultCards | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pagePanelShown, setPagePanelShown] = useState(false)
  const { persona } = usePersona()
  const personaId = persona?.id ?? null

  useEffect(() => {
    dispatch({ type: 'reset' })
  }, [personaId])

  const key = idsKey(state.view)
  useEffect(() => {
    if (key === null) {
      setCards(null)
      return
    }
    if (key === '') {
      setCards({ key, status: 'ready', products: [] })
      return
    }
    const controller = new AbortController()
    setCards({ key, status: 'loading', products: [] })
    readCards(key, controller.signal)
      .then(products => setCards({ key, status: 'ready', products }))
      .catch((error: unknown) => {
        if ((error as { name?: string })?.name === 'AbortError') return
        setCards({ key, status: 'failed', products: [] })
      })
    return () => controller.abort()
  }, [key, attempt])

  const onTurn = useCallback((event: TurnEvent) => dispatch({ type: 'event', event }), [])
  const clear = useCallback(() => dispatch({ type: 'clear' }), [])
  const retryCards = useCallback(() => setAttempt(value => value + 1), [])

  const shownRanking = state.view.kind === 'results' ? state.view.shown?.ranking ?? null : null
  const value = useMemo<StoreResultsValue>(
    () => ({
      view: state.view,
      status: state.status,
      failed: state.failed,
      cards: cards && cards.key === key ? cards : null,
      onTurn,
      clear,
      retryCards,
      pageRanking: pagePanelShown ? shownRanking : null,
      setPagePanelShown,
    }),
    [state, cards, key, onTurn, clear, retryCards, pagePanelShown, shownRanking],
  )
  return <StoreResultsContext.Provider value={value}>{children}</StoreResultsContext.Provider>
}
