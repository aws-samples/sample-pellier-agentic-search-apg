/**
 * The small light, dark and system control in the header.
 *
 * Three icon buttons in one pill. The pressed one is the shopper's choice;
 * the default is the system preference. Shared by the Storefront header and,
 * from cut 3, the Operator.
 */
import { Monitor, Moon, Sun } from 'lucide-react'
import { useEffect } from 'react'
import { applyTheme, resolveTheme, useTheme, type ThemeChoice } from './theme'
import './theme.css'

const OPTIONS: ReadonlyArray<{ choice: ThemeChoice; label: string; Icon: typeof Sun }> = [
  { choice: 'light', label: 'Light theme', Icon: Sun },
  { choice: 'dark', label: 'Dark theme', Icon: Moon },
  { choice: 'system', label: 'System theme', Icon: Monitor },
]

export default function ThemeControl({ className }: { className?: string }) {
  const { choice, setChoice } = useTheme()

  // The inline script set the attribute before first paint; this keeps it
  // true if the module and the script ever disagree on the stored choice.
  useEffect(() => {
    applyTheme(resolveTheme(choice))
  }, [choice])

  return (
    <div
      className={['pellier-theme-control', className ?? ''].filter(Boolean).join(' ')}
      role="group"
      aria-label="Theme"
      data-testid="theme-control"
    >
      {OPTIONS.map(({ choice: option, label, Icon }) => (
        <button
          key={option}
          type="button"
          className="pellier-theme-option"
          aria-label={label}
          title={label}
          aria-pressed={choice === option}
          data-choice={option}
          onClick={() => setChoice(option)}
        >
          <Icon size={15} strokeWidth={1.8} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}
