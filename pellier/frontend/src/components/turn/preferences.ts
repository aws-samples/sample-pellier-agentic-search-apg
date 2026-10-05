/**
 * Builder view choices, remembered per browser.
 *
 * Both are off by default. They are view and request preferences, not
 * evidence, so browser storage is the right home for them.
 *
 * Builder view is one global switch in the shared header: the page's ranking
 * panel, the dock's evidence and the Operator's investigation all read it, so
 * every reader subscribes to the same value and moves together.
 */
import { useCallback, useState, useSyncExternalStore } from 'react'

export const BUILDER_VIEW_KEY = 'pellier-builder-view'
export const SKILL_MODE_KEY = 'pellier-skill-mode'

export type SkillMode = 'fixed' | 'on_demand'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Private mode or a full store: the choice lasts for this page only.
  }
}

export function readBuilderView(): boolean {
  return read(BUILDER_VIEW_KEY) === 'on'
}

const builderViewListeners = new Set<() => void>()
// Where storage throws, the choice lasts for this page in memory.
let builderViewInMemory = false

export function writeBuilderView(on: boolean): void {
  write(BUILDER_VIEW_KEY, on ? 'on' : 'off')
  builderViewInMemory = on
  builderViewListeners.forEach(listener => listener())
}

function builderViewSnapshot(): boolean {
  try {
    return localStorage.getItem(BUILDER_VIEW_KEY) === 'on'
  } catch {
    return builderViewInMemory
  }
}

function subscribeBuilderView(listener: () => void): () => void {
  builderViewListeners.add(listener)
  return () => builderViewListeners.delete(listener)
}

export function readSkillMode(): SkillMode {
  return read(SKILL_MODE_KEY) === 'on_demand' ? 'on_demand' : 'fixed'
}

export function writeSkillMode(mode: SkillMode): void {
  write(SKILL_MODE_KEY, mode)
}

export function useBuilderView(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribeBuilderView, builderViewSnapshot, builderViewSnapshot)
  const update = useCallback((next: boolean) => writeBuilderView(next), [])
  return [on, update]
}

export function useSkillMode(): [SkillMode, (mode: SkillMode) => void] {
  const [mode, setMode] = useState<SkillMode>(readSkillMode)
  const update = useCallback((next: SkillMode) => {
    writeSkillMode(next)
    setMode(next)
  }, [])
  return [mode, update]
}
