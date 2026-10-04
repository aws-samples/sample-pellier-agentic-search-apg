/**
 * The small switch in the panel header. Off by default, remembered per
 * browser. When on, a second switch lets the agent load its own skills
 * (progressive disclosure, in-process only).
 */
import type { SkillMode } from './preferences'

interface ToggleProps {
  id: string
  label: string
  checked: boolean
  onChange: (next: boolean) => void
}

function Toggle({ id, label, checked, onChange }: ToggleProps) {
  return (
    <label className="tn-switch" htmlFor={id}>
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

export interface BuilderViewSwitchProps {
  builderView: boolean
  onBuilderView: (on: boolean) => void
  skillMode?: SkillMode
  onSkillMode?: (mode: SkillMode) => void
}

export default function BuilderViewSwitch({
  builderView,
  onBuilderView,
  skillMode,
  onSkillMode,
}: BuilderViewSwitchProps) {
  return (
    <div className="tn-switches" data-testid="builder-view-switch">
      <Toggle id="tn-builder-view" label="Builder view" checked={builderView} onChange={onBuilderView} />
      {builderView && onSkillMode && (
        <Toggle
          id="tn-skill-mode"
          label="Agent loads its skills"
          checked={skillMode === 'on_demand'}
          onChange={next => onSkillMode(next ? 'on_demand' : 'fixed')}
        />
      )}
    </div>
  )
}
