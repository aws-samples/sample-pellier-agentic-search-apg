/**
 * Each lab's path through the three surfaces, and where this browser is on it.
 *
 * A lab moves between the Storefront, Code Editor, a terminal, the Operator
 * desk and the Observatory. Nothing on screen used to say which of those came
 * next, and every surface change dropped the lab: Anna's "Why this answer?"
 * opened under Marco's lab, and Jessica's case left the Observatory for the
 * Operator with no way back. The steps below are the Workshop Studio guide's
 * required path, in its order and its words.
 *
 * The position is a place, not a result. A step behind the current one was
 * visited here; it is never marked done, because the guide's terminal checks
 * are the only proof that a lab passed.
 */
import { useCallback, useSyncExternalStore } from 'react'

import { LAB_EXERCISE_IDS, type LabExerciseId } from '../observatory/labs/labCatalog'

export type JourneySurface = 'storefront' | 'code' | 'terminal' | 'operator' | 'observatory'

export const SURFACE_LABELS: Record<JourneySurface, string> = {
  storefront: 'Storefront',
  code: 'Code Editor',
  terminal: 'Terminal',
  operator: 'Operator',
  observatory: 'Observatory',
}

export interface JourneyStep {
  surface: JourneySurface
  /** A few words, shown on the stepper. */
  label: string
  /** What to do, in one sentence. */
  action: string
  /** The file, command or control the guide names. */
  detail?: string
  /** Where the step happens inside the app. Code Editor and terminal steps have none. */
  href?: string
  optional?: boolean
}

export const LAB_JOURNEYS: Record<LabExerciseId, JourneyStep[]> = {
  'grounded-inventory': [
    { surface: 'storefront', label: 'Ask as Marco', href: '/',
      action: 'Select Marco, sign in as marco, and send both stock questions in one conversation.',
      detail: 'Ask Pellier › Scenario & account details › Sign in for account requests' },
    { surface: 'code', label: 'Inventory contract',
      action: 'Task 1A: return check_inventory’s result without recasting it.',
      detail: 'pellier/backend/services/agent_tools.py' },
    { surface: 'code', label: 'Wire the agent',
      action: 'Task 1B: give the Inventory Agent its tool.',
      detail: 'pellier/backend/agents/inventory_agent.py' },
    { surface: 'terminal', label: 'Check and restart',
      action: 'Run the contract check with an unknown and an ambiguous query, then restart.',
      detail: 'python3 scripts/lab1_contract_check.py · sudo systemctl restart pellier' },
    { surface: 'storefront', label: 'Ask again', href: '/',
      action: 'Replay the stock question, open Match details, then Why this answer?, and copy the turn.',
      detail: 'Match details › Why this answer?' },
    { surface: 'observatory', label: 'Read the receipt', href: '/observatory/proof-board',
      action: 'Why this answer? opens this turn’s receipt on the Proof Board.' },
    { surface: 'terminal', label: 'Record lab-1.json',
      action: 'Reconcile the turn with Aurora in psql and save lab-1.json.',
      detail: 'psql · jq' },
  ],
  'retrieval-acceptance': [
    { surface: 'storefront', label: 'Ask as Anna', href: '/',
      action: 'Sign in as anna, select Anna, ask for the housewarming gift, and read the plan in Why this answer?',
      detail: 'Why this answer? › recorded plan' },
    { surface: 'code', label: 'Recorded RRF',
      action: 'Task 2A: reconstruct the fusion expression from the recorded ranks.',
      detail: 'workshop/lab-2-rrf.sql' },
    { surface: 'code', label: 'Keep requirements',
      action: 'Task 2B: let a retry relax a preference, never a requirement.',
      detail: 'pellier/backend/services/search_plan.py' },
    { surface: 'terminal', label: 'Prove the fallback',
      action: 'Choose the preference that forces a fallback, check the plan contract and restart.',
      detail: 'python3 scripts/lab2_plan_contract_check.py · sudo systemctl restart pellier' },
    { surface: 'terminal', label: 'Record lab-2.json',
      action: 'Fill the RRF worksheet and save lab-2.json.',
      detail: 'psql · jq' },
    { surface: 'observatory', label: 'See ranks move', href: '/observatory/search', optional: true,
      action: 'Optional: compare vector, lexical and fused ranks for a new query.' },
  ],
  'managed-agent-path': [
    { surface: 'terminal', label: 'Prerequisites',
      action: 'Run the Lab 3 doctor before editing.',
      detail: 'python3 scripts/workshop_doctor.py --lab 3 --phase prerequisites' },
    { surface: 'code', label: 'Publish the tool',
      action: 'Task 3A: publish get_ticket_history and bind it to the caller.',
      detail: 'scripts/deploy/gateway_tool_schemas.py · pellier/backend/services/agentcore_gateway.py' },
    { surface: 'terminal', label: 'Deploy',
      action: 'Task 3B: deploy the managed path.',
      detail: 'python3 scripts/provision_agentcore_end_to_end.py --mode participant' },
    { surface: 'terminal', label: 'Challenge scope',
      action: 'Probe an owned and a foreign ticket read, then recall Theo’s memory.',
      detail: 'python3 scripts/probe_gateway_tool.py · python3 scripts/showcase_agentcore_memory.py recall' },
    { surface: 'storefront', label: 'Ask as Theo', href: '/',
      action: 'Sign in as theo, select Theo, send both turns, and check Why this answer?' },
    { surface: 'terminal', label: 'Record lab-3.json',
      action: 'Correlate the build, caller, Memory and Aurora evidence and save lab-3.json.',
      detail: 'psql · jq' },
    { surface: 'observatory', label: 'Memory view', href: '/observatory/memory', optional: true,
      action: 'Optional: inspect the extracted preference and its recall.' },
  ],
  'fail-closed-policy': [
    { surface: 'code', label: 'Ownership rule',
      action: 'Task 4A: complete the Cedar unless block.',
      detail: 'policies/workshop_identity_match_forbid.cedar' },
    { surface: 'terminal', label: 'Deploy policy',
      action: 'Render and deploy the policy, then run the doctor.' },
    { surface: 'code', label: 'RLS and absence',
      action: 'Task 4B: write the row ownership predicate and the keyed absence proof.',
      detail: 'workshop/lab-4-rls.sql · workshop/lab-4-absence.sql' },
    { surface: 'terminal', label: 'Five outcomes',
      action: 'Prove the five outcomes, RLS and keyed absence.',
      detail: 'python3 scripts/prove_governance_outcomes.py' },
    { surface: 'observatory', label: 'Govern evidence', href: '/observatory/govern/verification', optional: true,
      action: 'Optional: read which control acted in Govern › Evidence & verification.' },
    { surface: 'operator', label: 'Investigate', href: '/operator/clients/CUST-JESSICA#operator-concierge',
      action: 'Sign in as operator, open Jessica’s Operator chat and ask the investigation prompt.' },
    { surface: 'observatory', label: 'Inspect the turn',
      action: 'In the reply, open Inspect this turn in Observatory › Recorded artifact.',
      detail: 'case-investigator precedes resolution-planner; fingerprintMatches is true' },
    { surface: 'operator', label: 'Review and execute', href: '/operator/reviews',
      action: 'Prepare the return review, then Confirm and Execute, checking each phase; reopen Jessica’s record.',
      detail: 'python3 scripts/prove_operator_review.py' },
  ],
}

export const LAB_JOURNEY_KEY = 'pellier-lab-journey'
const CHANGE_EVENT = 'pellier-lab-journey-change'

export interface LabJourneyState {
  /** The lab the guide is showing, or null when it is hidden. */
  lab: LabExerciseId | null
  /** The current step per lab, so switching labs resumes each one. */
  steps: Partial<Record<LabExerciseId, number>>
}

const EMPTY: LabJourneyState = { lab: null, steps: {} }

function isLab(value: unknown): value is LabExerciseId {
  return typeof value === 'string' && (LAB_EXERCISE_IDS as ReadonlyArray<string>).includes(value)
}

function clampStep(lab: LabExerciseId, step: unknown): number {
  const last = LAB_JOURNEYS[lab].length - 1
  return typeof step === 'number' && Number.isInteger(step) ? Math.min(Math.max(step, 0), last) : 0
}

let cachedRaw: string | null | undefined
let cachedState: LabJourneyState = EMPTY

/** The stored position. Unknown labs and malformed records read as empty. */
export function readLabJourney(): LabJourneyState {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(LAB_JOURNEY_KEY)
  } catch {
    return EMPTY
  }
  // useSyncExternalStore needs a stable snapshot for an unchanged store.
  if (raw === cachedRaw) return cachedState
  cachedRaw = raw
  cachedState = EMPTY
  if (!raw) return cachedState
  try {
    const parsed = JSON.parse(raw) as { lab?: unknown; steps?: Record<string, unknown> }
    const steps: LabJourneyState['steps'] = {}
    for (const id of LAB_EXERCISE_IDS) {
      if (parsed.steps && id in parsed.steps) steps[id] = clampStep(id, parsed.steps[id])
    }
    cachedState = { lab: isLab(parsed.lab) ? parsed.lab : null, steps }
  } catch {
    cachedState = EMPTY
  }
  return cachedState
}

function write(state: LabJourneyState): void {
  try {
    localStorage.setItem(LAB_JOURNEY_KEY, JSON.stringify(state))
  } catch {
    // Storage can be unavailable; the guide then lasts for this page only.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

/** Show a lab's guide, resuming its last step. */
export function openLabJourney(lab: LabExerciseId): void {
  const current = readLabJourney()
  if (current.lab === lab) return
  write({ lab, steps: current.steps })
}

export function setLabJourneyStep(lab: LabExerciseId, step: number): void {
  const current = readLabJourney()
  write({ lab, steps: { ...current.steps, [lab]: clampStep(lab, step) } })
}

/** Hide the guide. Each lab keeps its step for when it is opened again. */
export function hideLabJourney(): void {
  write({ ...readLabJourney(), lab: null })
}

function subscribe(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === LAB_JOURNEY_KEY) onChange()
  }
  window.addEventListener(CHANGE_EVENT, onChange)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
    window.removeEventListener('storage', onStorage)
  }
}

/** The active lab and its current step, kept in sync across every surface. */
export function useLabJourney() {
  const state = useSyncExternalStore(subscribe, readLabJourney, () => EMPTY)
  const lab = state.lab
  const step = lab ? state.steps[lab] ?? 0 : 0
  const setStep = useCallback((next: number) => { if (lab) setLabJourneyStep(lab, next) }, [lab])
  return { lab, step, steps: lab ? LAB_JOURNEYS[lab] : [], setStep }
}
