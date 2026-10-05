/**
 * The Builder view switches.
 *
 * `BuilderViewToggle` is the one global switch, in the shared header: it
 * governs the page's "How it ranked" panel, the dock's evidence and the
 * Operator's investigation together. Off by default, remembered per browser.
 *
 * `SkillModeToggle` stays in the Ask Pellier dock and shows only while the
 * Builder view is on: it lets the agent load its own skills (progressive
 * disclosure, in-process only).
 */
import { useBuilderView, useSkillMode } from './preferences'

interface ToggleProps {
  id: string
  label: string
  checked: boolean
  onChange: (next: boolean) => void
  className?: string
}

function Toggle({ id, label, checked, onChange, className }: ToggleProps) {
  return (
    <label className={['tn-switch', className ?? ''].filter(Boolean).join(' ')} htmlFor={id}>
      <span className="tn-switch-label">{label}</span>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        className="tn-switch-track"
        data-state={checked ? 'on' : 'off'}
        onClick={() => onChange(!checked)}
      >
        <span className="tn-switch-thumb" aria-hidden="true" />
      </button>
    </label>
  )
}

export function BuilderViewToggle({ className }: { className?: string }) {
  const [builderView, setBuilderView] = useBuilderView()
  return (
    <Toggle
      id="tn-builder-view"
      label="Builder view"
      checked={builderView}
      onChange={setBuilderView}
      className={className}
    />
  )
}

export function SkillModeToggle() {
  const [builderView] = useBuilderView()
  const [skillMode, setSkillMode] = useSkillMode()
  if (!builderView) return null
  return (
    <div className="tn-switches" data-testid="skill-mode-switch">
      <Toggle
        id="tn-skill-mode"
        label="Agent loads its skills"
        checked={skillMode === 'on_demand'}
        onChange={next => setSkillMode(next ? 'on_demand' : 'fixed')}
      />
    </div>
  )
}
