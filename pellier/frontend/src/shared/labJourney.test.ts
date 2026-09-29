import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'

import {
  LAB_JOURNEYS,
  LAB_JOURNEY_KEY,
  hideLabJourney,
  openLabJourney,
  readLabJourney,
  setLabJourneyStep,
} from './labJourney'
import { LAB_EXERCISE_IDS } from '../observatory/labs/labCatalog'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = join(HERE, '..', '..', '..', '..')
const APP = readFileSync(join(HERE, '..', 'App.tsx'), 'utf8')

afterEach(() => localStorage.clear())

describe('lab journeys', () => {
  it('covers every lab with its own ordered steps', () => {
    expect(Object.keys(LAB_JOURNEYS).sort()).toEqual([...LAB_EXERCISE_IDS].sort())
    for (const steps of Object.values(LAB_JOURNEYS)) {
      expect(steps.length).toBeGreaterThanOrEqual(5)
      expect(new Set(steps.map(step => step.label)).size).toBe(steps.length)
      // Short enough to sit on the stepper beside its neighbours.
      for (const step of steps) expect(step.label.length).toBeLessThanOrEqual(18)
    }
  })

  it('links only the steps that happen inside the app', () => {
    for (const step of Object.values(LAB_JOURNEYS).flat()) {
      if (step.surface === 'code' || step.surface === 'terminal') expect(step.href).toBeUndefined()
    }
  })

  it('names only files and scripts that exist in this repository', () => {
    const named = Object.values(LAB_JOURNEYS).flat()
      .filter(step => step.surface === 'code' || step.surface === 'terminal')
      .flatMap(step => (step.detail ?? '').split(' · '))
      .map(part => part.match(/(?:^|\s)((?:pellier|scripts|workshop|policies)\/[\w./-]+)/)?.[1])
      .filter((path): path is string => Boolean(path))
    expect(named.length).toBeGreaterThanOrEqual(12)
    for (const path of named) expect(existsSync(join(REPO, path)), path).toBe(true)
  })

  it('points every in-app step at a route the app serves', () => {
    for (const step of Object.values(LAB_JOURNEYS).flat()) {
      if (!step.href || step.href === '/') continue
      const [surface, first] = step.href.split(/[?#]/)[0].split('/').filter(Boolean)
      if (surface === 'observatory') expect(APP, step.href).toMatch(new RegExp(`path="${first}(/:[a-zA-Z]+)?"`))
      if (surface === 'operator') expect(APP, step.href).toMatch(new RegExp(`path="${first}(/:[a-zA-Z]+)?"`))
    }
  })
})

describe('lab journey store', () => {
  it('opens a lab at its first step and resumes each lab where it was left', () => {
    openLabJourney('retrieval-acceptance')
    expect(readLabJourney()).toMatchObject({ lab: 'retrieval-acceptance' })
    setLabJourneyStep('retrieval-acceptance', 3)
    openLabJourney('grounded-inventory')
    setLabJourneyStep('grounded-inventory', 1)
    openLabJourney('retrieval-acceptance')
    expect(readLabJourney().steps).toEqual({ 'retrieval-acceptance': 3, 'grounded-inventory': 1 })
  })

  it('keeps steps within the lab and hides without forgetting them', () => {
    setLabJourneyStep('fail-closed-policy', 99)
    expect(readLabJourney().steps['fail-closed-policy']).toBe(LAB_JOURNEYS['fail-closed-policy'].length - 1)
    hideLabJourney()
    expect(readLabJourney().lab).toBeNull()
    expect(readLabJourney().steps['fail-closed-policy']).toBe(LAB_JOURNEYS['fail-closed-policy'].length - 1)
  })

  it('reads a malformed or unknown record as no lab', () => {
    localStorage.setItem(LAB_JOURNEY_KEY, '{not json')
    expect(readLabJourney()).toEqual({ lab: null, steps: {} })
    localStorage.setItem(LAB_JOURNEY_KEY, JSON.stringify({ lab: 'lab-9', steps: { 'lab-9': 2 } }))
    expect(readLabJourney()).toEqual({ lab: null, steps: {} })
  })
})
