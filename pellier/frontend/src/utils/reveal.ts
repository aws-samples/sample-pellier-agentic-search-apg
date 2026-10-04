/**
 * The reveal controller: Pellier's slow, even, character-by-character answer.
 *
 * It paces a text that arrives in bursts into a steady cadence, pauses at
 * sentence ends and commas, catches up gracefully when the backlog grows, and
 * never finishes more than about 1.5 s after the stream says it is complete.
 * It owns no DOM: a frame is the revealed prefix of the target text plus
 * whether the reveal is finished, and the component decides how to draw it.
 *
 * The pacing is by wall clock, not by tick count. Every character has a due
 * time; a tick commits every character whose due time has passed. A browser
 * allows a hidden tab about one timer a second, so a tick that fires late
 * catches up in one step instead of advancing one character per tick, the
 * finish bound holds by the clock, and the tab becoming visible again catches
 * up at once.
 *
 * Owner-confirmed values (2026-10-04): 24 ms per character, a 9x pause after a
 * sentence end, 4x after a comma, catch-up past 60 and 120 queued characters,
 * and a 1.5 s finish bound. `prefers-reduced-motion` shows text instantly.
 */

export interface RevealTiming {
  /** Milliseconds per character at the steady cadence. */
  cadenceMs: number
  /** Multiplier applied after `.`, `!` or `?`. */
  sentencePause: number
  /** Multiplier applied after `,`, `;` or `:`. */
  commaPause: number
  /** Backlog sizes past which the cadence speeds up. */
  catchUpAt: readonly [number, number]
  /** Cadence multipliers at each catch-up level. */
  catchUpFactors: readonly [number, number]
  /** The reveal finishes within this many ms of `done()`. */
  finishWithinMs: number
}

export const REVEAL_TIMING: RevealTiming = {
  cadenceMs: 24,
  sentencePause: 9,
  commaPause: 4,
  catchUpAt: [60, 120],
  catchUpFactors: [0.6, 0.35],
  finishWithinMs: 1500,
}

export interface RevealOptions extends Partial<RevealTiming> {
  /** Called with the revealed prefix after every change. */
  onFrame: (revealed: string, finished: boolean) => void
  /** Show text instantly instead of pacing it. */
  reducedMotion?: boolean
  /** The wall clock, in ms. Tests pass their own. */
  now?: () => number
}

export interface RevealController {
  /** The full text received so far. The reveal continues from its committed prefix. */
  setTarget: (text: string) => void
  /** The stream is complete: finish within the bound. */
  done: () => void
  /** Show everything now. */
  flush: () => void
  /** Stop and never call back again. */
  cancel: () => void
  revealed: () => string
  finished: () => boolean
}

const SENTENCE_END = /[.!?]/
const CLAUSE_END = /[,;:]/

function commonPrefixLength(a: string, b: string): number {
  const limit = Math.min(a.length, b.length)
  let index = 0
  while (index < limit && a[index] === b[index]) index += 1
  return index
}

export function createRevealController(options: RevealOptions): RevealController {
  const timing: RevealTiming = { ...REVEAL_TIMING, ...options }
  const { onFrame, reducedMotion = false, now = Date.now } = options
  const hasDocument = typeof document !== 'undefined'

  let target = ''
  let committed = ''
  let timer: ReturnType<typeof setTimeout> | null = null
  /** Wall-clock times: when the next character is due, and when the last one was. */
  let dueAt = 0
  let lastDueAt = 0
  let isDone = false
  let deadline: number | null = null
  let cancelled = false
  let finishedReported = false

  const clearTimer = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  const isFinished = () => isDone && committed.length >= target.length

  const emit = () => {
    const finished = isFinished()
    if (finished) {
      if (finishedReported) return
      finishedReported = true
    }
    onFrame(committed, finished)
  }

  const delayAfter = (char: string, at: number): number => {
    let delay = timing.cadenceMs
    if (SENTENCE_END.test(char)) delay *= timing.sentencePause
    else if (CLAUSE_END.test(char)) delay *= timing.commaPause
    const backlog = target.length - committed.length
    if (backlog > timing.catchUpAt[1]) delay *= timing.catchUpFactors[1]
    else if (backlog > timing.catchUpAt[0]) delay *= timing.catchUpFactors[0]
    // After `done()`, the rest is spread over the time left before the bound,
    // by the clock: once the bound has passed every delay is 0, and the next
    // tick commits everything that is left.
    if (deadline !== null && backlog > 0) {
      const remaining = Math.max(0, deadline - at)
      delay = Math.min(delay, remaining / backlog)
    }
    return delay
  }

  /** Commit every character due by now. */
  const advance = (): boolean => {
    const time = now()
    const before = committed.length
    while (committed.length < target.length && dueAt <= time) {
      const char = target[committed.length]
      committed += char
      lastDueAt = dueAt
      dueAt += delayAfter(char, time)
    }
    return committed.length !== before
  }

  const schedule = () => {
    if (cancelled || timer !== null) return
    if (committed.length >= target.length) {
      if (isFinished()) emit()
      return
    }
    timer = setTimeout(tick, Math.max(0, dueAt - now()))
  }

  const tick = () => {
    timer = null
    if (cancelled) return
    if (advance() || isFinished()) emit()
    schedule()
  }

  const onVisibilityChange = () => {
    if (cancelled || document.visibilityState !== 'visible') return
    clearTimer()
    tick()
  }
  if (hasDocument && !reducedMotion) document.addEventListener('visibilitychange', onVisibilityChange)

  return {
    setTarget(text: string) {
      if (cancelled) return
      const keep = commonPrefixLength(committed, text)
      const corrected = keep < committed.length
      target = text
      if (corrected) committed = committed.slice(0, keep)
      // A correction or a longer text reopens the reveal, so its end is
      // reported again when it comes.
      if (committed.length < target.length) finishedReported = false
      if (reducedMotion) {
        committed = target
        clearTimer()
        emit()
        return
      }
      if (corrected || committed.length >= target.length) emit()
      // The first character is due at once. Text arriving after an idle
      // spell is due from now, not from the old schedule: idleness banks
      // no characters.
      if (committed.length === 0) dueAt = now()
      else if (timer === null) dueAt = Math.max(dueAt, now())
      schedule()
    },
    done() {
      if (cancelled) return
      isDone = true
      const time = now()
      deadline = time + timing.finishWithinMs
      if (committed.length >= target.length) {
        emit()
        return
      }
      // Re-plan the pending wait under the new bound.
      clearTimer()
      const last = committed[committed.length - 1]
      dueAt = last ? Math.min(dueAt, lastDueAt + delayAfter(last, time)) : time
      schedule()
    },
    flush() {
      if (cancelled) return
      clearTimer()
      committed = target
      emit()
    },
    cancel() {
      cancelled = true
      clearTimer()
      if (hasDocument) document.removeEventListener('visibilitychange', onVisibilityChange)
    },
    revealed: () => committed,
    finished: () => isFinished(),
  }
}
