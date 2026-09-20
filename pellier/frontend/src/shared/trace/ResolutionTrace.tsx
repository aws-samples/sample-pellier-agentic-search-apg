import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, MotionConfig, useReducedMotion } from 'motion/react'
import { Check, ChevronDown, Pause, Play, RotateCcw } from 'lucide-react'
import './resolution-trace.css'

export type TraceStatus = 'running' | 'completed' | 'recorded' | 'pending' | 'failed' | 'unavailable' | 'denied' | 'blocked' | 'skipped' | 'unknown'

export interface ResolutionStep {
  id: string
  title: string
  status: TraceStatus
  summary?: string
  source?: string
  durationMs?: number | null
  detail?: ReactNode
}

export interface TraceOutcome {
  label: string
  body?: ReactNode
  status?: 'complete' | 'waiting' | 'failed' | 'blocked' | 'unknown'
}

interface Props {
  title?: string
  request?: string
  steps: ResolutionStep[]
  mode: 'live' | 'recorded'
  busy?: boolean
  outcome?: TraceOutcome | null
  recordingKey?: string
  recordingLabel?: string
  autoPlay?: boolean
  compact?: boolean
  showPlaybackControls?: boolean
  playbackIntervalMs?: number
  announce?: boolean
  onReplayComplete?: () => void
  /**
   * `showcase` renders every step from the first frame, dimmed until it is
   * reached, and types the request in. The empty panel it replaces reserved
   * its full height and said nothing for the first second and a half. Live
   * and compact traces keep the plain reveal: an Operator watching real work
   * must not see a row for a step that has not been reported yet.
   */
  variant?: 'default' | 'showcase'
}

/** Preserve unknown and non-enforced observations. Never promote them to success. */
export function traceStatus(status?: string | null): TraceStatus {
  if (['complete', 'completed', 'succeeded', 'success'].includes(status ?? '')) return 'completed'
  if (['running', 'started', 'in_progress'].includes(status ?? '')) return 'running'
  if (['failed', 'error'].includes(status ?? '')) return 'failed'
  if (['denied', 'policy_denied'].includes(status ?? '')) return 'denied'
  if (status === 'blocked') return 'blocked'
  if (status === 'unavailable') return 'unavailable'
  if (status === 'skipped') return 'skipped'
  if (['pending', 'planned', 'queued'].includes(status ?? '')) return 'pending'
  if (status === 'recorded') return 'recorded'
  return 'unknown'
}

const STATUS_LABEL: Record<TraceStatus, string> = {
  running: 'In progress', completed: 'Completed', recorded: 'Recorded',
  pending: 'Pending', failed: 'Failed', unavailable: 'Unavailable',
  denied: 'Denied', blocked: 'Blocked', skipped: 'Skipped', unknown: 'Not established',
}

/** One presentation, two clocks: live events or deliberately labelled playback. */
export default function ResolutionTrace({
  title = 'Resolution trace', request, steps, mode, busy = false, outcome,
  recordingKey = '', recordingLabel, autoPlay = false, compact = false,
  onReplayComplete, showPlaybackControls = true, playbackIntervalMs = 1100, announce = true,
  variant = 'default',
}: Props) {
  const reduceMotion = Boolean(useReducedMotion())
  const id = useId()
  const root = useRef<HTMLElement>(null)
  const list = useRef<HTMLOListElement>(null)
  const follow = useRef(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [manualExpansion, setManualExpansion] = useState(false)
  const [visibleCount, setVisibleCount] = useState(autoPlay && mode === 'recorded' && !reduceMotion ? 0 : steps.length)
  const [playing, setPlaying] = useState(autoPlay && mode === 'recorded' && !reduceMotion)
  const [inView, setInView] = useState(true)
  const [pageVisible, setPageVisible] = useState(!document.hidden)
  const completedCallback = useRef(onReplayComplete)
  completedCallback.current = onReplayComplete
  const showcase = variant === 'showcase' && mode === 'recorded'
  const typing = showcase && !reduceMotion && Boolean(request)
  const [typedCount, setTypedCount] = useState(typing ? 0 : (request?.length ?? 0))
  const typedOut = !typing || typedCount >= (request?.length ?? 0)

  useEffect(() => {
    if (mode !== 'recorded') return
    setVisibleCount(autoPlay && !reduceMotion ? 0 : steps.length)
    setPlaying(autoPlay && !reduceMotion)
    setManualExpansion(false)
    follow.current = true
    setTypedCount(typing ? 0 : (request?.length ?? 0))
  }, [recordingKey, mode, autoPlay, reduceMotion, steps.length, typing, request])

  useEffect(() => {
    const visibility = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', visibility)
    const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(
      entries => setInView(entries[0]?.isIntersecting ?? true), { threshold: 0.12 },
    )
    if (root.current) observer?.observe(root.current)
    return () => {
      document.removeEventListener('visibilitychange', visibility)
      observer?.disconnect()
    }
  }, [])

  useEffect(() => {
    if (!typing || !playing || !inView || !pageVisible || typedOut) return
    const total = request?.length ?? 0
    const perTick = Math.max(1, Math.ceil(total / 40))
    const timer = window.setTimeout(() => setTypedCount(count => Math.min(count + perTick, total)), 30)
    return () => window.clearTimeout(timer)
  }, [typing, playing, inView, pageVisible, typedOut, typedCount, request])

  useEffect(() => {
    if (mode !== 'recorded' || !playing || !inView || !pageVisible || !typedOut) return
    if (visibleCount >= steps.length) {
      setPlaying(false)
      completedCallback.current?.()
      return
    }
    // This is presentation pacing, never an execution-duration measurement.
    const timer = window.setTimeout(() => setVisibleCount(count => count + 1), reduceMotion ? 0 : playbackIntervalMs)
    return () => window.clearTimeout(timer)
  }, [mode, playing, inView, pageVisible, typedOut, visibleCount, steps.length, reduceMotion, playbackIntervalMs])

  const revealed = mode === 'live' ? steps : steps.slice(0, visibleCount)
  // Showcase keeps the whole shape on screen and dims what has not been
  // reached, so the panel never reserves height for rows it is not showing.
  const rendered = showcase ? steps : revealed
  const settled = mode === 'live' ? !busy : visibleCount >= steps.length
  const active = [...revealed].reverse().find(step => step.status === 'running')?.id ?? revealed.at(-1)?.id
  const openId = manualExpansion ? expanded : active

  useEffect(() => {
    const container = list.current
    if (!container || !follow.current) return
    // Showcase opens a source excerpt inside the step it belongs to, so the
    // bottom of the list is the end of a code block rather than the new step.
    // Bring the step itself to the top instead; a live log still follows the tail.
    const step = showcase && active
      ? container.querySelector<HTMLElement>(`[data-step-id="${CSS.escape(active)}"]`)
      : null
    container.scrollTo?.({
      top: step ? step.offsetTop - container.offsetTop : container.scrollHeight,
      // Row reveals supply motion. Immediate internal scrolling avoids mistaking
      // a programmatic smooth-scroll frame for a reader scrolling into history.
      behavior: 'instant',
    })
  }, [active, revealed.length, reduceMotion, showcase])

  function replay() {
    setVisibleCount(reduceMotion ? steps.length : 0)
    setPlaying(!reduceMotion)
    setManualExpansion(false)
    follow.current = true
  }

  return (
    <MotionConfig reducedMotion="user" transition={{ duration: reduceMotion ? 0 : 0.55, ease: [0.22, 1, 0.36, 1] }}>
      <section className={`resolution-trace${compact ? ' resolution-trace--compact' : ''}${showcase ? ' resolution-trace--showcase' : ''}`} ref={root} aria-label={title} data-trace-mode={mode}>
        <header className="resolution-trace-head">
          <span className="resolution-trace-kicker">{title}</span>
          <span className="resolution-trace-mode">{mode === 'live' ? (busy ? 'Live activity' : 'Observed activity') : 'Recorded playback'}</span>
        </header>
        {request && (
          <p className="resolution-trace-request">
            {typing ? (
              <>
                <span className="sr-only">{request}</span>
                <span className="resolution-trace-typing" aria-hidden="true">
                  <span className="resolution-trace-typed">
                    {request.slice(0, typedCount)}
                    {!typedOut && <span className="resolution-trace-caret" />}
                  </span>
                  <span className="resolution-trace-reserve">{request}</span>
                </span>
              </>
            ) : request}
          </p>
        )}
        {recordingLabel && <p className="resolution-trace-recording">{recordingLabel}</p>}
        {mode === 'recorded' && showPlaybackControls && steps.length > 0 && (
          <div className="resolution-trace-controls" role="group" aria-label="Trace playback">
            <button type="button" onClick={() => {
              if (settled) replay()
              else setPlaying(value => !value)
            }}>
              {playing ? <Pause size={14} /> : <Play size={14} />}
              {playing ? 'Pause' : settled ? 'Play again' : 'Play'}
            </button>
            <button type="button" onClick={replay}><RotateCcw size={14} />Replay</button>
            <button type="button" onClick={() => {
              setVisibleCount(steps.length)
              setPlaying(false)
              completedCallback.current?.()
            }}>Show all</button>
            <span>{revealed.length} / {steps.length}</span>
          </div>
        )}
        <ol ref={list} className="resolution-trace-list" onScroll={() => {
          const el = list.current
          if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}>
          {rendered.length === 0 && <li className="resolution-trace-empty">{mode === 'live' ? 'Waiting for the first reported step.' : 'The recorded steps will appear here.'}</li>}
          {rendered.map((step, index) => {
            const reached = index < revealed.length
            const open = reached && openId === step.id
            return (
              <motion.li key={step.id} layout="position" className="resolution-trace-step" data-step-id={step.id} data-step-status={step.status} data-current={reached && step.id === active || undefined} data-reached={reached}
                initial={reduceMotion || showcase ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} aria-hidden={reached ? undefined : true}>
                <button className="resolution-trace-step-head" type="button" aria-expanded={open} aria-controls={`${id}-${index}`} disabled={!reached} tabIndex={reached ? undefined : -1}
                  onClick={() => {
                    setManualExpansion(true)
                    setExpanded(open ? null : step.id)
                    follow.current = false
                  }}>
                  <span className="resolution-trace-number" aria-label={`Step ${index + 1}`}>{String(index + 1).padStart(2, '0')}</span>
                  <span className="resolution-trace-step-title">{step.title}</span>
                  {/* A step the playback has not reached states no outcome.
                      Carrying "Completed" ahead of the reveal would assert a
                      result the recording has not shown yet, which is the one
                      thing this panel exists to be exact about. The element
                      stays so its grid column does not collapse. */}
                  <span className="resolution-trace-status">
                    {reached && step.status === 'completed' && <Check size={12} aria-hidden="true" />}
                    {reached && ['denied', 'blocked', 'failed', 'unavailable'].includes(step.status) && (
                      <span className="resolution-trace-status-dot" aria-hidden="true" />
                    )}
                    {reached && STATUS_LABEL[step.status]}
                  </span>
                  <ChevronDown className="resolution-trace-chevron" size={14} aria-hidden="true" />
                </button>
                {reached && step.summary && <p className="resolution-trace-summary">{step.summary}</p>}
                <AnimatePresence initial={false}>
                  {open && (
                    <motion.div id={`${id}-${index}`} className="resolution-trace-detail" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                      <div className="resolution-trace-facts">
                        {step.source && <span>{step.source}</span>}
                        {step.durationMs != null && Number.isFinite(step.durationMs) && step.durationMs >= 0 && <span>{step.durationMs < 1000 ? `${Math.round(step.durationMs)} ms` : `${(step.durationMs / 1000).toFixed(1)} s`} measured</span>}
                      </div>
                      {step.detail}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.li>
            )
          })}
        </ol>
        <div className="resolution-trace-announcement sr-only" role={announce ? 'status' : undefined} aria-live={announce ? undefined : 'off'}>
          {mode === 'live' ? `${revealed.length} reported steps. ${active ? revealed.find(s => s.id === active)?.title : ''}` : `${revealed.length} of ${steps.length} recorded steps shown.`}
        </div>
        <footer className="resolution-trace-outcome" data-outcome={settled ? outcome?.status : 'waiting'}>
          <motion.div key={settled && outcome ? outcome.label : 'following'}
            initial={reduceMotion ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>
          <span className="resolution-trace-kicker">{settled && outcome ? outcome.label : mode === 'live' ? 'Following the request' : 'Following the recording'}</span>
          {settled && outcome?.body ? <div className="resolution-trace-outcome-body">{outcome.body}</div> : <p>{mode === 'live' ? 'Each step reflects an event received from the application.' : 'Playback changes the presentation only. It does not execute the request.'}</p>}
          </motion.div>
        </footer>
      </section>
    </MotionConfig>
  )
}
