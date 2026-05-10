/**
 * UserMessage — right-aligned ink bubble with asymmetric corners.
 *
 * Matches the editorial chat mockup: ink bg, cream text, 14px padding,
 * max-width 80%, right-aligned. Border-radius 14/14/4/14 gives it the
 * squared bottom-right corner.
 *
 * ``variant="resumed"`` renders a quieter italic pill — used as the
 * pseudo-user-turn that anchors a welcome-back response. No user
 * actually typed these words; the italic + muted treatment is the
 * tell.
 */

const INK = '#2d1810'
const INK_QUIET = '#a68668'
const CREAM = '#fbf4e8'

export interface UserMessageProps {
  text: string
  variant?: 'default' | 'resumed'
}

export default function UserMessage({ text, variant = 'default' }: UserMessageProps) {
  const isResumed = variant === 'resumed'
  return (
    <div
      data-testid="user-message"
      data-variant={variant}
      className="flex justify-end mb-4"
    >
      <div
        className={`max-w-[80%] text-[15px] leading-[1.5] px-[14px] py-[10px] ${isResumed ? 'italic' : ''}`}
        style={
          isResumed
            ? {
                background: 'transparent',
                color: INK_QUIET,
                border: `1px dashed ${INK_QUIET}50`,
                borderRadius: '14px 14px 4px 14px',
                letterSpacing: '-0.003em',
              }
            : {
                background: INK,
                color: CREAM,
                borderRadius: '14px 14px 4px 14px',
                letterSpacing: '-0.003em',
              }
        }
      >
        {text}
      </div>
    </div>
  )
}
