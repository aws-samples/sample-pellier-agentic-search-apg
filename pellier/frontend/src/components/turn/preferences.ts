/**
 * Builder view choices, remembered per browser.
 *
 * Both are off by default. They are view and request preferences, not
 * evidence, so browser storage is the right home for them.
 */
import { useCallback, useState } from 'react'

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

export function writeBuilderView(on: boolean): void {
  write(BUILDER_VIEW_KEY, on ? 'on' : 'off')
}

export function readSkillMode(): SkillMode {
  return read(SKILL_MODE_KEY) === 'on_demand' ? 'on_demand' : 'fixed'
}

export function writeSkillMode(mode: SkillMode): void {
  write(SKILL_MODE_KEY, mode)
}

export function useBuilderView(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState<boolean>(readBuilderView)
  const update = useCallback((next: boolean) => {
    writeBuilderView(next)
    setOn(next)
  }, [])
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
