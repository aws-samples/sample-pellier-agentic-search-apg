import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import ResolutionTrace, { type ResolutionStep, type TraceOutcome } from './ResolutionTrace'
import recordedScenarios from '../../data/pellierTraceScenarios.json'
import TraceScenarioDetails from './TraceScenarioDetails'
import './trace-scenarios.css'

const HOLD_RESULT_MS = 4800

export default function TraceScenarioLoop({ showDetails = false }: { showDetails?: boolean }) {
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

  /** The excerpt belongs to the step whose work it came from, so it opens in
   *  place as that step is reached rather than sitting in a separate panel. */
  function stepsWithSource(example: typeof recordedScenarios[number]): ResolutionStep[] {
    const { codeStepId, codeLabel, language, code, codeNote } = example.inspection
    return (example.steps as ResolutionStep[]).map(step => step.id === codeStepId
      ? {
        ...step,
        detail: <div className="trace-step-source">
          <div className="trace-step-source-panel">
            <div className="trace-step-source-heading"><span>{codeLabel}</span><span>{language}</span></div>
            <pre tabIndex={0} aria-label={codeLabel}><code>{code}</code></pre>
          </div>
          <p>{codeNote}</p>
        </div>,
      }
      : step)
  }

  function trace(index: number, playback: boolean) {
    const example = recordedScenarios[index]
    return <><ResolutionTrace
      title={`${example.label} · ${example.title}`} request={example.request} steps={stepsWithSource(example)}
      mode="recorded" variant="showcase" autoPlay={playback && !reducedMotion} showPlaybackControls={false}
      recordingKey={`${example.id}:${cycle}`} playbackIntervalMs={1600} announce={false}
      recordingLabel={example.provenance}
      onReplayComplete={() => setFinished(true)}
      outcome={{ label: example.outcomeLabel, body: example.answer, status: example.outcomeStatus as TraceOutcome['status'] }}
    />
      {showDetails && <TraceScenarioDetails example={example} />}
    </>
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
            <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>{example.chapter}
          </button>
        ))}
      </div>
      {!showAll && (
        <div className="trace-scenario-layer">
          <p className="trace-scenario-adds">{scenario.adds}</p>
          {scenario.buildsOn && <p className="trace-scenario-builds">{scenario.buildsOn}</p>}
        </div>
      )}
      {showDetails && !showAll && (
        <a className="trace-scenario-inspect" href={`#trace-details-${scenario.id}`}>
          Inspect SQL, source, and exercise details <span aria-hidden>↓</span>
        </a>
      )}
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
        <span>{reducedMotion ? 'Choose a chapter to inspect.' : showAll ? 'All three chapters are open.' : 'Three separate recordings, played in order. Hover or focus to hold one open.'}</span>
        <button type="button" onClick={() => {
          setShowAll(value => !value)
          setFinished(false)
          setCycle(value => value + 1)
        }}>{showAll ? 'Play the sequence' : 'View all three'}</button>
      </div>
    </section>
  )
}
