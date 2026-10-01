/**
 * The active lab's path, under the shared surface navigation on every surface.
 *
 * One row: the lab, its steps as a stepper, and the one next action. The step's
 * full instruction, the lab's reference views and the lab switch open from the
 * row's menu over the page, so the row costs one line of height and no more.
 *
 * It replaces the Observatory-only lab strip. The surface links above stay the
 * only way to move between surfaces; this names the order the lab visits them.
 */
import { useRef, type ReactNode } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import {
  SURFACE_LABELS,
  hideLabJourney,
  openLabJourney,
  useLabJourney,
  type JourneyStep,
} from '../shared/labJourney'
import { LAB_EXERCISES } from '../observatory/labs/labCatalog'
import { LAB_REFERENCE_GROUPS, REFERENCES } from '../observatory/components/referenceCatalog'
import '../styles/lab-journey.css'

type Surface = 'storefront' | 'operator' | 'observatory'

function surfaceFor(path: string): Surface {
  if (path === '/operator' || path.startsWith('/operator/')) return 'operator'
  if (path === '/observatory' || path.startsWith('/observatory/')) return 'observatory'
  return 'storefront'
}

/** A step is where you already are when its surface, and its page, are open. */
function onStep(step: JourneyStep, pathname: string): boolean {
  if (!step.href) return false
  if (step.surface === 'storefront') return surfaceFor(pathname) === 'storefront'
  const path = step.href.split(/[?#]/)[0]
  return pathname === path || pathname.startsWith(`${path}/`)
}

export default function LabJourneyBar() {
  const { pathname } = useLocation()
  const { lab, step, steps, setStep } = useLabJourney()
  const menu = useRef<HTMLDetailsElement>(null)
  if (!lab || pathname === '/signin' || steps.length === 0) return null

  const exercise = LAB_EXERCISES.find(item => item.id === lab)!
  const number = Number(exercise.number)
  const group = LAB_REFERENCE_GROUPS.find(item => item.lab === lab)
  const current = steps[step]
  const next = steps[step + 1]
  const nextLab = LAB_EXERCISES[LAB_EXERCISES.indexOf(exercise) + 1]
  const closeMenu = () => { if (menu.current) menu.current.open = false }

  let action: ReactNode
  if (current.href && !onStep(current, pathname)) {
    action = <Link className="pellier-journey-action" to={current.href}>Open in {SURFACE_LABELS[current.surface]}</Link>
  } else if (next) {
    action = <button type="button" className="pellier-journey-action" onClick={() => setStep(step + 1)}>Next: {next.label}</button>
  } else if (nextLab) {
    action = <Link className="pellier-journey-action" to={`/observatory/workbench?lab=${nextLab.id}`} onClick={() => openLabJourney(nextLab.id)}>Start Lab {Number(nextLab.number)}</Link>
  } else {
    action = <Link className="pellier-journey-action" to="/observatory">Lab Collection</Link>
  }

  return (
    <nav className="pellier-journey" aria-label={`Lab ${number} guide`} data-testid="lab-journey">
      <p className="pellier-journey-lab">
        <span>Lab {number}</span>
        <strong>{exercise.anchorName}</strong>
      </p>
      <ol className="pellier-journey-steps">
        {steps.map((item, index) => {
          const state = index < step ? 'earlier' : index === step ? 'current' : 'upcoming'
          return (
            <li key={item.id} data-state={state} data-optional={item.optional ? 'true' : undefined}>
              <button
                type="button"
                onClick={() => setStep(index)}
                aria-current={state === 'current' ? 'step' : undefined}
                title={`${SURFACE_LABELS[item.surface]}: ${item.action}`}
              >
                <span className="pellier-journey-marker" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="pellier-journey-label">{item.label}</span>
                <span className="sr-only">, step {index + 1} of {steps.length}, {SURFACE_LABELS[item.surface]}{item.optional ? ', optional' : ''}</span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="pellier-journey-now" aria-live="polite">
        <span>{step + 1}/{steps.length}</span>
        {current.label}
      </p>
      {action}
      <details className="pellier-journey-menu" ref={menu}>
        <summary aria-label="Step details, reference views and labs"><ChevronDown size={16} aria-hidden="true" /></summary>
        <div className="pellier-journey-panel">
          <section className="pellier-journey-panel-now" aria-label="Current step">
            <span className="pellier-journey-surface">Step {step + 1} of {steps.length} · {SURFACE_LABELS[current.surface]}{current.optional ? ' · optional' : ''}</span>
            <p>{current.action}</p>
            {current.detail ? <code>{current.detail}</code> : null}
          </section>
          <ol className="pellier-journey-panel-steps" aria-label={`Lab ${number} steps`}>
            {steps.map((item, index) => (
              <li key={item.id} data-state={index < step ? 'earlier' : index === step ? 'current' : 'upcoming'}>
                <button type="button" onClick={() => setStep(index)}>
                  <span className="pellier-journey-surface">{SURFACE_LABELS[item.surface]}</span>
                  <span>{index + 1}. {item.label}{item.optional ? ' (optional)' : ''}</span>
                </button>
              </li>
            ))}
          </ol>
          <div className="pellier-journey-panel-links">
            <section aria-label={`Lab ${number} views`}>
              <span className="pellier-journey-surface">Observatory views</span>
              <Link to={`/observatory/workbench?lab=${lab}`} onClick={closeMenu}>Workbench</Link>
              {group?.refs.map(id => <Link key={id} to={REFERENCES[id].path} onClick={closeMenu}>{REFERENCES[id].label}</Link>)}
            </section>
            <section aria-label="Labs">
              <span className="pellier-journey-surface">Labs</span>
              <div className="pellier-journey-labs">
                {LAB_EXERCISES.map(item => (
                  <Link
                    key={item.id}
                    to={`/observatory/workbench?lab=${item.id}`}
                    aria-current={item.id === lab ? 'true' : undefined}
                    aria-label={`Lab ${Number(item.number)} ${item.anchorName}: ${item.title}`}
                    title={`Lab ${Number(item.number)} · ${item.anchorName}`}
                    onClick={() => { openLabJourney(item.id); closeMenu() }}
                  >
                    {Number(item.number)}
                  </Link>
                ))}
              </div>
            </section>
          </div>
          <button type="button" className="pellier-journey-hide" onClick={hideLabJourney}>
            <X size={14} aria-hidden="true" /> Hide the lab guide
          </button>
        </div>
      </details>
    </nav>
  )
}
