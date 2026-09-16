import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import ResolutionTrace, { type ResolutionStep, type TraceOutcome } from './ResolutionTrace'
import recordedScenarios from '../../data/pellierTraceScenarios.json'
import './trace-scenarios.css'

const HOLD_RESULT_MS = 4800

export default function TraceScenarioLoop() {
  const reducedMotion = Boolean(useReducedMotion())
  const root = useRef<HTMLElement>(null)
  const [active, setActive] = useState(0)
  const [cycle, setCycle] = useState(0)
  const [finished, setFinished] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [visible, setVisible] = useState(true)
  const [pageVisible, setPageVisible] = useState(!document.hidden)
  const scenario = recordedScenarios[active]

  useEffect(() => {
    const listener = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', listener)
    const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(
      entries => setVisible(entries[0]?.isIntersecting ?? true), { threshold: .15 },
    )
    if (root.current) observer?.observe(root.current)
    return () => {
      document.removeEventListener('visibilitychange', listener)
      observer?.disconnect()
    }
  }, [])

  useEffect(() => {
    if (!finished || showAll || reducedMotion || hovered || focused || !visible || !pageVisible) return
    const timer = window.setTimeout(() => {
      setFinished(false)
      setActive(index => (index + 1) % recordedScenarios.length)
      setCycle(value => value + 1)
    }, HOLD_RESULT_MS)
    return () => window.clearTimeout(timer)
  }, [finished, showAll, reducedMotion, hovered, focused, visible, pageVisible])

  function select(index: number) {
    setActive(index)
    setCycle(value => value + 1)
    setFinished(false)
    setShowAll(false)
  }

  function trace(index: number, playback: boolean) {
    const example = recordedScenarios[index]
    return <ResolutionTrace
      title={example.title} request={example.request} steps={example.steps as ResolutionStep[]}
      mode="recorded" autoPlay={playback && !reducedMotion} showPlaybackControls={false}
      recordingKey={`${example.id}:${cycle}`} playbackIntervalMs={1600} announce={false}
      recordingLabel={example.provenance}
      onReplayComplete={() => setFinished(true)}
      outcome={{ label: example.outcomeLabel, body: example.answer, status: example.outcomeStatus as TraceOutcome['status'] }}
    />
  }

  return (
    <section ref={root} className="trace-scenario-loop" aria-label="Recorded Pellier examples"
      data-active-scenario={scenario.id} data-view={showAll ? 'all' : 'sequence'}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false)
      }}>
      <div className="trace-scenario-tabs" role="group" aria-label="Example scenarios">
        {recordedScenarios.map((example, index) => (
          <button type="button" key={example.id} aria-pressed={!showAll && index === active}
            onClick={() => select(index)}>
            <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>{example.label}
          </button>
        ))}
      </div>
      {showAll ? (
        <div className="trace-scenario-all">{recordedScenarios.map((example, index) => <div key={example.id}>{trace(index, false)}</div>)}</div>
      ) : (
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={`${scenario.id}:${cycle}`} className="trace-scenario-stage"
            initial={reducedMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? { opacity: 1 } : { opacity: 0, y: -4 }}
            transition={{ duration: reducedMotion ? 0 : .6, ease: [.22, 1, .36, 1] }}>
            {trace(active, true)}
          </motion.div>
        </AnimatePresence>
      )}
      <div className="trace-scenario-foot">
        <span>{reducedMotion ? 'Choose an example to inspect.' : showAll ? 'All examples remain open for inspection.' : 'Three recorded requests, on repeat. Hover or focus to hold the result.'}</span>
        <button type="button" onClick={() => {
          setShowAll(value => !value)
          setFinished(false)
          setCycle(value => value + 1)
        }}>{showAll ? 'Play examples' : 'View all examples'}</button>
      </div>
    </section>
  )
}
