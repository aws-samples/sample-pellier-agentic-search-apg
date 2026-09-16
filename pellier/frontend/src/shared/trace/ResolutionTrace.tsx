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

  useEffect(() => {
    if (mode !== 'recorded') return
    setVisibleCount(autoPlay && !reduceMotion ? 0 : steps.length)
    setPlaying(autoPlay && !reduceMotion)
    setManualExpansion(false)
    follow.current = true
  }, [recordingKey, mode, autoPlay, reduceMotion, steps.length])

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
    if (mode !== 'recorded' || !playing || !inView || !pageVisible) return
    if (visibleCount >= steps.length) {
      setPlaying(false)
      completedCallback.current?.()
      return
    }
    // This is presentation pacing, never an execution-duration measurement.
    const timer = window.setTimeout(() => setVisibleCount(count => count + 1), reduceMotion ? 0 : playbackIntervalMs)
    return () => window.clearTimeout(timer)
  }, [mode, playing, inView, pageVisible, visibleCount, steps.length, reduceMotion, playbackIntervalMs])

  const visible = mode === 'live' ? steps : steps.slice(0, visibleCount)
  const settled = mode === 'live' ? !busy : visibleCount >= steps.length
  const active = [...visible].reverse().find(step => step.status === 'running')?.id ?? visible.at(-1)?.id
  const openId = manualExpansion ? expanded : active

  useEffect(() => {
    const container = list.current
    if (!container || !follow.current) return
    container.scrollTo?.({
      top: container.scrollHeight,
      // Row reveals supply motion. Immediate internal scrolling avoids mistaking
      // a programmatic smooth-scroll frame for a reader scrolling into history.
      behavior: 'instant',
    })
  }, [active, visible.length, reduceMotion])

  function replay() {
    setVisibleCount(reduceMotion ? steps.length : 0)
    setPlaying(!reduceMotion)
    setManualExpansion(false)
    follow.current = true
  }

  return (
    <MotionConfig reducedMotion="user" transition={{ duration: reduceMotion ? 0 : 0.55, ease: [0.22, 1, 0.36, 1] }}>
      <section className={`resolution-trace${compact ? ' resolution-trace--compact' : ''}`} ref={root} aria-label={title} data-trace-mode={mode}>
        <header className="resolution-trace-head">
          <span className="resolution-trace-kicker">{title}</span>
          <span className="resolution-trace-mode">{mode === 'live' ? (busy ? 'Live activity' : 'Observed activity') : 'Recorded playback'}</span>
        </header>
        {request && <p className="resolution-trace-request">{request}</p>}
        {recordingLabel && <p className="resolution-trace-recording">{recordingLabel}</p>}
        {mode === 'recorded' && showPlaybackControls && steps.length > 0 && (
          <div className="resolution-trace-controls" aria-label="Trace playback">
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
            <span>{visible.length} / {steps.length}</span>
          </div>
        )}
        <ol ref={list} className="resolution-trace-list" onScroll={() => {
          const el = list.current
          if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}>
          {visible.length === 0 && <li className="resolution-trace-empty">{mode === 'live' ? 'Waiting for the first reported step.' : 'The recorded steps will appear here.'}</li>}
          {visible.map((step, index) => {
            const open = openId === step.id
            return (
              <motion.li key={step.id} layout="position" className="resolution-trace-step" data-step-id={step.id} data-step-status={step.status} data-current={step.id === active || undefined}
                initial={reduceMotion ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <button className="resolution-trace-step-head" type="button" aria-expanded={open} aria-controls={`${id}-${index}`}
                  onClick={() => {
                    setManualExpansion(true)
                    setExpanded(open ? null : step.id)
                    follow.current = false
                  }}>
                  <span className="resolution-trace-number" aria-label={`Step ${index + 1}`}>{String(index + 1).padStart(2, '0')}</span>
                  <span className="resolution-trace-step-title">{step.title}</span>
                  <span className="resolution-trace-status">
                    {step.status === 'completed' && <Check size={12} aria-hidden="true" />}
                    {STATUS_LABEL[step.status]}
                  </span>
                  <ChevronDown className="resolution-trace-chevron" size={14} aria-hidden="true" />
                </button>
                {step.summary && <p className="resolution-trace-summary">{step.summary}</p>}
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
          {mode === 'live' ? `${visible.length} reported steps. ${active ? visible.find(s => s.id === active)?.title : ''}` : `${visible.length} of ${steps.length} recorded steps shown.`}
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
