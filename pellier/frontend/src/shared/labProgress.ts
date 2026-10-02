/**
 * Where the participant left off.
 *
 * A workshop is interrupted constantly: a question from the next seat, a
 * browser closed at the break, a laptop that slept through Lab 1. This store
 * keeps the one fact needed to come back, in the browser that was used, so
 * Resume is a link rather than a memory test.
 *
 * It records the lab, the step within the workbench, and the next action in
 * the participant's own terms. It is not a completion signal: the Observatory
 * is optional and has no honest notion of "done", so nothing here claims
 * progress through the workshop.
 */
import { LAB_EXERCISE_IDS, type LabExerciseId } from '../observatory/labs/labCatalog'

export const LAB_PROGRESS_KEY = 'pellier-lab-progress'

/** The workbench steps, matching `FOCUS_PANELS` ids. */
const LAB_PROGRESS_STEPS = ['run', 'inspect', 'reconcile'] as const

export type LabProgressStep = (typeof LAB_PROGRESS_STEPS)[number]

export interface LabProgress {
  lab: LabExerciseId
  step: LabProgressStep
  /** What to do next, in the participant's words. May be empty. */
  nextAction: string
  /** ISO timestamp of the write. */
  updatedAt: string
}

export type LabProgressInput = Omit<LabProgress, 'updatedAt'>

function isLabId(value: unknown): value is LabExerciseId {
  return (
    typeof value === 'string' &&
    (LAB_EXERCISE_IDS as ReadonlyArray<string>).includes(value)
  )
}

function isStep(value: unknown): value is LabProgressStep {
  return (
    typeof value === 'string' &&
    (LAB_PROGRESS_STEPS as ReadonlyArray<string>).includes(value)
  )
}

/**
 * The stored progress, or `null`.
 *
 * A record naming a lab that no longer exists, or one that cannot be parsed,
 * is discarded: resuming into a dead route is worse than not offering resume.
 */
export function readLabProgress(): LabProgress | null {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(LAB_PROGRESS_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<LabProgress>
    if (!isLabId(parsed.lab) || !isStep(parsed.step)) return null
    return {
      lab: parsed.lab,
      step: parsed.step,
      nextAction: typeof parsed.nextAction === 'string' ? parsed.nextAction : '',
      updatedAt:
        typeof parsed.updatedAt === 'string'
          ? parsed.updatedAt
          : new Date(0).toISOString(),
    }
  } catch {
    return null
  }
}

/** Record where the participant is. Storage failures are non-fatal. */
export function writeLabProgress(progress: LabProgressInput): void {
  try {
    localStorage.setItem(
      LAB_PROGRESS_KEY,
      JSON.stringify({ ...progress, updatedAt: new Date().toISOString() }),
    )
  } catch {
    // A private window must not break the workbench.
  }
}

/** The workbench route that reopens this position. */
export function resumeHref(progress: LabProgress): string {
  return `/observatory/workbench?lab=${progress.lab}&step=${progress.step}`
}
