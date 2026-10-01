import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import {
  LAB_JOURNEYS,
  LAB_JOURNEY_KEY,
  hideLabJourney,
  openLabJourney,
  readLabJourney,
  setLabJourneyStep,
  useLabJourney,
} from './labJourney'
import { LAB_EXERCISE_IDS } from '../observatory/labs/labCatalog'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = join(HERE, '..', '..', '..', '..')
const APP = readFileSync(join(HERE, '..', 'App.tsx'), 'utf8')

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('lab journeys', () => {
  it('covers every lab with its own ordered steps', () => {
    expect(Object.keys(LAB_JOURNEYS).sort()).toEqual([...LAB_EXERCISE_IDS].sort())
    for (const steps of Object.values(LAB_JOURNEYS)) {
      expect(steps.length).toBeGreaterThanOrEqual(5)
      expect(new Set(steps.map(step => step.label)).size).toBe(steps.length)
      expect(new Set(steps.map(step => step.id)).size).toBe(steps.length)
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
  it('migrates earlier numeric bookmarks and writes stable step IDs', () => {
    localStorage.setItem(LAB_JOURNEY_KEY, JSON.stringify({
      lab: 'fail-closed-policy', steps: { 'fail-closed-policy': 7 },
    }))
    expect(LAB_JOURNEYS['fail-closed-policy'][readLabJourney().steps['fail-closed-policy']!].id).toBe('prepare-review')
    hideLabJourney()
    expect(JSON.parse(localStorage.getItem(LAB_JOURNEY_KEY)!)).toEqual({
      version: 2, lab: null, steps: { 'fail-closed-policy': 'prepare-review' },
    })
  })

  it('resumes a saved ID and falls back safely when that step no longer exists', () => {
    localStorage.setItem(LAB_JOURNEY_KEY, JSON.stringify({
      version: 2, lab: 'retrieval-acceptance',
      steps: { 'retrieval-acceptance': 'prove-fallback', 'grounded-inventory': 'removed-step' },
    }))
    expect(readLabJourney().steps).toEqual({ 'retrieval-acceptance': 3, 'grounded-inventory': 0 })
  })

  it('keeps the guide usable in memory when browser storage is blocked', () => {
    readLabJourney()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    openLabJourney('grounded-inventory')
    setLabJourneyStep('grounded-inventory', 2)
    expect(readLabJourney()).toEqual({ lab: 'grounded-inventory', steps: { 'grounded-inventory': 2 } })
    hideLabJourney()
    expect(readLabJourney()).toEqual({ lab: null, steps: { 'grounded-inventory': 2 } })
  })

  it('responds to another tab clearing the saved journey', () => {
    openLabJourney('grounded-inventory')
    const { result } = renderHook(() => useLabJourney())
    expect(result.current.lab).toBe('grounded-inventory')
    act(() => {
      localStorage.clear()
      window.dispatchEvent(new StorageEvent('storage', { key: null }))
    })
    expect(result.current.lab).toBeNull()
  })

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
