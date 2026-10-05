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
 *     result holding the most of the answer's picks, the later one on a tie;
 *   - at the end the grid leads with the answer's picks, the cards Ask
 *     Pellier shows under the answer, in its order, from whichever of the
 *     turn's results holds each one; the chosen result's own order follows,
 *     without repeats. A pick no result of the turn holds is not shown, and
 *     the page never reads anything but the turn's ids;
 *   - the turn ends without a search: the page is as it was before the turn;
 *   - the turn fails: the page is as it was, with a calm notice.
 *
 * "Show the whole store" and the pellier. wordmark return to the store grid
 * and leave the conversation alone. A new shopper starts clean.
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

/**
 * At most this many ids in one grid: the bound `GET /api/products?ids=`
 * accepts (`RESULT_IDS_MAX` in `services/store_tools.py`).
 */
const GRID_IDS_MAX = 30

/** One catalog call's result, as its done step carried it. */
interface CallResult {
  stepId: string
  finding: string | null
  results: StepResults
  ranking: RankingPayload | null
}

/** A call of the turn that carried a ranking, for "How it ranked". */
export interface RankedCall {
  stepId: string
  finding: string | null
  ranking: RankingPayload
}

export interface ShownResult {
  /** The result whose order the grid follows: its count, limits and filters. */
  results: StepResults
  /** That result's own ranking, when it carried one. */
  ranking: RankingPayload | null
  /** The answer's picks, in its order, from any of the turn's results. */
  picks: string[]
  /** The grid, in order: the picks, then the result's own order without them. */
  ids: string[]
  /** Every call of the turn with a ranking, in the order the calls started. */
  rankings: RankedCall[]
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
  candidates: CallResult[]
  /** The catalog calls' step ids, in the order they started. */
  started: string[]
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
  /** How many times the shopper went back to the whole store. */
  storeVisits: number
}

type Action =
  | { type: 'event'; event: TurnEvent }
  | { type: 'clear' }
  | { type: 'reset' }

const INITIAL: State = { view: { kind: 'store' }, turn: null, status: null, failed: false, storeVisits: 0 }

function isCatalogStep(step: TurnStep): boolean {
  return CATALOG_TOOLS.has(step.builder?.tool ?? '')
}

function hasPieces(candidate: CallResult): boolean {
  return (candidate.results.product_ids ?? []).length > 0
}

/**
 * Which of a turn's results the page shows while it runs: the latest one with
 * pieces, so a later empty search never hides the pieces an answer can name;
 * a skeleton while a catalog call runs and nothing with pieces has landed;
 * an empty result only when every result was empty.
 */
function streamingChoice(turn: RunningTurn): CallResult | null | undefined {
  const withPieces = turn.candidates.filter(hasPieces)
  if (withPieces.length > 0) return withPieces[withPieces.length - 1]
  if (turn.running > 0) return null
  if (turn.candidates.length > 0) return turn.candidates[turn.candidates.length - 1]
  return undefined
}

/**
 * At the end, the result that holds the most of the answer's picks, so the
 * page and the answer agree; a tie goes to the later result. With no pick in
 * any result, the streaming choice stands.
 */
function finalChoice(turn: RunningTurn, picks: readonly string[]): CallResult | null | undefined {
  const fallback = streamingChoice({ ...turn, running: 0 })
  if (picks.length === 0) return fallback
  let best: CallResult | undefined
  let bestOverlap = 0
  for (const candidate of turn.candidates) {
    const ids = new Set(candidate.results.product_ids ?? [])
    const overlap = picks.filter(id => ids.has(id)).length
    if (overlap > 0 && overlap >= bestOverlap) {
      best = candidate
      bestOverlap = overlap
    }
  }
  return best ?? fallback
}

/** The answer's picks that one of the turn's results holds, in the answer's order, once each. */
function heldPicks(turn: RunningTurn, picks: readonly string[]): string[] {
  const held = new Set(turn.candidates.flatMap(candidate => candidate.results.product_ids ?? []))
  return [...new Set(picks)].filter(id => held.has(id))
}

function rankedCalls(turn: RunningTurn): RankedCall[] {
  const calls: RankedCall[] = []
  for (const candidate of turn.candidates) {
    if (candidate.ranking) calls.push({ stepId: candidate.stepId, finding: candidate.finding, ranking: candidate.ranking })
  }
  const position = (stepId: string) => turn.started.indexOf(stepId)
  return calls.sort((a, b) => position(a.stepId) - position(b.stepId))
}

function shownFor(turn: RunningTurn, choice: CallResult, picks: readonly string[] = []): ShownResult {
  const own = (choice.results.product_ids ?? []).filter(id => !picks.includes(id))
  return {
    results: choice.results,
    ranking: choice.ranking,
    picks: [...picks],
    ids: [...picks, ...own].slice(0, GRID_IDS_MAX),
    rankings: rankedCalls(turn),
  }
}

function withTurn(state: State, turn: RunningTurn, choice: CallResult | null | undefined): State {
  if (turn.dismissed || choice === undefined) return { ...state, turn }
  const shown = choice ? shownFor(turn, choice) : null
  return { ...state, turn, view: { kind: 'results', query: turn.query, shown } }
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
    const started = turn.started.includes(step.id) ? turn.started : [...turn.started, step.id]
    const next = { ...turn, started, running: turn.running + 1 }
    return withTurn(state, next, streamingChoice(next))
  }
  const results = step.results
  const finished = { ...turn, running: Math.max(0, turn.running - 1) }
  if (step.status !== 'done' || !results?.available || !Array.isArray(results.product_ids)) {
    return withTurn(state, finished, streamingChoice(finished))
  }
  const call: CallResult = {
    stepId: step.id,
    finding: step.finding ?? null,
    results,
    ranking: step.builder?.ranking ?? null,
  }
  const next = { ...finished, candidates: [...finished.candidates, call] }
  return withTurn(state, next, streamingChoice(next))
}

function onEnd(state: State, outcome: 'complete' | 'failed' | 'stopped', answerPicks: readonly string[]): State {
  const turn = state.turn
  if (!turn) return state
  const ended = { ...state, turn: null, status: null }
  if (turn.dismissed) return ended
  if (outcome === 'failed') return { ...ended, view: turn.previous, failed: true }
  const picks = outcome === 'complete' ? heldPicks(turn, answerPicks) : []
  const choice = finalChoice(turn, picks)
  if (!choice) return { ...ended, view: turn.previous }
  return { ...ended, view: { kind: 'results', query: turn.query, shown: shownFor(turn, choice, picks) } }
}

function reducer(state: State, action: Action): State {
  if (action.type === 'reset') return INITIAL
  if (action.type === 'clear') {
    const turn = state.turn ? { ...state.turn, dismissed: true } : null
    return { ...state, view: { kind: 'store' }, turn, failed: false, storeVisits: state.storeVisits + 1 }
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
          started: [],
          running: 0,
          dismissed: false,
        },
        status: RESULTS.STARTING,
        failed: false,
        storeVisits: state.storeVisits,
      }
    }
    case 'status':
      return state.turn ? { ...state, status: event.label } : state
    case 'step':
      return onStep(state, event.step)
    case 'end':
      return onEnd(state, event.outcome, event.picks ?? [])
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
  /** Back to the whole store: the results view closes and the home bar empties. */
  clear: () => void
  /** Counts each `clear`, so the home bar can empty even with no results showing. */
  storeVisits: number
  retryCards: () => void
  /** The ranking the page's panel shows, while the page shows it. */
  pageRanking: RankingPayload | null
  setPageRanking: (ranking: RankingPayload | null) => void
}

const StoreResultsContext = createContext<StoreResultsValue | null>(null)

/** The results view, or null outside its provider (a surface with no store page). */
export function useStoreResults(): StoreResultsValue | null {
  return useContext(StoreResultsContext)
}

function idsKey(view: ResultsView): string | null {
  if (view.kind !== 'results' || !view.shown) return null
  return view.shown.ids.join(',')
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
  const [pageRanking, setPageRanking] = useState<RankingPayload | null>(null)
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

  const value = useMemo<StoreResultsValue>(
    () => ({
      view: state.view,
      status: state.status,
      failed: state.failed,
      cards: cards && cards.key === key ? cards : null,
      onTurn,
      clear,
      storeVisits: state.storeVisits,
      retryCards,
      pageRanking: state.view.kind === 'results' ? pageRanking : null,
      setPageRanking,
    }),
    [state, cards, key, onTurn, clear, retryCards, pageRanking],
  )
  return <StoreResultsContext.Provider value={value}>{children}</StoreResultsContext.Provider>
}
